// The house's own PV forecast (user, 2026-10-19): Open-Meteo's forecast of the irradiance on the three 25° planes of
// the modules, east (8 modules, string 1), west (8) and north (6, both string 2), Trina Vertex S TSM-DE09R.08 (415 to
// 435 Wp), each plane's irradiance times its modules, at the cell temperature the datasheet gives for that irradiance
// and the air's temperature (-0.34 % per K above 25 °C, NOCT 43 °C), times a factor per string (W per W/m² per
// module) fitted each day on the last 14 days of Open-Meteo's archived forecasts against the string's energy, as a
// ratio of sums: one for each hour of the day where that hour's irradiance is enough to tell, so it learns the shade
// (string 1 loses its afternoon to it), else the day's (user, 2026-10-19), both on the clear days of the 14 alone,
// those both sunny and forecast so, where the forecast's irradiance holds: on all 14 the cloudy days' forecast errors
// went into the factors, and clear summer days came out 1.0 kWh too high (user, 2026-10-19: "an sonnigen Sommertagen
// merklich darüber"); an hour's factor at most 1.1 times the day's and smoothed with its neighbours', weighted by
// their irradiance, as with as few as 3 clear days one hour's could run off (9 June 2025: 11.9 kW forecast at 11 h for
// 6.2). Replayed on 30 September 2024 to 18 October 2026, each day fitted on the 14 before: clear summer days 0.02 kWh
// too low and 1.39 off (on all 14 days +1.01 and 1.88), their afternoon from 13 to 18 h 0.11 too high, 0.75 off; all
// days 0.04 too low and 2.25 off, the afternoon 0.00 and 1.13 off (the first model, a
// least-squares fit per plane on the afternoons, was 2.1 kWh a day too low, in summer 6.7, as least squares on
// forecasts comes out low wherever they err and it could not tell the west plane from the north one). The hours of
// today and tomorrow go into pv_forecast_hourly (JSON, read by heatpump_dhw_management) and as a forecast series into
// pv_forecast_power, each hour's mean at its middle, so that the line through them lies over the measured power (the
// PV page draws both), and each day's total into pv_forecast_energy at the day's 23:59:59, as the daily totals stand
// (energy_daily_*).
// the house's location from openHAB's own settings (Settings, Regional Settings), rounded to 2 decimals, about 1 km
// and finer than the weather models' grid, so that no coordinates stand in the script
const HERE = (() => {
  const point = osgi.getService('org.openhab.core.i18n.LocationProvider').getLocation();
  if (point === null) {
    throw new Error('no location set in openHAB (Settings, Regional Settings)');
  }
  return { lat: point.getLatitude().doubleValue().toFixed(2), lon: point.getLongitude().doubleValue().toFixed(2) };
})();
const LOCATION = `latitude=${HERE.lat}&longitude=${HERE.lon}&timezone=Europe%2FVienna&timeformat=unixtime`;
const TILT = 25;
// the planes as the strings behave: the house stands about 10° turned (by the map east -80, west 100, north 170; the
// strings' curves on sunny days confirm north at about 170), but replayed on two years each turn forecast worse:
// string 1 (east, no optimizers, string 2 has Huawei P2 ones) loses its afternoon to shade and runs like a plane
// facing east to east-north-east (user's map and module data, 2026-10-19)
const PLANES = { east: -90, west: 90, north: 180 };
const MODULES = { east: 8, west: 8, north: 6 };
// the modules' power falls by 0.34 % per K of cell temperature above 25 °C; a cell is (NOCT 43 °C − 20 °C) / 800 W/m²
// warmer than the air per W/m² on it
const TEMPERATURE_COEFFICIENT = -0.0034;
const CELL_RISE = (43 - 20) / 800;
// W per W/m² per plane at 25 °C cell temperature (its modules times its string's factor), fitted on 5 to 18 October
// 2026; used until the rule's own fit succeeds
const DEFAULT = { east: 3.51, west: 2.49, north: 1.87 };
const MODEL = 7;  // the factors' model; factors of another one are fitted anew (7: the house's own location)
const HOUR_CAP = 1.1;  // an hour's factor at most this many times the day's
// a clear day of the fit: the strings' energy and the forecast's both at least this share of the window's best; with
// fewer than CLEAR_DAYS of them, all days count
const CLEAR = 0.85;
const CLEAR_DAYS = 3;
const STRING_OF = { east: 's1', west: 's2', north: 's2' };
const FIT_DAYS = 14;
const TRIES = 3;
const Thread = Java.type('java.lang.Thread');
const JTimeSeries = Java.type('org.openhab.core.types.TimeSeries');
const JInstant = Java.type('java.time.Instant');
const QuantityType = Java.type('org.openhab.core.library.types.QuantityType');
const Persistence = Java.type('org.openhab.core.persistence.extensions.PersistenceExtensions');
const store = cache.private;
const hourly = items.getItem('pv_forecast_hourly');
const now = Date.now();

