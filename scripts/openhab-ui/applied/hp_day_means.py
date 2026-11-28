#!/usr/bin/env python3
"""The heat pump's mean powers per day, each over the hours of its purpose (user, 2026-11-28: "Die Warmwasserleistung
nur für den Betrieb im Warmwasser rechnen, der Rest fällt nur im Heizbetrieb auf die Heizung"; of three ways to count
the heating's hours, "Rest des Tages"): the hot water's heat and electric power (the latter added the same day) over
the hours the heat pump made hot water (the three-way valve on DHW, or the tank's booster heater on), the space
heating's electric and heat power over the rest of the hours with the heating switched on
(pyaltherma_climate_control_power; a summer day has none); 0 where a day has less than 6 minutes of them (a valve's
blip of 36 s once made 34 kW). Items energy_daily_heatpump_space_electric_mean,
energy_daily_heatpump_space_heat_mean, energy_daily_heatpump_dhw_electric_mean and
energy_daily_heatpump_dhw_heat_mean in kW, and the two counts of hours, energy_daily_heatpump_space_hours and
energy_daily_heatpump_dhw_hours, one point per day at 23:59:59 as the other daily totals. Rule energy_daily_totals
writes them from espaltherma_energy_space_today, espaltherma_heating_energy_space_today, espaltherma_energy_dhw_today
and espaltherma_heating_energy_dhw_today and the hours from the states' changes since midnight in InfluxDB, so
today's point is the mean so far; the block is appended to its script here, or replaces the one an earlier run
appended (also the first version's, which divided by the day's 24 hours). apply also writes the days from 19 October
2024 (the counters' first whole day) to yesterday, from each day's last counter reading and the states in InfluxDB,
through openHAB's persistence REST API, only the days whose stored point differs (equal timestamps overwrite); check
prints what it would write.
Usage: hp_day_means.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
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
# the states the hours come from
VALVE, BSH, HEATING = "espaltherma_3way_valve_mode", "espaltherma_bsh_mode", "pyaltherma_climate_control_power"
# target item, its label, the day counter it divides, the hours it divides by
MEANS = [("energy_daily_heatpump_space_electric_mean", "Wärmepumpe Heizung Ø Stromleistung täglich",
          "espaltherma_energy_space_today", "space"),
         ("energy_daily_heatpump_space_heat_mean", "Wärmepumpe Heizung Ø Heizleistung täglich",
          "espaltherma_heating_energy_space_today", "space"),
         # the hot water's electricity too (user, 2026-11-28: "Für das Warmwasser braucht es doch auch eine
         # durchschnittliche Stromleistung")
         ("energy_daily_heatpump_dhw_electric_mean", "Wärmepumpe Warmwasser Ø Stromleistung täglich",
          "espaltherma_energy_dhw_today", "dhw"),
         ("energy_daily_heatpump_dhw_heat_mean", "Wärmepumpe Warmwasser Ø Heizleistung täglich",
          "espaltherma_heating_energy_dhw_today", "dhw")]
HOURS = [("energy_daily_heatpump_space_hours", "Wärmepumpe Heizung Stunden täglich", "space"),
         ("energy_daily_heatpump_dhw_hours", "Wärmepumpe Warmwasser Stunden täglich", "dhw")]
ITEMS = {name: ("Number:Power", label, "material:bar_chart", "kW", "%.3f %unit%") for name, label, _, _ in MEANS}
ITEMS.update({name: ("Number:Time", label, "material:schedule", "h", "%.2f %unit%") for name, label, _ in HOURS})
MIN_HOURS = 0.1  # below, a mean says nothing: 0
TAIL = "    });\n}"
# the block's first line, now and as earlier runs wrote it
MARKERS = ("\n  // the heat pump's mean powers of the day, each over", "\n  // the heat pump's mean powers of the day",
           "\n  // the space heating's mean electric and heat power")
BLOCK = """
  // the heat pump's mean powers of the day, each over the hours of its purpose (user, 2026-11-28): the hot water's
  // heat and electricity over the hours the heat pump made hot water (the three-way valve on DHW, or the tank's
  // booster heater on), the space heating's electricity and heat over the rest of the hours with the heating switched
  // on (none on a summer day); the hours from the states' changes since midnight, so today's means are those so far; 0 below 6 minutes of
  // such hours (a valve's blip of 36 s once made 34 kW)
  const from = time.toZDT('00:00');
  const fromMs = from.toInstant().toEpochMilli();
  const toMs = time.toZDT().toInstant().toEpochMilli();
  const names = {valve: '""" + VALVE + """', bsh: '""" + BSH + """', heating: '""" + HEATING + """'};
  const states = {};
  const changes = [];
  Object.entries(names).forEach(([key, name]) => {
    const p = items.getItem(name).persistence;
    const before = p.persistedState(from, 'influxdb');
    states[key] = before === null ? null : String(before.state);
    p.getAllStatesBetween(from, time.toZDT(), 'influxdb').forEach((s) => {
      changes.push([s.timestamp.toInstant().toEpochMilli(), key, String(s.state)]);
    });
  });
  changes.sort((a, b) => a[0] - b[0]);
  const hours = {space: 0, dhw: 0};
  let since = fromMs;
  const count = (until) => {
    const span = Math.max(0, until - since) / 3600000;
    const dhwValve = states.valve === 'DHW';
    if (dhwValve || states.bsh === 'ON') {
      hours.dhw += span;
    }
    if (states.heating === 'ON' && !dhwValve) {
      hours.space += span;
    }
    since = Math.max(since, until);
  };
  changes.forEach(([ms, key, state]) => {
    count(ms);
    states[key] = state;
  });
  count(toMs);
  const persistAll = (target, state) => {
    items.getItem(target).postUpdate(state);
    items.getItem(target).persistence.persist(endOfDay, state, 'influxdb');
  };
