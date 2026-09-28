#!/usr/bin/env python3
"""Back-fill energy_daily_self_use: last photovoltaics_own_ec_day value per local day, stamped 23:59:59 local.
Days without that counter fall back to energy_daily_pv - energy_daily_grid_export, which it equals by definition.
Usage: self_use_backfill.py check|apply
"""
import datetime
import json
import sys
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

INFLUX = "http://127.0.0.1:8086"
TZ = ZoneInfo("Europe/Vienna")
TARGET, SOURCE = "energy_daily_self_use", "photovoltaics_own_ec_day"


def query(q):
    url = f"{INFLUX}/query?" + urllib.parse.urlencode({"db": "openhab", "epoch": "ns", "q": q})
    series = json.load(urllib.request.urlopen(url, timeout=120))["results"][0].get("series", [])
    return series[0]["values"] if series else []


def by_day(rows):
    return {datetime.datetime.fromtimestamp(ns / 1e9, TZ).date(): v for ns, v in rows if v is not None}


today = datetime.datetime.now(TZ).date()
existing = by_day(query(f'SELECT value FROM "{TARGET}"'))
assert all(day >= today for day in existing), f"{TARGET} already has past points"
raw = by_day(query(f"SELECT last(value) FROM \"{SOURCE}\" WHERE time >= '2024-09-01T00:00:00Z' "
                   f"GROUP BY time(1d) tz('Europe/Vienna')"))
pv = by_day(query('SELECT value FROM "energy_daily_pv"'))
export = by_day(query('SELECT value FROM "energy_daily_grid_export"'))
lines, fallback, diffs = [], 0, []
for day in sorted(set(pv) | set(raw)):
    if day >= today:
        continue
    derived = pv[day] - export[day] if day in pv and day in export else None
    value = raw.get(day)
    if value is None:
        value, fallback = derived, fallback + 1
    elif derived is not None and abs(value - derived) > 0.05:
        diffs.append((day, round(value, 3), round(derived, 3)))
    if value is None:
        continue
    end = datetime.datetime.combine(day, datetime.time(23, 59, 59), TZ)
    lines.append(f"{TARGET},item={TARGET} value={round(max(0.0, value), 3)!r} {int(end.timestamp())}")
print(f"{len(lines)} days, {fallback} from pv - export, first={lines[0] if lines else None}")
print(f"{len(diffs)} days where the counter and pv - export differ by more than 0.05 kWh: {diffs[:8]}")
if sys.argv[1] == "apply":
    for i in range(0, len(lines), 5000):
        req = urllib.request.Request(f"{INFLUX}/write?" + urllib.parse.urlencode({"db": "openhab", "precision": "s"}),
                                     data="\n".join(lines[i:i + 5000]).encode(), method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            assert resp.status == 204, resp.status
    print("written")
