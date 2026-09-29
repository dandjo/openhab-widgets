#!/usr/bin/env python3
"""Give the rule weather_forecast the script beside this script (weather_forecast_rule.js), which draws the weather
from its own WMO codes: a day's sky from its sunshine, fog, precipitation and thunder only where they mark the day, the
present's and each hour's sky from the cloud layers, and each hour's code with day or night in weather_hourly, for the
forecast chart's weather drawings.
Usage: weather_symbols_update.py check|apply   (with openHAB stopped for apply)"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "..", "awattar_migrate.py")).read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
sys.path.insert(0, os.path.join(HERE, "..", "i18n"))
from de_labels import RULE_DESCRIPTIONS  # noqa: E402
NAME = "automation_rules.json"
data, enc = m.detect(m.DB + NAME)
rule = data["weather_forecast"]["value"]
(action,) = rule["actions"]
action["configuration"]["script"] = open(os.path.join(HERE, "weather_forecast_rule.js")).read()
rule["description"] = RULE_DESCRIPTIONS["weather_forecast"]
text = m.encode(data, *enc)
print(f"{NAME}: encoder html={enc[0]} newline={enc[1]} ok; weather_forecast script {len(action['configuration']['script'])} chars")
if sys.argv[1] == "apply":
    open(m.DB + NAME, "w", encoding="utf-8").write(text)
    print("written")
