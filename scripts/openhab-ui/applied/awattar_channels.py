#!/usr/bin/env python3
"""Link and persist market-gross, total-net and total-gross of the aWATTar bridge and show them in MainUI and sitemap.

Usage: awattar_channels.py check|apply   (run as root with openHAB stopped for apply)
"""
import copy
import sys

src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)

BRIDGE = "awattar:bridge:epex_spot_awattar"
GROUP = "epex_spot_awattar_prices"
# 1.5 ct/kWh net surcharge; the binding adds its 3 % fee on top of market + base, so base = 1.5 / 1.03
BASE_PRICE = 1.456311
NEW = [
    # item, channel, item label, UI title
    ("epex_spot_awattar_market_gross", "market-gross", "EPEX Spot aWATTar Market Gross", "aWATTar Market Gross"),
    ("epex_spot_awattar_total_net", "total-net", "EPEX Spot aWATTar Total Net", "aWATTar Total Net"),
    ("epex_spot_awattar_total_gross", "total-gross", "EPEX Spot aWATTar Total Gross", "aWATTar Total Gross"),
]
ALL_PRICES = ["epex_spot_awattar"] + [n[0] for n in NEW]


def migrate_items(d):
    for name, _, label, _ in NEW:
        assert name not in d, name
        d = m.insert(d, name, {
            "class": "org.openhab.core.items.ManagedItemProvider$PersistedItem",
            "value": {"groupNames": ["influxdb_forecast", "epex_spot", GROUP], "itemType": "Number:EnergyPrice",
                      "tags": ["Point"], "label": label, "category": "price"},
        })
    assert GROUP not in d
    d = m.insert(d, GROUP, {
        "class": "org.openhab.core.items.ManagedItemProvider$PersistedItem",
        "value": {"groupNames": [], "itemType": "Group", "tags": [], "label": "EPEX Spot aWATTar Prices",
                  "category": "price"},
    })
    groups = d["epex_spot_awattar"]["value"]["groupNames"]
    assert groups == ["influxdb_forecast", "epex_spot"], groups
    groups.append(GROUP)
    return d


def migrate_metadata(d):
    pattern = d["stateDescription:epex_spot_awattar"]["value"]["configuration"]["pattern"]
    for name, *_ in NEW:
        for ns, value, cfg in (("unit", "EUR/kWh", {}), ("stateDescription", " ", {"pattern": pattern})):
            key = f"{ns}:{name}"
            assert key not in d, key
            d = m.insert(d, key, {
                "class": "org.openhab.core.items.Metadata",
                "value": {"key": {"segments": [ns, name], "uid": key}, "value": value, "configuration": dict(cfg)},
            })
    return d


def migrate_links(d):
    for name, channel, *_ in NEW:
        uid = f"{BRIDGE}:{channel}"
        key = f"{name} -> {uid}"
        assert key not in d, key
        d = m.insert(d, key, {
            "class": "org.openhab.core.thing.link.ItemChannelLink",
            "value": {"channelUID": {"segments": uid.split(":"), "uid": uid},
                      "configuration": {"properties": {}}, "itemName": name},
        })
    return d


def migrate_things(d):
    cfg = d[BRIDGE]["value"]["configuration"]
    assert cfg["basePrice"] == 1.5, cfg
    cfg["basePrice"] = BASE_PRICE
    return d


def migrate_pages(d):
    chart = d["epex_spot"]["value"]["slots"]
    series = chart["series"]
    assert len(series) == 1, series
    for name, _, _, title in NEW:
        s = copy.deepcopy(series[0])
        s["config"]["name"] = title
        s["config"]["item"] = name
        series.append(s)
    series[0]["config"]["name"] = "aWATTar Market Net"
    chart["legend"] = [{"component": "oh-chart-legend", "config": {"show": True, "bottom": "3", "type": "scroll"}}]

    inserted = []

    def walk(node):
        if isinstance(node, list):
            for i, w in enumerate(node):
                if (isinstance(w, dict) and w.get("component") == "oh-label-item"
                        and w.get("config", {}).get("item") == "epex_spot_awattar"):
                    for j, (name, _, _, title) in enumerate(NEW, start=1):
                        node.insert(i + j, {"component": "oh-label-item", "config": {
                            "action": "popup", "actionModal": "page:epex_spot", "icon": "oh:price",
                            "iconUseState": True, "item": name, "title": title}})
                        inserted.append(name)
                    return
            for w in node:
                walk(w)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)

    walk(d["overview"])
    assert len(inserted) == 3, inserted
    return d


def migrate_sitemap(d):
    top = d["default"]["value"]["slots"]["widgets"][0]["slots"]["widgets"]
    epex = next(w for w in top if w.get("config", {}).get("item") == "epex_spot_awattar")
    rows = epex["slots"]["widgets"]
    assert rows[0]["config"] == {"icon": "price", "item": "epex_spot_awattar", "label": "aWATTar"}, rows[0]
    template = rows[0]
    for j, (name, _, _, title) in enumerate(NEW, start=1):
        row = copy.deepcopy(template)
        row["config"]["item"] = name
        row["config"]["label"] = title
        row["slots"]["widgets"][0]["config"]["item"] = name
        rows.insert(j, row)
    last = rows[-1]
    assert last["component"] == "Chart" and last["config"]["item"] == "epex_spot_awattar", last
    last["config"]["item"] = GROUP
    last["config"]["legend"] = True
    return d


FILES = {
    "org.openhab.core.items.Item.json": migrate_items,
    "org.openhab.core.items.Metadata.json": migrate_metadata,
    "org.openhab.core.thing.link.ItemChannelLink.json": migrate_links,
    "org.openhab.core.thing.Thing.json": migrate_things,
    "uicomponents_ui_page.json": migrate_pages,
    "uicomponents_system_sitemap.json": migrate_sitemap,
}


def main():
    results = {}
    for name, fn in FILES.items():
        data, enc = m.detect(m.DB + name)
        results[name] = m.encode(fn(data), *enc)
        print(f"{name}: encoder html={enc[0]} newline={enc[1]} ok")
    if sys.argv[1] != "apply":
        return
    for name, text in results.items():
        with open(m.DB + name, "w", encoding="utf-8") as f:
            f.write(text)
    print("written")


main()
