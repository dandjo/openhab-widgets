#!/usr/bin/env python3
"""The house's PV forecast for the days before rule pv_forecast wrote it (user, 2026-10-19: "Kannst du die Prognose
auch rückwirkend berechnen, damit ich sie vergleichen kann?"): Open-Meteo's archived forecasts (historical forecast
API, the same the rule fits on) of the irradiance on the three 25° planes, weighted by the rule's present factors
(from pv_forecast_hourly), written into pv_forecast_power as the rule writes it: each hour's mean at the hour's middle,
from the first day of PV readings (30 September 2024) to the day before the rule began (today's points are the
rule's). Equal timestamps overwrite, so a second run replaces the first.
check prints what it would write and each month's forecast against the measured yield (energy_daily_pv); apply writes.
Usage: pv_forecast_history.py check|apply [FIRST_DAY [LAST_DAY]]   (on homepi, as pi)"""
import datetime
import json
import sys
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Vienna")
INFLUX = "http://127.0.0.1:8086"
LOCATION = "latitude=LAT&longitude=LON&timezone=Europe%2FVienna&timeformat=unixtime"
TILT = 25
PLANES = {"east": -90, "west": 90, "north": 180}
ITEM = "pv_forecast_power"


def get(url, tries=4):
    """An answer of Open-Meteo, asked again after 5, 10 and 15 seconds when it has none (503 while overloaded)."""
    for n in range(tries):
        if n:
            time.sleep(5 * n)
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                answer = json.load(r)
            if not answer.get("error") and "hourly" in answer:
                return answer
        except Exception:
            pass
    raise SystemExit(f"no answer from {url}")


def irradiance(first, last, azimuth):
    """One plane's irradiance by the hour's start (Open-Meteo gives an hour's mean at its end), a quarter at a time."""
    out, start = {}, first
    while start <= last:
        end = min(last, start + datetime.timedelta(days=91))
        h = get(f"https://historical-forecast-api.open-meteo.com/v1/forecast?{LOCATION}&start_date={start}"
                f"&end_date={end}&hourly=global_tilted_irradiance&tilt={TILT}&azimuth={azimuth}")["hourly"]
        out.update({t - 3600: g for t, g in zip(h["time"], h["global_tilted_irradiance"]) if isinstance(g, (int, float))})
        start = end + datetime.timedelta(days=1)
    return out


def influx(query):
    url = f"{INFLUX}/query?db=openhab&epoch=s&q=" + urllib.parse.quote(query)
    with urllib.request.urlopen(url) as r:
        series = json.load(r)["results"][0].get("series", [])
    return series[0]["values"] if series else []


def main():
    apply = sys.argv[1] == "apply"
    today = datetime.datetime.now(TZ).date()
    first = datetime.date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else datetime.date(2024, 9, 30)
    last = datetime.date.fromisoformat(sys.argv[3]) if len(sys.argv) > 3 else today - datetime.timedelta(days=1)
    with urllib.request.urlopen("http://127.0.0.1:8080/rest/items/pv_forecast_hourly/state") as r:
        k = json.loads(r.read().decode())["k"]
    print(f"factors east {k['east']}, west {k['west']}, north {k['north']} W per W/m²; days {first} to {last}")
    g = {plane: irradiance(first, last, azimuth) for plane, azimuth in PLANES.items()}
    hours = sorted(t for t in g["east"] if t in g["west"] and t in g["north"])
    end = int(datetime.datetime.combine(last + datetime.timedelta(days=1), datetime.time(), TZ).timestamp())
    points = [(t, round(k["east"] * g["east"][t] + k["west"] * g["west"][t] + k["north"] * g["north"][t]))
              for t in hours if t < end]
    print(f"{len(points)} hours, the first {datetime.datetime.fromtimestamp(points[0][0], TZ)}, "
          f"the last {datetime.datetime.fromtimestamp(points[-1][0], TZ)}")
    # each day's forecast against the measured yield, the day's last value of energy_daily_pv (written at 23:59:59)
    days = {}
    for t, w in points:
        d = datetime.datetime.fromtimestamp(t, TZ).date()
        days[d] = days.get(d, 0) + w / 1000
    measured = {datetime.datetime.fromtimestamp(t, TZ).date(): v
                for t, v in influx(f"SELECT last(value) FROM energy_daily_pv WHERE time >= '{first}T00:00:00Z' "
                                   "GROUP BY time(1d, 22h)") if v is not None}
    months = {}
    for d, f in days.items():
        if d in measured:
            months.setdefault(d.strftime("%Y-%m"), []).append((f, measured[d]))
    print("month    days  measured  forecast  mean |error|  bias  (kWh a day)")
    for m, rows in sorted(months.items()):
        n = len(rows)
        print(f"{m}  {n:4}  {sum(r[1] for r in rows) / n:8.1f}  {sum(r[0] for r in rows) / n:8.1f}  "
              f"{sum(abs(r[0] - r[1]) for r in rows) / n:11.1f}  {sum(r[0] - r[1] for r in rows) / n:+5.1f}")
    if not apply:
        return
    lines = [f"{ITEM},item={ITEM} value={w} {t + 1800}" for t, w in points]
    for i in range(0, len(lines), 5000):
        req = urllib.request.Request(f"{INFLUX}/write?db=openhab&precision=s", method="POST",
                                     data="\n".join(lines[i:i + 5000]).encode())
        with urllib.request.urlopen(req) as r:
            assert r.status == 204, r.status
    print(f"written {len(lines)} points")


main()
