"""An envless client, small enough to read in one sitting.

This is the piece any application would carry. It does three things:

  1. Pulls the environment it was issued a token for, once, at boot.
  2. Holds a connection open and re-pulls the moment something changes, so a
     value can be corrected without a deploy or a restart.
  3. Answers `get`, `get_int` and `get_bool` in between.

If envless cannot be reached the application still starts, in a clearly
degraded state, and keeps trying in the background. Configuration going quiet
should never be the reason a service is down.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

import httpx

log = logging.getLogger("pigeon.config")

TRUTHY = {"1", "true", "yes", "on", "enabled"}
FALSEY = {"0", "false", "no", "off", "disabled"}


class EnvlessConfig:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        on_change: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.on_change = on_change

        self.values: dict[str, str] = {}
        self.project = ""
        self.environment = ""
        self.environment_slug = ""
        self.aspect = "clear"
        self.version = ""
        self.loaded_at: datetime | None = None
        self.connected = False
        self.last_error: str | None = None
        self.reloads = 0

        self._task: asyncio.Task | None = None

    # -- reading -----------------------------------------------------------

    def get(self, key: str, default: str = "") -> str:
        return self.values.get(key, default)

    def get_int(self, key: str, default: int) -> int:
        try:
            return int(self.values[key])
        except (KeyError, ValueError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        raw = self.values.get(key, "").strip().lower()
        if raw in TRUTHY:
            return True
        if raw in FALSEY:
            return False
        return default

    @property
    def healthy(self) -> bool:
        return bool(self.values) and self.last_error is None

    # -- fetching ----------------------------------------------------------

    async def load(self) -> bool:
        """Pull the current configuration. Returns whether anything changed."""
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.base_url}/v1/config", headers=headers)
        except httpx.HTTPError as exc:
            self.last_error = f"Cannot reach envless at {self.base_url} ({exc.__class__.__name__})"
            log.warning(self.last_error)
            return False

        if response.status_code == 401:
            self.last_error = "envless rejected this token. It may have been revoked."
            log.error(self.last_error)
            return False
        if response.status_code != 200:
            self.last_error = f"envless answered {response.status_code}."
            log.error(self.last_error)
            return False

        payload = response.json()
        changed = payload["version"] != self.version

        self.values = dict(payload["values"])
        self.project = payload["project"]
        self.environment = payload["environment"]
        self.environment_slug = payload["environment_slug"]
        self.aspect = payload["aspect"]
        self.version = payload["version"]
        self.loaded_at = datetime.now(timezone.utc)
        self.last_error = None
        if changed:
            self.reloads += 1
        return changed

    # -- staying current ---------------------------------------------------

    async def _watch(self) -> None:
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "text/event-stream"}
        backoff = 1.0

        while True:
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream(
                        "GET", f"{self.base_url}/v1/stream", headers=headers
                    ) as stream:
                        if stream.status_code != 200:
                            raise httpx.HTTPError(f"stream returned {stream.status_code}")
                        self.connected = True
                        backoff = 1.0
                        log.info("Listening to %s for configuration changes", self.environment)

                        async for line in stream.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            try:
                                notice = json.loads(line[5:].strip())
                            except json.JSONDecodeError:
                                continue
                            if notice.get("reason") == "connected":
                                continue
                            log.info("Configuration changed: %s", notice.get("reason"))
                            if await self.load() and self.on_change:
                                await self.on_change()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # the line dropped; take it up again
                self.connected = False
                log.warning("Lost the connection to envless (%s). Retrying.", exc)

            # While the line is down, poll, so a change is picked up anyway.
            await asyncio.sleep(backoff)
            if await self.load() and self.on_change:
                await self.on_change()
            backoff = min(backoff * 2, 15.0)

    async def start(self) -> None:
        await self.load()
        self._task = asyncio.create_task(self._watch())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self.connected = False
