#!/usr/bin/env python3
"""60 °C on the sun's budget in heatpump_dhw_management, in place of Smart Grid (user, 2026-10-19).
The rule no longer switches Smart Grid. It forced the unit on (3, the tank to 60 °C) at a full battery and a surplus of
2 kW, mostly after the compressor's own stop at 55 °C, and below about 19 °C outside the unit then started the
compressor again at 54.x °C for 5 to 10 minutes (9 of 9 such switch-ons since 12 October 2026, none of 19 before, when
only the booster heater came). Instead the target goes to 60 °C when the PV forecast of pv_forecast_ml
(pv_forecast_hourly) pays for it: today's rest of the forecast, less the house until the PV ends (its last hour's mean
without the heat pump, at least 0.3 kW, plus 0.15 kW of heating) and what the battery still takes to be full
(0.075 kWh per %), must cover the tank's way to 60 °C (0.25 kWh per kelvin) plus a reserve of 0.5 kWh to begin, on the
same 2 kW surplus as 55 °C, and the way alone to keep it. Raised within a compressor charge, the booster heater takes
over at 55 °C at once (50 of 51 such charges since August 2025); on a tank at rest at 50 °C or above only the booster
heater comes, after its 20-minute timer ([8-03]), the compressor starting only 5 K under its 55 °C ([6-00]) (194
switches to 60 °C without Smart Grid, August 2025 to June 2026). When the budget fails during a charge the target goes
back to 55 °C, where the booster heater stops and a compressor run still ends (never cut short, user 2026-10-18).
Replaces the Smart Grid block of dhw_sg_hold.py (its NEW version, live since 2026-10-18 21:45) and drops its helper and
the lock comment's mention. Tested in mini-racer (begin, hold, abort in both phases, the rest at a tank at rest,
sunset, a stale or missing forecast, the lock, a missing reading, the log line; Smart Grid never commanded).
apply also sets the rule's German description from i18n/de_labels.py, and Smart Grid to 0 if it is not.
Usage: dhw_sun_budget.py check|apply   (on homepi; the REST token from ~/.openhab_token, never printed)"""
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "http://127.0.0.1:8080/rest"
UID = "heatpump_dhw_management"

