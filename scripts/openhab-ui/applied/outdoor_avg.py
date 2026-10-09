#!/usr/bin/env python3
"""The outdoor temperature the heating curve works with (user, 2026-10-09): the rule heatpump_outdoor_average smooths
the heat pump's outdoor sensor espaltherma_ext_ambient_temp as the controller does and writes the result into
espaltherma_ext_ambient_temp_avg every quarter hour and at start. The controller's averaging acts as an exponential
mean whose time constant is its averaging time: over both heating seasons the leaving water setpoint followed such a
mean with 24 h at 0.21 K rms, a plain mean over the last 24 h at 0.35 K (36 h: 0.29). ESPAltherma does not report
that time (none of its register definitions holds it), so it stands in the item's metadata 'averaging' (hours, 0 =
none, 24 here); a change of the controller's setting needs only that value changed, not a new item.
Usage: outdoor_avg.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080/rest"
TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
ITEM = "espaltherma_ext_ambient_temp_avg"
ITEM_DTO = {"type": "Number:Temperature", "name": ITEM, "label": "ESPAltherma Außentemperatur gemittelt",
            "category": "material:thermostat", "tags": ["Measurement", "Temperature"],
            "groupNames": ["espaltherma", "influxdb_change", "mapdb_change_restore"]}
METADATA = {"unit": {"value": "°C", "config": {}},
            "stateDescription": {"value": " ", "config": {"pattern": "%.1f %unit%"}},
            "averaging": {"value": "24", "config": {}}}
SCRIPT = """// the outdoor temperature the heating curve works with: the heat pump's outdoor sensor smoothed as the controller
// does it, an exponential mean whose time constant is the controller's averaging time (a plain mean over that time
// matched the setpoint worse); ESPAltherma does not report that time, so it stands in this item's metadata
// 'averaging' (hours, 0 = none). Each run carries the last mean forward by the sensor's mean since then: the exact one
// of the last run, after a start the last one stored; the item gets it to a tenth, as the sensor reads.
const target = items.getItem('espaltherma_ext_ambient_temp_avg');
const source = items.getItem('espaltherma_ext_ambient_temp');
const meta = target.getMetadata('averaging');
const hours = meta !== null && meta.value.trim() !== '' && !isNaN(Number(meta.value)) ? Number(meta.value) : 24;
const now = time.toZDT();
if (source.numericState !== null) {
  let mean = null;
  if (hours <= 0) {
    cache.private.remove('mean');
    mean = source.numericState;
  } else {
    let last = cache.private.get('mean');
    if (last === null || last === undefined) {
      const stored = target.persistence.persistedState(now, 'influxdb');
      last = stored === null || stored.numericState === null ? null : { value: stored.numericState, at: stored.timestamp };
    }
    if (last === null) {
      const seed = source.persistence.averageSince(now.minusHours(hours), 'influxdb');
      mean = seed === null ? null : seed.numericState;
    } else {
      const seconds = (now.toInstant().toEpochMilli() - last.at.toInstant().toEpochMilli()) / 1000;
      const input = seconds > 0 ? source.persistence.averageSince(last.at, 'influxdb') : null;
      mean = input === null || input.numericState === null ? last.value :
        last.value + (1 - Math.exp(-seconds / (hours * 3600))) * (input.numericState - last.value);
    }
    if (mean !== null) {
      cache.private.put('mean', { value: mean, at: now });
    }
  }
  if (mean !== null) {
    target.postUpdate(Quantity(mean.toFixed(1) + ' °C'));
  }
}
"""
RULE = {
    "uid": "heatpump_outdoor_average",
    "name": "Wärmepumpe Außentemperatur gemittelt",
    "description": "Glättet die Außentemperatur der Wärmepumpe (espaltherma_ext_ambient_temp) wie die Regelung für "
                   "die Heizkurve: exponentielles Mittel mit der Mittelungszeit aus dem Metadatum 'averaging' von "
                   "espaltherma_ext_ambient_temp_avg (Stunden) als Zeitkonstante; schreibt es jede Viertelstunde und "
                   "beim Start dorthin.",
    "tags": [],
    "triggers": [{"id": "1", "type": "timer.GenericCronTrigger", "configuration": {"cronExpression": "0 0/15 * * * ? *"}},
                 {"id": "2", "type": "core.SystemStartlevelTrigger", "configuration": {"startlevel": 100}}],
    "conditions": [],
    "actions": [{"id": "3", "type": "script.ScriptAction",
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
print("rule heatpump_outdoor_average:", "exists" if call("GET", "/rules/heatpump_outdoor_average") == 200 else "missing")
if apply:
    print(ITEM, "PUT", call("PUT", f"/items/{ITEM}", ITEM_DTO))
    for ns, body in METADATA.items():
        print(f"  metadata {ns} PUT", call("PUT", f"/items/{ITEM}/metadata/{ns}", body))
    exists = call("GET", "/rules/heatpump_outdoor_average") == 200
    print("rule", "PUT " + str(call("PUT", "/rules/heatpump_outdoor_average", RULE)) if exists else
          "POST " + str(call("POST", "/rules", RULE)))
    print("run now:", call("POST", "/rules/heatpump_outdoor_average/runnow", {}))
