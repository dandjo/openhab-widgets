#!/usr/bin/env python3
"""Import the MyŠkoda app's trip export (Reiseverlauf, "tripStatistics_<VIN>.csv", user 2026-10-26) into InfluxDB's
measurement skoda_trips, where the rule skoda_enyaq_status keeps the trips it finds from its reads: one point per
session at its start, tag source=app, the export's fields (numbers as floats, as the rule writes them, since InfluxDB
fixes a field's type), and its two places as the trip map's points. The app's sessions replace every trip of the
export's span (+2 hours), the found ones ("ca.") as well. The export knows of a session only its start and end
(and how many public charging stops it made); where our own reads saw it, the places the car stood at in between
come from InfluxDB (parking state and position, the address since it is persisted there, and the charge gained at a
stop from the charging state and the charge), numbered between start and end on the trip's map (user, 2026-10-26:
"Zwischenstopp fehlt"). A stop whose address our reads do not have takes the address of a known place within NAMED
metres: every start, stop and end with an address of the trips in InfluxDB before the import, and the export's own, so
an address once found stays with a later import. A session the rule still holds open in
skoda_enyaq_trip_state is dropped when the export covers it. Then it starts the rule, which rebuilds the popups' list.
No item may be named skoda_trips: the nightly downsampler leaves only measurements without an item alone. Nothing of
the trips (addresses, positions) is printed here; delete the export afterwards, its file name holds the VIN.
Usage: skoda_trips.py check|apply EXPORT.csv   (on homepi, as pi; the API token from ~/.openhab_token)"""
import csv
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

INFLUX = "http://127.0.0.1:8086"
MEASUREMENT = "skoda_trips"
REST = "http://127.0.0.1:8080/rest"
RULE, STATE_ITEM = "skoda_enyaq_status", "skoda_enyaq_trip_state"
ZONE = ZoneInfo("Europe/Vienna")
SESSION_GAP = timedelta(hours=2)
MOVED = 200  # m: a place this far from the one before is a new one, as the rule counts
NAMED = 50   # m: a stop without an address takes the address of a known place this near


def ms(text):
    """An export's local time (26.10.2026 11:35) in ms since the epoch."""
    return int(datetime.strptime(text, "%d.%m.%Y %H:%M").replace(tzinfo=ZONE).timestamp() * 1000)


def number(text):
    text = (text or "").strip()
    return float(text) if text else None


def position(text):
    parts = [p.strip() for p in (text or "").split(",")]
    return [float(parts[0]), float(parts[1])] if len(parts) == 2 and all(parts) else None


def trip(row):
    start, end = ms(row["Start of trip"]), ms(row["End of trip"])
    a, b = position(row["Start coordinates"]), position(row["End coordinates"])
    points = [[*a, start, row["Start address"], 0]] if a else []
    points += [[*b, end, row["End address"], 0]] if b else []
    fields = {"end": end, "approx": False, "from": row["Start address"], "to": row["End address"],
              "km": number(row["Distance in km"]), "odoStart": number(row["Start odometer in km"]),
              "odoEnd": number(row["End odometer in km"]), "drive": number(row["Driving time in minutes"]),
              "travel": number(row["Travel time in minutes"]), "speed": number(row["Average speed in km/h"]),
              "kwh": number(row["Electricity consumption in kWh"]),
              "kwh100": number(row["Average electricity consumption in kWh/100km"]),
              "socStart": number(row["Start SoC in %"]), "socEnd": number(row["End SoC in %"]),
              "stops": number(row["Public charging stops"]) or 0.0,
              "gained": number(row["Public charge SoC gained in %"]) or 0.0,
              "short": row["Short trip"].strip().lower() == "true", "classification": row["Classification"] or None,
              "points": json.dumps(points, ensure_ascii=False)}
    return start, fields


def series(item, first, last):
    q = f'SELECT value FROM "{item}" WHERE time >= {first}ms AND time <= {last}ms'
    res = influx("/query?" + urllib.parse.urlencode({"db": "openhab", "epoch": "ms", "q": q}))["results"][0]
    return [(t, v) for t, v in res["series"][0]["values"]] if "series" in res else []


def meters(a, b):
    rad = math.pi / 180
    x = (b[1] - a[1]) * rad * math.cos((a[0] + b[0]) / 2 * rad)
    return math.hypot(x, (b[0] - a[0]) * rad) * 6371000


def known_places():
    """Every place with an address of the trips in InfluxDB: (latitude, longitude, address)."""
    q = f"SELECT points FROM {MEASUREMENT}"
    res = influx("/query?" + urllib.parse.urlencode({"db": "openhab", "q": q}))["results"][0]
    rows = res["series"][0]["values"] if "series" in res else []
    return [(p[0], p[1], p[3]) for _, text in rows for p in json.loads(text or "[]") if p[3]]


def named(pos, known):
    near = [(meters(pos, k[:2]), k[2]) for k in known]
    near = [n for n in near if n[0] <= NAMED]
    return min(near)[1] if near else None


