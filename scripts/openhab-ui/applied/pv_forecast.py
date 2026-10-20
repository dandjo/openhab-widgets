#!/usr/bin/env python3
"""The house's PV forecast as items (user, 2026-10-19), written by pv_forecast_ml (/opt/pv_forecast_ml, systemd timers
as pi, README there) since the rule pv_forecast was removed (user, 2026-10-20): a gradient boosting model per string
on the raw data alone (ten weather models' irradiance on the modules' three 25° planes, the weather, the sun's
position), every 30 minutes (2 and 32 past) for today and tomorrow, for heatpump_dhw_management's 60 °C on the sun's
budget (dhw_sun_budget.py) and the Photovoltaik page.
- pv_forecast_hourly (String, MapDB restores it): {"at": written (epoch s), "trained": the model's training, "source":
  "ml" (or "plain", the plain physical forecast, while no model exists), "h": [[hour's start, W], ...]}, read by
  heatpump_dhw_management, which takes a forecast older than 3 hours for none;
- pv_forecast_power (W): the same hours as a forecast series in InfluxDB (group influxdb_forecast; the service writes
  the points straight into InfluxDB, only changed ones), each hour's mean at the hour's middle, set for the running hour;
- pv_forecast_pv1_power, pv_forecast_pv2_power (W): the strings' forecasts as pv_forecast_power, whose sum it is (a
  model per string, user, 2026-10-20), for the Photovoltaik page's strings;
- pv_forecast_energy (kWh): each day's total from today on at the day's 23:59:59 (forecast series, as the daily
  totals energy_daily_* stand), set to today's, for the Photovoltaik page's yield per day;
- pv_forecast_energy_tomorrow (kWh): tomorrow's total, persisted on change (the day-ahead forecasts' history).
apply creates or updates the equipment, its items and their metadata, and removes what the rule left: the rule
pv_forecast and the item pv_forecast_ml_hourly.
Usage: pv_forecast.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080/rest"
TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
GROUP = "pv_forecast"
ITEMS = {
    # an equipment of the house's PV in the model (user, 2026-10-19)
    GROUP: {"type": "Group", "label": "PV Prognose", "category": "material:solar_power", "tags": ["Equipment"],
            "groupNames": ["photovoltaics"]},
    "pv_forecast_power": {"type": "Number:Power", "label": "PV Prognose Leistung", "category": "material:solar_power",
                          "tags": ["Power", "Measurement"], "groupNames": [GROUP, "influxdb_forecast"]},
    # the strings' (user, 2026-10-20)
    **{f"pv_forecast_pv{n}_power": {"type": "Number:Power", "label": f"PV Prognose PV{n} Leistung",
                                    "category": "material:solar_power", "tags": ["Power", "Measurement"],
                                    "groupNames": [GROUP, "influxdb_forecast"]} for n in (1, 2)},
    "pv_forecast_hourly": {"type": "String", "label": "PV Prognose Stunden", "category": "material:schedule",
                           "tags": ["Status"], "groupNames": [GROUP, "mapdb_change_restore"]},
    "pv_forecast_energy": {"type": "Number:Energy", "label": "PV Prognose Tagesenergie", "category": "material:solar_power",
                           "tags": ["Energy", "Measurement"], "groupNames": [GROUP, "influxdb_forecast"]},
    # tomorrow's total as it is forecast through the day, its history the day-ahead forecasts
    "pv_forecast_energy_tomorrow": {"type": "Number:Energy", "label": "PV Prognose Tagesenergie morgen",
                                    "category": "material:solar_power", "tags": ["Energy", "Measurement"],
                                    "groupNames": [GROUP, "influxdb_change"]},
}
for name, item in ITEMS.items():
    item["name"] = name
METADATA = {
    GROUP: {},
    "pv_forecast_power": {"unit": {"value": "W"},
                          "stateDescription": {"value": " ", "config": {"pattern": "%.0f %unit%", "readOnly": True}}},
    **{f"pv_forecast_pv{n}_power": {"unit": {"value": "W"},
                                    "stateDescription": {"value": " ", "config": {"pattern": "%.0f %unit%",
                                                                                  "readOnly": True}}} for n in (1, 2)},
    "pv_forecast_hourly": {"stateDescription": {"value": " ", "config": {"readOnly": True}}},
    "pv_forecast_energy": {"unit": {"value": "kWh"},
                           "stateDescription": {"value": " ", "config": {"pattern": "%.1f %unit%", "readOnly": True}}},
    "pv_forecast_energy_tomorrow": {"unit": {"value": "kWh"},
                                    "stateDescription": {"value": " ", "config": {"pattern": "%.1f %unit%",
                                                                                  "readOnly": True}}},
}
# what the rule pv_forecast left, removed (user, 2026-10-20)
RETIRED = {"rule": "pv_forecast", "item": "pv_forecast_ml_hourly"}


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
for group in ("influxdb_forecast", "mapdb_change_restore", "influxdb_change"):
    assert call("GET", f"/items/{group}")[0] == 200, f"group {group} missing"
for name in ITEMS:
    status, item = call("GET", f"/items/{name}")
    print(f"item {name}:", f"exists, state {str(item['state'])[:60]}" if status == 200 else "missing")
rule_left = call("GET", f"/rules/{RETIRED['rule']}")[0] == 200
item_left = call("GET", f"/items/{RETIRED['item']}")[0] == 200
print(f"rule {RETIRED['rule']}:", "exists, to remove" if rule_left else "gone")
print(f"item {RETIRED['item']}:", "exists, to remove" if item_left else "gone")
if apply:
    for name, item in ITEMS.items():
        print(f"item {name} PUT", call("PUT", f"/items/{name}", item)[0])
        for namespace, meta in METADATA[name].items():
            print(f"  metadata {namespace} PUT", call("PUT", f"/items/{name}/metadata/{namespace}", meta)[0])
    if rule_left:
        print(f"rule {RETIRED['rule']} DELETE", call("DELETE", f"/rules/{RETIRED['rule']}")[0])
    if item_left:
        print(f"item {RETIRED['item']} DELETE", call("DELETE", f"/items/{RETIRED['item']}")[0])
