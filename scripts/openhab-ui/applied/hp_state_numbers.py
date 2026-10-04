#!/usr/bin/env python3
"""The heat pump's defrost (a switch) and three-way valve (a text) mirrored as numbers, 1 for defrosting and for hot
water, 0 otherwise, by the rule heatpump_state_numbers: MainUI's chart series read an item's states as numbers, so only
these can name the states in a chart's shared tooltip (the bands stay drawn from the original items).
Usage: hp_state_numbers.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080/rest"
TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
GROUPS = ["influxdb_change", "influxdb_periodic"]
ITEMS = {
    "heatpump_defrost_value": "Wärmepumpe Abtauen als Zahl (1 = Abtauen)",
    "heatpump_valve_value": "Wärmepumpe 3-Wege-Ventil als Zahl (1 = Warmwasser)",
}
SCRIPT = """// mirrors the heat pump's defrost (a switch) and three-way valve (a text) as numbers, 1 for defrosting and for hot
// water, 0 otherwise: MainUI's chart series read an item's states as numbers, so only these can name the states in a
// chart's shared tooltip; the bands in the charts stay drawn from the original items
const pairs = [['espaltherma_defrost_operaton', 'heatpump_defrost_value', 'ON'],
               ['espaltherma_3way_valve_mode', 'heatpump_valve_value', 'DHW']];
for (const [source, target, on] of pairs) {
  const state = items.getItem(source).state;
  if (state === 'NULL' || state === 'UNDEF') {
    continue;
  }
  items.getItem(target).postUpdate(state === on ? 1 : 0);
}
"""
RULE = {
    "uid": "heatpump_state_numbers",
    "name": "Wärmepumpe Zustände als Zahlen",
    "description": "Spiegelt Abtauen (espaltherma_defrost_operaton) und 3-Wege-Ventil (espaltherma_3way_valve_mode) als "
                   "Zahlen in heatpump_defrost_value und heatpump_valve_value (1 = Abtauen bzw. Warmwasser), damit "
                   "der gemeinsame Tooltip der Diagramme ihren Zustand nennen kann.",
    "tags": [],
    "triggers": [{"id": "1", "type": "core.ItemStateChangeTrigger", "configuration": {"itemName": "espaltherma_defrost_operaton"}},
                 {"id": "2", "type": "core.ItemStateChangeTrigger", "configuration": {"itemName": "espaltherma_3way_valve_mode"}},
                 {"id": "3", "type": "core.SystemStartlevelTrigger", "configuration": {"startlevel": 100}}],
    "conditions": [],
    "actions": [{"id": "4", "type": "script.ScriptAction",
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
for name, label in ITEMS.items():
    exists = call("GET", f"/items/{name}") == 200
    print(f"item {name}: {'exists' if exists else 'missing'}", end="")
    if apply:
        print(" -> PUT", call("PUT", f"/items/{name}", {"type": "Number", "name": name, "label": label,
                                                         "category": "", "tags": [], "groupNames": GROUPS}))
    else:
        print()
exists = call("GET", "/rules/heatpump_state_numbers") == 200
print(f"rule heatpump_state_numbers: {'exists' if exists else 'missing'}", end="")
if apply:
    print(" ->", "PUT", call("PUT", "/rules/heatpump_state_numbers", RULE) if exists else
          ("POST " + str(call("POST", "/rules", RULE))))
    print("run now:", call("POST", "/rules/heatpump_state_numbers/runnow", {}))
else:
    print()
