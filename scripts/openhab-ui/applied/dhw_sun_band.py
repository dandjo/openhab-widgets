#!/usr/bin/env python3
"""The sun's budget for 60 °C on the PV forecast's low bound (user, 2026-11-08). pv_forecast_ml gives each hour of
pv_forecast_hourly a band, [start, W, low W, high W], calibrated at each training so that the rest of a day from 12:00
falls below the low bound on about one day in ten; heatpump_dhw_management's sunSpare() now sums the low bound where an
hour has one, instead of the forecast (the hours the PV runs, >= 100 W, still by the forecast). On a clear day the low
bound lies close to the forecast (14 August 2026: 27.8 against 27.9 kWh from 12:00), on an uncertain one well below
(12 March 2026: 3.2 against 8.5), so 60 °C begins only where the sun pays for it on about nine days in ten
(walk-forward over 2026: 8.6 % of the days fell below the band's rest from 12:00). Hours without a band (an older
forecast, or the plain one) count with the forecast as before. Tested in mini-racer (the band used, the forecast
without one, mixed hours, the PV's hours by the forecast, a stale forecast).
apply also sets the rule's German description from i18n/de_labels.py.
Usage: dhw_sun_band.py check|apply   (on homepi; the REST token from ~/.openhab_token, never printed)"""
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "http://127.0.0.1:8080/rest"
UID = "heatpump_dhw_management"

COMMENT_OLD = """// kWh today's rest of the PV would still send to the grid, or null without a fresh forecast (3 hours) or once the PV
// has ended; the house by its last hour's mean without the heat pump, plus the heating
"""
COMMENT_NEW = """// kWh today's rest of the PV would still send to the grid, or null without a fresh forecast (3 hours) or once the PV
// has ended: the PV by the forecast band's low bound where an hour has one (pv_forecast_ml since 2026-11-08; the rest
// of a day falls below it on about one day in ten), else by the forecast; the hours the PV runs by the forecast; the
// house by its last hour's mean without the heat pump, plus the heating
"""
LOOP_OLD = """  for (const [start, watts] of forecast.h) {
    const share = Math.max(0, Math.min(start + 3600, midnight) - Math.max(start, now)) / 3600;
    pv += watts / 1000 * share;
"""
LOOP_NEW = """  for (const [start, watts, low] of forecast.h) {
    const share = Math.max(0, Math.min(start + 3600, midnight) - Math.max(start, now)) / 3600;
    pv += (typeof low === 'number' ? low : watts) / 1000 * share;
"""
PAIRS = [(COMMENT_OLD, COMMENT_NEW), (LOOP_OLD, LOOP_NEW)]


def patch(script):
    if all(new in script for _, new in PAIRS):
        return script, "already patched"
    for old, new in PAIRS:
        assert script.count(old) == 1, f"block found {script.count(old)} times: {old[:60]!r}"
        script = script.replace(old, new)
    return script, "patched"


def call(method, path, token, body=None, content="application/json"):
    data = None if body is None else (body if isinstance(body, str) else json.dumps(body)).encode()
    req = urllib.request.Request(BASE + path, method=method, data=data,
                                 headers={"Authorization": "Bearer " + token, "Content-Type": content})
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw.startswith((b"{", b"[")) else raw.decode()
    except urllib.error.HTTPError as e:
        return e.code, None


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(HERE, "..", "i18n"))
    from de_labels import RULE_DESCRIPTIONS  # noqa: E402
    APPLY = sys.argv[1:2] == ["apply"]
    TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
    st, rule = call("GET", f"/rules/{UID}", TOKEN)
    assert st == 200, (UID, st)
    for a in rule["actions"]:
        if a["configuration"].get("script"):
            a["configuration"]["script"], how = patch(a["configuration"]["script"])
            print(f"{UID}: {how} ({len(a['configuration']['script'])} chars)")
    put = {k: rule[k] for k in ("uid", "name", "description", "tags", "triggers", "conditions", "actions", "configuration",
                                "configDescriptions", "visibility", "templateUID") if k in rule}
    put["description"] = RULE_DESCRIPTIONS[UID]
    print(f"{UID}: description {'unchanged' if rule.get('description') == put['description'] else 'new'}")
    print(f"{UID}: PUT", call("PUT", f"/rules/{UID}", TOKEN, put)[0] if APPLY else "(check)")
