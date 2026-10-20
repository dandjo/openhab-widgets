#!/usr/bin/env python3
"""A PV forecast for openHAB, learnt from the installation's own measurements.

A gradient boosting model per string of the inverter (scikit-learn's HistGradientBoostingRegressor) learns the string's
energy per hour from Open-Meteo's forecasts alone: the irradiance on each plane of modules from ten weather models,
the weather of Open-Meteo's best match (radiation parts, temperature, humidity, three cloud layers, wind,
precipitation, snow, visibility), the sun's elevation and azimuth and the day of the year. The house's forecast is
the sum of the strings'. The training data are Open-Meteo's archived forecasts (its historical forecast API) and the
strings' measured power from openHAB's persistence; nothing else is assumed about the modules.

Each training is checked before it replaces the models in use: a candidate trained on all but the last 60 days must
forecast those days about as well as a plain physical forecast (the irradiance times the modules at the cells'
temperature, scaled by one factor fitted on the same days). The check catches a broken training, which lands far
above that; a failed one keeps the models in use and sends a push notification through an openHAB script.

The settings come from the environment, PV_FORECAST_ML_<setting>, the README lists them: PLANES and STRINGS must be
set, the location falls back to openHAB's regional settings, the rest has defaults.

Commands:
  update     add the days missing up to yesterday to the weather cache and to the cache of the strings' energy per
             hour, and drop from both the days before the first PV reading openHAB's persistence still holds
  train      update, then train and check a candidate; if it passes, the models trained on all days replace the ones
             in use, else those stay (exit 1, a warning in the log, a push notification through NOTIFY_RULE)
  forecast   today's and tomorrow's hours from the forecast API into openHAB: pv_forecast_hourly (JSON {at, trained,
             source, h: [[hour's start, W], ...]}), pv_forecast_power and each string's forecast item, each hour's
             mean at its middle as forecast series through openHAB's persistence (only changed points),
             pv_forecast_energy with each day's total at its 23:59:59, and their states (the running hour's, today's
             total) as well as pv_forecast_energy_tomorrow; without a model the plain physical forecast with the last
             training's factor
  backfill FROM [--apply]
             the forecast as the models would have made it from FROM to yesterday, month by month as train decides,
             with --apply written into the forecast series, the points replaced saved before in the state directory
  restore FILE
             write the points of such a backup back
  status     the last training's figures and the caches' extent
Nothing here talks to the database itself: every reading and every write goes through openHAB's REST API for its
persistence (GET and PUT /rest/persistence/items/<item>, the service PERSISTENCE), so that the database's connection
is configured in openHAB alone.
"""
import collections
import csv
import datetime
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo


# ---------------------------------------------------------------- the settings, from the environment

def setting(name, default=None):
    """PV_FORECAST_ML_<name>; a setting without a default must be set"""
    value = os.environ.get(f"PV_FORECAST_ML_{name}", default)
    if value is None:
        sys.exit(f"PV_FORECAST_ML_{name} is not set (see the README)")
    return value


def system_timezone():
    """the system's time zone by its name, from /etc/localtime's link into the zoneinfo database, else UTC"""
    path = os.path.realpath("/etc/localtime")
    return path.split("zoneinfo/", 1)[1] if "zoneinfo/" in path else "UTC"


# a plane of modules: its azimuth in degrees from south (east negative, as Open-Meteo takes it), its tilt in degrees
# and the number of its modules
Plane = collections.namedtuple("Plane", "name azimuth tilt modules")
# a string of the inverter: the item of its measured power, the item its forecast goes to and the planes of its modules
PvString = collections.namedtuple("PvString", "measured_item forecast_item planes")


def parse_planes(text):
    """{name: Plane} from name:azimuth:tilt:modules, comma-separated"""
    planes = {}
    for entry in text.split(","):
        name, azimuth, tilt, modules = entry.split(":")
        planes[name] = Plane(name, float(azimuth), float(tilt), int(modules))
    return planes


def parse_strings(text):
    """[PvString] from measured item:forecast item:planes joined by +, comma-separated"""
    strings = []
    for entry in text.split(","):
        measured_item, forecast_item, planes = entry.split(":")
        strings.append(PvString(measured_item, forecast_item, planes.split("+")))
    return strings


