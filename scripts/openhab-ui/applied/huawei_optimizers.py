#!/usr/bin/env python3
"""The optimizers on string 2 of the Huawei inverter as items (user, 2026-10-20), filled by the rule huawei_optimizers
(huawei_optimizers.js next to this file), which reads the inverter's file of their readings through huawei_modbus_proxy:
- per optimizer (FusionSolar's 1.0.<address>; north 1.0.1 to 1.0.6, west 1.0.7 to 1.0.14) huawei_optimizer_<aa>_power,
  _temperature and _energy (lifetime), persisted by the rule with each reading's own time, and _energy_day (today's,
  only the state);
- per plane huawei_optimizers_west_/north_power and _energy_day, and huawei_optimizers_temperature_max (the hottest),
  persisted the same way;
- huawei_optimizers_east_energy_total: string 1's lifetime yield (east, without optimizers) estimated by the rule from
  the optimizers' counters and the strings' measured ratio, restored by MapDB;
- huawei_optimizers_status (how many run, which do not, alarms), huawei_optimizers_updated (the newest reading's time)
  and huawei_optimizers_state (the gap still to read and the serial numbers, JSON), restored by MapDB.
The series are in no InfluxDB persistence group: the rule persists every reading with its time, and openHAB would store
the states again with the time they were set.
apply creates or updates the equipment, its items, their metadata and the rule.
Usage: huawei_optimizers.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
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
UID = "huawei_optimizers"
GROUP = "huawei_optimizers"
P = GROUP + "_"
PLANES = {"north": ("Nord", range(1, 7)), "west": ("West", range(7, 15))}


def point(type_, label, category, tags, restore=False):
    return {"type": type_, "label": label, "category": category, "tags": tags,
            "groupNames": [GROUP, "mapdb_change_restore"] if restore else [GROUP]}


def state(pattern, **cfg):
    return {"stateDescription": {"value": " ", "config": {"pattern": pattern, "readOnly": True, **cfg}}}


POWER = {"unit": {"value": "W"}, **state("%.0f %unit%")}
TEMPERATURE = {"unit": {"value": "°C"}, **state("%.1f %unit%")}
LIFETIME = {"unit": {"value": "kWh"}, **state("%.1f %unit%")}
TODAY = {"unit": {"value": "kWh"}, **state("%.2f %unit%")}

ITEMS = {GROUP: {"type": "Group", "label": "PV Optimierer", "category": "material:solar_power", "tags": ["Equipment"],
                 "groupNames": ["photovoltaics"]}}
METADATA = {GROUP: {}}
for plane, (name, addresses) in PLANES.items():
    for a in addresses:
        q, label = f"huawei_optimizer_{a:02d}_", f"PV Optimierer {name} 1.0.{a}"
        ITEMS[q + "power"] = point("Number:Power", f"{label} Leistung", "material:solar_power", ["Power", "Measurement"])
        ITEMS[q + "temperature"] = point("Number:Temperature", f"{label} Temperatur", "material:thermostat",
                                         ["Temperature", "Measurement"])
        ITEMS[q + "energy"] = point("Number:Energy", f"{label} Ertrag gesamt", "material:solar_power",
                                    ["Energy", "Measurement"])
        ITEMS[q + "energy_day"] = point("Number:Energy", f"{label} Ertrag heute", "material:solar_power",
                                        ["Energy", "Measurement"])
        METADATA.update({q + "power": POWER, q + "temperature": TEMPERATURE, q + "energy": LIFETIME,
                         q + "energy_day": TODAY})
for plane, (name, _) in PLANES.items():
    ITEMS[f"{P}{plane}_power"] = point("Number:Power", f"PV Optimierer {name} Leistung", "material:solar_power",
                                       ["Power", "Measurement"])
    ITEMS[f"{P}{plane}_energy_day"] = point("Number:Energy", f"PV Optimierer {name} Ertrag heute", "material:solar_power",
                                            ["Energy", "Measurement"])
    METADATA.update({f"{P}{plane}_power": POWER, f"{P}{plane}_energy_day": TODAY})
# string 1 (east) has no optimizers: its lifetime yield estimated by the rule, for the east modules on the PV page
ITEMS[P + "east_energy_total"] = point("Number:Energy", "PV Ost Ertrag gesamt (geschätzt)", "material:solar_power",
                                       ["Energy", "Measurement"], restore=True)
METADATA[P + "east_energy_total"] = LIFETIME
ITEMS[P + "temperature_max"] = point("Number:Temperature", "PV Optimierer Temperatur max.", "material:thermostat",
                                     ["Temperature", "Measurement"])
ITEMS[P + "status"] = point("String", "PV Optimierer Status", "material:info", ["Status"], restore=True)
ITEMS[P + "updated"] = point("DateTime", "PV Optimierer Messzeitpunkt", "material:schedule", ["Timestamp", "Point"],
                             restore=True)
ITEMS[P + "state"] = point("String", "PV Optimierer Zustand", "material:data_object", ["Status"], restore=True)
METADATA.update({P + "temperature_max": TEMPERATURE, P + "status": state("%s"), P + "updated": state("%1$td.%1$tm. %1$tR"),
                 P + "state": state("%s")})
for name, item in ITEMS.items():
    item["name"] = name

RULE = {
    "uid": UID,
    "name": "PV Optimierer",
    "description": RULE_DESCRIPTIONS[UID],
    "tags": [],
    # every minute at :30; the script decides whether this minute reads live readings or a piece of a gap
    "triggers": [{"id": "1", "type": "timer.GenericCronTrigger", "configuration": {"cronExpression": "30 * * * * ? *"}}],
    "conditions": [],
    "actions": [{"id": "2", "type": "script.ScriptAction",
                 "configuration": {"type": "application/javascript",
                                   "script": open(os.path.join(HERE, "huawei_optimizers.js"), encoding="utf-8").read()}}],
}


def call(method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, method=method, data=data,
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            text = r.read().decode()
            return r.status, json.loads(text) if text.startswith(("{", "[")) else text
    except urllib.error.HTTPError as e:
        return e.code, None


apply = sys.argv[1] == "apply"
for group in ("photovoltaics", "mapdb_change_restore"):
    assert call("GET", f"/items/{group}")[0] == 200, f"group {group} missing"
missing = [name for name in ITEMS if call("GET", f"/items/{name}")[0] != 200]
print(f"items: {len(ITEMS)}, missing {len(missing)}")
exists = call("GET", f"/rules/{UID}")[0] == 200
print(f"rule {UID}:", "exists" if exists else "missing", f"(script {len(RULE['actions'][0]['configuration']['script'])} chars)")
if apply:
    for name, item in ITEMS.items():
        status = call("PUT", f"/items/{name}", item)[0]
        meta = [call("PUT", f"/items/{name}/metadata/{ns}", m)[0] for ns, m in METADATA[name].items()]
        if status not in (200, 201) or any(m not in (200, 201) for m in meta):
            print(f"item {name}: PUT {status}, metadata {meta}")
    print(f"items PUT: {len(ITEMS)}")
    print(f"rule {UID}", f"PUT {call('PUT', f'/rules/{UID}', RULE)[0]}" if exists else f"POST {call('POST', '/rules', RULE)[0]}")
