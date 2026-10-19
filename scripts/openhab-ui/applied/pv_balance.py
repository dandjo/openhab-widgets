#!/usr/bin/env python3
"""House consumption and PV self-use on the strings' generation instead of the inverter's yield (user, 2026-10-19,
wizard steps 5 and 6): the inverter's yield (huawei_inverter_e_day) counts the battery's discharge, leaves out what the
strings charge it with, and in winter the battery's charge from the grid comes back out through it, so
- home_ec_day (rule home_energy) = yield − export + import − the battery's grid charge (energy_storage_grid_charge_day,
  rule photovoltaics_energy_day): the grid charge was house consumption before (7.8 to 9.2 kWh a day too much on the
  winter days checked); and where it came from: home_from_grid_day (import less the grid charge),
  home_from_battery_day (the battery's discharge, at most what is left) and home_from_pv_day (the rest);
- photovoltaics_own_ec_day (rule photovoltaics_own_energy) = generation (photovoltaics_generation_day) − export: the
  PV used in the house or charged into the battery, the inverter's losses with it;
- energy_daily_totals keeps the day's generation from photovoltaics_generation_day, the grid charge and the three
  sources as daily totals, the self-use ratio as self-use / generation and the self-sufficiency as
  (consumption − import) / consumption.
History: the daily totals from 30 September 2024 (energy_daily_home, _self_use, _self_use_share,
_self_sufficiency, _battery_grid_charge, _house_pv, _house_battery, _house_grid) from the daily totals of yield,
export, import and generation, the battery's discharge (from 24 July 2025, the first battery readings) and the grid
charge from the active power's minute means; the day counters home_ec_day, photovoltaics_own_ec_day, the three
home_from_* and the three of photovoltaics_energy_day for the last HISTORY_DAYS days a point a minute where they
change (older ones keep their old points). apply first changes items and rules, then writes the history up to the
moment the rules changed (equal timestamps overwrite; the day counters' old points in that span are deleted first).
check prints each month's old and new consumption and self-use.
Usage: pv_balance.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
import datetime
import json
import os
import sys
import time
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
FIRST = datetime.date(2024, 9, 30)
HISTORY_DAYS = 35  # the raw data's month and a few days; tile_history compares with the last 7
PERSIST = ["influxdb_change", "influxdb_periodic"]
KWH = {"unit": {"value": "kWh"}, "stateDescription": {"value": " ", "config": {"pattern": "%.2f %unit%"}}}
LIVE = {
    "home_from_pv_day": "Haus aus PV heute",
    "home_from_battery_day": "Haus aus Akku heute",
    "home_from_grid_day": "Haus aus Netz heute",
}
DAILY = {
    "energy_daily_battery_grid_charge": "Energie täglich Akku-Netzladung",
    "energy_daily_house_pv": "Energie täglich Haus aus PV",
    "energy_daily_house_battery": "Energie täglich Haus aus Akku",
    "energy_daily_house_grid": "Energie täglich Haus aus Netz",
}
ITEMS = {**{n: {"type": "Number:Energy", "name": n, "label": label, "category": "material:home",
                "tags": ["Energy", "Measurement"], "groupNames": ["smart_meter", *PERSIST]} for n, label in LIVE.items()},
         **{n: {"type": "Number:Energy", "name": n, "label": label, "category": "material:bar_chart", "tags": [],
                "groupNames": []} for n, label in DAILY.items()}}

FRESH = """// a figure of another rule counts only once it was written since midnight (until then it holds yesterday's)
const fresh = (name) => {
  const item = items.getItem(name);
  const at = item.lastStateUpdateTimestamp;
  return at !== null && at !== undefined && !at.isBefore(time.toZDT('00:00')) && item.numericState !== null;
};
"""
HOME_OLD = """if (e_day !== null && grid_production_delta !== null && grid_consumption_delta !== null
    && !(e_day === 0 && grid_production_delta.numericState > 0)) {
  const energy = e_day - grid_production_delta.numericState + grid_consumption_delta.numericState;
  // a day counter is never negative nor beyond 300 kWh: a lagging e_day or a meter glitch, skip the run (2026-10-07)
  if (energy >= 0 && energy <= 300) persistEnergy('home_ec_day', energy, 'kWh');
}"""
HOME_NEW = FRESH + """// the battery's charge from the grid (rule photovoltaics_energy_day) is no house consumption: the inverter's yield
// gives it back when the battery discharges (user, 2026-10-19)
const grid_charge = fresh('energy_storage_grid_charge_day') ? items.getItem('energy_storage_grid_charge_day').numericState : 0;
if (e_day !== null && grid_production_delta !== null && grid_consumption_delta !== null
    && !(e_day === 0 && grid_production_delta.numericState > 0)) {
  const consumption = grid_consumption_delta.numericState;
  const energy = e_day - grid_production_delta.numericState + consumption - grid_charge;
  // a day counter is never negative nor beyond 300 kWh: a lagging e_day or a meter glitch, skip the run (2026-10-07)
  if (energy >= 0 && energy <= 300) {
    persistEnergy('home_ec_day', energy, 'kWh');
    // where it came from: the grid less the battery's grid charge, the battery's discharge (at most what is left),
    // the rest from PV straight
    const discharge = fresh('huawei_inverter_energy_storage_day_discharge')
      ? items.getItem('huawei_inverter_energy_storage_day_discharge').numericState : 0;
    const grid = Math.min(energy, Math.max(0, consumption - grid_charge));
    const battery = Math.max(0, Math.min(discharge, energy - grid));
    persistEnergy('home_from_grid_day', grid, 'kWh');
    persistEnergy('home_from_battery_day', battery, 'kWh');
    persistEnergy('home_from_pv_day', Math.max(0, energy - grid - battery), 'kWh');
  }
}"""
OWN_OLD = """const e_day = items.getItem('huawei_inverter_e_day').numericState;
const grid_production_delta = items.getItem('huawei_inverter_power_meter_grid_production').persistence.deltaSince(time.toZDT('00:00'));

