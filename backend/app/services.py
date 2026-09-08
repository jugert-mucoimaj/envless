"""Shared work that several routers need: audit trail, config versions,
dotenv parsing, and the read shape for a variable.
"""

import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import events
from .crypto import decrypt, encrypt, mask
from .models import AuditEvent, Revision, Variable
from .schemas import VariableRead


def record_audit(
    db: Session,
    *,
    action: str,
    summary: str,
    project_id: uuid.UUID | None = None,
    environment_id: uuid.UUID | None = None,
    actor: str = "operator",
    alert: bool = False,
    detail: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        project_id=project_id,
        environment_id=environment_id,
        actor=actor,
        action=action,
        summary=summary,
        alert=alert,
        detail=detail or {},
    )
    db.add(event)
    return event


def record_revision(
    db: Session,
    *,
    variable: Variable | None,
    environment_id: uuid.UUID,
    key: str,
    action: str,
    value_encrypted: str = "",
    previous_value_encrypted: str = "",
    actor: str = "operator",
    version: int = 1,
) -> None:
    db.add(
        Revision(
            environment_id=environment_id,
            variable_id=variable.id if variable else None,
            key=key,
            action=action,
            value_encrypted=value_encrypted,
            previous_value_encrypted=previous_value_encrypted,
            actor=actor,
            version=version,
        )
    )


def resolve_values(db: Session, environment_id: uuid.UUID) -> dict[str, str]:
    """The plaintext map an application actually runs on."""
    rows = db.scalars(
        select(Variable).where(Variable.environment_id == environment_id).order_by(Variable.key)
    ).all()
    return {row.key: decrypt(row.value_encrypted) for row in rows}


def config_version(values: dict[str, str]) -> str:
    """A short digest of the resolved config; changes whenever any value does."""
    digest = hashlib.sha256()
    for key in sorted(values):
        digest.update(key.encode())
        digest.update(b"\x00")
        digest.update(values[key].encode())
        digest.update(b"\x1e")
    return digest.hexdigest()[:16]


CONSOLE_CHANNEL = "console"


def announce_change(db: Session, environment_id: uuid.UUID, reason: str) -> str:
    """Tell every app subscribed to this environment that its config moved.

    The same notice also goes to the console channel, which is how the command
    centre keeps its panel current without polling.
    """
    values = resolve_values(db, environment_id)
    version = config_version(values)
    payload = {
        "environment_id": str(environment_id),
        "version": version,
        "reason": reason,
        "at": datetime.now(timezone.utc).isoformat(),
        "keys": sorted(values),
    }
    events.publish(str(environment_id), payload)
    events.publish(CONSOLE_CHANNEL, payload)
    return version


def to_read(variable: Variable, *, reveal: bool = False) -> VariableRead:
    plaintext = decrypt(variable.value_encrypted)
    hidden = variable.is_secret and not reveal
    return VariableRead(
        id=variable.id,
        environment_id=variable.environment_id,
        key=variable.key,
        value=mask(plaintext) if hidden else plaintext,
        revealed=not hidden,
        is_secret=variable.is_secret,
        note=variable.note,
        version=variable.version,
        length=len(plaintext),
        created_at=variable.created_at,
        updated_at=variable.updated_at,
    )


def parse_dotenv(body: str) -> list[tuple[str, str]]:
    """Parse pasted .env text into (key, value) pairs, tolerantly.

    Handles `export ` prefixes, `#` comments, blank lines, and single or double
    quoted values. Lines that are not `KEY=value` are ignored rather than
    failing the whole paste.
    """
    pairs: list[tuple[str, str]] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            pairs.append((key, value))
    return pairs


def render_dotenv(values: dict[str, str]) -> str:
    """Serialise a config map back into .env text, quoting where needed."""
    lines = []
    for key in sorted(values):
        value = values[key]
        if value == "" or any(ch in value for ch in ' #"\'\n\t'):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\n")
            lines.append(f'{key}="{escaped}"')
        else:
            lines.append(f"{key}={value}")
    return "\n".join(lines) + ("\n" if lines else "")


def store_value(plaintext: str) -> str:
    return encrypt(plaintext)
