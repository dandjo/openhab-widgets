#!/usr/bin/env python3
"""air_conditioning_circuit_power: the E-Car's charge as a state instead of the 300 W threshold, Faikin always
subtracted, the car capped by its charging current at the plug's voltage. Replaces the rule's script with
e_car_state_rule.js next to this file and its description; refuses if the rule no longer holds the threshold version.
Usage: e_car_state_rule.py check|apply   (as root, with openHAB stopped for apply)"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
src = open("/home/pi/scripts/openhab-ui/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)

UID = "air_conditioning_circuit_power"
OLD_SHA = "e74feddcf92954c61cbcf1bd5348dd96d298b607eba5011882f97146dc4a2128"  # the threshold version as deployed on 2026-09-27
SCRIPT = open(os.path.join(HERE, "e_car_state_rule.js"), encoding="utf-8").read()
DESCRIPTION = ("Teilt die Messung des Shelly EM der Klimaanlage in E-Auto (e_car_*) und Klimaanlage selbst "
               "(air_conditioning_unit_power) auf und spiegelt den Schalter des Shelly-Relais. Ob das Auto lädt, ist "
               "ein Zustand: Start bei einem Anstieg um mindestens 1,2 kW, den Faikin nicht erklärt, Ende bei einem "
               "solchen Abfall oder einem Rest, der für das Auto zu klein ist. Beim Laden bekommt das Auto den Rest "
               "nach Faikin und Innengerät, höchstens seinen Ladestrom mal Spannung; Faikins Messung bleibt immer bei "
               "der Klimaanlage.")


def migrate_rules(d):
    r = d[UID]["value"]
    action = r["actions"][0]
    old = action["configuration"]["script"]
    assert hashlib.sha256(old.encode()).hexdigest() == OLD_SHA, "the rule changed since this migration was written"
    action["configuration"]["script"] = SCRIPT
    r["description"] = DESCRIPTION
    return d


name = "automation_rules.json"
data, enc = m.detect(m.DB + name)
text = m.encode(migrate_rules(data), *enc)
print(f"{name}: encoder html={enc[0]} newline={enc[1]} ok; script {len(SCRIPT)} chars")
if sys.argv[1] == "apply":
    with open(m.DB + name, "w", encoding="utf-8") as f:
        f.write(text)
    print("written")
