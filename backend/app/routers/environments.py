"""A single environment: its variables, history, export, and access tokens."""

import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import events, guard
from ..crypto import decrypt, new_access_token
from ..db import get_db
from ..models import AccessToken, Environment, Revision, Variable
from ..schemas import (
    BulkImport,
    BulkImportResult,
    ConsumerRead,
    EnvironmentRead,
    EnvironmentUpdate,
    RevisionRead,
    SightingRead,
    TokenCreate,
    TokenIssued,
    TokenRead,
    VariableCreate,
    VariableRead,
    VariableUpdate,
    validate_key,
)
from ..services import (
    announce_change,
    config_version,
    parse_dotenv,
    record_audit,
    record_revision,
    render_dotenv,
    resolve_values,
    store_value,
    to_read,
)

router = APIRouter(prefix="/api/environments", tags=["environments"])


def get_environment(environment_id: uuid.UUID, db: Session = Depends(get_db)) -> Environment:
    environment = db.get(Environment, environment_id)
    if environment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No environment with that id.")
    return environment


def _env_read(environment: Environment) -> EnvironmentRead:
    return EnvironmentRead(
        id=environment.id,
        project_id=environment.project_id,
        slug=environment.slug,
        name=environment.name,
        aspect=environment.aspect,
        rank=environment.rank,
        variable_count=len(environment.variables),
        updated_at=environment.updated_at,
    )


@router.get("/{environment_id}", response_model=EnvironmentRead)
def read_environment(environment: Environment = Depends(get_environment)) -> EnvironmentRead:
    return _env_read(environment)


@router.patch("/{environment_id}", response_model=EnvironmentRead)
def update_environment(
    payload: EnvironmentUpdate,
    environment: Environment = Depends(get_environment),
    db: Session = Depends(get_db),
) -> EnvironmentRead:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(environment, field, value)
    record_audit(
        db,
        action="environment.updated",
        summary=f"Updated environment {environment.name}",
        project_id=environment.project_id,
        environment_id=environment.id,
    )
    db.commit()
    db.refresh(environment)
    return _env_read(environment)


@router.delete("/{environment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_environment(
    environment: Environment = Depends(get_environment), db: Session = Depends(get_db)
) -> None:
    name, project_id = environment.name, environment.project_id
    db.delete(environment)
    record_audit(
        db,
        action="environment.deleted",
        summary=f"Deleted environment {name}",
        project_id=project_id,
    )
    db.commit()


# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------


@router.get("/{environment_id}/variables", response_model=list[VariableRead])
def list_variables(
    reveal: bool = Query(False, description="Return secret values in full."),
    environment: Environment = Depends(get_environment),
) -> list[VariableRead]:
    return [to_read(variable, reveal=reveal) for variable in environment.variables]


@router.post(
    "/{environment_id}/variables",
    response_model=VariableRead,
    status_code=status.HTTP_201_CREATED,
)
def create_variable(
    payload: VariableCreate,
    environment: Environment = Depends(get_environment),
    db: Session = Depends(get_db),
) -> VariableRead:
    variable = Variable(
        environment_id=environment.id,
        key=payload.key,
        value_encrypted=store_value(payload.value),
        is_secret=payload.is_secret,
        note=payload.note,
        version=1,
    )
    db.add(variable)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{environment.name} already has a variable called {payload.key}.",
        ) from exc

    record_revision(
        db,
        variable=variable,
        environment_id=environment.id,
        key=variable.key,
        action="created",
        value_encrypted=variable.value_encrypted,
        version=1,
    )
    record_audit(
        db,
        action="variable.created",
        summary=f"Added {variable.key} to {environment.name}",
        project_id=environment.project_id,
        environment_id=environment.id,
        detail={"key": variable.key},
    )
    db.commit()
    db.refresh(variable)
    announce_change(db, environment.id, f"{variable.key} added")
    return to_read(variable, reveal=True)