TIMEZONE = ZoneInfo(setting("TIMEZONE", system_timezone()))
STATE_DIR = os.path.expanduser(setting("STATE", "~/.local/state/pv_forecast_ml"))
OPENHAB_REST = setting("OPENHAB_URL", "http://127.0.0.1:8080").rstrip("/") + "/rest"
OPENHAB_TOKEN_FILE = os.path.expanduser(setting("OPENHAB_TOKEN_FILE", "~/.openhab_token"))
PERSISTENCE_SERVICE = setting("PERSISTENCE", "influxdb")
NOTIFY_RULE = setting("NOTIFY_RULE", "notify_broadcast")  # the script a failed training runs; empty: none
FORECAST_API = setting("FORECAST_API", "https://api.open-meteo.com/v1/forecast")
HISTORICAL_API = setting("HISTORICAL_API", "https://historical-forecast-api.open-meteo.com/v1/forecast")
PLANES = parse_planes(setting("PLANES"))
STRINGS = parse_strings(setting("STRINGS"))
# no day before it is used, nor any before the first PV reading
FIRST_DAY = datetime.date.fromisoformat(setting("FIRST", "2000-01-01"))
WEATHER_MODELS = setting("MODELS", "best_match,icon_eu,ecmwf_ifs025,meteofrance_seamless,ukmo_seamless,knmi_seamless,"
                                   "metno_seamless,gfs_seamless,dmi_seamless,geosphere_arome_austria").split(",")
# the modules' datasheet, for the plain forecast: the power's change per K above 25 °C cell temperature in %, and NOCT
TEMPERATURE_COEFFICIENT = float(setting("TEMP_COEFFICIENT", "-0.34"))
NOCT = float(setting("NOCT", "43"))  # °C

# ---------------------------------------------------------------- what the models learn from, what they write

WEATHER_VARIABLES = ["shortwave_radiation", "direct_radiation", "diffuse_radiation", "direct_normal_irradiance",
                     "temperature_2m", "relative_humidity_2m", "cloud_cover", "cloud_cover_low", "cloud_cover_mid",
                     "cloud_cover_high", "wind_speed_10m", "precipitation", "snow_depth", "visibility"]
# each weather model's irradiance on each plane, a column "<model>_<plane>"
IRRADIANCE_COLUMNS = [f"{model}_{plane}" for model in WEATHER_MODELS for plane in PLANES]
# the sun's elevation and azimuth at the hour's middle, the day of the year as a point on a circle
SUN_AND_SEASON = ["sun_el", "sun_az", "doy_s", "doy_c"]
FEATURES = WEATHER_VARIABLES + SUN_AND_SEASON + IRRADIANCE_COLUMNS
DAYLIGHT_ELEVATION = -3  # degrees: an hour counts as daylight while the sun stands above this at its middle
MIN_VALUES_PER_COLUMN = 100  # a feature column with fewer values over the training hours is left out
CHECK_DAYS = 60
# the candidate fails when it came out more than this many times the plain forecast's error: the check is to catch a
# broken training (a bug, a library's change, a broken cache or broken readings), which lands far above it; replayed
# weekly over more than a year, a sound candidate came out 0.44 to 0.6 times the plain forecast's error in summer and
# winter, but up to 1.01 in calm autumn weeks, when one factor fits well
CHECK_TOLERANCE = 1.2
MODEL_PARAMETERS = dict(max_iter=400, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=40, l2_regularization=1.0,
                        random_state=0)

HOURLY_ITEM = "pv_forecast_hourly"
HOUSE_POWER_ITEM = "pv_forecast_power"
ENERGY_ITEM = "pv_forecast_energy"
ENERGY_TOMORROW_ITEM = "pv_forecast_energy_tomorrow"
POWER_ITEMS = [HOUSE_POWER_ITEM, *(string.forecast_item for string in STRINGS)]  # the house's, then the strings'

WEATHER_CACHE_FILE = os.path.join(STATE_DIR, "weather.csv")
MEASURED_CACHE_FILE = os.path.join(STATE_DIR, "measured.csv")
MODEL_FILE = os.path.join(STATE_DIR, "model.joblib")
META_FILE = os.path.join(STATE_DIR, "meta.json")
SENT_FILE = os.path.join(STATE_DIR, "sent.json")


def log(*args):
    print(*args, flush=True)


# ---------------------------------------------------------------- openHAB and its persistence

def read_token():
    return open(OPENHAB_TOKEN_FILE).read().strip()


def openhab_request(method, path, body=None, content_type="application/json"):
    data = None if body is None else (body if isinstance(body, str) else json.dumps(body)).encode()
    request = urllib.request.Request(OPENHAB_REST + path, method=method, data=data,
                                     headers={"Authorization": "Bearer " + read_token(), "Content-Type": content_type})
    with urllib.request.urlopen(request, timeout=30) as response:
        text = response.read().decode()
        return json.loads(text) if text.startswith(("{", "[")) else text


def location():
    """(latitude, longitude) from LATITUDE and LONGITUDE, else openHAB's location, rounded to 2 decimals (about 1 km,
    finer than the weather models' grid)"""
    latitude = os.environ.get("PV_FORECAST_ML_LATITUDE")
    longitude = os.environ.get("PV_FORECAST_ML_LONGITUDE")
    if not (latitude and longitude):
        regional = openhab_request("GET", "/services/org.openhab.i18n/config")
        latitude, longitude = regional["location"].split(",")[:2]
    return round(float(latitude), 2), round(float(longitude), 2)


