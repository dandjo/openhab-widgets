#!/usr/bin/env python3
"""Tado on the top level of the semantic model (user, 2026-11-11): the equipment tado, the Tado zone's temperature and
humidity, leaves the structural group air_conditioning (Klimaanlage) and stands alone, as apollo_air_1 does; its
members and their metadata stay as they are. Its page is generated (dashboard.py, tado_blocks()).
apply PUTs the item tado with the same type, label, category and tags and no group.
Usage: tado_top_level.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080/rest"
TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
ITEM = "tado"
LEAVES = "air_conditioning"


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, method=method, data=data,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            text = r.read().decode()
            return r.status, json.loads(text) if text else None
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


status, item = call("GET", f"/items/{ITEM}?recursive=false")
assert status == 200, (status, item)
print(f"{ITEM}: {item['type']}, groups {item['groupNames']}, tags {item['tags']}, members "
      f"{[m['name'] for m in item.get('members', [])] or 'see below'}")
body = {k: item[k] for k in ("type", "name", "label", "category", "tags") if k in item}
for key in ("groupType", "function"):  # a group's base type and aggregation, kept where it has them
    if key in item:
        body[key] = item[key]
body["groupNames"] = [g for g in item["groupNames"] if g != LEAVES]
print("PUT would set groupNames", body["groupNames"], "(unchanged)" if body["groupNames"] == item["groupNames"] else "")
if sys.argv[1] == "apply" and body["groupNames"] != item["groupNames"]:
    print(f"item {ITEM} PUT", call("PUT", f"/items/{ITEM}", body)[0])
    status, after = call("GET", f"/items/{ITEM}?recursive=false")
    print(f"{ITEM} now: groups {after['groupNames']}, tags {after['tags']}, label {after['label']}")
