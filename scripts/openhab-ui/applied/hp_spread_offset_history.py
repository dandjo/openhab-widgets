#!/usr/bin/env python3
"""Take the inlet sensor's offset out of the heat pump's heating powers in its history, the way heatpump_metering does
since 14 October 2026 (applied/hp_spread_offset.py; user, 2026-10-14: "rechne die historie neu"), and make what derives
from them follow: the instantaneous COPs, the day heat energies and the daily COPs.

The offset: while the pump circulates and nothing heats, the leaving water after the backup heater reads 0.70 K and the
one before it 0.60 K above the inlet (every such minute since September 2024, no drift), so flow × spread showed 0.3 to
0.6 kW of heat with only the pump running and some 15 to 20 % too much while running. The corrected rule counts heat
only while the compressor (its isInverter: the circuit over 70 W, a frequency or a primary current) or the backup heater
runs, from the spread less the offset: after the heater flow × 69.834 × 0.7 W less (l/min × 60 × 1.1639 Wh/(kg·K)),
before it flow × 69.834 × 0.6 W less. A value the cap held (applied/hp_heat_cap_history.py: at most what the compressor
can deliver) stays: there flow × spread lay over the cap by far more than the offset. Negative values (defrost) take
the offset too. Raw points are taken run by run as in the cap rewrite (the five powers within 100 ms, the inputs at
the run's first point, a heater on up to 100 ms before counts). Points older than the downsampler's cutoff that lie on
a minute are time-weighted minute means: a minute without any source (frequency, primary current and both heater steps
0, circuit mean at most 70 W) becomes 0, any other loses the offset at the minute's mean flow (in a minute's pump-only
part the phantom heat is that offset, so the mean comes out as if gated). Space and DHW lose what the after-heater heat
lost at their run (raw: the part that holds it, DHW with or without the booster's 2 kW; minute means: in proportion to
their heat where both hold some, the valve switched within the minute); the total loses what space and DHW lost at its
run, so space + DHW still equals the total. A CUTOFF (local time) leaves points from then on as they are, for the day
the corrected rule went live: its counters then lose the energy removed before it.

Energy, daily COPs: as in hp_heat_cap_history.py: per day the removed power of space and DHW (original − corrected) is
integrated like the counters were (trapezoidal on one shared time step, a run every 3 s between the points, a silence
over five minutes not bridged, a minute mean's removal counted once its minute is over), at every counter point the
removed energy since midnight is subtracted from space and DHW, the total takes their sum at its run; between two
points no counter gives more than it counted there (a shortfall follows later), a value that would fall below zero is
held at 0. The electrical energies stay. Daily COPs are recomputed at their points where the heat changed; over 12
keeps the old point, as the rule would not write it. Instantaneous COPs follow at their points by corrected/original
heat (minute means by the minute's mean heats); 0 where the corrected heat is not positive, as the rule writes then.

From 31 October 2024, as the cap (before, the rule held powers for up to 15 minutes after the compressor stopped and
its counters do not integrate them), to 13 October 2026; 14 October 2026 with the cutoff at the switch.
check: dry run with the numbers. apply: plan again, refuse if a check fails or a day's heat would rise, write every
original point to the journal (~/.local/state/spread_offset_history/journal.csv.gz, or $SPREAD_STATE: measurement, tag,
time, old, new, raw) before the first write, write in batches (never while influx-downsample.service runs or within
20 minutes before its 01:00 start, nor after it moved on), then verify; an interrupted apply resumes from the journal.
verify: re-query and check. undo: write the journal's old values back; raw points downsampled since are skipped.
Usage: hp_spread_offset_history.py check|apply [FIRST_DAY LAST_DAY [CUTOFF]] | verify | undo   (on homepi, as pi)"""
import bisect
import collections
import datetime
import gzip
import json
import math
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

INFLUX = "http://127.0.0.1:8086"
TZ = ZoneInfo("Europe/Vienna")
S = 10 ** 9
MS = 10 ** 6
MIN = 60 * S
DAY = 86400 * S
MAX_GAP = 300 * S  # a longer silence of the rule (openHAB or ESPAltherma down) counts nothing
TICK = 3 * S  # the rule runs on every ESPAltherma message, about every 3 s
RUN = 100 * MS  # the points of one run lie within a few ms, under load up to ~100 ms
FIRST_DAY = datetime.date(2024, 10, 31)
LAST_DAY = datetime.date(2026, 10, 13)  # later only with a cutoff
STATE_DIR = os.environ.get("SPREAD_STATE", os.path.expanduser("~/.local/state/spread_offset_history"))
OFF_BEFORE, OFF_AFTER = 0.6, 0.7  # K the leaving water before / after the backup heater reads above the inlet
WATTS = 60 * 1.1639  # W per l/min and K
CUTOFF = math.inf  # ns; points from then on stay (set from the command line)
JOURNAL = os.path.join(STATE_DIR, "journal.csv.gz")
STATE = os.path.join(STATE_DIR, "state.json")
DOWNSAMPLE_STATE = os.path.expanduser("~/.local/state/influx_downsample/state.json")
P = "espaltherma_"
INPUT = {"circuit": "heatpump_power", "lwt": P + "leaving_water_temp_before_buh", "outdoor": P + "ext_ambient_temp",
         "buh1": P + "buh_step1_mode", "buh2": P + "buh_step2_mode", "bsh": P + "bsh_mode",  # switches as 1/0
         "flow": P + "flow_sensor", "freq": P + "inv_frequency", "current": P + "inv_primary_current"}
SWITCHES = ("buh1", "buh2", "bsh")
POWER = {"before": P + "heating_power_before_buh", "after": P + "heating_power_after_buh",
         "space": P + "heating_power_space", "dhw": P + "heating_power_dhw", "total": P + "heating_power"}
