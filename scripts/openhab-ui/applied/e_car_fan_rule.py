#!/usr/bin/env python3
"""air_conditioning_circuit_power: the indoor unit's share from its measured fan curve (fan speed, streamer) and
standby instead of two learned base loads, other loads on the circuit learned in standby. Replaces the rule's
script with e_car_fan_rule.js next to this file and its description; refuses if the rule no longer holds the
state machine version.
Usage: e_car_fan_rule.py check|apply   (as root, with openHAB stopped for apply)"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
src = open("/home/pi/scripts/openhab-ui/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)

UID = "air_conditioning_circuit_power"
OLD_SHA = "9cb741fb4ea47ea848544cabf91998b5c06655e22cdf72c7bf51079f65f5de12"  # the state machine version as deployed on 2026-09-27
SCRIPT = open(os.path.join(HERE, "e_car_fan_rule.js"), encoding="utf-8").read()
DESCRIPTION = ("Teilt die Messung des Shelly EM der Klimaanlage in E-Auto (e_car_*) und Klimaanlage selbst "
               "(air_conditioning_unit_power) auf und spiegelt den Schalter des Shelly-Relais. Ob das Auto lädt, ist "
               "ein Zustand: Start bei einem Anstieg um mindestens 1,2 kW, den Faikin nicht erklärt, Ende bei einem "
               "solchen Abfall oder einem Rest, der für das Auto zu klein ist. Beim Laden bekommt das Auto den Rest "
               "nach Faikin, Innengerät und anderen Verbrauchern, höchstens seinen Ladestrom mal Spannung; Faikins "
               "Messung bleibt immer bei der Klimaanlage. Das Innengerät folgt seiner am 27.09.2026 gemessenen "
               "Kennlinie über die Lüfterdrehzahl, mit und ohne Streamer, und seinem Standby; andere Verbraucher am "
               "Stromkreis werden im Standby gelernt.")


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