// an hourly value of Open-Meteo by the hour's start (it gives an hour's mean, a temperature its value, at the hour's
// end), or null; no answer, an error answer ({error: true, reason}: Open-Meteo's 503 while it is overloaded) or one
// without the data is asked again after 5 and 10 seconds, as the weather rule does
function series(host, range, query, field) {
  const url = `https://${host}/v1/forecast?${LOCATION}&${range}&hourly=${query}`;
  for (let n = 0; n < TRIES; n++) {
    if (n > 0) {
      Thread.sleep(5000 * n);
    }
    try {
      const h = JSON.parse(actions.HTTP.sendHttpGetRequest(url, 20000)).hourly;
      const out = new Map();
      h.time.forEach((t, i) => {
        if (typeof h[field][i] === 'number') {
          out.set(t - 3600, h[field][i]);
        }
      });
      return out;
    } catch (e) {
      // asked again
    }
  }
  return null;
}
const irradiance = (host, range, azimuth) => series(host, range,
  `global_tilted_irradiance&tilt=${TILT}&azimuth=${azimuth}`, 'global_tilted_irradiance');
const temperatures = (host, range) => series(host, range, 'temperature_2m', 'temperature_2m');

function planes(host, range) {
  const out = {};
  for (const [plane, azimuth] of Object.entries(PLANES)) {
    out[plane] = irradiance(host, range, azimuth);
    if (out[plane] === null) {
      return null;
    }
  }
  return out;
}

// a module's power at an irradiance and the air's temperature against its power at 25 °C cell temperature (1 without
// a temperature)
const derate = (g, temp) => (temp === undefined || temp === null ? 1 : 1 + TEMPERATURE_COEFFICIENT * (temp + CELL_RISE * g - 25));
// a plane's modules times their irradiance at that temperature
const unit = (plane, g, temps, t) => MODULES[plane] * g[plane].get(t) * derate(g[plane].get(t), temps ? temps.get(t) : null);

