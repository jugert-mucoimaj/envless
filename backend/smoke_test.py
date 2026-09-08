"""End-to-end check against a running envless API.

Walks the path a real operator takes: make a project, add a variable, change
it, import a .env, read the history, issue a token, pull the config through
the runtime API, and confirm a live subscriber is told when a value moves.

Run it with the API up:  .venv/Scripts/python.exe smoke_test.py
"""

import json
import sys
import threading
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
failures: list[str] = []


def call(method: str, path: str, body=None, headers=None, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = response.read()
            if raw:
                return response.status, payload.decode()
            return response.status, json.loads(payload) if payload else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        try:
            detail = json.loads(detail)
        except ValueError:
            pass
        return exc.code, detail


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {label}{'' if condition else f'  <- {detail}'}")
    if not condition:
        failures.append(label)


print("envless smoke test\n")

status, health = call("GET", "/health")
check("API is up and Postgres is reachable", status == 200 and health["database"] == "connected", str(health))

slug = f"smoke-{int(time.time())}"
status, project = call("POST", "/api/projects", {"name": "Smoke Test", "slug": slug})
check("Creating a project returns 201", status == 201, str(project))
check("A new project starts with three environments", len(project["environments"]) == 3, str(project))

status, duplicate = call("POST", "/api/projects", {"name": "Smoke Test", "slug": slug})
check("A duplicate project address is refused with 409", status == 409, str(duplicate))

status, bad = call("POST", "/api/projects", {"name": "Bad", "slug": "Not A Slug"})
check("An invalid project address is rejected", status == 422, str(bad))

env = next(e for e in project["environments"] if e["slug"] == "development")
env_id = env["id"]

status, variable = call(
    "POST",
    f"/api/environments/{env_id}/variables",
    {"key": "API_TOKEN", "value": "first-value", "is_secret": True},
)
check("Adding a variable returns 201", status == 201, str(variable))
variable_id = variable["id"]

status, bad_key = call(
    "POST", f"/api/environments/{env_id}/variables", {"key": "lower case", "value": "x"}
)
check("A malformed variable name is rejected", status == 422, str(bad_key))

status, clash = call(
    "POST", f"/api/environments/{env_id}/variables", {"key": "API_TOKEN", "value": "again"}
)
check("A duplicate variable name is refused with 409", status == 409, str(clash))

status, listed = call("GET", f"/api/environments/{env_id}/variables")
masked = next(v for v in listed if v["key"] == "API_TOKEN")
check("Secrets are masked in listings", masked["value"] != "first-value" and not masked["revealed"], str(masked))
check("A masked secret still reports its true length", masked["length"] == len("first-value"), str(masked))

status, revealed = call("GET", f"/api/environments/{env_id}/variables?reveal=true")
shown = next(v for v in revealed if v["key"] == "API_TOKEN")
check("Revealing returns the stored value", shown["value"] == "first-value", str(shown))

status, updated = call(
    "PATCH", f"/api/environments/{env_id}/variables/{variable_id}", {"value": "second-value"}
)
check("Updating a value bumps the version", updated["version"] == 2, str(updated))

status, unchanged = call(
    "PATCH", f"/api/environments/{env_id}/variables/{variable_id}", {"value": "second-value"}
)
check("Re-saving the same value does not bump the version", unchanged["version"] == 2, str(unchanged))

status, plain = call(
    "PATCH", f"/api/environments/{env_id}/variables/{variable_id}", {"is_secret": False}
)
check("A variable can be marked plain", plain["is_secret"] is False, str(plain))
status, trail = call("GET", f"/api/activity?environment_id={env_id}&limit=20")
check(
    "Changing how a value is protected is recorded",
    any(e["action"] == "variable.secrecy_changed" for e in trail),
    str([e["action"] for e in trail]),
)
check("Marking a variable plain does not bump its version", plain["version"] == 2, str(plain["version"]))
call("PATCH", f"/api/environments/{env_id}/variables/{variable_id}", {"is_secret": True})

paste = """
# pasted straight out of a .env file
export DATABASE_URL="postgres://user:pw@localhost/db"
RATE_LIMIT=25
EMPTY=
not a variable line
lower_case=ignored
"""
status, result = call(
    "POST", f"/api/environments/{env_id}/variables/import", {"body": paste, "overwrite": True}
)
check("Importing a .env creates the well-formed lines", result["created"] == 3, str(result))
check("Importing skips lines that are not variables", result["skipped"] == 1, str(result))

status, exported = call("GET", f"/api/environments/{env_id}/export?format=dotenv", raw=True)
check("Export round-trips a quoted value", 'DATABASE_URL=postgres://user:pw@localhost/db' in exported, exported)
check("Export quotes an empty value", 'EMPTY=""' in exported, exported)

status, history = call("GET", f"/api/environments/{env_id}/history")
check("History records every write", len(history) >= 5, str(len(history)))

status, issued = call("POST", f"/api/environments/{env_id}/tokens", {"name": "smoke"})
check("Issuing a token returns the secret once", status == 201 and issued["token"].startswith("envless_"), str(issued))
token = issued["token"]

status, listed_tokens = call("GET", f"/api/environments/{env_id}/tokens")
check("Listed tokens never carry the secret", "token" not in listed_tokens[0], str(listed_tokens[0]))

auth = {"Authorization": f"Bearer {token}"}
status, config = call("GET", "/v1/config", headers=auth)
check("An app pulls its config with the token", config["values"]["API_TOKEN"] == "second-value", str(config))
check("The config names its environment", config["environment_slug"] == "development", str(config))

status, denied = call("GET", "/v1/config", headers={"Authorization": "Bearer envless_wrong"})
check("A bad token is refused with 401", status == 401, str(denied))

# A subscriber should hear about a change made through the API.
heard: list[str] = []


def listen():
    request = urllib.request.Request(BASE + "/v1/stream")
    request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=15) as stream:
            for raw in stream:
                line = raw.decode().strip()
                if line.startswith("data:"):
                    heard.append(line[5:].strip())
                if len(heard) >= 2:
                    return
    except Exception:
        pass


listener = threading.Thread(target=listen, daemon=True)
listener.start()
time.sleep(1.5)
call("PATCH", f"/api/environments/{env_id}/variables/{variable_id}", {"value": "third-value"})
listener.join(timeout=8)

check("A live subscriber is told when a value changes", len(heard) >= 2, f"received {heard}")
if len(heard) >= 2:
    change = json.loads(heard[1])
    check("The change notice names what moved", "API_TOKEN" in change.get("reason", ""), str(change))
    check("The change notice carries the new version", bool(change.get("version")), str(change))

status, after = call("GET", "/v1/config", headers=auth)
check("The app now reads the new value", after["values"]["API_TOKEN"] == "third-value", str(after))
check("A changed value produces a new config version", after["version"] != config["version"], str(after))

status, _ = call("DELETE", f"/api/environments/{env_id}/variables/{variable_id}")
check("Deleting a variable returns 204", status == 204, str(status))
status, final = call("GET", "/v1/config", headers=auth)
check("The deleted variable is gone from the config", "API_TOKEN" not in final["values"], str(final))

status, _ = call("DELETE", f"/api/projects/{project['id']}")
check("Deleting the project cleans up", status == 204, str(status))
status, gone = call("GET", "/v1/config", headers=auth)
check("A token for a deleted environment stops working", status in (401, 404), str(gone))

print()
if failures:
    print(f"{len(failures)} check(s) failed:")
    for name in failures:
        print(f"  - {name}")
    sys.exit(1)
print("All checks passed.")