EL = {"space": P + "electrical_power_space", "dhw": P + "electrical_power_dhw", "total": P + "electrical_power"}
COP = {"space": P + "cop_space", "dhw": P + "cop_dhw", "total": P + "cop"}
HEAT = {"space": P + "heating_energy_space_today", "dhw": P + "heating_energy_dhw_today",
        "total": P + "heating_energy_today"}
ENERGY = {"space": P + "energy_space_today", "dhw": P + "energy_dhw_today", "total": P + "energy_today"}
DCOP = {"space": P + "dcop_space", "dhw": P + "dcop_dhw", "total": P + "dcop"}
PARTS = ("space", "dhw", "total")
ALL = [m for group in (INPUT, POWER, EL, COP, HEAT, ENERGY, DCOP) for m in group.values()]
WRITTEN = [m for group in (POWER, COP, HEAT, DCOP) for m in group.values()]
t0 = time.time()


def log(msg):
    print(f"[{time.time() - t0:6.0f} s] {msg}", flush=True)


# ---------------------------------------------------------------- InfluxDB

def query(q):
    url = f"{INFLUX}/query?" + urllib.parse.urlencode({"db": "openhab", "epoch": "ns", "q": q})
    with urllib.request.urlopen(url, timeout=900) as r:
        results = json.load(r)["results"]
    out = []
    for res in results:
        if "error" in res:
            raise RuntimeError(f"{q[:200]}: {res['error']}")
        out += res.get("series", [])
    return out


def write(lines):
    req = urllib.request.Request(f"{INFLUX}/write?" + urllib.parse.urlencode({"db": "openhab", "rp": "autogen",
                                                                             "precision": "ns"}),
                                 data="\n".join(lines).encode(), method="POST")
    with urllib.request.urlopen(req, timeout=300) as resp:
        assert resp.status == 204, resp.status


def line(m, tag, t, v):
    """A point with exactly the tag set it has: the downsampler writes without tags, openHAB with item=<name>."""
    return f"{m},item={tag} value={float(v)!r} {t}" if tag else f"{m} value={float(v)!r} {t}"


def raw_from():
    """Up to where the downsampler has turned the raw points into minute values (ns)."""
    weeks = json.load(open(DOWNSAMPLE_STATE))["weeks"]
    until = 0
    for week in sorted(weeks):
        until = max(until, weeks[week].get("until", 0))
        if not weeks[week].get("done"):
            break
    return until


def downsampler_busy():
    """True while influx-downsample.service runs or its 01:00 start is less than 20 minutes away."""
    active = subprocess.run(["systemctl", "is-active", "influx-downsample.service"], capture_output=True,
                            text=True).stdout.strip()
    now = datetime.datetime.now(TZ)
    return active in ("active", "activating", "reloading", "deactivating") or (now.hour == 0 and now.minute >= 40)


def midnight(day):
    return int(datetime.datetime.combine(day, datetime.time(), TZ).timestamp()) * S


