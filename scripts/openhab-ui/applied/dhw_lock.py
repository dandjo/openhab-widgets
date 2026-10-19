#!/usr/bin/env python3
"""Hot water off from 21 to 12 h and the tank's main charge in the afternoon (user, 2026-10-18), in
heatpump_dhw_management:
- A PV surplus raises the setpoint to 55 °C only from 12 h: the air is warmest then and the PV strongest, the tank
  stands hot for less time before the evening's showers (draws peak 18-22 h and 7-10 h), and the heating's start at
  9 h keeps the compressor to itself.
- From 21 to 12 h the rule switches the hot water off (pyaltherma_dhw_power) instead of holding the tank at 30 °C: 30 °C
  is no hot water, a tank drawn below it in the evening was charged at the compressor's highest speed for nothing
  (16 October 2026: 18 minutes at 59 to 64 Hz up to 30 °C; the morning's charge began at 27.6 °C anyway), and in the
  month before no morning charge was one to 30 °C (all 27 were PV charges to 55 °C). The 30 °C setpoint is gone:
  switched on by hand during the lock, the hot water heats to the default 45 °C. A charge still running at 21 h ends
  first. The Switch heatpump_dhw_lock (InfluxDB on change, MapDB restores it) remembers that the rule
  switched it off, so 12 h switches on only what the lock switched off: a switch-off by hand stays, a switch-on by
  hand meanwhile holds until 12 h, and switching the management off turns the hot water on again. Smart Grid forces
  nothing during the lock (three forced charges in the month before began 11:24-11:55; they now wait for 12 h). The
  Daikin ran no disinfection in that time (the tank above 57.5 °C only by day in the 120 days before).
The same day's earlier versions (off 21 to 6 h, 30 °C until 12 h; the lock's item first named heatpump_dhw_night_off,
renamed when the lock reached noon: its state is carried over, then the old item and its few points in InfluxDB go)
are undone first. Tested in mini-racer (the lock, a
running charge or booster heater waits, manual switching, a restart's missing readings, the management switched off,
the setpoints by time and surplus).
apply also creates the item and sets the rule's German description from i18n/de_labels.py.
Usage: dhw_lock.py check|apply   (on homepi; the REST token from ~/.openhab_token, never printed)"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "i18n"))
from de_labels import RULE_DESCRIPTIONS  # noqa: E402

TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
BASE = "http://127.0.0.1:8080/rest"
UID = "heatpump_dhw_management"
FLAG, OLD_FLAG = "heatpump_dhw_lock", "heatpump_dhw_night_off"
ITEM = {"type": "Switch", "name": FLAG, "label": "Wärmepumpe Warmwasser-Sperre", "category": "material:lock_clock",
        "tags": [], "groupNames": ["influxdb_change", "mapdb_change_restore"]}
APPLY = sys.argv[1:2] == ["apply"]

# the script before 2026-10-18 (ORIGINAL blocks) and what this applier makes of it
OLD_IDLE = """const isIdletime = () =>
  time.ZonedDateTime.now().isBetweenTimes('21:00', '12:00');"""
OLD_SET30 = """  if (isIdletime()) {
    dhw_setpoint = 30;
  }
"""
NEW_SET30 = """  // no 30 °C any more from 21 to 12 h: the hot water is off then (below); switched on by hand meanwhile it heats to
  // the default 45 °C, real hot water (user, 2026-10-18)
"""
OLD_PV = """  if (free_power <= -2000) {
    dhw_setpoint = 55;
  }"""
NEW_PV = """  // the tank's main charge in the afternoon (user, 2026-10-18): the air is warmest then and the PV strongest, the tank
  // stands hot for less time before the evening's showers, and the heating's start at 9 h keeps the compressor to
  // itself; before 12 h the tank keeps what the evening left
  if (free_power <= -2000 && !isIdletime()) {
    dhw_setpoint = 55;
  }"""
OLD_MAIN = """// domestic hot water

