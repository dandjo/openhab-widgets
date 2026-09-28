#!/usr/bin/env python3
"""Move the aWATTar prices from the HTTP binding to the aWATTar binding with forecast persistence.

Usage: awattar_migrate.py check|apply   (run as root with openHAB stopped for apply)
"""
import json
import sys

DB = "/var/lib/openhab/jsondb/"
ADDONS = "/var/lib/openhab/config/org/openhab/addons.config"

BRIDGE = "awattar:bridge:epex_spot_awattar"
OLD_THING = "http:url:epex_spot_awattar"
OLD_TRANSFORMS = ["config:js:awattar_current_item", "config:js:awattar_extrema_item"]
RULE_UID = "epex_spot_awattar_extrema"

RULE_SCRIPT = """const price = items.getItem('epex_spot_awattar');
const now = time.toZDT();
const current = price.persistence.persistedState(now, 'influxdb');
const slots = current === null ? [] : price.persistence.getAllStatesBetween(current.timestamp, now.plusDays(2), 'influxdb');

if (slots.length > 0) {
  const cheapest = slots.reduce((a, b) => (b.numericState < a.numericState ? b : a));
  const priciest = slots.reduce((a, b) => (b.numericState > a.numericState ? b : a));
  items.getItem('epex_spot_awattar_cheapest').postUpdate(cheapest.quantityState);
  items.getItem('epex_spot_awattar_cheapest_hour').postUpdate(cheapest.timestamp);
  items.getItem('epex_spot_awattar_priciest').postUpdate(priciest.quantityState);
  items.getItem('epex_spot_awattar_priciest_hour').postUpdate(priciest.timestamp);
}"""

GSON_ESCAPES = {"<": "\\u003c", ">": "\\u003e", "&": "\\u0026", "=": "\\u003d", "'": "\\u0027",
                " ": "\\u2028", " ": "\\u2029"}


def encode(data, html, newline):
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if html:
        for char, esc in GSON_ESCAPES.items():
            text = text.replace(char, esc)
    return text + ("\n" if newline else "")


def detect(path):
    raw = open(path, encoding="utf-8").read()
    data = json.loads(raw)
    for html in (False, True):
        for newline in (False, True):
            if encode(data, html, newline) == raw:
                return data, (html, newline)
    raise SystemExit(f"no byte-exact encoder for {path}")


def insert(data, key, value):
    """Insert key keeping the file's (near-)sorted order."""
    items = [(k, v) for k, v in data.items() if k != key]
    pos = next((i for i, (k, _) in enumerate(items) if k > key), len(items))
    items.insert(pos, (key, value))
    return dict(items)


def channel(cid, label, description):
    return {
        "uid": f"{BRIDGE}:{cid}",
        "id": cid,
        "channelTypeUID": "awattar:uom-price",
        "itemType": "Number:EnergyPrice",
        "kind": "STATE",
        "label": label,
        "description": description,
        "defaultTags": ["Status", "Price"],
        "properties": {},
        "configuration": {},
    }


def migrate_things(d):
    d.pop(OLD_THING)
    return insert(d, BRIDGE, {
        "class": "org.openhab.core.thing.internal.ThingStorageEntity",
        "value": {
            "isBridge": True,
            "channels": [
                channel("market-net", "Net Market Price", "Price without VAT and network charge"),
                channel("market-gross", "Gross Market Price", "Price with VAT but without network charge"),
                channel("total-net", "Net Total Price", "Price with network charge but without VAT"),
                channel("total-gross", "Gross Total Price", "Price with network charge and VAT"),
            ],
            "label": "EPEX Spot aWATTar",
            "configuration": {"basePrice": 1.5, "country": "AT", "serviceFee": 3, "vatPercent": 20},
            "properties": {"thingTypeVersion": "1"},
            "UID": BRIDGE,
            "thingTypeUID": "awattar:bridge",
        },
    })


def migrate_links(d):
    old = [k for k, v in d.items() if v["value"]["channelUID"]["uid"].startswith(OLD_THING + ":")]
    assert len(old) == 5, old
    for k in old:
        d.pop(k)
    uid = f"{BRIDGE}:market-net"
    return insert(d, f"epex_spot_awattar -> {uid}", {
        "class": "org.openhab.core.thing.link.ItemChannelLink",
        "value": {
            "channelUID": {"segments": uid.split(":"), "uid": uid},
            "configuration": {"properties": {}},
            "itemName": "epex_spot_awattar",
        },
    })