def day_of(t):
    return datetime.datetime.fromtimestamp(t // S, TZ).date()


def days(first, last):
    d = first
    while d <= last:
        yield d
        d += datetime.timedelta(days=1)


# ---------------------------------------------------------------- series

class Series:
    """A persisted series as a step function: the points of a day [(t, v, tag)], the last one before it first."""

    def __init__(self, carry, pts):
        self.carry = carry
        self.pts = pts
        allp = ([carry] if carry else []) + pts
        self.t = [p[0] for p in allp]
        self.v = [p[1] for p in allp]
        self.times = {p[0] for p in pts}
        self._cum = None

    def at(self, t):
        i = bisect.bisect_right(self.t, t) - 1
        return self.v[i] if i >= 0 else None

    def wmean(self, a, b):
        """The time-weighted mean over [a, b), from the first value on if the series starts within."""
        if not self.t or b <= self.t[0]:
            return None
        if self._cum is None:
            c, cum = 0.0, [0.0]
            for i in range(1, len(self.t)):
                c += self.v[i - 1] * (self.t[i] - self.t[i - 1])
                cum.append(c)
            self._cum = cum
        a = max(a, self.t[0])

        def f(x):
            i = bisect.bisect_right(self.t, x) - 1
            return self._cum[i] + self.v[i] * (x - self.t[i])
        return (f(b) - f(a)) / (b - a)

    def with_values(self, carry_v, values):
        """The same points with other values."""
        carry = (self.carry[0], carry_v, self.carry[2]) if self.carry else None
        return Series(carry, [(t, v, tag) for (t, _, tag), v in zip(self.pts, values)])


def load(day, names=ALL):
    """{measurement: Series} of a local day, with each one's last point within two days before it."""
    a, b = midnight(day), midnight(day + datetime.timedelta(days=1))
    sel = ", ".join(f'"{m}"' for m in names)
    carry, pts = {}, collections.defaultdict(list)
    for s in query(f"SELECT last(value) FROM {sel} WHERE time >= {a - 2 * DAY} AND time < {a} GROUP BY *"):
        tag = (s.get("tags") or {}).get("item") or ""
        for t, v in s["values"]:
            if v is not None and (s["name"] not in carry or t >= carry[s["name"]][0]):
                carry[s["name"]] = (t, float(v), tag)
    for s in query(f"SELECT value FROM {sel} WHERE time >= {a} AND time < {b} GROUP BY *"):
        tag = (s.get("tags") or {}).get("item") or ""
        pts[s["name"]] += [(t, float(v), tag) for t, v in s["values"] if v is not None]
    return {m: Series(carry.get(m), sorted(pts[m])) for m in names}, a, b


def apply_changes(data, changes):
    """The day's data with the changed points' new values."""
    by_m = collections.defaultdict(dict)
    for m, tag, t, _, new in changes:
        by_m[m][(t, tag)] = new
    out = dict(data)
    for m, ch in by_m.items():
        s = data[m]
        out[m] = s.with_values(s.carry[1] if s.carry else None, [ch.get((t, tag), v) for t, v, tag in s.pts])
    return out


# ---------------------------------------------------------------- the cap

class Caps:
    """The cap at every point of the five powers: per run of the rule for raw points, per minute for minute means."""

    def __init__(self, data, raw_until):
        self.d, self.raw_until = data, raw_until
        self.inp = {k: data[m] for k, m in INPUT.items()}
        self._caps, self._src = {}, {}
        self.run_start, self.run_end = {}, {}
        pts = sorted((t, k) for k, m in POWER.items() for t, _, _ in data[m].pts if not self.minute(t))
        run, seen = [], set()
        for t, k in pts + [(math.inf, None)]:
            if run and (t - run[-1] > RUN or k in seen):
                for x in run:
                    self.run_start[x], self.run_end[x] = run[0], run[-1]
                run, seen = [], set()
            run.append(t)
            seen.add(k)

    def minute(self, t):
        return t < self.raw_until and t % MIN == 0

    def cap(self, t):
        """(compressor_max, backup heater, booster heater) for the point at t, or None without a circuit reading."""
        t = self.run_start.get(t, t)
        if t in self._caps:
            return self._caps[t]
        if self.minute(t):
            f = lambda s: s.wmean(t, t + MIN)
            sw = f
        else:
            f = lambda s: s.at(t)
            sw = lambda s: max(s.at(t - RUN) or 0.0, s.at(t) or 0.0)
        circuit = f(self.inp["circuit"])
        res = None
        if circuit is not None:
            lwt, outdoor = f(self.inp["lwt"]), f(self.inp["outdoor"])
            tc = (35.0 if lwt is None else lwt) + 273.15 + 3
            te = (7.0 if outdoor is None else outdoor) + 273.15 - 7
            cc = min(12000.0, 0.8 * tc / max(5.0, tc - te) * max(0.0, circuit))
            buh = 2000.0 * (sw(self.inp["buh1"]) or 0.0) + 4000.0 * (sw(self.inp["buh2"]) or 0.0)
            bsh = 2000.0 * (sw(self.inp["bsh"]) or 0.0)
            res = (cc, buh, bsh)
        self._caps[t] = res
        return res

    def limit(self, k, t):
        c = self.cap(t)
        if c is None:
            return None
        cc, buh, bsh = c
        return {"before": cc, "after": cc + buh, "space": cc + buh, "dhw": cc + buh + bsh, "total": cc + buh + bsh}[k]

    def end(self, t):
        """The last point of t's run: where the run's other powers are found."""
        return self.run_end.get(t, t)

    def source(self, t):
        """(whether the compressor or the backup heater ran, the flow in l/min) for the point at t: raw points as the
        rule saw them at its run, minute means whether any source ran within the minute and its mean flow."""
        t = self.run_start.get(t, t)
        if t in self._src:
            return self._src[t]
        inp = self.inp
        if self.minute(t):
            f = lambda s: s.wmean(t, t + MIN) or 0.0
            on = f(inp["circuit"]) > 70 or any(f(inp[k]) > 0 for k in ("freq", "current", "buh1", "buh2"))
        else:
            f = lambda s: s.at(t) or 0.0
            sw = lambda s: max(s.at(t - RUN) or 0.0, s.at(t) or 0.0)
            on = f(inp["circuit"]) > 70 or f(inp["freq"]) > 0 or f(inp["current"]) > 0 \
                or sw(inp["buh1"]) > 0 or sw(inp["buh2"]) > 0
        self._src[t] = (on, max(0.0, f(inp["flow"])))
        return self._src[t]


# ---------------------------------------------------------------- one day

class Day:
    """The corrected powers and what follows from them for one day."""

    def __init__(self, day, data, a, b, raw_until):
        self.day, self.d, self.a, self.b, self.raw_until = day, data, a, b, raw_until
        self.caps = Caps(data, raw_until)
        self.changes = []  # (measurement, tag, t, old, new)
        self.stats = collections.Counter()
        self.max_power = {}  # measurement -> (max original, max corrected)
        self.correct_powers()
        self.integrate()
        self.correct_energies()
        self.correct_dcops()
        self.correct_cops()

    def minute(self, t):
        return self.caps.minute(t)

    def fixed(self, k, t, v, offset):
        """The before- or after-heater heat at t without the offset: 0 without a source, a value the cap held stays."""
        if t >= CUTOFF or v == 0:
            return v
        on, flow = self.caps.source(t)
        if not on:
            self.stats["power points without a source, set to 0"] += 1
            return 0.0
        lim = self.caps.limit(k, t)
        if lim is not None and v >= lim - 0.01:
            self.stats["power points the cap held, kept"] += 1
            return v
        nv = v - WATTS * offset * flow
        return nv if self.minute(t) else round(nv, 2)

    def holds_after(self, k, t, v):
        """The share of the after-heater heat at t's run that part k holds: raw points 1 or 0 by its value (DHW with or
        without the booster's 2 kW), minute means in proportion to space's and DHW's heat where both have a mean."""
        e = self.caps.end(t)
        a = self.old["after"].at(e)
        if a is None or a == 0:
            return 0.0
        if not self.minute(t):
            cands = (v, v - 2000.0) if k == "dhw" else (v,)
            return 1.0 if any(abs(c - a) <= 0.02 for c in cands) else 0.0
        bsh = 2000.0 * (self.caps.inp["bsh"].wmean(t, t + MIN) or 0.0)
        own = {"space": self.old["space"], "dhw": self.old["dhw"]}
        heat = {}
        for part, s in own.items():
            x = v if part == k else (s.at(t) if t in s.times else None)
            heat[part] = None if x is None else (x - bsh if part == "dhw" else x)
        mine, other = heat[k], heat["dhw" if k == "space" else "space"]
        if mine is None or mine <= 0:
            return 0.0
        if other is None or other <= 0:
            return 1.0
        self.stats["minute means with the valve switching, offset in proportion"] += 1 if k == "space" else 0
        return mine / (mine + other)

    def correct_powers(self):
        self.old = {k: self.d[m] for k, m in POWER.items()}
        self.new = {}
        for k, off in (("before", OFF_BEFORE), ("after", OFF_AFTER)):
            s = self.old[k]
            carry_v = self.fixed(k, s.carry[0], s.carry[1], off) if s.carry else None
            self.new[k] = s.with_values(carry_v, [self.fixed(k, t, v, off) for t, v, _ in s.pts])
        # space and DHW: what the after-heater heat lost at their run, by the share they hold of it
        for k in ("space", "dhw"):
            s = self.old[k]

            def part(t, v):
                if t >= CUTOFF or v == 0:
                    return v
                e = self.caps.end(t)
                ao, an = self.old["after"].at(e), self.new["after"].at(e)
                if ao is None or an is None or ao == an:
                    return v
                share = self.holds_after(k, t, v)
                if share == 0:
                    return v
                nv = v - share * (ao - an)
                return nv if self.minute(t) else round(nv, 2)
            carry_v = part(*s.carry[:2]) if s.carry else None
            self.new[k] = s.with_values(carry_v, [part(t, v) for t, v, _ in s.pts])
        # the total: what space and DHW lost at its run
        tot = self.old["total"]
        vals = []
        for t, v, _ in tot.pts:
            if t >= CUTOFF:
                vals.append(v)
                continue
            e = self.caps.end(t)
            parts = [(self.old[k].at(e), self.new[k].at(e)) for k in ("space", "dhw")]
            if any(o is None or n is None for o, n in parts):
                vals.append(v)
                continue
            nv = v - sum(o - n for o, n in parts)
            vals.append(nv if self.minute(t) else round(nv, 2))
        self.new["total"] = tot.with_values(tot.carry[1] if tot.carry else None, vals)
        for k, m in POWER.items():
            o, n = self.old[k], self.new[k]
            self.max_power[m] = (max((v for _, v, _ in o.pts), default=None),
                                 max((v for _, v, _ in n.pts), default=None))
            for (t, v, tag), (_, nv, _) in zip(o.pts, n.pts):
                if abs(nv - v) > 1e-9:
                    self.changes.append((m, tag, t, v, nv))

    def _set(self, k, i, v):
        s = self.new[k]
        t, _, tag = s.pts[i]
        s.pts[i] = (t, v, tag)
        s.v[i + (1 if s.carry else 0)] = v
        s._cum = None

    def removed(self, k, t):
        o, n = self.old[k].at(t), self.new[k].at(t)
        return 0.0 if o is None or n is None else o - n

    def integrate(self):
        """Cumulative removed energy (Wh) since midnight per part on one shared time step: every point of the powers,
        of the counters and of espaltherma_energy_today (rule runs), between them a run every 3 s, trapezoidal; a
        silence over five minutes is not bridged. Also the original total power's integral, to compare with the
        counter."""
        grid = {self.a}
        for k in PARTS:
            grid |= self.old[k].times | self.d[HEAT[k]].times
        grid |= self.d[ENERGY["total"]].times
        self.grid = sorted(grid)
        self.gi = {t: i for i, t in enumerate(self.grid)}
        self.power_times = sorted(self.old["space"].times | self.old["dhw"].times | self.old["total"].times)
        self.cum = {k: [0.0] for k in PARTS}
        self.orig_integral, self.gap_lost = 0.0, 0.0
        prev = None
        for t in self.grid:
            r = {"space": self.removed("space", t), "dhw": self.removed("dhw", t)}
            r["total"] = r["space"] + r["dhw"]
            p = self.old["total"].at(t) or 0.0
            if prev is not None:
                pt, pr, pp = prev
                dt = t - pt
                tail = dt - TICK * max(0, math.ceil(dt / TICK) - 1)
                for k in PARTS:
                    add = (pr[k] * (dt - tail) + (pr[k] + r[k]) / 2 * tail) / 3.6e12
                    if dt <= MAX_GAP:
                        self.cum[k].append(self.cum[k][-1] + add)
                    else:
                        self.cum[k].append(self.cum[k][-1])
                        if k == "total":
                            self.gap_lost += add
                if dt <= MAX_GAP:
                    self.orig_integral += (pp * (dt - tail) + (pp + p) / 2 * tail) / 3.6e12
            prev = (t, r, p)

    def removed_energy(self, k, t):
        """Removed energy of part k from midnight up to the run at t (Wh), t a grid point. A minute mean's removal
        counts once its minute is over: the counters were integrated on the raw points, and when within the minute
        the overshoot came is unknown."""
        i = bisect.bisect_right(self.power_times, t) - 1
        if i >= 0:
            p = self.power_times[i]
            if self.minute(p) and t < p + MIN:
                return self.cum[k][self.gi[p]]
        return self.cum[k][self.gi[t]]

    def correct_energies(self):
        """Subtract the removed energy from every counter point of the day. Between two points of a counter no more
        is taken than it counted there (a shortfall follows later; a defrost, negative heat, gives nothing); a value
        that would fall below zero is held at 0, as the recomputed history holds it. The total takes what space and
        DHW took at its run, so the split still sums exactly."""
        self.heat_old, self.heat_new, eff = {}, {}, {}

        def correct(k, takes):
            m, s = HEAT[k], self.d[HEAT[k]]
            values, out = [], []
            for (t, v, tag), b in zip(s.pts, takes):
                nv = round(v - b / 1000, 6) if b != 0 else v
                if nv < 0 <= v:
                    nv = 0.0
                    self.stats[f"{m}: held at 0"] += 1
                if abs(nv - v) <= 5e-7:
                    nv = v
                values.append(nv)
                out.append((t, (v - nv) * 1000))
                if nv != v:
                    self.changes.append((m, tag, t, v, nv))
            self.heat_old[k] = s
            self.heat_new[k] = s.with_values(s.carry[1] if s.carry else None, values)
            eff[k] = out

        for k in ("space", "dhw"):
            prev_v, b, takes = 0.0, 0.0, []
            for t, v, _ in self.d[HEAT[k]].pts:
                if t > self.a:
                    b = min(self.removed_energy(k, t), b + max(0.0, (v - prev_v) * 1000))
                takes.append(b)
                prev_v = v
            correct(k, takes)

        def part(k, t):
            pts = eff[k]
            i = bisect.bisect_right(pts, (t, math.inf)) - 1
            return pts[i][1] if i >= 0 else 0.0
        # the total's run: its points come right after the parts', within some 100 ms
        correct("total", [part("space", t + RUN) + part("dhw", t + RUN) if t > self.a else 0.0
                          for t, _, _ in self.d[HEAT["total"]].pts])
        self.taken_total = eff["total"]
        self.taken = eff
        pts = self.d[HEAT["total"]].pts
        if pts:
            self.stats["removal the counters did not count, not taken (Wh)"] += round(
                self.removed_energy("total", pts[-1][0]) - eff["total"][-1][1], 3)

    def correct_dcops(self):
        for k, m in DCOP.items():
            ho, hn, e = self.heat_old[k], self.heat_new[k], self.d[ENERGY[k]]
            for t, old, tag in self.d[m].pts:
                h0, h = ho.at(t), hn.at(t)
                if h0 is None or h is None or abs(h - h0) <= 5e-7:
                    continue
                el = e.at(t)
                new = round(h / el, 2) if h > 0 and el is not None and el > 0 else 0.0
                if new > 12:
                    self.stats[f"{m}: over 12, old point kept"] += 1
                elif abs(new - old) > 0.004:
                    self.changes.append((m, tag, t, old, new))

    def correct_cops(self):
        for k, m in COP.items():
            o, n, el = self.old[k], self.new[k], self.d[EL[k]]
            for t, old, tag in self.d[m].pts:
                if self.minute(t):
                    ho, hn = o.wmean(t, t + MIN), n.wmean(t, t + MIN)
                    if ho is None or hn is None or hn >= ho - 1e-9:
                        continue
                    new = old * hn / ho if hn > 0 and ho > 0 else 0.0
                    if new < old - 1e-9:
                        self.changes.append((m, tag, t, old, new))
                else:
                    ho, hn = o.at(t), n.at(t)
                    if ho is None or hn is None or hn >= ho - 1e-9 or ho <= 0:
                        continue
                    new = round(old * hn / ho, 2) if hn > 0 else 0.0
                    if abs(new - old) > 0.004:
                        self.changes.append((m, tag, t, old, new))
            # where the original ratio was over 10 (not written) and the corrected one is not, the corrected rule would
            # have written a point; counted, not added
            for t, v, _ in o.pts:
                if self.minute(t):
                    continue
                nv, e = n.at(t), el.at(t)
                if nv is not None and nv < v - 1e-9 and e is not None and e > 0 and v / e > 10 >= nv / e > 0:
                    self.stats[f"{m}: a point the corrected rule would have written, not added"] += 1

    # ------------------------------------------------------------ results

    def day_heat(self, new=True):
        s = (self.heat_new if new else self.heat_old)["total"]
        return s.pts[-1][1] if s.pts else 0.0

    def day_removed(self):
        """Removed heat of the day (Wh): taken at the day's last heat counter point."""
        return self.taken_total[-1][1] if self.taken_total else 0.0

    def day_dcop(self, new=True):
        h = self.day_heat(new)
        s = self.d[ENERGY["total"]]
        e = s.pts[-1][1] if s.pts else 0.0
        return round(h / e, 2) if h > 0 and e > 0 else 0.0


# ---------------------------------------------------------------- checks on a day's data

def invariants(day, data, raw_until, old=None):
    """Counts: a power over its cap (+1 W); space + DHW − total of the powers (at each total point, with its run's
    parts) and of the heat energies (likewise) further from 0 than in the original by over 1 W / 1 Wh (without old:
    further than 0); a daily COP off heat/electrical of the day by over 0.01 (ratios over 12 left out)."""
    caps = Caps(data, raw_until)
    out = collections.Counter()
    for k, m in POWER.items():
        for t, v, _ in data[m].pts:
            lim = caps.limit(k, t)
            out["power points"] += 1
            if lim is not None and v > lim + 1:
                ov = old[m].at(t) if old else None
                if ov is not None and v <= ov + 0.01:
                    # the live rule capped with the circuit's live reading, the persisted one may lag (5 s): not raised
                    out[f"{m} above the cap as in the original, not raised"] += 1
                else:
                    out[f"{m} over its cap"] += 1

    def split(dat, series, t, end):
        tot = dat[series["total"]].at(t)
        sp, dh = dat[series["space"]].at(end), dat[series["dhw"]].at(end)
        return None if tot is None or sp is None or dh is None else tot - sp - dh

    def own(series, t):
        """Whether space and DHW have a point of their own in the total's run (else one holds an earlier value)."""
        if caps.minute(t):
            return all(t in data[series[k]].times for k in ("space", "dhw"))
        a, b = caps.run_start.get(t, t), caps.end(t)
        return all(any(a <= x <= b for x in data[series[k]].t[bisect.bisect_left(data[series[k]].t, a):][:3])
                   for k in ("space", "dhw"))

    for name, series, tol, end in (("power", POWER, 1.0, caps.end), ("heat energy", HEAT, 0.001, lambda t: t + RUN)):
        for t, _, _ in data[series["total"]].pts:
            dn = split(data, series, t, end(t))
            if dn is None:
                continue
            out[f"{name} split checked"] += 1
            do = split(old, series, t, end(t)) if old else 0.0
            if do is not None and abs(dn) > abs(do) + tol:
                if name == "power" and old and not own(series, t):
                    out[f"{name} split further from the original by over {tol} where a part holds an earlier "
                        f"minute's value"] += 1
                    key = "max of those changes (W)"
                    out[key] = max(out[key], round(abs(dn) - abs(do), 1))
                else:
                    out[f"{name} split further off by over {tol}"] += 1
    for k, m in DCOP.items():
        h, e = data[HEAT[k]], data[ENERGY[k]]
        for t, v, _ in data[m].pts:
            hv, ev = h.at(t), e.at(t)
            if hv is None or ev is None:
                continue
            r = hv / ev if hv > 0 and ev > 0 else 0.0
            if r > 12:
                continue
            out["dcop checked"] += 1
            if abs(v - r) > 0.01:
                out[f"{m} off heat/electrical"] += 1
    return out


FAILS = ("over its cap", "further off", "off heat")


def merge(total, part):
    """Add a day's counts; a "max of" entry keeps the largest."""
    for k, v in part.items():
        total[k] = max(total[k], v) if k.startswith("max of") else total[k] + v


# ---------------------------------------------------------------- check and apply

def save_state(state):
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE)


