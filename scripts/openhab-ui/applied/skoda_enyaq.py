#!/usr/bin/env python3
"""The Škoda Enyaq's own data from the official MyŠkoda Public API (user, 2026-10-25): charge, range, charging,
odometer, locks and openings, parking position and climate as items in the equipment skoda_enyaq (part of e_car),
which the rule skoda_enyaq_status (skoda_enyaq.js next to this file) fills every 5 minutes while the car charges or
drives, otherwise every 15 (20 requests an hour per vehicle). A read does not wake the car: the values are what it
last reported, skoda_enyaq_updated says when. Four items take commands to the car (user, same day): the charge target
skoda_enyaq_charge_target (Ladeziel, 50 to 100 % in steps of 10; skoda_enyaq_charge_limit, Ladelimit, is the same set
value the car charges to, while skoda_enyaq_battery_care_target is what Škoda sets it back to after the next charge
with battery care on), skoda_enyaq_charging (ON starts, OFF stops a charge),
skoda_enyaq_climate (ON starts, OFF stops the air conditioning) and its target temperature skoda_enyaq_climate_target
(LO = 15.5 °C, 16 to 29.5 °C in steps of 0.5, HI = 30 °C as the app offers them, sent with the start); the same rule sends them, without autoupdate, so their state
changes once Škoda accepted the command, and reports in skoda_enyaq_command_result. The values the E-Auto page charts go into InfluxDB (the position too, the
user wanted its history); everything is restored after a restart.
The API key and the VIN are not in this file nor in the rule but in /var/lib/openhab/credentials/skoda-api.json on
homepi, {"apiKey": "...", "vin": "..."} (owner pi, group openhab, mode 640); a new key goes there.
apply creates or updates the equipment, its items, their metadata and the rule, and runs the rule once.
Usage: skoda_enyaq.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
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
SCRIPT = open(os.path.join(HERE, "skoda_enyaq.js"), encoding="utf-8").read()
UID = "skoda_enyaq_status"
GROUP = "skoda_enyaq"
P = GROUP + "_"

# where the values go: their course into InfluxDB (and every quarter hour for continuous charts), states on change;
# everything back after a restart, as the rule asks the API only every 5 to 15 minutes
COURSE = ["influxdb_change", "influxdb_periodic", "mapdb_change_restore"]
CHANGE = ["influxdb_change", "mapdb_change_restore"]
RESTORE = ["mapdb_change_restore"]

CHARGING_STATES = ("CHARGING=Lädt,READY_FOR_CHARGING=Ladebereit,CONSERVING=Ladeerhaltung,"
                   "CONNECT_CABLE=Nicht eingesteckt,CHARGING_INTERRUPTED=Unterbrochen,DISCHARGING=Entlädt")
CLIMATE_STATES = ("OFF=Aus,COOLING=Kühlt,HEATING=Heizt,HEATING_AUXILIARY=Heizt mit Zusatzheizung,VENTILATION=Lüftet,"
                  "COMPLETED=Fertig,UNKNOWN=Unbekannt,UNSUPPORTED=Nicht unterstützt")
API_STATES = ("OK=OK,KEY_EXPIRED=Schlüssel abgelaufen,NOT_AUTHORIZED=Nicht berechtigt,RATE_LIMITED=Limit erreicht,"
              "ERROR=Fehler,NO_CREDENTIALS=Keine Zugangsdaten")
OPEN_CLOSED = "OPEN=Offen,CLOSED=Geschlossen"


def state(pattern, **cfg):
    return {"stateDescription": {"value": " ", "config": {"pattern": pattern, "readOnly": True, **cfg}}}


def command(pattern, **cfg):
    """A state description for an item that takes commands; openHAB does not set its state from the command itself
    (autoupdate off), the rule does once the car's API accepted it."""
    return {"stateDescription": {"value": " ", "config": {"pattern": pattern, "readOnly": False, **cfg}},
            "autoupdate": {"value": "false"}}


def quantity(unit, pattern):
    return {"unit": {"value": unit}, **state(pattern)}