// sources are null right after startup until modbus values and persistence are available;
// e_day can read 0 for a moment after a modbus outage although energy was exported today already
if (e_day !== null && grid_production_delta !== null
    && !(e_day === 0 && grid_production_delta.numericState > 0)) {
  const energy = e_day - grid_production_delta.numericState;"""
OWN_NEW = FRESH + """// the PV used in the house or charged into the battery: the strings' generation (rule photovoltaics_energy_day) less
// the export; the inverter's yield counts the battery's discharge (user, 2026-10-19)
const generation = fresh('photovoltaics_generation_day') ? items.getItem('photovoltaics_generation_day').numericState : null;
const grid_production_delta = items.getItem('huawei_inverter_power_meter_grid_production').persistence.deltaSince(time.toZDT('00:00'));

// sources are null right after startup until modbus values and persistence are available
if (generation !== null && grid_production_delta !== null) {
  const energy = generation - grid_production_delta.numericState;"""
DAILY_OLD_GEN = """  // the day's PV generation: the two strings' energy from their time-weighted mean power since midnight, as the
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
DAILY_OLD_PAIRS = """  ['photovoltaics_own_ec_day', 'energy_daily_self_use'],
];"""
DAILY_NEW_PAIRS = """  ['photovoltaics_own_ec_day', 'energy_daily_self_use'],
  // the strings' generation (the inverter's yield above counts the battery's discharge), the battery's charge from the
  // grid and where the house's energy came from (user, 2026-10-19)
  ['photovoltaics_generation_day', 'energy_daily_pv_generation'],
  ['energy_storage_grid_charge_day', 'energy_daily_battery_grid_charge'],
  ['home_from_pv_day', 'energy_daily_house_pv'],
  ['home_from_battery_day', 'energy_daily_house_battery'],
  ['home_from_grid_day', 'energy_daily_house_grid'],
];"""
DAILY_OLD_SHARES = """  // the day's shares in per cent, as Grafana's panel "PV-Eigenverbrauch pro Tag" computed them: of the yield used in
  // the house (self-consumption ratio) and of the house's consumption that PV covered (self-sufficiency)
  const own = items.getItem('photovoltaics_own_ec_day').numericState;
  [['huawei_inverter_e_day', 'energy_daily_self_use_share'], ['home_ec_day', 'energy_daily_self_sufficiency']]
    .forEach(([whole, target]) => {
      const w = items.getItem(whole).numericState;
      if (own !== null && w !== null && w > 0) {
        const state = Quantity(Math.min(100, Math.max(0, own / w * 100)).toFixed(1) + ' %');
        items.getItem(target).postUpdate(state);
        items.getItem(target).persistence.persist(endOfDay, state, 'influxdb');
      }
    });"""
DAILY_NEW_SHARES = """  // the day's shares in per cent: of the generation used in the house or charged into the battery (self-consumption
  // ratio) and of the house's consumption not taken from the grid (self-sufficiency), on the strings' generation
  // since 2026-10-19, as the inverter's yield counts the battery's discharge
  const value = (name) => items.getItem(name).numericState;
  const own = value('photovoltaics_own_ec_day');
  const generation = value('photovoltaics_generation_day');
  const home = value('home_ec_day');
  const imported = value('huawei_inverter_power_meter_ec_day');
  [[own, generation, 'energy_daily_self_use_share'],
   [home === null || imported === null ? null : home - imported, home, 'energy_daily_self_sufficiency']]
    .forEach(([part, whole, target]) => {
      if (part !== null && whole !== null && whole > 0) {
        const state = Quantity(Math.min(100, Math.max(0, part / whole * 100)).toFixed(1) + ' %');
        items.getItem(target).postUpdate(state);
        items.getItem(target).persistence.persist(endOfDay, state, 'influxdb');
      }
    });"""
RULES = {
    "home_energy": ([(HOME_OLD, HOME_NEW)], ["huawei_inverter_e_day", "huawei_inverter_power_meter_grid_consumption",
                                             "huawei_inverter_power_meter_grid_production", "energy_storage_grid_charge_day"]),
    "photovoltaics_own_energy": ([(OWN_OLD, OWN_NEW)], ["photovoltaics_generation_day",
                                                        "huawei_inverter_power_meter_grid_production"]),
    "energy_daily_totals": ([(DAILY_OLD_GEN, ""), (DAILY_OLD_PAIRS, DAILY_NEW_PAIRS), (DAILY_OLD_SHARES, DAILY_NEW_SHARES)],
                            None),
}


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
    url = f"{INFLUX}/query?db=openhab&epoch=ms&q=" + urllib.parse.quote(query)
    with urllib.request.urlopen(url) as r:
        series = json.load(r)["results"][0].get("series", [])
    return series[0]["values"] if series else []


def write(lines):
    for i in range(0, len(lines), 5000):
        req = urllib.request.Request(f"{INFLUX}/write?db=openhab&precision=ms", method="POST",
                                     data="\n".join(lines[i:i + 5000]).encode())
        with urllib.request.urlopen(req) as r:
            assert r.status == 204, r.status


def ms(d, h=0, m=0, s=0):
    return int(datetime.datetime.combine(d, datetime.time(h, m, s), TZ).timestamp() * 1000)


def daily_values(item, first, end):
    """A daily total's value by local day (its point at 23:59:59)."""
    return {datetime.datetime.fromtimestamp(t / 1000, TZ).date(): v
            for t, v in influx(f"SELECT value FROM {item} WHERE time >= {ms(first)}ms AND time < {end}ms") if v is not None}


def minutes(item, a, b, fn="mean"):
    """An item's minute values from a to b (ms), each minute's mean (or last, max), the last one carried on."""
    return {t: v for t, v in influx(f"SELECT {fn}(value) FROM {item} WHERE time >= {a}ms AND time < {b}ms "
                                    "GROUP BY time(1m) fill(previous)") if v is not None}


def grid_charge_days(first, end):
    """Each day's grid charge (kWh): the active power's minute means below zero, on days where it went below -20 W."""
    out = {}
    for t, low in influx(f"SELECT min(value) FROM huawei_inverter_active_power WHERE time >= {ms(first)}ms AND time < {end}ms "
                         "GROUP BY time(1d, 22h)"):
        if low is None or low > -20:
            continue
        # the bucket starts at 22:00 UTC; take the local days it touches
        for d in {datetime.datetime.fromtimestamp(t / 1000, TZ).date(),
                  datetime.datetime.fromtimestamp(t / 1000 + 43200, TZ).date()}:
            if d in out or not first <= d:
                continue
            a, b = ms(d), ms(d + datetime.timedelta(days=1))
            out[d] = sum(max(0, -v) for v in minutes("huawei_inverter_active_power", a, min(b, end)).values()) / 60000
    return out


def history_daily(end):
    first = FIRST
    yesterday = datetime.datetime.fromtimestamp(end / 1000, TZ).date() - datetime.timedelta(days=1)
    e = daily_values("energy_daily_pv", first, end)
    exp = daily_values("energy_daily_grid_export", first, end)
    imp = daily_values("energy_daily_grid_import", first, end)
    gen = daily_values("energy_daily_pv_generation", first, end)
    old_home = daily_values("energy_daily_home", first, end)
    old_own = daily_values("energy_daily_self_use", first, end)
    # the battery's discharge: each day's last hourly reading before 23 h (the counter can still hold the day's total
    # for a moment after midnight)
    dis = {}
    for t, v in influx(f"SELECT last(value) FROM huawei_inverter_energy_storage_day_discharge WHERE time >= {ms(first)}ms "
                       f"AND time < {end}ms GROUP BY time(1h)"):
        if v is not None:
            d = datetime.datetime.fromtimestamp(t / 1000, TZ)
            if d.hour < 23:
                dis[d.date()] = v
    g = grid_charge_days(first, end)
    rows = {}
    d = first
    while d <= yesterday:
        if d in e and d in exp and d in imp and d in gen:
            G = g.get(d, 0.0)
            home = max(0.0, e[d] - exp[d] + imp[d] - G)
            own = max(0.0, gen[d] - exp[d])
            grid = min(home, max(0.0, imp[d] - G))
            battery = max(0.0, min(dis.get(d, 0.0), home - grid))
            rows[d] = {"energy_daily_home": home, "energy_daily_self_use": own,
                       "energy_daily_self_use_share": min(100, own / gen[d] * 100) if gen[d] > 0 else None,
                       "energy_daily_self_sufficiency": min(100, max(0, (home - imp[d]) / home * 100)) if home > 0 else None,
                       "energy_daily_battery_grid_charge": G, "energy_daily_house_pv": max(0.0, home - grid - battery),
                       "energy_daily_house_battery": battery, "energy_daily_house_grid": grid,
                       "_old_home": old_home.get(d), "_old_own": old_own.get(d)}
        d += datetime.timedelta(days=1)
    return rows


def history_live(end):
    """The day counters of the last HISTORY_DAYS days, a value a minute, each day from its midnight."""
    today = datetime.datetime.fromtimestamp(end / 1000, TZ).date()
    out = {}
    for k in range(HISTORY_DAYS, -1, -1):
        d = today - datetime.timedelta(days=k)
        a, b = ms(d), min(ms(d + datetime.timedelta(days=1)), end)
        get = lambda item, fn="mean": minutes(item, a, b, fn)
        p1, p2, pin = get("huawei_inverter_pv1_power"), get("huawei_inverter_pv2_power"), get("huawei_inverter_input_power", "max")
        act, eday = get("huawei_inverter_active_power"), get("huawei_inverter_e_day", "last")
        prod, cons = get("huawei_inverter_power_meter_grid_production", "last"), get("huawei_inverter_power_meter_grid_consumption", "last")
        dis = get("huawei_inverter_energy_storage_day_discharge", "last")
        p0 = next((prod[t] for t in sorted(prod)), None)
        c0 = next((cons[t] for t in sorted(cons)), None)
        gen = G = peak = 0.0
        settled = {}
        for t in range(a, b, 60000):
            gen += (p1.get(t, 0) + p2.get(t, 0)) / 60000
            G += max(0, -act.get(t, 0)) / 60000
            peak = max(peak, pin.get(t, 0))
            minute = (t - a) // 60000
            # the inverter's and the battery's day counters can hold yesterday's total for a moment after midnight
            e = eday.get(t, 0) if minute >= 3 else min(eday.get(t, 0), eday.get(a + 5 * 60000, 0))
            di = dis.get(t, 0) if minute >= 3 else min(dis.get(t, 0), dis.get(a + 5 * 60000, 0))
            exp = prod.get(t, p0) - p0 if p0 is not None else 0
            imp = cons.get(t, c0) - c0 if c0 is not None else 0
            home = max(0.0, e - exp + imp - G)
            grid = min(home, max(0.0, imp - G))
            battery = max(0.0, min(di, home - grid))
            settled[t] = {"photovoltaics_generation_day": round(gen, 3), "photovoltaics_peak_day": round(peak),
                          "energy_storage_grid_charge_day": round(G, 3),
                          "photovoltaics_own_ec_day": round(max(0.0, gen - exp), 3), "home_ec_day": round(home, 3),
                          "home_from_grid_day": round(grid, 3), "home_from_battery_day": round(battery, 3),
                          "home_from_pv_day": round(max(0.0, home - grid - battery), 3)}
        out[d] = settled
    return out


apply = sys.argv[1] == "apply"
for name in ITEMS:
    status, item = call("GET", f"/items/{name}")
    print(f"item {name}:", f"exists, state {item['state']}" if status == 200 else "missing")
rules = {}
for uid, (reps, triggers) in RULES.items():
    status, rule = call("GET", f"/rules/{uid}")
    assert status == 200, uid
    script = rule["actions"][0]["configuration"]["script"]
    done = all(new and new in script for old, new in reps if new) and all(old not in script for old, _ in reps)
    if not done:
        for old, new in reps:
            assert script.count(old) == 1, (uid, old[:60])
            script = script.replace(old, new)
    rule["actions"][0]["configuration"]["script"] = script
    if triggers:
        cron = [t for t in rule["triggers"] if t["type"] != "core.ItemStateChangeTrigger"]
        rule["triggers"] = [{"id": str(i + 1), "type": "core.ItemStateChangeTrigger", "configuration": {"itemName": n}}
                            for i, n in enumerate(triggers)] + [{**t, "id": str(len(triggers) + i + 1)} for i, t in enumerate(cron)]
    if uid in RULE_DESCRIPTIONS:
        rule["description"] = RULE_DESCRIPTIONS[uid]
    rule.pop("status", None)
    rule.pop("editable", None)
    rules[uid] = rule
    print(f"rule {uid}:", "already changed" if done else "gets the change")
now = int(time.time() * 1000)
rows = history_daily(now)
months = {}
for d, r in rows.items():
    m = months.setdefault(d.strftime("%Y-%m"), [0, 0, 0, 0, 0, 0])
    m[0] += 1; m[1] += r["_old_home"] or 0; m[2] += r["energy_daily_home"]; m[3] += r["_old_own"] or 0
    m[4] += r["energy_daily_self_use"]; m[5] += r["energy_daily_battery_grid_charge"]
print("month    days  house old  new  self-use old  new  grid charge  (kWh a day)")
for m, (n, ho, hn, oo, on, gc) in sorted(months.items()):
    print(f"{m}  {n:4}  {ho / n:9.1f} {hn / n:5.1f}  {oo / n:12.1f} {on / n:5.1f}  {gc / n:11.2f}")
if apply:
    for name, item in ITEMS.items():
        print(f"item {name} PUT", call("PUT", f"/items/{name}", item)[0],
              *(call("PUT", f"/items/{name}/metadata/{ns}", meta)[0] for ns, meta in KWH.items()))
    cutoff = int(time.time() * 1000)
    for uid, rule in rules.items():
        print(f"rule {uid} PUT", call("PUT", f"/rules/{uid}", rule)[0])
    lines = []
    for d, r in sorted(rows.items()):
        t = ms(d, 23, 59, 59)
        lines += [f"{k},item={k} value={round(v, 3)} {t}" for k, v in r.items() if not k.startswith("_") and v is not None]
    write(lines)
    print(f"daily history written: {len(lines)} points")
    live = history_live(cutoff)
    names = ["photovoltaics_generation_day", "photovoltaics_peak_day", "energy_storage_grid_charge_day",
             "photovoltaics_own_ec_day", "home_ec_day", *LIVE]
    start = ms(min(live))
    for name in names:
        influx_q = f"DELETE FROM {name} WHERE time >= {start * 1000000} AND time < {cutoff * 1000000}"
        urllib.request.urlopen(f"{INFLUX}/query?db=openhab&q=" + urllib.parse.quote(influx_q), data=b"").read()
    lines = []
    for d, settled in sorted(live.items()):
        last = {}
        for t, values in sorted(settled.items()):
            for k, v in values.items():
                if last.get(k) != v:
                    lines.append(f"{k},item={k} value={v} {t}")
                    last[k] = v
    write(lines)
    print(f"day counters written: {len(lines)} points, {min(live)} to the change at "
          f"{datetime.datetime.fromtimestamp(cutoff / 1000, TZ):%H:%M:%S}")