def iso_time(epoch):
    return datetime.datetime.fromtimestamp(epoch, TIMEZONE).isoformat(timespec="milliseconds")


HISTORY_PAGE_SIZE = 50000


def read_history(item, start, end):
    """the item's readings in openHAB's persistence from start to end (epoch seconds) as [(epoch seconds, value in the
    item's unit)], with the reading before start and the one after end (boundary)"""
    readings, page = [], 0
    while True:
        query = urllib.parse.urlencode({"serviceId": PERSISTENCE_SERVICE, "starttime": iso_time(start),
                                        "endtime": iso_time(end), "boundary": "true", "page": page,
                                        "pagelength": HISTORY_PAGE_SIZE})
        rows = openhab_request("GET", f"/persistence/items/{item}?{query}").get("data", [])
        for row in rows:
            try:
                readings.append((row["time"] / 1000, float(str(row["state"]).split()[0])))
            except ValueError:
                pass
        if len(rows) < HISTORY_PAGE_SIZE:
            return readings
        page += 1


def store_point(item, epoch, state):
    """a state (with its unit) at an epoch second into openHAB's persistence; a point at the same time is replaced"""
    query = urllib.parse.urlencode({"serviceId": PERSISTENCE_SERVICE, "time": iso_time(epoch), "state": state})
    openhab_request("PUT", f"/persistence/items/{item}?{query}")


def first_measured_day():
    """the day of the first string's first reading openHAB's persistence still holds, not before FIRST_DAY: the
    database's retention drops older days"""
    item = STRINGS[0].measured_item
    query = urllib.parse.urlencode({"serviceId": PERSISTENCE_SERVICE, "starttime": iso_time(day_start(FIRST_DAY)),
                                    "page": 0, "pagelength": 1})
    rows = openhab_request("GET", f"/persistence/items/{item}?{query}").get("data", [])
    if not rows:
        sys.exit(f"no reading of {item} in openHAB's persistence {PERSISTENCE_SERVICE}")
    return max(FIRST_DAY, local_day(rows[0]["time"] / 1000))


def notify(text):
    """a push notification to every device through openHAB's script NOTIFY_RULE"""
    if not NOTIFY_RULE:
        return
    try:
        openhab_request("POST", f"/rules/{NOTIFY_RULE}/runnow", {"message": text})
    except (urllib.error.URLError, TimeoutError) as error:
        log(f"no notification sent: {error}")


# ---------------------------------------------------------------- Open-Meteo

def ask_open_meteo(url):
    """Open-Meteo's hourly data, asked again after 5, 10, ... seconds while it has none (its 503 when overloaded)"""
    for attempt in range(6):
        if attempt:
            time.sleep(5 * attempt)
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                answer = json.load(response)
            if "hourly" in answer:
                return answer["hourly"]
        except (urllib.error.URLError, TimeoutError, ValueError):
            pass
    raise RuntimeError("Open-Meteo did not answer")


def fetch_weather(api_url, latitude, longitude, time_span):
    """{hour's start: {column: value}}: each plane's irradiance from every weather model (one request per plane) and
    the best match's weather; Open-Meteo gives an hour's mean (or a value) at the hour's end"""
    rows = {}
    common = (f"{api_url}?latitude={latitude}&longitude={longitude}"
              f"&timezone={urllib.parse.quote(TIMEZONE.key, safe='')}&timeformat=unixtime&{time_span}")
    for plane in PLANES.values():
        hourly = ask_open_meteo(f"{common}&hourly=global_tilted_irradiance&tilt={plane.tilt:g}"
                                f"&azimuth={plane.azimuth:g}&models={','.join(WEATHER_MODELS)}")
        for model in WEATHER_MODELS:
            for hour_end, value in zip(hourly["time"], hourly.get(f"global_tilted_irradiance_{model}", [])):
                if isinstance(value, (int, float)):
                    rows.setdefault(hour_end - 3600, {})[f"{model}_{plane.name}"] = value
    hourly = ask_open_meteo(f"{common}&hourly={','.join(WEATHER_VARIABLES)}")
    for variable in WEATHER_VARIABLES:
        for hour_end, value in zip(hourly["time"], hourly.get(variable, [])):
            if isinstance(value, (int, float)):
                rows.setdefault(hour_end - 3600, {})[variable] = value
    return rows


# ---------------------------------------------------------------- time and the sun

