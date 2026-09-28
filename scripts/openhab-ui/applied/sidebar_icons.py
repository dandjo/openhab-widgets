#!/usr/bin/env python3
"""Material icons for the device pages in the sidebar. Usage: sidebar_icons.py check|apply (openHAB stopped for apply)"""
import sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
ICONS = {"netatmo": "cloud", "smartpi": "electric_meter", "power_meter": "electric_meter", "photovoltaics": "solar_power",
         "energy_storage": "battery_charging_full", "air_conditioning": "ac_unit", "heatpump": "heat_pump",
         "ventilation": "air", "water_meter": "water", "coffee_machine": "coffee", "washing_machine_1": "local_laundry_service",
         "washing_machine_2": "local_laundry_service", "tumble_dryer": "dry_cleaning", "refrigerator": "kitchen",
         "dishwasher": "flatware", "living_room_entertainment": "tv", "network": "router", "office_1": "computer",
         "office_2": "computer", "terrace_light": "light", "bicycle_batteries": "electric_bike", "epex_spot": "euro"}
data, enc = m.detect(m.DB + "uicomponents_ui_page.json")
for uid, icon in ICONS.items():
    data[uid]["value"]["config"]["icon"] = "material:" + icon
text = m.encode(data, *enc)
print("pages", len(ICONS), "ok")
if sys.argv[1] == "apply":
    open(m.DB + "uicomponents_ui_page.json", "w", encoding="utf-8").write(text)
    print("written")
