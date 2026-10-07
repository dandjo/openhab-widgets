#!/usr/bin/env python3
"""Delete physically impossible points from InfluxDB (Modbus int32/uint32 sentinels such as -2147483647 or
21474836.47 and what derived counters made of them; negative or absurd day counters). Consecutive bad points with
no good point between them go in one time-range DELETE (InfluxDB ignores OR'ed timestamps, and each DELETE costs
~6 s). Every deleted point is saved first, so it can be written back.
Usage: glitch_clean.py plan|apply   (on homepi; journal in ~/.local/state/glitch_cleanup/)"""
import datetime, json, os, re, subprocess, sys, time

STATE = os.path.expanduser("~/.local/state/glitch_cleanup")


def q(query):
    p = subprocess.run(["influx", "-database", "openhab", "-format", "json", "-precision", "rfc3339", "-execute", query],
                       capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr or p.stdout)
    return json.loads(p.stdout) if p.stdout.strip() else {}


def rows(r):
    try:
        return r["results"][0]["series"][0]["values"]
    except (KeyError, IndexError):
        return []


RANGES = {
    "huawei_inverter_power_meter_active_power": (-30000, 30000),
    "huawei_inverter_power_meter_reactive_power": (-30000, 30000),
    "huawei_inverter_power_meter_grid_consumption": (1, 1000000),
    "huawei_inverter_power_meter_grid_production": (1, 1000000),
    "huawei_inverter_energy_storage_unit_1_power": (-15000, 15000),
    "huawei_inverter_energy_storage_unit_1_day_discharge": (0, 100),
    "huawei_inverter_energy_storage_unit_1_total_charge": (1, 100000),
    "huawei_inverter_energy_storage_unit_1_total_discharge": (1, 100000),
    "huawei_inverter_power_meter_ec_day": (0, 300),
    "huawei_inverter_power_meter_ep_day": (0, 300),
    "home_ec_day": (0, 300),
    "photovoltaics_own_ec_day": (0, 300),
    "water_meter_value_day": (0, 300),
}
for n in "123":
    RANGES[f"huawei_inverter_power_meter_l{n}_active_power"] = (-15000, 15000)
    RANGES[f"huawei_inverter_power_meter_l{n}_current"] = (-60, 60)
    RANGES[f"huawei_inverter_power_meter_l{n}_voltage"] = (150, 300)


def groups(m, lo, hi):
    bad = rows(q(f'SELECT "value" FROM "{m}" WHERE "value" < {lo} OR "value" > {hi}'))
    out, cur = [], []
    for t, v in bad:
        if cur:
            good = rows(q(f'SELECT COUNT("value") FROM "{m}" WHERE time > \'{cur[-1][0]}\' AND time < \'{t}\' '
                          f'AND "value" >= {lo} AND "value" <= {hi}'))
            if good and good[0][1]:
                out.append(cur)
                cur = []
        cur.append((t, v))
    if cur:
        out.append(cur)
    return bad, out


def main():
    mode = sys.argv[1:2]
    if mode not in (["plan"], ["apply"]):
        sys.exit(__doc__)
    os.makedirs(STATE, exist_ok=True)
    total_pts = total_grp = 0
    for m, (lo, hi) in RANGES.items():
        bad, grp = groups(m, lo, hi)
        if not bad:
            continue
        total_pts += len(bad)
        total_grp += len(grp)
        print(f"{m:56s} {len(bad):4d} points in {len(grp):3d} windows", flush=True)
        if mode == ["apply"]:
            with open(os.path.join(STATE, f"{m}.json"), "w") as f:
                json.dump({"range": [lo, hi], "deleted": bad}, f)
            for g in grp:
                q(f'DELETE FROM "{m}" WHERE time >= \'{g[0][0]}\' AND time <= \'{g[-1][0]}\'')
            left = rows(q(f'SELECT COUNT("value") FROM "{m}" WHERE "value" < {lo} OR "value" > {hi}'))
            print(f"    left: {left[0][1] if left else 0}", flush=True)
    print(f"total {total_pts} points in {total_grp} windows (~{total_grp * 7 // 60} min to delete)")


main()