HELPER = """const energyStorageFull = () =>
  items.getItem('huawei_inverter_energy_storage_soc').numericState > 99;

"""
LOCK_OLD = """switching it on by hand meanwhile holds until 12 h. Smart Grid
// forces nothing during the lock (below, as the hot water is off)
"""
LOCK_NEW = """switching it on by hand meanwhile holds until 12 h
"""
ANCHOR = """const tankTempReachedSetpoint = () =>
  items.getItem('espaltherma_dhw_tank_temp').numericState >= items.getItem('pyaltherma_dhw_temp_heating').numericState;
"""
BUDGET = """
// 60 °C when the sun pays for it (user, 2026-10-19), in place of Smart Grid: what today's rest of the PV forecast (pv_forecast_ml,
// pv_forecast_hourly) would still send to the grid once the house is covered until the PV ends and the battery is full; when
// that covers the tank's way to 60 °C, the target is 60 °C. Within a compressor charge the booster heater then takes
// over at 55 °C at once (50 of 51 such charges since August 2025, down to 2 °C outside), where Smart Grid, switched on
// at a full battery after the compressor's stop, started the compressor again at 54.x °C below about 19 °C outside
// (9 of 9 since 12 October 2026); a tank at rest at 50 °C or above gets only the booster heater, after its 20-minute
// delay timer ([8-03]), as the compressor starts only 5 K under its 55 °C ([6-00])
const BATTERY_KWH_PER_PERCENT = 0.075;  // 7.5 kWh: the battery's charge counter against its level, 15 to 19 October 2026
const HOUSE_KW_MIN = 0.3;               // the house without the heat pump at the least
const HEATING_KW = 0.15;                // the space heating's mean from 12 to 17 h (0.02 to 0.20 kW, 12 to 19 October 2026)
const TANK_KWH_PER_K = 0.25;            // electricity per kelvin of the tank: the compressor's to its 55 °C (2.9 kWh for 43
                                        // to 55 °C on 19 October 2026) as the booster heater's above (1.1 to 1.2 kWh to 60)
const RESERVE = 0.5;                    // kWh the budget must leave over to begin 60 °C, not to keep it

// kWh today's rest of the PV would still send to the grid, or null without a fresh forecast (3 hours) or once the PV
// has ended; the house by its last hour's mean without the heat pump, plus the heating
const sunSpare = () => {
  let forecast = null;
  try {
    forecast = JSON.parse(items.getItem('pv_forecast_hourly').state);
  } catch (e) {
    return null;
  }
  const now = Date.now() / 1000;
  if (!forecast || !Array.isArray(forecast.h) || !(now - forecast.at < 3 * 3600)) {
    return null;
  }
  const midnight = time.toZDT('00:00').plusDays(1).toEpochSecond();
  let pv = 0;
  let hours = 0;
  for (const [start, watts] of forecast.h) {
    const share = Math.max(0, Math.min(start + 3600, midnight) - Math.max(start, now)) / 3600;
    pv += watts / 1000 * share;
    if (watts >= 100) {
      hours += share;
    }
  }
  if (hours === 0) {
    return null;
  }
  const since = time.ZonedDateTime.now().minusMinutes(60);
  const mean = (name) => {
    const s = items.getItem(name).persistence.averageSince(since, 'influxdb');
    return s === null || s === undefined ? null : s.numericState;
  };
  const home = mean('home_active_power');
  const pump = mean('espaltherma_electrical_power');
  const house = Math.max(HOUSE_KW_MIN, home !== null && pump !== null ? (home - pump) / 1000 : 0) + HEATING_KW;
  return pv - house * hours - (100 - items.getItem('huawei_inverter_energy_storage_soc').numericState)
    * BATTERY_KWH_PER_PERCENT;
};
"""
TAIL_OLD = """  // Smart Grid, once on, holds (user, 2026-10-18):
  // - while the compressor charges the tank, always: a hot-water compressor run is never cut short (user), and taking
  //   Smart Grid back stopped it, to start again once the battery was full (12 and 13 October: up to 7 compressor
  //   starts an afternoon, 0.1 to 0.7 K each);
  // - while the booster heater alone heats, down to a battery of 80 %;
  // - while the surplus is at least 1 kW (the same 15-minute mean, the heat pump left out) and the battery at least
  //   95 %: the booster heater's 2 kW drew the battery below 100 % within minutes even with 2 to 3 kW to spare, and
  //   Smart Grid flapped while that ended it (18 October: nine times from 12:03 to 14:45)
  const smartGrid = items.getItem('espaltherma_smart_grid');
  const soc = items.getItem('huawei_inverter_energy_storage_soc').numericState;
  const compressorCharge = items.getItem('espaltherma_inv_frequency').numericState > 0
    && items.getItem('espaltherma_3way_valve_mode').state === 'DHW';
  const holds = smartGrid.state === '3'
    && (compressorCharge || (isBsh() && soc >= 80) || (free_power <= -1000 && soc >= 95));
  if (free_power <= -2000 && energyStorageFull()) {
    smartGrid.sendCommandIfDifferent('3');  // Forced ON
  } else if (!holds) {
    smartGrid.sendCommandIfDifferent('0');  // Free running
  }
  // set setpoint only if machine not active or if setpoint is greater than current setpoint, and only if it changed
  if ((!isInverterDhw() && !isBsh()) || dhw_setpoint > items.getItem('pyaltherma_dhw_temp_heating').numericState) {
    items.getItem('pyaltherma_dhw_temp_heating').sendCommandIfDifferent(Quantity(dhw_setpoint + ' °C'));
  }
"""
TAIL_NEW = """  // 60 °C when the sun pays for it (above): begun on the same 2 kW surplus as 55 °C and with the reserve, kept while
  // the budget still covers the rest of the tank's way; logged when it begins or ends
  const current = items.getItem('pyaltherma_dhw_temp_heating').numericState;
  const tank = items.getItem('espaltherma_dhw_tank_temp').numericState;
  const spare = isIdletime() || tank === null ? null : sunSpare();
  const need = tank === null ? null : Math.max(0, 60 - tank) * TANK_KWH_PER_K;
  if (spare !== null && ((current >= 60 && spare >= need) || (free_power <= -2000 && spare >= need + RESERVE))) {
    dhw_setpoint = 60;
  }
  if ((dhw_setpoint === 60) !== (current >= 60)) {
    console.info(`hot water: ${dhw_setpoint === 60 ? '60 °C' : 'back from 60 °C'}, the sun's budget `
      + `${spare === null ? 'none' : `${spare.toFixed(1)} kWh`} for ${need === null ? '?' : need.toFixed(1)} kWh `
      + `(tank ${tank} °C, surplus ${Math.round(-free_power)} W)`);
  }
  // set setpoint only if machine not active or if setpoint is greater than current setpoint, and only if it changed;
  // a 60 °C the sun no longer pays for goes back to 55 °C during a charge: the booster heater stops there, and a
  // compressor run still ends at its 55 °C, it is never cut short (user, 2026-10-18)
  if ((!isInverterDhw() && !isBsh()) || dhw_setpoint > current) {
    items.getItem('pyaltherma_dhw_temp_heating').sendCommandIfDifferent(Quantity(dhw_setpoint + ' °C'));
  } else if (current >= 60 && dhw_setpoint < 60) {
    items.getItem('pyaltherma_dhw_temp_heating').sendCommandIfDifferent(Quantity('55 °C'));
  }
"""
# the first version of 2026-10-19 (live from 15:38 for a few minutes), without the log line
TAIL_V1 = """  // 60 °C when the sun pays for it (above): begun on the same 2 kW surplus as 55 °C and with the reserve, kept while
  // the budget still covers the rest of the tank's way
  const current = items.getItem('pyaltherma_dhw_temp_heating').numericState;
  const tank = items.getItem('espaltherma_dhw_tank_temp').numericState;
  const spare = isIdletime() || tank === null ? null : sunSpare();
  if (spare !== null) {
    const need = Math.max(0, 60 - tank) * TANK_KWH_PER_K;
    if ((current >= 60 && spare >= need) || (free_power <= -2000 && spare >= need + RESERVE)) {
      dhw_setpoint = 60;
    }
  }
  // set setpoint only if machine not active or if setpoint is greater than current setpoint, and only if it changed;
  // a 60 °C the sun no longer pays for goes back to 55 °C during a charge: the booster heater stops there, and a
  // compressor run still ends at its 55 °C, it is never cut short (user, 2026-10-18)
  if ((!isInverterDhw() && !isBsh()) || dhw_setpoint > current) {
    items.getItem('pyaltherma_dhw_temp_heating').sendCommandIfDifferent(Quantity(dhw_setpoint + ' °C'));
  } else if (current >= 60 && dhw_setpoint < 60) {
    items.getItem('pyaltherma_dhw_temp_heating').sendCommandIfDifferent(Quantity('55 °C'));
  }
"""
PAIRS = [(HELPER, ""), (LOCK_OLD, LOCK_NEW), (ANCHOR, ANCHOR + BUDGET), (TAIL_OLD, TAIL_NEW)]


