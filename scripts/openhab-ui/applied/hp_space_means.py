#!/usr/bin/env python3
"""The heat pump's mean powers per day, over the day's 24 hours (23 or 25 when the clocks change): the space heating's
electric and heat power (user, 2026-11-28: "durchschnittliche Stromleistung und Heizleistung (nur Heizung, ohne
Warmwasser) pro Tag") and the hot water's heat power (user, the same day: "zusätzlich durchschnittliche Heizleistung
(nur Warmwasser)"): energy_daily_heatpump_space_electric_mean, energy_daily_heatpump_space_heat_mean and
energy_daily_heatpump_dhw_heat_mean in kW, one point per day at 23:59:59 as the other daily totals. Rule
energy_daily_totals writes them from espaltherma_energy_space_today, espaltherma_heating_energy_space_today and
espaltherma_heating_energy_dhw_today over the hours since midnight, so today's point is the mean so far; the block is
appended to its script here, or replaces the one an earlier run appended. apply also fills the days from 19 October
2024 (the counters' first whole day) to yesterday of each item that lacks them, from each day's last counter reading
in InfluxDB, written through openHAB's persistence REST API (equal timestamps overwrite, so a second run replaces the
first); check prints what it would write.
Usage: hp_space_means.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
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
FIRST = datetime.date(2024, 10, 19)
UID = "energy_daily_totals"
# target item, its label, the day counter it divides
MEANS = [("energy_daily_heatpump_space_electric_mean", "Wärmepumpe Heizung Ø Stromleistung täglich",
          "espaltherma_energy_space_today"),
         ("energy_daily_heatpump_space_heat_mean", "Wärmepumpe Heizung Ø Heizleistung täglich",
          "espaltherma_heating_energy_space_today"),
         ("energy_daily_heatpump_dhw_heat_mean", "Wärmepumpe Warmwasser Ø Heizleistung täglich",
          "espaltherma_heating_energy_dhw_today")]
METADATA = {"unit": {"value": "kW"}, "stateDescription": {"value": " ", "config": {"pattern": "%.3f %unit%"}}}
TAIL = "    });\n}"
# the block's first line, now and as the first run (two items) wrote it
MARKERS = ("\n  // the heat pump's mean powers of the day", "\n  // the space heating's mean electric and heat power")
BLOCK = """
  // the heat pump's mean powers of the day, the space heating's electric and heat power and the hot water's heat power:
  // each energy over the hours since midnight, so over the whole day once it is over (23 or 25 hours when the clocks
  // change) (user, 2026-11-28)
  const hours = time.Duration.between(time.toZDT('00:00'), time.toZDT()).toMillis() / 3600000;
""" + "  [" + ",\n   ".join(f"['{src}', '{item}']" for item, _, src in MEANS) + """].forEach(([source, target]) => {
    const kwh = value(source);
    if (kwh !== null) {
      const state = Quantity((kwh / hours).toFixed(3) + ' kW');
      items.getItem(target).postUpdate(state);
      items.getItem(target).persistence.persist(endOfDay, state, 'influxdb');
    }
  });
}"""


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


def query(q):
    url = f"{INFLUX}/query?" + urllib.parse.urlencode({"db": "openhab", "epoch": "ns", "q": q})
    series = json.load(urllib.request.urlopen(url, timeout=120))["results"][0].get("series", [])
    return series[0]["values"] if series else []


def midnight(d):
    return datetime.datetime.combine(d, datetime.time(), TZ)


def history(source):
    """{day: mean kW} from FIRST to yesterday: the day's last counter reading over the day's hours"""
    today = datetime.datetime.now(TZ).date()
    rows = query(f"SELECT last(value) FROM \"{source}\" WHERE time >= '{midnight(FIRST).isoformat()}' "
                 f"AND time < '{midnight(today).isoformat()}' GROUP BY time(1d) tz('Europe/Vienna')")
    out = {}
    for ns, kwh in rows:
        day = datetime.datetime.fromtimestamp(ns / 1e9, TZ).date()
        if kwh is None or not FIRST <= day < today:
            continue
        hours = (midnight(day + datetime.timedelta(days=1)) - midnight(day)).total_seconds() / 3600
        out[day] = kwh / hours
    return out


apply = sys.argv[1:] == ["apply"]
if sys.argv[1:] not in (["check"], ["apply"]):
    sys.exit(__doc__)
exists = {}
for name, _, _ in MEANS:
    status, item = call("GET", f"/items/{name}")
    exists[name] = status == 200
    print(f"item {name}:", f"exists, state {item['state']}" if status == 200 else "missing")
status, rule = call("GET", f"/rules/{UID}")
assert status == 200, f"rule {UID} missing"
script = rule["actions"][0]["configuration"]["script"]
found = [m for m in MARKERS if script.count(m) == 1]
if found:  # an earlier run's block, the script's end: cut it off
    base = script[:script.index(found[0])]
else:
    assert script.endswith(TAIL), "the rule's script does not end as expected"
    base = script[:-len(TAIL)] + "    });\n"
assert base.endswith("    });\n"), "the rule's script does not end as expected before the block"
assert "const value = (name) =>" in base, "the rule has no value() helper"
new_script = base + BLOCK
print(f"rule {UID}:", "up to date" if new_script == script else "block replaced" if found else "gets the block")
days = {name: history(src) for name, _, src in MEANS}
stored = {name: (query(f'SELECT count(value) FROM "{name}"') or [[0, 0]])[0][1] for name, _, _ in MEANS}
for name, d in days.items():
    top = max(d, key=d.get)
    print(f"history {name}: {len(d)} days, {min(d)} to {max(d)}, highest {top} {d[top]:.3f} kW, "
          f"days at 0: {sum(1 for v in d.values() if v == 0)}; stored {stored[name]} points")
if apply:
    for name, label, _ in MEANS:
        if exists[name]:
            continue  # a PUT of an existing item would reset its state
        body = {"type": "Number:Power", "name": name, "label": label, "category": "material:bar_chart", "tags": [],
                "groupNames": []}
        print(f"item {name} PUT", call("PUT", f"/items/{name}", body)[0],
              *(call("PUT", f"/items/{name}/metadata/{ns}", meta)[0] for ns, meta in METADATA.items()))
    rule["actions"][0]["configuration"]["script"] = new_script
    rule["description"] = RULE_DESCRIPTIONS[UID]
    rule.pop("status", None)
    rule.pop("editable", None)
    print(f"rule {UID} PUT", call("PUT", f"/rules/{UID}", rule)[0])
    n = 0
    for name, d in days.items():
        if stored[name] >= len(d):
            continue  # filled by an earlier run
        for day, kw in sorted(d.items()):
            end = datetime.datetime.combine(day, datetime.time(23, 59, 59), TZ).isoformat(timespec="milliseconds")
            q = urllib.parse.urlencode({"serviceId": "influxdb", "time": end, "state": f"{kw:.3f} kW"})
            status = call("PUT", f"/persistence/items/{name}?{q}")[0]
            assert status == 200, (name, day, status)
            n += 1
    print(f"history written through openHAB: {n} points")
    print(f"rule {UID} runnow", call("POST", f"/rules/{UID}/runnow", {})[0])
