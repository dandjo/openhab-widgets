#!/usr/bin/env python3
"""The grid's strongest quarter-hours for the Stromzähler page (user, 2026-11-02: the grid operator charges for a
month's strongest quarter-hour mean of the import; which consumers cause it): the rule grid_peaks (grid_peaks.js
beside this script) writes every quarter-hour, a minute after it, and right after openHAB starts, a month's 7
strongest days by their strongest quarter-hour with what each consumer drew then. The values are numbers as the
daily energies have them: grid_peak_daily (kW) gets every day's strongest quarter as its values in InfluxDB, for the
overview's calendar (grid_peak_daily_backfill.py wrote the days before); grid_peak_monthly (kW) the running month's
peak as its state and every finished month since October 2024 once as a point in its measurement, the only store of
finished months, with the month's 7 days and their breakdowns as JSON beside the value. grid_peak_breakdown (JSON)
holds every month for the page, the running one first: it shows 6 and on demand the older ones. The consumers'
groups come from the UI generator (PEAK_GROUPS in dashboard.py), as the consumption card's.
Usage: grid_peaks.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token, never printed)"""
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(os.path.dirname(HERE), "dashboard.py")
MODE = sys.argv[1:]
sys.argv = [GEN, "check"]  # the generator's module code reads its mode; its main() is not run
ns = {"__file__": GEN, "__name__": "dashboard"}
exec(compile(open(GEN).read().replace("\nmain()\n", "\n"), GEN, "exec"), ns)

BASE = "http://127.0.0.1:8080/rest"
TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
RULE_UID = "grid_peaks"
BREAKDOWN_ITEM = ns["GRID_PEAK_BREAKDOWN"]
MONTHLY_ITEM = ns["GRID_PEAK_MONTHLY"]
DAILY_ITEM = ns["GRID_PEAK_DAILY"]
SCRIPT = open(os.path.join(HERE, "grid_peaks.js"), encoding="utf-8").read()


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def item_type(name):
    req = urllib.request.Request(f"{BASE}/items/{name}", headers={"Authorization": "Bearer " + TOKEN})
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)["type"]
    except urllib.error.HTTPError:
        return None


def main():
    if MODE[:1] not in (["check"], ["apply"]):
        sys.exit(__doc__)
    groups = [[name, items_] for name, items_, _ in ns["PEAK_GROUPS"]]
    rule = {
        "uid": RULE_UID,
        "name": "Netz-Spitzenviertelstunden",
        "description": "Sucht jede Viertelstunde die 7 stärksten Tage des laufenden Monats nach ihrer stärksten "
                       "Viertelstunde (Viertelstunden-Mittel der Netzleistung) samt der Leistung jeder "
                       "Verbrauchergruppe; die Spitze des Monats als Zustand von grid_peak_monthly und jeden "
                       "abgeschlossenen Monat ab Oktober 2024 einmal in dessen InfluxDB-Messreihe; alle Monate als "
                       "JSON in grid_peak_breakdown für die Seite Stromzähler; die stärkste Viertelstunde jedes "
                       "Tages als Wert von grid_peak_daily für den Kalender der Übersicht (applied/grid_peaks.py, "
                       "Gruppen aus dem UI-Generator).",
        "tags": [],
        "triggers": [{"id": "1", "type": "timer.GenericCronTrigger",
                      "configuration": {"cronExpression": "0 1/15 * * * ? *"}},
                     # right after a start too: the item is not persisted and would stay NULL until the next run
                     {"id": "3", "type": "core.SystemStartlevelTrigger", "configuration": {"startlevel": 100}}],
        "conditions": [],
        "actions": [{"id": "2", "type": "script.ScriptAction",
                     "configuration": {"type": "application/javascript",
                                       "script": SCRIPT.replace("__GROUPS__",
                                                                json.dumps(groups, ensure_ascii=False))}}],
    }
    # every month as the page reads it, worked out anew on every run (no MapDB: the finished months are the
    # measurement's, the running one is worked out again)
    breakdown = {"type": "String", "name": BREAKDOWN_ITEM, "label": "Netz-Spitzenlast Aufteilung",
                 "category": "material:bolt", "tags": [], "groupNames": []}
    # the running month's peak; the rule writes the finished months into InfluxDB itself, one point at a month's start
    monthly = {"type": "Number:Power", "name": MONTHLY_ITEM, "label": "Netz-Spitzenlast des Monats",
               "category": "material:bolt", "tags": [], "groupNames": []}
    # every day's strongest quarter for the overview's calendar: the rule writes its values into InfluxDB itself, one
    # a day at 23:59:59 as the daily energies, so it is in no persistence group; its state is the running day's
    daily = {"type": "Number:Power", "name": DAILY_ITEM, "label": "Netz-Spitzenlast des Tages",
             "category": "material:bolt", "tags": [], "groupNames": []}
    daily_meta = {"unit": {"value": "kW"}, "stateDescription": {"value": " ", "config": {"pattern": "%.2f %unit%"}}}
    for name in (BREAKDOWN_ITEM, MONTHLY_ITEM):
        print(f"item {name}:", "exists" if call("GET", f"/items/{name}") == 200 else "missing")
    print(f"item {DAILY_ITEM}:", "exists" if call("GET", f"/items/{DAILY_ITEM}") == 200 else "missing")
    exists = call("GET", f"/rules/{RULE_UID}") == 200
    print(f"rule {RULE_UID}:", "exists" if exists else "missing", f"({len(groups)} consumer groups)")
    if MODE[0] == "apply":
        print("breakdown item PUT", call("PUT", f"/items/{BREAKDOWN_ITEM}", breakdown))
        # an item of another type (the String grid_peak_monthly was until 2026-11-02) is made anew
        if item_type(MONTHLY_ITEM) not in (None, monthly["type"]):
            print("monthly item of another type DELETE", call("DELETE", f"/items/{MONTHLY_ITEM}"))
        for item, meta_ in ((monthly, daily_meta), (daily, daily_meta)):
            print(f"item {item['name']} PUT", call("PUT", f"/items/{item['name']}", item))
            for namespace, meta in meta_.items():
                print(f"  metadata {namespace} PUT", call("PUT", f"/items/{item['name']}/metadata/{namespace}", meta))
        print("rule", ("PUT " + str(call("PUT", f"/rules/{RULE_UID}", rule))) if exists else
              ("POST " + str(call("POST", "/rules", rule))))
        print("run now:", call("POST", f"/rules/{RULE_UID}/runnow", {}))


main()
