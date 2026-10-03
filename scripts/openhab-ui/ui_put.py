#!/usr/bin/env python3
"""Write UI components into the running openHAB through its REST API, without a restart.

Usage: ui_put.py check|apply BODY   (on homepi, as pi)

BODY is what ui_diff.py writes: {"ui:page": {uid: component}, "ui:widget": {...}}, null for a uid to delete.
check reads every target first and says what apply would do; apply PUTs a component that exists, POSTs one that
does not and DELETEs a null. The API token is read from ~/.openhab_token and never printed.
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080/rest/ui/components"


def call(method, url, token, body=None):
    req = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json",
                                          "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def main():
    mode, path = sys.argv[1], sys.argv[2]
    if mode not in ("check", "apply"):
        sys.exit(__doc__)
    with open(os.path.expanduser("~/.openhab_token")) as f:
        token = f.read().strip()
    with open(path, encoding="utf-8") as f:
        body = json.load(f)
    failed = False
    for kind, components in body.items():
        for uid, value in components.items():
            url = f"{BASE}/{kind}/{uid}"
            status = call("GET", url, token)
            if status not in (200, 404):
                print(f"GET {kind}/{uid}: {status}")
                failed = True
                continue
            exists = status == 200
            if value is None:
                method, target = ("DELETE", url) if exists else (None, None)
            else:
                method, target = ("PUT", url) if exists else ("POST", f"{BASE}/{kind}")
            if method is None:
                print(f"{kind}/{uid}: already gone")
            elif mode == "check":
                print(f"{kind}/{uid}: would {method}")
            else:
                status = call(method, target, token, value)
                print(f"{method} {kind}/{uid}: {status}")
                failed |= status >= 300
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
