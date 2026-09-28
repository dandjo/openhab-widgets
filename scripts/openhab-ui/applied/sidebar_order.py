#!/usr/bin/env python3
"""The sidebar's pages numbered anew from 1: the weather first, the electricity price below it, then the devices in
their order so far (E-Car after the energy storage). Run after the generator has added the weather page.
Usage: sidebar_order.py check|apply   (with openHAB stopped for apply)"""
import sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
ORDER = ["weather", "epex_spot", "netatmo", "smartpi", "power_meter", "photovoltaics", "energy_storage", "e_car",
         "air_conditioning", "heatpump", "ventilation", "water_meter", "coffee_machine", "washing_machine_1",
         "washing_machine_2", "tumble_dryer", "refrigerator", "dishwasher", "living_room_entertainment", "network",
         "office_1", "office_2", "terrace_light", "bicycle_batteries"]
NAME = "uicomponents_ui_page.json"
data, enc = m.detect(m.DB + NAME)
sidebar = {uid for uid, p in data.items() if p["value"]["config"].get("sidebar")}
# a check before the generator has run may miss the weather page, an apply must find every page
missing = set(ORDER) - sidebar
assert not sidebar - set(ORDER) and (not missing or sys.argv[1] == "check" and missing == {"weather"}), \
    (sorted(sidebar - set(ORDER)), sorted(missing))
for n, uid in enumerate(ORDER, 1):
    if uid not in data:
        print(f"{n:2} {uid:26} not there yet")
        continue
    config = data[uid]["value"]["config"]
    print(f"{n:2} {uid:26} {config.get('order')!s:>4} -> {n}  {config.get('label')}")
    config["order"] = str(n)
text = m.encode(data, *enc)
print(f"{NAME}: encoder html={enc[0]} newline={enc[1]} ok; {len(ORDER)} pages")
if sys.argv[1] == "apply":
    open(m.DB + NAME, "w", encoding="utf-8").write(text)
    print("written")
