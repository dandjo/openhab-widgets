#!/usr/bin/env python3
"""Smart Grid held in heatpump_dhw_management: the rule forces it on (3, the tank to 60 °C) on a PV surplus of 2 kW or
more with the battery above 99 %, and took it back as soon as one of them no longer held. Once on, it now holds:
- While the compressor charges the tank, always (user, 2026-10-18: a hot-water compressor run is never cut short; on
  2026-10-13 down to a battery of 80 %): the charge itself draws the battery below 100 % within one to three minutes
  (compressor and booster heater 3.4 to 3.8 kW against about 3 kW of PV), so every forced charge ended after a few
  minutes and began again once the battery was full: on 12 and 13 October 2026, 11 of 12 forced phases ended that
  way, with up to 7 compressor starts an afternoon that lifted the tank 0.1 to 0.7 K each, every one leaving a hot
  compressor for the heating.
- While the booster heater alone heats, down to a battery of 80 % (user, 2026-10-18).
- While the surplus is at least 1 kW (the same 15-minute mean, the heat pump left out) and the battery at least 95 %
  (user, 2026-10-18: until the surplus is really gone): the booster heater's 2 kW alone drew the battery below 100 %
  within minutes even with 2 to 3 kW to spare, so Smart Grid still flapped (18 October 2026: nine times from 12:03 to
  14:45 with seven booster runs, seven times on 12 and 13 October; at all but two of the switch-offs the surplus was
  still 2 to 3 kW, the battery at 98 to 99 %). Replayed on the seven Smart Grid days since 9 October, the surplus fell
  below 1 kW 0.5 to 4 hours after the first start.
Switching it on is unchanged. The earlier versions (2026-10-13, 2026-10-18 21:33) are replaced when found. Tested in
mini-racer (start, the holds and their ends, the lock, a missing reading).
apply also sets the rule's German description from i18n/de_labels.py.
Usage: dhw_sg_hold.py check|apply   (on homepi; the REST token from ~/.openhab_token, never printed)"""
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "i18n"))
from de_labels import RULE_DESCRIPTIONS  # noqa: E402

TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
BASE = "http://127.0.0.1:8080/rest"
UID = "heatpump_dhw_management"
APPLY = sys.argv[1:2] == ["apply"]

ORIGINAL = """  if (free_power <= -2000 && energyStorageFull()) {
    items.getItem('espaltherma_smart_grid').sendCommandIfDifferent('3');  // Forced ON
  } else {
    items.getItem('espaltherma_smart_grid').sendCommandIfDifferent('0');  // Free running
  }"""
# 2026-10-13: only a forced charge's compressor held it
V1 = """  // a forced charge's compressor runs to its end: the charge draws the battery below 100 % within minutes itself, and
  // taking Smart Grid back then stopped it, to start again once the battery was full (up to 7 compressor starts an
  // afternoon, 0.1 to 0.7 K each); only a battery below 80 % ends it early, and the booster heater alone holds
  // nothing, its stopping and starting again costs nothing (user, 2026-10-13)
  const forcedCharge = items.getItem('espaltherma_smart_grid').state === '3'
    && items.getItem('espaltherma_inv_frequency').numericState > 0
    && items.getItem('espaltherma_3way_valve_mode').state === 'DHW'
    && items.getItem('huawei_inverter_energy_storage_soc').numericState >= 80;
  if (free_power <= -2000 && energyStorageFull()) {
    items.getItem('espaltherma_smart_grid').sendCommandIfDifferent('3');  // Forced ON
  } else if (!forcedCharge) {
    items.getItem('espaltherma_smart_grid').sendCommandIfDifferent('0');  // Free running
  }"""
# 2026-10-18 21:33: also the surplus held it, a compressor charge only down to 80 %
V2 = """  // Smart Grid, once on, holds until the surplus is really gone (user, 2026-10-18), not only until the battery's first
  // per cent: the booster heater's 2 kW drew the battery below 100 % within minutes even with 2 to 3 kW to spare, and
  // Smart Grid flapped (18 October: nine times from 12:03 to 14:45); it ends once the surplus is below 1 kW (the same
  // 15-minute mean, the heat pump left out) or the battery below 95 %, so the heaters take at most about 0.4 kWh of the
  // evening's charge. A forced charge's compressor runs to its end even down to 80 %: taking Smart Grid back then
  // stopped it, to start again once the battery was full (up to 7 compressor starts an afternoon, 0.1 to 0.7 K each;
  // user, 2026-10-13)
  const smartGrid = items.getItem('espaltherma_smart_grid');
  const soc = items.getItem('huawei_inverter_energy_storage_soc').numericState;
  const forcedCharge = smartGrid.state === '3'
    && items.getItem('espaltherma_inv_frequency').numericState > 0
    && items.getItem('espaltherma_3way_valve_mode').state === 'DHW'
    && soc >= 80;
  const surplusHolds = smartGrid.state === '3' && free_power <= -1000 && soc >= 95;
  if (free_power <= -2000 && energyStorageFull()) {
    smartGrid.sendCommandIfDifferent('3');  // Forced ON
  } else if (!forcedCharge && !surplusHolds) {
    smartGrid.sendCommandIfDifferent('0');  // Free running
  }"""
NEW = """  // Smart Grid, once on, holds (user, 2026-10-18):
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
  }"""


def patch(script):
    if NEW in script:
        return script, "already patched"
    for old, how in ((V2, "patched (21:33 version replaced)"), (V1, "patched (2026-10-13 version replaced)"),
                     (ORIGINAL, "patched")):
        if old in script:
            assert script.count(old) == 1, f"Smart Grid block found {script.count(old)} times"
            return script.replace(old, NEW), how
    raise AssertionError("Smart Grid block not found")


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        return e.code, None


if __name__ == "__main__":
    st, rule = call("GET", f"/rules/{UID}")
    assert st == 200, (UID, st)
    for a in rule["actions"]:
        if a["configuration"].get("script"):
            a["configuration"]["script"], how = patch(a["configuration"]["script"])
            print(f"{UID}: {how}")
    put = {k: rule[k] for k in ("uid", "name", "description", "tags", "triggers", "conditions", "actions", "configuration",
                                "configDescriptions", "visibility", "templateUID") if k in rule}
    put["description"] = RULE_DESCRIPTIONS[UID]
    print(f"{UID}: PUT", call("PUT", f"/rules/{UID}", put)[0] if APPLY else "(check)")
