#!/usr/bin/env python3
"""Daily PV self-use total for the overview's Energy per Day chart: item, metadata, and a fifth pair in energy_daily_totals.
Usage: self_use.py check|apply   (run as root with openHAB stopped for apply)
"""
import sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)

ITEM, LABEL, SOURCE = "energy_daily_self_use", "Energy Daily Self Use", "photovoltaics_own_ec_day"


def migrate_items(d):
    assert ITEM not in d
    return m.insert(d, ITEM, {"class": "org.openhab.core.items.ManagedItemProvider$PersistedItem",
                              "value": {"groupNames": [], "itemType": "Number:Energy", "tags": [],
                                        "label": LABEL, "category": "energy"}})


def migrate_metadata(d):
    for ns, value, cfg in (("unit", "kWh", {}), ("stateDescription", " ", {"pattern": "%.2f %unit%"})):
        key = f"{ns}:{ITEM}"
        assert key not in d, key
        d = m.insert(d, key, {"class": "org.openhab.core.items.Metadata",
                              "value": {"key": {"segments": [ns, ITEM], "uid": key}, "value": value,
                                        "configuration": dict(cfg)}})
    return d


def migrate_rules(d):
    rule = d["energy_daily_totals"]["value"]
    action = rule["actions"][0]["configuration"]
    old = "  ['huawei_inverter_power_meter_ep_day', 'energy_daily_grid_export'],\n];"
    assert action["script"].count(old) == 1
    action["script"] = action["script"].replace(
        old, f"  ['huawei_inverter_power_meter_ep_day', 'energy_daily_grid_export'],\n  ['{SOURCE}', '{ITEM}'],\n];")
    rule["description"] = ("Keeps one point per day for PV yield, home consumption, grid import, grid export and PV "
                           "self-use, for charts over weeks, months and years.")
    t = d["temperature_15min"]["value"]
    t["description"] = t["description"].replace("for the dashboard chart", "for the overview page's chart")
    return d


FILES = {"org.openhab.core.items.Item.json": migrate_items,
         "org.openhab.core.items.Metadata.json": migrate_metadata,
         "automation_rules.json": migrate_rules}
results = {}
for name, fn in FILES.items():
    data, enc = m.detect(m.DB + name)
    results[name] = m.encode(fn(data), *enc)
    print(name, "encoder", enc, "ok")
if sys.argv[1] == "apply":
    for name, text in results.items():
        open(m.DB + name, "w", encoding="utf-8").write(text)
    print("written")
