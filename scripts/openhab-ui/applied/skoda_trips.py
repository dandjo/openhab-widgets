#!/usr/bin/env python3
"""Import the MyŠkoda app's trip export (Reiseverlauf, "tripStatistics_<VIN>.csv", user 2026-10-26) into the trip
history the rule skoda_enyaq_status keeps in /var/lib/openhab/skoda/trips.json. The app's sessions replace every trip
of the export's span, the ones the rule found from its reads ("ca.") as well; a session the rule still holds open is
dropped when the export covers it. The rule rebuilds the popup's list from the files on its next run, which this
starts. The files hold addresses and positions: they stay on homepi, owned by openhab, readable by its group only,
and nothing of them is printed here.
Usage: skoda_trips.py check|apply EXPORT.csv   (on homepi, as pi with sudo; the API token from ~/.openhab_token)"""
import csv
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DIR = "/var/lib/openhab/skoda"
TRIPS, STATE = f"{DIR}/trips.json", f"{DIR}/trip-state.json"
ZONE = ZoneInfo("Europe/Vienna")
SESSION_GAP = timedelta(hours=2)
RULE = "skoda_enyaq_status"


def utc(text):
    """An export's local time (26.10.2026 11:35) as UTC in ISO, as the rule writes its times."""
    t = datetime.strptime(text, "%d.%m.%Y %H:%M").replace(tzinfo=ZONE)
    return t.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def number(text, kind=float):
    text = (text or "").strip()
    return kind(float(text)) if text else None


def position(text):
    parts = [p.strip() for p in (text or "").split(",")]
    return [float(parts[0]), float(parts[1])] if len(parts) == 2 and all(parts) else None


def trip(row):
    return {"start": utc(row["Start of trip"]), "end": utc(row["End of trip"]), "approx": False, "source": "app",
            "from": row["Start address"], "to": row["End address"], "fromPos": position(row["Start coordinates"]),
            "toPos": position(row["End coordinates"]), "km": number(row["Distance in km"], int),
            "odoStart": number(row["Start odometer in km"], int), "odoEnd": number(row["End odometer in km"], int),
            "drive": number(row["Driving time in minutes"], int), "travel": number(row["Travel time in minutes"], int),
            "speed": number(row["Average speed in km/h"], int), "kwh": number(row["Electricity consumption in kWh"]),
            "kwh100": number(row["Average electricity consumption in kWh/100km"]),
            "socStart": number(row["Start SoC in %"], int), "socEnd": number(row["End SoC in %"], int),
            "stops": number(row["Public charging stops"], int) or 0,
            "gained": number(row["Public charge SoC gained in %"], int) or 0,
            "short": row["Short trip"].strip().lower() == "true", "classification": row["Classification"] or None}


def read(path, fallback):
    done = subprocess.run(["sudo", "cat", path], capture_output=True, text=True)
    return json.loads(done.stdout) if done.returncode == 0 and done.stdout.strip() else fallback


def write(path, value):
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False)
    try:
        subprocess.run(["sudo", "install", "-o", "openhab", "-g", "openhab", "-m", "640", f.name, path], check=True)
    finally:
        os.unlink(f.name)


def when(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def main():
    mode, source = sys.argv[1], sys.argv[2]
    rows = list(csv.DictReader(open(source, encoding="utf-8-sig")))
    imported = sorted((trip(r) for r in rows), key=lambda t: t["start"])
    if not imported:
        sys.exit("no trips in the export")
    first, last = when(imported[0]["start"]), when(max(t["end"] for t in imported))
    history = read(TRIPS, {"trips": []})
    kept = [t for t in history.get("trips", []) if not (first <= when(t["start"]) <= last + SESSION_GAP)]
    replaced = len(history.get("trips", [])) - len(kept)
    merged = sorted(kept + imported, key=lambda t: t["start"])
    state = read(STATE, {})
    session = state.get("session")
    covered = session is not None and session.get("start") is not None and \
        datetime.fromtimestamp(session["start"] / 1000, ZoneInfo("UTC")) <= last + SESSION_GAP
    print(f"export: {len(imported)} trips, {first:%d.%m.%Y} to {last:%d.%m.%Y}, "
          f"{sum(t['km'] or 0 for t in imported)} km; history now {len(history.get('trips', []))} trips, "
          f"{replaced} of them in the export's span replaced, {len(merged)} after the import; open session: "
          f"{'dropped (in the export)' if covered else 'kept' if session else 'none'}")
    if mode != "apply":
        return
    subprocess.run(["sudo", "install", "-d", "-o", "openhab", "-g", "openhab", "-m", "750", DIR], check=True)
    write(TRIPS, {"trips": merged})
    if covered:
        del state["session"]
        write(STATE, state)
    token = open(os.path.expanduser("~/.openhab_token")).read().strip()
    req = urllib.request.Request(f"http://127.0.0.1:8080/rest/rules/{RULE}/runnow", method="POST", data=b"{}",
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        print("written; rule run:", r.status)


main()
