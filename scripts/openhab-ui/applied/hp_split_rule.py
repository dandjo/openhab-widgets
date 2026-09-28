#!/usr/bin/env python3
"""heatpump_metering: variants A and B of 27 September 2026. A: with the valve on DHW a compressor running with the
pump off stays hot water (a hot-water cycle can start with a short pump run on Space). B: with space heating
switched off nothing is space heating; a pump run alone is standby. Replaces the rule's script with
hp_split_rule.js next to this file and its description; refuses if the rule changed since.
Usage: hp_split_rule.py check|apply   (as root, with openHAB stopped for apply)"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
src = open("/home/pi/scripts/openhab-ui/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)

UID = "heatpump_metering"
OLD_SHA = "40798587d859b5c60abfcdf55f503535268c0859d9a49e0ec9541804afcc6a38"  # as deployed on 2026-09-27
SCRIPT = open(os.path.join(HERE, "hp_split_rule.js"), encoding="utf-8").read()
DESCRIPTION = ("Teilt die elektrische Leistung der Wärmepumpe in Heizung, Warmwasser und Standby, leitet die "
               "Heizleistung aus Durchfluss und Spreizung ab, berechnet momentane COPs und integriert alles mit einem "
               "gemeinsamen Zeitschritt zu den Energien von heute. Bei ausgeschalteter Heizung zählt nichts als "
               "Heizung, ein reiner Pumpenlauf als Standby; meldet das Ventil Warmwasser, bleibt ein Verdichterlauf "
               "bei stehender Pumpe Warmwasser.")


def migrate_rules(d):
    r = d[UID]["value"]
    action = r["actions"][0]
    assert hashlib.sha256(action["configuration"]["script"].encode()).hexdigest() == OLD_SHA, \
        "the rule changed since this migration was written"
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