def migrate_items(d):
    groups = d["epex_spot_awattar"]["value"]["groupNames"]
    assert groups == ["influxdb_change", "epex_spot"], groups
    groups[0] = "influxdb_forecast"
    return insert(d, "influxdb_forecast", {
        "class": "org.openhab.core.items.ManagedItemProvider$PersistedItem",
        "value": {"groupNames": [], "itemType": "Group", "tags": [], "label": "004 InfluxDB Forecast", "category": ""},
    })


def migrate_metadata(d):
    assert "unit:epex_spot_awattar" not in d
    return insert(d, "unit:epex_spot_awattar", {
        "class": "org.openhab.core.items.Metadata",
        "value": {
            "key": {"segments": ["unit", "epex_spot_awattar"], "uid": "unit:epex_spot_awattar"},
            "value": "EUR/kWh",
            "configuration": {},
        },
    })


def migrate_persistence(d):
    configs = d["influxdb"]["value"]["configs"]
    assert not any("influxdb_forecast*" in c["items"] for c in configs)
    configs.append({"items": ["influxdb_forecast*"], "strategies": ["forecast"], "filters": []})
    return d


def migrate_transforms(d):
    for uid in OLD_TRANSFORMS:
        d.pop(uid)
    return d


def migrate_rules(d):
    assert RULE_UID not in d
    return insert(d, RULE_UID, {
        "class": "org.openhab.core.automation.dto.RuleDTO",
        "value": {
            "triggers": [
                {"id": "1", "configuration": {"cronExpression": "0 0/15 * * * ? *"}, "type": "timer.GenericCronTrigger"},
                {"id": "2", "configuration": {"startlevel": 100}, "type": "core.SystemStartlevelTrigger"},
            ],
            "conditions": [],
            "actions": [
                {"inputs": {}, "id": "3",
                 "configuration": {"script": RULE_SCRIPT, "type": "application/javascript"},
                 "type": "script.ScriptAction"},
            ],
            "configuration": {},
            "configDescriptions": [],
            "templateState": "no-template",
            "uid": RULE_UID,
            "name": "EPEX Spot aWATTar Extrema",
            "tags": [],
            "visibility": "VISIBLE",
            "description": "Finds the cheapest and priciest persisted aWATTar price from the running slot to the end of the published day-ahead prices.",
        },
    })


def migrate_sitemap(d):
    """Drop the sub-page charts of the unpersisted cheapest/priciest items."""
    removed = []

    def walk(node):
        if isinstance(node, dict):
            slots = node.get("slots", {})
            widgets = slots.get("widgets") if isinstance(slots, dict) else None
            if node.get("component") == "Text" and widgets and all(
                    w.get("component") == "Chart"
                    and w.get("config", {}).get("item") in ("epex_spot_awattar_cheapest", "epex_spot_awattar_priciest")
                    for w in widgets):
                removed.append(node["config"]["item"])
                del node["slots"]
                return
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(d)
    assert sorted(removed) == ["epex_spot_awattar_cheapest", "epex_spot_awattar_priciest"], removed
    return d


FILES = {
    "org.openhab.core.thing.Thing.json": migrate_things,
    "org.openhab.core.thing.link.ItemChannelLink.json": migrate_links,
    "org.openhab.core.items.Item.json": migrate_items,
    "org.openhab.core.items.Metadata.json": migrate_metadata,
    "org.openhab.core.persistence.PersistenceServiceConfiguration.json": migrate_persistence,
    "org.openhab.core.transform.Transformation.json": migrate_transforms,
    "automation_rules.json": migrate_rules,
    "uicomponents_system_sitemap.json": migrate_sitemap,
}


def migrate_addons(text):
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(eol)
    idx = next(i for i, l in enumerate(lines) if l.startswith('binding="'))
    assert lines[idx].endswith('"'), lines[idx]
    bindings = lines[idx][len('binding="'):-1].split(",")
    assert "http" in bindings and "awattar" not in bindings, bindings
    bindings = ["awattar" if b == "http" else b for b in bindings]
    lines[idx] = 'binding="' + ",".join(bindings) + '"'
    return eol.join(lines)


def main():
    mode = sys.argv[1]
    results = {}
    for name, fn in FILES.items():
        data, enc = detect(DB + name)
        results[name] = (encode(fn(data), *enc), enc)
        print(f"{name}: encoder html={enc[0]} newline={enc[1]} ok")
    addons_new = migrate_addons(open(ADDONS, newline="").read())
    print("addons:", [l for l in addons_new.split("\n") if l.startswith("binding=")][0])
    if mode != "apply":
        return
    for name, (text, _) in results.items():
        with open(DB + name, "w", encoding="utf-8") as f:
            f.write(text)
    with open(ADDONS, "w", newline="") as f:
        f.write(addons_new)
    print("written")


main()
