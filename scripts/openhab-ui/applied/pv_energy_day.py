#!/usr/bin/env python3
"""The day's PV and battery figures the inverter's counters do not give (user, 2026-10-19, after the inverter's yield
turned out to count the battery's discharge): rule photovoltaics_energy_day (pv_energy_day.js next to this file)
writes every minute, from InfluxDB since midnight,
- photovoltaics_generation_day: the strings' energy since midnight (kWh), the PV generation;
- photovoltaics_peak_day: the strings' highest input power since midnight (W);
- energy_storage_grid_charge_day: what the inverter drew from the AC side to charge the battery from the grid (kWh),
  its active power below zero; checked on 4, 17 and 25 December 2025 and 5 January 2026: the inverter's yield − export
  + import − this matched the house's own power integral within 0.1 kWh (home_ec_day without it: 7.8 to 9.2 kWh high).
All three persisted on change and every few minutes like the inverter's day counters.
apply creates or updates the items, their metadata and the rule, and runs it once.
Usage: pv_energy_day.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
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
SCRIPT = open(os.path.join(HERE, "pv_energy_day.js"), encoding="utf-8").read()
UID = "photovoltaics_energy_day"
PERSIST = ["influxdb_change", "influxdb_periodic"]
ITEMS = {
    "photovoltaics_generation_day": {"type": "Number:Energy", "label": "Photovoltaik Erzeugung heute",
                                     "category": "material:solar_power", "tags": ["Energy", "Measurement"],
                                     "groupNames": ["photovoltaics", *PERSIST]},
    "photovoltaics_peak_day": {"type": "Number:Power", "label": "Photovoltaik Spitze heute",
                               "category": "material:solar_power", "tags": ["Power", "Measurement"],
                               "groupNames": ["photovoltaics", *PERSIST]},
    "energy_storage_grid_charge_day": {"type": "Number:Energy", "label": "Batteriespeicher Netzladung heute",
                                       "category": "material:battery_charging_full", "tags": ["Energy", "Measurement"],
                                       "groupNames": ["huawei_inverter_energy_storage", *PERSIST]},
}
for name, item in ITEMS.items():
    item["name"] = name
METADATA = {
    "photovoltaics_generation_day": {"unit": {"value": "kWh"},
                                     "stateDescription": {"value": " ", "config": {"pattern": "%.2f %unit%", "readOnly": True}}},
    "photovoltaics_peak_day": {"unit": {"value": "W"},
                               "stateDescription": {"value": " ", "config": {"pattern": "%.0f %unit%", "readOnly": True}}},
    "energy_storage_grid_charge_day": {"unit": {"value": "kWh"},
                                       "stateDescription": {"value": " ", "config": {"pattern": "%.2f %unit%", "readOnly": True}}},
}
RULE = {
    "uid": UID,
    "name": "Photovoltaik Tagesenergie",
    "description": RULE_DESCRIPTIONS[UID],
    "tags": [],
    # every minute at its 30th second, apart from the rules on the full minute
    "triggers": [{"id": "1", "type": "timer.GenericCronTrigger", "configuration": {"cronExpression": "30 * * * * ? *"}},
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
for name in ITEMS:
    status, item = call("GET", f"/items/{name}")
    print(f"item {name}:", f"exists, state {item['state']}" if status == 200 else "missing")
exists = call("GET", f"/rules/{UID}")[0] == 200
print(f"rule {UID}:", "exists" if exists else "missing", f"(script {len(SCRIPT)} chars)")
if apply:
    for name, item in ITEMS.items():
        print(f"item {name} PUT", call("PUT", f"/items/{name}", item)[0])
        for namespace, meta in METADATA[name].items():
            print(f"  metadata {namespace} PUT", call("PUT", f"/items/{name}/metadata/{namespace}", meta)[0])
    print(f"rule {UID}", f"PUT {call('PUT', f'/rules/{UID}', RULE)[0]}" if exists else f"POST {call('POST', '/rules', RULE)[0]}")
    print(f"rule {UID} runnow", call("POST", f"/rules/{UID}/runnow", {})[0])
