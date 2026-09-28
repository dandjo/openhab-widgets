#!/usr/bin/env python3
"""German labels and material icons for homepi's openHAB: items, things, channels, metadata options, rules,
transformations, the device pages and the sitemap. Item names stay unchanged.
Usage: german_apply.py check|apply   (run as root with openHAB stopped for apply)
"""
import collections, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import de_labels as L
import icons_de as I
src = open(os.path.join(HERE, "..", "awattar_migrate.py")).read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
GENERATED = re.compile(r"^(overview|appliance_.*|flow_.*|hp_.*|e_car|home)$")
stats = collections.Counter()
ITEM_ICON = {}


def tr(s, what):
    t = L.translate(s)
    if t is None or t == s:
        stats[f"{what} unchanged"] += 1
        return s
    stats[f"{what} translated"] += 1
    return t


def migrate_items(d):
    for name, it in d.items():
        v = it["value"]
        label_en = v.get("label") or ""
        icon = I.icon_for(name, label_en, v["itemType"])
        ITEM_ICON[name] = icon
        v["category"] = icon[3:] if icon.startswith("oh:") else icon  # classic categories carry no prefix
        v["label"] = tr(label_en, "item label")
    return d


def migrate_things(d):
    for uid, t in d.items():
        v = t["value"]
        v["label"] = tr(v.get("label"), "thing label")
        for c in v.get("channels", []):
            if c.get("label"):
                c["label"] = tr(c["label"], "channel label")
    return d


def migrate_metadata(d):
    for key, md in d.items():
        cfg = md["value"]["configuration"]
        if key.split(":")[0] in ("stateDescription", "commandDescription") and cfg.get("options") in L.OPTIONS:
            cfg["options"] = L.OPTIONS[cfg["options"]]
            stats["options translated"] += 1
    for item, options in L.STATE_OPTIONS.items():
        key = f"stateDescription:{item}"
        if key in d:
            d[key]["value"]["configuration"]["options"] = options
        else:
            d = m.insert(d, key, {"class": "org.openhab.core.items.Metadata", "value": {
                "key": {"segments": ["stateDescription", item], "uid": key}, "value": " ",
                "configuration": {"options": options, "pattern": "%s"}}})
        stats["state options"] += 1
    return d


def migrate_rules(d):
    for uid, r in d.items():
        v = r["value"]
        v["name"] = tr(v.get("name"), "rule name")
        if uid in L.RULE_DESCRIPTIONS:
            v["description"] = L.RULE_DESCRIPTIONS[uid]
            stats["rule description"] += 1
    return d


def migrate_transformations(d):
    for uid, t in d.items():
        if t["value"].get("label") in L.TRANSFORMATIONS:
            t["value"]["label"] = L.TRANSFORMATIONS[t["value"]["label"]]
            stats["transformation label"] += 1
    return d


def widget_icon(cfg, sitemap=False):
    item = cfg.get("item")
    icon = cfg.get("icon")
    if item in ITEM_ICON:
        new = ITEM_ICON[item]
    elif isinstance(icon, str):
        bare = icon[3:] if icon.startswith("oh:") else icon
        new = ("material:" + I.CLASSIC_TO_MATERIAL[bare]) if bare in I.CLASSIC_TO_MATERIAL else icon
    else:
        return
    if sitemap and new.startswith("oh:"):
        new = new[3:]
    if icon != new and (icon is not None or item in ITEM_ICON):
        if icon is None and not sitemap:
            return  # page widgets without an icon keep none
        cfg["icon"] = new
        stats[("sitemap" if sitemap else "page") + " icon"] += 1


def walk_page(c):
    if isinstance(c, dict):
        cfg = c.get("config", {})
        for key in ("title", "label", "text", "footer", "subtitle", "header", "name"):
            val = cfg.get(key)
            if isinstance(val, str) and val and not val.startswith("="):
                cfg[key] = tr(val, "page text")
        if "icon" in cfg:
            widget_icon(cfg)
        for v in c.get("slots", {}).values():
            for x in v:
                walk_page(x)


def migrate_pages(d):
    for uid, p in d.items():
        if GENERATED.match(uid):
            continue
        v = p["value"]
        if v["config"].get("label"):
            v["config"]["label"] = tr(v["config"]["label"], "page label")
        for slot in v.get("slots", {}).values():
            for x in slot:
                walk_page(x)
    return d


def walk_sitemap(c):
    cfg = c.get("config", {})
    label = cfg.get("label")
    if label:
        mt = re.match(r"^(.*?)(\s*\[.*\])?$", label)
        text, fmt = mt.group(1), mt.group(2) or ""
        if label.endswith("[]"):
            cfg["label"] = tr(label, "sitemap label")
        else:
            cfg["label"] = tr(text, "sitemap label") + fmt
    if cfg.get("mappings"):
        cfg["mappings"] = [re.sub(r'="([^"]*)"$', lambda mm: '="' + (L.translate(mm.group(1)) or mm.group(1)) + '"', x)
                           for x in cfg["mappings"]]
    widget_icon(cfg, sitemap=True)
    for x in c.get("slots", {}).get("widgets", []):
        walk_sitemap(x)


def migrate_sitemap(d):
    walk_sitemap(d["default"]["value"])
    return d


FILES = [("org.openhab.core.items.Item.json", migrate_items),  # first: the icons of the widgets follow the items
         ("org.openhab.core.thing.Thing.json", migrate_things),
         ("org.openhab.core.items.Metadata.json", migrate_metadata),
         ("automation_rules.json", migrate_rules),
         ("org.openhab.core.transform.Transformation.json", migrate_transformations),
         ("uicomponents_ui_page.json", migrate_pages),
         ("uicomponents_system_sitemap.json", migrate_sitemap)]
results = {}
for name, fn in FILES:
    data, enc = m.detect(m.DB + name)
    results[name] = m.encode(fn(data), *enc)
    print(name, "encoder", enc, "ok")
for k, v in sorted(stats.items()):
    print(f"  {k}: {v}")
if sys.argv[1] == "apply":
    for name, text in results.items():
        open(m.DB + name, "w", encoding="utf-8").write(text)
    print("written")
