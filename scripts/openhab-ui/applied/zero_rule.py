#!/usr/bin/env python3
"""InfluxDB persistence: a second configuration for the group influxdb_change_at_most that stores every change to
exactly 0 at once, past the 5 s time filter of the first one; filters of one configuration are ANDed, configurations
are independent. The include filter compares the number alone, so 0 W, 0 VA, 0 var and 0 A all match.
Usage: zero_rule.py check|apply  (apply with openHAB stopped)"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "awattar_migrate.py")).read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)

NAME = "org.openhab.core.persistence.PersistenceServiceConfiguration.json"
GROUP = "influxdb_change_at_most*"
FILTER = {"name": "onlyZero", "lower": 0, "upper": 0, "unit": "", "inverted": False}
CONFIG = {"items": [GROUP], "strategies": ["everyChange"], "filters": [FILTER["name"]]}

data, enc = m.detect(m.DB + NAME)
cfg = data["influxdb"]["value"]
assert FILTER["name"] not in [f["name"] for k in ("thresholdFilters", "timeFilters", "equalsFilters", "includeFilters")
                              for f in cfg[k]], "filter exists already"
at = next(i for i, c in enumerate(cfg["configs"]) if c["items"] == [GROUP])  # right after the 5 s configuration
cfg["configs"].insert(at + 1, CONFIG)
cfg["includeFilters"].append(FILTER)
text = m.encode(data, *enc)
print(f"{NAME}: encoder html={enc[0]} newline={enc[1]} ok; configs {len(cfg['configs'])}, "
      f"includeFilters {[f['name'] for f in cfg['includeFilters']]}")
if sys.argv[1] == "apply":
    with open(m.DB + NAME, "w", encoding="utf-8") as f:
        f.write(text)
    print("written")
