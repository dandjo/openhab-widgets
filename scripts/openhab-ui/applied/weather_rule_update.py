#!/usr/bin/env python3
"""Give the rule weather_forecast the script beside this script (weather_forecast_rule.js): GeoSphere's AROME Austria
first, Open-Meteo's best match for the days AROME does not reach. Usage: weather_rule_update.py check|apply
(with openHAB stopped for apply)"""
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
rule["description"] = ("Holt alle 30 Minuten und beim Start das aktuelle Wetter und Min./Max. für heute und die zwei "
                       "Folgetage von Open-Meteo, Modell GeoSphere AROME Austria (Tage außerhalb seiner Reichweite "
                       "aus dem Best Match), für Wien, für die Wetterleiste der Übersicht.")
text = m.encode(data, *enc)
print(f"{NAME}: encoder html={enc[0]} newline={enc[1]} ok; weather_forecast script {len(action['configuration']['script'])} chars")
if sys.argv[1] == "apply":
    open(m.DB + NAME, "w", encoding="utf-8").write(text)
    print("written")
