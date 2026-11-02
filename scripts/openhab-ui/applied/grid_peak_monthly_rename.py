#!/usr/bin/env python3
"""The finished months of the grid peaks take the name grid_peak_monthly, beside grid_peak_daily (user, 2026-11-02:
"grid_peak_months soll grid_peak_monthly werden"): the InfluxDB measurement grid_peak_months is copied point by point
into grid_peak_monthly (tags kept: SELECT INTO with GROUP BY *), every point compared, and the old measurement dropped
only once the live rule grid_peaks no longer names it, so a run of the old rule cannot work the months out again.
Run apply before grid_peaks.py apply (copies) and after it (drops); a further run changes nothing.
Usage: grid_peak_monthly_rename.py check|apply   (on homepi; InfluxDB on 127.0.0.1:8086 without a login, the API token
from ~/.openhab_token, never printed)"""
import json
import os
import sys
import urllib.parse
import urllib.request

INFLUX = "http://127.0.0.1:8086/query"
OLD, NEW = "grid_peak_months", "grid_peak_monthly"
RULE = "http://127.0.0.1:8080/rest/rules/grid_peaks"


def influx(q, post=False):
    data = urllib.parse.urlencode({"db": "openhab", "epoch": "ms", "q": q})
    req = (urllib.request.Request(INFLUX, data=data.encode(), method="POST") if post
           else urllib.request.Request(INFLUX + "?" + data))
    result = json.load(urllib.request.urlopen(req, timeout=120))["results"][0]
    if "error" in result:
        sys.exit(f"InfluxDB: {result['error']}")
    return result.get("series", [])


def points(measurement):
    """{month key: (time, days, kw, t)} of a measurement."""
    out = {}
    for s in influx(f'SELECT * FROM "{measurement}" GROUP BY *'):
        cols = s["columns"]
        for v in s["values"]:
            row = dict(zip(cols, v))
            out[s["tags"]["m"]] = (row["time"], row["days"], row["kw"], row["t"])
    return out


def rule_names_old():
    token = open(os.path.expanduser("~/.openhab_token")).read().strip()
    req = urllib.request.Request(RULE, headers={"Authorization": "Bearer " + token})
    rule = json.load(urllib.request.urlopen(req, timeout=30))
    return any(OLD + "'" in a["configuration"].get("script", "") or OLD + '"' in a["configuration"].get("script", "")
               for a in rule["actions"])


def main():
    if sys.argv[1:2] not in (["check"], ["apply"]):
        sys.exit(__doc__)
    old, new = points(OLD), points(NEW)
    print(f"{OLD}: {len(old)} months, {NEW}: {len(new)} months")
    if not old:
        print("nothing to rename")
        return
    if sys.argv[1] == "check":
        print("the live rule names", OLD if rule_names_old() else NEW)
        return
    if any(new.get(k) != v for k, v in old.items()):
        influx(f'SELECT * INTO "{NEW}" FROM "{OLD}" GROUP BY *', post=True)
        new = points(NEW)
        print(f"copied: {NEW} has {len(new)} months")
    differ = [k for k, v in old.items() if new.get(k) != v]
    if differ:
        sys.exit(f"{len(differ)} months differ after the copy, {OLD} kept")
    print(f"all {len(old)} months alike in {NEW}")
    if rule_names_old():
        print(f"the live rule still names {OLD}: kept until grid_peaks.py apply, then run this again")
        return
    influx(f'DROP MEASUREMENT "{OLD}"', post=True)
    print(f"{OLD} dropped")


main()
