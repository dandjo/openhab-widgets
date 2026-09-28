#!/usr/bin/env python3
"""Recompute the E-Car history with the charge state machine of the rule air_conditioning_circuit_power, from
the first point of e_car_power (29 May 2026) up to CUTOFF, when the rule took over (openHAB stopped for its
deploy). The state machine is replayed over the circuit's and Faikin's points plus a minute tick, as the rule
runs. e_car_power is overwritten at its existing points and gets a point where a charge starts or ends;
air_conditioning_unit_power (circuit minus car) follows at the same times. e_car_energy_today/_total are
integrated anew at their existing points up to the start of this run, and air_conditioning_unit_energy_today/
_total are the meter's minus the car's; the car's electrical values go to 0 where it no longer charges. Old
values go to a gzipped CSV first. openHAB keeps running: the energy rule's next run builds on the new points.
Usage: e_car_state_rebuild.py check|apply CUTOFF_NS [BACKUP.csv.gz]"""
import bisect
import collections
import datetime
import gzip
import json
import sys
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

INFLUX = "http://127.0.0.1:8086"
TZ = ZoneInfo("Europe/Vienna")
DAY = int(86400e9)
MODE, CUTOFF = sys.argv[1], int(sys.argv[2])
NOW = time.time_ns() - int(5e9)  # points the rules write while this runs stay theirs


def query(q):
    url = f"{INFLUX}/query?" + urllib.parse.urlencode({"db": "openhab", "epoch": "ns", "q": q})
    series = json.load(urllib.request.urlopen(url, timeout=600))["results"][0].get("series", [])
    return [(t, v) for t, v in series[0]["values"]] if series else []


def points(m, a, b):
    out, step = [], 14 * DAY
    for s in range(a, b, step):
        out += query(f'SELECT value FROM "{m}" WHERE time >= {s} AND time < {min(b, s + step)}')
    return out


