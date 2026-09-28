#!/usr/bin/env python3
"""Back-fill the E-Car from the plug, Faikin and the A/C switch since Faikin's history begins:
e_car_power at every plug point, and per past day e_car_energy_today (0 at 00:00, the day's energy at
23:59:59) and e_car_energy_total (the running sum at 23:59:59).
Usage: e_car_backfill.py check|apply   (with openHAB stopped for apply)
"""
import bisect
import datetime
import json
import sys
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

INFLUX = "http://127.0.0.1:8086"
TZ = ZoneInfo("Europe/Vienna")


def query(q):
    url = f"{INFLUX}/query?" + urllib.parse.urlencode({"db": "openhab", "epoch": "ns", "q": q})
    series = json.load(urllib.request.urlopen(url, timeout=300))["results"][0].get("series", [])
    return [(t, v) for t, v in series[0]["values"]] if series else []


def write(lines):
    for i in range(0, len(lines), 5000):
        req = urllib.request.Request(f"{INFLUX}/write?" + urllib.parse.urlencode({"db": "openhab", "precision": "ns"}),
                                     data="\n".join(lines[i:i + 5000]).encode(), method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            assert resp.status == 204, resp.status


faikin = query('SELECT value FROM "faikout_perfera_power"')
switch = query('SELECT value FROM "faikout_perfera_switch"')
first_real = query('SELECT value FROM "e_car_power" ORDER BY time ASC LIMIT 1')[0][0]
assert not query('SELECT value FROM "e_car_energy_today" WHERE time < now() - 1d'), "past energy points exist"
start = faikin[0][0]
ft, st = [t for t, _ in faikin], [t for t, _ in switch]


def last(times, series, t, default):
    i = bisect.bisect_right(times, t) - 1
    return series[i][1] if i >= 0 and series[i][1] is not None else default


power = []
day = datetime.timedelta(days=7).total_seconds() * 1e9
a = start
while a < first_real:
    b = min(first_real, int(a + day))
    for t, plug in query(f'SELECT value FROM "air_conditioning_power" WHERE time >= {a} AND time < {b}'):
        if plug is None:
            continue
        rest = max(0.0, plug - last(ft, faikin, t, 0))
        on = last(st, switch, t, 0) in (1, "ON", True)
        power.append((t, 0.0 if on and rest < 300 else round(rest, 2)))
    a = b

# per local day: integrate the step function; today is left to the rule
today = datetime.datetime.now(TZ).date()
energy = {}
for (t, v), (t2, _) in zip(power, power[1:] + [(first_real, None)]):
    d0 = datetime.datetime.fromtimestamp(t / 1e9, TZ)
    while t < t2:
        next_midnight = datetime.datetime.combine(d0.date() + datetime.timedelta(days=1), datetime.time(), TZ)
        cut = min(t2, int(next_midnight.timestamp() * 1e9))
        energy[d0.date()] = energy.get(d0.date(), 0) + v * (cut - t) / 1e9 / 3600 / 1000
        t, d0 = cut, next_midnight
lines = [f"e_car_power,item=e_car_power value={v!r} {t}" for t, v in power]
total, days = 0.0, []
for d in sorted(energy):
    if d >= today:
        continue
    total += energy[d]
    ts0 = int(datetime.datetime.combine(d, datetime.time(), TZ).timestamp() * 1e9)
    ts1 = int(datetime.datetime.combine(d, datetime.time(23, 59, 59), TZ).timestamp() * 1e9)
    lines += [f"e_car_energy_today,item=e_car_energy_today value=0.0 {ts0}",
              f"e_car_energy_today,item=e_car_energy_today value={round(energy[d], 3)!r} {ts1}",
              f"e_car_energy_total,item=e_car_energy_total value={round(total, 3)!r} {ts1}"]
    days.append((d.isoformat(), round(energy[d], 2)))
print(f"{len(power)} power points from {datetime.datetime.fromtimestamp(start / 1e9, TZ):%Y-%m-%d %H:%M} "
      f"to {datetime.datetime.fromtimestamp(first_real / 1e9, TZ):%Y-%m-%d %H:%M}, {len(days)} past days, total {total:.1f} kWh")
print("biggest days:", sorted(days, key=lambda x: -x[1])[:6])
print("last days:", days[-5:])
if sys.argv[1] == "apply":
    write(lines)
    print("written", len(lines), "points")
