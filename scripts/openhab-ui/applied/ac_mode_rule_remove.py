#!/usr/bin/env python3
"""Remove air_conditioning_mode_power: the UI switches the air conditioner itself again, and a mode may be chosen
while it is off. Usage: ac_mode_rule_remove.py check|apply   (with openHAB stopped for apply)"""
import sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
data, enc = m.detect(m.DB + "automation_rules.json")
assert "air_conditioning_mode_power" in data
data.pop("air_conditioning_mode_power")
text = m.encode(data, *enc)
print(len(data), "rules left")
if sys.argv[1] == "apply":
    open(m.DB + "automation_rules.json", "w", encoding="utf-8").write(text)
    print("written")
