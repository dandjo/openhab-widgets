#!/usr/bin/env python3
"""Give the rule weather_forecast the script beside this script (weather_forecast_rule.js) and move it off Open-Meteo's
busy full and half hours to :07:17 and :37:17: every answer checked and asked again up to twice, hours and days merged
with the last run's by their time, so a failed request never shortens the forecast.
Usage: weather_forecast_update.py check|apply   (with openHAB stopped for apply)"""
import os
import sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "automation_rules.json"
data, enc = m.detect(m.DB + NAME)
rule = data["weather_forecast"]["value"]
(action,) = rule["actions"]
action["configuration"]["script"] = open(os.path.join(HERE, "weather_forecast_rule.js")).read()
(cron,) = [t for t in rule["triggers"] if t["type"] == "timer.GenericCronTrigger"]
print("cron", cron["configuration"]["cronExpression"], "-> 17 7/30 * * * ? *")
cron["configuration"]["cronExpression"] = "17 7/30 * * * ? *"
rule["description"] = ("Holt um :07 und :37 jeder Stunde und beim Start das aktuelle Wetter, die nächsten 61 Stunden und "
                       "fünf Tage von Open-Meteo, Modell GeoSphere AROME Austria (was es nicht abdeckt, aus dem Best "
                       "Match), für Wien; wiederholt fehlgeschlagene Anfragen und behält Stunden und Tage, die ein Lauf "
                       "nicht bringt, aus dem letzten Lauf.")
text = m.encode(data, *enc)
print(f"{NAME}: encoder html={enc[0]} newline={enc[1]} ok; weather_forecast script {len(action['configuration']['script'])} chars")
if sys.argv[1] == "apply":
    open(m.DB + NAME, "w", encoding="utf-8").write(text)
    print("written")
