"""Database engine, session factory, and the FastAPI session dependency."""

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# Columns added after the first version shipped. There are no migrations here
# on purpose - this is a local tool - but dropping someone's database to add a
# column would be rude, so the few additions are applied in place.
LATER_ADDITIONS = (
    "ALTER TABLE access_tokens ADD COLUMN IF NOT EXISTS last_ip VARCHAR(64) DEFAULT ''",
    "ALTER TABLE access_tokens ADD COLUMN IF NOT EXISTS last_version VARCHAR(32) DEFAULT ''",
    "ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS alert BOOLEAN DEFAULT FALSE",
    "CREATE INDEX IF NOT EXISTS ix_audit_events_alert ON audit_events (alert)",
)


def ensure_schema() -> None:
    """Create anything missing, then add the columns that came later."""
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        for statement in LATER_ADDITIONS:
            connection.execute(text(statement))


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
