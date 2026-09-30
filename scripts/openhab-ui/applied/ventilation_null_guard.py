#!/usr/bin/env python3
"""Keep the ventilation's level while a reading its automatics need is missing: after a restart the Netatmo CO2 and
humidity are NULL until the cloud answers, and a missing value compares as 0 in JavaScript, so CO2 "below 500" and
humidity "up to 35 %" held and the rule ventilation_management switched to level 1. The rule now leaves the level as
it is while an enabled automatic lacks its reading, and the CO2 alert waits for a reading too; the two Netatmo items
join mapdb_change_restore, so a restart restores their last value.
Usage: ventilation_null_guard.py check|apply   (with openHAB stopped for apply)"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "..", "awattar_migrate.py")).read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
RESTORE = ["netatmo_weatherstation_co2", "netatmo_weatherstation_atmospheric_humidity"]
REPLACE = [
    ("""// calculate level and debounce

if (items.getItem('ventilation_management').state === 'ON' && items.getItem('ventilation_timer').numericState <= 0) {""",
     """// calculate level and debounce; while an enabled automatic lacks its reading (NULL after a restart, UNDEF while the
// Netatmo cloud fails) the level stays, as a missing value would compare as 0

const lacks = (management, item) => items.getItem(management).state === 'ON'
  && items.getItem(item).numericState === null;
const missing = lacks('ventilation_co2_management', 'netatmo_weatherstation_co2')
  || lacks('ventilation_humidity_management', 'netatmo_weatherstation_atmospheric_humidity')
  || lacks('ventilation_temperature_management', 'espaltherma_ext_ambient_temp');

if (items.getItem('ventilation_management').state === 'ON' && items.getItem('ventilation_timer').numericState <= 0
  && !missing) {"""),
    ("""// alert CO2 level and debounce

if (!co2_alert_item.persistence.changedSince(time.ZonedDateTime.now().minusMinutes(30))) {""",
     """// alert CO2 level and debounce, only with a reading

if (co2_item.numericState !== null && !co2_alert_item.persistence.changedSince(time.ZonedDateTime.now().minusMinutes(30))) {"""),
]

ITEMS, RULES = "org.openhab.core.items.Item.json", "automation_rules.json"
files = {name: m.detect(m.DB + name) for name in (ITEMS, RULES)}
items, rules = files[ITEMS][0], files[RULES][0]
for n in RESTORE:
    groups = items[n]["value"]["groupNames"]
    assert "mapdb_change_restore" not in groups, n
    groups.append("mapdb_change_restore")
    print(f"{n}: {groups}")
(action,) = rules["ventilation_management"]["value"]["actions"]
script = action["configuration"]["script"]
for old, new in REPLACE:
    assert script.count(old) == 1, old[:60]
    script = script.replace(old, new)
action["configuration"]["script"] = script
print(f"ventilation_management: {len(REPLACE)} replacements, script {len(script)} chars")
texts = {ITEMS: m.encode(items, *files[ITEMS][1]), RULES: m.encode(rules, *files[RULES][1])}
if sys.argv[1] == "apply":
    for name, text in texts.items():
        open(m.DB + name, "w", encoding="utf-8").write(text)
    print("written")
