"""The reason this exists: a credential leaked, kill it everywhere.

Walks the story end to end against the running stack. It rotates a real secret
in Pigeon's Development environment and measures how long a running
application takes to be on the new value.

    .venv/Scripts/python.exe rotation_demo.py

Needs the API on :8000 and Pigeon on :8100. It puts the original value back at
the end, so it can be run as often as you like.
"""

import base64
import json
import os
import time
import urllib.error
import urllib.request

ENVLESS = "http://127.0.0.1:8000"
PIGEON = "http://127.0.0.1:8100"
SECRET = "SMTP_PASSWORD"


def call(base, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base + path, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()
    except urllib.error.URLError as exc:
        return 0, str(exc)


def say(line=""):
    print(line)


def rule(title):
    print(f"\n{title}\n{'-' * len(title)}")


def new_secret():
    return "pm-" + base64.urlsafe_b64encode(os.urandom(15)).decode().rstrip("=")


status, _ = call(ENVLESS, "GET", "/health")
if status != 200:
    say("The envless API is not answering on :8000. Start it first.")
    raise SystemExit(1)
status, pigeon = call(PIGEON, "GET", "/api/state")
if status != 200:
    say("Pigeon is not answering on :8100. Start it first.")
    raise SystemExit(1)

_, projects = call(ENVLESS, "GET", "/api/projects")
project = next(p for p in projects if p["slug"] == "pigeon")
env = next(e for e in project["environments"] if e["slug"] == "development")
env_id = env["id"]

_, rows = call(ENVLESS, "GET", f"/api/environments/{env_id}/variables")
row = next(r for r in rows if r["key"] == SECRET)
_, full = call(ENVLESS, "GET", f"/api/environments/{env_id}/variables/{row['id']}?reveal=true")
original = full["value"]

rule("Before")
_, before = call(ENVLESS, "GET", f"/api/environments/{env_id}/status")
say(f"  {project['name']} / {env['name']} is at version {before['version'][:8]}")
say(f"  {before['consumers']} application(s) reading it, {before['up_to_date']} on the current value")
say(f"  Pigeon reports version {pigeon['version'][:8]}, reloaded {pigeon['reloads']} times so far")
say(f"  {SECRET} is currently {original[:6]}... ({len(original)} characters)")

rule("The credential leaks")
say("  Someone posts a screenshot. This value is public now.")
say("  Nothing about the running application changes - it is still using it.")

rule("Rotate it")
replacement = new_secret()
say(f"  Writing a new {SECRET} into {env['name']}.")
started = time.perf_counter()
status, _ = call(
    ENVLESS,
    "PATCH",
    f"/api/environments/{env_id}/variables/{row['id']}",
    {"value": replacement},
)
if status != 200:
    say(f"  The write was refused ({status}).")
    raise SystemExit(1)

_, mid = call(ENVLESS, "GET", f"/api/environments/{env_id}/status")
say(f"  Version moved to {mid['version'][:8]}.")
if mid["waiting"]:
    say(f"  Still on the old value: {', '.join(mid['waiting'])}")

rule("Watch it land")
deadline = time.perf_counter() + 15
settled = None
while time.perf_counter() < deadline:
    _, now = call(PIGEON, "GET", "/api/state")
    if now and now["version"] == mid["version"]:
        settled = time.perf_counter() - started
        break
    time.sleep(0.05)

if settled is None:
    say("  Pigeon did not pick the change up within 15 seconds.")
    say("  Check that it is still connected to envless.")
else:
    say(f"  Pigeon is on version {mid['version'][:8]} after {settled * 1000:.0f} ms.")
    _, after = call(PIGEON, "GET", "/api/state")
    say(f"  It has now reloaded {after['reloads']} times, without restarting once.")

# The consumer list is what says the old value is genuinely out of use.
for _ in range(20):
    _, done = call(ENVLESS, "GET", f"/api/environments/{env_id}/status")
    if not done["waiting"]:
        break
    time.sleep(0.25)
say(f"  envless reports {done['up_to_date']} of {done['consumers']} on the current value.")
if done["waiting"]:
    say(f"  Still waiting on: {', '.join(done['waiting'])}")
else:
    say("  Nothing is still holding the leaked value.")

rule("The trail")
_, trail = call(ENVLESS, "GET", f"/api/activity?environment_id={env_id}&limit=6")
for entry in reversed(trail[:4]):
    when = entry["created_at"][11:19]
    say(f"  {when}  {entry['summary']}")

rule("Putting it back")
call(ENVLESS, "PATCH", f"/api/environments/{env_id}/variables/{row['id']}", {"value": original})
for _ in range(20):
    _, back = call(PIGEON, "GET", "/api/state")
    _, envstate = call(ENVLESS, "GET", f"/api/environments/{env_id}/status")
    if back and back["version"] == envstate["version"]:
        break
    time.sleep(0.25)
say(f"  {SECRET} restored, everything back on version {envstate['version'][:8]}.")
say()
say("That is the whole argument for the thing: one edit, no deploy, no restart,")
say("and a list naming anything that has not caught up yet.")