@router.get("/{environment_id}/variables/{variable_id}", response_model=VariableRead)
def read_variable(
    variable_id: uuid.UUID,
    reveal: bool = Query(False),
    environment: Environment = Depends(get_environment),
    db: Session = Depends(get_db),
) -> VariableRead:
    variable = db.get(Variable, variable_id)
    if variable is None or variable.environment_id != environment.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No variable with that id here.")
    return to_read(variable, reveal=reveal)


@router.patch("/{environment_id}/variables/{variable_id}", response_model=VariableRead)
def update_variable(
    variable_id: uuid.UUID,
    payload: VariableUpdate,
    environment: Environment = Depends(get_environment),
    db: Session = Depends(get_db),
) -> VariableRead:
    variable = db.get(Variable, variable_id)
    if variable is None or variable.environment_id != environment.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No variable with that id here.")

    fields = payload.model_dump(exclude_unset=True)
    previous_encrypted = variable.value_encrypted
    previous_key = variable.key
    previous_secrecy = variable.is_secret
    value_changed = False

    if fields.get("value") is not None and decrypt(previous_encrypted) != fields["value"]:
        variable.value_encrypted = store_value(fields["value"])
        value_changed = True
    if fields.get("key") is not None:
        variable.key = fields["key"]
    if fields.get("is_secret") is not None:
        variable.is_secret = fields["is_secret"]
    if fields.get("note") is not None:
        variable.note = fields["note"]

    renamed = variable.key != previous_key
    # Whether a value is masked is not cosmetic - it decides who can read it
    # off a screen - so a change to it is recorded like any other.
    secrecy_changed = variable.is_secret != previous_secrecy
    if value_changed or renamed:
        variable.version += 1

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{environment.name} already has a variable called {fields.get('key')}.",
        ) from exc

    if value_changed or renamed:
        record_revision(
            db,
            variable=variable,
            environment_id=environment.id,
            key=variable.key,
            action="updated",
            value_encrypted=variable.value_encrypted,
            previous_value_encrypted=previous_encrypted,
            version=variable.version,
        )
        summary = (
            f"Renamed {previous_key} to {variable.key} in {environment.name}"
            if renamed
            else f"Updated {variable.key} in {environment.name}"
        )
        record_audit(
            db,
            action="variable.updated",
            summary=summary,
            project_id=environment.project_id,
            environment_id=environment.id,
            detail={"key": variable.key, "previous_key": previous_key},
        )

    if secrecy_changed:
        record_audit(
            db,
            action="variable.secrecy_changed",
            summary=(
                f"{variable.key} in {environment.name} is now "
                f"{'masked as a secret' if variable.is_secret else 'shown in full'}"
            ),
            project_id=environment.project_id,
            environment_id=environment.id,
            detail={"key": variable.key, "is_secret": variable.is_secret},
        )

    db.commit()
    db.refresh(variable)
    if value_changed or renamed:
        announce_change(db, environment.id, f"{variable.key} updated")
    return to_read(variable, reveal=True)


@router.delete(
    "/{environment_id}/variables/{variable_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_variable(
    variable_id: uuid.UUID,
    environment: Environment = Depends(get_environment),
    db: Session = Depends(get_db),
) -> None:
    variable = db.get(Variable, variable_id)
    if variable is None or variable.environment_id != environment.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No variable with that id here.")

    key = variable.key
    record_revision(
        db,
        variable=None,
        environment_id=environment.id,
        key=key,
        action="deleted",
        previous_value_encrypted=variable.value_encrypted,
        version=variable.version,
    )
    record_audit(
        db,
        action="variable.deleted",
        summary=f"Removed {key} from {environment.name}",
        project_id=environment.project_id,
        environment_id=environment.id,
        detail={"key": key},
    )
    db.delete(variable)
    db.commit()
    announce_change(db, environment.id, f"{key} removed")


