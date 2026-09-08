"""Request and response shapes for the API."""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
ASPECTS = ("clear", "caution", "danger")


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=64)
    description: str = ""

    @field_validator("slug")
    @classmethod
    def check_slug(cls, value: str) -> str:
        value = value.strip().lower()
        if not SLUG_PATTERN.match(value):
            raise ValueError("Use lowercase letters, numbers and hyphens, starting with a letter or number.")
        return value


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None


class EnvironmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=64)
    aspect: str = "clear"
    rank: int = 0

    @field_validator("slug")
    @classmethod
    def check_slug(cls, value: str) -> str:
        value = value.strip().lower()
        if not SLUG_PATTERN.match(value):
            raise ValueError("Use lowercase letters, numbers and hyphens, starting with a letter or number.")
        return value

    @field_validator("aspect")
    @classmethod
    def check_aspect(cls, value: str) -> str:
        if value not in ASPECTS:
            raise ValueError(f"Aspect must be one of: {', '.join(ASPECTS)}.")
        return value


class EnvironmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    aspect: str | None = None
    rank: int | None = None

    @field_validator("aspect")
    @classmethod
    def check_aspect(cls, value: str | None) -> str | None:
        if value is not None and value not in ASPECTS:
            raise ValueError(f"Aspect must be one of: {', '.join(ASPECTS)}.")
        return value


class EnvironmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    slug: str
    name: str
    aspect: str
    rank: int
    variable_count: int = 0
    updated_at: datetime


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    description: str
    created_at: datetime
    updated_at: datetime
    environments: list[EnvironmentRead] = []


def validate_key(value: str) -> str:
    value = value.strip()
    if not KEY_PATTERN.match(value):
        raise ValueError(
            "Names use capitals, numbers and underscores, and start with a letter — like DATABASE_URL."
        )
    return value


class VariableCreate(BaseModel):
    key: str = Field(min_length=1, max_length=255)
    value: str = ""
    is_secret: bool = True
    note: str = ""

    @field_validator("key")
    @classmethod
    def check_key(cls, value: str) -> str:
        return validate_key(value)


class VariableUpdate(BaseModel):
    key: str | None = Field(default=None, min_length=1, max_length=255)
    value: str | None = None
    is_secret: bool | None = None
    note: str | None = None

    @field_validator("key")
    @classmethod
    def check_key(cls, value: str | None) -> str | None:
        return None if value is None else validate_key(value)


class VariableRead(BaseModel):
    id: uuid.UUID
    environment_id: uuid.UUID
    key: str
    value: str            # masked when is_secret and not revealed
    revealed: bool
    is_secret: bool
    note: str
    version: int
    length: int
    created_at: datetime
    updated_at: datetime


class BulkImport(BaseModel):
    """Paste a .env file in; each non-comment line becomes a variable."""

    body: str
    overwrite: bool = True
    mark_secret: bool = True


class BulkImportResult(BaseModel):
    created: int
    updated: int
    skipped: int
    keys: list[str]


class RevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    action: str
    actor: str
    version: int
    created_at: datetime


class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID | None
    environment_id: uuid.UUID | None
    actor: str
    action: str
    summary: str
    alert: bool = False
    detail: dict
    created_at: datetime


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class TokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    environment_id: uuid.UUID
    name: str
    prefix: str
    last_used_at: datetime | None
    pull_count: int
    revoked_at: datetime | None
    created_at: datetime
    last_ip: str = ""
    last_version: str = ""


class SightingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ip: str
    user_agent: str
    pull_count: int
    first_seen_at: datetime
    last_seen_at: datetime


class ConsumerRead(TokenRead):
    """A token, plus whether whatever holds it is currently up to date."""

    up_to_date: bool
    reading_now: bool
    reads_in_a_minute: int
    sightings: list[SightingRead] = []


class PropagationRead(BaseModel):
    """After a change: who has the new value yet."""

    version: str
    consumers: int
    up_to_date: int
    waiting: list[str]


class TokenIssued(TokenRead):
    token: str  # shown once, at creation


class RuntimeConfig(BaseModel):
    """What a running application receives when it asks for its configuration."""

    project: str
    project_slug: str
    environment: str
    environment_slug: str
    aspect: str
    version: str
    generated_at: datetime
    values: dict[str, str]
