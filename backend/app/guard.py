"""Rate limiting and the two things worth waking someone up for.

An application reading its own configuration is a quiet client: it is told when
something changes, so it pulls at boot and rarely again. Anything pulling
hundreds of times a minute, or reading from an address it has never read from
before, is not behaving like an application.

Neither rule is clever. That is the point - both are a counter and a lookup,
and both explain themselves in one sentence when they fire.
"""

import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import AccessToken, TokenSighting
from .services import record_audit

WINDOW_SECONDS = 60

# Per-token hit times, kept in memory. A restart forgets them, which is the
# right trade for a counter that only has to be accurate over one minute.
_hits: dict[uuid.UUID, deque[float]] = defaultdict(deque)

# Alerts repeat as long as whatever caused them is still happening, so each
# kind is held back to one entry per token per interval.
_last_alert: dict[tuple[uuid.UUID, str], float] = {}
BURST_QUIET_SECONDS = 300
REFUSAL_QUIET_SECONDS = 60


def _recent(token_id: uuid.UUID) -> int:
    hits = _hits[token_id]
    cutoff = time.time() - WINDOW_SECONDS
    while hits and hits[0] < cutoff:
        hits.popleft()
    return len(hits)


def _should_say(token_id: uuid.UUID, kind: str, quiet_for: float) -> bool:
    now = time.time()
    if now - _last_alert.get((token_id, kind), 0.0) < quiet_for:
        return False
    _last_alert[(token_id, kind)] = now
    return True


def hits_in_window(token_id: uuid.UUID) -> int:
    """How many times this token has read in the last minute."""
    return _recent(token_id)


def take_slot(token_id: uuid.UUID) -> tuple[bool, int, int]:
    """Count this read. Returns (allowed, used, limit)."""
    limit = get_settings().runtime_rate_limit
    used = _recent(token_id)
    if used >= limit:
        return False, used, limit
    _hits[token_id].append(time.time())
    return True, used + 1, limit


def note_refusal(db: Session, token: AccessToken, ip: str, used: int, limit: int) -> None:
    """Record that a token was turned away, without writing a row per request."""
    if not _should_say(token.id, "refused", REFUSAL_QUIET_SECONDS):
        return
    record_audit(
        db,
        action="token.rate_limited",
        summary=f"Refused {token.name}: {used} reads a minute, over the limit of {limit}",
        environment_id=token.environment_id,
        actor=token.name,
        alert=True,
        detail={"token": token.name, "ip": ip, "used": used, "limit": limit},
    )
    db.commit()


def observe(
    db: Session,
    token: AccessToken,
    *,
    ip: str,
    user_agent: str,
    version: str,
    project_id: uuid.UUID | None = None,
) -> list[str]:
    """Record a successful read and raise anything that looks wrong.

    Returns the alerts raised, so a caller can log them.
    """
    now = datetime.now(timezone.utc)
    raised: list[str] = []

    known = db.scalars(
        select(TokenSighting).where(TokenSighting.token_id == token.id)
    ).all()
    here = next((sighting for sighting in known if sighting.ip == ip), None)

    if here is None:
        db.add(
            TokenSighting(
                token_id=token.id,
                ip=ip,
                user_agent=user_agent[:255],
                pull_count=1,
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        # The first address a token reads from is simply where it lives. A
        # second one, later, is the interesting case.
        if known:
            raised.append("unfamiliar_source")
            record_audit(
                db,
                action="token.unfamiliar_source",
                summary=(
                    f"{token.name} read from {ip}, an address it has not used before"
                ),
                project_id=project_id,
                environment_id=token.environment_id,
                actor=token.name,
                alert=True,
                detail={
                    "token": token.name,
                    "ip": ip,
                    "user_agent": user_agent[:255],
                    "known_addresses": sorted(s.ip for s in known),
                },
            )
    else:
        here.pull_count += 1
        here.last_seen_at = now
        if user_agent and here.user_agent != user_agent[:255]:
            here.user_agent = user_agent[:255]

    used = _recent(token.id)
    threshold = get_settings().runtime_burst_alert
    if used >= threshold and _should_say(token.id, "burst", BURST_QUIET_SECONDS):
        raised.append("burst")
        record_audit(
            db,
            action="token.burst",
            summary=f"{token.name} read {used} times in a minute, well above its normal rate",
            project_id=project_id,
            environment_id=token.environment_id,
            actor=token.name,
            alert=True,
            detail={"token": token.name, "ip": ip, "reads_in_a_minute": used},
        )

    token.last_used_at = now
    token.pull_count += 1
    token.last_ip = ip
    token.last_version = version
    db.commit()
    return raised


def forget(token_id: uuid.UUID) -> None:
    """Drop a revoked token's counters."""
    _hits.pop(token_id, None)
    for key in [key for key in _last_alert if key[0] == token_id]:
        _last_alert.pop(key, None)
