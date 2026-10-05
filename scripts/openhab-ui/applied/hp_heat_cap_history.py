#!/usr/bin/env python3
"""Cap the heating powers in the heat pump's history the way heatpump_metering caps them since 5 October 2026
(applied/hp_heat_cap.py; user, 2026-10-05: the history kept the implausible 12 to 22.8 kW for 5 to 20 s at the start
of hot-water charges, when cold tank water meets the warm water standing in the unit and flow × spread overshoots),
and make what derives from them follow: the instantaneous COPs, the day heat energies and the daily COPs.

The cap, with each input's last value: compressor_max = min(12000, 0.8 × T_cond / max(5, T_cond − T_evap) ×
max(0, heatpump_power)), T_cond = leaving water before the backup heater + 273.15 + 3 (35 °C when missing), T_evap =
outdoor + 273.15 − 7 (7 °C when missing); nothing is capped where heatpump_power has no value. before_buh ≤
compressor_max; after_buh and space ≤ compressor_max + backup heater (2 kW step 1, 4 kW step 2 while on); DHW and the
total ≤ that + the booster heater's 2 kW while on (the rule adds it to DHW). Negative values (defrost) stay. Raw points
are taken run by run: the points of the five powers within 100 ms of each other, no series twice, are one run of the
rule and share one cap, from the inputs at the run's first point (a heater counts if it was on up to 100 ms before:
the rule may have read the switch before its change was persisted). Points older than the downsampler's cutoff
(~/scripts/influx_downsample.py) that lie on a minute are time-weighted minute means: there the inputs are their means
over the same minute (switches as their share of it), and in a minute whose space, DHW and total all have a mean (the
valve switched within it) the after-heater heat over the cap comes off space and DHW in proportion. The total takes
off what space and DHW took at its run, never staying above its own cap, so space + DHW still equals the total.

Energy: per day the removed power of space and DHW (original − capped) is integrated like the counters were,
trapezoidal on one shared time step (every point of the powers, of the counters and of espaltherma_energy_today, and
between them a run every 3 s, ESPAltherma's cadence), a silence over five minutes not bridged; a minute mean's removal
counts once its minute is over (the counters were integrated on the raw points). At every counter point the removed
energy since midnight is subtracted from space and DHW, the total takes their sum at its run; between two points no
counter gives more than it counted there (a shortfall follows later), so where a counter did not count (a silence
the powers do not show, a defrost's negative heat) nothing is taken, and a value that would fall below zero is held
at 0, as the recomputed history holds it. The electrical energies stay. Daily COPs are recomputed at their points from the corrected heat and the
electrical energy where the heat changed; over 12 keeps the old point, as the rule would not write it. Instantaneous
COPs follow at their points: raw points by capped/original heat of their run, minute means are limited to the
minute's capped heat over its electrical power; none is added where the original ratio was over 10 and not written.

From 31 October 2024, the first day whose persisted powers integrate to its counters (within 0.2 % on 95 % of the
days since), to 4 October 2026; never 5 October 2026 or later, whose energies sit in the live rule's accumulators.
Before, the rule did not post every heating power (it held one for up to 15 minutes after the compressor stopped, and
the counters, recomputed from the inputs on 27 September 2026, differ by up to 12 %; the cap would take up to 14 % of
a day), and before the split on 18 October 2024 an older rule's counters integrated those held values; those days
are left as they are. Cross-checked on raw days against a replay of the rule's heat from its inputs with the cap
(hp_model): 89.0 / 86.5 / 49.3 / 83.6 / 557 Wh removed there, 89.0 / 84.8 / 48.1 / 86.3 / 566 Wh here (20, 24, 28
September, 2 and 4 October 2026).
check: dry run with the numbers. apply: plan again, refuse if a day's heat drops by more than 10 % or a check fails,
write every original point to the journal (~/.local/state/heat_cap_history/journal.csv.gz: measurement, tag, time,
old, new, raw) before the first write, write in batches (never while influx-downsample.service runs or within 20
minutes before its 01:00 start, nor after it moved on), then verify; an interrupted apply resumes from the journal.
verify: re-query and check. undo: write the journal's old values back; raw points downsampled since are skipped
(their minute means carry the cap).
Usage: hp_heat_cap_history.py check|apply [FIRST_DAY LAST_DAY] | verify | undo   (on homepi, as pi)"""
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
LAST_DAY = datetime.date(2026, 10, 4)
STATE_DIR = os.environ.get("HEAT_CAP_STATE", os.path.expanduser("~/.local/state/heat_cap_history"))
JOURNAL = os.path.join(STATE_DIR, "journal.csv.gz")
STATE = os.path.join(STATE_DIR, "state.json")
DOWNSAMPLE_STATE = os.path.expanduser("~/.local/state/influx_downsample/state.json")
P = "espaltherma_"
INPUT = {"circuit": "heatpump_power", "lwt": P + "leaving_water_temp_before_buh", "outdoor": P + "ext_ambient_temp",
         "buh1": P + "buh_step1_mode", "buh2": P + "buh_step2_mode", "bsh": P + "bsh_mode"}  # switches as 1/0
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
        self._caps = {}
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


