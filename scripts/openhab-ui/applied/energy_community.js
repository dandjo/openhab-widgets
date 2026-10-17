// The house's energy community (WiEnergy): the public forecast and signal, static files the operator regenerates
// every hour (API stage 1). Balance, production and consumption go into InfluxDB as a forecast series per quarter hour;
// the running quarter hour's level and certainty and the next surplus window go into plain items. No control here.
// the community's id is set by the applier (energy_community.py) from ~/.config/energy-community.json
const BASE = 'https://eeg-wienergy.at/make/api/v1/public/communities/__COMMUNITY__';
const P = 'energy_community_';
const SERIES = { balance: 'balanceW', production: 'productionW', consumption: 'consumptionW' };
const JTimeSeries = Java.type('org.openhab.core.types.TimeSeries');
const JInstant = Java.type('java.time.Instant');
const QuantityType = Java.type('org.openhab.core.library.types.QuantityType');
const Persistence = Java.type('org.openhab.core.persistence.extensions.PersistenceExtensions');
const store = cache.private;
const now = Date.now();

function fetchJson(name) {
  const body = actions.HTTP.sendHttpGetRequest(`${BASE}/${name}.json`, 15000);
  if (body === null || body === undefined || body === '') {
    return null;
  }
  try {
    return JSON.parse(body);
  } catch (e) {
    return null;
  }
}

function post(suffix, value) {
  const item = items.getItem(P + suffix);
  if (item.state !== String(value)) {
    item.postUpdate(value);
  }
}

// the file of this run, or the last good one while the site does not answer
function load(name) {
  const fresh = fetchJson(name);
  if (fresh !== null) {
    store.put(name, fresh);
    if (store.get('failing')) {
      console.info('EEG: WiEnergy wieder erreichbar');
      store.remove('failing');
    }
    return fresh;
  }
  if (!store.get('failing')) {
    console.warn('EEG: WiEnergy nicht erreichbar, die letzten Werte gelten bis zu ihrem Ablauf');
    store.put('failing', true);
  }
  return store.get(name) || null;
}

const covers = (v) => Date.parse(v.start) <= now && now < Date.parse(v.end);

// 1. The series. Only points whose value changed since the last write are stored, so the hourly regeneration does
//    not rewrite three days of points; equal timestamps overwrite in InfluxDB, so ADD is enough and REPLACE (which
//    InfluxDB 1.x cannot honour, it only logs a warning per series) is not needed.
const forecast = load('forecast');
if (forecast !== null && Array.isArray(forecast.values)) {
  const sent = store.get('sent') || {};
  for (const [suffix, key] of Object.entries(SERIES)) {
    const series = new JTimeSeries(JTimeSeries.Policy.ADD);
    let n = 0;
    for (const v of forecast.values) {
      if (v.quality === 'unavailable' || v.confidence === 'unavailable' || typeof v[key] !== 'number') {
        continue;
      }
      const watts = Math.round(v[key]);
      const id = `${suffix}@${v.start}`;
      if (sent[id] === watts) {
        continue;
      }
      series.add(JInstant.ofEpochMilli(Date.parse(v.start)), new QuantityType(`${watts} W`));
      sent[id] = watts;
      n++;
    }
    if (n > 0) {
      Persistence.persist(items.getItem(P + suffix).rawItem, series, 'influxdb');
    }
  }
  // what lies more than a day back is never sent again
  for (const id of Object.keys(sent)) {
    if (Date.parse(id.split('@')[1]) < now - 86400000) {
      delete sent[id];
    }
  }
  store.put('sent', sent);
  // the running quarter hour's values at once, not only at the next slot the forecast persistence sets
  const current = forecast.values.find(covers);
  for (const [suffix, key] of Object.entries(SERIES)) {
    const ok = current && current.quality !== 'unavailable' && current.confidence !== 'unavailable'
      && typeof current[key] === 'number';
    post(suffix, ok ? `${Math.round(current[key])} W` : 'UNDEF');
  }
}

// 2. The signal: the quarter hour that is running now (the file's own `current` is the one at generation time), never
//    after the file's expiry, and the next surplus window that has not ended yet.
const signal = load('signal');
const valid = signal !== null && now < Date.parse(signal.expiresAt);
const interval = valid && Array.isArray(signal.intervals) ? signal.intervals.find(covers) : undefined;
if (interval && interval.confidence !== 'unavailable') {
  post('level', interval.level);
  post('certainty', interval.certainty);
} else {
  post('level', valid ? 'unavailable' : 'UNDEF');
  post('certainty', 'UNDEF');
}
const next = valid && Array.isArray(signal.windows)
  ? signal.windows.filter((w) => Date.parse(w.end) > now).sort((a, b) => Date.parse(a.start) - Date.parse(b.start))[0]
  : undefined;
if (next) {
  post('window_start', next.start);
  post('window_end', next.end);
  post('window_energy', `${Math.round(next.expectedSurplusKwh * 10) / 10} kWh`);
  post('window_certainty', next.certainty);
} else {
  for (const s of ['window_start', 'window_end', 'window_energy', 'window_certainty']) {
    post(s, 'UNDEF');
  }
}