// the factors from the last FIT_DAYS whole days, or null: per string one factor, its energy over those days against
// its modules' irradiance at their temperature, a ratio of sums, which leaves the total unbiased
function fit() {
  const today = time.toZDT('00:00');
  const first = today.minusDays(FIT_DAYS);
  const day = (z) => z.toLocalDate().toString();
  const range = `start_date=${day(first)}&end_date=${day(today.minusDays(1))}`;
  const g = planes('historical-forecast-api.open-meteo.com', range);
  const temps = temperatures('historical-forecast-api.open-meteo.com', range);
  if (g === null || temps === null) {
    return null;
  }
  const string1 = items.getItem('huawei_inverter_pv1_power');
  const string2 = items.getItem('huawei_inverter_pv2_power');
  let hours = 0, daylight = 0;
  const records = [];  // [day, local hour of the day, string 1's power, its modules' irradiance, string 2's, its]
  for (let d = 0; d < FIT_DAYS; d++) {
    for (let hour = 0; hour < 24; hour++) {
      const begin = first.plusDays(d).plusHours(hour);
      const t = begin.toEpochSecond();
      if (!g.east.has(t) || !g.west.has(t) || !g.north.has(t) || !temps.has(t)) {
        continue;
      }
      const x1 = unit('east', g, temps, t);
      const x2 = unit('west', g, temps, t) + unit('north', g, temps, t);
      if (x1 + x2 <= 0) {
        continue;  // night
      }
      daylight++;
      const end = begin.plusHours(1);
      const p1 = string1.persistence.averageBetween(begin, end, 'influxdb');
      const p2 = string2.persistence.averageBetween(begin, end, 'influxdb');
      if (p1 === null || p2 === null || p1.numericState === null || p2.numericState === null) {
        continue;
      }
      records.push([d, begin.hour(), p1.numericState, x1, p2.numericState, x2]);
      hours++;
    }
  }
  // the clear days: the strings' day and the forecast's both near the window's best
  const days = {};
  for (const [d, , a, x, b, y] of records) {
    const sums = days[d] || (days[d] = [0, 0]);
    sums[0] += a + b; sums[1] += x + y;
  }
  const best = Object.values(days).reduce(([m, f], [a, x]) => [Math.max(m, a), Math.max(f, x)], [0, 0]);
  const clear = Object.keys(days).map(Number)
    .filter((d) => days[d][0] >= CLEAR * best[0] && days[d][1] >= CLEAR * best[1]);
  const used = clear.length >= CLEAR_DAYS ? records.filter(([d]) => clear.includes(d)) : records;
  let m1 = 0, m2 = 0, u1 = 0, u2 = 0;
  const byHour = {};  // the local hour of the day: [string 1's energy, its irradiance, string 2's, its]
  for (const [, h, a, x, b, y] of used) {
    m1 += a; u1 += x; m2 += b; u2 += y;
    const sums = byHour[h] || (byHour[h] = [0, 0, 0, 0]);
    sums[0] += a; sums[1] += x; sums[2] += b; sums[3] += y;
  }
  // at least half the daylight hours, with sun enough: as much as 10 hours of 500 W/m² on the west plane
  if (hours < daylight / 2 || u2 < 10 * 500 * MODULES.west) {
    return null;
  }
  const s1 = m1 / u1;
  const s2 = m2 / u2;
  if (!(s1 > 0) || !(s2 > 0)) {
    return null;
  }
  const round = (v) => Math.round(v * 100) / 100;
  // each hour of the day its own factor where its irradiance makes at least a twentieth of a mean hour's (of 12), at
  // most HOUR_CAP times the day's, then with its neighbours' weighted by their irradiance; else none, and the day's
  // stands
  const own = (i) => {
    const day = i === 0 ? s1 : s2;
    const raw = [...Array(24).keys()].map((h) => {
      const sums = byHour[h];
      return sums && sums[i + 1] > 0.05 * (i === 0 ? u1 : u2) / 12 ? Math.min(sums[i] / sums[i + 1], HOUR_CAP * day) : null;
    });
    return raw.map((v, h) => {
      if (v === null) {
        return null;
      }
      let num = 0, den = 0;
      for (const k of [h - 1, h, h + 1]) {
        if (k >= 0 && k < 24 && raw[k] !== null) {
          num += raw[k] * byHour[k][i + 1]; den += byHour[k][i + 1];
        }
      }
      return Math.round(num / den * 1000) / 1000;
    });
  };
  return { east: round(MODULES.east * s1), west: round(MODULES.west * s2), north: round(MODULES.north * s2),
    hourly: { s1: own(0), s2: own(2) }, clear: clear.length >= CLEAR_DAYS ? clear.length : 0, at: Math.round(now / 1000),
    model: MODEL };
}

// the last fit: this run's, the cache's, the item's (restored at startup), or the defaults
let previous = null;
try {
  previous = JSON.parse(hourly.state);
} catch (e) {
  previous = null;
}
let factors = store.get('factors')
  || (previous && previous.k ? { ...previous.k, hourly: previous.kh, at: previous.fit, model: previous.model } : null);
if (factors && factors.model !== MODEL) {
  factors = null;  // another model's, fitted anew below
}
const fittedToday = factors && factors.at
  && time.toZDT(new Date(factors.at * 1000)).toLocalDate().equals(time.toZDT().toLocalDate());
// once a day, after 1 h, when yesterday is complete in both
if (!fittedToday && time.toZDT().hour() >= 1) {
  const fresh = fit();
  if (fresh !== null) {
    console.info(`PV-Prognose: Faktoren Ost ${fresh.east}, West ${fresh.west}, Nord ${fresh.north} W je W/m²`
      + (fresh.clear ? ` aus ${fresh.clear} klaren Tagen` : ' aus allen 14 Tagen (zu wenig klare)')
      + (factors ? ` (vorher ${factors.east}, ${factors.west}, ${factors.north})` : ''));
    factors = fresh;
    store.put('factors', factors);
  } else if (!store.get('fitFailed')) {
    console.warn('PV-Prognose: Abgleich der Faktoren fehlgeschlagen, die bisherigen gelten weiter');
    store.put('fitFailed', true);
  }
  if (fresh !== null) {
    store.remove('fitFailed');
  }
}
if (factors === null) {
  factors = { ...DEFAULT, at: null, model: MODEL };
}

