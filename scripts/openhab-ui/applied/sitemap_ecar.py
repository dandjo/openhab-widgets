#!/usr/bin/env python3
"""Sitemap: an E-Car entry above Air Conditioning in the Equipment frame, built like the plug entries.
Usage: sitemap_ecar.py check|apply   (run as root with openHAB stopped for apply)
"""
import copy, json, sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
NAME = "uicomponents_system_sitemap.json"


def migrate(d):
    root = d["default"]["value"]
    equipment = next(f for f in root["slots"]["widgets"] if f.get("config", {}).get("label") == "Equipment")
    entries = equipment["slots"]["widgets"]
    labels = [e.get("config", {}).get("label") for e in entries]
    assert "E-Car" not in labels
    fridge = entries[labels.index("Refrigerator")]
    car = json.loads(json.dumps(fridge).replace("refrigerator_", "e_car_"))
    car["config"].update(label="E-Car", icon="garage")
    frame = car["slots"]["widgets"][0]
    frame["config"]["label"] = "Calculated from the Air Conditioning Plug"
    first = frame["slots"]["widgets"][0]
    assert first["component"] == "Switch" and first["config"]["item"] == "e_car_switch"
    # the car has no switch of its own; this only mirrors the plug, which also cuts the air conditioner
    frame["slots"]["widgets"][0] = {"component": "Text", "config": {"icon": "switch", "item": "e_car_switch",
                                                                    "label": "Plug (Air Conditioning)"}}
    entries.insert(labels.index("Air Conditioning"), car)
    print("inserted before Air Conditioning at", labels.index("Air Conditioning"), "with",
          len(frame["slots"]["widgets"]), "widgets")
    return d


data, enc = m.detect(m.DB + NAME)
text = m.encode(migrate(data), *enc)
print(NAME, "encoder", enc, "ok")
if sys.argv[1] == "apply":
    open(m.DB + NAME, "w", encoding="utf-8").write(text)
    print("written")
