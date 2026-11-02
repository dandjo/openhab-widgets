// the grid's strongest quarter-hours by month (user, 2026-11-02): the grid operator charges for a month's strongest
// quarter-hour mean of the import, and the user wants to see which consumers cause it. For each of the last 6 months,
// the running one first, its 7 strongest days by their strongest quarter-hour, each with what the consumers drew then,
// as JSON in grid_peaks for the Stromzähler page; a month's strongest day holds its peak. The quarters are InfluxDB's
// 15-minute means of the meter's power: its import counter was stored only every 15 minutes in some months, which
// would smear a peak over two quarters. A finished month never changes, it comes from the item's last JSON (restored
// after a restart); the running month is worked out on every run, a quarter's breakdown it had before taken over.
const GROUPS = __GROUPS__;  // [[name, [power items]], ...] from the UI generator (PEAK_GROUPS in dashboard.py)
const GRID = 'huawei_inverter_power_meter_active_power';  // positive while it imports
const HOME = 'home_active_power';
const PV = 'huawei_inverter_input_power';
const BATTERY = 'huawei_inverter_energy_storage_power';  // positive while it gives, negative while it charges
const ITEM = 'grid_peaks';
const INFLUX = 'http://127.0.0.1:8086';
const Q = 15 * 60000;
const MONTHS = 6;
const DAYS = 7;
const BEFORE = 20 * 60000;  // read before a quarter too: an item stored only on change has its value from then
const store = cache.private;
const round = (x) => Math.round(x * 100) / 100;
const pad = (n) => (n < 10 ? '0' : '') + n;

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

// the n strongest days of [from, to) by their strongest finished quarter (of two alike the earlier), strongest first
function strongestDays(from, to, now, n) {
  const series = query(`SELECT mean(value) FROM "${GRID}" WHERE time >= ${from}ms AND time < ${to}ms ` +
    'GROUP BY time(15m) fill(none)')[0];
  const best = {};
  (series ? series.values : []).forEach((v) => {
    if (v[1] === null || v[0] + Q > now) {
      return;
    }
    const d = new Date(v[0]);
    const day = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
    if (!best[day] || v[1] / 1000 > best[day][1]) {
      best[day] = [v[0], v[1] / 1000];
    }
  });
  return Object.keys(best).map((k) => best[k]).sort((a, b) => b[1] - a[1] || a[0] - b[0]).slice(0, n);
}

// what the house drew in a quarter by consumer (kW), PV's power and the battery's discharge then
function breakdown(parts, t) {
  if (parts[t]) {
    return parts[t];
  }
  const names = [];
  GROUPS.forEach((g) => g[1].forEach((n) => { if (!names.includes(n)) { names.push(n); } }));
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

const draw = (d) => d.p.reduce((a, c) => a + c[1], 0);

try {
  const now = Date.now();
  const today = new Date(now);
  // the months of the last run, and their quarters' breakdowns
  const previous = {};
  const parts = store.get('parts', () => ({}));
  const last = items.getItem(ITEM).state;
  if (last && last.charAt(0) === '{') {
    (JSON.parse(last).months || []).forEach((m) => {
      previous[m.m] = m;
      m.d.forEach((d) => { if (!parts[d.t]) { parts[d.t] = {pv: d.pv, out: d.out, p: d.p}; } });
    });
  }
  const months = [];
  for (let k = 0; k < MONTHS; k++) {
    const from = new Date(today.getFullYear(), today.getMonth() - k, 1).getTime();
    const to = new Date(today.getFullYear(), today.getMonth() - k + 1, 1).getTime();
    const start = new Date(from);
    const key = `${start.getFullYear()}-${pad(start.getMonth() + 1)}`;
    if (k > 0 && previous[key] && !previous[key].cur) {
      months.push(previous[key]);
      continue;
    }
    const days = strongestDays(from, to, now, DAYS).map((q) => Object.assign({t: q[0], kw: round(q[1])},
      breakdown(parts, q[0])));
    if (days.length) {
      months.push({m: key, cur: k === 0, max: round(Math.max(...days.map(draw))), d: days});
    }
  }
  const kept = {};
  months.forEach((m) => m.d.forEach((d) => { kept[d.t] = true; }));
  Object.keys(parts).forEach((t) => { if (!kept[t]) { delete parts[t]; } });
  const max = round(Math.max(0, ...months.map((m) => draw(m.d[0]))));
  items.getItem(ITEM).postUpdate(JSON.stringify({at: now, max, months}));
  store.remove('failed');
} catch (e) {
  if (!store.get('failed')) {
    console.warn(`grid_peaks: ${e}`);
    store.put('failed', true);
  }
}
