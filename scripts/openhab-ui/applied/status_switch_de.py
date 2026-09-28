#!/usr/bin/env python3
"""Status switches (heat pump telemetry, finish and door signals, alerts, the E-Car mirror) show An/Aus.
Read-only, so openHAB derives no command buttons from the options. Usage: status_switch_de.py check|apply"""
import re, sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
items, _ = m.detect(m.DB + "org.openhab.core.items.Item.json")
status = sorted(n for n, v in items.items() if v["value"]["itemType"] == "Switch" and
                re.match(r"^(espaltherma_|miele_.*_(finished|door_signal)$|.*_finished$|netatmo_.*alert|e_car_switch$)", n))
data, enc = m.detect(m.DB + "org.openhab.core.items.Metadata.json")
for n in status:
    key = f"stateDescription:{n}"
    if key in data:
        cfg = data[key]["value"]["configuration"]
        cfg.update(options="ON=An,OFF=Aus", readOnly=True)
        cfg.setdefault("pattern", "%s")
    else:
        data = m.insert(data, key, {"class": "org.openhab.core.items.Metadata", "value": {
            "key": {"segments": ["stateDescription", n], "uid": key}, "value": " ",
            "configuration": {"options": "ON=An,OFF=Aus", "pattern": "%s", "readOnly": True}}})
text = m.encode(data, *enc)
print(len(status), "status switches ok")
if sys.argv[1] == "apply":
    open(m.DB + "org.openhab.core.items.Metadata.json", "w", encoding="utf-8").write(text)
    print("written")
