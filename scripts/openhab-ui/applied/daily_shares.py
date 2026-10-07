#!/usr/bin/env python3
"""The day's PV shares beside the daily totals (2026-10-07, Grafana's panel "PV-Eigenverbrauch pro Tag" rebuilt):
the items energy_daily_self_use_share (self-consumption / yield) and energy_daily_self_sufficiency
(self-consumption / house), in %, the daily totals rule as the generator now writes it, and their history computed
from the daily totals already stored (one point per day at its end, as the rule writes).
Usage: daily_shares.py check|apply   (on homepi; the REST token from ~/.openhab_token, never printed)"""
import json, os, subprocess, sys, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(os.path.dirname(HERE), "dashboard.py")
MODE = sys.argv[1:]
sys.argv = [GEN, "check"]
ns = {"__file__": GEN, "__name__": "dashboard"}
exec(compile(open(GEN).read().replace("\nmain()\n", "\n"), GEN, "exec"), ns)
TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
BASE = "http://127.0.0.1:8080/rest"
NUM = {"huawei_inverter_e_day": "energy_daily_pv", "home_ec_day": "energy_daily_home",
       "photovoltaics_own_ec_day": "energy_daily_self_use"}


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        return e.code, None


def series(m):
    out = subprocess.run(["influx", "-database", "openhab", "-format", "json", "-precision", "ns", "-execute",
                          f'SELECT "value" FROM "{m}"'], capture_output=True, text=True, check=True).stdout
    try:
        return {t: v for t, v in json.loads(out)["results"][0]["series"][0]["values"]}
    except (KeyError, IndexError):
        return {}


def main():
    if MODE[:1] not in (["check"], ["apply"]):
        sys.exit(__doc__)
    apply = MODE[0] == "apply"
    for item, label, own, whole in ns["DAILY_SHARES"]:
        exists = call("GET", f"/items/{item}")[0] == 200
        print(item, "exists" if exists else "missing")
        if apply and not exists:
            print("  PUT", call("PUT", f"/items/{item}", {"type": "Number:Dimensionless", "name": item, "label": label,
                                                         "category": "material:bar_chart", "tags": [], "groupNames": []})[0],
                  "unit", call("PUT", f"/items/{item}/metadata/unit", {"value": "%", "config": {}})[0],
                  "pattern", call("PUT", f"/items/{item}/metadata/stateDescription",
                                  {"value": " ", "config": {"pattern": "%.0f %%"}})[0])
    st, rule = call("GET", f"/rules/{ns['RULE_UID']}")
    script = rule["actions"][0]["configuration"]["script"]
    print("rule:", "up to date" if script == ns["RULE_SCRIPT"] else "differs")
    if apply and script != ns["RULE_SCRIPT"]:
        rule["actions"][0]["configuration"]["script"] = ns["RULE_SCRIPT"]
        put = {k: rule[k] for k in ("uid", "name", "description", "tags", "triggers", "conditions", "actions",
                                    "configuration", "configDescriptions", "visibility") if k in rule}
        print("  rule PUT", call("PUT", f"/rules/{ns['RULE_UID']}", put)[0])
    # history: the shares of every stored day, at the same moment as its totals
    own_s = series("energy_daily_self_use")
    for item, label, own, whole in ns["DAILY_SHARES"]:
        whole_s, done = series(NUM[whole]), series(item)
        lines = []
        for t, o in own_s.items():
            w = whole_s.get(t)
            if t in done or o is None or w is None or w <= 0:
                continue
            lines.append(f"{item},item={item} value={min(100.0, max(0.0, o / w * 100)):.1f} {t}")
        print(f"{item}: {len(lines)} days to write ({len(done)} there)")
        if apply and lines:
            req = urllib.request.Request("http://127.0.0.1:8086/write?db=openhab&rp=autogen&precision=ns",
                                         data="\n".join(lines).encode(), method="POST")
            print("  write", urllib.request.urlopen(req).status)


main()
