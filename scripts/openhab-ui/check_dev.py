import json, sys, datetime, subprocess
sys.argv = ["x", "update"]
def load(path):
    g = {}
    exec(compile(open(path).read().replace("\nmain()\n", "\n"), path, "exec"), g)
    return g
now = datetime.datetime(2026, 9, 25, 12, 0)
def build(g, devices=True):
    pages = {"overview": g["page"](now), **g["popup_pages"](now), **g["popup_pages_of"]("flow", g["FLOW_POPUPS"], now),
             **g["popup_pages_of"]("hp", g["HP_POPUPS"], now)}
    if devices:
        for uid, blocks in g["DEVICE_PAGES"].items():
            pages[uid] = g["layout_page"](uid, {"label": uid, "sidebar": True}, blocks(), now)
    return pages
g = load("dashboard_local.py"); new = build(g); again = build(g, devices=False); ref = build(load("ref_local.py"), devices=False)
print("overview stable after device pages:", all(json.dumps(again[u], sort_keys=True) == json.dumps(new[u], sort_keys=True) for u in again))
same = [u for u in ref if json.dumps(ref[u], sort_keys=True) == json.dumps(new[u], sort_keys=True)]
print("unchanged vs pre-devicepages:", len(same), "of", len(ref), "| differing:", [u for u in ref if u not in same])
exprs = []
def walk(v):
    if isinstance(v, str) and v.startswith("="): exprs.append(v[1:])
    elif isinstance(v, dict): [walk(x) for x in v.values()]
    elif isinstance(v, list): [walk(x) for x in v]
for p in new.values(): walk(p)
json.dump(exprs, open("exprs.json", "w"))

