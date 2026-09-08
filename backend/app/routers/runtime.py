"""The runtime API: how a deployed application gets its configuration.

An app presents an environment-scoped access token and receives the resolved
key/value map. `/v1/config` is a plain read with an ETag so repeat polls are
cheap; `/v1/stream` holds the connection open and pushes a notice the moment
the command centre changes something, so an app can pick up a new value
without a restart.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import events, guard
from ..config import get_settings
from ..crypto import hash_token
from ..db import SessionLocal, get_db
from ..models import AccessToken, Environment, Project
from ..schemas import RuntimeConfig
from ..services import config_version, record_audit, render_dotenv, resolve_values

router = APIRouter(prefix="/v1", tags=["runtime"])

UNAUTHORIZED = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    "Present a valid envless access token to read this configuration.",
    headers={"WWW-Authenticate": "Bearer"},
)


def _extract_token(authorization: str | None, header_token: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if header_token:
        return header_token.strip()
    raise UNAUTHORIZED


def _lookup(db: Session, plaintext: str) -> AccessToken:
    token = db.scalar(select(AccessToken).where(AccessToken.token_hash == hash_token(plaintext)))
    if token is None or token.revoked_at is not None:
        raise UNAUTHORIZED
    return token


def authenticate(
    authorization: str | None = Header(default=None),
    x_envless_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AccessToken:
    return _lookup(db, _extract_token(authorization, x_envless_token))


def caller_address(request: Request) -> str:
    """The address the read came from.

    A forwarded header is only believed when the deployment says something
    trustworthy is setting it; otherwise a caller could name its own address
    and walk straight past the unfamiliar-source check.
    """
    if get_settings().trust_proxy_header:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def admit(request: Request, db: Session, token: AccessToken) -> str:
    """Rate-limit a read, and refuse it if the token is going too fast."""
    ip = caller_address(request)
    allowed, used, limit = guard.take_slot(token.id)
    if not allowed:
        guard.note_refusal(db, token, ip, used, limit)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"This token has read {used} times in the last minute, over its limit of {limit}.",
            headers={"Retry-After": "60"},
        )
    return ip


def _mark_used(
    request: Request, db: Session, token: AccessToken, ip: str, version: str
) -> None:
    """Record the read, and raise anything about it that looks wrong."""
    environment = db.get(Environment, token.environment_id)
    guard.observe(
        db,
        token,
        ip=ip,
        user_agent=request.headers.get("user-agent", "")[:255],
        version=version,
        project_id=environment.project_id if environment else None,
    )


def _build(db: Session, environment: Environment) -> RuntimeConfig:
    project = db.get(Project, environment.project_id)
    values = resolve_values(db, environment.id)
    return RuntimeConfig(
        project=project.name if project else "",
        project_slug=project.slug if project else "",
        environment=environment.name,
        environment_slug=environment.slug,
        aspect=environment.aspect,
        version=config_version(values),
        generated_at=datetime.now(timezone.utc),
        values=values,
    )


@router.get("/config", response_model=RuntimeConfig)
def read_config(
    request: Request,
    response: Response,
    if_none_match: str | None = Header(default=None),
    token: AccessToken = Depends(authenticate),
    db: Session = Depends(get_db),
):
    environment = db.get(Environment, token.environment_id)
    if environment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This token's environment no longer exists.")

    ip = admit(request, db, token)
    config = _build(db, environment)
    etag = f'"{config.version}"'
    _mark_used(request, db, token, ip, config.version)

    if if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "no-cache"
    return config


@router.get("/config.env")
def read_config_dotenv(
    request: Request,
    token: AccessToken = Depends(authenticate),
    db: Session = Depends(get_db),
) -> Response:
    """The same configuration as .env text, for anything that reads a file."""
    environment = db.get(Environment, token.environment_id)
    if environment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This token's environment no longer exists.")
    ip = admit(request, db, token)
    values = resolve_values(db, environment.id)
    version = config_version(values)
    _mark_used(request, db, token, ip, version)
    return Response(
        content=render_dotenv(values),
        media_type="text/plain; charset=utf-8",
        headers={"ETag": f'"{version}"'},
    )


@router.get("/whoami")
def whoami(
    request: Request,
    token: AccessToken = Depends(authenticate),
    db: Session = Depends(get_db),
) -> dict:
    """Lets an app confirm which environment its token opens, without values."""
    admit(request, db, token)
    environment = db.get(Environment, token.environment_id)
    if environment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This token's environment no longer exists.")
    project = db.get(Project, environment.project_id)
    return {
        "token_name": token.name,
        "token_prefix": token.prefix,
        "project": project.name if project else "",
        "environment": environment.name,
        "environment_slug": environment.slug,
        "aspect": environment.aspect,
    }


def _resolve_stream_token(plaintext: str, ip: str, user_agent: str) -> tuple[uuid.UUID, str]:
    """Runs on a worker thread: validate the token and note the connection."""
    with SessionLocal() as db:
        token = _lookup(db, plaintext)
        environment = db.get(Environment, token.environment_id)
        if environment is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "This token's environment no longer exists."
            )
        record_audit(
            db,
            action="app.connected",
            summary=f"{token.name} opened a live connection to {environment.name} from {ip}",
            project_id=environment.project_id,
            environment_id=environment.id,
            detail={"ip": ip},
        )
        db.commit()
        # A connection is a read from somewhere, so it is checked the same way.
        guard.observe(
            db,
            token,
            ip=ip,
            user_agent=user_agent,
            version=config_version(resolve_values(db, environment.id)),
            project_id=environment.project_id,
        )
        return environment.id, token.name


def _current_version(environment_id: uuid.UUID) -> str:
    with SessionLocal() as db:
        return config_version(resolve_values(db, environment_id))


@router.get("/stream")
async def stream_config(
    request: Request,
    authorization: str | None = Header(default=None),
    x_envless_token: str | None = Header(default=None),
):
    """Server-sent events: one `change` message per edit in the command centre."""
    plaintext = _extract_token(authorization, x_envless_token)
    environment_id, token_name = await run_in_threadpool(
        _resolve_stream_token,
        plaintext,
        caller_address(request),
        request.headers.get("user-agent", "")[:255],
    )
    channel = str(environment_id)

    async def pump():
        queue = events.subscribe(channel)
        try:
            version = await run_in_threadpool(_current_version, environment_id)
            opening = {
                "version": version,
                "reason": "connected",
                "at": datetime.now(timezone.utc).isoformat(),
            }
            yield f"event: ready\ndata: {json.dumps(opening)}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=20)
                except asyncio.TimeoutError:
                    # Keeps proxies from closing an idle connection.
                    yield ": keep-alive\n\n"
                    continue
                yield f"event: change\ndata: {json.dumps(payload)}\n\n"
        finally:
            events.unsubscribe(channel, queue)

    return StreamingResponse(
        pump(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Envless-Client": token_name,
        },
    )
