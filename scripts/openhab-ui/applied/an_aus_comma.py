#!/usr/bin/env python3
"""On/off states read An/Aus like every other state, and the price states carry a decimal comma.
Usage: an_aus_comma.py check|apply"""
import sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)

OLD_PRICE = "JS(|(parseFloat(input)*100).toFixed(3) + ' ct/kWh'):%s"
NEW_PRICE = "JS(|(parseFloat(input)*100).toFixed(3).replace('.', ',') + ' ct/kWh'):%s"
LABELS = {"ESPAltherma System AUS": "ESPAltherma System aus"}


def metadata(data):
    n_opt = n_price = 0
    for key, v in data.items():
        cfg = v["value"].get("configuration", {})
        if key.startswith("stateDescription:") and cfg.get("options") == "ON=EIN,OFF=AUS":
            cfg["options"] = "ON=An,OFF=Aus"
            n_opt += 1
        if key.startswith("stateDescription:") and cfg.get("pattern") == OLD_PRICE:
            cfg["pattern"] = NEW_PRICE
            n_price += 1
    assert (n_opt, n_price) == (35, 6), (n_opt, n_price)
    return data


def relabel(v, count):
    if isinstance(v, dict):
        for k, x in v.items():
            if isinstance(x, str) and x in LABELS:
                v[k] = LABELS[x]
                count.append(k)
            else:
                relabel(x, count)
    elif isinstance(v, list):
        for x in v:
            relabel(x, count)
    return v


def labels(expected):
    def fn(data):
        count = []
        relabel(data, count)
        assert len(count) == expected, count
        return data
    return fn


FILES = {"org.openhab.core.items.Metadata.json": metadata,
         "org.openhab.core.items.Item.json": labels(1),
         "org.openhab.core.thing.Thing.json": labels(1)}
results = {}
for name, fn in FILES.items():
    data, enc = m.detect(m.DB + name)
    results[name] = m.encode(fn(data), *enc)
    print(name, "ok")
if sys.argv[1] == "apply":
    for name, text in results.items():
        open(m.DB + name, "w", encoding="utf-8").write(text)
    print("written")