def load_state():
    try:
        return json.load(open(STATE))
    except FileNotFoundError:
        return {}


def plan(mode, first, last):
    """Compute every day; in apply mode the changes go to the journal. Returns whether the numbers pass, and the
    downsampler's cutoff the plan was made with."""
    ru = raw_from()
    log(f"days {first} .. {last}; raw points from {datetime.datetime.fromtimestamp(ru // S, TZ)} on, minute means "
        f"before")
    changed, scanned = collections.Counter(), collections.Counter()
    max_power = {m: [None, None] for m in POWER.values()}
    stats, inv_old, inv_new = collections.Counter(), collections.Counter(), collections.Counter()
    per_day = []  # (day, heat old, heat new, removed Wh, dcop old, dcop new)
    integral_off = []
    raw_changed = raw_all = 0
    months = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])  # removed space, removed DHW, heat space, heat DHW
    journal = None
    if mode == "apply":
        os.makedirs(STATE_DIR, exist_ok=True)
        journal = gzip.open(JOURNAL, "wt")
        journal.write(f"# hp_spread_offset_history.py apply {datetime.datetime.now(TZ).isoformat(timespec='seconds')}, "
                      f"days {first} .. {last}, raw_from {ru}, cutoff {CUTOFF}\n")
        journal.write("measurement,tag,time_ns,old,new,raw\n")
    for day in days(first, last):
        data, a, b = load(day)
        d = Day(day, data, a, b, ru)
        for m, s in data.items():
            scanned[m] += len(s.pts)
        for m, *_ in d.changes:
            changed[m] += 1
        for m, (mo, mn) in d.max_power.items():
            if mo is not None and (max_power[m][0] is None or mo > max_power[m][0]):
                max_power[m][0] = mo
            if mn is not None and (max_power[m][1] is None or mn > max_power[m][1]):
                max_power[m][1] = mn
        if a >= ru:
            raw_changed += sum(1 for c in d.changes if c[0] in POWER.values())
            raw_all += sum(len(data[m].pts) for m in POWER.values())
        stats.update(d.stats)
        stats["removal over a silence over five minutes, not taken (Wh)"] += round(d.gap_lost, 3)
        heat = d.day_heat(False)
        if heat > 1:
            integral_off.append(abs(d.orig_integral / 1000 - heat) / heat)
        merge(inv_old, invariants(day, data, ru))
        merge(inv_new, invariants(day, apply_changes(data, d.changes), ru, data))
        per_day.append((day, heat, d.day_heat(True), d.day_removed(), d.day_dcop(False), d.day_dcop(True)))
        mo = months[day.strftime("%Y-%m")]
        for i, k in enumerate(("space", "dhw")):
            mo[i] += d.taken[k][-1][1] / 1000 if d.taken[k] else 0.0
            pts = d.heat_old[k].pts
            mo[2 + i] += pts[-1][1] if pts else 0.0
        if journal:
            for m, tag, t, old, new in d.changes:
                journal.write(f"{m},{tag},{t},{old!r},{new!r},{1 if t >= ru else 0}\n")
        if day.day == 1:
            log(f"{day}: {sum(changed.values())} points change so far")
    if journal:
        journal.close()
        with open(JOURNAL, "rb") as f:
            os.fsync(f.fileno())

    # ------------------------------------------------------------ report
    print("\npoints that change, per measurement (of the points in the range):")
    for m in WRITTEN:
        print(f"  {m:45s} {changed[m]:8d} of {scanned[m]:8d}")
    print("\nheating power, largest original -> largest corrected (W):")
    for m, (mo, mn) in max_power.items():
        print(f"  {m:45s} {mo if mo is None else round(mo, 1)} -> {mn if mn is None else round(mn, 1)}")
    total = sum(x[3] for x in per_day) / 1000
    heat = sum(x[1] for x in per_day)
    print(f"\nheat energy removed: {total:.1f} kWh of {heat:.1f} kWh ({100 * total / heat:.2f} %)")
    years = collections.defaultdict(lambda: [0.0, 0.0])
    for day, h, _, r, _, _ in per_day:
        years[day.year][0] += r / 1000
        years[day.year][1] += h
    for y, (r, h) in sorted(years.items()):
        print(f"  {y}: {r:.1f} kWh of {h:.1f} kWh ({100 * r / h if h else 0:.2f} %)")
    share = sorted((100 * r / 1000 / h, day, r) for day, h, _, r, _, _ in per_day if h > 0.5)
    pos = [s for s, _, _ in share]
    by_r = sorted(per_day, key=lambda x: -x[3])
    print(f"  largest day: {by_r[0][0]} {by_r[0][3]:.0f} Wh; of a day's heat (days over 0.5 kWh): median "
          f"{pos[len(pos) // 2]:.2f} %, 90 % of the days up to {pos[len(pos) * 9 // 10]:.2f} %, at most "
          f"{share[-1][0]:.2f} % on {share[-1][1]}")
    sept = sorted(100 * r / 1000 / h for day, h, _, r, _, _ in per_day
                  if datetime.date(2026, 9, 1) <= day <= datetime.date(2026, 9, 30) and h > 0.5)
    if sept:
        print(f"  September 2026: a day's heat lower by {sept[len(sept) // 2]:.2f} % in the median, at most "
              f"{sept[-1]:.2f} %; raw days: {raw_changed} of {raw_all} power points changed "
              f"({100 * raw_changed / max(1, raw_all):.1f} %)")
    print("\nper month: heat removed of the old heat, space / DHW (kWh):")
    for mk, (rs, rd, hs, hd) in sorted(months.items()):
        print(f"  {mk}: space {rs:6.1f} of {hs:7.1f} ({100 * rs / hs if hs else 0:5.1f} %), "
              f"DHW {rd:6.1f} of {hd:7.1f} ({100 * rd / hd if hd else 0:5.1f} %)")
    integral_off.sort()
    if integral_off:
        n = len(integral_off)
        print(f"  original heat power integrated vs the day's counter: median {100 * integral_off[n // 2]:.2f} % off, "
              f"95 % of the days within {100 * integral_off[int(n * 0.95)]:.2f} %, at most "
              f"{100 * integral_off[-1]:.2f} %")
    print("\nsample days: heat energy kWh old -> new (removed), daily COP old -> new:")
    fixed = {datetime.date(2024, 12, 15), datetime.date(2025, 1, 15), datetime.date(2025, 4, 15),
             datetime.date(2025, 7, 15), datetime.date(2025, 10, 15), datetime.date(2026, 2, 15),
             datetime.date(2026, 6, 15), datetime.date(2026, 9, 20), datetime.date(2026, 10, 4),
             datetime.date(2026, 10, 13), datetime.date(2026, 10, 14)}
    for day, h, hn, r, c, cn in by_r[:6] + [x for x in per_day if x[0] in fixed]:
        print(f"  {day}: {h:7.3f} -> {hn:7.3f} kWh ({r:5.0f} Wh, {100 * r / 1000 / h if h else 0:5.2f} %), "
              f"COP {c:.2f} -> {cn:.2f}")
    print("\nnotes:")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {round(v, 1) if isinstance(v, float) else v}")
    print("\nchecks, original (absolute) -> after the change (against the original):")
    for k in sorted(set(inv_old) | set(inv_new)):
        print(f"  {k}: {inv_old.get(k, 0)} -> {inv_new.get(k, 0)}")
    problems = []
    big = [(x, day) for x, day, _ in share if x > 60 and dict((p[0], p[1]) for p in per_day)[day] > 5]
    if big:
        problems.append(f"a day's heat drops by {max(big)[0]:.1f} % ({max(big)[1]})")
    rises = [(day, -r) for day, h, _, r, _, _ in per_day if r < -max(5.0, 0.005 * h * 1000)]
    if rises:
        problems.append(f"{len(rises)} days' heat would rise, e.g. {rises[0][0]} by {rises[0][1]:.0f} Wh")
    bad = {k: v for k, v in list(inv_new.items()) + list(stats.items()) if any(f in k for f in FAILS)}
    if bad:
        problems.append(f"checks fail after the change: {bad}")
    for p in problems:
        print("PROBLEM:", p)
    sys.stdout.flush()
    return not problems, ru


