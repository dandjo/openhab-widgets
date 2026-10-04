#!/usr/bin/env python3
"""heatpump_metering: the heating power no higher than the heat pump can deliver (user, 2026-10-05: above 18 kW, up to
22.8 kW, which the machine cannot do). The power comes from flow × spread; at the start of a hot-water charge cold water
from the tank meets the warm water still standing in the unit, and for 5 to 20 s the spread shows 8 to 10 K at a
compressor just starting. Capped: the compressor's heat at its circuit's draw (heatpump_power) times 0.8 of the Carnot
COP between the leaving water before the backup heater (+3 K) and the outdoor air (-7 K), above the 0.77 the unit
reaches in 99 % of the steady minutes of winter 2025/26 (median 0.63), and at most 12 kW, its highest steady output;
after the backup heater its nominal power on top while it runs. Without a reading of the circuit nothing is capped.
Replayed on September 2026: 2.9 % of the values capped, the day's heat 0.3 % lower in the median, at most 2.5 %.
Replaces the heat section of the live rule's script through the REST API; refuses if that section changed.
Usage: hp_heat_cap.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080/rest"
TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
UID = "heatpump_metering"
OLD = """  const diff_temp_after_buh = items.getItem('espaltherma_leaving_water_temp_after_buh').numericState - inlet_temp;
  heating_power_after_buh += flow_kg_h * thermal_capacity * diff_temp_after_buh;
"""
NEW = """  const diff_temp_after_buh = items.getItem('espaltherma_leaving_water_temp_after_buh').numericState - inlet_temp;
  heating_power_after_buh += flow_kg_h * thermal_capacity * diff_temp_after_buh;
  // no more than the heat pump can deliver: its compressor's circuit times 0.8 of the Carnot COP between the leaving
  // water (+3 K) and the outdoor air (-7 K), at most 12 kW, the backup heater's nominal power on top; flow × spread
  // overshoots at the start of a hot-water charge, when cold tank water meets the warm water in the unit
  // (see applied/hp_heat_cap.py)
  const circuit = items.getItem('heatpump_power').numericState;
  if (circuit !== null) {
    const leaving = items.getItem('espaltherma_leaving_water_temp_before_buh').numericState;
    const outdoor = items.getItem('espaltherma_ext_ambient_temp').numericState;
    const t_cond = (leaving === null ? 35 : leaving) + 273.15 + 3;
    const t_evap = (outdoor === null ? 7 : outdoor) + 273.15 - 7;
    const compressor_max = Math.min(12000, 0.8 * t_cond / Math.max(5, t_cond - t_evap) * Math.max(0, circuit));
    const buh_heat = (items.getItem('espaltherma_buh_step1_mode').state === 'ON' ? buh1_power : 0)
      + (items.getItem('espaltherma_buh_step2_mode').state === 'ON' ? buh2_power : 0);
    heating_power_before_buh = Math.min(heating_power_before_buh, compressor_max);
    heating_power_after_buh = Math.min(heating_power_after_buh, compressor_max + buh_heat);
  }
"""


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        data = r.read()
        return r.status, (json.loads(data) if data else None)


_, rule = call("GET", f"/rules/{UID}")
script = rule["actions"][0]["configuration"]["script"]
if NEW in script:
    print("already applied")
    sys.exit(0)
assert script.count(OLD) == 1, "the heat section of the rule changed since this script was written"
for name in ("buh1_power", "buh2_power"):
    assert f"const {name}" in script, f"{name} is not defined in the rule"
print("would replace the heat section of", UID)
if sys.argv[1] == "apply":
    rule["actions"][0]["configuration"]["script"] = script.replace(OLD, NEW)
    body = {k: rule[k] for k in ("uid", "name", "description", "tags", "visibility", "triggers", "conditions", "actions",
                                 "configuration", "configDescriptions") if k in rule}
    print("PUT", call("PUT", f"/rules/{UID}", body)[0])
