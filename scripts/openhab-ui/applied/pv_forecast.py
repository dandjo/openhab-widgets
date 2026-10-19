#!/usr/bin/env python3
"""The house's own PV forecast as items (user, 2026-10-19), for heatpump_dhw_management's 60 °C on the sun's budget
(dhw_sun_budget.py): the rule pv_forecast (pv_forecast.js next to this file) reads Open-Meteo's forecast of the
irradiance on the modules' three 25° planes (east: 8 modules on string 1; west 8 and north 6 on string 2) every
30 minutes and at startup, for today and tomorrow, and weighs the planes by factors it fits once a day (from 1 h) on the
afternoons (12 to 18 h) of the last 14 days of Open-Meteo's archived forecasts against the strings' power.
- pv_forecast_hourly (String, MapDB restores it): {"at": fetched, "fit": fitted (epoch s, null with the defaults),
  "k": the factors (W per W/m²), "h": [[hour's start, W], ...]}, read by heatpump_dhw_management, which takes a
  forecast older than 3 hours for none;
- pv_forecast_power (W): the same hours as a forecast series in InfluxDB through the group influxdb_forecast (policy
  ADD, only changed points), each hour's mean at the hour's middle, set for the running hour.
On 20 September to 18 October 2026, fitted like this, the afternoon from 13 to 18 h came out 0.5 kWh off on average
(0.2 kWh too high); with the whole day fitted, 0.7 kWh (0.6 too high). Tested in mini-racer with the real answers
(the fit against the same fit in Python, the series, a restart, the daily fit, Open-Meteo or its archive down, no PV
readings).
apply creates or updates the equipment, its items, their metadata and the rule, and runs the rule once.
Usage: pv_forecast.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
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
SCRIPT = open(os.path.join(HERE, "pv_forecast.js"), encoding="utf-8").read()
UID = "pv_forecast"
GROUP = "pv_forecast"
ITEMS = {
    GROUP: {"type": "Group", "label": "PV Prognose", "category": "material:solar_power", "tags": ["Equipment"],
            "groupNames": []},
    "pv_forecast_power": {"type": "Number:Power", "label": "PV Prognose Leistung", "category": "material:solar_power",
                          "tags": ["Power", "Measurement"], "groupNames": [GROUP, "influxdb_forecast"]},
    "pv_forecast_hourly": {"type": "String", "label": "PV Prognose Stunden", "category": "material:schedule",
                           "tags": ["Status"], "groupNames": [GROUP, "mapdb_change_restore"]},
}
for name, item in ITEMS.items():
    item["name"] = name
METADATA = {
    GROUP: {},
    "pv_forecast_power": {"unit": {"value": "W"},
                          "stateDescription": {"value": " ", "config": {"pattern": "%.0f %unit%", "readOnly": True}}},
    "pv_forecast_hourly": {"stateDescription": {"value": " ", "config": {"readOnly": True}}},
}
RULE = {
    "uid": UID,
    "name": "PV Prognose",
    "description": RULE_DESCRIPTIONS[UID],
    "tags": [],
    # every 30 minutes, apart from the weather rule's (7:17 and 37:17) and the EEG's quarter hours
    "triggers": [{"id": "1", "type": "timer.GenericCronTrigger", "configuration": {"cronExpression": "40 3/30 * * * ? *"}},
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
for group in ("influxdb_forecast", "mapdb_change_restore"):
    assert call("GET", f"/items/{group}")[0] == 200, f"group {group} missing"
for name in ITEMS:
    status, item = call("GET", f"/items/{name}")
    print(f"item {name}:", f"exists, state {str(item['state'])[:60]}" if status == 200 else "missing")
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
