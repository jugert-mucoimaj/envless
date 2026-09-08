"""Fill a fresh database with something worth looking at.

Creates two projects. The important one is Pigeon, the transactional messaging
service in ../pigeon that actually boots on this configuration, so the three
environments here are the three ways that app can behave.

Run it with:  .venv/Scripts/python.exe seed.py
Add --reset to drop everything first.
"""

import sys
from pathlib import Path

from sqlalchemy import select

from app.crypto import new_access_token
from app.db import Base, SessionLocal, engine
from app.models import AccessToken, Environment, Project, Variable
from app.services import record_audit, record_revision, store_value

REPO_ROOT = Path(__file__).resolve().parent.parent

PIGEON = {
    "slug": "pigeon",
    "name": "Pigeon",
    "description": "Transactional messaging. Sends the receipts, resets and alerts.",
    "environments": [
        {
            "slug": "development",
            "name": "Development",
            "aspect": "clear",
            "rank": 0,
            "variables": {
                "SERVICE_NAME": ("Pigeon (local)", False),
                "REGION": ("local", False),
                "DATABASE_URL": ("postgresql://postgres:kali@localhost:5432/pigeon_dev", True),
                "SMTP_HOST": ("localhost", False),
                "SMTP_PORT": ("1025", False),
                "SMTP_USERNAME": ("dev", False),
                "SMTP_PASSWORD": ("dev-mailpit-password", True),
                "SENDER_ADDRESS": ("pigeon@localhost", False),
                "RATE_LIMIT_PER_MINUTE": ("1000", False),
                "RETRY_ATTEMPTS": ("1", False),
                "FEATURE_BATCH_SEND": ("true", False),
                "FEATURE_DELIVERY_RECEIPTS": ("true", False),
                "MAINTENANCE_MODE": ("false", False),
                "BRAND_ACCENT": ("#2F6F4E", False),
                "SUPPORT_EMAIL": ("dev-null@pigeon.test", False),
                "LOG_LEVEL": ("debug", False),
                "WEBHOOK_SIGNING_SECRET": ("whsec_local_do_not_use", True),
            },
        },
        {
            "slug": "staging",
            "name": "Staging",
            "aspect": "caution",
            "rank": 1,
            "variables": {
                "SERVICE_NAME": ("Pigeon Staging", False),
                "REGION": ("eu-west-1", False),
                "DATABASE_URL": ("postgresql://pigeon:st4ging@db.staging.internal:5432/pigeon", True),
                "SMTP_HOST": ("smtp.sandbox.postmark.test", False),
                "SMTP_PORT": ("587", False),
                "SMTP_USERNAME": ("pigeon-staging", False),
                "SMTP_PASSWORD": ("pm-sandbox-8f2c1a9d4e", True),
                "SENDER_ADDRESS": ("no-reply@staging.pigeon.test", False),
                "RATE_LIMIT_PER_MINUTE": ("60", False),
                "RETRY_ATTEMPTS": ("3", False),
                "FEATURE_BATCH_SEND": ("true", False),
                "FEATURE_DELIVERY_RECEIPTS": ("false", False),
                "MAINTENANCE_MODE": ("false", False),
                "BRAND_ACCENT": ("#B8892B", False),
                "SUPPORT_EMAIL": ("staging-alerts@pigeon.test", False),
                "LOG_LEVEL": ("info", False),
                "WEBHOOK_SIGNING_SECRET": ("whsec_stg_5b7e2c11aa93", True),
            },
        },
        {
            "slug": "production",
            "name": "Production",
            "aspect": "danger",
            "rank": 2,
            "variables": {
                "SERVICE_NAME": ("Pigeon", False),
                "REGION": ("eu-west-1", False),
                "DATABASE_URL": ("postgresql://pigeon:c9K2wq7Lz@db.pigeon.internal:5432/pigeon", True),
                "SMTP_HOST": ("smtp.postmarkapp.test", False),
                "SMTP_PORT": ("587", False),
                "SMTP_USERNAME": ("pigeon-prod", False),
                "SMTP_PASSWORD": ("pm-live-3a91ce77b024f5", True),
                "SENDER_ADDRESS": ("receipts@pigeon.test", False),
                "RATE_LIMIT_PER_MINUTE": ("12", False),
                "RETRY_ATTEMPTS": ("5", False),
                "FEATURE_BATCH_SEND": ("false", False),
                "FEATURE_DELIVERY_RECEIPTS": ("true", False),
                "MAINTENANCE_MODE": ("false", False),
                "BRAND_ACCENT": ("#8C2F39", False),
                "SUPPORT_EMAIL": ("support@pigeon.test", False),
                "LOG_LEVEL": ("warning", False),
                "WEBHOOK_SIGNING_SECRET": ("whsec_live_d41f8a2b6c07", True),
                "STRIPE_API_KEY": ("sk_live_51Nq8xEfakeKeyForDemos", True),
            },
        },
    ],
}

