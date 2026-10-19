#!/usr/bin/env python3
"""The day's PV generation, for the Photovoltaik page's yield per day beside the forecast (user, 2026-10-19: the bars
show what the modules generated, the forecast beside them). The inverter's daily yield (huawei_inverter_e_day, kept
as energy_daily_pv) is no measure of it: it counts the battery's discharge and leaves out what the strings charge the
battery with, and in winter the battery's grid charge too, so against the strings it ran 0.63 to 10 times a day's
generation (July 2025 to October 2026). energy_daily_pv_generation is the two strings' energy instead (DC, as the forecast is
fitted on them): rule energy_daily_totals writes it with the other daily totals, one point per day at 23:59:59, from
the strings' time-weighted mean power since midnight; apply also fills the days from 30 September 2024 to yesterday
from the strings' hourly integrals in InfluxDB (equal timestamps overwrite, so a second run replaces the first).
Usage: pv_generation.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
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
INFLUX = "http://127.0.0.1:8086"
TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
TZ = ZoneInfo("Europe/Vienna")
UID = "energy_daily_totals"
ITEM = "energy_daily_pv_generation"
DEF = {"type": "Number:Energy", "name": ITEM, "label": "Energie täglich PV-Erzeugung", "category": "material:bar_chart",
       "tags": [], "groupNames": []}
METADATA = {"unit": {"value": "kWh"}, "stateDescription": {"value": " ", "config": {"pattern": "%.2f %unit%"}}}
STRINGS = ("huawei_inverter_pv1_power", "huawei_inverter_pv2_power")
FIRST = datetime.date(2024, 9, 30)
ANCHOR = """  // the day's shares in per cent, as Grafana's panel"""
BLOCK = """  // the day's PV generation: the two strings' energy from their time-weighted mean power since midnight, as the
  // inverter's yield above counts the battery's discharge and leaves out what the strings charge it with
  const midnight = time.toZDT('00:00');
  const hours = time.Duration.between(midnight, time.toZDT()).toMillis() / 3600000;
  const strings = ['huawei_inverter_pv1_power', 'huawei_inverter_pv2_power']
    .map((name) => items.getItem(name).persistence.averageSince(midnight, 'influxdb'));
  if (strings.every((s) => s !== null && s !== undefined && s.numericState !== null)) {
    const state = Quantity((strings.reduce((sum, s) => sum + s.numericState, 0) * hours / 1000).toFixed(3) + ' kWh');
    items.getItem('energy_daily_pv_generation').postUpdate(state);
    items.getItem('energy_daily_pv_generation').persistence.persist(endOfDay, state, 'influxdb');
  }
"""


def call(method, path, body=None, content="application/json"):
    data = None if body is None else (body if isinstance(body, str) else json.dumps(body)).encode()
    req = urllib.request.Request(BASE + path, method=method, data=data,
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": content})
    try:
        with urllib.request.urlopen(req) as r:
            text = r.read().decode()
            return r.status, json.loads(text) if text.startswith(("{", "[")) else text
    except urllib.error.HTTPError as e:
        return e.code, None


def influx(query):
    url = f"{INFLUX}/query?db=openhab&epoch=s&q=" + urllib.parse.quote(query)
    with urllib.request.urlopen(url) as r:
        series = json.load(r)["results"][0].get("series", [])
    return series[0]["values"] if series else []


def history():
    """Each day's generation in kWh from the strings' hourly integrals (hours fit local days in both offsets)."""
    start = datetime.datetime.combine(FIRST, datetime.time(), TZ)
    end = datetime.datetime.combine(datetime.datetime.now(TZ).date(), datetime.time(), TZ)
    days = {}
    for item in STRINGS:
        for t, kwh in influx(f"SELECT integral(value, 1h) / 1000 FROM {item} WHERE time >= {int(start.timestamp())}s "
                             f"AND time < {int(end.timestamp())}s GROUP BY time(1h)"):
            if kwh is not None:
                d = datetime.datetime.fromtimestamp(t, TZ).date()
                days[d] = days.get(d, 0) + kwh
    return days


apply = sys.argv[1] == "apply"
status, item = call("GET", f"/items/{ITEM}")
print(f"item {ITEM}:", f"exists, state {item['state']}" if status == 200 else "missing")
status, rule = call("GET", f"/rules/{UID}")
assert status == 200, f"rule {UID} missing"
script = rule["actions"][0]["configuration"]["script"]
patched = "energy_daily_pv_generation" in script
assert patched or script.count(ANCHOR) == 1, "anchor not found in the rule"
print(f"rule {UID}:", "has the generation" if patched else "gets the generation")
days = history()
print(f"history: {len(days)} days, {min(days)} to {max(days)}, e.g. "
      + ", ".join(f"{d} {days[d]:.2f}" for d in sorted(days)[-3:]))
if apply:
    print(f"item {ITEM} PUT", call("PUT", f"/items/{ITEM}", DEF)[0])
    for namespace, meta in METADATA.items():
        print(f"  metadata {namespace} PUT", call("PUT", f"/items/{ITEM}/metadata/{namespace}", meta)[0])
    if not patched:
        rule["actions"][0]["configuration"]["script"] = script.replace(ANCHOR, BLOCK + ANCHOR)
    rule["description"] = RULE_DESCRIPTIONS[UID]
    rule.pop("status", None)
    rule.pop("editable", None)
    print(f"rule {UID} PUT", call("PUT", f"/rules/{UID}", rule)[0])
    lines = []
    for d, kwh in sorted(days.items()):
        end = datetime.datetime.combine(d, datetime.time(23, 59, 59), TZ)
        lines.append(f"{ITEM},item={ITEM} value={kwh:.3f} {int(end.timestamp())}")
    req = urllib.request.Request(f"{INFLUX}/write?db=openhab&precision=s", method="POST", data="\n".join(lines).encode())
    with urllib.request.urlopen(req) as r:
        print(f"history written: {len(lines)} days ({r.status})")
    print(f"rule {UID} runnow", call("POST", f"/rules/{UID}/runnow", {})[0])
