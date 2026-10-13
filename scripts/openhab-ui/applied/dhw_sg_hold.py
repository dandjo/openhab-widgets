#!/usr/bin/env python3
"""Keep a forced-on hot-water charge's compressor running to its end (user, 2026-10-13): heatpump_dhw_management forces Smart Grid on
(3, the tank to 60 °C) on a PV surplus of 2 kW or more with the battery above 99 %, and took it back as soon as one of
them no longer held. The charge itself draws the battery below 100 % within one to three minutes (compressor and
booster heater 3.4 to 3.8 kW against about 3 kW of PV), so every forced charge ended after a few minutes and began again
once the battery was full: on 12 and 13 October 2026, 11 of 12 forced phases ended that way, with up to 7 compressor
starts an afternoon that lifted the tank 0.1 to 0.7 K each, every one leaving a hot compressor for the heating. Now
Smart Grid stays on while the compressor charges the tank and goes back to 0 once it has stopped, or earlier once the
battery falls below 80 %; the booster heater alone does not hold it, its stopping and starting again costs nothing
(user). Switching it on is unchanged. apply also sets the rule's German description from i18n/de_labels.py.
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

OLD = """  if (free_power <= -2000 && energyStorageFull()) {
    items.getItem('espaltherma_smart_grid').sendCommandIfDifferent('3');  // Forced ON
  } else {
    items.getItem('espaltherma_smart_grid').sendCommandIfDifferent('0');  // Free running
  }"""
NEW = """  // a forced charge's compressor runs to its end: the charge draws the battery below 100 % within minutes itself, and
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


def patch(script):
    if NEW in script:
        return script, "already holds forced charges"
    assert script.count(OLD) == 1, f"Smart Grid block found {script.count(OLD)} times"
    return script.replace(OLD, NEW), "patched"


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