def guard(ru):
    if downsampler_busy():
        raise SystemExit("influx-downsample.service runs or starts within 20 minutes; stopped, apply resumes later")
    if raw_from() != ru:
        raise SystemExit("the downsampler moved on since the plan; run undo, then apply again")


def read_journal():
    with gzip.open(JOURNAL, "rt") as f:
        for row in f:
            if row.startswith("#") or row.startswith("measurement,"):
                continue
            m, tag, t, old, new, raw = row.rstrip("\n").split(",")
            yield m, tag, int(t), float(old), float(new), raw == "1"


def write_journal(ru, state):
    """Write the journal's new values in batches, from where an interrupted run stopped."""
    done, n, batch = state.get("written", 0), 0, []

    def flush():
        guard(ru)
        write(batch)
        state["written"] = n
        save_state(state)
        time.sleep(0.2)  # let InfluxDB on the Pi keep up
    for m, tag, t, _, new, _ in read_journal():
        n += 1
        if n <= done:
            continue
        batch.append(line(m, tag, t, new))
        if len(batch) >= 5000:
            flush()
            batch = []
            if n % 250000 < 5000:
                log(f"{n} points written")
    if batch:
        flush()
    log(f"{n} points written")


def journal_days():
    """The journal's changes day by day: a day's changes were written together."""
    day, changes = None, []
    for m, tag, t, old, new, _ in read_journal():
        d = day_of(t)
        if d != day and changes:
            yield day, changes
            changes = []
        day = d
        changes.append((sys.intern(m), tag, t, old, new))
    if changes:
        yield day, changes


