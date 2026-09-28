#!/usr/bin/env python3
"""The air conditioning's circuit: the Shelly EM measures air conditioner and E-Car together. Items for the air
conditioner's own energy, today and total, as the meter's minus the car's; the two rules that split the
circuit get names of their own instead of e_car_*, and the energy rule fills the new items too.
Usage: ac_circuit.py check|apply   (with openHAB stopped for apply)"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "awattar_migrate.py")).read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)

NEW_ITEMS = {"air_conditioning_unit_energy_today": "Klimaanlage Geräteenergie heute",
             "air_conditioning_unit_energy_total": "Klimaanlage Geräteenergie gesamt"}


def items(d):
    for name, label in NEW_ITEMS.items():
        d = m.insert(d, name, {"class": "org.openhab.core.items.ManagedItemProvider$PersistedItem", "value": {
            "groupNames": ["air_conditioning", "influxdb_change", "influxdb_periodic"], "itemType": "Number:Energy",
            "tags": ["Energy", "Measurement"], "label": label, "category": "material:electric_meter"}})
    return d


def metadata(d):
    for name in NEW_ITEMS:
        for ns, value, cfg in (("unit", "kWh", {}), ("stateDescription", " ", {"pattern": "%.3f %unit%"})):
            key = f"{ns}:{name}"
            d = m.insert(d, key, {"class": "org.openhab.core.items.Metadata", "value": {
                "key": {"segments": [ns, name], "uid": key}, "value": value, "configuration": cfg}})
    return d


OLD_ENERGY_TAIL = """    persistEnergy('e_car_energy_today', today, 'kWh');
    totalItem.postUpdate(Quantity((base + today).toFixed(3) + ' kWh'));
  }
}"""
NEW_ENERGY_TAIL = """    persistEnergy('e_car_energy_today', today, 'kWh');
    totalItem.postUpdate(Quantity((base + today).toFixed(3) + ' kWh'));
    // the air conditioner's own energy is the meter's minus the car's, so the two always add up to the meter
    const meterToday = items.getItem('air_conditioning_energy_today').numericState;
    const meterTotal = items.getItem('air_conditioning_energy_total').numericState;
    if (meterToday !== null) {
      persistEnergy('air_conditioning_unit_energy_today', Math.max(0, meterToday - today), 'kWh');
    }
    if (meterTotal !== null) {
      items.getItem('air_conditioning_unit_energy_total').postUpdate(
        Quantity(Math.max(0, meterTotal - base - today).toFixed(3) + ' kWh'));
    }
  }
}"""
RULES = {  # old uid: (new uid, name, description)
    "e_car_power": ("air_conditioning_circuit_power", "Klimaanlagen-Stromkreis Leistung",
                    "Teilt die Messung des Shelly EM der Klimaanlage in E-Auto (e_car_*) und Klimaanlage selbst "
                    "(air_conditioning_unit_power) auf, nach Leistung und Schalter von Faikin, und spiegelt den "
                    "Schalter des Shelly-Relais. Unter 300 W lädt das Auto nicht; die gelernte Grundlast der "
                    "Klimaanlage (Standby, Innengerät) wird beim Laden abgezogen."),
    "e_car_energy": ("air_conditioning_circuit_energy", "Klimaanlagen-Stromkreis Energie",
                     "Energie des E-Autos heute, seine Leistung seit Mitternacht integriert, und gesamt auf Basis "
                     "von gestern; die Energie der Klimaanlage selbst als Messung des Shelly EM minus E-Auto."),
}


def rules(d):
    for old, (new, name, description) in RULES.items():
        r = d.pop(old)
        v = r["value"]
        v.update(uid=new, name=name, description=description)
        if old == "e_car_energy":
            cfg = v["actions"][0]["configuration"]
            assert cfg["script"].count(OLD_ENERGY_TAIL) == 1
            cfg["script"] = cfg["script"].replace(OLD_ENERGY_TAIL, NEW_ENERGY_TAIL)
        d = m.insert(d, new, r)
    return d


FILES = {"org.openhab.core.items.Item.json": items, "org.openhab.core.items.Metadata.json": metadata,
         "automation_rules.json": rules}
results = {}
for fname, fn in FILES.items():
    data, enc = m.detect(m.DB + fname)
    results[fname] = m.encode(fn(data), *enc)
    print(fname, "ok")
if sys.argv[1] == "apply":
    for fname, text in results.items():
        open(m.DB + fname, "w", encoding="utf-8").write(text)
    print("written")
