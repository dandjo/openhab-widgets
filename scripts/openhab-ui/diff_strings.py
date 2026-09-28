import json, sys, datetime
sys.argv = ["x", "update"]
exec(open("check_dev.py").read().split("g = load(")[0])  # load() and build()
new, old = build(load("dashboard_local.py")), build(load("prev_local.py"))
def flat(v, path="", out=None):
    out = {} if out is None else out
    if isinstance(v, dict):
        for k, x in v.items(): flat(x, f"{path}/{k}", out)
    elif isinstance(v, list):
        for i, x in enumerate(v): flat(x, f"{path}/{i}", out)
    else:
        out[path] = v
    return out
total = 0
for uid in new:
    a, b = flat(old[uid]), flat(new[uid])
    if a.keys() != b.keys():
        print(uid, "STRUCTURE differs", set(a) ^ set(b)); continue
    d = [(k, a[k], b[k]) for k in a if a[k] != b[k]]
    total += len(d)
    for k, x, y in d:
        print(uid, "|", str(x)[:110], "\n    ->", str(y)[:130])
print("changed values:", total)
