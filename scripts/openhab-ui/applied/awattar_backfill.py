#!/usr/bin/env python3
"""Backfill market-gross, total-net and total-gross history from epex_spot_awattar (market-net).

Uses the aWATTar binding's formulas (AwattarApi): gross market = net * vat;
net total = (net + base) + |net + base| * fee; gross total = net total * vat.
Only points older than the first point the binding wrote into each target measurement are written.

Usage: awattar_backfill.py check|apply
"""
import json
import sys
import urllib.parse
import urllib.request

INFLUX = "http://127.0.0.1:8086"
DB = "openhab"
VAT = 1.20
FEE = 0.03
BASE = 0.01456311  # EUR/kWh, same as the bridge's basePrice 1.456311 ct

TARGETS = {
    "epex_spot_awattar_market_gross": lambda p: p * VAT,
    "epex_spot_awattar_total_net": lambda p: (p + BASE) + abs(p + BASE) * FEE,
    "epex_spot_awattar_total_gross": lambda p: ((p + BASE) + abs(p + BASE) * FEE) * VAT,
}


def query(q):
    url = f"{INFLUX}/query?" + urllib.parse.urlencode({"db": DB, "epoch": "ns", "q": q})
    result = json.load(urllib.request.urlopen(url))["results"][0]
    series = result.get("series", [])
    return series[0]["values"] if series else []


def write(lines):
    req = urllib.request.Request(f"{INFLUX}/write?" + urllib.parse.urlencode({"db": DB, "precision": "ns"}),
                                 data="\n".join(lines).encode(), method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        assert resp.status == 204, resp.status


def main():
    apply = sys.argv[1] == "apply"
    for measurement, formula in TARGETS.items():
        first = query(f'SELECT first(value) FROM "{measurement}"')
        assert first, f"{measurement} has no points yet; start openHAB first"
        cutoff = first[0][0]
        existing = query(f'SELECT count(value) FROM "{measurement}" WHERE time < {cutoff}')
        assert not existing or existing[0][1] == 0, f"{measurement} already has points before its first binding point"
        source = query(f'SELECT value FROM "epex_spot_awattar" WHERE time < {cutoff}')
        lines = [f"{measurement},item={measurement} value={formula(v)!r} {t}" for t, v in source if v is not None]
        print(f"{measurement}: cutoff={cutoff} points={len(lines)} sample={lines[-1] if lines else None}")
        if apply:
            for i in range(0, len(lines), 10000):
                write(lines[i:i + 10000])
            print(f"  written {len(lines)}")


main()
