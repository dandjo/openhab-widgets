// the grid's strongest quarter-hours (user, 2026-11-02): the grid operator charges for the month's strongest
// quarter-hour mean of the import, and the user wants to know which consumers cause it. Per quarter the import energy
// from the meter's counter, interpolated at the quarter's bounds, so a gap in the record (Monday's backup stops
// openHAB at 4:00 for about 20 minutes) spreads over its quarters instead of piling into one; for the month's
// strongest and the 5 strongest of the last 7 days (events at least 45 minutes apart) what the consumers drew then,
// as JSON in grid_peaks for the Stromzähler page. Finished quarters never change: their import and breakdown stay in
// the rule's private cache, so a run reads only what is new.
const GROUPS = __GROUPS__;  // [[name, [power items]], ...] from the UI generator (PEAK_GROUPS in dashboard.py)
const COUNTER = 'huawei_inverter_power_meter_grid_consumption';  // the meter's import in kWh
const HOME = 'home_active_power';
const PV = 'huawei_inverter_input_power';
const BATTERY = 'huawei_inverter_energy_storage_power';  // positive while it gives, negative while it charges
const ITEM = 'grid_peaks';
const INFLUX = 'http://127.0.0.1:8086';
const Q = 15 * 60000;
const DAYS = 7;
const TOP = 5;
const APART = 30 * 60000;   // strong quarters closer than this, start to start, are one event
const BEFORE = 20 * 60000;  // read before a quarter too: an item stored only on change has its value from then
const MAX_KWH = 25;         // a quarter's import beyond this is a glitch of the counter
const store = cache.private;
const round = (x) => Math.round(x * 100) / 100;

function query(q) {
  const body = actions.HTTP.sendHttpGetRequest(`${INFLUX}/query?db=openhab&epoch=ms&q=${encodeURIComponent(q)}`, 30000);
  if (!body) {
    throw new Error('InfluxDB gave no answer');
  }
  const result = (JSON.parse(body).results || [])[0] || {};
  if (result.error) {
    throw new Error(result.error);
  }
  return result.series || [];
}

// each finished quarter's mean import in kW, by its start, from first on (the cache holds the ones before)
function importQuarters(kw, first, end) {
  const series = query(`SELECT value FROM "${COUNTER}" WHERE time >= ${first - 3600000}ms`)[0];
  const points = series ? series.values.filter((v) => v[1] !== null) : [];
  let i = 0;
  // the counter at a bound, linear between the readings around it; null without one after it yet
  const at = (bound) => {
    while (i + 1 < points.length && points[i + 1][0] <= bound) {
      i++;
    }
    if (i + 1 >= points.length || points[i][0] > bound) {
      return null;
    }
    const [t0, v0] = points[i];
    const [t1, v1] = points[i + 1];
    return v0 + (v1 - v0) * (bound - t0) / (t1 - t0);
  };
  let before = at(first);
  for (let bound = first; bound < end; bound += Q) {
    const after = at(bound + Q);
    if (before !== null && after !== null && after - before >= 0 && after - before < MAX_KWH) {
      kw[bound] = Math.round((after - before) * 4 * 1000) / 1000;
    }
    before = after;
  }
}

// the strongest n quarters, each at least APART from a stronger one; of two alike the earlier
function strongest(quarters, n) {
  const picked = [];
  quarters.slice().sort((a, b) => b[1] - a[1] || a[0] - b[0]).forEach((q) => {
    if (picked.length < n && picked.every((p) => Math.abs(p[0] - q[0]) > APART)) {
      picked.push(q);
    }
  });
  return picked;
}

// what the house drew in a quarter by consumer (kW), PV's power and the battery's discharge then
function breakdown(parts, t) {
  if (parts[t]) {
    return parts[t];
  }
  const names = [];
  GROUPS.forEach((g) => g[1].concat([]).forEach((n) => { if (!names.includes(n)) { names.push(n); } }));
  names.push(HOME, PV, BATTERY);
  const series = query(`SELECT mean(value) FROM ${names.map((n) => `"${n}"`).join(',')} WHERE time >= ` +
    `${t - BEFORE}ms AND time < ${t + Q}ms GROUP BY time(1m) fill(previous)`);
  const mean = {};
  series.forEach((s) => {
    const values = s.values.filter((v) => v[0] >= t && v[0] < t + Q && v[1] !== null).map((v) => v[1]);
    mean[s.name] = values.length ? values.reduce((a, b) => a + b, 0) / values.length / 1000 : 0;
  });
  const get = (n) => mean[n] || 0;
  const consumers = GROUPS.map((g) => [g[0], g[1].reduce((a, n) => a + get(n), 0)]);
  const metered = consumers.reduce((a, c) => a + c[1], 0);
  consumers.push(['Nicht gemessen', Math.max(0, get(HOME) - metered)]);
  consumers.push(['Akku laden', Math.max(0, -get(BATTERY))]);
  parts[t] = {pv: round(get(PV)), out: round(Math.max(0, get(BATTERY))),
              p: consumers.filter((c) => c[1] >= 0.05).map((c) => [c[0], round(c[1])]).sort((a, b) => b[1] - a[1])};
  return parts[t];
}

try {
  const now = Date.now();
  const end = Math.floor(now / Q) * Q;
  const today = new Date(now);
  const monthStart = new Date(today.getFullYear(), today.getMonth(), 1).getTime();
  const weekStart = end - DAYS * 86400000;
  const from = Math.min(weekStart, monthStart);
  const kw = store.get('quarters', () => ({}));
  const parts = store.get('parts', () => ({}));
  [kw, parts].forEach((m) => Object.keys(m).forEach((k) => { if (Number(k) < from) { delete m[k]; } }));
  let first = from;
  while (first < end && kw[first] !== undefined) {
    first += Q;
  }
  if (first < end) {
    importQuarters(kw, first, end);
  }
  const all = Object.keys(kw).map((k) => [Number(k), kw[k]]);
  const week = strongest(all.filter((q) => q[0] >= weekStart), TOP);
  const month = strongest(all.filter((q) => q[0] >= monthStart), 1)[0] || null;
  const row = (q, m) => Object.assign({t: q[0], kw: round(q[1]), m}, breakdown(parts, q[0]));
  const rows = [];
  if (month && !week.some((q) => q[0] === month[0])) {
    rows.push(row(month, true));
  }
  week.forEach((q) => rows.push(row(q, month !== null && q[0] === month[0])));
  const max = round(Math.max(0, ...rows.map((r) => r.p.reduce((a, c) => a + c[1], 0))));
  const text = JSON.stringify({at: now, month: month ? {t: month[0], kw: round(month[1])} : null, max, rows});
  if (items.getItem(ITEM).state !== text) {
    items.getItem(ITEM).postUpdate(text);
  }
  store.remove('failed');
} catch (e) {
  if (!store.get('failed')) {
    console.warn(`grid_peaks: ${e}`);
    store.put('failed', true);
  }
}
