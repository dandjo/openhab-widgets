#!/usr/bin/env python3
"""The weather page's day popups (user, 2026-10-08: a tap on a forecast day opens its hours and quarter hours): the
items weather_hourly_days and weather_quarter_hours, and the rule weather_forecast with the script beside this script
(weather_forecast_rule.js), which fills them; through the REST API, openHAB keeps running. apply runs the rule once
afterwards, so the items hold the five days at once.
Usage: weather_day_setup.py check|apply   (on homepi, as pi; the API token in ~/.openhab_token, never printed)"""
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "i18n"))
from de_labels import RULE_DESCRIPTIONS  # noqa: E402

BASE = "http://127.0.0.1:8080/rest"
TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json",
                                          "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            text = r.read().decode()
            return r.status, (json.loads(text) if text.strip().startswith(("{", "[")) else None)
    except urllib.error.HTTPError as e:
        return e.code, None


def item(label, icon):
    return {"type": "String", "label": label, "category": f"material:{icon}", "tags": [],
            "groupNames": ["weather", "mapdb_change_restore"]}


ITEMS = {"weather_hourly_days": item("Wetter Stunden der fünf Tage", "schedule"),
         "weather_quarter_hours": item("Wetter Viertelstunden der fünf Tage", "schedule")}


def main():
    mode = sys.argv[1]
    if mode not in ("check", "apply"):
        sys.exit(__doc__)
    for name, dto in ITEMS.items():
        status, _ = call("GET", f"/items/{name}")
        print(f"item {name}: {'exists' if status == 200 else 'new'}")
        if mode == "apply":
            status, _ = call("PUT", f"/items/{name}", {"name": name, **dto})
            print(f"  PUT {status}")
            if status not in (200, 201):
                sys.exit(1)
    status, rule = call("GET", "/rules/weather_forecast")
    if status != 200:
        sys.exit(f"rule weather_forecast: GET {status}")
    (action,) = rule["actions"]
    script = open(os.path.join(HERE, "weather_forecast_rule.js")).read()
    changed = action["configuration"]["script"] != script
    print(f"rule weather_forecast: script {'changes' if changed else 'unchanged'} ({len(script)} chars)")
    if mode == "apply":
        action["configuration"]["script"] = script
        rule["description"] = RULE_DESCRIPTIONS["weather_forecast"]
        dto = {k: rule[k] for k in ("uid", "name", "description", "tags", "visibility", "triggers", "conditions",
                                    "actions", "configuration", "configDescriptions") if k in rule}
        status, _ = call("PUT", "/rules/weather_forecast", dto)
        print(f"  PUT {status}")
        if status != 200:
            sys.exit(1)
        status, _ = call("POST", "/rules/weather_forecast/runnow", {})
        print(f"  run now {status}")


main()
