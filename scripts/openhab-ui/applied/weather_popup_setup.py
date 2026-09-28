#!/usr/bin/env python3
"""The forecast popup's items and rules: in the group weather, restored after a restart and in no InfluxDB group, the
hourly and daily forecast as JSON (weather_hourly, weather_daily), written by the rule weather_forecast with its new
script (weather_forecast_rule.js beside this script), and GeoSphere Austria's warnings: the highest level in effect
now or within 24 hours (weather_warning_level, 0 to 3 with German state options), that warning as a short text
(weather_warning_text) and every warning not yet ended as JSON (weather_warning_list), written by the new rule
weather_warnings every 15 minutes and at start-up (weather_warnings_rule.js).
Usage: weather_popup_setup.py check|apply   (with openHAB stopped for apply)"""
import os
import sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
HERE = os.path.dirname(os.path.abspath(__file__))
ITEM = "org.openhab.core.items.ManagedItemProvider$PersistedItem"
members = ["weather", "mapdb_change_restore"]


def item(type_, label, icon):
    return {"groupNames": members, "itemType": type_, "tags": [], "label": label, "category": f"material:{icon}"}


ITEMS = {"weather_hourly": item("String", "Wetter Stundenprognose", "schedule"),
         "weather_daily": item("String", "Wetter Tagesprognose", "calendar_month"),
         "weather_warning_level": item("Number", "Wetterwarnung Stufe", "warning"),
         "weather_warning_text": item("String", "Wetterwarnung", "warning"),
         "weather_warning_list": item("String", "Wetterwarnungen", "warning")}
META = {"stateDescription:weather_warning_level": ({"pattern": "%d", "options": "0=Keine,1=Gelb,2=Orange,3=Rot"}, " ")}
FORECAST_DESCRIPTION = (
    "Holt alle 30 Minuten und beim Start das aktuelle Wetter, Min./Max. für heute und die zwei Folgetage sowie die "
    "Vorhersage der nächsten 61 Stunden und 5 Tage als JSON von Open-Meteo, Modell GeoSphere AROME Austria (Stunden "
    "und Tage außerhalb seiner Reichweite und die Regenwahrscheinlichkeit aus dem Best Match), für Wien, für die "
    "Wetterleiste der Übersicht und ihr Popup.")
WARNINGS = {"class": "org.openhab.core.automation.dto.RuleDTO", "value": {
    "triggers": [{"id": "1", "configuration": {"cronExpression": "0 0/15 * * * ? *"}, "type": "timer.GenericCronTrigger"},
                 {"id": "2", "configuration": {"startlevel": 100}, "type": "core.SystemStartlevelTrigger"}],
    "conditions": [], "actions": [{"inputs": {}, "id": "3", "configuration": {
        "script": open(os.path.join(HERE, "weather_warnings_rule.js")).read(), "type": "application/javascript"},
        "type": "script.ScriptAction"}],
    "configuration": {}, "configDescriptions": [], "templateState": "no-template", "uid": "weather_warnings",
    "name": "Wetter Warnungen", "tags": [], "visibility": "VISIBLE",
    "description": "Holt alle 15 Minuten und beim Start die amtlichen Wetterwarnungen der GeoSphere Austria für Wien: "
                   "die höchste Stufe der Warnungen, die jetzt oder in den nächsten 24 Stunden gelten, diese als "
                   "Kurztext und alle noch nicht abgelaufenen Warnungen als JSON, für die Wetterleiste der Übersicht "
                   "und ihr Popup."}}

files = {name: m.detect(m.DB + name) for name in ("org.openhab.core.items.Item.json",
                                                   "org.openhab.core.items.Metadata.json", "automation_rules.json")}
items, _ = files["org.openhab.core.items.Item.json"]
for n, v in ITEMS.items():
    assert n not in items, n
    items = m.insert(items, n, {"class": ITEM, "value": v})
meta, _ = files["org.openhab.core.items.Metadata.json"]
for key, (config, value) in META.items():
    assert key not in meta, key
    ns, name = key.split(":", 1)
    meta = m.insert(meta, key, {"class": "org.openhab.core.items.Metadata", "value": {
        "key": {"segments": [ns, name], "uid": key}, "value": value, "configuration": config}})
rules, _ = files["automation_rules.json"]
assert "weather_warnings" not in rules
forecast = rules["weather_forecast"]["value"]
(action,) = forecast["actions"]
action["configuration"]["script"] = open(os.path.join(HERE, "weather_forecast_rule.js")).read()
forecast["description"] = FORECAST_DESCRIPTION
rules = m.insert(rules, "weather_warnings", WARNINGS)
new = {"org.openhab.core.items.Item.json": items, "org.openhab.core.items.Metadata.json": meta,
       "automation_rules.json": rules}
texts = {name: m.encode(new[name], *files[name][1]) for name in new}
print(f"{len(ITEMS)} items, {len(META)} metadata, rule weather_forecast updated "
      f"({len(action['configuration']['script'])} chars), rule weather_warnings added")
if sys.argv[1] == "apply":
    for name, text in texts.items():
        open(m.DB + name, "w", encoding="utf-8").write(text)
    print("written")
