#!/usr/bin/env python3
"""Add to the heat pump day energies what heatpump_metering lost at each openHAB restart before it bridged restarts
(from 24 September 2026, when the days became the rule's own integration, to 30 September 2026): the trapezoid
between the powers at the last write before the restart and at the first write after it, as the rule now bridges
them, per energy item with one shared time step (the totals get the sum of their parts); recompute the daily COPs
from there on. A restart is a pause in the rule's writes of two to fifteen minutes (the rule's own limit) across
which the counter did not move while openHAB was down (home_active_power, written every 10 s, paused too), within one
day; a gap already bridged moves the counter, so a second run finds nothing. For today run it with openHAB stopped,
so the rule continues from the corrected values; past days can be written while it runs.
Usage: INFLUX=http://127.0.0.1:8086 hp_restart_backfill.py check|apply FIRST_DAY LAST_DAY [OLD_VALUES.csv.gz]"""
import bisect
import datetime
import gzip
import sys
from zoneinfo import ZoneInfo

import hp_model as hm

MODE, FIRST, LAST = sys.argv[1], sys.argv[2], sys.argv[3]
P = "espaltherma_"
POWER = {P + "energy_space_today": P + "electrical_power_space", P + "energy_dhw_today": P + "electrical_power_dhw",
         P + "energy_standby_today": P + "electrical_power_standby", P + "energy_today": P + "electrical_power",
         P + "heating_energy_space_today": P + "heating_power_space",
         P + "heating_energy_dhw_today": P + "heating_power_dhw", P + "heating_energy_today": P + "heating_power"}
DCOP = {P + "dcop_space": (P + "heating_energy_space_today", P + "energy_space_today"),
        P + "dcop_dhw": (P + "heating_energy_dhw_today", P + "energy_dhw_today"),
        P + "dcop": (P + "heating_energy_today", P + "energy_today")}
S = 10**9
TZ = ZoneInfo("Europe/Vienna")
MAX_RESTART = 900 * S  # the rule bridges a restart up to 15 minutes
HOME_PAUSE = 60 * S  # home_power writes every 10 s while openHAB runs


def midnight(day):
    return int(datetime.datetime.combine(day, datetime.time(), TZ).timestamp()) * S


def at(series, t):
    i = bisect.bisect_right([x for x, _ in series], t) - 1
    return series[i][1] if i >= 0 else None


def after_restart(series, t):
    # the powers the first run after the restart posted, persisted within a few seconds of its energy write
    for x, v in series:
        if t - 5 * S <= x <= t + 5 * S:
            return v
    return at(series, t)


PARTS = {P + "energy_today": [P + "energy_space_today", P + "energy_dhw_today", P + "energy_standby_today"],
         P + "heating_energy_today": [P + "heating_energy_space_today", P + "heating_energy_dhw_today"]}
fix = []
day, last_day = datetime.date.fromisoformat(FIRST), datetime.date.fromisoformat(LAST)
while day <= last_day:
    DAY0, DAY1 = midnight(day), midnight(day + datetime.timedelta(days=1))
    total = hm.points(P + "energy_today", DAY0, DAY1)
    home = [t for t, _ in hm.points("home_active_power", DAY0, DAY1)]

    def openhab_down(a, b):
        inside = [a] + [t for t in home if a < t < b] + [b]
        return max(y - x for x, y in zip(inside, inside[1:])) >= HOME_PAUSE

    gaps = [(a, b) for (a, va), (b, vb) in zip(total, total[1:])
            if 120 * S < b - a <= MAX_RESTART and abs(vb - va) < 5e-7 and openhab_down(a, b)]
    powers = {p: hm.points(p, DAY0 - hm.DAY, DAY1) for p in POWER.values()}
    print(f"== {day}: {len(gaps)} restarts")


    corr = {m: [] for m in POWER}  # (from time, cumulative correction in kWh, rounded like the stored values)
    for a, b in gaps:
        seconds = (b - a) / S
        step = {}
        for m, p in POWER.items():
            if m not in PARTS:
                before, after = at(powers[p], a), after_restart(powers[p], b)
                step[m] = round((before + after) / 2 * seconds / 3600 / 1000, 6)
        # the totals get the sum of their parts, as the rule bridges them, so the split still sums exactly
        for m, parts in PARTS.items():
            step[m] = round(sum(step[x] for x in parts), 6)
        for m in POWER:
            prev = corr[m][-1][1] if corr[m] else 0.0
            corr[m].append((b, round(prev + step[m], 6)))
        if step[P + "energy_today"] >= 0.005:
            print(f"  restart {(a - DAY0) / 3600e9:6.3f} h -> {(b - DAY0) / 3600e9:6.3f} h ({seconds:.0f} s): "
                  f"electrical {step[P + 'energy_today'] * 1000:6.1f} Wh, heat {step[P + 'heating_energy_today'] * 1000:6.1f} Wh")

    def shift(m, t):
        c = 0.0
        for b, v in corr[m]:
            if t >= b:
                c = v
        return c

    new_series = {}
    for m in POWER:
        pts = hm.points(m, DAY0, DAY1)
        new_series[m] = [(t, round(v + shift(m, t), 6)) for t, v in pts]
        for (t, v), (_, nv) in zip(pts, new_series[m]):
            if abs(nv - v) > 5e-7:
                fix.append((m, t, v, nv))
    e_end = corr[P + "energy_today"][-1][1] if gaps else 0.0
    h_end = corr[P + "heating_energy_today"][-1][1] if gaps else 0.0
    # the parts still sum to their totals at the day's last write
    t, v = new_series[P + "energy_today"][-1]
    parts = sum(at(new_series[k], t) or 0 for k in PARTS[P + "energy_today"])
    old_total = hm.points(P + "energy_today", DAY0, DAY1)[-1][1]
    print(f"  day total {old_total:.3f} -> {v:.3f} kWh (+{e_end:.3f}), heat +{h_end:.3f} kWh; parts {parts:.6f} = total {v:.6f}")
    first = gaps[0][1] if gaps else DAY1
    for m, (hk, ek) in DCOP.items():
        for t, old in hm.points(m, first, DAY1):
            h, e = at(new_series[hk], t), at(new_series[ek], t)
            if h is None or e is None:
                continue
            new = round(h / e, 2) if h > 0 and e > 0 else 0.0
            if new <= 12 and (old is None or abs(new - old) > 0.005):
                fix.append((m, t, old, new))
    day += datetime.timedelta(days=1)

print(f"{len(fix)} points change")
if MODE == "apply":
    with gzip.open(sys.argv[4], "wt") as f:
        f.write("measurement,time_ns,old,new\n")
        for m, t, old, new in fix:
            f.write(f"{m},{t},{'' if old is None else old},{new}\n")
    hm.write([f"{m},item={m} value={float(new)!r} {t}" for m, t, _, new in fix])
    print(f"written {len(fix)} points; old values in {sys.argv[4]}")
