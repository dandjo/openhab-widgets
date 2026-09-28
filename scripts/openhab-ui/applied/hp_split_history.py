#!/usr/bin/env python3
"""Correct the heat pump's split history for variants A and B of heatpump_metering (27 September 2026), from the
first split point (18 October 2024) up to CUTOFF, when the new rule took over (openHAB stopped for its deploy).

Power: wherever space heating is off (pyaltherma_climate_control_power and espaltherma_space_heating_operation
both off) or the valve reports DHW, power booked as space heating moves to hot water, the electrical power of a
pump run alone (no compressor, no backup heater) to standby; the instantaneous COPs follow, totals do not change.
Energy: days before 24 September 2026, when heatpump_metering began to integrate with one shared time step, are
replayed from the rule's inputs with its split (hp_model.Metering, the same as the rule's JavaScript on every
evaluation) and integrated like the rule, trapezoidal with one shared time step and no bridging of a silence over
5 minutes (openHAB down), so space + DHW + standby equals the total; later days
keep the rule's integration and get the moved energy added and subtracted. Daily COPs follow the energies (a value
over 12 keeps its old point, as the rule would not write it). apply writes only if the replay's plug energy matches
the plug's own day meter (median within 1 %, 90 % of the days within 5 %). Old values go to a gzipped CSV first. Runs on the
workstation through an ssh tunnel to InfluxDB (hp_model.INFLUX).
Usage: hp_split_history.py check|apply CUTOFF_NS [BACKUP.csv.gz]"""
import array
import bisect
import collections
import datetime
import gzip
import sys
import time
from zoneinfo import ZoneInfo

import hp_model as hm

TZ = ZoneInfo("Europe/Vienna")
MODE, CUTOFF = sys.argv[1], int(sys.argv[2])
EXACT_FROM = int(datetime.datetime(2026, 9, 24, tzinfo=TZ).timestamp() * 1e9)
TICK, SILENCE, MAX_GAP = 20e9, 300e9, 300e9
P = "espaltherma_"
EL = {"space": P + "electrical_power_space", "dhw": P + "electrical_power_dhw", "standby": P + "electrical_power_standby"}
HEAT = {"space": P + "heating_power_space", "dhw": P + "heating_power_dhw"}
COP = {"space": P + "cop_space", "dhw": P + "cop_dhw"}
ENERGY = {"space": P + "energy_space_today", "dhw": P + "energy_dhw_today", "standby": P + "energy_standby_today",
          "total": P + "energy_today", "h_space": P + "heating_energy_space_today",
          "h_dhw": P + "heating_energy_dhw_today", "h_total": P + "heating_energy_today"}
DCOP = {P + "dcop_space": ("h_space", "space"), P + "dcop_dhw": ("h_dhw", "dhw"), P + "dcop": ("h_total", "total")}
t0 = time.time()


def log(msg):
    print(f"[{time.time() - t0:6.0f} s] {msg}", flush=True)


class Step:
    """A persisted series as a step function: the last value at or before a time."""
    def __init__(self, pts, default=0.0):
        self.t, self.v, self.default = [t for t, _ in pts], [v for _, v in pts], default
        self.times = set(self.t)

    def at(self, t):
        i = bisect.bisect_right(self.t, t) - 1
        return self.v[i] if i >= 0 and self.v[i] is not None else self.default


