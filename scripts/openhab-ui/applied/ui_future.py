#!/usr/bin/env python3
"""Add the EPEX Spot chart page with future prices and wire it into overview and sitemap.

Usage: ui_future.py check|apply   (run as root with openHAB stopped for apply)
"""
import datetime
import sys

src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)

PAGE_UID = "epex_spot"
PRICE_ITEMS = ("epex_spot_awattar", "epex_spot_awattar_cheapest", "epex_spot_awattar_priciest")


def java_timestamp(now):
    hour = now.hour % 12 or 12
    return f"{now:%b} {now.day}, {now.year}, {hour}:{now:%M:%S} {'AM' if now.hour < 12 else 'PM'}"


def page(now):
    return {
        "class": "org.openhab.core.ui.components.RootUIComponent",
        "value": {
            "uid": PAGE_UID,
            "tags": [],
            "props": {"parameters": [], "parameterGroups": []},
            "timestamp": java_timestamp(now),
            "component": "oh-chart-page",
            "config": {
                "chartType": "",
                "future": "0.75",
                "icon": "oh:price",
                "label": "EPEX Spot",
                "order": "22",
                "period": "2D",
                "sidebar": True,
            },
            "slots": {
                "grid": [{"component": "oh-chart-grid", "config": {}}],
                "xAxis": [{"component": "oh-time-axis", "config": {"gridIndex": 0}}],
                "yAxis": [{"component": "oh-value-axis", "config": {"gridIndex": 0, "name": "EUR/kWh"}}],
                "series": [{"component": "oh-time-series", "config": {
                    "name": "aWATTar",
                    "gridIndex": 0,
                    "xAxisIndex": 0,
                    "yAxisIndex": 0,
                    "type": "line",
                    "step": "end",
                    "item": "epex_spot_awattar",
                }}],
                "legend": [],
                "tooltip": [{"component": "oh-chart-tooltip", "config": {
                    "show": True, "trigger": "axis", "confine": True, "smartFormatter": True,
                }}],
                "dataZoom": [],
                "visualMap": [],
                "title": [],
                "toolbox": [],
            },
        },
    }


def migrate_pages(d):
    assert PAGE_UID not in d
    rewired = []

    def walk(node):
        if isinstance(node, dict):
            cfg = node.get("config", {})
            if (node.get("component") == "oh-label-item" and cfg.get("item") in PRICE_ITEMS
                    and cfg.get("action") == "analyzer"):
                cfg.pop("actionAnalyzerItems", None)
                cfg["action"] = "popup"
                cfg["actionModal"] = f"page:{PAGE_UID}"
                rewired.append(cfg["item"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(d["overview"])
    assert sorted(rewired) == sorted(PRICE_ITEMS), rewired
    return m.insert(d, PAGE_UID, page(datetime.datetime.now()))


def migrate_sitemap(d):
    changed = []

    def walk(node):
        if isinstance(node, dict):
            cfg = node.get("config", {})
            if node.get("component") == "Chart" and cfg.get("item") == "epex_spot_awattar":
                assert cfg.get("period") == "D-D", cfg
                cfg["period"] = "12h-36h"
                changed.append(cfg)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(d)
    assert len(changed) == 2, changed
    return d


FILES = {
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
