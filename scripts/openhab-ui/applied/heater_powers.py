#!/usr/bin/env python3
"""The heaters' own electrical powers, so the heat pump drawing shows each device's draw at the device: the rule
heatpump_metering writes espaltherma_electrical_power_buh (the backup heater in the wall unit, 2 kW step 1, 4 kW
step 2) and espaltherma_electrical_power_bsh (the booster heater in the tank, 2 kW), the nominal powers it already
adds to espaltherma_electrical_power; the measured heatpump_power is the outdoor unit's circuit.
Usage: heater_powers.py check|apply   (with openHAB stopped for apply)"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "..", "awattar_migrate.py")).read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
ITEM = "org.openhab.core.items.ManagedItemProvider$PersistedItem"
NEW = {"espaltherma_electrical_power_buh": "ESPAltherma Elektrische Leistung Heizstab",
       "espaltherma_electrical_power_bsh": "ESPAltherma Elektrische Leistung Zusatzheizung"}
OLD = """persistPower('espaltherma_electrical_power', electrical_power);
"""
ADD = """persistPower('espaltherma_electrical_power', electrical_power);
// the heaters' own nominal powers, for the drawing's devices: the backup heater in the wall unit, the booster heater
// in the tank; the measured heatpump_power is the outdoor unit's circuit
persistPower('espaltherma_electrical_power_buh',
  (items.getItem('espaltherma_buh_step1_mode').state === 'ON' ? buh1_power : 0)
  + (items.getItem('espaltherma_buh_step2_mode').state === 'ON' ? buh2_power : 0));
persistPower('espaltherma_electrical_power_bsh', isBsh ? bsh_power : 0);
"""

names = ("org.openhab.core.items.Item.json", "org.openhab.core.items.Metadata.json", "automation_rules.json")
files = {name: m.detect(m.DB + name) for name in names}
items, meta, rules = (files[name][0] for name in names)
sibling = items["espaltherma_electrical_power_standby"]["value"]
for n, label in NEW.items():
    assert n not in items, n
    items = m.insert(items, n, {"class": ITEM, "value": {**sibling, "label": label, "groupNames": list(sibling["groupNames"]),
                                                         "tags": list(sibling["tags"])}})
    for ns, value, config in (("stateDescription", " ", {"pattern": "%.2f %unit%"}), ("unit", "W", {})):
        key = f"{ns}:{n}"
        assert key not in meta, key
        meta = m.insert(meta, key, {"class": "org.openhab.core.items.Metadata", "value": {
            "key": {"segments": [ns, n], "uid": key}, "value": value, "configuration": config}})
    print(f"{n}: {label}")
(action,) = rules["heatpump_metering"]["value"]["actions"]
script = action["configuration"]["script"]
assert script.count(OLD) == 1
action["configuration"]["script"] = script.replace(OLD, ADD)
print(f"heatpump_metering: script {len(action['configuration']['script'])} chars")
new = {names[0]: items, names[1]: meta, names[2]: rules}
texts = {name: m.encode(new[name], *files[name][1]) for name in names}
if sys.argv[1] == "apply":
    for name, text in texts.items():
        open(m.DB + name, "w", encoding="utf-8").write(text)
    print("written")
