"""envless - the control plane for application configuration.

Two surfaces live here:

  /api/...  the command centre uses this to read and write environments
  /v1/...   running applications use this to fetch the configuration they
            were issued a token for
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from . import events
from .config import get_settings
from .db import engine, ensure_schema
from . import models  # noqa: F401  - imported so the tables register on Base
from .routers import activity, environments, projects, runtime


@asynccontextmanager
async def lifespan(app: FastAPI):
    events.bind_loop(asyncio.get_running_loop())
    ensure_schema()
    yield


app = FastAPI(
    title="envless",
    version="1.0.0",
    summary="Store environment variables once, hand them to whatever is running.",
    lifespan=lifespan,
)

# Anything on the local machine may talk to the API: the command centre, the
# apps running on these environments, and whatever port the dev server picked
# today. CORS_ORIGINS adds hosts beyond localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["ETag"],
)

app.include_router(projects.router)
app.include_router(environments.router)
app.include_router(activity.router)
app.include_router(runtime.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Is the API up, and can it reach Postgres?"""
    try:
        with engine.connect() as connection:
            connection.execute(text("select 1"))
        database = "connected"
    except Exception as exc:  # surfaced in the command centre's status strip
        database = f"unreachable: {exc.__class__.__name__}"
    return {"service": "envless", "status": "ok", "database": database}
