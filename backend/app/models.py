"""The envless control plane, in five tables.

A project owns environments; an environment owns variables. Every write to a
variable also writes a revision, so a value can be traced back and rolled
forward again. Access tokens are scoped to a single environment: that is what a
running app presents when it asks envless for its configuration.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    environments: Mapped[list["Environment"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Environment.rank",
    )


class Environment(Base):
    __tablename__ = "environments"
    __table_args__ = (UniqueConstraint("project_id", "slug", name="uq_environment_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    slug: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(120))
    # How much care a change here deserves: clear / caution / danger.
    # Drives the signal lamp in the command centre.
    aspect: Mapped[str] = mapped_column(String(16), default="clear")
    rank: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped[Project] = relationship(back_populates="environments")
    variables: Mapped[list["Variable"]] = relationship(
        back_populates="environment",
        cascade="all, delete-orphan",
        order_by="Variable.key",
    )
    tokens: Mapped[list["AccessToken"]] = relationship(
        back_populates="environment", cascade="all, delete-orphan"
    )


class Variable(Base):
    __tablename__ = "variables"
    __table_args__ = (UniqueConstraint("environment_id", "key", name="uq_variable_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    environment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("environments.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(255))
    value_encrypted: Mapped[str] = mapped_column(Text)
    # Secrets are masked in listings and only sent in full on an explicit reveal.
    is_secret: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    environment: Mapped[Environment] = relationship(back_populates="variables")


class Revision(Base):
    """One row per write. Deletes are recorded too, so nothing vanishes silently."""

    __tablename__ = "revisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    environment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("environments.id", ondelete="CASCADE"), index=True
    )
    variable_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    key: Mapped[str] = mapped_column(String(255), index=True)
    value_encrypted: Mapped[str] = mapped_column(Text, default="")
    previous_value_encrypted: Mapped[str] = mapped_column(Text, default="")
    action: Mapped[str] = mapped_column(String(16))  # created | updated | deleted | restored
    actor: Mapped[str] = mapped_column(String(120), default="operator")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AccessToken(Base):
    """What a running application presents to pull its configuration."""

    __tablename__ = "access_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    environment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("environments.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    prefix: Mapped[str] = mapped_column(String(32))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pull_count: Mapped[int] = mapped_column(Integer, default=0)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Where this token last read from, and which version it got. Together these
    # answer the question that matters after a rotation: has everything picked
    # the new value up yet?
    last_ip: Mapped[str] = mapped_column(String(64), default="")
    last_version: Mapped[str] = mapped_column(String(32), default="")

    environment: Mapped[Environment] = relationship(back_populates="tokens")
    sightings: Mapped[list["TokenSighting"]] = relationship(
        back_populates="token", cascade="all, delete-orphan"
    )


class TokenSighting(Base):
    """Every place a token has been used from.

    One row per (token, address). A token that has read from the same address
    for months and then appears somewhere new is the signal worth waking up
    for, and it is a lookup in this table rather than a security product.
    """

    __tablename__ = "token_sightings"
    __table_args__ = (UniqueConstraint("token_id", "ip", name="uq_sighting_source"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    token_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("access_tokens.id", ondelete="CASCADE"), index=True
    )
    ip: Mapped[str] = mapped_column(String(64))
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    pull_count: Mapped[int] = mapped_column(Integer, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    token: Mapped[AccessToken] = relationship(back_populates="sightings")


class AuditEvent(Base):
    """Everything that happened, in one stream the command centre can read."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    environment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    actor: Mapped[str] = mapped_column(String(120), default="operator")
    action: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text, default="")
    # Set on the handful of entries that want someone to look at them, so the
    # ordinary traffic of a working day never buries them.
    alert: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
