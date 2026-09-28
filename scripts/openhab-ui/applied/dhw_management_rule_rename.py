#!/usr/bin/env python3
"""Rename the rule heatpump_management to heatpump_dhw_management, after the item it reacts to: the UI switches the
group heatpump_management, which passes the command on to its members, heatpump_dhw_management among them. The
rule keeps its triggers and script; its name becomes the item's label.
Usage: dhw_management_rule_rename.py check|apply   (with openHAB stopped for apply)"""
import sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
OLD, NEW, NAME = "heatpump_management", "heatpump_dhw_management", "Wärmepumpe Warmwasser-Automatik"
data, enc = m.detect(m.DB + "automation_rules.json")
assert OLD in data and NEW not in data
disabled = open(m.DB + "automation_rules_disabled.json").read()
assert OLD not in disabled, "the rule is disabled; rename it there too"
rule = data.pop(OLD)
assert rule["value"]["uid"] == OLD
rule["value"]["uid"] = NEW
print(f"{OLD} -> {NEW}; name {rule['value'].get('name')!r} -> {NAME!r}")
rule["value"]["name"] = NAME
data = m.insert(data, NEW, rule)
text = m.encode(data, *enc)
print(len(data), "rules")
if sys.argv[1] == "apply":
    open(m.DB + "automation_rules.json", "w", encoding="utf-8").write(text)
    print("written")
