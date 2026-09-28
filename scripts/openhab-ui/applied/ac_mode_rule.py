#!/usr/bin/env python3
"""Rule: commanding any air conditioner mode switches it on, so Off can be one of the modes in the UI.
Usage: ac_mode_rule.py check|apply   (run as root with openHAB stopped for apply)
"""
import sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
UID = "air_conditioning_mode_power"
SCRIPT = """// On the overview, Off is one of the air conditioner's modes: it switches the unit off, and choosing any
// real mode switches it on again
if (items.getItem('faikout_perfera_switch').state !== 'ON') {
  items.getItem('faikout_perfera_switch').sendCommand('ON');
}"""


def migrate_rules(d):
    assert UID not in d
    return m.insert(d, UID, {"class": "org.openhab.core.automation.dto.RuleDTO", "value": {
        "triggers": [{"id": "1", "configuration": {"itemName": "faikout_perfera_mode"},
                      "type": "core.ItemCommandTrigger"}],
        "conditions": [],
        "actions": [{"inputs": {}, "id": "2", "configuration": {"script": SCRIPT, "type": "application/javascript"},
                     "type": "script.ScriptAction"}],
        "configuration": {}, "configDescriptions": [], "templateState": "no-template", "uid": UID,
        "name": "Air Conditioning Mode Power", "tags": [], "visibility": "VISIBLE",
        "description": "Switches the air conditioner on when a mode is commanded, so the UI can offer Off as a mode."}})


data, enc = m.detect(m.DB + "automation_rules.json")
text = m.encode(migrate_rules(data), *enc)
print("automation_rules.json encoder", enc, "rules", len(data) + 1)
if sys.argv[1] == "apply":
    open(m.DB + "automation_rules.json", "w", encoding="utf-8").write(text)
    print("written")
