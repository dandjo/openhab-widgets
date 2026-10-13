#!/usr/bin/env python3
"""The heat pump's day heating (user, 2026-10-13): in the transition season the house needs less heat at night than the
heat pump gives at its lowest speed, so it cycles in short runs however long the cycle guard makes its pauses; the
same heat given in a day window with the leaving water offset a little higher (+1 K by default) is enough load for
long runs, the house's mass carries it through the night, and more of it comes from the PV. The rule
heatpump_day_heating (hp_day_heating.js next to this file) sets the offset to the day offset in the window (default
9–19 h) and to −10 K outside it, where the setpoint stays at the controller's minimum of 20 °C and it never calls for
heat; day mode while the 24-hour mean outdoor temperature (espaltherma_ext_ambient_temp_avg, the heating curve's
basis) is 10 °C or more, until it falls below 8 °C, or until the heating ran through two whole windows in a row without
reaching its own stop (hot-water charges and the short runs after them never count as its stops, their time is taken
out of the window); after such a fallback day mode returns once the 24-hour mean has risen 2 K above its value then.
In normal operation the offset goes back to 0 once and the cycle guard (hp_cycle_guard.js) works as before; in day mode
the guard keeps out, as it reads heatpump_day_heating_state.
Items: the switch heatpump_day_heating (a member of heatpump_management, like the two other heat pump automations, so
the Automatik pill switches it too), heatpump_day_heating_state (day, night, normal, off), the settings
heatpump_day_heating_offset (K, whole kelvins: the controller takes no others), heatpump_day_heating_start and _end
(hours, decimals for minutes), and the rule's memory heatpump_day_heating_full_days and heatpump_day_heating_resume
(°C, UNDEF while none); all restored by MapDB after a restart, state, offset and the memory in InfluxDB on change.
apply creates or updates items, metadata and the rule, sets the settings to their defaults where they have no state yet
and the switch to the group's state. Apply before the cycle guard's update, which reads the state item.
Usage: hp_day_heating.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
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
SCRIPT = open(os.path.join(HERE, "hp_day_heating.js"), encoding="utf-8").read()
UID = SWITCH = "heatpump_day_heating"
GROUP = "heatpump_management"
STATE, OFFSET, START, END, FULL, RESUME = (f"{UID}_{s}" for s in ("state", "offset", "start", "end", "full_days",
                                                                   "resume"))
KEEP = ["influxdb_change", "mapdb_change_restore"]
ITEMS = {
    SWITCH: {"type": "Switch", "label": "Wärmepumpe Tagheizung-Automatik", "tags": ["Switch"],
             "groupNames": ["influxdb_change", GROUP, "mapdb_change_restore"]},
    STATE: {"type": "String", "label": "Wärmepumpe Tagheizung Zustand", "tags": [], "groupNames": KEEP},
    OFFSET: {"type": "Number", "label": "Wärmepumpe Tagheizung Offset", "tags": [], "groupNames": KEEP},
    START: {"type": "Number", "label": "Wärmepumpe Tagheizung Beginn", "tags": [], "groupNames": ["mapdb_change_restore"]},
    END: {"type": "Number", "label": "Wärmepumpe Tagheizung Ende", "tags": [], "groupNames": ["mapdb_change_restore"]},
    FULL: {"type": "Number", "label": "Wärmepumpe Tagheizung volle Fenster", "tags": [], "groupNames": KEEP},
    RESUME: {"type": "Number", "label": "Wärmepumpe Tagheizung zurück ab", "tags": [], "groupNames": KEEP},
}
for name, item in ITEMS.items():
    item.update(name=name, category="material:wb_sunny")
METADATA = {
    SWITCH: {"stateDescription": {"value": " ", "config": {"pattern": "%s"}}},
    STATE: {"stateDescription": {"value": " ", "config": {"pattern": "%s", "readOnly": True,
                                                          "options": "day=Tag,night=Nacht,normal=Normalbetrieb,off=Aus"}}},
    OFFSET: {"stateDescription": {"value": " ", "config": {"pattern": "%+.0f K", "min": -10, "max": 10, "step": 1}}},
    START: {"stateDescription": {"value": " ", "config": {"pattern": "%s Uhr", "min": 0, "max": 24, "step": 0.5}}},
    END: {"stateDescription": {"value": " ", "config": {"pattern": "%s Uhr", "min": 0, "max": 24, "step": 0.5}}},
    FULL: {"stateDescription": {"value": " ", "config": {"pattern": "%.0f", "readOnly": True}}},
    RESUME: {"stateDescription": {"value": " ", "config": {"pattern": "%.1f °C", "readOnly": True}}},
}
DEFAULTS = {OFFSET: "1", START: "9", END: "19", FULL: "0", RESUME: "UNDEF"}
# the season, the settings, the compressor's start and stop, the offset and the guard's lock at once; the leaving
# water against the setpoint, which changes every few seconds, every 20 seconds, between the guard's runs
WATCHED = ("espaltherma_ext_ambient_temp_avg", "pyaltherma_leaving_water_temp_offset_heating",
           "espaltherma_inv_frequency", "espaltherma_3way_valve_mode", "espaltherma_defrost_operaton", SWITCH,
           "pyaltherma_climate_control_power", OFFSET, START, END, "heatpump_cycle_lock")
RULE = {
    "uid": UID,
    "name": "Wärmepumpe Tagheizung-Automatik",
    "description": RULE_DESCRIPTIONS[UID],
    "tags": [],
    "triggers": [{"type": "core.ItemStateChangeTrigger", "configuration": {"itemName": n}} for n in WATCHED] +
                [{"type": "timer.GenericCronTrigger", "configuration": {"cronExpression": "10/20 * * * * ? *"}}],
    "conditions": [],
    "actions": [{"id": str(len(WATCHED) + 2), "type": "script.ScriptAction",
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
status, group = call("GET", f"/items/{GROUP}")
assert status == 200, f"group {GROUP}: {status}"
print(f"group {GROUP}: function {group.get('function')}, state {group['state']}, "
      f"members {[m['name'] for m in group.get('members', [])]}")
for name in ITEMS:
    status, item = call("GET", f"/items/{name}")
    print(f"item {name}:", f"exists, state {item['state']}" if status == 200 else "missing")
for name in WATCHED:
    if name not in ITEMS:
        assert call("GET", f"/items/{name}")[0] == 200, f"watched item {name} missing"
print(f"rule {UID}:", "exists" if call("GET", f"/rules/{UID}")[0] == 200 else "missing",
      f"({len(RULE['triggers'])} triggers, script {len(SCRIPT)} chars)")
if apply:
    for name, item in ITEMS.items():
        print(f"item {name} PUT", call("PUT", f"/items/{name}", item)[0])
        for namespace, meta in METADATA[name].items():
            print(f"  metadata {namespace} PUT", call("PUT", f"/items/{name}/metadata/{namespace}", meta)[0])
    initial = dict(DEFAULTS, **{SWITCH: group["state"] if group["state"] in ("ON", "OFF") else "OFF"})
    for name, value in initial.items():
        if call("GET", f"/items/{name}")[1]["state"] in ("NULL", "UNDEF"):
            print(f"item {name} state {value}", call("PUT", f"/items/{name}/state", value, "text/plain")[0])
    exists = call("GET", f"/rules/{UID}")[0] == 200
    print(f"rule {UID}", f"PUT {call('PUT', f'/rules/{UID}', RULE)[0]}" if exists else
          f"POST {call('POST', '/rules', RULE)[0]}")
