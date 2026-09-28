#!/usr/bin/env python3
"""e_car_power's comments: the air conditioning is metered by a Shelly EM whose relay is wired to nothing.
Usage: e_car_comment.py check|apply   (with openHAB stopped for apply)"""
import sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
PAIRS = [("// The E-Car charges behind the air conditioning's plug. Faikin reports the power of the outdoor unit only;",
          "// The E-Car charges on the air conditioning's circuit. Faikin reports the power of the outdoor unit only;"),
         ("// the car has no switch of its own; this mirrors the plug, which also cuts the air conditioner",
          "// the car has no switch of its own; this mirrors the relay of the air conditioning's Shelly EM, which is\n"
          "// wired to nothing")]
data, enc = m.detect(m.DB + "automation_rules.json")
cfg = data["e_car_power"]["value"]["actions"][0]["configuration"]
for old, new in PAIRS:
    assert cfg["script"].count(old) == 1, old
    cfg["script"] = cfg["script"].replace(old, new)
text = m.encode(data, *enc)
print("e_car_power comments ok")
if sys.argv[1] == "apply":
    open(m.DB + "automation_rules.json", "w", encoding="utf-8").write(text)
    print("written")
