#!/usr/bin/env python3
"""After hp_split_history.py: the day energies heatpump_metering wrote from CUTOFF on still build on its uncorrected
accumulators. Shift them by the correction hp_split_history.py made at the last point before CUTOFF, recompute the
daily COPs there, and write, with openHAB stopped, so the rule continues from the corrected values after its start.
Usage: hp_split_tail.py check|apply CUTOFF_NS HISTORY_BACKUP.csv.gz [TAIL_BACKUP.csv.gz]"""
import bisect
import csv
import datetime
import gzip
import sys
import time
from zoneinfo import ZoneInfo

import hp_model as hm

MODE, CUTOFF, HISTORY = sys.argv[1], int(sys.argv[2]), sys.argv[3]
P = "espaltherma_"
ENERGY = [P + "energy_space_today", P + "energy_dhw_today", P + "energy_standby_today", P + "energy_today",
          P + "heating_energy_space_today", P + "heating_energy_dhw_today", P + "heating_energy_today"]
DCOP = {P + "dcop_space": (P + "heating_energy_space_today", P + "energy_space_today"),
        P + "dcop_dhw": (P + "heating_energy_dhw_today", P + "energy_dhw_today"),
        P + "dcop": (P + "heating_energy_today", P + "energy_today")}
NOW = time.time_ns()

def midnight(t):
    d = datetime.datetime.fromtimestamp(t // 1_000_000_000, ZoneInfo("Europe/Vienna"))
    return int(datetime.datetime.combine(d.date(), datetime.time(), d.tzinfo).timestamp() * 1e9)


# the correction at the last point before CUTOFF on CUTOFF's day, per energy item; an item corrected on earlier days
# only (a total, the heat of a day that moved none) gets none
DAY = midnight(CUTOFF)
last = {}
with gzip.open(HISTORY, "rt") as f:
    for row in csv.DictReader(f):
        m, t = row["measurement"], int(row["time_ns"])
        if m in ENERGY and DAY <= t < CUTOFF and (m not in last or t > last[m][0]) and row["old"] != "":
            last[m] = (t, float(row["new"]) - float(row["old"]))
fix = []
new_series = {}
for m in ENERGY:
    delta = last.get(m, (0, 0.0))[1]
    pts = hm.points(m, CUTOFF, NOW)
    new_series[m] = [(t, v if abs(delta) < 5e-7 else round(max(0.0, v + delta), 6)) for t, v in pts]
    for (t, v), (_, n) in zip(pts, new_series[m]):
        if abs(n - v) > 5e-7:
            fix.append((m, t, v, n))
    print(f"{m}: correction {delta:+.6f} kWh on {sum(1 for x in fix if x[0] == m)} of {len(pts)} points")


def at(m, t):
    s = new_series[m]
    i = bisect.bisect_right([x for x, _ in s], t) - 1
    return s[i][1] if i >= 0 else None


for m, (hk, ek) in DCOP.items():
    n_changed = 0
    for t, old in hm.points(m, CUTOFF, NOW):
        h, e = at(hk, t), at(ek, t)
        if h is None or e is None:
            continue
        new = round(h / e, 2) if h > 0 and e > 0 else 0.0
        if new <= 12 and (old is None or abs(new - old) > 0.005):
            fix.append((m, t, old, new))
            n_changed += 1
    print(f"{m}: {n_changed} points change")
if MODE == "apply":
    with gzip.open(sys.argv[4], "wt") as f:
        f.write("measurement,time_ns,old,new\n")
        for m, t, old, new in fix:
            f.write(f"{m},{t},{'' if old is None else old},{new}\n")
    hm.write([f"{m},item={m} value={float(new)!r} {t}" for m, t, _, new in fix])
    print(f"written {len(fix)} points; old values in {sys.argv[4]}")