""" + "  [" + ",\n   ".join(f"['{src}', '{item}', '{base}']" for item, _, src, base in MEANS) + \
    """].forEach(([source, target, base]) => {
    const kwh = value(source);
    if (kwh !== null) {
      const kw = hours[base] >= """ + str(MIN_HOURS) + """ ? kwh / hours[base] : 0;
      persistAll(target, Quantity(kw.toFixed(3) + ' kW'));
    }
  });
""" + "  [" + ", ".join(f"['{item}', '{base}']" for item, _, base in HOURS) + """].forEach(([target, base]) => {
    persistAll(target, Quantity(hours[base].toFixed(3) + ' h'));
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


def query(q, epoch="ns"):
    url = f"{INFLUX}/query?" + urllib.parse.urlencode({"db": "openhab", "epoch": epoch, "q": q})
    series = json.load(urllib.request.urlopen(url, timeout=120))["results"][0].get("series", [])
    return series[0]["values"] if series else []


def midnight(d):
    return datetime.datetime.combine(d, datetime.time(), TZ)


def ms(d):
    return int(midnight(d).timestamp() * 1000)


def day_hours(first, today):
    """{day: {"space": h, "dhw": h}} from first to yesterday, from the three states' points in InfluxDB as the rule
    counts them (a Switch stands there as 1 or 0)"""
    on = lambda v: v in (1, 1.0, "1", "ON", True)
    changes = []
    states = {}
    for key, name in (("valve", VALVE), ("bsh", BSH), ("heating", HEATING)):
        before = query(f'SELECT last(value) FROM "{name}" WHERE time < {ms(first)}ms', "ms")
        states[key] = before[0][1] if before else None
        changes += [(t, key, v) for t, v in
                    query(f'SELECT value FROM "{name}" WHERE time >= {ms(first)}ms AND time < {ms(today)}ms', "ms")]
    changes.sort(key=lambda c: c[0])
    out, i, day = {}, 0, first
    while day < today:
        start, end = ms(day), ms(day + datetime.timedelta(days=1))
        h = {"space": 0.0, "dhw": 0.0}
        since = start

        def count(until):
            span = max(0, until - since) / 3600000
            dhw_valve = states["valve"] == "DHW"
            if dhw_valve or on(states["bsh"]):
                h["dhw"] += span
            if on(states["heating"]) and not dhw_valve:
                h["space"] += span
            return max(since, until)

        while i < len(changes) and changes[i][0] < end:
            t, key, v = changes[i]
            since = count(t)
            states[key] = v
            i += 1
        count(end)
        out[day] = h
        day += datetime.timedelta(days=1)
    return out


def counters(source, today):
    """{day: kWh}: each day's last reading of a day counter"""
    rows = query(f"SELECT last(value) FROM \"{source}\" WHERE time >= '{midnight(FIRST).isoformat()}' "
                 f"AND time < '{midnight(today).isoformat()}' GROUP BY time(1d) tz('Europe/Vienna')")
    out = {}
    for ns, kwh in rows:
        day = datetime.datetime.fromtimestamp(ns / 1e9, TZ).date()
        if kwh is not None and FIRST <= day < today:
            out[day] = kwh
    return out


def stored(name, today):
    """{day: value} of the points an item holds at its days' ends"""
    rows = query(f"SELECT value FROM \"{name}\" WHERE time >= '{midnight(FIRST).isoformat()}' "
                 f"AND time < '{midnight(today).isoformat()}'")
    return {datetime.datetime.fromtimestamp(ns / 1e9, TZ).date(): v for ns, v in rows}


apply = sys.argv[1:] == ["apply"]
if sys.argv[1:] not in (["check"], ["apply"]):
    sys.exit(__doc__)
exists = {}
for name in ITEMS:
    status, item = call("GET", f"/items/{name}")
    exists[name] = status == 200
    print(f"item {name}:", f"exists, state {item['state']}" if status == 200 else "missing")
status, rule = call("GET", f"/rules/{UID}")
assert status == 200, f"rule {UID} missing"
script = rule["actions"][0]["configuration"]["script"]
found = next((m for m in MARKERS if script.count(m) == 1), None)
if found:  # an earlier run's block, the script's end: cut it off
    base = script[:script.index(found)]
else:
    assert script.endswith(TAIL), "the rule's script does not end as expected"
    base = script[:-len(TAIL)] + "    });\n"
assert base.endswith("    });\n"), "the rule's script does not end as expected before the block"
assert "const value = (name) =>" in base and "const endOfDay =" in base, "the rule lacks value() or endOfDay"
new_script = base + BLOCK
print(f"rule {UID}:", "up to date" if new_script == script else "block replaced" if found else "gets the block")
today = datetime.datetime.now(TZ).date()
hours = day_hours(FIRST, today)
want = {}
for name, _, src, base_ in MEANS:
    kwh = counters(src, today)
    want[name] = {d: (round(k / hours[d][base_], 3) if hours[d][base_] >= MIN_HOURS else 0.0) for d, k in kwh.items()}
for name, _, base_ in HOURS:
    want[name] = {d: round(h[base_], 3) for d, h in hours.items()}
writes = {}
for name, days in want.items():
    have = stored(name, today)
    writes[name] = {d: v for d, v in days.items() if have.get(d) is None or abs(have[d] - v) > 0.0005}
    top = max(days, key=days.get)
    unit = ITEMS[name][3]
    print(f"history {name}: {len(days)} days, {min(days)} to {max(days)}, highest {top} {days[top]:.3f} {unit}, "
          f"days at 0: {sum(1 for v in days.values() if v == 0)}; stored {len(have)}, to write {len(writes[name])}")
if apply:
    for name, (kind, label, category, unit, pattern) in ITEMS.items():
        if exists[name]:
            continue  # a PUT of an existing item would reset its state
        body = {"type": kind, "name": name, "label": label, "category": category, "tags": [], "groupNames": []}
        meta = {"unit": {"value": unit}, "stateDescription": {"value": " ", "config": {"pattern": pattern}}}
        print(f"item {name} PUT", call("PUT", f"/items/{name}", body)[0],
              *(call("PUT", f"/items/{name}/metadata/{ns}", m)[0] for ns, m in meta.items()))
    if new_script != script or rule.get("description") != RULE_DESCRIPTIONS[UID]:
        rule["actions"][0]["configuration"]["script"] = new_script
        rule["description"] = RULE_DESCRIPTIONS[UID]
        rule.pop("status", None)
        rule.pop("editable", None)
        print(f"rule {UID} PUT", call("PUT", f"/rules/{UID}", rule)[0])
    n = 0
    for name, days in writes.items():
        unit = ITEMS[name][3]
        for day, v in sorted(days.items()):
            end = datetime.datetime.combine(day, datetime.time(23, 59, 59), TZ).isoformat(timespec="milliseconds")
            q = urllib.parse.urlencode({"serviceId": "influxdb", "time": end, "state": f"{v:.3f} {unit}"})
            status = call("PUT", f"/persistence/items/{name}?{q}")[0]
            assert status == 200, (name, day, status)
            n += 1
    print(f"history written through openHAB: {n} points")
    print(f"rule {UID} runnow", call("POST", f"/rules/{UID}/runnow", {})[0])
