#!/usr/bin/env python3
"""A script (a rule without triggers) that sends a push notification to every device of openHAB Cloud with the text its
caller passes (user, 2026-10-20): POST /rest/rules/notify_broadcast/runnow with the body {"message": "..."}; openHAB
hands the body's keys to the script as variables. For services outside openHAB, which cannot call openHAB's actions:
pv_forecast_ml (/opt/pv_forecast_ml) when its nightly check discards a new model. Called without a text it sends
nothing and logs a warning.
apply creates or updates the script (notify_broadcast.js next to this file) with its German description from
i18n/de_labels.py.
Usage: notify_broadcast.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
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
UID = "notify_broadcast"
RULE = {
    "uid": UID,
    "name": "Benachrichtigung senden",
    "description": RULE_DESCRIPTIONS[UID],
    "tags": ["Script"],
    "triggers": [],
    "conditions": [],
    "actions": [{"id": "1", "type": "script.ScriptAction",
                 "configuration": {"type": "application/javascript",
                                   "script": open(os.path.join(HERE, "notify_broadcast.js"), encoding="utf-8").read()}}],
}


def call(method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, method=method, data=data,
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


exists = call("GET", f"/rules/{UID}") == 200
print(f"rule {UID}:", "exists" if exists else "missing")
if sys.argv[1] == "apply":
    print(f"rule {UID}", f"PUT {call('PUT', f'/rules/{UID}', RULE)}" if exists else f"POST {call('POST', '/rules', RULE)}")
