# pv_forecast_ml

A PV forecast for openHAB that learns from your own installation's measurements.

Every 30 minutes it forecasts today's and tomorrow's PV power hour by hour and writes it into openHAB: as items for
rules and as forecast series that charts can draw ahead of time. It needs no data sheet and no model of shading: a
machine learning model per string of the inverter learns from past weather forecasts and the power the string
actually produced.

## How it works

- **Inputs.** For each hour: the irradiance on each plane of modules as ten weather models forecast it (Open-Meteo's
  best match, DWD ICON-EU, ECMWF IFS, Météo-France, UK Met Office, KNMI, MET Norway, NOAA GFS, DMI and GeoSphere's
  AROME Austria), the weather of Open-Meteo's best match (radiation parts, temperature, humidity, three cloud layers,
  wind, precipitation, snow and visibility), the sun's position and the day of the year.
- **Models.** One gradient boosting model per string (scikit-learn's `HistGradientBoostingRegressor`) learns the
  string's energy per hour from these inputs. The house's forecast is the sum of the strings'. Each string's model
  sees all planes, so it can learn by itself how shading and the planes' mix affect its string.
- **Training data.** Open-Meteo's archived forecasts (its historical forecast API, for the same hours as forecast at
  the time) and the strings' measured power from openHAB's persistence, integrated to energy per hour. Both are cached
  locally; each night adds the day before.
- **A check before every model change.** Each night a candidate is trained on all but the last 60 days and has to
  forecast those 60 days about as well as a plain physical forecast (the irradiance times the modules at the cells'
  temperature, scaled by one factor fitted on the same days). Only if it does, models trained on all days replace the
  ones in use. A failed check points to a broken training, a bug or broken readings: the models in use stay and an
  openHAB script sends a push notification (in German).
- **Only through openHAB.** The service never talks to the database itself. It reads and writes through openHAB's
  REST API for its persistence, so the database connection is configured in openHAB alone.

## What it writes into openHAB

| Item | What |
| --- | --- |
| `pv_forecast_power` | the house's forecast power: each hour's mean at the hour's middle as a forecast series; its state is the running hour's |
| one item per string, named in the settings | the same for each string; together they add up to `pv_forecast_power` |
| `pv_forecast_energy` | each day's forecast total from today on, at the day's 23:59:59, as a forecast series; its state is today's |
| `pv_forecast_energy_tomorrow` | tomorrow's forecast total; persisted on change, its history shows the day-ahead forecasts |
| `pv_forecast_hourly` | JSON `{at, trained, source, h: [[hour's start, W], ...]}` for rules; `source` is `ml`, or `plain` before the first training |

Only changed points are written. If the service stops, the last forecast stays in the items, and the `at` field tells
rules how old it is.

## Requirements

- openHAB 4.1 or later with an API token that may write item states and persistence.
- A persistence service that stores points in the future, such as InfluxDB with the `forecast` strategy.
- The measured power of each string as an item with history in that persistence, ideally a year or more: the more
  seasons the models have seen, the better they get.
- Python 3.11 or later with numpy, scikit-learn and joblib (`requirements.txt`).
- Internet access to Open-Meteo (free, no key needed).

## Installing

1. In openHAB, create the items from [`openhab/pv_forecast.items`](openhab/pv_forecast.items), one forecast item per
   string, and add the forecast items to a persistence that stores future points. For the push notification after a
   failed training, create the script [`openhab/notify_broadcast.js`](openhab/notify_broadcast.js) with the UID
   `notify_broadcast`.
2. Install the service:

   ```
   sudo mkdir -p /opt/pv_forecast_ml
   sudo cp pv_forecast_ml.py README.md /opt/pv_forecast_ml/
   python3 -m venv ~/.venv/pv_forecast_ml
   ~/.venv/pv_forecast_ml/bin/pip install -r requirements.txt
   install -m 600 env.example ~/.venv/pv_forecast_ml/.env
   ```

3. Describe your planes and strings in `~/.venv/pv_forecast_ml/.env` (see the settings below).
4. Install the systemd units, adjusting the user and the paths in them, and train once:

   ```
   sudo cp pv-forecast-ml*.service pv-forecast-ml*.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now pv-forecast-ml.timer pv-forecast-ml-train.timer
   sudo systemctl start pv-forecast-ml-train
   ```

The first training fetches the archived forecasts for every day with measurements, which takes a few minutes. After
that the forecast runs at 2 and 32 minutes past every hour and the training every night at 02:30.

## Settings

The service reads its settings from environment variables; the systemd units load them from the `.env` file.

