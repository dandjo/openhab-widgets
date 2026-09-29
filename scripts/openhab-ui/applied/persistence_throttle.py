#!/usr/bin/env python3
"""Persist the fastest series less often, where no chart needs their pace: the SmartPi energy counters (1 to 5 s) and
the plugs' and Shellys' energy counters (today and total) at most once a minute through the new group
influxdb_change_at_most_minute, six plug gauges (power, power factor,
reactive and apparent power at 1 to 3 s) at most every 5 seconds through influxdb_change_at_most; and persist
huawei_inverter_optimizers_online, which Grafana's Photovoltaik dashboard charts but nothing stored. As for the 5 s
group, a second configuration stores a change to exactly 0 at once, and onlyZero now also knows 0 kWh, so a today
counter's reset at midnight is not held back.
Usage: persistence_throttle.py check|apply   (with openHAB stopped for apply)"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "..", "awattar_migrate.py")).read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
ITEM = "org.openhab.core.items.ManagedItemProvider$PersistedItem"
MINUTE_GROUP = "influxdb_change_at_most_minute"
MINUTE_FILTER = "atMostEveryMinute"
COUNTERS = ["smartpi_ebal", "smartpi_ec1", "smartpi_ec2", "smartpi_ec3", "smartpi_ep1", "smartpi_ep2", "smartpi_ep3"]
# the plugs' and Shellys' counters, today's and the total, of every device that has both
PLUGS = ["air_conditioning", "air_conditioning_unit", "bicycle_batteries", "coffee_machine", "dishwasher",
         "living_room_entertainment", "network", "office_1", "office_2", "refrigerator", "terrace_light", "tumble_dryer",
         "ventilation", "washing_machine_1", "washing_machine_2"]
COUNTERS += [f"{p}_energy_{k}" for p in PLUGS for k in ("today", "total")]
GAUGES = ["network_power_factor", "ventilation_power_factor", "living_room_entertainment_power",
          "living_room_entertainment_reactive_power", "living_room_entertainment_apparent_power",
          "living_room_entertainment_power_factor"]
PERSIST = ["huawei_inverter_optimizers_online"]

ITEMS, PERS = "org.openhab.core.items.Item.json", "org.openhab.core.persistence.PersistenceServiceConfiguration.json"
files = {name: m.detect(m.DB + name) for name in (ITEMS, PERS)}
items, pers = files[ITEMS][0], files[PERS][0]


def regroup(name, drop, add):
    groups = items[name]["value"]["groupNames"]
    assert drop is None or drop in groups, (name, groups)
    new = [g for g in groups if g != drop]
    for g in add:
        if g not in new:
            new.insert(0, g)
    items[name]["value"]["groupNames"] = new
    print(f"{name}: {groups} -> {new}")


assert MINUTE_GROUP not in items
items = m.insert(items, MINUTE_GROUP, {"class": ITEM, "value": {
    "groupNames": [], "itemType": "Group", "tags": [], "label": "001 InfluxDB bei Änderung, höchstens jede Minute",
    "category": "material:storage"}})
for n in COUNTERS:
    regroup(n, "influxdb_change", [MINUTE_GROUP])
for n in GAUGES:
    regroup(n, "influxdb_change", ["influxdb_change_at_most"])
for n in PERSIST:
    regroup(n, None, ["influxdb_periodic", "influxdb_change"])

cfg = pers["influxdb"]["value"]
assert not [f for f in cfg["timeFilters"] if f["name"] == MINUTE_FILTER]
cfg["timeFilters"].append({"name": MINUTE_FILTER, "value": 1, "unit": "m"})
at_most = next(i for i, c in enumerate(cfg["configs"]) if c["items"] == ["influxdb_change_at_most*"])
cfg["configs"][at_most:at_most] = [
    {"items": [f"{MINUTE_GROUP}*"], "strategies": ["everyChange"], "filters": [MINUTE_FILTER]},
    {"items": [f"{MINUTE_GROUP}*"], "strategies": ["everyChange"], "filters": ["onlyZero"]}]
(zero,) = [f for f in cfg["equalsFilters"] if f["name"] == "onlyZero"]
assert "0 kWh" not in zero["values"]
zero["values"].append("0 kWh")
print("onlyZero:", zero["values"])

texts = {ITEMS: m.encode(items, *files[ITEMS][1]), PERS: m.encode(pers, *files[PERS][1])}
print(f"{len(COUNTERS)} counters at most once a minute, {len(GAUGES)} gauges every 5 s, {len(PERSIST)} newly persisted")
if sys.argv[1] == "apply":
    for name, text in texts.items():
        open(m.DB + name, "w", encoding="utf-8").write(text)
    print("written")
