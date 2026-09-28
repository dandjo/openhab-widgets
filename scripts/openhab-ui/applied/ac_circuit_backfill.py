#!/usr/bin/env python3
"""History of the air conditioner's own power and energy since 29 May 2026, when Faikin's data and with it the
E-Car's begin: the meter's value minus the car's. The power at every stored point of the car before the first
live point of air_conditioning_unit_power, the energy per local day (0 at 00:00, the day at 23:59:59) and the
total at the end of each day. Before that no split exists and nothing is written.
Usage: ac_circuit_backfill.py check|apply   (with openHAB stopped for apply)"""
import bisect
import datetime
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


def ns(dt):
    return int(dt.timestamp() * 1e9)


first = query('SELECT value FROM "e_car_power" ORDER BY time ASC LIMIT 1')[0][0]
live = query('SELECT value FROM "air_conditioning_unit_power" ORDER BY time ASC LIMIT 1')
until = live[0][0] if live else ns(datetime.datetime.now(TZ))
assert not query(f'SELECT value FROM "air_conditioning_unit_energy_today" LIMIT 1'), "energy points exist already"

# power: meter minus car at every car point before the live series starts
lines, n_power = [], 0
a = first
prev = query(f'SELECT value FROM "air_conditioning_power" WHERE time < {first} ORDER BY time DESC LIMIT 1')
while a < until:
    b = min(until, a + WEEK)
    meter = prev + query(f'SELECT value FROM "air_conditioning_power" WHERE time >= {a} AND time < {b}')
    mt = [t for t, _ in meter]
    for t, car in query(f'SELECT value FROM "e_car_power" WHERE time >= {a} AND time < {b}'):
        i = bisect.bisect_right(mt, t) - 1
        if i < 0 or meter[i][1] is None or car is None:
            continue
        lines.append(f"air_conditioning_unit_power,item=air_conditioning_unit_power "
                     f"value={round(max(0.0, meter[i][1] - car), 2)!r} {t}")
        n_power += 1
    if meter:
        prev = [meter[-1]]
    a = b


def last_in(series, t0, t1):
    """The last value in [t0, t1) of a list of (t, v)."""
    ts = [t for t, _ in series]
    i = bisect.bisect_left(ts, t1) - 1
    return series[i][1] if i >= 0 and series[i][0] >= t0 else None


meter_today = query(f'SELECT value FROM "air_conditioning_energy_today" WHERE time >= {first}')
meter_total = query(f'SELECT value FROM "air_conditioning_energy_total" WHERE time >= {first}')
car_today = query(f'SELECT value FROM "e_car_energy_today" WHERE time >= {first}')
car_total = query(f'SELECT value FROM "e_car_energy_total" WHERE time >= {first}')
day = datetime.datetime.fromtimestamp(first / 1e9, TZ).date()
today = datetime.datetime.now(TZ).date()
days = []
while day < today:
    t0 = ns(datetime.datetime.combine(day, datetime.time(), TZ))
    t1 = ns(datetime.datetime.combine(day + datetime.timedelta(days=1), datetime.time(), TZ))
    end = ns(datetime.datetime.combine(day, datetime.time(23, 59, 59), TZ))
    mday, cday = last_in(meter_today, t0, t1), last_in(car_today, t0, t1)
    mtot, ctot = last_in(meter_total, t0, t1), last_in(car_total, t0, t1)
    if mday is not None and cday is not None:
        unit = round(max(0.0, mday - cday), 3)
        lines += [f"air_conditioning_unit_energy_today,item=air_conditioning_unit_energy_today value=0.0 {t0}",
                  f"air_conditioning_unit_energy_today,item=air_conditioning_unit_energy_today value={unit!r} {end}"]
        days.append((day.isoformat(), round(mday, 2), round(cday, 2), unit))
    if mtot is not None and ctot is not None:
        lines.append(f"air_conditioning_unit_energy_total,item=air_conditioning_unit_energy_total "
                     f"value={round(max(0.0, mtot - ctot), 3)!r} {end}")
    day += datetime.timedelta(days=1)
print(f"power: {n_power} points up to {datetime.datetime.fromtimestamp(until / 1e9, TZ):%Y-%m-%d %H:%M}; "
      f"energy: {len(days)} days")
print("last days (meter, car, air conditioner):", days[-6:])
print("biggest air conditioner days:", sorted(days, key=lambda x: -x[3])[:4])
if sys.argv[1] == "apply":
    write(lines)
    print("written", len(lines), "points")