@router.post("/{environment_id}/variables/import", response_model=BulkImportResult)
def import_variables(
    payload: BulkImport,
    environment: Environment = Depends(get_environment),
    db: Session = Depends(get_db),
) -> BulkImportResult:
    """Paste a .env file and have every line land as a variable."""
    existing = {variable.key: variable for variable in environment.variables}
    created = updated = skipped = 0
    touched: list[str] = []

    for key, value in parse_dotenv(payload.body):
        try:
            key = validate_key(key)
        except ValueError:
            skipped += 1
            continue

        current = existing.get(key)
        if current is None:
            variable = Variable(
                environment_id=environment.id,
                key=key,
                value_encrypted=store_value(value),
                is_secret=payload.mark_secret,
                version=1,
            )
            db.add(variable)
            db.flush()
            existing[key] = variable
            record_revision(
                db,
                variable=variable,
                environment_id=environment.id,
                key=key,
                action="created",
                value_encrypted=variable.value_encrypted,
                version=1,
            )
            created += 1
            touched.append(key)
        elif payload.overwrite and decrypt(current.value_encrypted) != value:
            previous = current.value_encrypted
            current.value_encrypted = store_value(value)
            current.version += 1
            record_revision(
                db,
                variable=current,
                environment_id=environment.id,
                key=key,
                action="updated",
                value_encrypted=current.value_encrypted,
                previous_value_encrypted=previous,
                version=current.version,
            )
            updated += 1
            touched.append(key)
        else:
            skipped += 1

    record_audit(
        db,
        action="variables.imported",
        summary=f"Imported {created + updated} variables into {environment.name}",
        project_id=environment.project_id,
        environment_id=environment.id,
        detail={"created": created, "updated": updated, "skipped": skipped},
    )
    db.commit()
    if created or updated:
        announce_change(db, environment.id, "imported from .env")
    return BulkImportResult(created=created, updated=updated, skipped=skipped, keys=touched)


@router.get("/{environment_id}/export")
def export_environment(
    fmt: str = Query("dotenv", pattern="^(dotenv|json)$", alias="format"),
    environment: Environment = Depends(get_environment),
    db: Session = Depends(get_db),
) -> Response:
    values = resolve_values(db, environment.id)
    record_audit(
        db,
        action="environment.exported",
        summary=f"Exported {environment.name} as {fmt}",
        project_id=environment.project_id,
        environment_id=environment.id,
    )
    db.commit()

    if fmt == "json":
        body = json.dumps(values, indent=2, sort_keys=True) + "\n"
        media_type = "application/json"
        filename = f"{environment.slug}.json"
    else:
        body = render_dotenv(values)
        media_type = "text/plain; charset=utf-8"
        filename = f"{environment.slug}.env"

    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{environment_id}/history", response_model=list[RevisionRead])
def environment_history(
    limit: int = Query(50, ge=1, le=500),
    environment: Environment = Depends(get_environment),
    db: Session = Depends(get_db),
) -> list[Revision]:
    return list(
        db.scalars(
            select(Revision)
            .where(Revision.environment_id == environment.id)
            .order_by(Revision.created_at.desc())
            .limit(limit)
        ).all()
    )


# ---------------------------------------------------------------------------
# Access tokens - what a running app presents to pull its configuration
# ---------------------------------------------------------------------------


@router.get("/{environment_id}/tokens", response_model=list[TokenRead])
def list_tokens(
    environment: Environment = Depends(get_environment), db: Session = Depends(get_db)
) -> list[AccessToken]:
    return list(
        db.scalars(
            select(AccessToken)
            .where(AccessToken.environment_id == environment.id)
            .order_by(AccessToken.created_at.desc())
        ).all()
    )


