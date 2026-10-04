#!/usr/bin/env python3
"""Since when washing machine 2, a machine behind a plug without program data, runs (user, 2026-10-04): the rule
washing_machine_2_since sets washing_machine_2_since when its power rises above 10 W and sets it UNDEF once it has
drawn 10 W or less for 15 minutes, so soaking and pauses within a program do not restart it. The appliance tile
shows the line 'Läuft seit 19:45 · 35 min' from it.
Usage: wm2_run_since.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080/rest"
TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
ITEM = "washing_machine_2_since"
SCRIPT = """// since when washing machine 2 runs (above 10 W); a run ends after 15 minutes at 10 W or less, so soaking and pauses
// within a program do not restart it
const item = items.getItem('washing_machine_2_since');
const active = (items.getItem('washing_machine_2_power').numericState || 0) > 10;
const running = item.state !== 'NULL' && item.state !== 'UNDEF';
const now = time.toZDT();
if (active) {
  cache.private.put('last', now.toInstant().toEpochMilli());
  if (!running) {
    item.postUpdate(now);
  }
} else if (running) {
  const last = cache.private.get('last');
  if (last === null || last === undefined || now.toInstant().toEpochMilli() - last > 15 * 60 * 1000) {
    item.postUpdate('UNDEF');
  }
}
"""
RULE = {
    "uid": "washing_machine_2_since",
    "name": "Waschmaschine 2 läuft seit",
    "description": "Merkt sich, seit wann Waschmaschine 2 läuft (über 10 W), in washing_machine_2_since, für die "
                   "Kachel der Haushaltsgeräte; ein Lauf endet nach 15 Minuten bei höchstens 10 W.",
    "tags": [],
    "triggers": [{"id": "1", "type": "core.ItemStateChangeTrigger", "configuration": {"itemName": "washing_machine_2_power"}},
                 {"id": "2", "type": "timer.GenericCronTrigger", "configuration": {"cronExpression": "0 * * * * ? *"}}],
    "conditions": [],
    "actions": [{"id": "3", "type": "script.ScriptAction",
                 "configuration": {"type": "application/javascript", "script": SCRIPT}}],
}


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
print("rule washing_machine_2_since:", "exists" if call("GET", "/rules/washing_machine_2_since") == 200 else "missing")
if apply:
    print("item PUT", call("PUT", f"/items/{ITEM}", {"type": "DateTime", "name": ITEM, "label": "Waschmaschine 2 läuft seit",
                                                     "category": "", "tags": [], "groupNames": []}))
    exists = call("GET", "/rules/washing_machine_2_since") == 200
    print("rule", "PUT " + str(call("PUT", "/rules/washing_machine_2_since", RULE)) if exists else
          "POST " + str(call("POST", "/rules", RULE)))
    print("run now:", call("POST", "/rules/washing_machine_2_since/runnow", {}))