def verify(ru):
    """Re-query every day with changes: the journal's new values are there, and the checks hold against the
    original (the journal's old values)."""
    missing, n_days, n_points, inv, finals = 0, 0, 0, collections.Counter(), []
    for day, changes in journal_days():
        n_days += 1
        n_points += len(changes)
        data, a, b = load(day)
        idx = {m: {(t, tag): v for t, v, tag in s.pts} for m, s in data.items()}
        for m, tag, t, _, new in changes:
            got = idx[m].get((t, tag))
            if got is None or abs(got - new) > 1e-9 * max(1.0, abs(new)):
                missing += 1
        old = apply_changes(data, [(m, tag, t, new, old) for m, tag, t, old, new in changes])
        merge(inv, invariants(day, data, ru, old))
        hs = data[HEAT["total"]].pts
        if hs:
            last = [c for c in changes if c[0] == HEAT["total"] and c[2] == hs[-1][0]]
            if last:
                finals.append((day, last[0][3], last[0][4], hs[-1][1]))
        if day.day == 1:
            log(f"verified up to {day}")
    print(f"\nverify: {n_days} days, {n_points} journaled points, {missing} not as planned")
    for k, v in sorted(inv.items()):
        print(f"  {k}: {v}")
    print("  the day's heat at its last counter point: planned old -> new, and what InfluxDB has now")
    for day, old, new, got in finals[::max(1, len(finals) // 10)]:
        print(f"  {day}: {old:.6f} -> {new:.6f} kWh, InfluxDB {got:.6f}")
    bad = {k: v for k, v in inv.items() if any(f in k for f in FAILS)}
    return missing == 0 and not bad


def undo():
    state = load_state()
    ru_now = raw_from()
    batch, n, skipped = [], 0, 0
    for m, tag, t, old, _, raw in read_journal():
        if raw and t < ru_now:
            skipped += 1  # downsampled since: the raw point is gone, its minute mean carries the correction
            continue
        batch.append(line(m, tag, t, old))
        n += 1
        if len(batch) >= 5000:
            guard(ru_now)
            write(batch)
            batch = []
            time.sleep(0.2)
    if batch:
        guard(ru_now)
        write(batch)
    state.update(status="undone", undone=datetime.datetime.now(TZ).isoformat(timespec="seconds"))
    save_state(state)
    log(f"undo: {n} old values written back, {skipped} raw points skipped that have been downsampled since")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("check", "apply", "verify", "undo"):
        raise SystemExit(__doc__.rsplit("\n", 1)[-1])
    global CUTOFF
    mode = sys.argv[1]
    first, last = FIRST_DAY, LAST_DAY
    if len(sys.argv) in (4, 5):
        first = max(FIRST_DAY, datetime.date.fromisoformat(sys.argv[2]))
        last = datetime.date.fromisoformat(sys.argv[3])
        if len(sys.argv) == 5:
            cut = datetime.datetime.fromisoformat(sys.argv[4])
            CUTOFF = int((cut if cut.tzinfo else cut.replace(tzinfo=TZ)).timestamp()) * S
            if last > day_of(CUTOFF):
                raise SystemExit("the last day lies after the cutoff's day")
            log(f"cutoff {datetime.datetime.fromtimestamp(CUTOFF // S, TZ)}: points from then on stay")
        elif last > LAST_DAY:
            raise SystemExit(f"days after {LAST_DAY} only with a cutoff (the corrected rule's switch)")
    state = load_state()
    if mode == "check":
        plan("check", first, last)
    elif mode == "apply":
        if state.get("status") == "applied":
            raise SystemExit(f"already applied on {state.get('applied')}; undo first to apply again")
        if downsampler_busy():
            raise SystemExit("influx-downsample.service runs or starts within 20 minutes; try later")
        if state.get("status") == "applying":
            ru = state["raw_from"]
            log(f"resuming the interrupted apply from the journal, {state.get('written', 0)} points written")
        else:
            if os.path.exists(JOURNAL):
                os.replace(JOURNAL, JOURNAL.replace(".csv.gz", f".{int(time.time())}.csv.gz"))
            ok, ru = plan("apply", first, last)
            if not ok:
                os.replace(JOURNAL, JOURNAL.replace(".csv.gz", ".refused.csv.gz"))
                raise SystemExit("not applied")
            state = {"status": "applying", "raw_from": ru, "written": 0, "days": [str(first), str(last)],
                     "started": datetime.datetime.now(TZ).isoformat(timespec="seconds")}
            save_state(state)
        write_journal(ru, state)
        state.update(status="applied", applied=datetime.datetime.now(TZ).isoformat(timespec="seconds"))
        save_state(state)
        log(f"applied; old values in {JOURNAL}")
        if not verify(ru):
            raise SystemExit("verification failed")
        log("verified")
    elif mode == "verify":
        if not verify(state.get("raw_from", raw_from())):
            raise SystemExit("verification failed")
    else:
        undo()


if __name__ == "__main__":
    main()