@router.post(
    "/{environment_id}/tokens",
    response_model=TokenIssued,
    status_code=status.HTTP_201_CREATED,
)
def issue_token(
    payload: TokenCreate,
    environment: Environment = Depends(get_environment),
    db: Session = Depends(get_db),
) -> TokenIssued:
    plaintext, prefix, token_hash = new_access_token()
    token = AccessToken(
        environment_id=environment.id,
        name=payload.name,
        prefix=prefix,
        token_hash=token_hash,
    )
    db.add(token)
    record_audit(
        db,
        action="token.issued",
        summary=f"Issued token {payload.name} for {environment.name}",
        project_id=environment.project_id,
        environment_id=environment.id,
        detail={"prefix": prefix},
    )
    db.commit()
    db.refresh(token)
    return TokenIssued(
        id=token.id,
        environment_id=token.environment_id,
        name=token.name,
        prefix=token.prefix,
        last_used_at=token.last_used_at,
        pull_count=token.pull_count,
        revoked_at=token.revoked_at,
        created_at=token.created_at,
        token=plaintext,
    )


@router.delete("/{environment_id}/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_token(
    token_id: uuid.UUID,
    environment: Environment = Depends(get_environment),
    db: Session = Depends(get_db),
) -> None:
    token = db.get(AccessToken, token_id)
    if token is None or token.environment_id != environment.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No token with that id here.")
    name = token.name
    guard.forget(token.id)
    db.delete(token)
    record_audit(
        db,
        action="token.revoked",
        summary=f"Revoked token {name}",
        project_id=environment.project_id,
        environment_id=environment.id,
    )
    db.commit()


# A token that has read recently is something that is actually running. Older
# than this and it is a token, not a consumer.
LIVE_WINDOW = timedelta(minutes=10)


def _live_tokens(db: Session, environment_id: uuid.UUID) -> list[AccessToken]:
    since = datetime.now(timezone.utc) - LIVE_WINDOW
    return list(
        db.scalars(
            select(AccessToken)
            .where(
                AccessToken.environment_id == environment_id,
                AccessToken.revoked_at.is_(None),
                AccessToken.last_used_at.is_not(None),
                AccessToken.last_used_at >= since,
            )
            .order_by(AccessToken.last_used_at.desc())
        ).all()
    )


@router.get("/{environment_id}/status")
def environment_status(
    environment: Environment = Depends(get_environment), db: Session = Depends(get_db)
) -> dict:
    """What the panel shows: the current version, and who is on it yet."""
    values = resolve_values(db, environment.id)
    version = config_version(values)
    live = _live_tokens(db, environment.id)
    behind = [token.name for token in live if token.last_version != version]
    return {
        "environment_id": str(environment.id),
        "version": version,
        "variable_count": len(values),
        "connected_apps": events.listener_count(str(environment.id)),
        "consumers": len(live),
        "up_to_date": len(live) - len(behind),
        "waiting": behind,
    }


@router.get("/{environment_id}/consumers", response_model=list[ConsumerRead])
def environment_consumers(
    environment: Environment = Depends(get_environment), db: Session = Depends(get_db)
) -> list[ConsumerRead]:
    """Every token issued here, and what it has actually been doing."""
    version = config_version(resolve_values(db, environment.id))
    recent = datetime.now(timezone.utc) - LIVE_WINDOW
    tokens = db.scalars(
        select(AccessToken)
        .where(AccessToken.environment_id == environment.id)
        .order_by(AccessToken.created_at.desc())
    ).all()

    return [
        ConsumerRead(
            id=token.id,
            environment_id=token.environment_id,
            name=token.name,
            prefix=token.prefix,
            last_used_at=token.last_used_at,
            pull_count=token.pull_count,
            revoked_at=token.revoked_at,
            created_at=token.created_at,
            last_ip=token.last_ip or "",
            last_version=token.last_version or "",
            up_to_date=token.last_version == version,
            reading_now=bool(token.last_used_at and token.last_used_at >= recent),
            reads_in_a_minute=guard.hits_in_window(token.id),
            sightings=[SightingRead.model_validate(s) for s in token.sightings],
        )
        for token in tokens
    ]
