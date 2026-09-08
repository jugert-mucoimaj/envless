"""The activity stream the command centre reads, and a live feed of it."""

import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from .. import events
from ..db import get_db
from ..models import AuditEvent, Environment
from ..schemas import AuditRead

router = APIRouter(prefix="/api/activity", tags=["activity"])

CONSOLE_CHANNEL = "console"


@router.get("", response_model=list[AuditRead])
def list_activity(
    project_id: uuid.UUID | None = None,
    environment_id: uuid.UUID | None = None,
    alerts_only: bool = Query(False, description="Only entries that want attention."),
    since: datetime | None = Query(None, description="Only entries after this moment."),
    limit: int = Query(60, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[AuditEvent]:
    query = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
    if project_id is not None:
        query = query.where(AuditEvent.project_id == project_id)
    if environment_id is not None:
        query = query.where(AuditEvent.environment_id == environment_id)
    if alerts_only:
        # An alert about an environment that has since been deleted cannot be
        # acted on, so it stays in the trail but stops being counted.
        query = query.where(
            AuditEvent.alert.is_(True),
            AuditEvent.environment_id.is_not(None),
            exists().where(Environment.id == AuditEvent.environment_id),
        )
    if since is not None:
        query = query.where(AuditEvent.created_at > since)
    return list(db.scalars(query).all())


@router.get("/stream")
async def stream_activity(request: Request):
    """Server-sent events so the command centre reflects changes as they land."""

    async def pump():
        queue = events.subscribe(CONSOLE_CHANNEL)
        try:
            hello = {"reason": "connected", "at": datetime.now(timezone.utc).isoformat()}
            yield f"event: ready\ndata: {json.dumps(hello)}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=20)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"event: change\ndata: {json.dumps(payload)}\n\n"
        finally:
            events.unsubscribe(CONSOLE_CHANNEL, queue)

    return StreamingResponse(
        pump(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
