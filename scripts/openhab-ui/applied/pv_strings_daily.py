#!/usr/bin/env python3
"""Each string's generation per day (user, 2026-10-20), for the east modules' estimate on the Photovoltaik page:
string 1 (east) has no optimizers, so its share of the optimizers' lifetime counters is estimated by the strings'
measured ratio (rule huawei_optimizers). energy_daily_pv1_generation and energy_daily_pv2_generation, one point per
day at 23:59:59 as the other daily totals: rule energy_daily_totals takes them from photovoltaics_pv1_generation_day
and photovoltaics_pv2_generation_day (rule photovoltaics_energy_day, pv_energy_day.py), two pairs set into its list
here. apply also fills the days from 30 September 2024 to yesterday from the strings' power readings, read through
openHAB's persistence REST API and integrated per day as InfluxDB's integral() does (trapezoids between the readings,
a segment across midnight split there; equal timestamps overwrite, so a second run replaces the first); check prints
how far their sum lies from energy_daily_pv_generation.
Usage: pv_strings_daily.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "i18n"))
from de_labels import RULE_DESCRIPTIONS  # noqa: E402

BASE = "http://127.0.0.1:8080/rest"
TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
TZ = ZoneInfo("Europe/Vienna")
FIRST = datetime.date(2024, 9, 30)
UID = "energy_daily_totals"
ITEMS = {f"energy_daily_pv{n}_generation": {"type": "Number:Energy", "name": f"energy_daily_pv{n}_generation",
                                            "label": f"Energie täglich PV{n}-Erzeugung", "category": "material:bar_chart",
                                            "tags": [], "groupNames": []} for n in (1, 2)}
METADATA = {"unit": {"value": "kWh"}, "stateDescription": {"value": " ", "config": {"pattern": "%.2f %unit%"}}}
ANCHOR = """  ['photovoltaics_generation_day', 'energy_daily_pv_generation'],
"""
PAIRS = """  // each string's generation, for the east modules' estimate (user, 2026-10-20)
  ['photovoltaics_pv1_generation_day', 'energy_daily_pv1_generation'],
  ['photovoltaics_pv2_generation_day', 'energy_daily_pv2_generation'],
"""


def call(method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, method=method, data=data,
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode()
            return r.status, json.loads(text) if text.startswith(("{", "[")) else text
    except urllib.error.HTTPError as e:
        return e.code, None


def iso(t):
    return datetime.datetime.fromtimestamp(t, TZ).isoformat(timespec="milliseconds")


def readings(item, a, b):
    """an item's readings from a to b (epoch seconds), with the one before and the one after"""
    q = urllib.parse.urlencode({"serviceId": "influxdb", "starttime": iso(a), "endtime": iso(b), "boundary": "true"})
    status, d = call("GET", f"/persistence/items/{item}?{q}")
    assert status == 200, (item, status)
    return [(r["time"] / 1000, float(r["state"])) for r in d.get("data", [])]


def energy(points, a, b):
    """kWh within [a, b) from power readings in W: the trapezoids between consecutive readings, cut at a and b"""
    total = 0.0
    for (t1, v1), (t2, v2) in zip(points, points[1:]):
        lo, hi = max(t1, a), min(t2, b)
        if t2 > t1 and lo < hi:
            va = v1 + (v2 - v1) * (lo - t1) / (t2 - t1)
            vb = v1 + (v2 - v1) * (hi - t1) / (t2 - t1)
            total += (va + vb) / 2 * (hi - lo) / 3600 / 1000
    return total


def midnight(d):
    return int(datetime.datetime.combine(d, datetime.time(), TZ).timestamp())


def history():
    """{day: (string 1's kWh, string 2's)} from FIRST to yesterday"""
    out, d = {}, FIRST
    today = datetime.datetime.now(TZ).date()
    while d < today:
        a, b = midnight(d), midnight(d + datetime.timedelta(days=1))
        out[d] = tuple(energy(readings(f"huawei_inverter_pv{n}_power", a, b - 0.001), a, b) for n in (1, 2))
        d += datetime.timedelta(days=1)
    return out


apply = sys.argv[1] == "apply"
for name in ITEMS:
    status, item = call("GET", f"/items/{name}")
    print(f"item {name}:", f"exists, state {item['state']}" if status == 200 else "missing")
status, rule = call("GET", f"/rules/{UID}")
assert status == 200, f"rule {UID} missing"
script = rule["actions"][0]["configuration"]["script"]
patched = "energy_daily_pv1_generation" in script
assert patched or script.count(ANCHOR) == 1, "anchor not found in the rule"
print(f"rule {UID}:", "has the strings" if patched else "gets the strings")
days = history()
q = urllib.parse.urlencode({"serviceId": "influxdb", "starttime": iso(midnight(FIRST)),
                            "endtime": iso(midnight(max(days) + datetime.timedelta(days=1)))})
both = {datetime.datetime.fromtimestamp(r["time"] / 1000, TZ).date(): float(r["state"])
        for r in call("GET", f"/persistence/items/energy_daily_pv_generation?{q}")[1]["data"]}
common = [d for d in days if d in both]
worst = max(common, key=lambda d: abs(sum(days[d]) - both[d]))
print(f"history: {len(days)} days, {min(days)} to {max(days)}; string 1 {sum(v[0] for v in days.values()):.0f} kWh, "
      f"string 2 {sum(v[1] for v in days.values()):.0f}; against energy_daily_pv_generation on {len(common)} days: "
      f"{sum(sum(days[d]) for d in common):.0f} against {sum(both[d] for d in common):.0f} kWh, the largest day apart "
      f"{worst} {sum(days[worst]):.2f} against {both[worst]:.2f}")
if apply:
    for name, item in ITEMS.items():
        print(f"item {name} PUT", call("PUT", f"/items/{name}", item)[0])
        for namespace, meta in METADATA.items():
            call("PUT", f"/items/{name}/metadata/{namespace}", meta)
    if not patched:
        rule["actions"][0]["configuration"]["script"] = script.replace(ANCHOR, ANCHOR + PAIRS)
    rule["description"] = RULE_DESCRIPTIONS[UID]
    rule.pop("status", None)
    rule.pop("editable", None)
    print(f"rule {UID} PUT", call("PUT", f"/rules/{UID}", rule)[0])
    n = 0
    for d, values in sorted(days.items()):
        end = datetime.datetime.combine(d, datetime.time(23, 59, 59), TZ).isoformat(timespec="milliseconds")
        for k, kwh in enumerate(values, 1):
            q = urllib.parse.urlencode({"serviceId": "influxdb", "time": end, "state": f"{kwh:.3f} kWh"})
            status = call("PUT", f"/persistence/items/energy_daily_pv{k}_generation?{q}")[0]
            assert status == 200, (d, k, status)
            n += 1
    print(f"history written through openHAB: {n} points")
    print(f"rule {UID} runnow", call("POST", f"/rules/{UID}/runnow", {})[0])
