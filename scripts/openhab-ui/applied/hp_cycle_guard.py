#!/usr/bin/env python3
"""The heat pump's cycle guard (user, 2026-10-11; a start lock since 2026-10-12): the controller stops the compressor
once the leaving water after the backup heater reaches the setpoint + 3 K and calls for heat again at setpoint − 1 K.
A start's start-up control lifts the water about 4.5 K above the return below about 9 °C outdoors (42–48 Hz, ~4 kW);
with the return less than 3 K below the curve it reaches the stop within minutes, and the next start 7 minutes later
fails the same way, often for hours after a hot-water charge (heating season 2025/26: 312 such short runs in 32
series, 21 of them begun within 20 minutes after a charge), while every start with the return 3 K or more below the
curve came through. Within an hour after a charge or a short run a hot compressor makes most starts above 9 °C end in
the first minute. The rule heatpump_cycle_management (hp_cycle_guard.js next to this file) therefore lowers the
leaving water offset by 5 K once the compressor has stood 100 seconds (below 9 °C after every run, above only after a
charge or a run shorter than 10 minutes, never after a defrost), which keeps the controller from calling for heat,
and gives the start free again once the return has stayed 3.2 K (2.8 K once the compressor has cooled below 45 °C)
below the curve for 2 minutes, above 9 °C once it is 2.5 K below, the discharge pipe has cooled below 38 °C or an
hour has passed, and 2 hours after the stop at the latest. During a run it changes nothing. The controller keeps the
setpoint at or above its minimum leaving water temperature (field [9-01], 20 °C since 2026-10-12, 25 °C before, when a
lock did nothing above 9 °C); the rule checks after each lock that the setpoint dropped and leaves stops alone for
6 hours where a minimum it met would leave less than a kelvin.
Its switch heatpump_cycle_management is a member of the group heatpump_management, like the hot-water automation; with
two members the group's function becomes OR(ON, OFF), as ventilation_management has it, so the Automatik pill shows An
while one automation runs.
heatpump_cycle_lock holds the kelvins the offset is lowered by (InfluxDB on change, MapDB restores it for the rule
after a restart). apply sets the new switch to the group's state and the lock to 0 where they have none yet, refuses
while the former lift heatpump_cycle_raise is above 0, and deletes that item once the rule no longer uses it.
In the day heating's window (hp_day_heating.py) the guard locks only after a charge or a short run, by the rules above
9 °C whatever the outdoor air, and in its night it keeps out and leaves a lock to the day heating as it stands, without
a write (it reads heatpump_day_heating_state, so apply hp_day_heating.py first). The return's marks lie below the
setpoint without the lock, the curve plus the offset the lock was taken from (the day offset in the window). Every
decision waits 20 seconds after any change of the offset, not only after its own writes, as the setpoint reports back
about 5 seconds later.
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
UID, SWITCH, LOCK, GROUP = "heatpump_cycle_management", "heatpump_cycle_management", "heatpump_cycle_lock", \
    "heatpump_management"
FORMER = "heatpump_cycle_raise"  # the lift of the guard's first version, until 2026-10-12
ITEMS = {
    SWITCH: {"type": "Switch", "name": SWITCH, "label": "Wärmepumpe Taktschutz-Automatik", "category": "material:tune",
             "tags": ["Switch"], "groupNames": ["influxdb_change", GROUP, "mapdb_change_restore"]},
    LOCK: {"type": "Number", "name": LOCK, "label": "Wärmepumpe Taktschutz Sperre", "category": "material:tune",
           "tags": [], "groupNames": ["influxdb_change", "mapdb_change_restore"]},
}
METADATA = {SWITCH: {"stateDescription": {"value": " ", "config": {"pattern": "%s"}}},
            LOCK: {"stateDescription": {"value": " ", "config": {"pattern": "%.0f K"}}}}
# the compressor's start and stop, the offset, the valve and the switches at once; the return and the discharge pipe,
# which change every few seconds, every 20 seconds
WATCHED = ("espaltherma_inv_frequency", "pyaltherma_leaving_water_temp_offset_heating", "espaltherma_3way_valve_mode",
           "espaltherma_defrost_operaton", SWITCH, "pyaltherma_climate_control_power",
           "espaltherma_space_heating_operation", "espaltherma_smart_grid", "heatpump_day_heating_state")
RULE = {
    "uid": UID,
    "name": "Wärmepumpe Taktschutz-Automatik",
    "description": RULE_DESCRIPTIONS[UID],
    "tags": [],
    "triggers": [{"type": "core.ItemStateChangeTrigger", "configuration": {"itemName": n}} for n in WATCHED] +
                [{"type": "timer.GenericCronTrigger", "configuration": {"cronExpression": "0/20 * * * * ? *"}}],
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
status, former = call("GET", f"/items/{FORMER}")
print(f"item {FORMER}:", f"exists, state {former['state']} (deleted by apply)" if status == 200 else "gone")
if apply and status == 200 and former["state"] not in ("0", "NULL", "UNDEF"):
    sys.exit(f"{FORMER} is {former['state']}: the former guard still lifts the offset, apply once it is 0")
if apply:
    dto = {k: group[k] for k in ("type", "name", "label", "category", "tags", "groupNames", "groupType")}
    print(f"group {GROUP} PUT", call("PUT", f"/items/{GROUP}", dict(dto, function=function))[0])
    for name, item in ITEMS.items():
        print(f"item {name} PUT", call("PUT", f"/items/{name}", item)[0])
        for namespace, meta in METADATA[name].items():
            print(f"  metadata {namespace} PUT", call("PUT", f"/items/{name}/metadata/{namespace}", meta)[0])
    for name, initial in ((LOCK, "0"), (SWITCH, group["state"] if group["state"] in ("ON", "OFF") else "OFF")):
        if call("GET", f"/items/{name}")[1]["state"] in ("NULL", "UNDEF"):
            print(f"item {name} state {initial}", call("PUT", f"/items/{name}/state", initial, "text/plain")[0])
    exists = call("GET", f"/rules/{UID}")[0] == 200
    print(f"rule {UID}", f"PUT {call('PUT', f'/rules/{UID}', RULE)[0]}" if exists else
          f"POST {call('POST', '/rules', RULE)[0]}")
    if status == 200:
        print(f"item {FORMER} DELETE", call("DELETE", f"/items/{FORMER}")[0])
