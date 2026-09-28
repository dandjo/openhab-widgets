#!/usr/bin/env python3
"""Back-fill the energy_daily_* items: last value of each day counter per local day, stamped 23:59:59 local.

Usage: daily_backfill.py check|apply
"""
import datetime
import json
import sys
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

INFLUX = "http://127.0.0.1:8086"
DB = "openhab"
TZ = ZoneInfo("Europe/Vienna")
PAIRS = [
    ("energy_daily_pv", "huawei_inverter_e_day"),
    ("energy_daily_home", "home_ec_day"),
    ("energy_daily_grid_import", "huawei_inverter_power_meter_ec_day"),
    ("energy_daily_grid_export", "huawei_inverter_power_meter_ep_day"),
]


def query(q):
    url = f"{INFLUX}/query?" + urllib.parse.urlencode({"db": DB, "epoch": "ns", "q": q})
    series = json.load(urllib.request.urlopen(url, timeout=120))["results"][0].get("series", [])
    return series[0]["values"] if series else []


def write(lines):
    req = urllib.request.Request(f"{INFLUX}/write?" + urllib.parse.urlencode({"db": DB, "precision": "s"}),
                                 data="\n".join(lines).encode(), method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        assert resp.status == 204, resp.status


def main():
    apply = sys.argv[1] == "apply"
    today = datetime.datetime.now(TZ).date()
    for target, source in PAIRS:
        existing = query(f'SELECT count(value) FROM "{target}"')
        assert not existing or existing[0][1] == 0, f"{target} already has points"
        rows = query(f'SELECT last(value) FROM "{source}" WHERE time >= \'2024-09-01T00:00:00Z\' '
                     f"GROUP BY time(1d) tz('Europe/Vienna')")
        lines = []
        for ns, value in rows:
            day = datetime.datetime.fromtimestamp(ns / 1e9, TZ).date()
            if value is None or day >= today:
                continue
            end = datetime.datetime.combine(day, datetime.time(23, 59, 59), TZ)
            lines.append(f"{target},item={target} value={round(value, 3)!r} {int(end.timestamp())}")
        print(f"{target} <- {source}: {len(lines)} days, first={lines[0] if lines else None}, last={lines[-1] if lines else None}")
        if apply:
            for i in range(0, len(lines), 5000):
                write(lines[i:i + 5000])
            print("  written")


main()