def sun_position(epoch, latitude, longitude):
    """the sun's elevation and azimuth (degrees, the azimuth from north) at an epoch second, NOAA's approximation"""
    days = epoch / 86400 + 2440587.5 - 2451545.0  # since J2000.0
    mean_anomaly = math.radians((357.528 + 0.9856003 * days) % 360)
    ecliptic_longitude = math.radians((280.46 + 0.9856474 * days) % 360 + 1.915 * math.sin(mean_anomaly)
                                      + 0.020 * math.sin(2 * mean_anomaly))
    obliquity = math.radians(23.439 - 0.0000004 * days)
    right_ascension = math.atan2(math.cos(obliquity) * math.sin(ecliptic_longitude), math.cos(ecliptic_longitude))
    declination = math.asin(math.sin(obliquity) * math.sin(ecliptic_longitude))
    sidereal_hours = (18.697374558 + 24.06570982441908 * days) % 24
    hour_angle = math.radians(sidereal_hours * 15 + longitude) - right_ascension
    lat = math.radians(latitude)
    elevation = math.asin(math.sin(lat) * math.sin(declination)
                          + math.cos(lat) * math.cos(declination) * math.cos(hour_angle))
    azimuth = math.atan2(-math.sin(hour_angle),
                         math.tan(declination) * math.cos(lat) - math.sin(lat) * math.cos(hour_angle))
    return math.degrees(elevation), math.degrees(azimuth) % 360


def local_day(epoch):
    return datetime.datetime.fromtimestamp(epoch, TIMEZONE).date()


def day_start(day):
    return int(datetime.datetime.combine(day, datetime.time(), TIMEZONE).timestamp())


def day_end(day):
    return int(datetime.datetime.combine(day, datetime.time(23, 59, 59), TIMEZONE).timestamp())


# ---------------------------------------------------------------- the weather cache

def load_weather_cache():
    if not os.path.exists(WEATHER_CACHE_FILE):
        return {}
    with open(WEATHER_CACHE_FILE) as f:
        reader = csv.reader(f)
        columns = next(reader)[1:]
        return {int(row[0]): {column: float(value) for column, value in zip(columns, row[1:]) if value != ""}
                for row in reader}


def save_weather_cache(cache):
    os.makedirs(STATE_DIR, exist_ok=True)
    columns = WEATHER_VARIABLES + IRRADIANCE_COLUMNS
    with open(WEATHER_CACHE_FILE + ".tmp", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["t", *columns])
        for hour in sorted(cache):
            writer.writerow([hour, *[cache[hour].get(column, "") for column in columns]])
    os.replace(WEATHER_CACHE_FILE + ".tmp", WEATHER_CACHE_FILE)


def update_weather_cache():
    """the days missing up to yesterday from the historical forecast API, the last two again (late data); the days
    before the first PV reading persistence still holds dropped"""
    cache = load_weather_cache()
    latitude, longitude = location()
    today = datetime.datetime.now(TIMEZONE).date()
    first = first_measured_day()
    dropped = [hour for hour in cache if local_day(hour) < first]
    for hour in dropped:
        del cache[hour]
    yesterday = today - datetime.timedelta(days=1)
    last = max((local_day(hour) for hour in cache), default=None)
    start = first if last is None else max(first, last - datetime.timedelta(days=2))
    fetched = 0
    while start <= yesterday:
        end = min(yesterday, start + datetime.timedelta(days=90))
        rows = fetch_weather(HISTORICAL_API, latitude, longitude, f"start_date={start}&end_date={end}")
        for hour, row in rows.items():
            cache.setdefault(hour, {}).update(row)
        fetched += len(rows)
        start = end + datetime.timedelta(days=1)
    save_weather_cache(cache)
    log(f"weather cache: {len(cache)} hours from {first} to {yesterday}, {fetched} fetched, {len(dropped)} dropped")
    return cache


# ---------------------------------------------------------------- the strings' measured energy

