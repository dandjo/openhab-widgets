#!/usr/bin/env python3
"""The battery's power averaged over the last 5 minutes, written every minute by the rule battery_power_5min into
huawei_inverter_energy_storage_power_5min (negative while charging, as the power): the base of the time until the
battery is full or empty that the energy flow shows (proposals 2026-10-04).
Usage: battery_power_5min.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080/rest"
TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
ITEM = "huawei_inverter_energy_storage_power_5min"
SCRIPT = """// the battery's power averaged over the last 5 minutes (negative while charging): the base of the time until it is
// full or empty in the energy flow
const average = items.getItem('huawei_inverter_energy_storage_power').persistence.averageSince(
  time.toZDT().minusMinutes(5), 'influxdb');
if (average !== null && average.numericState !== null) {
  items.getItem('huawei_inverter_energy_storage_power_5min').postUpdate(Quantity(Math.round(average.numericState) + ' W'));
}
"""
RULE = {
    "uid": "battery_power_5min",
    "name": "Batteriespeicher Leistung 5 min",
    "description": "Mittelt die Leistung des Batteriespeichers über die letzten 5 Minuten in "
                   "huawei_inverter_energy_storage_power_5min (negativ beim Laden): Grundlage der Zeit bis voll oder "
                   "leer im Energiefluss.",
    "tags": [],
    "triggers": [{"id": "1", "type": "timer.GenericCronTrigger", "configuration": {"cronExpression": "0 * * * * ? *"}}],
    "conditions": [],
    "actions": [{"id": "2", "type": "script.ScriptAction",
                 "configuration": {"type": "application/javascript", "script": SCRIPT}}],
}


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


apply = sys.argv[1] == "apply"
print(f"item {ITEM}:", "exists" if call("GET", f"/items/{ITEM}") == 200 else "missing")
print("rule battery_power_5min:", "exists" if call("GET", "/rules/battery_power_5min") == 200 else "missing")
if apply:
    print("item PUT", call("PUT", f"/items/{ITEM}", {"type": "Number:Power", "name": ITEM,
                                                      "label": "Batteriespeicher Leistung 5 min", "category": "",
                                                      "tags": [], "groupNames": []}))
    print("unit PUT", call("PUT", f"/items/{ITEM}/metadata/unit", {"value": "W", "config": {}}))
    print("pattern PUT", call("PUT", f"/items/{ITEM}/metadata/stateDescription",
                              {"value": " ", "config": {"pattern": "%.0f %unit%"}}))
    exists = call("GET", "/rules/battery_power_5min") == 200
    print("rule", "PUT " + str(call("PUT", "/rules/battery_power_5min", RULE)) if exists else
          "POST " + str(call("POST", "/rules", RULE)))
    print("run now:", call("POST", "/rules/battery_power_5min/runnow", {}))
