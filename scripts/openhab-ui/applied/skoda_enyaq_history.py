#!/usr/bin/env python3
"""One-off correction of the Enyaq's charge history in InfluxDB (user, 2026-10-25), once the charge items were settled:
skoda_enyaq_charge_target (Ladeziel) is targetStateOfChargeInPercent, the value set in the car that it charges to;
skoda_enyaq_battery_care_target is batteryCareModeTargetValueInPercent; skoda_enyaq_charge_limit is gone.
- The charge target's points from before (written while it held the battery care target) are deleted, and the charge
  limit's points, which held the set value all along (corrected before: its first 80 % became 100 %), are written as
  the charge target's at their own times.
- The charge limit's measurement is dropped.
Run after skoda_enyaq.py apply, which writes the charge target's first point in its new meaning; everything older than
that point is replaced.
Usage: skoda_enyaq_history.py check|apply   (on homepi, as pi)"""
import json
import sys
import urllib.parse
import urllib.request

INFLUX = "http://127.0.0.1:8086"
DB = "openhab"
TARGET = "skoda_enyaq_charge_target"
LIMIT = "skoda_enyaq_charge_limit"


def query(q, method="GET"):
    params = {"db": DB, "epoch": "ns", "q": q}
    if method == "GET":
        req = urllib.request.Request(f"{INFLUX}/query?" + urllib.parse.urlencode(params))
    else:
        req = urllib.request.Request(f"{INFLUX}/query", data=urllib.parse.urlencode(params).encode(), method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)["results"][0]


def points(measurement):
    series = query(f'SELECT "value" FROM "{measurement}"').get("series", [])
    return [tuple(v) for v in series[0]["values"]] if series else []


def write(lines):
    req = urllib.request.Request(f"{INFLUX}/write?" + urllib.parse.urlencode({"db": DB, "precision": "ns"}),
                                 data="\n".join(lines).encode(), method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        assert resp.status == 204, resp.status


apply = sys.argv[1] == "apply"
target, limit = points(TARGET), points(LIMIT)
assert limit, f"{LIMIT} has no points (already done?)"
newest_time, newest_value = target[-1]
# the charge target's newest point must be its first in the new meaning: newer than the limit's history, same value
assert newest_time > limit[-1][0] and newest_value == limit[-1][1], \
    "apply skoda_enyaq.py first, so the charge target has a point in its new meaning"
old = [t for t, _ in target if t < newest_time]
print(f"{TARGET}: {len(old)} older points to replace by the {len(limit)} points of {LIMIT}")
for t, v in limit:
    print("  ", t, v)
if apply:
    query(f'DELETE FROM "{TARGET}" WHERE time < {newest_time}', method="POST")
    write([f"{TARGET},item={TARGET} value={v} {t}" for t, v in limit])
    query(f'DROP MEASUREMENT "{LIMIT}"', method="POST")
    print(f"{TARGET}: replaced; {LIMIT} dropped")
