#!/usr/bin/env python3
"""heatpump_metering: bridge a restart of openHAB (30 September 2026). The rule keeps its accumulators in
cache.private, which a restart empties, so the first run after it continued from the persisted energies without
integrating the 3-4 minutes the restart took; on a day of config applies that lost 0.34 kWh while the heat pump ran.
Now that run rebuilds the last run from InfluxDB (the energies as last written, the parts' powers as they were then,
the totals as the sum of their parts) and bridges up to 15 minutes. Replaces the rule's script with
hp_restart_bridge.js next to this file and its description; refuses if the rule changed since.
Usage: hp_restart_bridge.py check|apply   (as root, with openHAB stopped for apply)"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
src = open("/home/pi/scripts/openhab-ui/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)

UID = "heatpump_metering"
OLD_SHA = "d362a270cd7553744adb640c298c760f00cb348cfda360efeb77c3b79bb2b263"  # as deployed on 2026-09-30
SCRIPT = open(os.path.join(HERE, "hp_restart_bridge.js"), encoding="utf-8").read()
DESCRIPTION = ("Teilt die elektrische Leistung der Wärmepumpe in Heizung, Warmwasser und Standby, leitet die "
               "Heizleistung aus Durchfluss und Spreizung ab, berechnet momentane COPs und integriert alles mit einem "
               "gemeinsamen Zeitschritt zu den Energien von heute. Bei ausgeschalteter Heizung zählt nichts als "
               "Heizung, ein reiner Pumpenlauf als Standby; meldet das Ventil Warmwasser, bleibt ein Verdichterlauf "
               "bei stehender Pumpe Warmwasser. Einen Neustart von openHAB bis 15 Minuten überbrückt sie aus den in "
               "InfluxDB gespeicherten Werten.")


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
