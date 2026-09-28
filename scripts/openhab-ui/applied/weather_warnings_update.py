#!/usr/bin/env python3
"""Give the rule weather_warnings the script beside this script (weather_warnings_rule.js): from orange on, a rising
warning level goes out as a broadcast notification. Usage: weather_warnings_update.py check|apply
(with openHAB stopped for apply)"""
import os
import sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "automation_rules.json"
data, enc = m.detect(m.DB + NAME)
rule = data["weather_warnings"]["value"]
(action,) = rule["actions"]
action["configuration"]["script"] = open(os.path.join(HERE, "weather_warnings_rule.js")).read()
rule["description"] = ("Holt alle 15 Minuten und beim Start die Unwetterwarnungen der GeoSphere Austria für Wien: höchste "
                       "Stufe, Kurztext und Liste; steigt die Stufe auf Orange oder Rot, geht eine Broadcast-"
                       "Benachrichtigung hinaus.")
text = m.encode(data, *enc)
print(f"{NAME}: encoder html={enc[0]} newline={enc[1]} ok; weather_warnings script {len(action['configuration']['script'])} chars")
if sys.argv[1] == "apply":
    open(m.DB + NAME, "w", encoding="utf-8").write(text)
    print("written")
