#!/usr/bin/env python3
"""air_conditioning_unit_power: the air conditioner's own power, the plug minus the E-Car, written by e_car_power;
the sitemap's Air Conditioning entry shows it instead of the plug.
Usage: ac_unit.py check|apply   (run as root with openHAB stopped for apply)
"""
import copy, sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
ITEM = "air_conditioning_unit_power"

OLD = """const acOn = items.getItem('faikout_perfera_switch').state === 'ON';
if (plug !== null) {
  const rest = Math.max(0, plug - ac);
  const power = acOn && rest < 300 ? 0 : rest;"""
NEW = """const acOn = items.getItem('faikout_perfera_switch').state === 'ON';
if (plug !== null) {
  // while the air conditioner is off the whole plug is the car; the two always add up to the plug
  const rest = Math.max(0, plug - ac);
  const power = !acOn ? plug : rest < 300 ? 0 : rest;
  items.getItem('air_conditioning_unit_power').postUpdate(Quantity(Math.max(0, plug - power).toFixed(2) + ' W'));"""


def migrate_items(d):
    assert ITEM not in d
    item = copy.deepcopy(d["air_conditioning_power"])
    item["value"]["label"] = "Air Conditioning Unit Power"
    return m.insert(d, ITEM, item)


def migrate_metadata(d):
    for ns in ("unit", "stateDescription"):
        md = copy.deepcopy(d[f"{ns}:air_conditioning_power"])
        md["value"]["key"] = {"segments": [ns, ITEM], "uid": f"{ns}:{ITEM}"}
        assert f"{ns}:{ITEM}" not in d
        d = m.insert(d, f"{ns}:{ITEM}", md)
    return d


def migrate_rules(d):
    r = d["e_car_power"]["value"]
    script = r["actions"][0]["configuration"]["script"]
    assert script.count(OLD) == 1
    r["actions"][0]["configuration"]["script"] = script.replace(OLD, NEW)
    r["description"] = ("Splits the air conditioning's plug into the E-Car and the air conditioner itself "
                        "(air_conditioning_unit_power), from Faikin's power and switch, and mirrors the plug's switch.")
    return d


def migrate_sitemap(d):
    root = d["default"]["value"]
    equipment = next(f for f in root["slots"]["widgets"] if f.get("config", {}).get("label") == "Equipment")
    ac = next(e for e in equipment["slots"]["widgets"] if e.get("config", {}).get("label") == "Air Conditioning")
    assert ac["config"]["item"] == "air_conditioning_power"
    ac["config"]["item"] = ITEM
    return d


FILES = {"org.openhab.core.items.Item.json": migrate_items,
         "org.openhab.core.items.Metadata.json": migrate_metadata,
         "automation_rules.json": migrate_rules,
         "uicomponents_system_sitemap.json": migrate_sitemap}
results = {}
for name, fn in FILES.items():
    data, enc = m.detect(m.DB + name)
    results[name] = m.encode(fn(data), *enc)
    print(name, "encoder", enc, "ok")
if sys.argv[1] == "apply":
    for name, text in results.items():
        open(m.DB + name, "w", encoding="utf-8").write(text)
    print("written")
