#!/usr/bin/env python3
"""Compressor starts per day, for hot water and for the heating (user, 2026-10-11: "wie viele Starts es pro Tag gab ...
eine Nummer jeweils für Warmwasser und Heizung separat"), as badges on the overview's Heizung & Warmwasser.
The rule heatpump_starts_today (hp_starts.js next to this file) counts a start whenever the compressor
(espaltherma_inv_frequency) leaves 0 Hz: for hot water when the valve stands on DHW at the start or within its first
2 minutes, else for the heating; a heating run whose valve turns to hot water later is no new start. During a defrost
the compressor stops for about a minute, twice; a start at most 2 minutes after a stop, with the defrost flag on from
2 minutes before that stop, continues the run (in the history 2024-09..2026-10 every defrost restart came after
30-90 s, every other restart after 90 s or more). The counts start at 0 at midnight; MapDB restores them after a
restart, and a restored count without a point in InfluxDB since midnight is yesterday's and goes back to 0.
Replayed on the history: 2026-10-10 2 hot-water and 18 heating starts, 2026-01-15 0 and 3 (44 defrost restarts not
counted; both charges of that day began inside heating runs).
Both items: InfluxDB on change (one point per start, the day's last value is its count), MapDB restores them.
apply DHW HEATING sets today's counts once the rule has run (for a start in the middle of a day).
Usage: hp_starts.py check|apply [DHW HEATING]   (on homepi, as pi; the API token from ~/.openhab_token)"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "i18n"))
from de_labels import RULE_DESCRIPTIONS  # noqa: E402

BASE = "http://127.0.0.1:8080/rest"
TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
SCRIPT = open(os.path.join(HERE, "hp_starts.js"), encoding="utf-8").read()
UID, DHW, HEATING = "heatpump_starts_today", "heatpump_starts_dhw_today", "heatpump_starts_heating_today"
ITEMS = {
    DHW: {"type": "Number", "name": DHW, "label": "Wärmepumpe Starts Warmwasser heute", "category": "material:autorenew",
          "tags": [], "groupNames": ["influxdb_change", "mapdb_change_restore"]},
    HEATING: {"type": "Number", "name": HEATING, "label": "Wärmepumpe Starts Heizung heute",
              "category": "material:autorenew", "tags": [], "groupNames": ["influxdb_change", "mapdb_change_restore"]},
}
METADATA = {name: {"stateDescription": {"value": " ", "config": {"pattern": "%d"}}} for name in ITEMS}
WATCHED = ("espaltherma_inv_frequency", "espaltherma_3way_valve_mode", "espaltherma_defrost_operaton")
RULE = {
    "uid": UID,
    "name": "Wärmepumpe Starts heute",
    "description": RULE_DESCRIPTIONS[UID],
    "tags": [],
    "triggers": [{"type": "core.ItemStateChangeTrigger", "configuration": {"itemName": n}} for n in WATCHED] +
                [{"type": "timer.GenericCronTrigger", "configuration": {"cronExpression": "0 * * * * ? *"}},
                 # a start in the last 2 minutes of a day is decided before midnight, so it counts on its day
                 {"type": "timer.GenericCronTrigger", "configuration": {"cronExpression": "59 59 23 * * ? *"}}],
    "conditions": [],
    "actions": [{"id": str(len(WATCHED) + 3), "type": "script.ScriptAction",
                 "configuration": {"type": "application/javascript", "script": SCRIPT}}],
}
for i, t in enumerate(RULE["triggers"]):
    t["id"] = str(i + 1)


def call(method, path, body=None, content="application/json"):
    data = None if body is None else (body if isinstance(body, str) else json.dumps(body)).encode()
    req = urllib.request.Request(BASE + path, method=method, data=data,
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": content})
    try:
        with urllib.request.urlopen(req) as r:
            text = r.read().decode()
            return r.status, json.loads(text) if text.startswith(("{", "[")) else text
    except urllib.error.HTTPError as e:
        return e.code, None


apply = sys.argv[1] == "apply"
initial = dict(zip((DHW, HEATING), sys.argv[2:4])) if len(sys.argv) >= 4 else {}
for name in ITEMS:
    status, item = call("GET", f"/items/{name}")
    print(f"item {name}:", f"exists, state {item['state']}" if status == 200 else "missing")
print(f"rule {UID}:", "exists" if call("GET", f"/rules/{UID}")[0] == 200 else "missing",
      f"({len(RULE['triggers'])} triggers, script {len(SCRIPT)} chars)")
if initial:
    print("today's counts to set once the rule has run:", initial)
if apply:
    for name, item in ITEMS.items():
        print(f"item {name} PUT", call("PUT", f"/items/{name}", item)[0])
        for namespace, meta in METADATA[name].items():
            print(f"  metadata {namespace} PUT", call("PUT", f"/items/{name}/metadata/{namespace}", meta)[0])
    exists = call("GET", f"/rules/{UID}")[0] == 200
    print(f"rule {UID}", f"PUT {call('PUT', f'/rules/{UID}', RULE)[0]}" if exists else
          f"POST {call('POST', '/rules', RULE)[0]}")
    if initial:
        # the rule's first run sets NULL counts to 0 and keeps its state from then on; set today's counts after it
        print(f"rule {UID} runnow", call("POST", f"/rules/{UID}/runnow", {})[0])
        for _ in range(30):
            if all(call("GET", f"/items/{n}")[1]["state"] not in ("NULL", "UNDEF") for n in initial):
                break
            time.sleep(1)
        for name, value in initial.items():
            print(f"item {name} state {value}", call("PUT", f"/items/{name}/state", str(value), "text/plain")[0])
