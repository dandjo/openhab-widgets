#!/usr/bin/env python3
"""The weather bar's items and rule: the group weather with the present weather (weather_code, a WMO code with German
state options, and weather_is_day) and today's and the next two days' minimum and maximum (weather_day0_min …
weather_day2_max), restored after a restart; the rule weather_forecast fills them from Open-Meteo every 30 minutes
and at start-up (weather_forecast_rule.js beside this script).
Usage: weather_setup.py check|apply   (with openHAB stopped for apply)"""
import copy
import os
import sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
HERE = os.path.dirname(os.path.abspath(__file__))
ITEM = "org.openhab.core.items.ManagedItemProvider$PersistedItem"
WMO = [(0, "Klar"), (1, "Überwiegend klar"), (2, "Teilweise bewölkt"), (3, "Bedeckt"), (45, "Nebel"),
       (48, "Nebel mit Reif"), (51, "Leichter Nieselregen"), (53, "Nieselregen"), (55, "Starker Nieselregen"),
       (56, "Leichter gefrierender Nieselregen"), (57, "Gefrierender Nieselregen"), (61, "Leichter Regen"),
       (63, "Regen"), (65, "Starker Regen"), (66, "Leichter gefrierender Regen"), (67, "Gefrierender Regen"),
       (71, "Leichter Schneefall"), (73, "Schneefall"), (75, "Starker Schneefall"), (77, "Schneegriesel"),
       (80, "Leichte Regenschauer"), (81, "Regenschauer"), (82, "Heftige Regenschauer"), (85, "Leichte Schneeschauer"),
       (86, "Schneeschauer"), (95, "Gewitter"), (96, "Gewitter mit Hagel"), (99, "Gewitter mit starkem Hagel")]
DAYS = ["heute", "morgen", "übermorgen"]
members = ["weather", "mapdb_change_restore"]
ITEMS = {"weather": {"groupNames": [], "itemType": "Group", "tags": [], "label": "Wetter",
                     "category": "material:wb_sunny"},
         "weather_code": {"groupNames": members, "itemType": "Number", "tags": [], "label": "Wetter aktuell",
                          "category": "material:wb_sunny"},
         "weather_is_day": {"groupNames": members, "itemType": "Switch", "tags": [], "label": "Wetter Tag",
                            "category": "material:wb_sunny"}}
META = {"stateDescription:weather_code": ({"pattern": "%d", "options": ",".join(f"{c}={t}" for c, t in WMO)}, " "),
        "stateDescription:weather_is_day": ({"options": "ON=Tag,OFF=Nacht"}, " ")}
for i, day in enumerate(DAYS):
    for key, word in (("min", "Min."), ("max", "Max.")):
        name = f"weather_day{i}_{key}"
        ITEMS[name] = {"groupNames": members, "itemType": "Number:Temperature", "tags": [],
                       "label": f"Wetter {day} {word}", "category": "material:thermostat"}
        META[f"stateDescription:{name}"] = ({"pattern": "%.1f %unit%"}, " ")
        META[f"unit:{name}"] = ({}, "°C")
RULE = {"class": "org.openhab.core.automation.dto.RuleDTO", "value": {
    "triggers": [{"id": "1", "configuration": {"cronExpression": "0 0/30 * * * ? *"}, "type": "timer.GenericCronTrigger"},
                 {"id": "2", "configuration": {"startlevel": 100}, "type": "core.SystemStartlevelTrigger"}],
    "conditions": [], "actions": [{"inputs": {}, "id": "3", "configuration": {
        "script": open(os.path.join(HERE, "weather_forecast_rule.js")).read(), "type": "application/javascript"},
        "type": "script.ScriptAction"}],
    "configuration": {}, "configDescriptions": [], "templateState": "no-template", "uid": "weather_forecast",
    "name": "Wetter Prognose", "tags": [], "visibility": "VISIBLE",
    "description": "Holt alle 30 Minuten und beim Start das aktuelle Wetter und Min./Max. für heute und die zwei "
                   "Folgetage von Open-Meteo, für Wien, für die Wetterleiste der Übersicht."}}

files = {}
for name in ("org.openhab.core.items.Item.json", "org.openhab.core.items.Metadata.json", "automation_rules.json"):
    files[name] = m.detect(m.DB + name)
items, _ = files["org.openhab.core.items.Item.json"]
for n, v in ITEMS.items():
    assert n not in items, n
    items = m.insert(items, n, {"class": ITEM, "value": v})
meta, _ = files["org.openhab.core.items.Metadata.json"]
for key, (config, value) in META.items():
    assert key not in meta, key
    ns, item = key.split(":", 1)
    meta = m.insert(meta, key, {"class": "org.openhab.core.items.Metadata", "value": {
        "key": {"segments": [ns, item], "uid": key}, "value": value, "configuration": config}})
rules, _ = files["automation_rules.json"]
assert "weather_forecast" not in rules
rules = m.insert(rules, "weather_forecast", RULE)
new = {"org.openhab.core.items.Item.json": items, "org.openhab.core.items.Metadata.json": meta,
       "automation_rules.json": rules}
texts = {name: m.encode(new[name], *files[name][1]) for name in new}
print(f"{len(ITEMS)} items, {len(META)} metadata, rule weather_forecast")
if sys.argv[1] == "apply":
    for name, text in texts.items():
        open(m.DB + name, "w", encoding="utf-8").write(text)
    print("written")
