#!/usr/bin/env python3
"""The history of skoda_enyaq_km_today (user, 2026-11-09): the km driven per day as one point per day at 23:59:59, as
the rule skoda_enyaq_status writes it since, from the odometer's own InfluxDB history where it has one (since
2026-10-25) and before that from the trips in skoda_trips (their odometer at the start and at the end). A day's km are
its last reading less the last one before it; days without a kilometre get no point. Up to yesterday: today is the
rule's. A point at a day's 23:59:59 is replaced, so a second run writes the same.
Usage: skoda_km_history.py check|apply   (on homepi, as pi; the REST token from ~/.openhab_token, never printed)"""
import collections
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Vienna")
REST = "http://127.0.0.1:8080/rest"
INFLUX = "http://127.0.0.1:8086/query?db=openhab&epoch=ms&q="
ITEM = "skoda_enyaq_km_today"
ODOMETER = "skoda_enyaq_odometer"
TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()


def influx(query):
    with urllib.request.urlopen(INFLUX + urllib.parse.quote(query), timeout=60) as r:
        result = json.load(r)["results"][0]
    if "error" in result:
        sys.exit(f"InfluxDB: {result['error']}")
    series = (result.get("series") or [{"columns": [], "values": []}])[0]
    return [dict(zip(series["columns"], v)) for v in series["values"]]


def store(epoch_ms, km):
    stamp = dt.datetime.fromtimestamp(epoch_ms / 1000, TZ).isoformat(timespec="milliseconds")
    query = urllib.parse.urlencode({"serviceId": "influxdb", "time": stamp, "state": f"{km} km"})
    req = urllib.request.Request(f"{REST}/persistence/items/{ITEM}?{query}", method="PUT",
                                 headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def readings():
    """(ms, km) of the odometer: its own history, and before its first reading the trips' odometer at start and end"""
    own = [(r["time"], r["value"]) for r in influx(f'SELECT value FROM "{ODOMETER}"') if r["value"] is not None]
    first_own = min((t for t, _ in own), default=None)
    trips = []
    for r in influx('SELECT odoStart, odoEnd, "end" FROM skoda_trips'):
        if first_own is not None and r["time"] >= first_own:
            continue
        if isinstance(r.get("odoStart"), (int, float)):
            trips.append((r["time"], r["odoStart"]))
        if isinstance(r.get("odoEnd"), (int, float)):
            trips.append((r["end"] if isinstance(r.get("end"), (int, float)) else r["time"], r["odoEnd"]))
    return sorted(trips + own), first_own


def day_km(points):
    """{day: km} from the readings: each day's last reading less the last one before the day"""
    last = collections.OrderedDict()
    for t, v in points:
        last[dt.datetime.fromtimestamp(t / 1000, TZ).date()] = v
    km, before = {}, points[0][1] if points else None
    for day, value in last.items():
        km[day] = max(0, round(value - before))
        before = value
    return km


def main():
    if sys.argv[1:] not in (["check"], ["apply"]):
        sys.exit(__doc__)
    points, first_own = readings()
    if not points:
        sys.exit("no odometer readings and no trips")
    today = dt.datetime.now(TZ).date()
    km = {d: v for d, v in day_km(points).items() if d < today and v > 0}
    months = collections.Counter()
    for d, v in km.items():
        months[d.strftime("%Y-%m")] += v
    print(f"odometer's own readings from {dt.datetime.fromtimestamp(first_own / 1000, TZ):%Y-%m-%d}" if first_own
          else "no odometer readings of its own")
    print(f"{len(km)} days with km, {sum(km.values())} km, from {min(km)} to {max(km)}")
    print("per month:", ", ".join(f"{m} {v}" for m, v in sorted(months.items())))
    stored = influx(f'SELECT count(value) FROM "{ITEM}"')
    print(f"{ITEM} points stored now: {stored[0]['count'] if stored else 0}")
    if sys.argv[1] != "apply":
        return
    codes = collections.Counter()
    for d, v in sorted(km.items()):
        end = int(dt.datetime.combine(d, dt.time(23, 59, 59), TZ).timestamp() * 1000)
        codes[store(end, v)] += 1
    print("written:", dict(codes))


main()
