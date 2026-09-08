"""Checks the two alert rules, the rate limit, and rotation propagation.

The rate limit and propagation are exercised over HTTP, the way a real client
meets them. The unfamiliar-source rule is exercised against `guard.observe`
directly, because faking a second source address over HTTP would mean either
trusting a header the server is right not to trust, or binding envless to
something wider than loopback just to run a test.

Run it with the API up:  .venv/Scripts/python.exe guard_test.py
"""

import json
import sys
import time
import urllib.error
import urllib.request
import uuid

from sqlalchemy import select

from app.db import SessionLocal
from app.guard import observe
from app.models import AccessToken, AuditEvent

BASE = "http://127.0.0.1:8000"
failures: list[str] = []


def call(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, raw.decode()


def check(label, condition, detail=""):
    print(f"  {'PASS' if condition else 'FAIL'}  {label}{'' if condition else f'  <- {detail}'}")
    if not condition:
        failures.append(label)


def alerts_for(env_id):
    return call("GET", f"/api/activity?environment_id={env_id}&alerts_only=true&limit=200")[1]


print("envless guard test\n")

slug = f"guard-{int(time.time())}"
_, project = call("POST", "/api/projects", {"name": "Guard Test", "slug": slug})
env_id = next(e["id"] for e in project["environments"] if e["slug"] == "development")
call("POST", f"/api/environments/{env_id}/variables",
     {"key": "API_KEY", "value": "leaked-value-abc123", "is_secret": True})

_, busy = call("POST", f"/api/environments/{env_id}/tokens", {"name": "busy app"})
_, steady = call("POST", f"/api/environments/{env_id}/tokens", {"name": "steady app"})

# --- an ordinary read is attributed -----------------------------------------
status, config = call("GET", "/v1/config", token=steady["token"])
check("A token can read its configuration", status == 200, str(config))
first_version = config["version"]

_, consumers = call("GET", f"/api/environments/{env_id}/consumers")
mine = next(c for c in consumers if c["id"] == steady["id"])
check("The read is attributed to the token", mine["pull_count"] >= 1, str(mine["pull_count"]))
check("The source address is recorded", mine["last_ip"] == "127.0.0.1", mine["last_ip"])
check("The token counts as reading now", mine["reading_now"] is True, str(mine["reading_now"]))
check("The token is on the current version", mine["up_to_date"] is True, str(mine))
check("One source has been seen", len(mine["sightings"]) == 1, str(mine["sightings"]))

# --- the unfamiliar-source rule, against the rule itself ---------------------
with SessionLocal() as db:
    token_row = db.scalar(select(AccessToken).where(AccessToken.id == uuid.UUID(steady["id"])))
    raised = observe(db, token_row, ip="203.0.113.7", user_agent="curl/8", version=first_version)
    check("Reading from a new address is flagged", "unfamiliar_source" in raised, str(raised))

    entry = db.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == "token.unfamiliar_source")
        .order_by(AuditEvent.created_at.desc())
    )
    check("The alert names the new address", entry.detail.get("ip") == "203.0.113.7", str(entry.detail))
    check("The alert is flagged for attention", entry.alert is True, str(entry.alert))
    check(
        "The alert lists where it read from before",
        "127.0.0.1" in entry.detail.get("known_addresses", []),
        str(entry.detail),
    )

    # Reading again from an address already seen is unremarkable.
    again = observe(db, token_row, ip="203.0.113.7", user_agent="curl/8", version=first_version)
    check("A second read from the same address is not flagged", "unfamiliar_source" not in again, str(again))

_, consumers = call("GET", f"/api/environments/{env_id}/consumers")
mine = next(c for c in consumers if c["id"] == steady["id"])
check("Both sources are kept", len(mine["sightings"]) == 2, str(mine["sightings"]))

# --- reading far too fast ----------------------------------------------------
codes = [call("GET", "/v1/config", token=busy["token"])[0] for _ in range(135)]
check("A token reading normally is served", codes[0] == 200, str(codes[:3]))
check("A token reading far too fast is refused", 429 in codes, f"no 429 in {len(codes)} reads")
if 429 in codes:
    check("It is refused at its limit, not before", 110 < codes.index(429) < 135, str(codes.index(429)))

status, refused = call("GET", "/v1/config", token=busy["token"])
check("The refusal explains itself", status == 429 and "limit" in refused["detail"], str(refused))

kinds = {a["action"] for a in alerts_for(env_id)}
check("A burst raises an alert", "token.burst" in kinds, str(kinds))
check("Being refused raises an alert", "token.rate_limited" in kinds, str(kinds))

raised = alerts_for(env_id)
check("The burst alert is raised once, not per read",
      len([a for a in raised if a["action"] == "token.burst"]) == 1, str(len(raised)))
check("The refusal alert is raised once, not per read",
      len([a for a in raised if a["action"] == "token.rate_limited"]) == 1, str(len(raised)))
check("One token reading hard does not affect another",
      call("GET", "/v1/config", token=steady["token"])[0] == 200, "the quiet token was refused")

_, everything = call("GET", f"/api/activity?environment_id={env_id}&limit=200")
ordinary = [a for a in everything if a["action"] in ("variable.created", "token.issued")]
check("Ordinary entries are not flagged", all(not a["alert"] for a in ordinary), str(ordinary[:1]))

# --- rotating a value, and watching it land ---------------------------------
print("\n  rotation")
_, rows = call("GET", f"/api/environments/{env_id}/variables")
key_row = next(r for r in rows if r["key"] == "API_KEY")

_, before = call("GET", f"/api/environments/{env_id}/status")
check("Before rotating, everything is up to date", before["up_to_date"] == before["consumers"], str(before))

started = time.time()
call("PATCH", f"/api/environments/{env_id}/variables/{key_row['id']}",
     {"value": "rotated-value-xyz789"})

_, mid = call("GET", f"/api/environments/{env_id}/status")
check("Rotating moves the version", mid["version"] != first_version, str(mid["version"]))
check("Consumers are shown as behind", mid["up_to_date"] < mid["consumers"], str(mid))
check("It names what has not caught up", "steady app" in mid["waiting"], str(mid["waiting"]))

status, after = call("GET", "/v1/config", token=steady["token"])
elapsed = time.time() - started
check("The consumer receives the rotated value",
      after["values"]["API_KEY"] == "rotated-value-xyz789", str(after["values"]))

_, done = call("GET", f"/api/environments/{env_id}/status")
check("It is no longer listed as waiting", "steady app" not in done["waiting"], str(done["waiting"]))
print(f"        rotated and picked up in {elapsed * 1000:.0f} ms")

# --- revoking stops it dead --------------------------------------------------
call("DELETE", f"/api/environments/{env_id}/tokens/{steady['id']}")
status, gone = call("GET", "/v1/config", token=steady["token"])
check("A revoked token stops reading immediately", status == 401, str(gone))

call("DELETE", f"/api/projects/{project['id']}")

print()
if failures:
    print(f"{len(failures)} check(s) failed:")
    for name in failures:
        print(f"  - {name}")
    sys.exit(1)
print("All checks passed.")
