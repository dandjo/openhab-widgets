#!/usr/bin/env python3
"""heatpump_metering: the heating power without the inlet sensor's offset, and only while something heats (user,
2026-10-14). While the pump circulates and neither the compressor nor the backup heater runs, the leaving water after
the backup heater reads 0.70 K and the one before it 0.60 K above the inlet: the median of every such minute from
September 2024 on (189 days, 9,861 steady minutes at 22 to 25 °C, daily medians 0.65 to 0.80, no drift between the
seasons), where the water has no source but the pump (some 0.05 K). Flow × spread therefore showed 0.3 to 0.6 kW of
heat with only the pump running (3.1 kWh in the unheated night of 13/14 October 2026) and some 15 to 20 % too much
while running, for space heating and its COP alike. The leaving sensors agree within 0.1 K, so the inlet sensor is the
odd one; with the water standing they read their surroundings (after the heater 0.9 to 1.3 K, before it 3 to 12 K
above the inlet), which is no calibration. The offset could only be measured at 22 to 25 °C; hot-water charges
(45 to 55 °C) take the same, as the user agreed.
Now the spread is taken less the offset, and heat counts only while the compressor (the rule's isInverter) or the
backup heater runs; the cap of applied/hp_heat_cap.py stays after it. The history follows by
applied/hp_spread_offset_history.py.
The hot-water end estimate (heatpump_dhw_eta, applied/hp_dhw_eta.py) divides the heat power by the kWh one kelvin at the
tank's sensor takes, a table measured with the old heat; it takes the same correction: on the compressor's charges of
winter 2025/26 and summer 2026 the corrected heat is 0.814 to 0.835 of the old per 5 K of tank temperature, so 0.42,
0.46, 0.50, 0.53, 0.53, 0.58 kWh/K at 27 to 52 °C become 0.35, 0.38, 0.42, 0.44, 0.44, 0.47.
Replaces the heat section of heatpump_metering's script and the table in heatpump_dhw_eta's through the REST API;
refuses if either changed.
Usage: hp_spread_offset.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080/rest"
TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
UID = "heatpump_metering"
OLD = """if (items.getItem('espaltherma_operation_mode').state === 'Heating') {
  const flow_kg_h = items.getItem('espaltherma_flow_sensor').numericState * 60;  // converts l/min to kg/h for water
  const thermal_capacity = 1.1639;  // of water in Wh/(kg•K)
  const inlet_temp = items.getItem('espaltherma_inlet_water_temp').numericState;
  const diff_temp_before_buh = items.getItem('espaltherma_leaving_water_temp_before_buh').numericState - inlet_temp;
  heating_power_before_buh += flow_kg_h * thermal_capacity * diff_temp_before_buh;
  const diff_temp_after_buh = items.getItem('espaltherma_leaving_water_temp_after_buh').numericState - inlet_temp;
  heating_power_after_buh += flow_kg_h * thermal_capacity * diff_temp_after_buh;
"""
NEW = """// the inlet sensor reads below the leaving water sensors: with the pump circulating and nothing heating, the one after
// the backup heater shows 0.7 K more, the one before it 0.6 K (every such minute since September 2024, no drift); so
// the spread is taken less that offset, and heat counts only while the compressor or the backup heater runs: before,
// the pump alone showed 0.3-0.6 kW of heat (see applied/hp_spread_offset.py)
const spread_offset_before_buh = 0.6;  // K
const spread_offset_after_buh = 0.7;  // K

if (items.getItem('espaltherma_operation_mode').state === 'Heating' && (isInverter || isBuh)) {
  const flow_kg_h = items.getItem('espaltherma_flow_sensor').numericState * 60;  // converts l/min to kg/h for water
  const thermal_capacity = 1.1639;  // of water in Wh/(kg•K)
  const inlet_temp = items.getItem('espaltherma_inlet_water_temp').numericState;
  const diff_temp_before_buh = items.getItem('espaltherma_leaving_water_temp_before_buh').numericState - inlet_temp
    - spread_offset_before_buh;
  heating_power_before_buh += flow_kg_h * thermal_capacity * diff_temp_before_buh;
  const diff_temp_after_buh = items.getItem('espaltherma_leaving_water_temp_after_buh').numericState - inlet_temp
    - spread_offset_after_buh;
  heating_power_after_buh += flow_kg_h * thermal_capacity * diff_temp_after_buh;
"""


ETA_UID = "heatpump_dhw_eta"
ETA_OLD = "const kwhPerK = [[27, 0.42], [32, 0.46], [37, 0.50], [42, 0.53], [47, 0.53], [52, 0.58]];"
ETA_NEW = ("// with the heat less the inlet sensor's offset (applied/hp_spread_offset.py)\n"
           "const kwhPerK = [[27, 0.35], [32, 0.38], [37, 0.42], [42, 0.44], [47, 0.44], [52, 0.47]];")


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        data = r.read()
        return r.status, (json.loads(data) if data else None)


def patch(uid, old, new, what, checks=()):
    _, rule = call("GET", f"/rules/{uid}")
    script = rule["actions"][0]["configuration"]["script"]
    if new in script:
        print(f"{uid}: already applied")
        return
    assert script.count(old) == 1, f"{uid}: the {what} changed since this script was written"
    for check in checks:
        check(script)
    print(f"{uid}: would replace the {what}")
    if sys.argv[1] == "apply":
        rule["actions"][0]["configuration"]["script"] = script.replace(old, new)
        body = {k: rule[k] for k in ("uid", "name", "description", "tags", "visibility", "triggers", "conditions",
                                     "actions", "configuration", "configDescriptions") if k in rule}
        print(f"{uid}: PUT", call("PUT", f"/rules/{uid}", body)[0])


def defined_before(script):
    for name in ("isInverter", "isBuh"):
        assert script.index(f"const {name} =") < script.index(OLD), f"{name} is not defined before the heat section"


if len(sys.argv) != 2 or sys.argv[1] not in ("check", "apply"):
    raise SystemExit(__doc__.rsplit("\n", 1)[-1])
patch(UID, OLD, NEW, "heat section", (defined_before,))
patch(ETA_UID, ETA_OLD, ETA_NEW, "kWh per kelvin table")
