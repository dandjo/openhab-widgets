#!/usr/bin/env python3
"""One-off correction of the Enyaq's charge history in InfluxDB (user, 2026-10-25), after the meaning of the two charge
items was settled: skoda_enyaq_charge_limit is the value set in the car that it charges to, skoda_enyaq_charge_target
the care target Škoda sets it back to after a charge with battery care on (80 %).
- skoda_enyaq_battery_care_target, an item for the care target that turned out to be the charge target, is dropped.
- skoda_enyaq_charge_limit: its points of 80 % before the correction came from a wrong cap by the care target; the car
  had 100 % set, so they become 100 %.
- skoda_enyaq_charge_target: its points before its first point as the care target (the first 80 %) held the set value
  (100 %, a commanded 90 %); battery care was on all day, so they become 80 %.
Points are rewritten in place: same measurement, tag and timestamp, new value.
Usage: skoda_enyaq_history.py check|apply   (on homepi, as pi)"""
import json
import sys
import urllib.parse
import urllib.request

INFLUX = "http://127.0.0.1:8086"
DB = "openhab"
DROPPED = "skoda_enyaq_battery_care_target"
LIMIT = "skoda_enyaq_charge_limit"
TARGET = "skoda_enyaq_charge_target"
CARE_TARGET = 80


def query(q, method="GET"):
    params = {"db": DB, "epoch": "ns", "q": q}
    if method == "GET":
        req = urllib.request.Request(f"{INFLUX}/query?" + urllib.parse.urlencode(params))
    else:
        req = urllib.request.Request(f"{INFLUX}/query", data=urllib.parse.urlencode(params).encode(), method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)["results"][0]


def points(measurement):
    series = query(f'SELECT "item", "value" FROM "{measurement}"').get("series", [])
    return [tuple(v) for v in series[0]["values"]] if series else []


def write(lines):
    req = urllib.request.Request(f"{INFLUX}/write?" + urllib.parse.urlencode({"db": DB, "precision": "ns"}),
                                 data="\n".join(lines).encode(), method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        assert resp.status == 204, resp.status


apply = sys.argv[1] == "apply"
limit, target = points(LIMIT), points(TARGET)
first_care = next((t for t, _, v in target if v == CARE_TARGET), None)
assert first_care is not None, "the charge target has no care target point yet: apply skoda_enyaq.py first"
limit_fix = [(t, item, 100) for t, item, v in limit if v == CARE_TARGET and t < first_care]
target_fix = [(t, item, CARE_TARGET) for t, item, v in target if t < first_care and v != CARE_TARGET]
dropped = points(DROPPED)
print(f"{DROPPED}: {len(dropped)} points to drop")
print(f"{LIMIT}: {len(limit_fix)} points 80 -> 100 before the first care target point")
print(f"{TARGET}: {len(target_fix)} points -> {CARE_TARGET} before the first care target point")
if apply:
    if dropped:
        query(f'DROP MEASUREMENT "{DROPPED}"', method="POST")
        print(f"{DROPPED} dropped")
    lines = [f'{LIMIT},item={item} value={value} {t}' for t, item, value in limit_fix] + \
            [f'{TARGET},item={item} value={value} {t}' for t, item, value in target_fix]
    if lines:
        write(lines)
        print(f"{len(lines)} points rewritten")
