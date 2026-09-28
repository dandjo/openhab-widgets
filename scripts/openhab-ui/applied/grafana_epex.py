#!/usr/bin/env python3
"""Replace the computed aWATTar curves in Grafana's Overview > EPEX Spot panel with the stored measurements.

Reads a service-account token from ~/.grafana-token; the token is never printed.
Usage: grafana_epex.py check|apply
"""
import copy
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:3000/apis/dashboard.grafana.app/v2/namespaces/default/dashboards/S8ZmnnBVz"
SERIES = [
    ("aWATTar market net", "epex_spot_awattar"),
    ("aWATTar market gross", "epex_spot_awattar_market_gross"),
    ("aWATTar total net", "epex_spot_awattar_total_net"),
    ("aWATTar total gross", "epex_spot_awattar_total_gross"),
]


def request(method, body=None):
    token = open(os.path.expanduser("~/.grafana-token")).read().strip()
    req = urllib.request.Request(BASE, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} failed: HTTP {e.code} {e.read()[:300]!r}")


def main():
    dash = request("GET")
    panel = next(e for e in dash["spec"]["elements"].values() if e["spec"].get("title") == "EPEX Spot")
    queries = panel["spec"]["data"]["spec"]["queries"]
    print("before:", [(q["spec"]["query"]["spec"]["alias"], q["spec"]["query"]["spec"]["measurement"],
                       q["spec"]["query"]["spec"]["select"][0][-1]["params"][0]) for q in queries])
    template = next(q for q in queries if q["spec"]["refId"] == "epex_spot_awattar")
    new = []
    for alias, measurement in SERIES:
        q = copy.deepcopy(template)
        q["spec"]["refId"] = measurement
        q["spec"]["query"]["spec"]["alias"] = alias
        q["spec"]["query"]["spec"]["measurement"] = measurement
        q["spec"]["query"]["spec"]["select"][0][-1]["params"] = [" * 100"]
        new.append(q)
    panel["spec"]["data"]["spec"]["queries"] = new
    print("after: ", [(q["spec"]["query"]["spec"]["alias"], q["spec"]["query"]["spec"]["measurement"],
                       q["spec"]["query"]["spec"]["select"][0][-1]["params"][0]) for q in new])
    print("resourceVersion:", dash["metadata"].get("resourceVersion"), "generation:", dash["metadata"].get("generation"))
    if sys.argv[1] != "apply":
        return
    result = request("PUT", dash)
    print("saved, generation:", result["metadata"].get("generation"))


main()
