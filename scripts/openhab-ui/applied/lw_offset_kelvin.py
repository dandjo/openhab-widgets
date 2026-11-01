#!/usr/bin/env python3
"""The leaving water offset in kelvins for the UI (user, 2026-11-01: "Alles auf K", as the day heating's offset): the
item pyaltherma_leaving_water_temp_offset_heating is a Number:Temperature in °C, and MainUI's slider sends its value
with the unit it shows, so "3 K" would be taken as an absolute temperature (-270.15 °C). A plain Number linked to
the same MQTT channel (mqtt:number, unit °C) shows "+3 K" and sends a bare number, which the channel takes in its unit.
It has no groups and no tags: no persistence of its own and no second point in the semantic model; the rules keep
writing the °C item, both follow the channel's state.
Usage: lw_offset_kelvin.py check|apply   (on homepi; the REST token from ~/.openhab_token, never printed)"""
import json, os, sys, urllib.error, urllib.parse, urllib.request

TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
BASE = "http://127.0.0.1:8080/rest"
APPLY = sys.argv[1:2] == ["apply"]
SOURCE = "pyaltherma_leaving_water_temp_offset_heating"
ITEM = SOURCE + "_k"
CHANNEL = "mqtt:topic:mosquitto:pyaltherma:" + SOURCE


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
if sys.argv[1:2] not in (["check"], ["apply"]):
    sys.exit(__doc__)
item = {"type": "Number", "name": ITEM, "label": "Pyaltherma Vorlauf-Offset Heizen (K)", "category": "material:tune",
        "tags": [], "groupNames": []}
meta = {"value": " ", "config": {"pattern": "%+.0f K", "min": -10, "max": 10, "step": 1}}
link = {"itemName": ITEM, "channelUID": CHANNEL, "configuration": {}}
print(f"item {ITEM}:", "exists" if call("GET", f"/items/{q(ITEM)}")[0] == 200 else "missing")
print("link:", "exists" if call("GET", f"/links/{q(ITEM)}/{q(CHANNEL)}")[0] == 200 else "missing")
if APPLY:
    print("item PUT", call("PUT", f"/items/{q(ITEM)}", item)[0])
    print("stateDescription PUT", call("PUT", f"/items/{q(ITEM)}/metadata/stateDescription", meta)[0])
    print("link PUT", call("PUT", f"/links/{q(ITEM)}/{q(CHANNEL)}", link)[0])
