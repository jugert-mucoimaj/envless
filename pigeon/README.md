# Pigeon

A fictional transactional messaging service, and the reason envless exists.

Pigeon's own `.env` holds three lines:

```
ENVLESS_URL=http://127.0.0.1:8000
ENVLESS_TOKEN=envless_…
PORT=8100
```

Where envless is, proof of which environment it may read, and a port. That is
all. The sending route, the rate limit, the retry count, which features are on,
whether it is in maintenance, even its accent colour — all of it comes from
envless at boot, and is corrected in place when someone changes a value in the
command centre.

## Running it

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

The token comes from `backend/seed.py`, which writes `.env` for you. To move
Pigeon onto Staging or Production, issue a token for that environment in the
command centre and paste it in — nothing else about the app changes.

`ENVLESS_ENV_FILE` moves where that `.env` is read from, which is how the
container stack keeps its token in a volume rather than writing over the one a
local setup is using. Anything already in the environment beats the file, so
compose can point `ENVLESS_URL` at the API service without editing anything.
`HOST` does the same for the bind address: loopback on a laptop, `0.0.0.0` in
a container.

## What the configuration decides

| Variable | What it does here |
|---|---|
| `SERVICE_NAME` | the name on the page and in the browser tab |
| `REGION` | shown beside the environment |
| `SMTP_HOST`, `SMTP_PORT` | the delivery route every message reports going through |
| `SMTP_USERNAME`, `SENDER_ADDRESS` | who messages come from |
| `DATABASE_URL` | shown as the store, with the password redacted |
| `RATE_LIMIT_PER_MINUTE` | enforced — sends past it are refused with a 429 |
| `RETRY_ATTEMPTS` | recorded against each message |
| `FEATURE_BATCH_SEND` | shows the count field; sending several at once fails without it |
| `FEATURE_DELIVERY_RECEIPTS` | adds a receipt id to each sent message |
| `MAINTENANCE_MODE` | refuses every send and puts a banner up |
| `BRAND_ACCENT` | the accent colour of the whole page |
| `SUPPORT_EMAIL` | the address in the footer |
| `LOG_LEVEL` | shown in the readout |

## The files

| | |
|---|---|
| `config_client.py` | the envless client — pull at boot, listen for changes, fall back gracefully |
| `app.py` | the service: sending, rate limiting, and the state the page renders |
| `templates/index.html` | one page, which re-reads itself when configuration moves |
| `integration_test.py` | 17 checks that a change in envless changes what Pigeon does |
| `Dockerfile` | the Pigeon image, brought up by `docker compose --profile demo` |

`config_client.py` is the part worth copying into a real application. It holds
an SSE connection to `/v1/stream`, re-pulls on a change, and if envless goes
away it keeps the last configuration it had and retries in the background —
configuration being unreachable should never be why a service is down.

## Trying it

With the backend, command centre and Pigeon all up:

1. Open Pigeon at http://127.0.0.1:8100 and the command centre beside it.
2. Set `RATE_LIMIT_PER_MINUTE` to `3` in Pigeon → Development.
3. Pigeon's readout follows immediately. The fourth send in a minute is refused,
   quoting the number you set.
4. Set `MAINTENANCE_MODE` to `true` and sending stops altogether.
5. Set `BRAND_ACCENT` to `#4A3AA8` and the page changes colour.

`integration_test.py` does the same thing without the watching.
