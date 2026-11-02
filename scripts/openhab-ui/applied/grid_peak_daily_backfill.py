#!/usr/bin/env python3
"""The days before the rule grid_peaks wrote them (user, 2026-11-02: a calendar of the daily grid peak on the
overview): every day's strongest quarter-hour of the meter's import as the item grid_peak_daily's values in InfluxDB,
one point a day at 23:59:59 local time, as the daily energies have them and as the rule writes the running month; a
quarter is InfluxDB's 15-minute mean of huawei_inverter_power_meter_active_power, in kW, to two decimals, as in
grid_peaks.js. From October 2024, where the meter's record is complete, to the month before the running one;
writing a day again overwrites it, so a second run changes nothing.
Usage: grid_peak_daily_backfill.py check|apply   (on homepi; InfluxDB on 127.0.0.1:8086 without a login)"""
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

Z = ZoneInfo("Europe/Vienna")
INFLUX = "http://127.0.0.1:8086"
GRID = "huawei_inverter_power_meter_active_power"
DAILY = "grid_peak_daily"
FIRST = (2024, 10)
Q = 15 * 60000


def query(q):
    url = f"{INFLUX}/query?" + urllib.parse.urlencode({"db": "openhab", "epoch": "ms", "q": q})
    result = json.load(urllib.request.urlopen(url, timeout=120))["results"][0]
    if "error" in result:
        sys.exit(f"InfluxDB: {result['error']}")
    return result.get("series", [])


def month_days(year, month):
    """{local date: kW} of every day of the month with a quarter."""
    a = datetime(year, month, 1, tzinfo=Z)
    b = datetime(year + month // 12, month % 12 + 1, 1, tzinfo=Z)
    series = query(f'SELECT mean(value) FROM "{GRID}" WHERE time >= {int(a.timestamp() * 1000)}ms AND '
                   f'time < {int(b.timestamp() * 1000)}ms GROUP BY time(15m) fill(none)')
    best = {}
    for t, w in (series[0]["values"] if series else []):
        if w is None:
            continue
        day = datetime.fromtimestamp(t / 1000, Z).date()
        if day not in best or w / 1000 > best[day][1]:
            best[day] = (t, w / 1000)
    return {day: kw for day, (_, kw) in best.items()}


def main():
    if sys.argv[1:2] not in (["check"], ["apply"]):
        sys.exit(__doc__)
    now = datetime.now(Z)
    year, month = FIRST
    total, written = 0, 0
    while (year, month) < (now.year, now.month):
        days = month_days(year, month)
        total += len(days)
        if sys.argv[1] == "apply" and days:
            lines = [f"{DAILY},item={DAILY} value={round(kw, 2)} "
                     f"{int(datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=Z).timestamp() * 1000)}"
                     for d, kw in sorted(days.items())]
            req = urllib.request.Request(f"{INFLUX}/write?db=openhab&precision=ms", data="\n".join(lines).encode(),
                                         method="POST", headers={"Content-Type": "text/plain"})
            with urllib.request.urlopen(req, timeout=60) as r:
                if r.status != 204:
                    sys.exit(f"InfluxDB answered {r.status} for {year}-{month:02d}")
            written += len(lines)
        print(f"{year}-{month:02d}: {len(days)} days" + (f", max {max(days.values()):.2f} kW" if days else ""))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    print(f"days: {total}" + (f", written: {written}" if sys.argv[1] == "apply" else " (check only)"))


main()
