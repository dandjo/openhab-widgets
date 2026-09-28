#!/usr/bin/env python3
"""Replaces the include filter onlyZero (it cannot compare quantities without a unit, logs a warning and lets every
value through) by an equals filter on the zero states as items report them. Usage: zero_rule_equals.py check|apply"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "awattar_migrate.py")).read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)

NAME = "org.openhab.core.persistence.PersistenceServiceConfiguration.json"
FILTER = {"name": "onlyZero", "values": ["0", "0 W", "0 VA", "0 var", "0 A", "0 V"], "inverted": False}

data, enc = m.detect(m.DB + NAME)
cfg = data["influxdb"]["value"]
assert [f["name"] for f in cfg["includeFilters"]] == ["onlyZero"], cfg["includeFilters"]
cfg["includeFilters"] = []
cfg["equalsFilters"].append(FILTER)
text = m.encode(data, *enc)
print(f"{NAME}: encoder html={enc[0]} newline={enc[1]} ok; equalsFilters {cfg['equalsFilters']}")
if sys.argv[1] == "apply":
    with open(m.DB + NAME, "w", encoding="utf-8") as f:
        f.write(text)
    print("written")
