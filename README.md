# envless

Keep your environment variables in one place, and hand them to whatever is
running — while it is running.

Most configuration tools are read-at-boot: your app loads its `.env` when it
starts, and changing a value means a redeploy. envless holds the connection
open. Change a value in the command centre and every running application has it
about a hundred milliseconds later, with no restart, no deploy, and a list
naming anything that has not caught up yet.

That matters most on the worst day. A credential leaks; you need it dead
everywhere, and you need to know nothing is still using the old one.

```
  you                       envless                    your app
  ───                       ───────                    ────────
  change a value  ────────▶  encrypt, version,
                             audit, publish
                                   │
                                   ├──── SSE ────▶  re-reads /v1/config
                                   │                and applies it
                                   ▼
                             "2 of 3 on the current value
                              — waiting on billing-worker"
```

Self-hosted, AGPL-3.0, Docker files ready to go.

---

## Run it

You need Docker. That is the whole list.

```bash
git clone https://github.com/jugert-mucoimaj/envless.git
cd envless

cp .env.example .env          # then put a key in it, see below
docker compose --profile setup run --rm seed
docker compose up --build
```

Open **http://localhost:3000**.

### The one thing you have to set

`ENVLESS_MASTER_KEY` encrypts every value envless stores. There is no default
on purpose — a key committed to a repository is a key every deployment shares,
and nobody would ever notice. Generate one:

```bash
docker run --rm python:3.12-alpine sh -c \
  "pip install -q cryptography && python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
```

Put it in `.env` as `ENVLESS_MASTER_KEY=` and keep it somewhere safe. Values
written under one key cannot be read under another, and envless will not
re-encrypt them for you.

### What comes up

| | | |
|---|---|---|
| command centre | http://localhost:3000 | where you put a name and a value in and save it |
| API | http://localhost:8000 | `/docs` for the interactive reference |
| Postgres | localhost:5433 | 5433, so it does not collide with one you already run |

Add `--profile demo` and you also get **Pigeon** on http://localhost:8100 — a
small fictional service that runs entirely on configuration envless hands it.
Put the two windows side by side, change `RATE_LIMIT_PER_MINUTE`, and watch it
take effect. It is the fastest way to see the point.

The `setup` profile seeds two example projects and issues Pigeon a token. Skip
it if you would rather start empty.

---

## Customise it

Everything below goes in `.env`, next to `docker-compose.yml`.

### Ports

```bash
CENTRE_PORT=3000
API_PORT=8000
PIGEON_PORT=8100
POSTGRES_PORT=5433
```

If you move `API_PORT`, move `NEXT_PUBLIC_ENVLESS_API` with it. That one is
read by the **browser**, not the container, so it is compiled into the command
centre's bundle when the image is built — it has to be an address your browser
can reach, and changing it means `docker compose build centre`, not a restart.

```bash
NEXT_PUBLIC_ENVLESS_API=http://127.0.0.1:8000
```

### Behind a domain

Put a reverse proxy in front, point `NEXT_PUBLIC_ENVLESS_API` at the public API
address, rebuild the centre image, and add the origin:

```bash
CORS_ORIGINS=https://envless.example.com
TRUST_PROXY_HEADER=true
```

Turn `TRUST_PROXY_HEADER` on **only** when something you control is rewriting
`X-Forwarded-For`. Otherwise any caller can name its own source address and
walk straight past the unfamiliar-source alert.

### How much reading is too much

```bash
RUNTIME_RATE_LIMIT=120     # reads a minute before a token gets a 429
RUNTIME_BURST_ALERT=30     # reads a minute worth flagging
```

An application is *told* when its configuration changes, so it pulls at boot
and rarely again. Both numbers sit well above that on purpose — they are meant
to catch something that is not behaving like an application.

### Your own database

Point `DATABASE_URL` at it and drop the `postgres` service from
`docker-compose.yml`:

```bash
DATABASE_URL=postgresql+psycopg://user:password@your-host:5432/envless
```

Tables are created on startup. There are no migrations to run.

### Making it yours

