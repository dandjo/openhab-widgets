#!/usr/bin/env python3
"""Recompute the E-Car history with the standby-aware split of e_car_power: at every existing point of
e_car_power the rule is replayed (a rest under 300 W is never the car, the learned base load of the air
conditioner comes off while it charges); e_car_energy_today and e_car_energy_total are integrated anew at
their existing points, air_conditioning_unit_power and the car's electrical values follow. Only existing points
are overwritten; their old values go to a gzipped CSV first.
Usage: e_car_rebuild.py check|apply BACKUP.csv.gz   (with openHAB stopped for apply)"""
import bisect
import collections
import datetime
import gzip
import json
import sys
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

INFLUX = "http://127.0.0.1:8086"
TZ = ZoneInfo("Europe/Vienna")
WEEK = int(7 * 86400 * 1e9)


def query(q):
    url = f"{INFLUX}/query?" + urllib.parse.urlencode({"db": "openhab", "epoch": "ns", "q": q})
    series = json.load(urllib.request.urlopen(url, timeout=600))["results"][0].get("series", [])
    return [(t, v) for t, v in series[0]["values"]] if series else []


def write(lines):
    for i in range(0, len(lines), 5000):
        req = urllib.request.Request(f"{INFLUX}/write?" + urllib.parse.urlencode({"db": "openhab", "precision": "ns"}),
                                     data="\n".join(lines[i:i + 5000]).encode(), method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            assert resp.status == 204, resp.status


class Last:
    """The last value at or before a time, for times asked in increasing order."""
    def __init__(self, points, default):
        self.t, self.v, self.default = [t for t, _ in points], [v for _, v in points], default

    def at(self, t):
        i = bisect.bisect_right(self.t, t) - 1
        return self.v[i] if i >= 0 and self.v[i] is not None else self.default


faikin = Last(query('SELECT value FROM "faikout_perfera_power"'), 0.0)
switch = Last(query('SELECT value FROM "faikout_perfera_switch"'), 0)
first = query('SELECT value FROM "e_car_power" ORDER BY time ASC LIMIT 1')[0][0]
end = query('SELECT value FROM "e_car_power" ORDER BY time DESC LIMIT 1')[0][0] + 1

# the small series, looked up while streaming through e_car_power
small = {m: query(f'SELECT value FROM "{m}" WHERE time >= {first}') for m in
         ("e_car_energy_today", "e_car_energy_total", "air_conditioning_unit_power", "e_car_apparent_power",
          "e_car_reactive_power", "e_car_power_factor", "e_car_current")}
asks = sorted({t for pts in small.values() for t, _ in pts})
car_at, energy_at, plug_at = {}, {}, {}

bases = {True: 10.0, False: 10.0}
bases[True] = 20.0
changed = []  # (t, old, new) of e_car_power
energy, prev_t, prev_v = 0.0, None, 0.0
ask_i = 0
a = first
plug_prev = query(f'SELECT value FROM "air_conditioning_power" WHERE time < {first} ORDER BY time DESC LIMIT 1')
while a < end:
    b = min(end, a + WEEK)
    plug = Last(plug_prev + query(f'SELECT value FROM "air_conditioning_power" WHERE time >= {a} AND time < {b}'), None)
    for t, old in query(f'SELECT value FROM "e_car_power" WHERE time >= {a} AND time < {b}'):
        # answer the lookups that fall before this point from the state so far
        while ask_i < len(asks) and asks[ask_i] < t:
            s = asks[ask_i]
            car_at[s] = prev_v
            energy_at[s] = energy + (prev_v * (s - prev_t) / 3.6e15 if prev_t is not None else 0)
            plug_at[s] = plug.at(s)
            ask_i += 1
        if prev_t is not None:
            energy += prev_v * (t - prev_t) / 3.6e15  # W·ns → kWh
        p = plug.at(t)
        if p is None:
            new = old
        else:
            on = switch.at(t) in (1, "ON", True)
            rest = max(0.0, p - (faikin.at(t) if on else 0.0))
            base = bases[on]
            new = 0.0
            if rest >= 300:
                new = round(max(0.0, rest - base), 2)
            elif rest < 150:
                bases[on] = base + 0.1 * (rest - base)
        if old is None or abs(new - old) > 0.005:
            changed.append((t, old, new))
        prev_t, prev_v = t, new
    tail = plug.t[-1] if plug.t else None
    plug_prev = [(tail, plug.v[-1])] if tail is not None else plug_prev
    a = b
while ask_i < len(asks):
    s = asks[ask_i]
    car_at[s] = prev_v
    energy_at[s] = energy + prev_v * (s - prev_t) / 3.6e15
    plug_at[s] = plug.at(s)
    ask_i += 1


def midnight_before(t):
    d = datetime.datetime.fromtimestamp(t / 1e9, TZ)
    return int(datetime.datetime.combine(d.date(), datetime.time(), TZ).timestamp() * 1e9)


# energy since the first point at every local midnight, integrated over the new series step by step
mids = sorted({midnight_before(t) for t, _ in small["e_car_energy_today"]} | {midnight_before(t) for t, _ in small["e_car_energy_total"]})
# E(midnight): the energy at the ask closest before each midnight plus the step up to it is not tracked, so
# the midnights are asked in a second pass over the small series only: today(t) = E(t) - E(last today point
# at or before midnight), which the backfill wrote as exactly 00:00 with value 0 and the rule writes after it
e_mid = {}
today_pts = small["e_car_energy_today"]
for t, _ in today_pts:
    m = midnight_before(t)
    if t == m:
        e_mid[m] = energy_at[t]
    elif m < first:  # the first day: its 00:00 point lies before the first power point, the energy starts at 0
        e_mid[m] = 0.0
fix = collections.defaultdict(list)  # measurement → (t, old, new)
missing_mid = set()
for t, old in today_pts:
    m = midnight_before(t)
    if m not in e_mid:
        missing_mid.add(m)
        continue
    new = round(energy_at[t] - e_mid[m], 3)
    if old is None or abs(new - old) > 0.0005:
        fix["e_car_energy_today"].append((t, old, new))
for t, old in small["e_car_energy_total"]:
    new = round(energy_at[t], 3)
    if old is None or abs(new - old) > 0.0005:
        fix["e_car_energy_total"].append((t, old, new))
for t, old in small["air_conditioning_unit_power"]:
    p = plug_at[t]
    if p is not None:
        new = round(max(0.0, p - car_at[t]), 2)
        if old is None or abs(new - old) > 0.005:
            fix["air_conditioning_unit_power"].append((t, old, new))
for msr in ("e_car_apparent_power", "e_car_reactive_power", "e_car_power_factor", "e_car_current"):
    for t, old in small[msr]:
        if car_at[t] == 0 and old not in (0, 0.0, None):
            fix[msr].append((t, old, 0.0))
fix["e_car_power"] = changed

old_total = small["e_car_energy_total"][-1][1]
new_total = fix["e_car_energy_total"][-1][2] if fix["e_car_energy_total"] else old_total
print(f"e_car_power: {len(changed)} of the points change; bases learned: off {bases[False]:.1f} W, on {bases[True]:.1f} W")
print(f"midnights without a 00:00 point (their today points left as they are): "
      f"{[datetime.datetime.fromtimestamp(m / 1e9, TZ).isoformat() for m in sorted(missing_mid)]}")
for m in sorted(missing_mid):
    print("   points that day:", [(datetime.datetime.fromtimestamp(t / 1e9, TZ).strftime("%H:%M:%S"), v)
                                 for t, v in today_pts if midnight_before(t) == m][:8])
print(f"total: {old_total} -> {new_total} kWh")
for msr, pts in fix.items():
    print(f"  {msr}: {len(pts)} points")
day_end = {}
for t, old, new in fix["e_car_energy_today"]:
    d = datetime.datetime.fromtimestamp(t / 1e9, TZ).date()
    day_end[d] = (old, new)
print("last days (old -> new):", [(d.isoformat(), o, n) for d, (o, n) in sorted(day_end.items())[-6:]])
if sys.argv[1] == "apply":
    with gzip.open(sys.argv[2], "wt") as f:
        f.write("measurement,time_ns,old,new\n")
        for msr, pts in fix.items():
            for t, old, new in pts:
                f.write(f"{msr},{t},{old},{new}\n")
    write([f"{msr},item={msr} value={float(new)!r} {t}" for msr, pts in fix.items() for t, _, new in pts])
    print("written; old values in", sys.argv[2])
