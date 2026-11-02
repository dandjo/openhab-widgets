#!/usr/bin/env python3
"""The finished months of grid_peak_monthly in openHAB's form, as grid_peak_daily has its days (user, 2026-11-02: the
values as numbers; grid_peak_monthly a Number:Power item): every point without the tag item is written anew with
item=grid_peak_monthly and its peak as value (kw before; a month without a record gets none), m, t and days kept;
every point compared, then the old series dropped. A further run changes nothing.
Usage: grid_peak_monthly_format.py check|apply   (on homepi; InfluxDB on 127.0.0.1:8086 without a login)"""
import json
import sys
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8086"
M = "grid_peak_monthly"


def influx(q, post=False):
    data = urllib.parse.urlencode({"db": "openhab", "epoch": "ms", "q": q})
    req = (urllib.request.Request(BASE + "/query", data=data.encode(), method="POST") if post
           else urllib.request.Request(BASE + "/query?" + data))
    result = json.load(urllib.request.urlopen(req, timeout=120))["results"][0]
    if "error" in result:
        sys.exit(f"InfluxDB: {result['error']}")
    return result.get("series", [])


def points():
    """(old, new): {month key: (time, value, t, days)} of the series without and with the tag item."""
    old, new = {}, {}
    for s in influx(f'SELECT * FROM "{M}" GROUP BY *'):
        tags = s.get("tags", {})
        for v in s["values"]:
            row = dict(zip(s["columns"], v))
            if tags.get("item", "") == "":
                peak = row.get("kw") if row["days"] != "[]" else None
                old[tags["m"]] = (row["time"], peak, row["t"], row["days"])
            else:
                new[tags["m"]] = (row["time"], row.get("value"), row["t"], row["days"])
    return old, new


def line(key, p):
    time, value, t, days = p
    text = days.replace("\\", "\\\\").replace('"', '\\"')
    return f'{M},item={M},m={key} ' + (f"value={value}," if value is not None else "") + f't={t}i,days="{text}" {time}'


def main():
    if sys.argv[1:2] not in (["check"], ["apply"]):
        sys.exit(__doc__)
    old, new = points()
    print(f"old form: {len(old)} months, openHAB's form: {len(new)} months")
    if not old or sys.argv[1] == "check":
        return
    missing = [k for k, p in old.items() if new.get(k) != p]
    if missing:
        body = "\n".join(line(k, old[k]) for k in sorted(missing)).encode()
        req = urllib.request.Request(f"{BASE}/write?db=openhab&precision=ms", data=body, method="POST",
                                     headers={"Content-Type": "text/plain"})
        with urllib.request.urlopen(req, timeout=60) as r:
            if r.status != 204:
                sys.exit(f"InfluxDB answered {r.status}")
        print(f"written: {len(missing)} months")
        old, new = points()
    differ = [k for k, p in old.items() if new.get(k) != p]
    if differ:
        sys.exit(f"{len(differ)} months differ, the old form kept")
    print(f"all {len(old)} months alike in openHAB's form")
    influx(f"DROP SERIES FROM \"{M}\" WHERE \"item\" = ''", post=True)
    old, new = points()
    print(f"old series dropped: old form {len(old)}, openHAB's form {len(new)} months")


main()