// the forecast of today and tomorrow
const g = planes('api.open-meteo.com', 'forecast_days=2');
if (g === null) {
  if (!store.get('failing')) {
    console.warn('PV-Prognose: Open-Meteo nicht erreichbar, die letzte Prognose gilt weiter');
    store.put('failing', true);
  }
} else {
  if (store.get('failing')) {
    console.info('PV-Prognose: Open-Meteo wieder erreichbar');
    store.remove('failing');
  }
  // the air's temperature for the cells' (without it, the power at 25 °C)
  const temps = temperatures('api.open-meteo.com', 'forecast_days=2');
  // a plane's factor per module at an hour: its string's for that hour of the day, else the day's
  const perModule = (p, t) => {
    const own = factors.hourly ? factors.hourly[STRING_OF[p]][time.toZDT(new Date(t * 1000)).hour()] : null;
    return own === null || own === undefined ? factors[p] / MODULES[p] : own;
  };
  const hours = [...g.east.keys()].filter((t) => g.west.has(t) && g.north.has(t)).sort((a, b) => a - b)
    .map((t) => [t, Math.round(Object.keys(PLANES).reduce((sum, p) => sum + perModule(p, t) * unit(p, g, temps, t), 0))]);
  hourly.postUpdate(JSON.stringify({ at: Math.round(now / 1000), fit: factors.at, model: MODEL,
    k: { east: factors.east, west: factors.west, north: factors.north }, kh: factors.hourly || null, h: hours }));
  // the series: each hour's mean at the hour's middle, only points that changed since the last write (equal
  // timestamps overwrite in InfluxDB)
  const sent = store.get('sent') || {};
  const series = new JTimeSeries(JTimeSeries.Policy.ADD);
  let n = 0;
  for (const [t, watts] of hours) {
    if (sent[t] === watts) {
      continue;
    }
    series.add(JInstant.ofEpochSecond(t + 1800), new QuantityType(`${watts} W`));
    sent[t] = watts;
    n++;
  }
  if (n > 0) {
    Persistence.persist(items.getItem('pv_forecast_power').rawItem, series, 'influxdb');
  }
  // each day's total from today on (the first hour, yesterday's last, belongs to a day the rule no longer writes), at
  // the day's 23:59:59, only totals that changed; the item holds today's
  const todayEnd = time.toZDT('23:59:59').withNano(0).toEpochSecond();
  const days = new Map();
  for (const [t, watts] of hours) {
    const end = time.toZDT(new Date(t * 1000)).withHour(23).withMinute(59).withSecond(59).withNano(0).toEpochSecond();
    if (end >= todayEnd) {
      days.set(end, (days.get(end) || 0) + watts / 1000);
    }
  }
  const daily = new JTimeSeries(JTimeSeries.Policy.ADD);
  let m = 0;
  for (const [end, kwh] of days) {
    const value = Math.round(kwh * 100) / 100;
    if (sent[`d${end}`] !== value) {
      daily.add(JInstant.ofEpochSecond(end), new QuantityType(`${value} kWh`));
      sent[`d${end}`] = value;
      m++;
    }
  }
  if (m > 0) {
    Persistence.persist(items.getItem('pv_forecast_energy').rawItem, daily, 'influxdb');
  }
  // today's total and tomorrow's as states, for the PV page's tile
  [['pv_forecast_energy', todayEnd], ['pv_forecast_energy_tomorrow', todayEnd + 86400]].forEach(([name, end]) => {
    const key = [...days.keys()].find((k) => Math.abs(k - end) <= 3600);  // a day of 23 or 25 hours
    if (key !== undefined) {
      const energy = items.getItem(name);
      const value = Math.round(days.get(key) * 100) / 100;
      if (energy.numericState !== value) {
        energy.postUpdate(`${value} kWh`);
      }
    }
  });
  for (const t of Object.keys(sent)) {
    if (Number(String(t).replace('d', '')) * 1000 < now - 86400000) {
      delete sent[t];
    }
  }
  store.put('sent', sent);
  // the running hour's value at once, not only at the next hour the forecast persistence sets
  const current = hours.find(([t]) => t * 1000 <= now && now < (t + 3600) * 1000);
  const power = items.getItem('pv_forecast_power');
  const value = current ? `${current[1]} W` : 'UNDEF';
  if (power.state !== value) {
    power.postUpdate(value);
  }
}
