#!/usr/bin/env python3
"""Sitemap: the E-Car entry gets material:electric_car, a font icon Basic UI ships locally.
Usage: sitemap_icon.py check|apply   (run as root with openHAB stopped for apply)
"""
import sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
NAME = "uicomponents_system_sitemap.json"


def migrate(d):
    root = d["default"]["value"]
    equipment = next(f for f in root["slots"]["widgets"] if f.get("config", {}).get("label") == "Equipment")
    car = next(e for e in equipment["slots"]["widgets"] if e.get("config", {}).get("label") == "E-Car")
    assert car["config"]["icon"] == "garage"
    car["config"]["icon"] = "material:electric_car"
    return d


data, enc = m.detect(m.DB + NAME)
text = m.encode(migrate(data), *enc)
print(NAME, "encoder", enc, "ok")
if sys.argv[1] == "apply":
    open(m.DB + NAME, "w", encoding="utf-8").write(text)
    print("written")
