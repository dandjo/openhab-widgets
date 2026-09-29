#!/usr/bin/env python3
"""The present weather as a symbol instead of a WMO code: the item weather_symbol (String, German state options, in the
weather group and restored after a restart) replaces weather_code, and the rule weather_forecast gets the script beside
this script (weather_forecast_rule.js), which works out five sky levels, veil clouds and showers with the sun out for
the present, every hour and every day.
Usage: weather_symbol_update.py check|apply   (with openHAB stopped for apply)"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "..", "awattar_migrate.py")).read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
sys.path.insert(0, os.path.join(HERE, "..", "i18n"))
from de_labels import RULE_DESCRIPTIONS  # noqa: E402
ITEM = "org.openhab.core.items.ManagedItemProvider$PersistedItem"
SYMBOLS = [("clear", "Wolkenlos"), ("fair", "Heiter"), ("partly", "Wolkig"), ("mostly", "Stark bewölkt"),
           ("overcast", "Bedeckt"), ("veil", "Schleierwolken"), ("fog", "Nebel"), ("rain", "Regen"), ("snow", "Schnee"),
           ("thunder", "Gewitter"), ("rain_sun", "Regenschauer"), ("snow_sun", "Schneeschauer"),
           ("thunder_sun", "Gewitterschauer")]
OLD, NEW = "weather_code", "weather_symbol"

names = ("org.openhab.core.items.Item.json", "org.openhab.core.items.Metadata.json", "automation_rules.json")
files = {name: m.detect(m.DB + name) for name in names}
items, meta, rules = (files[name][0] for name in names)

old = items.pop(OLD)["value"]
assert NEW not in items
items = m.insert(items, NEW, {"class": ITEM, "value": {"groupNames": old["groupNames"], "itemType": "String",
                                                        "tags": [], "label": old["label"], "category": old["category"]}})
meta.pop(f"stateDescription:{OLD}")
assert not [k for k in meta if k.split(":", 1)[1] == OLD], "more metadata on weather_code"
key = f"stateDescription:{NEW}"
meta = m.insert(meta, key, {"class": "org.openhab.core.items.Metadata", "value": {
    "key": {"segments": ["stateDescription", NEW], "uid": key}, "value": " ",
    "configuration": {"options": ",".join(f"{s}={t}" for s, t in SYMBOLS)}}})

rule = rules["weather_forecast"]["value"]
(action,) = rule["actions"]
action["configuration"]["script"] = open(os.path.join(HERE, "weather_forecast_rule.js")).read()
rule["description"] = RULE_DESCRIPTIONS["weather_forecast"]
assert f"items.{OLD}" not in action["configuration"]["script"]  # weather_code stays the API field's name

new = {names[0]: items, names[1]: meta, names[2]: rules}
texts = {name: m.encode(new[name], *files[name][1]) for name in names}
print(f"item {OLD} -> {NEW} ({len(SYMBOLS)} state options); weather_forecast script "
      f"{len(action['configuration']['script'])} chars")
if sys.argv[1] == "apply":
    for name, text in texts.items():
        open(m.DB + name, "w", encoding="utf-8").write(text)
    print("written")