def patch(script):
    if TAIL_NEW in script and BUDGET in script:
        return script, "already patched"
    if TAIL_V1 in script and BUDGET in script:
        assert script.count(TAIL_V1) == 1
        return script.replace(TAIL_V1, TAIL_NEW), "patched (first version of 2026-10-19 replaced)"
    for old, new in PAIRS:
        assert script.count(old) == 1, f"block found {script.count(old)} times: {old[:60]!r}"
        script = script.replace(old, new)
    assert "smart_grid" not in script and "energyStorageFull" not in script, "Smart Grid left in the script"
    return script, "patched"


def call(method, path, token, body=None, content="application/json"):
    data = None if body is None else (body if isinstance(body, str) else json.dumps(body)).encode()
    req = urllib.request.Request(BASE + path, method=method, data=data,
                                 headers={"Authorization": "Bearer " + token, "Content-Type": content})
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw.startswith((b"{", b"[")) else raw.decode()
    except urllib.error.HTTPError as e:
        return e.code, None


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(HERE, "..", "i18n"))
    from de_labels import RULE_DESCRIPTIONS  # noqa: E402
    APPLY = sys.argv[1:2] == ["apply"]
    TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
    assert call("GET", "/items/pv_forecast_hourly", TOKEN)[0] == 200, "pv_forecast_hourly missing (pv_forecast.py)"
    st, rule = call("GET", f"/rules/{UID}", TOKEN)
    assert st == 200, (UID, st)
    for a in rule["actions"]:
        if a["configuration"].get("script"):
            a["configuration"]["script"], how = patch(a["configuration"]["script"])
            print(f"{UID}: {how} ({len(a['configuration']['script'])} chars)")
    put = {k: rule[k] for k in ("uid", "name", "description", "tags", "triggers", "conditions", "actions", "configuration",
                                "configDescriptions", "visibility", "templateUID") if k in rule}
    put["description"] = RULE_DESCRIPTIONS[UID]
    print(f"{UID}: PUT", call("PUT", f"/rules/{UID}", TOKEN, put)[0] if APPLY else "(check)")
    sg = call("GET", "/items/espaltherma_smart_grid/state", TOKEN)[1]
    print("espaltherma_smart_grid:", sg, "->", ("0 " + str(call("POST", "/items/espaltherma_smart_grid", TOKEN, "0",
                                                                 "text/plain")[0])) if APPLY and sg != "0" else "unchanged")