# ---------------------------------------------------------------- one day

class Day:
    """The capped powers and what follows from them for one day."""

    def __init__(self, day, data, a, b, raw_until):
        self.day, self.d, self.a, self.b, self.raw_until = day, data, a, b, raw_until
        self.caps = Caps(data, raw_until)
        self.changes = []  # (measurement, tag, t, old, new)
        self.stats = collections.Counter()
        self.max_power = {}  # measurement -> (max original, max capped)
        self.cap_powers()
        self.integrate()
        self.correct_energies()
        self.correct_dcops()
        self.correct_cops()

    def minute(self, t):
        return self.caps.minute(t)

    def capped(self, k, t, v):
        lim = self.caps.limit(k, t)
        if lim is None or v <= lim:
            return v
        return lim if self.minute(t) else min(v, round(lim, 2))  # the rule stores 2 decimals

    def cap_powers(self):
        self.old, self.new = {}, {}
        for k, m in POWER.items():
            s = self.d[m]
            self.old[k] = s
            carry_v = self.capped(k, s.carry[0], s.carry[1]) if s.carry else None
            self.new[k] = s.with_values(carry_v, [self.capped(k, t, v) for t, v, _ in s.pts])
        # minutes in which the valve switched: space, DHW and the total all have a mean there; the heat over the cap
        # after the backup heater comes off space and DHW in proportion
        idx = {k: {t: i for i, (t, _, _) in enumerate(self.old[k].pts)} for k in PARTS}
        for t in sorted(self.old["space"].times & self.old["dhw"].times & self.old["total"].times):
            if not self.minute(t) or self.caps.cap(t) is None:
                continue
            cc, buh, bsh = self.caps.cap(t)
            x = cc + buh
            sp, dhw_full = (self.old[k].pts[idx[k][t]][1] for k in ("space", "dhw"))
            dhw = dhw_full - bsh
            r = max(0.0, sp + dhw - x)
            rs, rd = max(0.0, sp - x), max(0.0, dhw - x)
            extra = max(0.0, r - rs - rd)
            cs, cd = max(0.0, sp - rs), max(0.0, dhw - rd)
            if extra > 0 and cs + cd > 0:
                rs, rd = rs + extra * cs / (cs + cd), rd + extra * cd / (cs + cd)
                if cs > 0 and cd > 0:
                    self.stats["minute means with the valve switching, capped in proportion"] += 1
            self._set("space", idx["space"][t], sp - rs)
            self._set("dhw", idx["dhw"][t], dhw_full - rd)
        # the total: what space and DHW took at its run, at most its own cap
        tot = self.old["total"]
        for i, (t, v, _) in enumerate(tot.pts):
            own = self.capped("total", t, v)
            e = self.caps.end(t)
            parts = [(self.old[k].at(e), self.new[k].at(e)) for k in ("space", "dhw")]
            if any(o is None or n is None for o, n in parts):
                new = own
            else:
                new = min(own, max(v - sum(o - n for o, n in parts), min(v, 0.0)))
                if not self.minute(t):
                    new = round(new, 2)
            self._set("total", i, new)
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
                    e = el.wmean(t, t + MIN)
                    new = min(old, hn / e if hn > 0 and e is not None and e > 0 else 0.0)
                    if new < old - 1e-9:
                        self.changes.append((m, tag, t, old, new))
                else:
                    ho, hn = o.at(t), n.at(t)
                    if ho is None or hn is None or hn >= ho - 1e-9 or ho <= 0:
                        continue
                    new = round(old * hn / ho, 2) if hn > 0 else 0.0
                    if abs(new - old) > 0.004:
                        self.changes.append((m, tag, t, old, new))
            # where the original ratio was over 10 (not written) and the capped one is not, the capped rule would have
            # written a point; counted, not added
            for t, v, _ in o.pts:
                if self.minute(t):
                    continue
                nv, e = n.at(t), el.at(t)
                if nv is not None and nv < v - 1e-9 and e is not None and e > 0 and v / e > 10 >= nv / e > 0:
                    self.stats[f"{m}: a point the capped rule would have written, not added"] += 1

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
    raw_capped = raw_all = 0
    journal = None
    if mode == "apply":
        os.makedirs(STATE_DIR, exist_ok=True)
        journal = gzip.open(JOURNAL, "wt")
        journal.write(f"# hp_heat_cap_history.py apply {datetime.datetime.now(TZ).isoformat(timespec='seconds')}, "
                      f"days {first} .. {last}, raw_from {ru}\n")
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
            raw_capped += sum(1 for c in d.changes if c[0] in POWER.values())
            raw_all += sum(len(data[m].pts) for m in POWER.values())
        stats.update(d.stats)
        stats["removal over a silence over five minutes, not taken (Wh)"] += round(d.gap_lost, 3)
        heat = d.day_heat(False)
        if heat > 1:
            integral_off.append(abs(d.orig_integral / 1000 - heat) / heat)
        merge(inv_old, invariants(day, data, ru))
        merge(inv_new, invariants(day, apply_changes(data, d.changes), ru, data))
        per_day.append((day, heat, d.day_heat(True), d.day_removed(), d.day_dcop(False), d.day_dcop(True)))
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
    print("\nheating power, largest original -> largest capped (W):")
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
              f"{sept[-1]:.2f} %; raw days: {raw_capped} of {raw_all} power points capped "
              f"({100 * raw_capped / max(1, raw_all):.1f} %)")
    integral_off.sort()
    if integral_off:
        n = len(integral_off)
        print(f"  original heat power integrated vs the day's counter: median {100 * integral_off[n // 2]:.2f} % off, "
              f"95 % of the days within {100 * integral_off[int(n * 0.95)]:.2f} %, at most "
              f"{100 * integral_off[-1]:.2f} %")
    print("\nsample days: heat energy kWh old -> new (removed), daily COP old -> new:")
    fixed = {datetime.date(2024, 12, 15), datetime.date(2025, 1, 15), datetime.date(2025, 4, 15),
             datetime.date(2025, 7, 15), datetime.date(2025, 10, 15), datetime.date(2026, 2, 15),
             datetime.date(2026, 6, 15), datetime.date(2026, 9, 20), datetime.date(2026, 10, 4)}
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
    if share and share[-1][0] > 10:
        problems.append(f"a day's heat drops by {share[-1][0]:.1f} % ({share[-1][1]})")
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
            skipped += 1  # downsampled since: its minute mean carries the cap, the raw point is gone
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
    mode = sys.argv[1]
    first, last = FIRST_DAY, LAST_DAY
    if len(sys.argv) == 4:
        first = max(FIRST_DAY, datetime.date.fromisoformat(sys.argv[2]))
        last = min(LAST_DAY, datetime.date.fromisoformat(sys.argv[3]))
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