def stops(start, end, first, last, known):
    """The places our reads saw the car stand at between a session's start and end, after first and before last: each
    PARKED of the parking state at the position it then held, the address there and the charge gained while it stood
    (a CHARGING stretch from the charge at its start to the charge at its end); one within MOVED of the place before it
    (or of the start) is the same place, the last one within MOVED of the end is the end itself."""
    states = series("skoda_enyaq_parking_state", start, end)
    positions = series("skoda_enyaq_parking_position", start - 60000, end)
    addresses = series("skoda_enyaq_parking_address", start - 60000, end)
    charging = series("skoda_enyaq_charging_state", start, end)
    socs = series("skoda_enyaq_soc", start - 60000, end)
    at = lambda rows, t: next((v for tt, v in reversed(rows) if tt <= t + 60000), None)
    out, before = [], first[:2]
    moves = [t for t, v in states if v == "IN_MOTION"]
    for t, v in states:
        if v != "PARKED" or not start < t < end:
            continue
        text = at(positions, t)
        if not text:
            continue
        pos = [float(x) for x in str(text).split(",")[:2]]
        if meters(pos, before) <= MOVED:
            continue
        leave = next((m for m in moves if m > t), end)
        gained = 0
        on = None
        for ct, cv in charging:
            if ct < t or ct > leave:
                continue
            if cv == "CHARGING" and on is None:
                on = at(socs, ct)
            elif cv != "CHARGING" and on is not None:
                now = at(socs, ct)
                gained += max(0, (now or on) - on)
                on = None
        if on is not None:
            gained += max(0, (at(socs, leave) or on) - on)
        out.append([pos[0], pos[1], t, at(addresses, t) or named(pos, known), round(gained)])
        before = pos
    if out and meters(out[-1][:2], last[:2]) <= MOVED and out[-1][4] == 0:
        out.pop()
    return out


def line(start, fields):
    def value(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return repr(float(v))
        return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'
    body = ",".join(f"{k}={value(v)}" for k, v in fields.items() if v is not None)
    return f"{MEASUREMENT},source=app {body} {start}"


def influx(path, data=None):
    req = urllib.request.Request(INFLUX + path, data=data, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=120) as r:
        text = r.read().decode()
    return json.loads(text) if text.startswith("{") else text


def count(first, last):
    q = f"SELECT count(km) FROM {MEASUREMENT} WHERE time >= {first}ms AND time <= {last}ms"
    res = influx("/query?" + urllib.parse.urlencode({"db": "openhab", "q": q}))["results"][0]
    return int(res["series"][0]["values"][0][1]) if "series" in res else 0


def rest(method, path, body=None, content="application/json"):
    token = open(os.path.expanduser("~/.openhab_token")).read().strip()
    req = urllib.request.Request(REST + path, method=method, data=None if body is None else body.encode(),
                                 headers={"Authorization": "Bearer " + token, "Content-Type": content})
    with urllib.request.urlopen(req) as r:
        return r.read().decode()


def main():
    mode, source = sys.argv[1], sys.argv[2]
    trips = sorted((trip(r) for r in csv.DictReader(open(source, encoding="utf-8-sig"))), key=lambda t: t[0])
    if not trips:
        sys.exit("no trips in the export")
    added = 0
    known = known_places() + [(p[0], p[1], p[3]) for _, f in trips for p in json.loads(f["points"]) if p[3]]
    for start, fields in trips:
        points = json.loads(fields["points"])
        if len(points) == 2:
            between = stops(start, fields["end"], points[0], points[1], known)
            if between:
                fields["points"] = json.dumps([points[0], *between, points[1]], ensure_ascii=False)
                added += len(between)
    first = trips[0][0]
    last = max(f["end"] for _, f in trips) + int(SESSION_GAP.total_seconds() * 1000)
    state_text = rest("GET", f"/items/{STATE_ITEM}/state")
    try:
        state = json.loads(state_text)
    except json.JSONDecodeError:
        state = {}
    session = (state or {}).get("session")
    covered = bool(session) and session.get("start") is not None and session["start"] <= last
    replaced = count(first, last)
    print(f"export: {len(trips)} trips, {datetime.fromtimestamp(first / 1000, ZONE):%d.%m.%Y} to "
          f"{datetime.fromtimestamp((last - SESSION_GAP.total_seconds() * 1000) / 1000, ZONE):%d.%m.%Y}, "
          f"{sum(f['km'] or 0 for _, f in trips):.0f} km, {added} stops in between from our own reads; "
          f"{replaced} trips in InfluxDB in its span replaced; "
          f"open session: {'dropped (in the export)' if covered else 'kept' if session else 'none'}")
    if mode != "apply":
        return
    q = f"DELETE FROM {MEASUREMENT} WHERE time >= {first}ms AND time <= {last}ms"
    influx("/query?" + urllib.parse.urlencode({"db": "openhab"}), urllib.parse.urlencode({"q": q}).encode())
    influx("/write?" + urllib.parse.urlencode({"db": "openhab", "precision": "ms"}),
           "\n".join(line(s, f) for s, f in trips).encode())
    if covered:
        del state["session"]
        rest("PUT", f"/items/{STATE_ITEM}/state", json.dumps(state), "text/plain")
    rest("POST", f"/rules/{RULE}/runnow", "{}")
    print(f"written: {count(first, last)} trips in the span; rule run")


main()
