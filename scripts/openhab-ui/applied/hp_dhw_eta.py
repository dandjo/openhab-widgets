#!/usr/bin/env python3
"""When the tank's charge will end, for the heat pump's ring in the energy flow and in the heating card, which fills
towards that end, and for the line under the heating tile and the energy flow's tooltip (user, 2026-10-04): the rule
heatpump_dhw_eta sets heatpump_dhw_eta every minute while the tank charges (heatpump_dhw_since set), UNDEF otherwise.
The charge's target: 60 °C while Smart Grid is forced on (3, as the hot-water automation sets it on a PV surplus with a
full battery), else the DHW setpoint. Two phases, as the user described them (2026-10-04):
- the compressor (valve on DHW) charges fast, up to 55 °C at most: per 0.1 K the mean of the tank's rise over the
  last 3 minutes, shaped by the typical rise that slows as the tank warms (0.30 K/min at 35 °C, 0.26 at 49, 0.18
  from 51), and of the heat power over those 3 minutes divided by the kWh one kelvin at the sensor takes (0.42 at
  27 °C to 0.58 at 52, measured on the charges of winter 2025/26 and summer 2026); above 55 °C the booster heater
  takes 7 minutes per kelvin. From the charge's 5th minute on; during a defrost (the valve stays on DHW, the tank
  loses about 2.5 K in 5 minutes) and the 3 minutes after it the end moves on with the clock.
- the booster heater alone (valve off DHW) heats the water from the top, while the sensor sits in the upper third: a
  slow start, then a steep rise. Its curve, the share of the rise against the share of the time, goes as t^1.4;
  from the share reached and the rise over the last 3 minutes follow the phase's length and the time left, below 5 %
  of the rise 7 minutes per kelvin from the phase's start.
Replayed on whole charges (winter 2025/26, summer 2026) the end was missed by a median 4 to 5 minutes with the
compressor (about 1 in the last 10 minutes, 2 to 4 with 10 to 20 left), 3 (winter) to 9 (summer, PV surplus) with the
booster heater alone; an estimate stood in 94 to 96 % of the charges' minutes.
Usage: hp_dhw_eta.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080/rest"
TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
ITEM, LABEL = "heatpump_dhw_eta", "Wärmepumpe Warmwasser fertig um"
SCRIPT = """// when the tank's charge will end (see ~/scripts/openhab-ui/applied/hp_dhw_eta.py): the compressor from the tank's
// rise and the heat power over the last 3 minutes, up to 55 °C; the booster heater alone along its steepening curve
const eta = items.getItem('heatpump_dhw_eta');
const since = items.getItem('heatpump_dhw_since');
const tank = items.getItem('espaltherma_dhw_tank_temp');
const T = tank.numericState;
const setpoint = items.getItem('espaltherma_dhw_setpoint').numericState;
const target = items.getItem('espaltherma_smart_grid').state === '3' ? 60 : setpoint;
const dhw = items.getItem('espaltherma_3way_valve_mode').state === 'DHW';
const booster = items.getItem('espaltherma_bsh_mode').state === 'ON';
const now = time.toZDT();
const nowMs = now.toInstant().toEpochMilli();
const lastRun = cache.private.get('lastRun') || nowMs;
cache.private.put('lastRun', nowMs);
if (items.getItem('espaltherma_defrost_operaton').state === 'ON') {
  cache.private.put('defrost', nowMs);
}
const running = since.state !== 'NULL' && since.state !== 'UNDEF' && (dhw || booster);
const started = running ? time.toZDT(since.state).toInstant().toEpochMilli() : nowMs;
const curve = [[35, 0.30], [40, 0.28], [49, 0.26], [51, 0.18], [60, 0.17]];
const kwhPerK = [[27, 0.42], [32, 0.46], [37, 0.50], [42, 0.53], [47, 0.53], [52, 0.58]];
const interp = (pts, x) => {
  if (x <= pts[0][0]) return pts[0][1];
  for (let i = 1; i < pts.length; i++) {
    if (x <= pts[i][0]) {
      const [x0, y0] = pts[i - 1], [x1, y1] = pts[i];
      return y0 + (y1 - y0) * (x - x0) / (x1 - x0);
    }
  }
  return pts[pts.length - 1][1];
};
const past = tank.persistence.persistedState(now.minusMinutes(3), 'influxdb');
const rise = past === null || past.numericState === null || T === null ? null : (T - past.numericState) / 3;
let minutes = null;
let hold = false;
if (!running || T === null || target === null) {
  cache.private.remove('boosterStart');
} else if (T >= target - 0.1) {
  minutes = 0;
} else if (dhw) {
  cache.private.remove('boosterStart');
  const defrost = cache.private.get('defrost');
  if (defrost !== null && defrost !== undefined && nowMs - defrost < 3 * 60 * 1000) {
    hold = true;
  } else if (nowMs - started >= 5 * 60 * 1000) {
    const avg = items.getItem('espaltherma_heating_power').persistence.averageSince(now.minusMinutes(3), 'influxdb');
    const kw = avg === null || avg.numericState === null ? 0 : avg.numericState / 1000;
    const hpTarget = Math.min(target, 55);
    let m = 0;
    for (let x = T; x < hpTarget - 1e-9 && m !== null; x += 0.1) {
      const s = Math.min(0.1, hpTarget - x);
      const parts = [];
      if (rise !== null && rise > 0) parts.push(rise * interp(curve, x + s / 2) / interp(curve, T));
      if (kw > 0.5) parts.push(kw / interp(kwhPerK, x + s / 2) / 60);
      m = parts.length ? m + s / (parts.reduce((a, b) => a + b) / parts.length) : null;
    }
    if (m !== null) minutes = m + Math.max(0, target - Math.max(T, 55)) * 7;
  }
} else {
  let start = cache.private.get('boosterStart');
  if (start === null || start === undefined) {
    start = [nowMs, T];
    cache.private.put('boosterStart', start);
  }
  const span = Math.max(0.5, target - start[1]);
  const share = (T - start[1]) / span;
  if (share >= 0.05 && rise !== null && rise > 0) {
    const tau = Math.min(0.99, Math.pow(share, 1 / 1.4));
    minutes = 1.4 * span * Math.pow(tau, 0.4) / rise * (1 - tau);
  } else {
    minutes = Math.max(1, 7 * span - (nowMs - start[0]) / 60000);
  }
}
const known = eta.state !== 'NULL' && eta.state !== 'UNDEF';
if (minutes !== null) {
  eta.postUpdate(now.plusSeconds(Math.round(minutes * 60)));
} else if (hold && known) {
  // a defrost: no heat goes into the tank, the end moves on with the clock
  eta.postUpdate(time.toZDT(eta.state).plusSeconds(Math.round((nowMs - lastRun) / 1000)));
} else if (!hold && known) {
  eta.postUpdate('UNDEF');
}
"""
RULE = {
    "uid": "heatpump_dhw_eta",
    "name": "Wärmepumpe Warmwasser fertig um",
    "description": "Schätzt jede Minute, wann die Warmwasser-Ladung fertig ist (heatpump_dhw_eta): mit Verdichter aus "
                   "Anstieg und Wärmeleistung der letzten 3 Minuten bis 55 °C, darüber und mit dem Heizstab allein "
                   "entlang seiner steiler werdenden Kurve; für den Bogen der Wärmepumpe im Energiefluss und in "
                   "Heizung & Warmwasser.",
    "tags": [],
    "triggers": [{"type": "core.ItemStateChangeTrigger", "configuration": {"itemName": n}}
                 for n in ("espaltherma_3way_valve_mode", "heatpump_dhw_since", "espaltherma_dhw_setpoint",
                           "espaltherma_bsh_mode", "espaltherma_smart_grid", "espaltherma_defrost_operaton")] +
                [{"type": "timer.GenericCronTrigger", "configuration": {"cronExpression": "30 * * * * ? *"}}],
    "conditions": [],
    "actions": [{"id": "5", "type": "script.ScriptAction",
                 "configuration": {"type": "application/javascript", "script": SCRIPT}}],
}
for i, t in enumerate(RULE["triggers"]):
    t["id"] = str(i + 1)


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


apply = sys.argv[1] == "apply"
print(f"item {ITEM}:", "exists" if call("GET", f"/items/{ITEM}") == 200 else "missing")
print("rule heatpump_dhw_eta:", "exists" if call("GET", "/rules/heatpump_dhw_eta") == 200 else "missing")
if apply:
    print(ITEM, "PUT", call("PUT", f"/items/{ITEM}", {"type": "DateTime", "name": ITEM, "label": LABEL,
                                                      "category": "", "tags": [], "groupNames": []}))
    exists = call("GET", "/rules/heatpump_dhw_eta") == 200
    print("rule", "PUT " + str(call("PUT", "/rules/heatpump_dhw_eta", RULE)) if exists else
          "POST " + str(call("POST", "/rules", RULE)))
    print("run now:", call("POST", "/rules/heatpump_dhw_eta/runnow", {}))