def write(lines):
    for i in range(0, len(lines), 5000):
        req = urllib.request.Request(f"{INFLUX}/write?" + urllib.parse.urlencode({"db": "openhab", "precision": "ns"}),
                                     data="\n".join(lines[i:i + 5000]).encode(), method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            assert resp.status == 204, resp.status


class Last:
    """The last value at or before a time."""
    def __init__(self, pts, default=None):
        self.t, self.v, self.default = [t for t, _ in pts], [v for _, v in pts], default

    def at(self, t):
        i = bisect.bisect_right(self.t, t) - 1
        return self.v[i] if i >= 0 and self.v[i] is not None else self.default


class StateMachine:
    """The rule's split() in Python; its output matched the rule's JavaScript on every evaluation since
    29 May 2026 (run in GraalJS). Times in ns."""
    def __init__(self):
        self.base = {True: 20.0, False: 10.0}
        self.hist, self.charging, self.low_since, self.steady_since = [], None, None, None
        self.own, self.started, self.dev_sign, self.dev_n = 0.0, None, 0, 0

    def start(self, t):
        self.charging, self.low_since = True, None
        self.own, self.started, self.dev_sign, self.dev_n = 0.0, t, 0, 0

    def step(self, P, F, S, t, PF, V):
        f = F or 0
        rest = max(0, P - f)
        b = self.base[S]
        report = not self.hist or self.hist[-1][0] != P
        if self.charging is None:
            self.charging = False
            if rest >= 1200:
                self.start(t)
        elif report and self.hist:
            rise = max((P - hp) - max(0, f - hf) for hp, hf in self.hist[-2:])
            drop = min((P - hp) - min(0, f - hf) for hp, hf in self.hist[-2:])
            if not self.charging and rise >= 1200 and rest >= 1200:
                self.start(t)
            elif self.charging and drop <= -1200 and rest < 1200:
                self.charging = False
        if report:
            self.hist = (self.hist + [(P, f)])[-3:]
        if self.charging:
            if rest < 300:
                self.charging = False
            elif rest - b < 1000:
                self.low_since = self.low_since if self.low_since is not None else t
                if t - self.low_since >= 10e9:
                    self.charging = False
            else:
                self.low_since = None
        elif rest >= 1200 and (PF or 0) >= 0.95:
            self.steady_since = self.steady_since if self.steady_since is not None else t
            if t - self.steady_since >= 60e9:
                self.start(t)
        else:
            self.steady_since = None
        if not self.charging:
            self.low_since = None
            if f == 0 and rest < 150:
                self.base[S] = b + 0.1 * (rest - b)
            return 0.0
        self.steady_since = None
        volts = V if V and V > 150 else 230.0
        amps = (rest - b) / volts
        car = rest - b
        if not self.own or t - self.started < 30e9:
            self.own = max(self.own, min(amps, 2300.0 / volts))
        else:
            dev = amps - self.own
            if report:
                sign = 1 if dev > 0.015 * self.own else -1 if dev < -0.015 * self.own else 0
                self.dev_n = self.dev_n + 1 if sign and sign == self.dev_sign else 1 if sign else 0
                self.dev_sign = sign
            lasting = self.dev_n >= 3
            if (f == 0 and (dev <= 0.015 * self.own or (self.dev_sign > 0 and lasting))) or \
                    (f != 0 and self.dev_sign < 0 and lasting):
                self.own = amps
            car = min(rest - b, self.own * volts * 1.015)
        return max(0.0, min(car, 2300.0, P - b))


first = query('SELECT value FROM "e_car_power" ORDER BY time ASC LIMIT 1')[0][0]
assert first < CUTOFF <= NOW, (first, CUTOFF, NOW)

# the replay over the rule's inputs, with the minute cron between them
inputs = {"P": "air_conditioning_power", "F": "faikout_perfera_power", "S": "faikout_perfera_switch",
          "PF": "air_conditioning_power_factor", "V": "air_conditioning_voltage"}
before = {k: query(f'SELECT value FROM "{m}" WHERE time < {first} ORDER BY time DESC LIMIT 1') for k, m in inputs.items()}
stream = sorted((t, k, v) for k, m in inputs.items() for t, v in points(m, first, CUTOFF))
cur = {k: (pts[0][1] if pts else None) for k, pts in before.items()}
cur["F"] = cur["F"] or 0.0
sm = StateMachine()
evals = []  # (t, car) after every evaluation
minute = (first // 60_000_000_000 + 1) * 60_000_000_000


def evaluate(t):
    if cur["P"] is not None:
        evals.append((t, round(sm.step(cur["P"], cur["F"], cur["S"] in (1, 1.0, "ON"), t, cur["PF"], cur["V"]), 2)))


for t, k, v in stream:
    while minute <= t:
        evaluate(minute)
        minute += 60_000_000_000
    cur[k] = v
    if k not in ("PF", "V"):
        evaluate(t)
car_new = Last(evals, 0.0)

# e_car_power: existing points before the cutoff, plus the charge starts and ends
stored_power = points("e_car_power", first, NOW)
fix = collections.defaultdict(list)  # measurement → (t, old, new); old None: a new point
existing = {t for t, _ in stored_power}
for t, old in stored_power:
    if t < CUTOFF:
        new = car_new.at(t)
        if old is None or abs(new - old) > 0.005:
            fix["e_car_power"].append((t, old, new))
prev = 0.0
transitions = []
for t, c in evals:
    if (c > 0) != (prev > 0):
        transitions.append((t, c))
    prev = c
edges = [(t, c) for t, c in transitions if t not in existing]
print(f"charge starts and ends: {len(transitions)}, of them at a time without a stored point: {len(edges)}")
fix["e_car_power"] += [(t, None, c) for t, c in edges]

# the new step series of the car: replayed before the cutoff, the rule's own points after it
series = sorted([(t, car_new.at(t)) for t, _ in stored_power if t < CUTOFF] + edges +
                [(t, v) for t, v in stored_power if t >= CUTOFF])
car_at = Last(series, 0.0)

# air_conditioning_unit_power: circuit minus car, at its existing points before the cutoff and at the edges
circuit = Last(points("air_conditioning_power", first, CUTOFF))
for t, old in points("air_conditioning_unit_power", first, CUTOFF) + [(t, None) for t, _ in edges]:
    p = circuit.at(t)
    if p is not None:
        new = round(max(0.0, p - car_at.at(t)), 2)
        if old is None or abs(new - old) > 0.005:
            fix["air_conditioning_unit_power"].append((t, old, new))
for m in ("e_car_apparent_power", "e_car_reactive_power", "e_car_power_factor", "e_car_current"):
    for t, old in points(m, first, CUTOFF):
        if car_at.at(t) == 0 and old not in (0, 0.0, None):
            fix[m].append((t, old, 0.0))

# energy of the car since its first point, at any time: the step series integrated (W·ns → kWh)
cum_t, cum_e, e = [], [], 0.0
for (t0, v0), (t1, _) in zip(series, series[1:] + [(NOW, 0)]):
    cum_t.append(t0)
    cum_e.append(e)
    e += v0 * (t1 - t0) / 3.6e15


def energy(t):
    i = bisect.bisect_right(cum_t, t) - 1
    return 0.0 if i < 0 else cum_e[i] + series[i][1] * (t - cum_t[i]) / 3.6e15


def midnight(t):
    d = datetime.datetime.fromtimestamp(t / 1e9, TZ)
    return int(datetime.datetime.combine(d.date(), datetime.time(), TZ).timestamp() * 1e9)


def today(t):
    return energy(t) - energy(max(first, midnight(t)))


meter_today = Last(points("air_conditioning_energy_today", first, NOW))
meter_total = Last(points("air_conditioning_energy_total", first, NOW))
for m, fn in (("e_car_energy_today", today), ("e_car_energy_total", energy),
              ("air_conditioning_unit_energy_today",
               lambda t: None if meter_today.at(t) is None else max(0.0, meter_today.at(t) - today(t))),
              ("air_conditioning_unit_energy_total",
               lambda t: None if meter_total.at(t) is None else max(0.0, meter_total.at(t) - energy(t)))):
    for t, old in points(m, first, NOW):
        if midnight(t) == t and m.endswith("_today"):
            continue  # the 00:00 points of a day stay 0
        new = fn(t)
        if new is not None:
            new = round(new, 3)
            if old is None or abs(new - old) > 0.0005:
                fix[m].append((t, old, new))

stored_total = query('SELECT last(value) FROM "e_car_energy_total"')[0][1]
print(f"replayed {len(stream)} points and {len(evals)} evaluations up to "
      f"{datetime.datetime.fromtimestamp(CUTOFF / 1e9, TZ).isoformat(timespec='seconds')}; "
      f"learned base loads: off {sm.base[False]:.1f} W, on {sm.base[True]:.1f} W")
print(f"car energy since {datetime.datetime.fromtimestamp(first / 1e9, TZ).date()}: "
      f"{stored_total:.2f} kWh stored → {energy(NOW):.2f} kWh")
for m, pts in fix.items():
    print(f"  {m}: {sum(o is not None for _, o, _ in pts)} points changed, {sum(o is None for _, o, _ in pts)} added")
day_old = {}
for t, v in points("e_car_energy_today", midnight(NOW) - 4 * DAY, NOW):
    day_old[datetime.datetime.fromtimestamp(t / 1e9, TZ).date()] = (t, v)
print("car energy per day (last stored point of the day, old → new):",
      [(d.isoformat(), v, round(today(t), 3)) for d, (t, v) in sorted(day_old.items())])
if MODE == "apply":
    with gzip.open(sys.argv[3], "wt") as f:
        f.write("measurement,time_ns,old,new\n")
        for m, pts in fix.items():
            for t, old, new in pts:
                f.write(f"{m},{t},{'' if old is None else old},{new}\n")
    write([f"{m},item={m} value={float(new)!r} {t}" for m, pts in fix.items() for t, _, new in pts])
    print("written; old values in", sys.argv[3])
