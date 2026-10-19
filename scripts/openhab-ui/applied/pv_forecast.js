// The house's own PV forecast (user, 2026-10-19): Open-Meteo's forecast of the irradiance on the three 25° planes of
// the modules, east (8 modules, string 1), west (8) and north (6, both string 2), weighted by factors fitted each day
// on the last 14 days of Open-Meteo's archived forecasts against the strings' power: string 1 by the east plane alone,
// string 2 by west and north, both on the afternoons (12 to 18 h) the hot water decides on, where a fit on the whole
// day came out too high (20 September to 18 October 2026, the afternoon from 13 to 18 h: 0.5 kWh off on average,
// 0.2 kWh too high, against 0.7 and 0.6 with the whole day). The hours of today and tomorrow go into
// pv_forecast_hourly (JSON, read by heatpump_dhw_management) and as a forecast series into pv_forecast_power, each
// hour's mean at its middle, so that the line through them lies over the measured power (the PV page draws both).
const LOCATION = 'latitude=LAT&longitude=LON&timezone=Europe%2FVienna&timeformat=unixtime';
const TILT = 25;
const PLANES = { east: -90, west: 90, north: 180 };
// W per W/m², fitted on 5 to 18 October 2026; used until the rule's own fit succeeds
const DEFAULT = { east: 3.15, west: 2.99, north: 0.98 };
const FIT_DAYS = 14;
const FIT_HOURS = [12, 18];  // the hours fitted, from 12 to 18 h
const TRIES = 3;
const Thread = Java.type('java.lang.Thread');
const JTimeSeries = Java.type('org.openhab.core.types.TimeSeries');
const JInstant = Java.type('java.time.Instant');
const QuantityType = Java.type('org.openhab.core.library.types.QuantityType');
const Persistence = Java.type('org.openhab.core.persistence.extensions.PersistenceExtensions');
const store = cache.private;
const hourly = items.getItem('pv_forecast_hourly');
const now = Date.now();

// one plane's irradiance by the hour's start (Open-Meteo gives an hour's mean at its end), or null; no answer, an
// error answer ({error: true, reason}: Open-Meteo's 503 while it is overloaded) or one without the data is asked
// again after 5 and 10 seconds, as the weather rule does
function irradiance(host, range, azimuth) {
  const url = `https://${host}/v1/forecast?${LOCATION}&${range}&hourly=global_tilted_irradiance`
    + `&tilt=${TILT}&azimuth=${azimuth}`;
  for (let n = 0; n < TRIES; n++) {
    if (n > 0) {
      Thread.sleep(5000 * n);
    }
    try {
      const h = JSON.parse(actions.HTTP.sendHttpGetRequest(url, 20000)).hourly;
      const out = new Map();
      h.time.forEach((t, i) => {
        if (typeof h.global_tilted_irradiance[i] === 'number') {
          out.set(t - 3600, h.global_tilted_irradiance[i]);
        }
      });
      return out;
    } catch (e) {
      // asked again
    }
  }
  return null;
}

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

// y = a x1 + b x2 with a and b not negative; one plane alone where both together would need a negative one
function fit2(rows) {
  let s11 = 0, s12 = 0, s22 = 0, s1y = 0, s2y = 0;
  for (const [x1, x2, y] of rows) {
    s11 += x1 * x1; s12 += x1 * x2; s22 += x2 * x2; s1y += x1 * y; s2y += x2 * y;
  }
  const det = s11 * s22 - s12 * s12;
  if (det > 0) {
    const a = (s1y * s22 - s2y * s12) / det;
    const b = (s2y * s11 - s1y * s12) / det;
    if (a >= 0 && b >= 0) {
      return [a, b];
    }
  }
  const a = s11 > 0 ? Math.max(0, s1y / s11) : 0;
  const b = s22 > 0 ? Math.max(0, s2y / s22) : 0;
  const err = (p, q) => rows.reduce((e, [x1, x2, y]) => e + (y - p * x1 - q * x2) ** 2, 0);
  return err(a, 0) <= err(0, b) ? [a, 0] : [0, b];
}

// the factors from the last FIT_DAYS whole days, or null
function fit() {
  const today = time.toZDT('00:00');
  const first = today.minusDays(FIT_DAYS);
  const day = (z) => z.toLocalDate().toString();
  const g = planes('historical-forecast-api.open-meteo.com',
    `start_date=${day(first)}&end_date=${day(today.minusDays(1))}`);
  if (g === null) {
    return null;
  }
  const string1 = items.getItem('huawei_inverter_pv1_power');
  const string2 = items.getItem('huawei_inverter_pv2_power');
  const rows1 = [];
  const rows2 = [];
  for (let d = 0; d < FIT_DAYS; d++) {
    for (let hour = FIT_HOURS[0]; hour < FIT_HOURS[1]; hour++) {
      const begin = first.plusDays(d).plusHours(hour);
      const t = begin.toEpochSecond();
      if (!g.east.has(t) || !g.west.has(t) || !g.north.has(t)) {
        continue;
      }
      const end = begin.plusHours(1);
      const p1 = string1.persistence.averageBetween(begin, end, 'influxdb');
      const p2 = string2.persistence.averageBetween(begin, end, 'influxdb');
      if (p1 === null || p2 === null || p1.numericState === null || p2.numericState === null) {
        continue;
      }
      rows1.push([g.east.get(t), 0, p1.numericState]);
      rows2.push([g.west.get(t), g.north.get(t), p2.numericState]);
    }
  }
  // at least half the hours, and sun in 20 of them (the west plane above 100 W/m²)
  const sunny = rows2.filter(([w]) => w > 100).length;
  if (rows1.length < FIT_DAYS * (FIT_HOURS[1] - FIT_HOURS[0]) / 2 || sunny < 20) {
    return null;
  }
  const [east] = fit2(rows1);
  const [west, north] = fit2(rows2);
  if (!(east > 0) || !(west + north > 0)) {
    return null;
  }
  const round = (v) => Math.round(v * 100) / 100;
  return { east: round(east), west: round(west), north: round(north), at: Math.round(now / 1000) };
}

// the last fit: this run's, the cache's, the item's (restored at startup), or the defaults
let previous = null;
try {
  previous = JSON.parse(hourly.state);
} catch (e) {
  previous = null;
}
let factors = store.get('factors')
  || (previous && previous.k ? { ...previous.k, at: previous.fit } : null);
const fittedToday = factors && factors.at
  && time.toZDT(new Date(factors.at * 1000)).toLocalDate().equals(time.toZDT().toLocalDate());
// once a day, after 1 h, when yesterday is complete in both
if (!fittedToday && time.toZDT().hour() >= 1) {
  const fresh = fit();
  if (fresh !== null) {
    console.info(`PV-Prognose: Faktoren Ost ${fresh.east}, West ${fresh.west}, Nord ${fresh.north} W je W/m²`
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
  factors = { ...DEFAULT, at: null };
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
  const hours = [...g.east.keys()].filter((t) => g.west.has(t) && g.north.has(t)).sort((a, b) => a - b)
    .map((t) => [t, Math.round(factors.east * g.east.get(t) + factors.west * g.west.get(t)
      + factors.north * g.north.get(t))]);
  hourly.postUpdate(JSON.stringify({ at: Math.round(now / 1000), fit: factors.at,
    k: { east: factors.east, west: factors.west, north: factors.north }, h: hours }));
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
  for (const t of Object.keys(sent)) {
    if (Number(t) * 1000 < now - 86400000) {
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
