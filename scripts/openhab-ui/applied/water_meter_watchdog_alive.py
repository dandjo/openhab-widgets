#!/usr/bin/env python3
"""Let water_meter_watchdog call the water meter offline only when it has sent nothing (user, 2026-10-15): it took
water_meter_timestamp for the meter's last report, but AI-on-the-edge publishes there the time of its last valid
reading (firmware v16.1.0 sets it in SavePreValue(), which a round with an error skips). On the night of 15 October
2026 one reading 0.4 l too high (00:43) made every following round a "Neg. Rate" error until real use passed it at
02:00; the meter stayed connected and published every round, the watchdog reported it offline from 01:00 and again
after each restart. Now the rule takes the last update of water_meter_status, which the meter publishes at every step
of every round (every 3 min), errors included; a lasting reading error stays water_meter_error's to report. After a
restart the broker's retained status arrives before the rules run, so the meter does not look offline then either.
Usage: water_meter_watchdog_alive.py check|apply   (on homepi; the REST token from ~/.openhab_token, never printed)"""
import json
import os
import sys
import urllib.error
import urllib.request

TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
BASE = "http://127.0.0.1:8080/rest"
UID = "water_meter_watchdog"
APPLY = sys.argv[1:2] == ["apply"]

OLD = """const timestamp_item = items.getItem('water_meter_timestamp');
const is_alive = !timestamp_item.isUninitialized && timestamp_item.rawState.getInstant().isAfter(
  time.ZonedDateTime.now().minusMinutes(threshold_online_minutes).toInstant()
);"""
NEW = """// alive is any message: water_meter_status reports every step of every round (every 3 min), errors included, while
// water_meter_timestamp is the time of the last valid reading only and stood still through 75 minutes of
// "Neg. Rate" errors with the meter online (2026-10-15); a lasting reading error is water_meter_error's to report
const last_report = items.getItem('water_meter_status').lastStateUpdateInstant;
const is_alive = last_report !== null && last_report.isAfter(
  time.ZonedDateTime.now().minusMinutes(threshold_online_minutes).toInstant()
);"""


def patch(script):
    if NEW in script:
        return script, "already takes the status update"
    assert script.count(OLD) == 1, f"alive check found {script.count(OLD)} times"
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
    print(f"{UID}: PUT", call("PUT", f"/rules/{UID}", put)[0] if APPLY else "(check)")
    if APPLY:
        print(f"{UID}: runnow", call("POST", f"/rules/{UID}/runnow", {})[0])
