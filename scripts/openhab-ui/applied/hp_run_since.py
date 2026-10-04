#!/usr/bin/env python3
"""Since when the tank charges and since when the heating circuits carry water, for the runtime lines of the heating
card (user, 2026-10-04): the rule heatpump_run_since sets heatpump_dhw_since and heatpump_heating_since when a run
starts and sets them UNDEF once it has rested for 5 minutes, so a flickering pump or flow does not restart them.
A run of the tank: the pump running (or water flowing) with the valve on DHW, or its booster heater heating; of the
heating: the pump running with the valve on the heating circuits.
Usage: hp_run_since.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080/rest"
TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
ITEMS = {"heatpump_dhw_since": "Wärmepumpe Warmwasser lädt seit",
         "heatpump_heating_since": "Wärmepumpe Heizung läuft seit"}
SCRIPT = """// since when the tank charges and since when the heating circuits carry water, for the heating card's runtime lines;
// a run ends after 5 minutes of rest, so a flickering pump or flow does not restart it
const flow = items.getItem('espaltherma_flow_sensor').numericState || 0;
const pump = items.getItem('espaltherma_water_pump_operation').state === 'ON' || flow > 0;
const dhw = items.getItem('espaltherma_3way_valve_mode').state === 'DHW';
const bsh = items.getItem('espaltherma_bsh_mode').state === 'ON';
const now = time.toZDT();
for (const [name, active] of [['heatpump_dhw_since', (pump && dhw) || bsh], ['heatpump_heating_since', pump && !dhw]]) {
  const item = items.getItem(name);
  const running = item.state !== 'NULL' && item.state !== 'UNDEF';
  if (active) {
    cache.private.put(name, now.toInstant().toEpochMilli());
    if (!running) {
      item.postUpdate(now);
    }
  } else if (running) {
    const last = cache.private.get(name);
    if (last === null || last === undefined || now.toInstant().toEpochMilli() - last > 5 * 60 * 1000) {
      item.postUpdate('UNDEF');
    }
  }
}
"""
RULE = {
    "uid": "heatpump_run_since",
    "name": "Wärmepumpe Laufzeit seit",
    "description": "Merkt sich, seit wann der Warmwasserspeicher lädt (heatpump_dhw_since) und seit wann die Heizkreise "
                   "Wasser bekommen (heatpump_heating_since), für die Laufzeit-Zeilen der Karte Heizung & Warmwasser; "
                   "ein Lauf endet nach 5 Minuten Ruhe.",
    "tags": [],
    "triggers": [{"id": "1", "type": "core.ItemStateChangeTrigger", "configuration": {"itemName": n}}
                 for n in ("espaltherma_water_pump_operation", "espaltherma_flow_sensor", "espaltherma_3way_valve_mode",
                           "espaltherma_bsh_mode")] +
                [{"id": "5", "type": "timer.GenericCronTrigger", "configuration": {"cronExpression": "0 * * * * ? *"}}],
    "conditions": [],
    "actions": [{"id": "6", "type": "script.ScriptAction",
                 "configuration": {"type": "application/javascript", "script": SCRIPT}}],
}
for i, t in enumerate(RULE["triggers"]):
    t["id"] = str(i + 1)


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


apply = sys.argv[1] == "apply"
for name in ITEMS:
    print(f"item {name}:", "exists" if call("GET", f"/items/{name}") == 200 else "missing")
print("rule heatpump_run_since:", "exists" if call("GET", "/rules/heatpump_run_since") == 200 else "missing")
if apply:
    for name, label in ITEMS.items():
        print(name, "PUT", call("PUT", f"/items/{name}", {"type": "DateTime", "name": name, "label": label,
                                                         "category": "", "tags": [], "groupNames": []}))
    exists = call("GET", "/rules/heatpump_run_since") == 200
    print("rule", "PUT " + str(call("PUT", "/rules/heatpump_run_since", RULE)) if exists else
          "POST " + str(call("POST", "/rules", RULE)))
    print("run now:", call("POST", "/rules/heatpump_run_since/runnow", {}))
