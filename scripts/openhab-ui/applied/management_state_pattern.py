#!/usr/bin/env python3
"""Give the group heatpump_management the state description of its member heatpump_dhw_management (pattern %s), so
Basic UI shows its state beside the sitemap's Automatik switch as it does for every other switch.
Usage: management_state_pattern.py check|apply   (with openHAB stopped for apply)"""
import copy
import sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
NAME = "org.openhab.core.items.Metadata.json"
data, enc = m.detect(m.DB + NAME)
KEY, MEMBER = "stateDescription:heatpump_management", "stateDescription:heatpump_dhw_management"
assert KEY not in data and MEMBER in data
entry = copy.deepcopy(data[MEMBER])
entry["value"]["key"] = {"segments": ["stateDescription", "heatpump_management"], "uid": KEY}
data = m.insert(data, KEY, entry)
text = m.encode(data, *enc)
print(f"{NAME}: encoder html={enc[0]} newline={enc[1]} ok; {KEY} = {entry['value']['configuration']}")
if sys.argv[1] == "apply":
    open(m.DB + NAME, "w", encoding="utf-8").write(text)
    print("written")
