#!/usr/bin/env python3
"""Back-fill the 15-minute temperature means for the last 7 days (stamped at the end of each quarter hour)."""
import json, sys, urllib.parse, urllib.request
INFLUX, DB = "http://127.0.0.1:8086", "openhab"
PAIRS = [("temperature_indoor_15min", "espaltherma_indoor_ambient_temp"),
         ("temperature_outdoor_15min", "espaltherma_ext_ambient_temp")]


def query(q):
    url = f"{INFLUX}/query?" + urllib.parse.urlencode({"db": DB, "epoch": "s", "q": q})
    series = json.load(urllib.request.urlopen(url, timeout=120))["results"][0].get("series", [])
    return series[0]["values"] if series else []


for target, source in PAIRS:
    existing = query(f'SELECT count(value) FROM "{target}"')
    assert not existing or existing[0][1] == 0, f"{target} already has points"
    rows = query(f'SELECT mean(value) FROM "{source}" WHERE time > now() - 7d AND time < now() - 15m GROUP BY time(15m) fill(none)')
    lines = [f"{target},item={target} value={round(v, 1)!r} {t + 900}" for t, v in rows if v is not None]
    print(target, len(lines), lines[-1] if lines else None)
    if sys.argv[1] == "apply":
        req = urllib.request.Request(f"{INFLUX}/write?" + urllib.parse.urlencode({"db": DB, "precision": "s"}),
                                     data="\n".join(lines).encode(), method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            assert resp.status == 204
        print("  written")
