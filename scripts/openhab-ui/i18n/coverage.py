import json, re, collections, importlib
import de_labels
importlib.reload(de_labels)
T = de_labels.translate
d = json.load(open("labels_export.json"))
pages = json.load(open("pages_export.json"))
sm = json.load(open("sitemap_export.json"))
GENERATED = re.compile(r"^(overview|appliance_.*|flow_.*|hp_.*|e_car)$")
sources = collections.defaultdict(set)
for n, v in d["items"].items():
    sources["item"].add(v["label"])
for t in d["things"].values():
    sources["thing"].add(t["label"])
    for c in t["channels"]:
        if c["label"]:
            sources["channel"].add(c["label"])
for r in d["rules"].values():
    sources["rule"].add(r["name"])
def walk(c):
    if isinstance(c, dict):
        cfg = c.get("config", {})
        for key in ("title", "label", "text", "footer", "subtitle", "header"):
            val = cfg.get(key)
            if isinstance(val, str) and val and not val.startswith("="):
                sources["page"].add(val)
        for v in c.get("slots", {}).values():
            for x in v:
                walk(x)
for uid, p in pages.items():
    if GENERATED.match(uid):
        continue
    sources["page"].add(p["value"]["config"].get("label", ""))
    for sv in p["value"].get("slots", {}).values():
        for x in sv:
            walk(x)
def walk_sm(c):
    cfg = c.get("config", {})
    if cfg.get("label"):
        sources["sitemap"].add(re.sub(r"\s*\[.*\]$", "", cfg["label"]) if not cfg["label"].endswith("[]") else cfg["label"])
    for x in c.get("slots", {}).get("widgets", []):
        walk_sm(x)
walk_sm(sm["default"]["value"])
missing = {k: sorted(s for s in v if s and T(s) is None) for k, v in sources.items()}
for k, v in missing.items():
    print(f"== {k}: {len(v)} of {len(sources[k])} untranslated")
    if v:
        print("   " + " | ".join(v))
