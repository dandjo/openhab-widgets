#!/usr/bin/env python3
"""Rebuild the whole series of espaltherma_ext_ambient_temp_avg (see outdoor_avg.py) from its source's history: the
exponential mean of espaltherma_ext_ambient_temp's 1-minute means (carried forward through gaps, as averageSince holds
a state), to a tenth as the rule writes it, time constant the hours of the item's metadata 'averaging', one point per quarter hour (UTC) from a week
after the source's first point up to now. apply disables the rule, deletes the series, writes it, enables the rule and
runs it, so it carries on from the last point written.
Usage: outdoor_avg_backfill.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

INFLUX, DB, REST = "http://127.0.0.1:8086", "openhab", "http://127.0.0.1:8080/rest"
SOURCE, TARGET, RULE = "espaltherma_ext_ambient_temp", "espaltherma_ext_ambient_temp_avg", "heatpump_outdoor_average"
MIN, QUARTER, CHUNK, WARMUP = 60, 900, 30 * 86400, 7 * 86400
TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()


def query(q, write=False):
    """An InfluxQL query's first series; write: a POST, as DELETE needs (over a whole history it goes through every
    weekly shard, ~5 min for two years, hence the long timeout)."""
    params = urllib.parse.urlencode({"db": DB, "epoch": "s", "q": q})
    req = urllib.request.Request(f"{INFLUX}/query", data=params.encode(), method="POST") if write else \
        f"{INFLUX}/query?{params}"
    series = json.load(urllib.request.urlopen(req, timeout=3600))["results"][0].get("series", [])
    return series[0]["values"] if series else []


def rest(method, path, body, content="text/plain"):
    req = urllib.request.Request(REST + path, method=method, data=body.encode(),
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": content})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


item = json.load(urllib.request.urlopen(f"{REST}/items/{TARGET}?metadata=averaging"))
hours = float(item.get("metadata", {}).get("averaging", {}).get("value", 24))
apply = sys.argv[1] == "apply"
if apply:
    print("rule disabled:", rest("POST", f"/rules/{RULE}/enable", "false"))
end = int(time.time()) // MIN * MIN  # up to the last whole minute
start = query(f'SELECT first(value) FROM "{SOURCE}"')[0][0] // MIN * MIN

# the source's 1-minute means, carried forward through gaps, smoothed minute by minute
minutes = {}
t = start
while t < end:
    for ts, v in query(f'SELECT mean(value) FROM "{SOURCE}" WHERE time >= {t}s AND time < {min(t + CHUNK, end)}s '
                       f'GROUP BY time(1m) fill(none)'):
        minutes[ts] = v
    t += CHUNK
alpha = 1 - math.exp(-MIN / (hours * 3600)) if hours > 0 else 1.0
lines, mean, last = [], None, None
for ts in range(start, end, MIN):
    last = minutes.get(ts, last)
    mean = last if mean is None else mean + alpha * (last - mean)
    stamp = ts + MIN  # the mean over the minutes before this moment
    if stamp % QUARTER == 0 and stamp >= start + WARMUP:
        lines.append(f"{TARGET},item={TARGET} value={round(mean, 1)!r} {stamp}")

print(f"averaging {hours:g} h, source from {start}, up to {end}: {len(lines)} points")
print("first", lines[0])
print("last ", lines[-1])
print("now in the series:", query(f'SELECT count(value) FROM "{TARGET}"'))
if apply:
    query(f'DELETE FROM "{TARGET}"', write=True)
    for k in range(0, len(lines), 5000):
        req = urllib.request.Request(f"{INFLUX}/write?" + urllib.parse.urlencode({"db": DB, "precision": "s"}),
                                     data="\n".join(lines[k:k + 5000]).encode(), method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            assert resp.status == 204
    print("written", query(f'SELECT count(value) FROM "{TARGET}"'))
    print("rule enabled:", rest("POST", f"/rules/{RULE}/enable", "true"))
    print("run now:", rest("POST", f"/rules/{RULE}/runnow", "{}", "application/json"))
