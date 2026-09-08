"""Proves the whole chain: change a value in envless, and Pigeon obeys it.

Needs the backend on :8000 and Pigeon on :8100. Nothing here touches Pigeon's
own settings - every behaviour it checks is changed by writing to envless.

    .venv/Scripts/python.exe integration_test.py
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ENVLESS = "http://127.0.0.1:8000"
PIGEON = "http://127.0.0.1:8100"
failures: list[str] = []


def call(base, method, path, body=None, form=None):
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
    else:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"}
    request = urllib.request.Request(base + path, data=data, method=method)
    for key, value in headers.items():
        request.add_header(key, value)
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


def pigeon_state():
    return call(PIGEON, "GET", "/api/state")[1]


def find_development():
    _, projects = call(ENVLESS, "GET", "/api/projects")
    pigeon = next(p for p in projects if p["slug"] == "pigeon")
    return next(e for e in pigeon["environments"] if e["slug"] == "development")


def variable(env_id, key):
    _, rows = call(ENVLESS, "GET", f"/api/environments/{env_id}/variables")
    return next(row for row in rows if row["key"] == key)


def set_value(env_id, key, value):
    row = variable(env_id, key)
    call(ENVLESS, "PATCH", f"/api/environments/{env_id}/variables/{row['id']}", {"value": value})


def wait_for(predicate, timeout=8):
    """Pigeon is pushed to, not polled, but give the hop a moment to land."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = pigeon_state()
        if predicate(state):
            return state
        time.sleep(0.25)
    return pigeon_state()


print("envless -> Pigeon integration test\n")

env = find_development()
env_id = env["id"]
start = pigeon_state()
check("Pigeon booted on an envless environment", start["environment"] == "Development", str(start.get("environment")))
check("Pigeon is holding a live connection to envless", start["connected"] is True, str(start))
check("Pigeon reports the config version envless served", bool(start["version"]), str(start))
check("Pigeon never shows the store password", "****" in start["store"], start["store"])

# --- a value changed in envless reaches the running app --------------------
set_value(env_id, "RATE_LIMIT_PER_MINUTE", "7")
after = wait_for(lambda s: s["limit"] == 7)
check("Changing a value in envless reaches Pigeon without a restart", after["limit"] == 7, str(after["limit"]))
check("The config version moved with it", after["version"] != start["version"], str(after["version"]))
check("Pigeon counted the reload", after["reloads"] > start["reloads"], str(after["reloads"]))

# --- and the new value actually governs behaviour --------------------------
status, sent = call(PIGEON, "POST", "/send", form={"recipient": "someone@example.com", "subject": "Hello", "count": 1})
check("A send within the limit is accepted", status == 200 and sent["ok"], str(sent))

status, refused = call(PIGEON, "POST", "/send", form={"recipient": "someone@example.com", "count": 20})
check("A send past the new limit is refused", status == 429, str(refused))
check("The refusal names the limit envless set", "7" in refused["message"], refused["message"])

# --- a feature flag turns a capability off ---------------------------------
set_value(env_id, "FEATURE_BATCH_SEND", "false")
wait_for(lambda s: s["batch_send"] is False)
status, batched = call(PIGEON, "POST", "/send", form={"recipient": "someone@example.com", "count": 3})
check("Turning a feature off in envless disables it in Pigeon", status == 409, str(batched))

# --- maintenance mode stops the service ------------------------------------
set_value(env_id, "MAINTENANCE_MODE", "true")
paused = wait_for(lambda s: s["maintenance"] is True)
check("Maintenance mode reaches Pigeon", paused["maintenance"] is True, str(paused["maintenance"]))
status, blocked = call(PIGEON, "POST", "/send", form={"recipient": "someone@example.com"})
check("Pigeon stops sending while in maintenance", status == 503, str(blocked))

set_value(env_id, "MAINTENANCE_MODE", "false")
resumed = wait_for(lambda s: s["maintenance"] is False)
check("Turning maintenance off resumes sending", resumed["maintenance"] is False, str(resumed["maintenance"]))

# --- even presentation is configuration ------------------------------------
set_value(env_id, "BRAND_ACCENT", "#4A3AA8")
themed = wait_for(lambda s: s["accent"] == "#4A3AA8")
check("Pigeon takes its accent colour from envless", themed["accent"] == "#4A3AA8", themed["accent"])

# --- envless sees the app on the other end ---------------------------------
_, reading = call(ENVLESS, "GET", f"/api/environments/{env_id}/status")
check("envless reports the connected app", reading["connected_apps"] >= 1, str(reading))

# --- put everything back ---------------------------------------------------
print("\n  restoring the seeded values")
restore = {
    "RATE_LIMIT_PER_MINUTE": "1000",
    "MAINTENANCE_MODE": "false",
    "FEATURE_BATCH_SEND": "true",
    "BRAND_ACCENT": "#2F6F4E",
}
for key, value in restore.items():
    set_value(env_id, key, value)
back = wait_for(lambda s: s["limit"] == 1000 and s["accent"] == "#2F6F4E")
check("The seeded values are back in place", back["limit"] == 1000 and back["accent"] == "#2F6F4E", str(back["limit"]))

print()
if failures:
    print(f"{len(failures)} check(s) failed:")
    for name in failures:
        print(f"  - {name}")
    sys.exit(1)
print("All checks passed.")
