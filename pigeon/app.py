"""Pigeon - transactional messaging, configured entirely by envless.

Pigeon holds no settings of its own. Its own .env carries three lines: where
envless is, the token that proves which environment it may read, and the port
to listen on. Everything else - the sending route, the rate limit, which
features are on, whether it is in maintenance - comes from envless at boot and
is corrected in place when someone changes a value in the command centre.

That is the point of the app: change RATE_LIMIT_PER_MINUTE in envless and
Pigeon starts enforcing the new number without a restart.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from config_client import EnvlessConfig

BASE = Path(__file__).resolve().parent
# Defaults to the .env beside this file. A container stack points it somewhere
# shared instead, so it never writes over the local setup's token. Values
# already in the environment win over the file either way.
load_dotenv(os.getenv("ENVLESS_ENV_FILE") or BASE / ".env")

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s  %(message)s")
log = logging.getLogger("pigeon")

ENVLESS_URL = os.getenv("ENVLESS_URL", "http://127.0.0.1:8000")
ENVLESS_TOKEN = os.getenv("ENVLESS_TOKEN", "")
PORT = int(os.getenv("PORT", "8100"))
# Loopback is the right default for something run on a laptop; a container has
# to listen on every interface for its published port to reach anything.
HOST = os.getenv("HOST", "127.0.0.1")

templates = Jinja2Templates(directory=str(BASE / "templates"))

# What Pigeon has done since it started. Nothing here survives a restart -
# it is a demonstration, not a mail server.
outbox: deque[dict] = deque(maxlen=40)
sent_at: deque[float] = deque(maxlen=5000)

# Browsers watching this page, so a configuration change reaches the screen.
watchers: set[asyncio.Queue] = set()


def announce(reason: str) -> None:
    for queue in list(watchers):
        try:
            queue.put_nowait(reason)
        except asyncio.QueueFull:
            pass


async def on_config_change() -> None:
    log.info("Reloaded configuration, now at version %s", config.version)
    announce("configuration")


config = EnvlessConfig(ENVLESS_URL, ENVLESS_TOKEN, on_change=on_config_change)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not ENVLESS_TOKEN:
        log.error(
            "No ENVLESS_TOKEN. Run backend/seed.py, or issue a token in the command "
            "centre and put it in pigeon/.env."
        )
    await config.start()
    if config.healthy:
        log.info(
            "Booted on %s / %s with %d values (version %s)",
            config.project,
            config.environment,
            len(config.values),
            config.version,
        )
    yield
    await config.stop()


app = FastAPI(title="Pigeon", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Behaviour that the configuration actually decides
# ---------------------------------------------------------------------------


def rate_limit() -> int:
    return config.get_int("RATE_LIMIT_PER_MINUTE", 60)


def recent_sends() -> int:
    cutoff = time.time() - 60
    while sent_at and sent_at[0] < cutoff:
        sent_at.popleft()
    return len(sent_at)


def redact(value: str) -> str:
    """A connection string is fine for Pigeon to hold and wrong to put on screen."""
    if not value:
        return "unset"
    if "://" in value and "@" in value:
        scheme, _, rest = value.partition("://")
        credentials, _, host = rest.partition("@")
        user = credentials.split(":")[0]
        return f"{scheme}://{user}:****@{host}"
    return value if len(value) <= 12 else f"{value[:6]}…{value[-4:]}"


def delivery_route() -> str:
    host = config.get("SMTP_HOST", "unset")
    port = config.get("SMTP_PORT", "?")
    return f"{host}:{port}"


def state() -> dict:
    """Everything the page renders, in one place, straight from configuration."""
    limit = rate_limit()
    used = recent_sends()
    return {
        "service_name": config.get("SERVICE_NAME", "Pigeon"),
        "region": config.get("REGION", "unset"),
        "accent": config.get("BRAND_ACCENT", "#2f6f4e"),
        "sender": config.get("SENDER_ADDRESS", "unset"),
        "support_email": config.get("SUPPORT_EMAIL", ""),
        "route": delivery_route(),
        "smtp_user": config.get("SMTP_USERNAME", "unset"),
        "store": redact(config.get("DATABASE_URL")),
        "log_level": config.get("LOG_LEVEL", "info"),
        "retries": config.get_int("RETRY_ATTEMPTS", 1),
        "limit": limit,
        "used": used,
        "remaining": max(0, limit - used),
        "maintenance": config.get_bool("MAINTENANCE_MODE"),
        "batch_send": config.get_bool("FEATURE_BATCH_SEND"),
        "receipts": config.get_bool("FEATURE_DELIVERY_RECEIPTS"),
        "project": config.project,
        "environment": config.environment or "unknown",
        "environment_slug": config.environment_slug,
        "aspect": config.aspect,
        "version": config.version,
        "value_count": len(config.values),
        "connected": config.connected,
        "healthy": config.healthy,
        "error": config.last_error,
        "reloads": config.reloads,
        "loaded_at": config.loaded_at.isoformat() if config.loaded_at else None,
        "envless_url": ENVLESS_URL,
        "outbox": list(outbox),
    }


@app.get("/", response_class=HTMLResponse)
def page(request: Request):
    return templates.TemplateResponse(request, "index.html", {"s": state()})


@app.get("/api/state")
def api_state() -> JSONResponse:
    return JSONResponse(state())


@app.post("/send")
async def send(
    recipient: str = Form(""),
    subject: str = Form(""),
    count: int = Form(1),
) -> JSONResponse:
    """A simulated send, gated by whatever envless currently says."""
    if config.get_bool("MAINTENANCE_MODE"):
        return JSONResponse(
            {
                "ok": False,
                "message": "Pigeon is in maintenance. Turn MAINTENANCE_MODE off in envless to send.",
            },
            status_code=503,
        )

    recipient = recipient.strip()
    if "@" not in recipient:
        return JSONResponse(
            {"ok": False, "message": "Enter an address to send to."}, status_code=422
        )

    count = max(1, min(count, 25))
    if count > 1 and not config.get_bool("FEATURE_BATCH_SEND"):
        return JSONResponse(
            {
                "ok": False,
                "message": "Batch sending is off in this environment. Turn FEATURE_BATCH_SEND on in envless.",
            },
            status_code=409,
        )

    limit = rate_limit()
    if recent_sends() + count > limit:
        return JSONResponse(
            {
                "ok": False,
                "message": (
                    f"That would pass this environment's limit of {limit} a minute. "
                    f"{max(0, limit - recent_sends())} left. Raise RATE_LIMIT_PER_MINUTE in envless."
                ),
            },
            status_code=429,
        )

    now = datetime.now(timezone.utc)
    for index in range(count):
        sent_at.append(time.time())
        outbox.appendleft(
            {
                "id": uuid.uuid4().hex[:8],
                "at": now.strftime("%H:%M:%S"),
                "to": recipient,
                "subject": subject.strip() or "(no subject)",
                "via": delivery_route(),
                "from": config.get("SENDER_ADDRESS", "unset"),
                "attempts": config.get_int("RETRY_ATTEMPTS", 1),
                "receipt": uuid.uuid4().hex[:12] if config.get_bool("FEATURE_DELIVERY_RECEIPTS") else None,
                "environment": config.environment,
                "config_version": config.version,
                "batch": f"{index + 1}/{count}" if count > 1 else None,
            }
        )

    announce("sent")
    return JSONResponse(
        {
            "ok": True,
            "message": f"Handed {count} message{'s' if count > 1 else ''} to {delivery_route()}.",
        }
    )


@app.get("/events")
async def events(request: Request):
    """Tells this page's browser when the configuration underneath it moved."""

    async def pump():
        queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        watchers.add(queue)
        try:
            yield f"data: {json.dumps({'reason': 'ready'})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    reason = await asyncio.wait_for(queue.get(), timeout=20)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {json.dumps({'reason': reason})}\n\n"
        finally:
            watchers.discard(queue)

    return StreamingResponse(
        pump(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/health")
def health() -> dict:
    return {
        "service": "pigeon",
        "configured": config.healthy,
        "environment": config.environment,
        "config_version": config.version,
        "listening_to_envless": config.connected,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