| Variable | Default | Meaning |
| --- | --- | --- |
| `PV_FORECAST_ML_PLANES` | (required) | the planes of modules, comma-separated, each as `name:azimuth:tilt:modules`; the azimuth in degrees from south with east negative, the tilt in degrees. Example: `e:-90:25:8,w:90:25:8,n:180:25:6` |
| `PV_FORECAST_ML_STRINGS` | (required) | the inverter's strings, comma-separated, each as `measured power item:forecast power item:planes`, the planes joined by `+`. Example: `pv1_power:pv_forecast_pv1_power:e,pv2_power:pv_forecast_pv2_power:w+n` |
| `PV_FORECAST_ML_LATITUDE`, `PV_FORECAST_ML_LONGITUDE` | openHAB's location | the installation's location; rounded to 2 decimals, which is finer than the weather models' grid |
| `PV_FORECAST_ML_TIMEZONE` | the system's | the time zone the days are counted in, e.g. `Europe/Berlin` |
| `PV_FORECAST_ML_OPENHAB_URL` | `http://127.0.0.1:8080` | openHAB's address |
| `PV_FORECAST_ML_OPENHAB_TOKEN_FILE` | `~/.openhab_token` | a file holding the openHAB API token |
| `PV_FORECAST_ML_PERSISTENCE` | `influxdb` | the persistence service for the measurements and the forecast series |
| `PV_FORECAST_ML_NOTIFY_RULE` | `notify_broadcast` | the openHAB script a failed training runs; empty for no notification |
| `PV_FORECAST_ML_STATE` | `~/.local/state/pv_forecast_ml` | where the caches and the models are kept |
| `PV_FORECAST_ML_FIRST` | `2000-01-01` | the earliest day used for training |
| `PV_FORECAST_ML_MODELS` | the ten above | Open-Meteo's weather models, comma-separated |
| `PV_FORECAST_ML_FORECAST_API` | Open-Meteo's | the forecast API's address |
| `PV_FORECAST_ML_HISTORICAL_API` | Open-Meteo's | the historical forecast API's address |
| `PV_FORECAST_ML_TEMP_COEFFICIENT` | `-0.34` | the modules' power change per kelvin above 25 °C, in percent (for the plain forecast) |
| `PV_FORECAST_ML_NOCT` | `43` | the modules' nominal operating cell temperature in °C (for the plain forecast) |

The planes and the weather models determine the models' inputs. After changing either, delete `weather.csv` in the
state directory, so that the next run fetches every day again, and train; the forecast refuses models trained on
other inputs. After changing the strings' items, delete `measured.csv`.

## Commands

Normally the timers do everything. To run a command by hand, load the settings first:

```
set -a; . ~/.venv/pv_forecast_ml/.env; set +a
~/.venv/pv_forecast_ml/bin/python /opt/pv_forecast_ml/pv_forecast_ml.py COMMAND
```

| Command | What it does |
| --- | --- |
| `status` | shows the last training's figures and how far the caches reach |
| `update` | adds the missing days to the weather cache and to the cache of the strings' energy per hour |
| `train` | runs `update`, then trains and checks a candidate; exits with 1 if the check fails |
| `forecast` | writes today's and tomorrow's forecast into openHAB |
| `backfill FROM [--apply]` | computes the forecast the models would have made from the day `FROM` on, month by month as the nightly check would have decided; with `--apply` it writes it into the forecast series, after saving the points it replaces |
| `restore FILE` | writes the points of such a backup back |

The energy per hour is integrated from the power readings as InfluxDB's `integral()` does it: trapezoids between the
readings, split at the hour's border. Hours without a reading of their own are left out, so gaps in the
measurements do not distort the training.

## How well it works

On the installation it was developed for (22 modules on three planes, two strings), retrained weekly as the nightly
training would have done over most of a year, the forecast of a day's total was off by 1.8 kWh on average. A physical
forecast with factors fitted to the last two weeks was off by 2.3 kWh over the same days. One model per string came
out as well as one model for the whole house, and it gives each string a forecast of its own. More history helped:
trained on the last 6 months, the error was 2.44 kWh a day, on 12 months 1.94, on all 18 to 24 months 1.89.

Tried and left out, because they did not help:

- weighting recent days more than older ones;
- the strings' recent yields as inputs, or a correction by the model's own recent error;
- a correction within the day from how far the morning was off;
- satellite irradiance of the years before the installation (PVGIS) as extra training data, which helped only while
  the measurements covered less than a year;
- choosing the individually best weather models instead of models of different weather services: models of different
  services make different errors, and that is what the learner can use.