- **Environments are whatever you say.** The three you start with —
  development, staging, production — are only a convenient default. Add
  `preview`, `eu-west`, `tenant-42`, anything.
- **Aspect** (clear / caution / danger) is a real column, not decoration. It
  paints the band across the top of the command centre, so an environment
  carrying live traffic looks different from one that does not.
- **The command centre's look** lives in
  [`frontend/app/globals.css`](frontend/app/globals.css) — the colour tokens
  and two fonts at the top of the file. Change those and the whole screen
  follows.
- **Pigeon is optional.** It exists to demonstrate the runtime side. Drop the
  `pigeon` service and its folder if you do not want it.

---

## Point your own app at it

Issue a token in the command centre — **Tokens**, give it a name. It is shown
once; the database keeps only a hash. Then:

```bash
curl -H "Authorization: Bearer envless_..." http://localhost:8000/v1/config
curl -H "Authorization: Bearer envless_..." http://localhost:8000/v1/config.env
```

`/v1/config` carries an `ETag` — send it back as `If-None-Match` and an
unchanged configuration answers `304`. `/v1/config.env` returns `.env` text for
anything that would rather read a file.

For live updates, hold `/v1/stream` open and re-read when it says something
moved:

```python
async with client.stream("GET", f"{ENVLESS}/v1/stream", headers=auth) as stream:
    async for line in stream.aiter_lines():
        if line.startswith("data:"):
            await reload_config()      # a value changed; pick it up
```

A complete client — pulls at boot, listens for changes, keeps working if
envless goes away — is [`pigeon/config_client.py`](pigeon/config_client.py),
about 150 readable lines. Copy it.

A token opens exactly one environment and nothing else.

---

## What you get

**Values encrypted at rest.** Fernet, keyed by `ENVLESS_MASTER_KEY`. A dump of
the `variables` table is not useful on its own.

**Tokens hashed.** Generated once, shown once, stored as SHA-256. Losing one
means issuing another.

**Everything recorded.** Every write appends a revision — deletes included —
and an audit entry. Changing whether a value is masked is recorded too, because
that decides who can read it off a screen.

**Two alerts, and only two.** A token reading from an address it has never used
before, and a token reading far more often than an application needs to. Both
are a counter and a lookup; both explain themselves and say what to do next.
Neither pretends to be intrusion detection.

**Rotation you can watch land.** **Rotate** on a secret opens an editor that
deliberately does not show you the old value. Save, and the band at the top
counts running applications onto the new one and names any that lag.

**A command palette.** Ctrl-K. It is a command centre; it should be drivable
from the keyboard.

---

## Running it without Docker

Python 3.11+, Node 20+, and a Postgres you can reach.

```powershell
.\setup.ps1     # virtualenvs, packages, database, seeded projects
.\dev.ps1       # starts all three, each in its own window
```

`setup.ps1` generates a master key into `backend/.env` for you. There is a
manual walkthrough in [`backend/README.md`](backend/README.md) if you would
rather do each step yourself.

## Checking it

```powershell
cd backend; .\.venv\Scripts\python.exe smoke_test.py        # the API, end to end
cd backend; .\.venv\Scripts\python.exe guard_test.py        # rate limit, alerts, propagation
cd backend; .\.venv\Scripts\python.exe rotation_demo.py     # the leak-and-rotate story, timed
cd pigeon;  .\.venv\Scripts\python.exe integration_test.py  # envless -> a running app
cd frontend; npm run lint; npx tsc --noEmit; npm run build
```

The Python checks need the services already running.

## The three parts

| | |
|---|---|
| [`frontend/`](frontend/) | the command centre. Next.js. The band across the top takes the colour of the environment you are on, so you know what is running before you change it |
| [`backend/`](backend/) | FastAPI over Postgres. `/api/…` for the command centre, `/v1/…` for your applications, kept deliberately apart |
| [`pigeon/`](pigeon/) | a fictional messaging service that runs on envless and nothing else. The proof the loop closes |

Each has its own README and its own Dockerfile.

## Licence

[AGPL-3.0](LICENSE). Use it, change it, run it for yourself or for others — and
if you run a modified version as a network service, your users get the source
to that version too.
