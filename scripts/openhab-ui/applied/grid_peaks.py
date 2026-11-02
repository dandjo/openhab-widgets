#!/usr/bin/env python3
"""The grid's strongest quarter-hours for the Stromzähler page (user, 2026-11-02: the grid operator charges for a
month's strongest quarter-hour mean of the import; which consumers cause it): the rule grid_peaks (grid_peaks.js
beside this script) writes every quarter-hour, a minute after it, and right after openHAB starts, for each of the last
6 months its 7 strongest days by their strongest quarter-hour with what each consumer drew then, as JSON into the
String item grid_peaks, which MapDB restores, so finished months need not be worked out again; and every finished
month since October 2024 once into the InfluxDB measurement grid_peak_months, to trace them back beyond 6 months,
the whole archive also into the String item grid_peaks_archive for the page's older months. The consumers' groups come
from the UI generator (PEAK_GROUPS in dashboard.py), as the consumption card's.
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
ITEM = RULE_UID = ns["GRID_PEAKS"]
ARCHIVE_ITEM = ns["GRID_PEAKS_ARCHIVE"]
SCRIPT = open(os.path.join(HERE, "grid_peaks.js"), encoding="utf-8").read()


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def main():
    if MODE[:1] not in (["check"], ["apply"]):
        sys.exit(__doc__)
    groups = [[name, items_] for name, items_, _ in ns["PEAK_GROUPS"]]
    rule = {
        "uid": RULE_UID,
        "name": "Netz-Spitzenviertelstunden",
        "description": "Sucht jede Viertelstunde für die letzten 6 Monate die 7 stärksten Tage nach ihrer "
                       "stärksten Viertelstunde (Viertelstunden-Mittel der Netzleistung) und schreibt sie samt der "
                       "Leistung jeder Verbrauchergruppe als JSON in grid_peaks, für die Seite Stromzähler; "
                       "abgeschlossene Monate übernimmt sie aus dem letzten Ergebnis und schreibt jeden einmal ins "
                       "InfluxDB-Archiv grid_peak_months, ab Oktober 2024 (applied/grid_peaks.py, Gruppen aus dem "
                       "UI-Generator).",
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
    # restored after a restart: the rule takes the finished months from it
    item = {"type": "String", "name": ITEM, "label": "Netz-Spitzenviertelstunden", "category": "material:bolt",
            "tags": [], "groupNames": ["mapdb_change_restore"]}
    # the archive as the page reads it; the rule writes it anew from InfluxDB on every run where it changed
    archive = {"type": "String", "name": ARCHIVE_ITEM, "label": "Netz-Spitzenviertelstunden Archiv",
               "category": "material:bolt", "tags": [], "groupNames": []}
    print(f"item {ITEM}:", "exists" if call("GET", f"/items/{ITEM}") == 200 else "missing")
    print(f"item {ARCHIVE_ITEM}:", "exists" if call("GET", f"/items/{ARCHIVE_ITEM}") == 200 else "missing")
    exists = call("GET", f"/rules/{RULE_UID}") == 200
    print(f"rule {RULE_UID}:", "exists" if exists else "missing", f"({len(groups)} consumer groups)")
    if MODE[0] == "apply":
        print("item PUT", call("PUT", f"/items/{ITEM}", item))
        print("archive item PUT", call("PUT", f"/items/{ARCHIVE_ITEM}", archive))
        print("rule", ("PUT " + str(call("PUT", f"/rules/{RULE_UID}", rule))) if exists else
              ("POST " + str(call("POST", "/rules", rule))))
        print("run now:", call("POST", f"/rules/{RULE_UID}/runnow", {}))


main()
