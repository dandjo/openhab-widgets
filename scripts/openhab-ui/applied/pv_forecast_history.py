#!/usr/bin/env python3
"""The house's PV forecast for the days before rule pv_forecast wrote it (user, 2026-10-19: "Kannst du die Prognose
auch rückwirkend berechnen, damit ich sie vergleichen kann?"): Open-Meteo's archived forecasts (historical forecast
API, the same the rule fits on) of the irradiance on the three 25° planes and of the air's temperature, weighted by
factors fitted as the rule fits them, each day's on the 14 days before it (model 3 since 2026-10-19: a factor per
string and hour of the day where the hour's irradiance is enough to tell, else the string's for the whole day, its
energy against its modules' irradiance at the cells' temperature, -0.34 % per K above 25 °C, NOCT 43 °C;
the first days, with fewer than 7 days before them, take the first full fit's), written as the rule writes them: into pv_forecast_power each hour's mean at the hour's
middle, into pv_forecast_energy each day's total at its 23:59:59, from the first day of PV readings (30 September
2024) to yesterday (from today on the rule writes them). Equal timestamps overwrite, so a second run replaces the
first. check prints what it would write and each month's forecast against the strings' generation
(energy_daily_pv_generation, see pv_generation.py; the inverter's yield counts the battery); apply writes.
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
TEMPERATURE_COEFFICIENT, CELL_RISE = -0.0034, (43 - 20) / 800  # as in pv_forecast.js
MODULES = {"east": 8, "west": 8, "north": 6}
FIT_DAYS = 14
ITEM = "pv_forecast_power"
DAILY = "pv_forecast_energy"


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


def hourly(first, last, query, field):
    """An hourly value by the hour's start (Open-Meteo gives it at the hour's end), a quarter at a time."""
    out, start = {}, first
    while start <= last:
        end = min(last, start + datetime.timedelta(days=91))
        h = get(f"https://historical-forecast-api.open-meteo.com/v1/forecast?{LOCATION}&start_date={start}"
                f"&end_date={end}&hourly={query}")["hourly"]
        out.update({t - 3600: v for t, v in zip(h["time"], h[field]) if isinstance(v, (int, float))})
        start = end + datetime.timedelta(days=1)
    return out


def irradiance(first, last, azimuth):
    return hourly(first, last, f"global_tilted_irradiance&tilt={TILT}&azimuth={azimuth}", "global_tilted_irradiance")


def derate(g, temp):
    """A module's power at an irradiance and the air's temperature against its power at 25 °C cell temperature."""
    return 1 if temp is None else 1 + TEMPERATURE_COEFFICIENT * (temp + CELL_RISE * g - 25)


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
    temps = hourly(first, last, "temperature_2m", "temperature_2m")
    hours = sorted(t for t in g["east"] if t in g["west"] and t in g["north"])
    end = int(datetime.datetime.combine(last + datetime.timedelta(days=1), datetime.time(), TZ).timestamp())
    # the strings' energy per hour (kWh, the mean kW), for the factors of each day
    a = int(datetime.datetime.combine(first, datetime.time(), TZ).timestamp())
    measured = {n: {t: v for t, v in influx(f"SELECT integral(value, 1h) / 1000 FROM huawei_inverter_pv{n}_power "
                                            f"WHERE time >= {a}s AND time < {end}s GROUP BY time(1h)") if v is not None}
                for n in (1, 2)}
    unit = lambda p, t: MODULES[p] * g[p][t] * derate(g[p][t], temps.get(t))
    by_day = {}
    for t in hours:
        by_day.setdefault(datetime.datetime.fromtimestamp(t, TZ).date(), []).append(t)
    days_sorted = sorted(by_day)
    factors = {}
    hour_of = lambda t: datetime.datetime.fromtimestamp(t, TZ).hour
    for i, d in enumerate(days_sorted):
        sums = [0.0, 0.0, 0.0, 0.0]
        by_hour = {}
        for x in days_sorted[max(0, i - FIT_DAYS):i]:
            for t in by_day[x]:
                x1, x2 = unit("east", t), unit("west", t) + unit("north", t)
                if x1 + x2 > 0 and t in measured[1] and t in measured[2]:
                    m1, m2 = measured[1][t] * 1000, measured[2][t] * 1000
                    sums[0] += m1; sums[1] += x1; sums[2] += m2; sums[3] += x2
                    q = by_hour.setdefault(hour_of(t), [0.0, 0.0, 0.0, 0.0])
                    q[0] += m1; q[1] += x1; q[2] += m2; q[3] += x2
        if i >= 7 and sums[1] > 0 and sums[3] > 0:
            s1, s2 = sums[0] / sums[1], sums[2] / sums[3]
            # as the rule: an hour's own factor where its irradiance makes a twentieth of a mean hour's (of 12)
            own = lambda h, j, day, total: (by_hour[h][j] / by_hour[h][j + 1]
                                            if h in by_hour and by_hour[h][j + 1] > 0.05 * total / 12 else day)
            factors[d] = (s1, s2, [own(h, 0, s1, sums[1]) for h in range(24)], [own(h, 2, s2, sums[3]) for h in range(24)])
    first_fit = factors[min(factors)]
    print(f"factors per module, the last day's: string 1 {factors[max(factors)][0]:.3f}, string 2 "
          f"{factors[max(factors)][1]:.3f} W per W/m² (the rule now: east {k['east']}, west {k['west']}, north {k['north']})")
    points = []
    for t in hours:
        if t >= end:
            continue
        _, _, h1, h2 = factors.get(datetime.datetime.fromtimestamp(t, TZ).date(), first_fit)
        points.append((t, round(h1[hour_of(t)] * unit("east", t) + h2[hour_of(t)] * (unit("west", t) + unit("north", t)))))
    print(f"{len(points)} hours, the first {datetime.datetime.fromtimestamp(points[0][0], TZ)}, "
          f"the last {datetime.datetime.fromtimestamp(points[-1][0], TZ)}")
    # each day's forecast against the strings' generation, energy_daily_pv_generation's point at the day's 23:59:59
    days = {}
    for t, w in points:
        d = datetime.datetime.fromtimestamp(t, TZ).date()
        if first <= d <= last:
            days[d] = days.get(d, 0) + w / 1000
    measured = {datetime.datetime.fromtimestamp(t, TZ).date(): v
                for t, v in influx(f"SELECT value FROM energy_daily_pv_generation WHERE time >= '{first}T00:00:00Z'")
                if v is not None}
    months = {}
    for d, f in days.items():
        if d in measured:
            months.setdefault(d.strftime("%Y-%m"), []).append((f, measured[d]))
    print("month    days  measured  forecast  mean |error|  bias  (kWh a day)")
    every = [r for rows in months.values() for r in rows]
    print(f"all     {len(every):5}  {sum(r[1] for r in every) / len(every):8.1f}  {sum(r[0] for r in every) / len(every):8.1f}  "
          f"{sum(abs(r[0] - r[1]) for r in every) / len(every):11.2f}  {sum(r[0] - r[1] for r in every) / len(every):+5.2f}")
    for m, rows in sorted(months.items()):
        n = len(rows)
        print(f"{m}  {n:4}  {sum(r[1] for r in rows) / n:8.1f}  {sum(r[0] for r in rows) / n:8.1f}  "
              f"{sum(abs(r[0] - r[1]) for r in rows) / n:11.1f}  {sum(r[0] - r[1] for r in rows) / n:+5.1f}")
    if not apply:
        return
    lines = [f"{ITEM},item={ITEM} value={w} {t + 1800}" for t, w in points]
    lines += [f"{DAILY},item={DAILY} value={round(kwh, 2)} "
              f"{int(datetime.datetime.combine(d, datetime.time(23, 59, 59), TZ).timestamp())}" for d, kwh in days.items()]
    for i in range(0, len(lines), 5000):
        req = urllib.request.Request(f"{INFLUX}/write?db=openhab&precision=s", method="POST",
                                     data="\n".join(lines[i:i + 5000]).encode())
        with urllib.request.urlopen(req) as r:
            assert r.status == 204, r.status
    print(f"written {len(lines)} points")


main()