def hourly_energy(readings, start, end):
    """each hour's energy in kWh within [start, end) from power readings in W, as InfluxDB's integral(value, 1h) per
    hour gives it: the trapezoids between consecutive readings, one across an hour's border split there at the value
    interpolated linearly; only hours with a reading of their own"""
    energy = {}
    for (time1, power1), (time2, power2) in zip(readings, readings[1:]):
        if time2 <= time1:
            continue
        segment_start, segment_end = max(time1, start), min(time2, end)
        while segment_start < segment_end:
            border = min(segment_end, (segment_start // 3600 + 1) * 3600)
            power_at_start = power1 + (power2 - power1) * (segment_start - time1) / (time2 - time1)
            power_at_border = power1 + (power2 - power1) * (border - time1) / (time2 - time1)
            hour = int(segment_start // 3600 * 3600)
            mean_power = (power_at_start + power_at_border) / 2
            energy[hour] = energy.get(hour, 0.0) + mean_power * (border - segment_start) / 3600 / 1000
            segment_start = border
    hours_with_reading = {int(t // 3600 * 3600) for t, _ in readings if start <= t < end}
    return {hour: kwh for hour, kwh in energy.items() if hour in hours_with_reading}


def load_measured_cache():
    """{hour's start: (string 1's kWh, string 2's, ...)}; empty when the file holds another number of strings, so that
    update_measured_cache reads all days again"""
    if not os.path.exists(MEASURED_CACHE_FILE):
        return {}
    with open(MEASURED_CACHE_FILE) as f:
        reader = csv.reader(f)
        if len(next(reader)) != 1 + len(STRINGS):
            return {}
        return {int(row[0]): tuple(float(value) for value in row[1:]) for row in reader}


def update_measured_cache():
    """the strings' energy per hour from openHAB's persistence: the days missing up to yesterday, the last two again;
    the days before the first PV reading persistence holds dropped"""
    measured = load_measured_cache()
    first = first_measured_day()
    today = datetime.datetime.now(TIMEZONE).date()
    dropped = [hour for hour in measured if local_day(hour) < first]
    for hour in dropped:
        del measured[hour]
    last = max((local_day(hour) for hour in measured), default=None)
    day = first if last is None else max(first, last - datetime.timedelta(days=2))
    read = 0
    while day < today:
        start, end = day_start(day), day_start(day + datetime.timedelta(days=1))
        per_string = [hourly_energy(read_history(string.measured_item, start, end - 0.001), start, end)
                      for string in STRINGS]
        for hour in [hour for hour in measured if start <= hour < end]:
            del measured[hour]
        for hour in set.intersection(*(set(energy) for energy in per_string)):
            measured[hour] = tuple(energy[hour] for energy in per_string)
            read += 1
        day += datetime.timedelta(days=1)
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(MEASURED_CACHE_FILE + ".tmp", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["t", *(f"pv{number}_kwh" for number in range(1, len(STRINGS) + 1))])
        for hour in sorted(measured):
            writer.writerow([hour, *(round(kwh, 6) for kwh in measured[hour])])
    os.replace(MEASURED_CACHE_FILE + ".tmp", MEASURED_CACHE_FILE)
    log(f"measured cache: {len(measured)} hours from {first} to {today - datetime.timedelta(days=1)}, {read} read, "
        f"{len(dropped)} dropped")
    return measured


# ---------------------------------------------------------------- the plain physical forecast: the check's benchmark

def physical_estimate(weather, plane_names):
    """the planes' irradiance (best match) times their modules at the cells' temperature (TEMPERATURE_COEFFICIENT per
    K above 25 °C, a cell (NOCT - 20 °C) / 800 W/m² warmer than the air per W/m²), in kW at 1 kW/m² per module"""
    air_temperature = weather.get("temperature_2m", 15.0)
    total = 0.0
    for name in plane_names:
        irradiance = weather.get(f"best_match_{name}", 0.0)
        cell_temperature = air_temperature + irradiance * (NOCT - 20) / 800
        total += PLANES[name].modules * irradiance * (1 + TEMPERATURE_COEFFICIENT / 100 * (cell_temperature - 25))
    return total / 1000


# ---------------------------------------------------------------- the features and the models

def feature_vector(hour_start, weather, latitude, longitude):
    """the hour's features in the order of FEATURES (NaN where the weather lacks one), and the sun's elevation"""
    elevation, azimuth = sun_position(hour_start + 1800, latitude, longitude)
    day_of_year = datetime.datetime.fromtimestamp(hour_start, TIMEZONE).timetuple().tm_yday
    computed = {"sun_el": elevation, "sun_az": azimuth, "doy_s": math.sin(2 * math.pi * day_of_year / 365.25),
                "doy_c": math.cos(2 * math.pi * day_of_year / 365.25)}
    return [computed[name] if name in computed else weather.get(name, float("nan")) for name in FEATURES], elevation


def training_data(weather_cache, measured, latitude, longitude):
    """the daylight hours with measurements as numpy arrays: their starts, their features (a column per feature), the
    strings' measured energies and the plain forecast's estimates (a column per string)"""
    import numpy as np
    hours, features, energies, estimates = [], [], [], []
    complete = [hour for hour in measured if hour in weather_cache
                and all(f"best_match_{plane}" in weather_cache[hour] for plane in PLANES)]
    for hour in sorted(complete):
        vector, elevation = feature_vector(hour, weather_cache[hour], latitude, longitude)
        if elevation > DAYLIGHT_ELEVATION:
            hours.append(hour)
            features.append(vector)
            energies.append(measured[hour])
            estimates.append([physical_estimate(weather_cache[hour], string.planes) for string in STRINGS])
    return np.array(hours), np.array(features, dtype=float), np.array(energies), np.array(estimates)


def train_models(features, energies):
    """a model per string, each on the feature columns with enough values: a weather model not yet archived over the
    training days (one archived only recently) is left out, as an empty column stops the training"""
    import numpy as np
    from sklearn.ensemble import HistGradientBoostingRegressor
    used_columns = np.where((~np.isnan(features)).sum(axis=0) >= MIN_VALUES_PER_COLUMN)[0]
    models = []
    for string_index in range(energies.shape[1]):
        model = HistGradientBoostingRegressor(**MODEL_PARAMETERS)
        model.fit(features[:, used_columns], energies[:, string_index])
        model.feature_columns = used_columns
        models.append(model)
    return models


def feature_columns_of(model):
    # the models the first version saved keep their columns as pv_columns
    return model.feature_columns if hasattr(model, "feature_columns") else model.pv_columns


def predict_energies(models, features):
    """the strings' energies, a column per string; the house's is their sum"""
    import numpy as np
    columns = [model.predict(features[:, feature_columns_of(model)]) for model in models]
    return np.clip(np.column_stack(columns), 0, None)


def mean_daily_errors(hours, forecast, reference, measured):
    """over the days of the hours: the forecast's and the reference's mean absolute error of a day's total, and the
    number of days"""
    days = {}
    for hour, forecast_kwh, reference_kwh, measured_kwh in zip(hours, forecast, reference, measured):
        totals = days.setdefault(local_day(int(hour)), [0.0, 0.0, 0.0])
        totals[0] += forecast_kwh
        totals[1] += reference_kwh
        totals[2] += measured_kwh
    count = len(days)
    forecast_error = sum(abs(f - m) for f, r, m in days.values()) / count
    reference_error = sum(abs(r - m) for f, r, m in days.values()) / count
    return forecast_error, reference_error, count


def check_candidate(hours, features, energies, estimates, split, until):
    """a candidate trained on the hours before split, against the plain forecast fitted on the same hours (one factor
    for all planes), on the hours from split to until: (the candidate's error, the plain forecast's, days) for the
    house, then for each string"""
    before = hours < split
    checked = (hours >= split) & (hours < until)
    predicted = predict_energies(train_models(features[before], energies[before]), features[checked])
    reference = energies[before].sum() / estimates[before].sum() * estimates[checked]
    measured = energies[checked]
    house = mean_daily_errors(hours[checked], predicted.sum(1), reference.sum(1), measured.sum(1))
    per_string = [mean_daily_errors(hours[checked], predicted[:, index], reference[:, index], measured[:, index])
                  for index in range(energies.shape[1])]
    return [house] + per_string


def load_meta():
    return json.load(open(META_FILE)) if os.path.exists(META_FILE) else {}


def train():
    import joblib
    weather_cache = update_weather_cache()
    latitude, longitude = location()
    measured = update_measured_cache()
    hours, features, energies, estimates = training_data(weather_cache, measured, latitude, longitude)
    split = day_start(local_day(int(hours[-1])) - datetime.timedelta(days=CHECK_DAYS - 1))
    (model_error, plain_error, days), *string_errors = check_candidate(hours, features, energies, estimates, split,
                                                                       hours[-1] + 1)
    old_meta = load_meta()
    now = datetime.datetime.now(TIMEZONE).isoformat(timespec="seconds")
    meta = {"checked": now, "rows": int(len(energies)), "check_days": days, "forecast_mae": round(model_error, 3),
            "plain_mae": round(plain_error, 3),
            "strings_mae": {string.forecast_item: [round(errors[0], 3), round(errors[1], 3)]
                            for string, errors in zip(STRINGS, string_errors)},
            "plain_factor": round(float(energies.sum() / estimates.sum()), 5),
            "first": str(local_day(int(hours[0]))), "last": str(local_day(int(hours[-1]))),
            "trained": old_meta.get("trained")}
    # the check is on the house's forecast, the sum of the strings'
    passed = model_error <= CHECK_TOLERANCE * plain_error
    each_string = "; ".join(f"string {number} {errors[0]:.2f} against {errors[1]:.2f}"
                            for number, errors in enumerate(string_errors, 1))
    if passed:
        joblib.dump({"models": train_models(features, energies), "features": FEATURES}, MODEL_FILE + ".tmp")
        os.replace(MODEL_FILE + ".tmp", MODEL_FILE)
        meta["trained"] = now
        log(f"trained on {len(energies)} hours from {meta['first']} to {meta['last']}; the candidate over the last "
            f"{days} days {model_error:.2f} kWh a day off, the plain forecast {plain_error:.2f} ({each_string})")
    else:
        log(f"WARNING: the candidate over the last {days} days {model_error:.2f} kWh a day off, the plain forecast "
            f"{plain_error:.2f} ({each_string}): the model of {old_meta.get('trained')} stays")
        since = old_meta.get("trained")
        since = datetime.datetime.fromisoformat(since).strftime("%d.%m.%Y") if since else None
        german = lambda value: f"{value:.2f}".replace(".", ",")
        notify(f"PV-Prognose: neues Modell verworfen, es lag die letzten {days} Tage {german(model_error)} kWh pro "
               f"Tag daneben, die einfache Rechnung {german(plain_error)}. "
               + (f"Das Modell vom {since} gilt weiter." if since else "Es gilt die einfache Rechnung."))
    json.dump(meta, open(META_FILE, "w"), indent=1)
    if not passed:
        sys.exit(1)


# ---------------------------------------------------------------- the forecast into openHAB

def publish(hours, source, trained):
    """hours [[hour's start, the house's W, string 1's W, string 2's W, ...], ...] into openHAB's items and their
    forecast series; returns the number of points written"""
    now = time.time()
    hourly = {"at": int(now), "trained": trained, "source": source, "h": [hour[:2] for hour in hours]}
    openhab_request("PUT", f"/items/{HOURLY_ITEM}/state", json.dumps(hourly), "text/plain")
    try:
        sent = json.load(open(SENT_FILE))
    except (OSError, ValueError):
        sent = {}
    # each hour's mean at its middle
    points = {(item, hour_start + 1800): watts
              for hour_start, *powers in hours for item, watts in zip(POWER_ITEMS, powers)}
    today = datetime.datetime.now(TIMEZONE).date()
    day_totals = {}
    for hour_start, house_watts, *_ in hours:
        day = local_day(hour_start)
        if day >= today:
            day_totals[day] = day_totals.get(day, 0.0) + house_watts / 1000
    points.update({(ENERGY_ITEM, day_end(day)): round(kwh, 2) for day, kwh in day_totals.items()})
    written = 0
    for (item, epoch), value in points.items():
        if sent.get(f"{item} {epoch}") != value:
            store_point(item, epoch, f"{value} {'kWh' if item == ENERGY_ITEM else 'W'}")
            sent[f"{item} {epoch}"] = value
            written += 1
    running_hour = next((powers for hour_start, *powers in hours if hour_start <= now < hour_start + 3600),
                        [None] * len(POWER_ITEMS))
    states = {item: "UNDEF" if watts is None else f"{watts} W" for item, watts in zip(POWER_ITEMS, running_hour)}
    for item, day in ((ENERGY_ITEM, today), (ENERGY_TOMORROW_ITEM, today + datetime.timedelta(days=1))):
        if day in day_totals:
            states[item] = f"{round(day_totals[day], 2)} kWh"
    for item, state in states.items():
        openhab_request("PUT", f"/items/{item}/state", state, "text/plain")
    # keys "item epoch" of the last day; a key of another form (an older version's) goes, so its point is written again
    sent = {key: value for key, value in sent.items() if " " in key and int(key.split()[1]) >= now - 86400}
    json.dump(sent, open(SENT_FILE + ".tmp", "w"))
    os.replace(SENT_FILE + ".tmp", SENT_FILE)
    return written


def forecast():
    import numpy as np
    meta = load_meta()
    latitude, longitude = location()
    weather = fetch_weather(FORECAST_API, latitude, longitude, "forecast_days=2")
    weather = {hour: row for hour, row in weather.items() if all(f"best_match_{plane}" in row for plane in PLANES)}
    hour_starts = sorted(weather)
    vectors, elevations = zip(*(feature_vector(hour, weather[hour], latitude, longitude) for hour in hour_starts))
    if os.path.exists(MODEL_FILE):
        import joblib
        bundle = joblib.load(MODEL_FILE)
        assert bundle["features"] == FEATURES and "models" in bundle, "features changed, train again"
        predicted, source = predict_energies(bundle["models"], np.array(vectors, dtype=float)), "ml"
    elif "plain_factor" in meta:
        predicted = [[meta["plain_factor"] * physical_estimate(weather[hour], string.planes) for string in STRINGS]
                     for hour in hour_starts]
        source = "plain"
    else:
        raise RuntimeError("no model and no training yet: run train")
    # the strings rounded to whole W, the house their sum
    hours = []
    for hour_start, string_kwh, elevation in zip(hour_starts, predicted, elevations):
        string_watts = [round(float(kwh) * 1000) if elevation > DAYLIGHT_ELEVATION else 0 for kwh in string_kwh]
        hours.append([hour_start, sum(string_watts), *string_watts])
    written = publish(hours, source, meta.get("trained"))
    day_totals = {}
    for hour_start, *watts in hours:
        day = local_day(hour_start)
        day_totals[day] = [total + w / 1000 for total, w in zip(day_totals.get(day, [0.0] * len(watts)), watts)]
    log(f"forecast ({source}): "
        + ", ".join(f"{day} {totals[0]:.1f} kWh ({' + '.join(f'{kwh:.1f}' for kwh in totals[1:])})"
                    for day, totals in sorted(day_totals.items()) if totals[0] > 0)
        + f"; {written} points written")


def backfill(first, apply):
    """month by month as the nightly training would have gone: a candidate on the days until 60 days before the month,
    checked on those 60 against the plain forecast; where it passed, the model on all days before forecasts the month,
    else the old history stays"""
    import numpy as np
    weather_cache = load_weather_cache()
    latitude, longitude = location()
    measured = update_measured_cache()
    hours, features, energies, estimates = training_data(weather_cache, measured, latitude, longitude)
    predicted = np.full(energies.shape, np.nan)
    month = datetime.date(first.year, first.month, 1)
    while True:
        next_month = (month + datetime.timedelta(days=32)).replace(day=1)
        month_start, month_end = day_start(max(month, first)), day_start(next_month)
        in_month = (hours >= month_start) & (hours < month_end)
        if not in_month.any():
            break
        check_start = day_start(max(month, first) - datetime.timedelta(days=CHECK_DAYS))
        if check_start - hours[0] < 90 * 86400:
            log(f"  {month:%Y-%m}: skipped (less than 90 days to train a candidate on)")
            month = next_month
            continue
        (model_error, plain_error, days), *_ = check_candidate(hours, features, energies, estimates, check_start,
                                                               month_start)
        if model_error <= CHECK_TOLERANCE * plain_error:
            before = hours < month_start
            predicted[in_month] = predict_energies(train_models(features[before], energies[before]), features[in_month])
            factor = energies[before].sum() / estimates[before].sum()
            month_errors = mean_daily_errors(hours[in_month], predicted[in_month].sum(1),
                                             factor * estimates[in_month].sum(1), energies[in_month].sum(1))
            log(f"  {month:%Y-%m}: model (checked {model_error:.2f} against the plain forecast's {plain_error:.2f} on "
                f"{days} days); the month {month_errors[0]:.2f} kWh a day off, the plain forecast "
                f"{month_errors[1]:.2f}")
        else:
            log(f"  {month:%Y-%m}: skipped (the candidate {model_error:.2f} against the plain forecast's "
                f"{plain_error:.2f})")
        month = next_month
    forecast_made = ~np.isnan(predicted[:, 0])
    if not forecast_made.any():
        log("the model would not have forecast a single month: nothing to write")
        return
    model_days = {local_day(int(hour)) for hour in hours[forecast_made]}
    # the strings rounded to whole W, the house their sum, as forecast() writes them
    string_watts = {hour: [0] * len(STRINGS) for hour in weather_cache if local_day(hour) in model_days}
    for hour, string_kwh in zip(hours[forecast_made], predicted[forecast_made]):
        string_watts[int(hour)] = [round(float(kwh) * 1000) for kwh in string_kwh]
    day_totals = {}
    for hour, watts in string_watts.items():
        day_totals[local_day(hour)] = day_totals.get(local_day(hour), 0.0) + sum(watts) / 1000
    points = [(item, hour + 1800, f"{w} W") for hour, watts in sorted(string_watts.items())
              for item, w in zip(POWER_ITEMS, [sum(watts), *watts])]
    points += [(ENERGY_ITEM, day_end(day), f"{round(kwh, 2)} kWh") for day, kwh in sorted(day_totals.items())]
    if not apply:
        log(f"would write {len(points)} points ({len(string_watts)} hours, {len(day_totals)} days); "
            f"--apply writes them")
        return
    # the points replaced, so that restore writes them back
    start, end = min(string_watts) + 1800, max(day_end(day) for day in day_totals)
    backup = os.path.join(STATE_DIR, f"backup-{datetime.datetime.now(TIMEZONE):%Y%m%d-%H%M%S}.csv")
    with open(backup, "w", newline="") as f:
        writer = csv.writer(f)
        for item in (*POWER_ITEMS, ENERGY_ITEM):
            unit = "kWh" if item == ENERGY_ITEM else "W"
            for epoch, value in read_history(item, start, end):
                if start <= epoch <= end:
                    writer.writerow([item, int(epoch), f"{value:g} {unit}"])
    for item, epoch, state in points:
        store_point(item, epoch, state)
    log(f"written {len(points)} points ({len(string_watts)} hours, {len(day_totals)} days); the old ones in {backup}")


def restore(path):
    """the points of a backup written back"""
    count = 0
    with open(path) as f:
        for item, epoch, state in csv.reader(f):
            store_point(item, int(epoch), state)
            count += 1
    log(f"restored {count} points from {path}")


def status():
    print(open(META_FILE).read() if os.path.exists(META_FILE) else "no training yet")
    weather_cache = load_weather_cache()
    print(f"weather cache: {len(weather_cache)} hours"
          + (f", {local_day(min(weather_cache))} to {local_day(max(weather_cache))}" if weather_cache else ""))
    measured = load_measured_cache()
    print(f"measured cache: {len(measured)} hours"
          + (f", {local_day(min(measured))} to {local_day(max(measured))}" if measured else ""))


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    if command == "update":
        update_weather_cache()
        update_measured_cache()
    elif command == "train":
        train()
    elif command == "forecast":
        forecast()
    elif command == "backfill":
        backfill(datetime.date.fromisoformat(sys.argv[2]), "--apply" in sys.argv)
    elif command == "restore":
        restore(sys.argv[2])
    else:
        status()
