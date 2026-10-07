#!/usr/bin/env python3
"""The history the device pages' value tiles show and no item holds (user, 2026-10-06): the rule tile_history writes
it every 10 minutes and right after openHAB starts as JSON into the String item tile_history, which is not
persisted. Per item it keeps what the
tiles need (dashboard.py, tile_history_track()): y its value yesterday at this time and a the mean of the last 7 days
at this time (comparison with yesterday) and both again dt seconds later (y2, a2, with the run's time t: the tiles
interpolate to the minute shown, as the rule runs every 10 minutes), d its value at yesterday's end (yesterday's whole day, the base a
comparison needs), h its value some hours ago (trend), s 24 hourly means up to now (day's
course), f [unix, value] of the hours behind and ahead (the price strip). Finished hours stay in the rule's private
cache, so a run queries only the current hour anew.

Usage: tile_history.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token, never printed)
Run apply again whenever the generator's tiles read the history of other items."""
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
ITEM = RULE_UID = ns["TILE_HISTORY"]
SCRIPT = """// the history the device pages' value tiles show, as JSON in tile_history: per item y = its value yesterday at this
// time, a = the mean of the last 7 days at this time, y2/a2 = both dt seconds later (t = this run, the tiles
// interpolate to the minute shown), d = its value at yesterday's end, h = its value some hours ago, s = 24 hourly means up to now,
// f = [unix, value] of the hours behind and ahead; the items and what to keep of them come from the UI generator
const TRACK = __TRACK__;
const svc = 'influxdb';
const now = time.toZDT();
const hour0 = now.withMinute(0).withSecond(0).withNano(0);
// finished hours never change: their means stay here, a run queries only the current hour anew
const store = cache.private.get('hourly', () => ({}));
// yesterday's end does not change all day: read once a day
const midnight = now.withHour(0).withMinute(0).withSecond(0).withNano(0);
const ends = cache.private.get('day_ends', () => ({}));
if (ends.day !== midnight.toEpochSecond()) { ends.day = midnight.toEpochSecond(); ends.v = {}; }
// the next run's minute: up to it the tiles interpolate between now and dt later, within the day (before midnight
// dt shrinks, else yesterday's later value would be the reset counter of the next day)
const dt = Math.max(1, Math.min(600, midnight.plusDays(1).toEpochSecond() - now.toEpochSecond() - 1));
const mean = (xs) => xs.length ? Math.round(xs.reduce((a, b) => a + b, 0) / xs.length * 1000) / 1000 : null;
const val = (s) => (s === null || s === undefined || s.numericState === null || s.numericState === undefined) ?
  null : Math.round(s.numericState * 1000) / 1000;
const out = {};
for (const name of Object.keys(TRACK)) {
  const want = TRACK[name];
  let p;
  try { p = items.getItem(name).persistence; } catch (e) { continue; }
  const r = {};
  try {
    if (want.c) {
      r.y = val(p.persistedState(now.minusDays(1), svc));
      r.y2 = val(p.persistedState(now.minusDays(1).plusSeconds(dt), svc));
      const xs = [], xs2 = [];
      for (let k = 1; k <= 7; k++) {
        const v = val(p.persistedState(now.minusDays(k), svc));
        if (v !== null) xs.push(v);
        const v2 = val(p.persistedState(now.minusDays(k).plusSeconds(dt), svc));
        if (v2 !== null) xs2.push(v2);
      }
      r.a = mean(xs);
      r.a2 = mean(xs2);
      r.t = now.toEpochSecond();
      r.dt = dt;
      if (ends.v[name] === undefined || ends.v[name] === null) ends.v[name] = val(p.persistedState(midnight.minusSeconds(1), svc));
      r.d = ends.v[name];
    }
    if (want.t) r.h = val(p.persistedState(now.minusHours(want.t), svc));
    if (want.s) {
      const own = store[name] || {};
      const s = [];
      for (let i = 23; i >= 0; i--) {
        const begin = hour0.minusHours(i);
        const key = String(begin.toEpochSecond());
        let v = own[key];
        if (v === undefined || i === 0) {
          v = val(p.averageBetween(begin, i === 0 ? now : begin.plusHours(1), svc));
          if (i !== 0) own[key] = v;
        }
        s.push(v);
      }
      const oldest = hour0.minusHours(24).toEpochSecond();
      for (const k of Object.keys(own)) if (Number(k) < oldest) delete own[k];
      store[name] = own;
      r.s = s;
    }
    if (want.f) {
      const rows = p.getAllStatesBetween(hour0.minusHours(want.f[0]), hour0.plusHours(want.f[1]), svc);
      r.f = rows.map((x) => [x.timestamp.toEpochSecond(), Math.round(x.numericState * 10000) / 10000]);
    }
  } catch (e) {
    console.warn('tile_history: ' + name + ': ' + e);
  }
  out[name] = r;
}
items.getItem('tile_history').postUpdate(JSON.stringify(out));
"""


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
    tracked = ns["tile_history_track"]()
    rule = {
        "uid": RULE_UID,
        "name": "Kachel-Verlauf",
        "description": "Schreibt alle 10 Minuten und nach dem Start in tile_history, was die Werte-Kacheln der Geräteseiten an Verlauf "
                       "zeigen: Wert gestern um diese Zeit, Ø der letzten 7 Tage um diese Zeit, Wert am Ende von "
                       "gestern, Wert vor einigen "
                       "Stunden, 24 Stundenmittel und die Preise der kommenden Stunden (applied/tile_history.py, "
                       "Liste aus dem UI-Generator).",
        "tags": [],
        "triggers": [{"id": "1", "type": "timer.GenericCronTrigger",
                      "configuration": {"cronExpression": "0 0/10 * * * ? *"}},
                     # right after a start too: the item is not persisted and would stay NULL until the next run
                     {"id": "3", "type": "core.SystemStartlevelTrigger", "configuration": {"startlevel": 100}}],
        "conditions": [],
        "actions": [{"id": "2", "type": "script.ScriptAction",
                     "configuration": {"type": "application/javascript",
                                       "script": SCRIPT.replace("__TRACK__", json.dumps(tracked, separators=(",", ":")))}}],
    }
    item = {"type": "String", "name": ITEM, "label": "Kachel-Verlauf", "category": "", "tags": [], "groupNames": []}
    print(f"item {ITEM}:", "exists" if call("GET", f"/items/{ITEM}") == 200 else "missing")
    exists = call("GET", f"/rules/{RULE_UID}") == 200
    print(f"rule {RULE_UID}:", "exists" if exists else "missing", f"({len(tracked)} items tracked)")
    if MODE[0] == "apply":
        print("item PUT", call("PUT", f"/items/{ITEM}", item))
        print("rule", ("PUT " + str(call("PUT", f"/rules/{RULE_UID}", rule))) if exists else
              ("POST " + str(call("POST", "/rules", rule))))
        print("run now:", call("POST", f"/rules/{RULE_UID}/runnow", {}))


main()