if ("""
NEW_MAIN = """// domestic hot water

// off from 21 to 12 h (user, 2026-10-18), instead of held at 30 °C until 12 h: 30 °C is no hot water, a tank drawn
// below it in the evening was charged at the compressor's highest speed for nothing (16 October: 18 minutes at 59 to
// 64 Hz up to 30 °C, the morning's charge began at 27.6 °C anyway), and the day's charge comes from 12 h (above); in the
// month before, no morning charge was one to 30 °C, all 27 were PV charges to 55 °C. A charge still running at 21 h
// ends first. heatpump_dhw_lock remembers that the rule switched it off, so 12 h switches back on only what the
// lock switched off: a switch-off by hand stays, and switching it on by hand meanwhile holds until 12 h. Smart Grid
// forces nothing during the lock (below, as the hot water is off)
const dhwLock = items.getItem('heatpump_dhw_lock');
if (items.getItem('heatpump_dhw_management').state === 'ON' && isIdletime()) {
  if (!missing && dhwLock.state !== 'ON' && items.getItem('pyaltherma_dhw_power').state === 'ON'
      && !isInverterDhw() && !isBsh()) {
    dhwLock.postUpdate('ON');
    items.getItem('pyaltherma_dhw_power').sendCommand('OFF');
  }
} else if (dhwLock.state === 'ON') {
  // 12 h, or the management switched off: hot water on again
  dhwLock.postUpdate('OFF');
  items.getItem('pyaltherma_dhw_power').sendCommandIfDifferent('ON');
}

if ("""
PAIRS = [(OLD_SET30, NEW_SET30), (OLD_PV, NEW_PV), (OLD_MAIN, NEW_MAIN)]

# the earlier versions of the same day (live 03:20 and 03:40: off 21 to 6 h, 30 °C until 12 h), undone before PAIRS
V1_IDLE = OLD_IDLE + """

const isNight = () =>
  time.ZonedDateTime.now().isBetweenTimes('21:00', '06:00');"""
V2_MAIN = """// domestic hot water

// off at night, 21 to 6 h, instead of held at 30 °C (user, 2026-10-18): 30 °C is no hot water, and a tank drawn below
// it in the evening was charged at the compressor's highest speed for nothing (16 October: 18 minutes at 59 to 64 Hz up
// to 30 °C, the morning's charge began at 27.6 °C anyway). A charge still running at 21 h ends first.
// heatpump_dhw_night_off remembers that the rule switched it off, so the morning switches back on only what the night
// switched off: a switch-off by hand stays, and switching it on by hand at night holds until the morning
const nightOff = items.getItem('heatpump_dhw_night_off');
if (items.getItem('heatpump_dhw_management').state === 'ON' && isNight()) {
  if (!missing && nightOff.state !== 'ON' && items.getItem('pyaltherma_dhw_power').state === 'ON'
      && !isInverterDhw() && !isBsh()) {
    nightOff.postUpdate('ON');
    // the night's 30 °C set before switching off, so the morning switches on without a charge to the evening's 45 °C
    // (the setpoint below follows the switch only on the next run, as the switch's state lags its command)
    items.getItem('pyaltherma_dhw_temp_heating').sendCommandIfDifferent(Quantity('30 °C'));
    items.getItem('pyaltherma_dhw_power').sendCommand('OFF');
  }
} else if (nightOff.state === 'ON') {
  // the morning, or the management switched off: hot water on again
  nightOff.postUpdate('OFF');
  items.getItem('pyaltherma_dhw_power').sendCommandIfDifferent('ON');
}

if ("""
V1_MAIN = V2_MAIN.replace("""    // the night's 30 °C set before switching off, so the morning switches on without a charge to the evening's 45 °C
    // (the setpoint below follows the switch only on the next run, as the switch's state lags its command)
    items.getItem('pyaltherma_dhw_temp_heating').sendCommandIfDifferent(Quantity('30 °C'));
""", "")
# the third, live 03:55, with the item named heatpump_dhw_night_off
V3_MAIN = NEW_MAIN.replace("heatpump_dhw_lock", "heatpump_dhw_night_off").replace("dhwLock", "nightOff")
UNDO = [(V1_IDLE, OLD_IDLE), (V3_MAIN, OLD_MAIN), (V2_MAIN, OLD_MAIN), (V1_MAIN, OLD_MAIN), (NEW_PV, OLD_PV),
        (NEW_SET30, OLD_SET30)]


def patch(script):
    if NEW_MAIN in script and NEW_SET30 in script and NEW_PV in script:
        return script, "already patched"
    undone = [new for new, old in UNDO if new in script]
    for new, old in UNDO:
        script = script.replace(new, old)
    for old, new in PAIRS:
        assert script.count(old) == 1, ("block found", script.count(old), old[:50])
        script = script.replace(old, new)
    return script, "patched" + (" (earlier version undone)" if undone else "")


def call(method, path, body=None, content="application/json"):
    data = None if body is None else (body if isinstance(body, str) else json.dumps(body)).encode()
    req = urllib.request.Request(BASE + path, method=method, data=data,
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": content})
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw[:1] in (b"{", b"[") else None
    except urllib.error.HTTPError as e:
        return e.code, None


if __name__ == "__main__":
    st, item = call("GET", f"/items/{FLAG}")
    print(f"item {FLAG}:", f"exists, state {item['state']}" if st == 200 else "missing")
    st, rule = call("GET", f"/rules/{UID}")
    assert st == 200, (UID, st)
    for a in rule["actions"]:
        if a["configuration"].get("script"):
            a["configuration"]["script"], how = patch(a["configuration"]["script"])
            print(f"{UID}: {how}")
    st, old = call("GET", f"/items/{OLD_FLAG}")
    print(f"item {OLD_FLAG}:", f"exists, state {old['state']} (to be carried over and removed)" if st == 200 else "gone")
    if APPLY:
        # the item first: the patched script reads it; it takes over the old item's state (ON while the lock holds)
        print(f"item {FLAG} PUT", call("PUT", f"/items/{FLAG}", ITEM)[0])
        if call("GET", f"/items/{FLAG}")[1]["state"] in ("NULL", "UNDEF"):
            state = old["state"] if old and old["state"] in ("ON", "OFF") else "OFF"
            print(f"item {FLAG} state {state}", call("PUT", f"/items/{FLAG}/state", state, "text/plain")[0])
    put = {k: rule[k] for k in ("uid", "name", "description", "tags", "triggers", "conditions", "actions", "configuration",
                                "configDescriptions", "visibility", "templateUID") if k in rule}
    put["description"] = RULE_DESCRIPTIONS[UID]
    print(f"{UID}: PUT", call("PUT", f"/rules/{UID}", put)[0] if APPLY else "(check)")
    if APPLY and old:
        # only once the rule reads the new item: the old one, then its few points of the same night in InfluxDB
        print(f"item {OLD_FLAG} DELETE", call("DELETE", f"/items/{OLD_FLAG}")[0])
        q = urllib.parse.urlencode({"db": "openhab", "q": f'DROP MEASUREMENT "{OLD_FLAG}"'}).encode()
        with urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8086/query", data=q)) as r:
            print(f"InfluxDB {OLD_FLAG} DROP MEASUREMENT", r.status)
