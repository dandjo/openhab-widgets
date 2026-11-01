#!/usr/bin/env python3
"""The leaving water offset in kelvins (user, 2026-11-01: "Alles auf K", as the day heating's offset): the item
pyaltherma_leaving_water_temp_offset_heating is a plain Number shown as "%+.0f K", no longer a Number:Temperature in
°C. On a °C item MainUI's slider would send "3 K", an absolute temperature (−270.15 °C); a plain Number takes and
sends bare numbers, which its MQTT channel (mqtt:number, unit °C) publishes as they are, so the unit reads them as a
difference. The rules heatpump_day_heating and heatpump_cycle_management send bare numbers as well. Its label,
category, tags and groups (persistence, the pyaltherma equipment) stay; the unit metadata goes. The view item of the
first attempt (…_k, a plain Number beside the °C item) is removed.
Usage: lw_offset_kelvin.py check|apply   (on homepi; the REST token from ~/.openhab_token, never printed)"""
import json, os, sys, urllib.error, urllib.parse, urllib.request

TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
BASE = "http://127.0.0.1:8080/rest"
APPLY = sys.argv[1:2] == ["apply"]
ITEM = "pyaltherma_leaving_water_temp_offset_heating"
FORMER = ITEM + "_k"
PATTERN = {"value": " ", "config": {"pattern": "%+.0f K", "min": -10, "max": 10, "step": 1}}


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
status, item = call("GET", f"/items/{q(ITEM)}?metadata=unit,stateDescription")
assert status == 200, f"{ITEM} missing"
meta = item.get("metadata") or {}
print(f"{ITEM}: type {item['type']}, unit metadata {meta.get('unit', {}).get('value')}, "
      f"pattern {meta.get('stateDescription', {}).get('config', {}).get('pattern')}")
former = call("GET", f"/items/{q(FORMER)}")[0] == 200
print(f"{FORMER}:", "exists" if former else "gone")
if APPLY:
    if item["type"] != "Number":
        dto = {k: item[k] for k in ("name", "label", "category", "tags", "groupNames") if k in item}
        print("item PUT", call("PUT", f"/items/{q(ITEM)}", dict(dto, type="Number"))[0])
    if "unit" in meta:
        print("unit metadata DELETE", call("DELETE", f"/items/{q(ITEM)}/metadata/unit")[0])
    print("stateDescription PUT", call("PUT", f"/items/{q(ITEM)}/metadata/stateDescription", PATTERN)[0])
    if former:
        for link in call("GET", f"/links?itemName={q(FORMER)}")[1] or []:
            print("former link DELETE", call("DELETE", f"/links/{q(FORMER)}/{q(link['channelUID'])}")[0])
        print("former item DELETE", call("DELETE", f"/items/{q(FORMER)}")[0])
