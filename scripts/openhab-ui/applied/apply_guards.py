#!/usr/bin/env python3
"""Keep Modbus sentinels (int32/uint32 limits like -2147483647 or 21474836.47) out of the meter and battery items
and impossible values out of the derived day counters (2026-10-07): range_filter on the links (out of range keeps
the item's last value), and the day counter rules skip a run whose result is negative or absurd.
Usage: apply_guards.py check|apply   (on homepi; the REST token from ~/.openhab_token, never printed)"""
import json, os, sys, urllib.error, urllib.parse, urllib.request

TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
BASE = "http://127.0.0.1:8080/rest"
APPLY = sys.argv[1:2] == ["apply"]


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        return e.code, None


q = lambda s: urllib.parse.quote(s, safe="")
FILTERS = {
    "huawei_inverter_power_meter_active_power": "min=-30000&max=30000",
    "huawei_inverter_power_meter_reactive_power": "min=-30000&max=30000",
    "huawei_inverter_power_meter_grid_consumption": "min=1&max=1000000",
    "huawei_inverter_power_meter_grid_production": "min=1&max=1000000",
    "huawei_inverter_energy_storage_unit_1_power": "min=-15000&max=15000",
    "huawei_inverter_energy_storage_unit_1_day_charge": "min=0&max=100",
    "huawei_inverter_energy_storage_unit_1_day_discharge": "min=0&max=100",
    "huawei_inverter_energy_storage_unit_1_total_charge": "min=1&max=100000",
    "huawei_inverter_energy_storage_unit_1_total_discharge": "min=1&max=100000",
}
for n in "123":
    FILTERS[f"huawei_inverter_power_meter_l{n}_active_power"] = "min=-15000&max=15000"
    FILTERS[f"huawei_inverter_power_meter_l{n}_current"] = "min=-60&max=60"
    FILTERS[f"huawei_inverter_power_meter_l{n}_voltage"] = "min=150&max=300"

links = {l["itemName"]: l for l in call("GET", "/links")[1]}
for item, params in FILTERS.items():
    l = links[item]
    cfg = dict(l.get("configuration") or {})
    want = f"config:js:range_filter?{params}"
    old = cfg.get("toItemScript")
    if old == want:
        print(f"{item}: already {params}")
        continue
    cfg.update(profile="transform:JS", toItemScript=want)
    st = call("PUT", f"/links/{q(item)}/{q(l['channelUID'])}", {"itemName": item, "channelUID": l["channelUID"],
                                                               "configuration": cfg})[0] if APPLY else "-"
    print(f"{item}: {old} -> {want}  {st}")

GUARD = "// a day counter is never negative nor beyond 300 kWh: a lagging e_day or a meter glitch, skip the run (2026-10-07)"
RULES = {
    "home_energy": [("  persistEnergy('home_ec_day', energy, 'kWh');",
                     f"  {GUARD}\n  if (energy >= 0 && energy <= 300) persistEnergy('home_ec_day', energy, 'kWh');")],
    "photovoltaics_own_energy": [("  persistEnergy('photovoltaics_own_ec_day', energy, 'kWh');",
                                  f"  {GUARD}\n  if (energy >= 0 && energy <= 300) persistEnergy('photovoltaics_own_ec_day', energy, 'kWh');")],
    "huawei_inverter_power_meter_ec": [("if (energy_delta !== null) {",
                                        "// a meter glitch (21474836.47 kWh) or a reset makes the delta absurd: skip the run (2026-10-07)\n"
                                        "if (energy_delta !== null && energy_delta.numericState >= 0 && energy_delta.numericState <= 300) {")],
    "huawei_inverter_power_meter_ep": [("if (energy_delta !== null) {",
                                        "// a meter glitch (21474836.47 kWh) or a reset makes the delta absurd: skip the run (2026-10-07)\n"
                                        "if (energy_delta !== null && energy_delta.numericState >= 0 && energy_delta.numericState <= 300) {")],
    "water_meter_consumption": [("if (volume_delta !== null) {",
                                 "// a misread meter (the whole reading as one day's volume) makes the delta absurd: skip the run (2026-10-07)\n"
                                 "if (volume_delta !== null && volume_delta.numericState <= 10) {")],
}
for uid, pairs in RULES.items():
    st, rule = call("GET", f"/rules/{uid}")
    assert st == 200, (uid, st)
    for a in rule["actions"]:
        s = a["configuration"].get("script")
        if not s:
            continue
        for old, new in pairs:
            if new in s:
                print(f"{uid}: already guarded")
                continue
            assert s.count(old) == 1, (uid, s.count(old), old)
            s = s.replace(old, new)
        a["configuration"]["script"] = s
    put = {k: rule[k] for k in ("uid", "name", "description", "tags", "triggers", "conditions", "actions", "configuration",
                                "configDescriptions", "visibility", "templateUID") if k in rule}
    print(f"{uid}: guard", call("PUT", f"/rules/{uid}", put)[0] if APPLY else "(check)")