def midnight(t):
    d = datetime.datetime.fromtimestamp(t // 1_000_000_000, TZ)  # whole seconds: t / 1e9 rounds 23:59:59.999… up
    return int(datetime.datetime.combine(d.date(), datetime.time(), TZ).timestamp() * 1e9)


first = hm.query(f'SELECT value FROM "{EL["space"]}" ORDER BY time ASC LIMIT 1')[0][0]
START = midnight(first)
assert START < EXACT_FROM < CUTOFF <= time.time_ns(), (START, EXACT_FROM, CUTOFF)


def load(m, default=0.0, a=START, b=None):
    b = CUTOFF if b is None else b
    prev = hm.before(m, a)
    return Step(([(a, prev[1])] if prev else []) + hm.points(m, a, b), default)


fix = collections.defaultdict(list)  # measurement → [(t, old or None, new)]


def record(m, t, old_step, old, new, prev_diff):
    """Writes where the new value differs, and once more where it returns to the old one."""
    diff = abs((new or 0) - (old or 0)) > 1e-9
    if diff or prev_diff:
        fix[m].append((t, old if t in old_step.times else None, new))
    return diff


# --- power: move space heating where A or B say so
ev = hm.events(START, CUTOFF)
log(f"{len(ev)} input points loaded")
inp = collections.defaultdict(list)
for t, k, v in ev:
    inp[k].append((t, v))
inp = {k: Step(p, None) for k, p in inp.items()}


def target(t):
    """Where power booked as space heating at t belongs: None (stays), 'dhw', or 'standby' (a pump run alone)."""
    heating_off = inp["climate"].at(t) == "OFF" and inp["sh_operation"].at(t) == "OFF"
    if heating_off:
        inverter = (inp["plug"].at(t) or 0) > 70 or (inp["inv_frequency"].at(t) or 0) > 0 \
            or (inp["inv_current"].at(t) or 0) > 0
        return "dhw" if inverter or inp["buh1"].at(t) == "ON" or inp["buh2"].at(t) == "ON" else "standby"
    return "dhw" if inp["valve"].at(t) == "DHW" else None


def resplit(series, heat):
    old = {k: load(m) for k, m in series.items()}
    times = sorted(set().union(*(s.times for s in old.values())))
    new, moved = {k: [] for k in series}, []
    prev_diff = {k: False for k in series}
    for t in times:
        v = {k: s.at(t) for k, s in old.items()}
        n = dict(v)
        if (v["space"] or 0) > 0:
            to = target(t)
            if to is not None:
                to = "dhw" if heat else to
                n[to] = (n[to] or 0) + v["space"]
                n["space"] = 0.0
                moved.append(t)
        for k in series:
            new[k].append((t, n[k]))
            prev_diff[k] = record(series[k], t, old[k], v[k], n[k], prev_diff[k])
    log(f"{'heat' if heat else 'electrical'} split: {len(times)} times, {len(moved)} moved")
    return {k: Step(p) for k, p in new.items()}, old, moved


el_new, el_old, el_moved = resplit(EL, False)
heat_new, heat_old, heat_moved = resplit(HEAT, True)

# instantaneous COPs: space 0 where anything moved, DHW from the new powers (the rule writes a COP only up to 10
# and otherwise keeps the last one)
cop_old = {k: load(m) for k, m in COP.items()}
moved_set = set(el_moved) | set(heat_moved)
prev_diff, last_dhw = {k: False for k in COP}, None
for t in sorted(moved_set | cop_old["space"].times | cop_old["dhw"].times):
    new = {k: cop_old[k].at(t) for k in COP}
    if t in moved_set:
        e, h = el_new["dhw"].at(t), heat_new["dhw"].at(t)
        c = h / e if e > 0 and h > 0 else 0.0
        new = {"space": 0.0, "dhw": round(c, 2) if c <= 10 else (last_dhw if last_dhw is not None else new["dhw"])}
    last_dhw = new["dhw"]
    for k in COP:
        prev_diff[k] = record(COP[k], t, cop_old[k], cop_old[k].at(t), new[k], prev_diff[k])
log(f"cops: {len(fix[COP['space']])} space and {len(fix[COP['dhw']])} DHW points")

# --- energy before EXACT_FROM: replay the rule on its inputs, a run on every input change and at least every 20 s
changes = sorted({t for t, _, _ in ev})
runs = []
for a, b in zip(changes, changes[1:] + [CUTOFF]):
    runs.append(a)
    if b - a <= SILENCE:
        runs += range(int(a + TICK), int(b), int(TICK))
log(f"replay: {len(changes)} input changes, {len(runs)} runs")
metering, cur, valve_changed = hm.Metering(), {}, None
pos = 0
KEYS = ("space", "dhw", "standby", "total", "h_space", "h_dhw", "h_total", "plug")
cum_t, cum = array.array("q"), {k: array.array("d") for k in KEYS}
acc = {k: 0.0 for k in KEYS}
prev_t, prev_p = None, None
for t in runs:
    while pos < len(ev) and ev[pos][0] <= t:
        _, k, v = ev[pos]
        if k == "valve" and cur.get("valve") != v:
            valve_changed = ev[pos][0]
        cur[k] = v
        pos += 1
    r = metering.step(cur, t, valve_changed)
    r["plug"] = cur.get("plug") or 0.0
    p = {k: r[k] for k in KEYS}
    if prev_t is not None and t - prev_t <= MAX_GAP:
        for k in KEYS:
            acc[k] += (prev_p[k] + p[k]) / 2 * (t - prev_t) / 3.6e12  # Wh
    cum_t.append(int(t))
    for k in KEYS:
        cum[k].append(acc[k])
    prev_t, prev_p = t, p
log("replay integrated")


def replay_today(k, t):
    """Energy of part k from the midnight before t up to t (Wh), from the replay."""
    def at(x):
        i = bisect.bisect_right(cum_t, x) - 1
        if i < 0:
            return 0.0
        if i + 1 < len(cum_t) and cum_t[i + 1] - cum_t[i] <= MAX_GAP:
            f = (x - cum_t[i]) / (cum_t[i + 1] - cum_t[i])
            return cum[k][i] + f * (cum[k][i + 1] - cum[k][i])
        return cum[k][i]
    return at(t) - at(midnight(t))


# --- energy from EXACT_FROM: the moved power, integrated since midnight (sample and hold, as the rule's shared step
# sees the persisted series), added to where it went and taken from space
def moved_series(series_new, series_old):
    """Step series of new minus old per part, from EXACT_FROM."""
    out = {}
    for k in series_new:
        times = sorted(t for t in set(series_new[k].t) | set(series_old[k].t) if t >= midnight(EXACT_FROM))
        out[k] = [(t, (series_new[k].at(t) or 0) - (series_old[k].at(t) or 0)) for t in times]
    return out


class Integral:
    """A step series of differences, integrated (Wh), sample and hold."""
    def __init__(self, pts):
        self.t, self.v, self.c, e = [t for t, _ in pts], [v for _, v in pts], [], 0.0
        for (a, v), (b, _) in zip(pts, pts[1:] + [(CUTOFF, 0.0)]):
            self.c.append(e)
            e += v * (b - a) / 3.6e12

    def at(self, x):
        i = bisect.bisect_right(self.t, x) - 1
        return 0.0 if i < 0 else self.c[i] + self.v[i] * (x - self.t[i]) / 3.6e12

    def today(self, x):
        return self.at(x) - self.at(max(midnight(x), self.t[0] if self.t else x))


d_el = moved_series(el_new, el_old)
d_heat = moved_series(heat_new, heat_old)
d_parts = {"space": d_el["space"], "dhw": d_el["dhw"], "standby": d_el["standby"],
           "h_space": d_heat["space"], "h_dhw": d_heat["dhw"]}
moved_days = {midnight(t) for pts in d_parts.values() for t, v in pts if abs(v) > 1e-9}
d_nonzero = {k: Integral(pts) for k, pts in d_parts.items() if any(abs(v) > 1e-9 for _, v in pts)}
log(f"from 24 September: energy moved on {len(moved_days)} day(s)")

new_energy = {}
for k, m in ENERGY.items():
    pts = hm.points(m, START, CUTOFF)
    series = []
    for t, old in pts:
        new = old
        if old is not None and t != midnight(t):  # the 00:00 points of a day stay 0
            if t < EXACT_FROM:
                new = round(max(0.0, replay_today(k, t)) / 1000, 6)
            elif midnight(t) in moved_days:
                parts = [k] if not k.endswith("total") else []
                new = round(max(0.0, old + sum(d_nonzero[x].today(t) for x in parts if x in d_nonzero) / 1000), 6)
            if abs(new - old) > 5e-7:
                fix[m].append((t, old, new))
            else:
                new = old
        series.append((t, new))
    new_energy[k] = Step(series)
    log(f"{m}: {len(fix[m])} of {len(pts)} points change")

stats = collections.Counter()
for m, (hk, ek) in DCOP.items():
    for t, old in hm.points(m, START, CUTOFF):
        if t >= EXACT_FROM and midnight(t) not in moved_days:
            continue
        h, e = new_energy[hk].at(t), new_energy[ek].at(t)
        new = round(h / e, 2) if h > 0 and e > 0 else 0.0
        if new > 12:
            stats[f"{m}: over 12, old point kept"] += 1
        elif old is None or abs(new - old) > 0.005:
            fix[m].append((t, old, new))
    log(f"{m}: {len(fix[m])} points change")

# --- checks
def day_ends(a, b):
    """The last nanosecond of every day from a to b."""
    d = datetime.datetime.fromtimestamp(a / 1e9, TZ).date()
    while True:
        end = int(datetime.datetime.combine(d + datetime.timedelta(days=1), datetime.time(), TZ).timestamp() * 1e9) - 1
        if end >= b:
            return
        yield d, end
        d += datetime.timedelta(days=1)


print("\nthe replay against the rule's own shared-step integration, 24-26 September (kWh):")
for d, end in day_ends(EXACT_FROM, midnight(CUTOFF)):
    if midnight(end) in moved_days:
        continue
    print(f"  {d}: " + " | ".join(f"{k} {new_energy[k].at(end):.3f} vs {replay_today(k, end) / 1000:.3f}"
                                  for k in ("space", "dhw", "standby", "total", "h_total")))
meter = load("heatpump_energy_today")
dev = []
for d, end in day_ends(START, EXACT_FROM):
    mv, rp = meter.at(end), replay_today("plug", end) / 1000
    if mv and mv > 1:
        dev.append((rp - mv) / mv)
dev.sort()
median, p5, p95 = dev[len(dev) // 2], dev[len(dev) // 20], dev[len(dev) * 19 // 20]
print(f"the replay's plug energy against the plug's own day meter, {len(dev)} days before 24 September: median "
      f"{100 * median:+.2f} %, 5-95 % {100 * p5:+.2f} .. {100 * p95:+.2f} %")
print("\nper period, sum of the last point of each day, old → new (kWh):")
for a, b in [("2024-10-18", "2025-06-01"), ("2025-06-01", "2025-10-01"), ("2025-10-01", "2026-06-01"),
             ("2026-06-01", "2026-09-24"), ("2026-09-24", "2026-09-28")]:
    ta = int(datetime.datetime.fromisoformat(a).replace(tzinfo=TZ).timestamp() * 1e9)
    tb = min(CUTOFF, int(datetime.datetime.fromisoformat(b).replace(tzinfo=TZ).timestamp() * 1e9))
    ends = [end for _, end in day_ends(ta, tb)] + ([CUTOFF - 1] if tb == CUTOFF else [])
    cells = []
    for k, m in ENERGY.items():
        old_s = load(m, a=ta, b=tb)
        cells.append(f"{k} {sum(old_s.at(e) or 0 for e in ends):7.1f} → {sum(new_energy[k].at(e) or 0 for e in ends):7.1f}")
    print(f"  {a}..{b}: " + " | ".join(cells))
for m, pts in sorted(fix.items()):
    print(f"  {m}: {sum(o is not None for _, o, _ in pts)} points changed, {sum(o is None for _, o, _ in pts)} added")
for k, v in stats.items():
    print(f"  {k}: {v}")
sys.stdout.flush()
if MODE == "apply":
    assert abs(median) < 0.01 and p5 > -0.05 and p95 < 0.05, ("the replay misses the plug's meter", median, p5, p95)
    with gzip.open(sys.argv[3], "wt") as f:
        f.write("measurement,time_ns,old,new\n")
        for m, pts in fix.items():
            for t, old, new in pts:
                f.write(f"{m},{t},{'' if old is None else old},{new}\n")
    log(f"old values in {sys.argv[3]}")
    lines = [f"{m},item={m} value={float(new)!r} {t}" for m, pts in fix.items() for t, _, new in pts]
    for i in range(0, len(lines), 10000):
        hm.write(lines[i:i + 10000])
        time.sleep(0.5)  # let InfluxDB on the Pi keep up
    log(f"written {len(lines)} points")
