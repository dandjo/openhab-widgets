# pv_forecast_ml

The house's PV forecast for openHAB (on homepi since 2026-10-19; the only one since the rule `pv_forecast` was removed
on 2026-10-20). Gradient boosting models (scikit-learn's `HistGradientBoostingRegressor`), one per string, learn each
string's hourly energy from the raw data alone, a truth of their own; the house's forecast is their sum (since
2026-10-20). Their inputs, all from Open-Meteo's forecasts or the clock:

- the irradiance on the modules' planes (on homepi east, west and north, all at 25°) from ten weather models:
  Open-Meteo's best match, DWD ICON-EU, ECMWF IFS, Météo-France, UK Met Office, KNMI, MET Norway, NOAA GFS, DMI and
  GeoSphere's AROME Austria;
- the best match's weather: radiation parts, temperature, humidity, three cloud layers, wind, precipitation, snow
  and visibility;
- the sun's position and the day of the year.

It talks to InfluxDB only through openHAB's REST API for its persistence (`GET` and `PUT
/rest/persistence/items/<item>`, service `influxdb` by default), so that the database's connection is configured in
openHAB alone (user, 2026-10-20). Every 30 minutes the service writes today's and tomorrow's hours into openHAB:

- `pv_forecast_hourly`: JSON `{at, trained, source, h: [[hour's start, W], ...]}`, read by heatpump_dhw_management,
  which counts a forecast older than 3 hours as none;
- `pv_forecast_power`: each hour's mean at its middle as a forecast series through openHAB's persistence (only
  changed points); its state is the running hour's;
- each string's forecast item (on homepi `pv_forecast_pv1_power` for string 1, east, and `pv_forecast_pv2_power` for
  string 2, west and north): the same for the string; `pv_forecast_power` is their sum;
- `pv_forecast_energy`: each day's total from today on at 23:59:59, as a forecast series; its state is today's;
- `pv_forecast_energy_tomorrow`: tomorrow's total (openHAB persists it on change: the day-ahead forecasts).

On homepi the items come from `~/scripts/openhab-ui/applied/pv_forecast.py check|apply`
([`scripts/openhab-ui/applied/pv_forecast.py`](../../scripts/openhab-ui/applied/pv_forecast.py) in the widgets
repository).

## Settings

From the environment; on homepi from the venv's `.env`, which the systemd units read as their `EnvironmentFile`
([`env.example`](env.example) shows the format).

| Variable | Default | Meaning |
| --- | --- | --- |
| `PV_FORECAST_ML_PLANES` | (required) | the modules' planes, comma-separated, each `name:azimuth:tilt:modules`; the azimuth in degrees from south, east negative (as Open-Meteo takes it), the tilt in degrees; on homepi `e:-90:25:8,w:90:25:8,n:180:25:6` |
| `PV_FORECAST_ML_STRINGS` | (required) | the inverter's strings, comma-separated, each `measured power item:forecast power item:planes`, the planes joined by `+`; on homepi `huawei_inverter_pv1_power:pv_forecast_pv1_power:e,huawei_inverter_pv2_power:pv_forecast_pv2_power:w+n` |
| `PV_FORECAST_ML_LATITUDE`, `PV_FORECAST_ML_LONGITUDE` | openHAB's regional settings | the location, rounded to 2 decimals (about 1 km, finer than the weather models' grid) |
| `PV_FORECAST_ML_TIMEZONE` | the system's | the time zone of the days, by its name, e.g. `Europe/Vienna` |
| `PV_FORECAST_ML_OPENHAB_URL` | `http://127.0.0.1:8080` | openHAB's address |
| `PV_FORECAST_ML_OPENHAB_TOKEN_FILE` | `~/.openhab_token` | a file with an openHAB API token that may write item states and persistence |
| `PV_FORECAST_ML_PERSISTENCE` | `influxdb` | openHAB's persistence service for the readings and the forecast series |
| `PV_FORECAST_ML_NOTIFY_RULE` | `notify_broadcast` | the openHAB script a failed training runs with `{"message": ...}`; empty: none |
| `PV_FORECAST_ML_STATE` | `~/.local/state/pv_forecast_ml` | the caches, the models and their state |
| `PV_FORECAST_ML_FIRST` | `2000-01-01` | no earlier day is used (nor any before the first PV reading persistence holds) |
| `PV_FORECAST_ML_MODELS` | the ten above | Open-Meteo's weather models, comma-separated |
| `PV_FORECAST_ML_FORECAST_API` | Open-Meteo's forecast API | `https://api.open-meteo.com/v1/forecast` |
| `PV_FORECAST_ML_HISTORICAL_API` | Open-Meteo's historical forecast API | `https://historical-forecast-api.open-meteo.com/v1/forecast` |
| `PV_FORECAST_ML_TEMP_COEFFICIENT` | `-0.34` | the modules' power change per K above 25 °C cell temperature, in % (the plain forecast) |
| `PV_FORECAST_ML_NOCT` | `43` | the modules' nominal operating cell temperature in °C (the plain forecast) |

The planes and the weather models make the features: after changing either, delete `weather.csv` in the state
directory (the next update fetches every day again) and train; the forecast refuses a model trained on other
features. After changing the strings' items, delete `measured.csv`.

## Installing

```
sudo mkdir -p /opt/pv_forecast_ml && sudo cp * /opt/pv_forecast_ml/
python3 -m venv ~/.venv/pv_forecast_ml
~/.venv/pv_forecast_ml/bin/pip install -r requirements.txt
install -m 600 env.example ~/.venv/pv_forecast_ml/.env        # then set the planes and the strings in it
sudo cp pv-forecast-ml*.service pv-forecast-ml*.timer /etc/systemd/system/   # adjust User and the paths
sudo systemctl daemon-reload && sudo systemctl enable --now pv-forecast-ml.timer pv-forecast-ml-train.timer
sudo systemctl start pv-forecast-ml-train   # the first training, then the forecast runs every 30 minutes
```

## Layout on homepi

| Path | What |
| --- | --- |
| `/opt/pv_forecast_ml/pv_forecast_ml.py` | the service (root's, like all of `/opt`: changes with sudo) |
| `/opt/pv_forecast_ml/*.service`, `*.timer` | copies of the units, as published |
| `/home/pi/.venv/pv_forecast_ml` | its venv: numpy, scikit-learn, joblib |
| `/home/pi/.venv/pv_forecast_ml/.env` | its settings (mode 600) |
| `/home/pi/.local/state/pv_forecast_ml/weather.csv` | Open-Meteo's archived forecasts per hour |
| `/home/pi/.local/state/pv_forecast_ml/measured.csv` | the strings' energy per hour, from openHAB's persistence |
| `/home/pi/.local/state/pv_forecast_ml/model.joblib` | the models in use, one per string |
| `/home/pi/.local/state/pv_forecast_ml/meta.json` | the last training: when, the check's figures (the house's and each string's), the plain forecast's factor |
| `/home/pi/.local/state/pv_forecast_ml/sent.json` | the points last written, so that only changes go out |
| `/home/pi/.local/state/pv_forecast_ml/backup-*.csv` | the points a backfill replaced (item, epoch second, state) |
| `/etc/systemd/system/pv-forecast-ml.{service,timer}` | `forecast` at 2 and 32 minutes past each hour |
| `/etc/systemd/system/pv-forecast-ml-train.{service,timer}` | `train` nightly at 02:30 |

Both services run as `pi`.

## Commands

By hand, with the settings of the `.env`:

```
set -a; . ~/.venv/pv_forecast_ml/.env; set +a
~/.venv/pv_forecast_ml/bin/python /opt/pv_forecast_ml/pv_forecast_ml.py update|train|forecast|status
~/.venv/pv_forecast_ml/bin/python /opt/pv_forecast_ml/pv_forecast_ml.py backfill FROM [--apply]
~/.venv/pv_forecast_ml/bin/python /opt/pv_forecast_ml/pv_forecast_ml.py restore BACKUP
```

- **update**: adds the missing days up to yesterday to the weather cache and to the cache of the strings' energy per
  hour, and reads the last two days again. The energy comes from the strings' power readings in openHAB's persistence,
  integrated per hour as InfluxDB's `integral(value, 1h)` does: trapezoids between the readings, a segment across an
  hour's border split there. On three days that matched to the Wh. Where the old readings have gaps or outliers it
  stays plausible where InfluxDB's sum did not (9.6 kWh in one hour in June 2025), and the models came out a little
  better, 1.77 against 1.80 kWh a day off over 2026. Both caches drop the days before the first PV reading
  persistence still holds (InfluxDB's retention, 5 years on homepi; the first readings are of 2024-09-30): training
  needs both.
- **train**: runs update, then trains a candidate on all but the last 60 days and checks the house's forecast, the
  sum of the strings', on those 60 days (each string's figures are logged too). The benchmark is a plain physical
  forecast: the best match's irradiance times the modules at the cells' temperature times one factor, the ratio of
  sums over the same days. Unless the candidate came out more than 20 % worse, the models trained on all days replace
  the ones in use. Otherwise the one in use stays, the unit fails, a warning goes to the journal, and openHAB's script
  `notify_broadcast` sends a push notification. The check catches a broken training (a bug, a library's change, a
  broken cache or broken readings), which lands far above that. Replayed weekly from June 2025 to October 2026, the
  candidate's error was 0.44 to 0.6 times the plain forecast's in summer and winter, but up to 1.01 in the calm weeks
  of late September and October, when one factor fits well.
- **forecast**: writes the hours as above. Without any model it writes the plain forecast with the last training's
  factor, each string's from its own planes (`source: plain`).
- **backfill**: replays month by month what the nightly training would have decided and writes the models' forecast
  into `pv_forecast_power`, the strings' series and `pv_forecast_energy`; months that fail the check keep their old
  history. With `--apply` the old points are saved first, as a CSV in the state directory.
- **restore**: writes the points of such a backup back through openHAB.

If the service stops, the last forecast stays in the items. The hot water then ignores it after 3 hours.

## How good

On homepi, walk-forward on 2026, retrained weekly as the nightly training comes closest to; mean absolute error of a
day's total in kWh:

| Period | Model | Former rule `pv_forecast` |
| --- | --- | --- |
| 2026 (January to October) | 1.79 | 2.34 |
| Spring | 2.02 | 2.39 |
| Summer | 2.07 | 2.80 |
| Last 60 days | 1.37 | 1.37 |
| Afternoon, 13 to 18 h | 1.01 | 1.28 |

Since 2026-10-20 a model per string, the house's forecast their sum (same test, ten weather models):

| Period | Sum of the string models | One model for the house | String 1 (east) | String 2 (west, north) |
| --- | --- | --- | --- | --- |
| 2026 (January to October) | 1.81 | 1.85 | 0.81 | 1.15 |
| Spring | 2.08 | 2.15 | 0.94 | 1.26 |
| July to October | 1.70 | 1.71 | 0.75 | 1.14 |
| Last 60 days | 1.39 | 1.38 | 0.59 | 1.02 |

Each string's model sees all planes. Given only their own planes, retrained monthly over 2026, string 1 came out 0.84
against 0.83 and string 2 1.14 against 1.12. The inverter measures only the strings, so string 2's west and north
cannot be learnt apart.

More history helps. For April to October 2026 the error was 2.44 kWh a day with the last 6 months to train on, 1.94
with 12 months, and 1.89 with everything (18 to 24 months).

Not built in, after tests:

- **Weighting recent days more** (half-lives of 60 to 365 days): at most 0.06 better over the last 60 days, up to
  0.13 worse in spring, when last year's spring then counts too little.
- **The strings' recent yields as inputs**, or a correction by the model's own error over the last 14 days: worse.
- **The rule's forecast** as an input or mixed in: no better since the model has a full year to learn from.
- **PVGIS 6** has satellite irradiance up to 2025 but no forecast. As training years before the PV system it helped
  only while the measurements were short.
- **A correction within the day** by how far the measured morning was off: 12 to 18 h came out 1.05 kWh off at best,
  against 1.06 without.
- **The energy community's forecast** is made from Open-Meteo's weather data as well and has no measurements.
- **Solcast** needs an account.
- **Other weather models**: of the 19 that Open-Meteo archives, each alone came out 2.41 (DWD ICON-EU) to 4.91 kWh a
  day off (25 May to 18 October 2026). The best 5 to 9 of them in the model gave 1.94 to 1.97, worse than the nine
  of different weather services (1.79), whose errors differ more than those of the ICON family at the top. AROME
  Austria, the most local, alone 3.65 and archived only from 2026-03-24, is in anyway (user): the model came out the
  same with it (1.79).
