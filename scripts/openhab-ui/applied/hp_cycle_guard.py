#!/usr/bin/env python3
"""The heat pump's cycle guard (user, 2026-10-11): the controller stops the compressor once the leaving water after the
backup heater reaches the setpoint + 3 K and starts it at setpoint − 1 K. Below about 9 °C outdoors a start's start-up
control (42–48 Hz, ~4 kW) reaches that limit within 4 to 5 minutes: in the heating seasons 2024/25 and 2025/26 75–93 %
of those starts ended after 4.5 minutes, 7 minutes off and the next start (up to 51 a day), while the starts that came
through ran 3 hours in the median at 8 Hz. While it modulates, the controller holds the water about 1.5 K above
the setpoint, hunting by a kelvin, and as far above a lifted one. The rule heatpump_cycle_management (hp_cycle_guard.js
next to this file) lifts the leaving water offset by 2 K when the water comes 2 K above the setpoint during the start-up
control, and takes the lift back a kelvin at a time once the start-up control has ended, each time the compressor is at
its lowest speed and the water 0.5 K above the lifted setpoint at most; the rest goes 20 minutes after the start.
Its switch heatpump_cycle_management is a member of the group heatpump_management, like the hot-water automation; with
two members the group's function becomes OR(ON, OFF), as ventilation_management has it, so the Automatik pill shows An
while one automation runs.
heatpump_cycle_raise holds the lift (InfluxDB on change, MapDB restores it for the rule after a restart).
apply sets the new switch to the group's state and the lift to 0 where they have none yet.
Usage: hp_cycle_guard.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
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
SCRIPT = open(os.path.join(HERE, "hp_cycle_guard.js"), encoding="utf-8").read()
UID, SWITCH, LIFT, GROUP = "heatpump_cycle_management", "heatpump_cycle_management", "heatpump_cycle_raise", \
    "heatpump_management"
ITEMS = {
    SWITCH: {"type": "Switch", "name": SWITCH, "label": "Wärmepumpe Taktschutz-Automatik", "category": "material:tune",
             "tags": ["Switch"], "groupNames": ["influxdb_change", GROUP, "mapdb_change_restore"]},
    LIFT: {"type": "Number", "name": LIFT, "label": "Wärmepumpe Taktschutz Anhebung", "category": "material:tune",
           "tags": [], "groupNames": ["influxdb_change", "mapdb_change_restore"]},
}
METADATA = {SWITCH: {"stateDescription": {"value": " ", "config": {"pattern": "%s"}}},
            LIFT: {"stateDescription": {"value": " ", "config": {"pattern": "%.0f K"}}}}
WATCHED = ("espaltherma_inv_frequency", "espaltherma_leaving_water_temp_after_buh",
           "espaltherma_leaving_water_setpoint", "pyaltherma_leaving_water_temp_offset_heating",
           "espaltherma_3way_valve_mode", "espaltherma_startup_control", SWITCH, "pyaltherma_climate_control_power",
           "espaltherma_space_heating_operation", "espaltherma_smart_grid")
RULE = {
    "uid": UID,
    "name": "Wärmepumpe Taktschutz-Automatik",
    "description": RULE_DESCRIPTIONS[UID],
    "tags": [],
    "triggers": [{"type": "core.ItemStateChangeTrigger", "configuration": {"itemName": n}} for n in WATCHED] +
                [{"type": "timer.GenericCronTrigger", "configuration": {"cronExpression": "0 * * * * ? *"}}],
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
function = {"name": "OR", "params": ["ON", "OFF"]}
print(f"group {GROUP}: function {group.get('function')} -> {function}, state {group['state']}")
for name in ITEMS:
    status, item = call("GET", f"/items/{name}")
    print(f"item {name}:", f"exists, state {item['state']}" if status == 200 else "missing")
print(f"rule {UID}:", "exists" if call("GET", f"/rules/{UID}")[0] == 200 else "missing",
      f"({len(RULE['triggers'])} triggers, script {len(SCRIPT)} chars)")
if apply:
    dto = {k: group[k] for k in ("type", "name", "label", "category", "tags", "groupNames", "groupType")}
    print(f"group {GROUP} PUT", call("PUT", f"/items/{GROUP}", dict(dto, function=function))[0])
    for name, item in ITEMS.items():
        print(f"item {name} PUT", call("PUT", f"/items/{name}", item)[0])
        for namespace, meta in METADATA[name].items():
            print(f"  metadata {namespace} PUT", call("PUT", f"/items/{name}/metadata/{namespace}", meta)[0])
    for name, initial in ((LIFT, "0"), (SWITCH, group["state"] if group["state"] in ("ON", "OFF") else "OFF")):
        if call("GET", f"/items/{name}")[1]["state"] in ("NULL", "UNDEF"):
            print(f"item {name} state {initial}", call("PUT", f"/items/{name}/state", initial, "text/plain")[0])
    exists = call("GET", f"/rules/{UID}")[0] == 200
    print(f"rule {UID}", f"PUT {call('PUT', f'/rules/{UID}', RULE)[0]}" if exists else
          f"POST {call('POST', '/rules', RULE)[0]}")
