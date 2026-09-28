#!/usr/bin/env python3
"""Sitemap: the device entries of the Geräte frame carry the icons of their MainUI sidebar pages, not the icon of the
value they show. Usage: sitemap_nav_icons.py check|apply   (run as root with openHAB stopped for apply)"""
import sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
NAV = {"SmartPi": "electric_meter", "Stromzähler": "electric_meter", "Photovoltaik": "solar_power",
       "Batteriespeicher": "battery_charging_full", "E-Auto": "electric_car", "Klimaanlage": "ac_unit",
       "Wärmepumpe": "heat_pump", "Lüftung": "air", "Wasserzähler": "water", "Kaffeemaschine": "coffee",
       "Wäschetrockner": "dry_cleaning", "Waschmaschine 1": "local_laundry_service",
       "Waschmaschine 2": "local_laundry_service", "Kühlschrank": "kitchen", "Geschirrspüler": "flatware",
       "Büro 1": "computer", "Büro 2": "computer", "Wohnzimmer Medien": "tv", "Netzwerk": "router",
       "Terrassenlicht": "light", "Fahrradakkus": "electric_bike", "Innen": "cloud", "Außen": "cloud"}
data, enc = m.detect(m.DB + "uicomponents_system_sitemap.json")
frame = next(f for f in data["default"]["value"]["slots"]["widgets"] if f.get("config", {}).get("label") == "Geräte")
done = []
for w in frame["slots"]["widgets"]:
    label = w["config"].get("label")
    if label in NAV:
        w["config"]["icon"] = "material:" + NAV[label]
        done.append(label)
missing = [w["config"].get("label") for w in frame["slots"]["widgets"] if w["config"].get("label") not in NAV]
text = m.encode(data, *enc)
print(len(done), "entries; without a match:", missing)
if sys.argv[1] == "apply":
    open(m.DB + "uicomponents_system_sitemap.json", "w", encoding="utf-8").write(text)
    print("written")
