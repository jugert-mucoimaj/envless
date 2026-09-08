# envless backend

FastAPI over Postgres. Two surfaces, deliberately kept apart:

- **`/api/…`** — what the command centre uses. Reads and writes projects,
  environments, variables, tokens and history.
- **`/v1/…`** — what a running application uses. Presents a token, receives the
  configuration for exactly one environment, and nothing else.

Interactive docs are at http://127.0.0.1:8000/docs once it is running.

## Running it

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#   put that key in .env as ENVLESS_MASTER_KEY
.\.venv\Scripts\python.exe seed.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

`seed.py --reset` drops every table first and starts over.

In a container:

```powershell
docker build -t envless-api ./backend
docker run --rm -p 8000:8000 `
  -e DATABASE_URL=postgresql+psycopg://postgres:kali@host.docker.internal:5432/envless `
  -e ENVLESS_MASTER_KEY=... envless-api
```

The image runs as an unprivileged user and its healthcheck reports whether
Postgres is reachable, since the API is not much use without it. Usually you
want `docker compose` from the repo root instead, which brings its own
Postgres.

Tables are created on startup from the models. There are no migrations: this is
a local tool, and `--reset` plus a re-seed is the intended way to change shape.

## The files

| | |
|---|---|
| `app/main.py` | the application, its CORS rules, and `/health` |
| `app/models.py` | projects, environments, variables, revisions, tokens, token sightings, audit |
| `app/schemas.py` | request and response shapes, and the rules for names |
| `app/crypto.py` | Fernet encryption for values, SHA-256 for tokens |
| `app/services.py` | audit and revision writing, config versions, .env parsing |
| `app/events.py` | in-process pub/sub, so a write reaches open connections |
| `app/guard.py` | the per-token rate limit and the two alert rules |
| `app/routers/projects.py` | projects, and creating environments under them |
| `app/routers/environments.py` | variables, import, export, history, tokens |
| `app/routers/activity.py` | the audit stream the command centre reads |
| `app/routers/runtime.py` | `/v1/config`, `/v1/config.env`, `/v1/stream` |
| `seed.py` | two fictional projects, and a token written to `pigeon/.env` |
| `smoke_test.py` | 32 end-to-end checks against a running API |
| `guard_test.py` | 29 checks of the rate limit, the alerts, and rotation propagation |
| `rotation_demo.py` | the leak-and-rotate story, timed, against the running stack |
| `Dockerfile` | the API image, also used for the one-off seed service |

## How an application reads its configuration

```bash
curl -H "Authorization: Bearer envless_…" http://127.0.0.1:8000/v1/config
curl -H "Authorization: Bearer envless_…" http://127.0.0.1:8000/v1/config.env
curl -H "Authorization: Bearer envless_…" http://127.0.0.1:8000/v1/stream
```

`/v1/config` carries an `ETag`; send it back as `If-None-Match` and a
configuration that has not moved answers `304`. `/v1/stream` holds open and
emits a `change` event whenever a value in that environment is written, so an
app can re-read immediately rather than polling. `pigeon/config_client.py` is a
complete client in about 150 lines.

## Reading, watched

Every read through `/v1/…` is counted against its token. Past
`RUNTIME_RATE_LIMIT` a minute the token is refused with a `429` and a
`Retry-After`; one token going hard never affects another.

Two things raise an alert — an `audit_events` row with `alert` set:

| | |
|---|---|
| `token.unfamiliar_source` | the token read from an address it has not used before |
| `token.burst` | the token read more than `RUNTIME_BURST_ALERT` times in a minute |
| `token.rate_limited` | reads are being refused |

Each is held back to one entry per token per interval, so a token stuck in a
loop produces one alert rather than thousands. `token_sightings` holds one row
per (token, address) and is what the first rule looks up.

`GET /api/activity?alerts_only=true` returns them. It leaves out alerts about
environments that have since been deleted — those stay in the trail but cannot
be acted on, so they stop being counted.

## Who has the new value

`GET /api/environments/{id}/status` answers the question that matters after a
rotation:

```json
{ "version": "0e453168…", "consumers": 2, "up_to_date": 1, "waiting": ["billing-worker"] }
```

A consumer is a token that has read in the last ten minutes — something
actually running, not just something issued. `GET /api/environments/{id}/consumers`
gives the same picture per token, with the addresses each has read from.

## Storage

Values are encrypted with `ENVLESS_MASTER_KEY` before they are written, so a
dump of the `variables` table is not useful on its own. Every write also
appends to `revisions` — deletes included — and to `audit_events`, which is
what the command centre's activity ticker reads.

Tokens are generated once, returned once, and stored only as a hash. Losing one
means issuing another.