ATLAS = {
    "slug": "atlas",
    "name": "Atlas",
    "description": "The public site and its search index.",
    "environments": [
        {
            "slug": "development",
            "name": "Development",
            "aspect": "clear",
            "rank": 0,
            "variables": {
                "SITE_URL": ("http://localhost:4321", False),
                "SEARCH_INDEX": ("atlas_dev", False),
                "SEARCH_API_KEY": ("dev_search_key_0000", True),
                "ANALYTICS_ENABLED": ("false", False),
            },
        },
        {
            "slug": "production",
            "name": "Production",
            "aspect": "danger",
            "rank": 1,
            "variables": {
                "SITE_URL": ("https://atlas.test", False),
                "SEARCH_INDEX": ("atlas_live", False),
                "SEARCH_API_KEY": ("live_search_9d2be7f4c1", True),
                "ANALYTICS_ENABLED": ("true", False),
                "CDN_PURGE_TOKEN": ("cdn_purge_7f21ba9e", True),
            },
        },
    ],
}


def reset() -> None:
    print("Dropping every envless table.")
    Base.metadata.drop_all(bind=engine)


def build(db, spec: dict) -> Project:
    project = Project(slug=spec["slug"], name=spec["name"], description=spec["description"])
    db.add(project)
    db.flush()
    record_audit(
        db,
        action="project.created",
        summary=f"Created project {project.name}",
        project_id=project.id,
    )

    for env_spec in spec["environments"]:
        environment = Environment(
            project_id=project.id,
            slug=env_spec["slug"],
            name=env_spec["name"],
            aspect=env_spec["aspect"],
            rank=env_spec["rank"],
        )
        db.add(environment)
        db.flush()
        record_audit(
            db,
            action="environment.created",
            summary=f"Created environment {environment.name}",
            project_id=project.id,
            environment_id=environment.id,
        )

        for key, (value, is_secret) in env_spec["variables"].items():
            variable = Variable(
                environment_id=environment.id,
                key=key,
                value_encrypted=store_value(value),
                is_secret=is_secret,
                version=1,
            )
            db.add(variable)
            db.flush()
            record_revision(
                db,
                variable=variable,
                environment_id=environment.id,
                key=key,
                action="created",
                value_encrypted=variable.value_encrypted,
                actor="seed",
                version=1,
            )

        record_audit(
            db,
            action="variables.imported",
            summary=f"Seeded {len(env_spec['variables'])} variables into {environment.name}",
            project_id=project.id,
            environment_id=environment.id,
            actor="seed",
            detail={"created": len(env_spec["variables"])},
        )
    return project


def issue_for(db, project: Project, env_slug: str, token_name: str) -> tuple[str, Environment]:
    environment = db.scalar(
        select(Environment).where(
            Environment.project_id == project.id, Environment.slug == env_slug
        )
    )
    plaintext, prefix, token_hash = new_access_token()
    db.add(
        AccessToken(
            environment_id=environment.id,
            name=token_name,
            prefix=prefix,
            token_hash=token_hash,
        )
    )
    record_audit(
        db,
        action="token.issued",
        summary=f"Issued token {token_name} for {environment.name}",
        project_id=project.id,
        environment_id=environment.id,
        actor="seed",
        detail={"prefix": prefix},
    )
    return plaintext, environment


def write_pigeon_env(token: str) -> Path | None:
    """Point the Pigeon app at the environment we just built for it."""
    target = REPO_ROOT / "pigeon" / ".env"
    if not target.parent.exists():
        return None
    target.write_text(
        "# Written by backend/seed.py. Pigeon holds no configuration of its own -\n"
        "# these three lines are only how it finds envless and proves who it is.\n"
        "ENVLESS_URL=http://127.0.0.1:8000\n"
        f"ENVLESS_TOKEN={token}\n"
        "PORT=8100\n",
        encoding="utf-8",
    )
    return target


def main() -> None:
    if "--reset" in sys.argv:
        reset()
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        if db.scalar(select(Project).limit(1)) is not None:
            print("This database already has projects. Re-run with --reset to start over.")
            return

        pigeon = build(db, PIGEON)
        build(db, ATLAS)

        dev_token, dev_env = issue_for(db, pigeon, "development", "Pigeon local")
        stg_token, _ = issue_for(db, pigeon, "staging", "Pigeon staging runner")
        db.commit()

    print("\nSeeded envless.\n")
    print("  Projects      Pigeon, Atlas")
    print(f"  Environments  {dev_env.name}, Staging, Production")
    print("\nAccess tokens (shown once - the database keeps only a hash):\n")
    print(f"  Pigeon / Development   {dev_token}")
    print(f"  Pigeon / Staging       {stg_token}")

    written = write_pigeon_env(dev_token)
    if written:
        print(f"\nWrote the development token to {written}")
        print("Pigeon will boot on Development. Swap the token to move it to Staging.")


if __name__ == "__main__":
    main()