# suffix: (type, label after "Škoda Enyaq ", icon, tags, persistence groups, metadata)
POINTS = {
    "soc": ("Number:Dimensionless", "Ladestand", "battery_charging_full", ["Measurement", "Energy"], COURSE,
            quantity("%", "%.0f %unit%")),
    "range": ("Number:Length", "Reichweite", "route", ["Measurement"], COURSE, quantity("km", "%.0f %unit%")),
    "charging_state": ("String", "Ladestatus", "ev_station", ["Status"], CHANGE, state("%s", options=CHARGING_STATES)),
    "charge_power": ("Number:Power", "Ladeleistung", "bolt", ["Measurement", "Power"], COURSE,
                     quantity("kW", "%.1f %unit%")),
    "charge_type": ("String", "Ladeart", "electrical_services", ["Status"], CHANGE,
                    state("%s", options="AC=AC,DC=DC,OFF=Aus")),
    "full_at": ("DateTime", "Voll um", "schedule", ["Timestamp", "Point"], RESTORE, state("%1$ta %1$tR")),
    "charge_limit": ("Number:Dimensionless", "Ladelimit", "battery_full", ["Point"], CHANGE,
                     quantity("%", "%.0f %unit%")),
    "charge_target": ("Number:Dimensionless", "Ladeziel", "battery_charging_full", ["Setpoint"], CHANGE,
                      {"unit": {"value": "%"}, **command("%.0f %unit%", min=50, max=100, step=10)}),
    "charging": ("Switch", "Laden", "ev_station", ["Switch"], RESTORE, command("%s", options="ON=An,OFF=Aus")),
    "command_result": ("String", "letzter Befehl", "send", ["Status"], RESTORE, state("%s")),
    "battery_care": ("Switch", "Akkuschonung", "battery_saver", ["Status"], CHANGE,
                     state("%s", options="ON=An,OFF=Aus")),
    "battery_care_target": ("Number:Dimensionless", "Akkuschonung Ladeziel", "battery_saver", ["Point"], CHANGE,
                            quantity("%", "%.0f %unit%")),
    "plug": ("Switch", "Ladekabel", "power", ["Status"], CHANGE, state("%s", options="ON=Eingesteckt,OFF=Ausgesteckt")),
    "plug_locked": ("Switch", "Ladestecker verriegelt", "lock", ["Status"], CHANGE,
                    state("%s", options="ON=Verriegelt,OFF=Entriegelt")),
    "odometer": ("Number:Length", "Kilometerstand", "speed", ["Measurement"], CHANGE, quantity("km", "%.0f %unit%")),
    "locked": ("Switch", "Verriegelt", "lock", ["Status"], CHANGE, state("%s", options="ON=Verriegelt,OFF=Entriegelt")),
    "doors": ("Contact", "Türen", "sensor_door", ["Status", "Opening"], CHANGE, state("%s", options=OPEN_CLOSED)),
    "windows": ("Contact", "Fenster", "window", ["Status", "Opening"], CHANGE, state("%s", options=OPEN_CLOSED)),
    "trunk": ("Contact", "Kofferraum", "luggage", ["Status", "Opening"], CHANGE, state("%s", options=OPEN_CLOSED)),
    "bonnet": ("Contact", "Motorhaube", "directions_car", ["Status", "Opening"], CHANGE,
               state("%s", options=OPEN_CLOSED)),
    "lights": ("Switch", "Licht", "light", ["Status"], CHANGE, state("%s", options="ON=An,OFF=Aus")),
    "parking_state": ("String", "Parkstatus", "local_parking", ["Status"], CHANGE,
                      state("%s", options="PARKED=Geparkt,IN_MOTION=Fährt")),
    "parking_position": ("Location", "Parkposition", "place", ["Point"], CHANGE, {}),
    "parking_address": ("String", "Parkadresse", "signpost", ["Status"], RESTORE, state("%s")),
    "at_home": ("Switch", "zu Hause", "home", ["Status", "Presence"], CHANGE,
                state("%s", options="ON=Zu Hause,OFF=Unterwegs")),
    "climate_state": ("String", "Klimatisierung", "thermostat", ["Status"], CHANGE, state("%s", options=CLIMATE_STATES)),
    "climate": ("Switch", "Klimatisierung Ein/Aus", "air", ["Switch"], RESTORE,
                command("%s", options="ON=An,OFF=Aus")),
    "climate_target": ("Number:Temperature", "Klimatisierung Zieltemperatur", "device_thermostat",
                       ["Setpoint", "Temperature"], CHANGE,
                       {"unit": {"value": "°C"}, **command("%.1f %unit%", min=15.5, max=30, step=0.5)}),
    "updated": ("DateTime", "zuletzt gemeldet", "update", ["Timestamp", "Point"], RESTORE,
                state("%1$td.%1$tm. %1$tR")),
    "api_status": ("String", "API-Status", "cloud", ["Status"], RESTORE, state("%s", options=API_STATES)),
    "api_requests_left": ("Number", "API-Anfragen übrig", "data_usage", ["Point"], RESTORE, state("%.0f")),
    "api_key_expiry": ("DateTime", "API-Schlüssel gültig bis", "key", ["Timestamp", "Point"], RESTORE,
                       state("%1$td.%1$tm.%1$tY")),
}

ITEMS = {GROUP: {"name": GROUP, "type": "Group", "label": "Škoda Enyaq", "category": "material:electric_car",
                 "tags": ["Car"], "groupNames": ["e_car"]}}
METADATA = {GROUP: {}}
for suffix, (type_, label, icon, tags, groups, meta) in POINTS.items():
    ITEMS[P + suffix] = {"name": P + suffix, "type": type_, "label": f"Škoda Enyaq {label}",
                         "category": f"material:{icon}", "tags": tags, "groupNames": [GROUP, *groups]}
    METADATA[P + suffix] = meta

RULE = {
    "uid": UID,
    "name": "Škoda Enyaq Status",
    "description": RULE_DESCRIPTIONS[UID],
    "tags": [],
    # every 5 minutes, 20 s past, the script itself decides whether a read is due; once at startup; and on a command
    # to the charge limit, the charging switch, the air conditioning's switch or its target temperature
    "triggers": [{"id": "1", "type": "timer.GenericCronTrigger", "configuration": {"cronExpression": "20 0/5 * * * ? *"}},
                 {"id": "2", "type": "core.SystemStartlevelTrigger", "configuration": {"startlevel": 100}},
                 {"id": "4", "type": "core.ItemCommandTrigger", "configuration": {"itemName": P + "charge_target"}},
                 {"id": "5", "type": "core.ItemCommandTrigger", "configuration": {"itemName": P + "charging"}},
                 {"id": "6", "type": "core.ItemCommandTrigger", "configuration": {"itemName": P + "climate"}},
                 {"id": "7", "type": "core.ItemCommandTrigger", "configuration": {"itemName": P + "climate_target"}}],
    "conditions": [],
    "actions": [{"id": "3", "type": "script.ScriptAction",
                 "configuration": {"type": "application/javascript", "script": SCRIPT}}],
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
for group in ("e_car", "influxdb_change", "influxdb_periodic", "mapdb_change_restore"):
    assert call("GET", f"/items/{group}")[0] == 200, f"group {group} missing"
for name in ITEMS:
    status, item = call("GET", f"/items/{name}")
    print(f"item {name}:", f"exists, state {item['state']}" if status == 200 else "missing")
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
