#!/usr/bin/env python3
"""The renewable energy community the house belongs to (WiEnergy), as items (user,
2026-10-16): WiEnergy publishes a forecast per quarter hour for each of its communities as static JSON files it
regenerates every hour (API stage 1, no key); the rule energy_community_forecast (energy_community.js next to this file)
reads them every 15 minutes. Balance, production and consumption (W, positive balance = surplus) go into InfluxDB as a
forecast series through the group influxdb_forecast, so openHAB sets their state per quarter hour as it does the
aWATTar prices'; the level and certainty of the running quarter hour and the next surplus window (start, end, energy,
certainty) are plain items the rule sets, not persisted (it runs at startup). Nothing is controlled from them yet.
The community's id and name are not in this file but in ~/.config/energy-community.json on homepi,
{"community": "<id>", "name": "<label of the equipment>"}: the id goes into the rule's script, the name
becomes the equipment's label.
apply creates or updates the equipment, its items, their metadata and the rule, and runs the rule once.
Usage: energy_community.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "i18n"))
from de_labels import RULE_DESCRIPTIONS  # noqa: E402

BASE = "http://127.0.0.1:8080/rest"
TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
CONFIG = json.load(open(os.path.expanduser("~/.config/energy-community.json"), encoding="utf-8"))
SCRIPT = open(os.path.join(HERE, "energy_community.js"), encoding="utf-8").read().replace("__COMMUNITY__",
                                                                                     CONFIG["community"])
UID = "energy_community_forecast"
GROUP = "energy_community"
P = GROUP + "_"
LEVELS = "surplus=Überschuss,balanced=Ausgeglichen,deficit=Defizit,unavailable=Unbekannt"
CERTAINTIES = "certain=Sicher,likely=Wahrscheinlich,possible=Möglich,none=Keine"


def point(type_, label, category, tags, forecast=False):
    return {"type": type_, "label": label, "category": category, "tags": tags,
            "groupNames": [GROUP, "influxdb_forecast"] if forecast else [GROUP]}


ITEMS = {
    GROUP: {"type": "Group", "label": CONFIG["name"], "category": "material:solar_power", "tags": ["Equipment"],
            "groupNames": []},
    P + "balance": point("Number:Power", "EEG Bilanz", "material:bolt", ["Power", "Measurement"], forecast=True),
    P + "production": point("Number:Power", "EEG Erzeugung", "material:solar_power", ["Power", "Measurement"],
                            forecast=True),
    P + "consumption": point("Number:Power", "EEG Verbrauch", "material:bolt", ["Power", "Measurement"], forecast=True),
    P + "level": point("String", "EEG Stufe", "material:traffic", ["Status"]),
    P + "certainty": point("String", "EEG Sicherheit", "material:verified", ["Status"]),
    P + "window_start": point("DateTime", "EEG Fenster Beginn", "material:schedule", ["Timestamp", "Point"]),
    P + "window_end": point("DateTime", "EEG Fenster Ende", "material:schedule", ["Timestamp", "Point"]),
    P + "window_energy": point("Number:Energy", "EEG Fenster Energie", "material:battery_charging_full",
                               ["Energy", "Measurement"]),
    P + "window_certainty": point("String", "EEG Fenster Sicherheit", "material:verified", ["Status"]),
}
for name, item in ITEMS.items():
    item["name"] = name


def state(pattern, **cfg):
    return {"stateDescription": {"value": " ", "config": {"pattern": pattern, "readOnly": True, **cfg}}}


POWER = {"unit": {"value": "W"}, **state("%.0f %unit%")}
METADATA = {
    GROUP: {},
    P + "balance": POWER, P + "production": POWER, P + "consumption": POWER,
    P + "level": state("%s", options=LEVELS),
    P + "certainty": state("%s", options=CERTAINTIES),
    P + "window_start": state("%1$ta %1$tR"),
    P + "window_end": state("%1$ta %1$tR"),
    P + "window_energy": {"unit": {"value": "kWh"}, **state("%.1f %unit%")},
    P + "window_certainty": state("%s", options=CERTAINTIES),
}
RULE = {
    "uid": UID,
    "name": "EEG Prognose",
    "description": RULE_DESCRIPTIONS[UID],
    "tags": [],
    # 10 s after each quarter hour, so the running quarter hour is the new one; the files change once an hour
    "triggers": [{"id": "1", "type": "timer.GenericCronTrigger", "configuration": {"cronExpression": "10 0/15 * * * ? *"}},
                 {"id": "2", "type": "core.SystemStartlevelTrigger", "configuration": {"startlevel": 100}}],
    "conditions": [],
    "actions": [{"id": "3", "type": "script.ScriptAction",
                 "configuration": {"type": "application/javascript", "script": SCRIPT}}],
}


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
assert call("GET", "/items/influxdb_forecast")[0] == 200, "group influxdb_forecast missing"
for name in ITEMS:
    status, item = call("GET", f"/items/{name}")
    print(f"item {name}:", f"exists, state {item['state']}" if status == 200 else "missing")
print(f"rule {UID}:", "exists" if call("GET", f"/rules/{UID}")[0] == 200 else "missing",
      f"(script {len(SCRIPT)} chars)")
if apply:
    for name, item in ITEMS.items():
        print(f"item {name} PUT", call("PUT", f"/items/{name}", item)[0])
        for namespace, meta in METADATA[name].items():
            print(f"  metadata {namespace} PUT", call("PUT", f"/items/{name}/metadata/{namespace}", meta)[0])
    exists = call("GET", f"/rules/{UID}")[0] == 200
    print(f"rule {UID}", f"PUT {call('PUT', f'/rules/{UID}', RULE)[0]}" if exists else
          f"POST {call('POST', '/rules', RULE)[0]}")
    print(f"rule {UID} runnow", call("POST", f"/rules/{UID}/runnow", {})[0])
