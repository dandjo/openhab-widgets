import datetime, json, sys, time
from zoneinfo import ZoneInfo
import hp_model as hm
TZ = ZoneInfo("Europe/Vienna")
def ns(s):
    return int(datetime.datetime.fromisoformat(s).replace(tzinfo=TZ).timestamp() * 1e9)
a, b, out = ns(sys.argv[1]), ns(sys.argv[2]), sys.argv[3]
ev = hm.events(a, b)
steps, py = [], []
m = hm.Metering()
cur, valve_changed = {}, None
i = 0
while i < len(ev):
    t = ev[i][0]
    changes = []
    while i < len(ev) and ev[i][0] == t:
        _, k, v = ev[i]
        if k == "valve" and cur.get("valve") != v:
            valve_changed = t
        cur[k] = v
        changes.append([hm.INPUTS[k], v])
        i += 1
    steps.append([t / 1e6, changes])
    r = m.step(cur, t, valve_changed)
    py.append([r[k] for k in ("space", "dhw", "standby", "total", "h_before", "h_after", "h_space", "h_dhw", "h_total")])
json.dump({"steps": steps}, open(out, "w"))
json.dump(py, open(out + ".py", "w"))
print(f"{len(ev)} input points, {len(steps)} evaluations")
