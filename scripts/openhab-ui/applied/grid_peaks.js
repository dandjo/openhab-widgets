// the grid's strongest quarter-hours by month (user, 2026-11-02): the grid operator charges for a month's strongest
// quarter-hour mean of the import, and the user wants to see which consumers cause it. For each of the last 6 months,
// the running one first, its 7 strongest days by their strongest quarter-hour, each with what the consumers drew then,
// as JSON in grid_peaks for the Stromzähler page; a month's strongest day holds its peak. The quarters are InfluxDB's
// 15-minute means of the meter's power: its import counter was stored only every 15 minutes in some months, which
// would smear a peak over two quarters. A finished month never changes, it comes from the item's last JSON (restored
// after a restart); the running month is worked out on every run, a quarter's breakdown it had before taken over.
// Every finished month since the record began (October 2024) goes once into the InfluxDB measurement
// grid_peak_months (user, 2026-11-02: to trace them back beyond the page's 6 months), one point per month at its
// start with its key as the tag m, its peak (kw, t) and its 7 days as JSON; months the run did not work out anyway are
// added at most ARCHIVE_PER_RUN a run, so the first runs fill the past in steps. No item may carry the measurement's
// name: the nightly downsampler leaves only measurements without one alone. The whole archive goes into the String
// item grid_peaks_archive too, in the form of grid_peaks, for the page's older months (user, 2026-11-02).
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
const ARCHIVE = 'grid_peak_months';
const ARCHIVE_FROM = new Date(2024, 9, 1);  // the first whole month of the meter's record (October 2024)
const ARCHIVE_PER_RUN = 3;
const ARCHIVE_ITEM = 'grid_peaks_archive';
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
const monthKey = (ms) => { const d = new Date(ms); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`; };

// a month's 7 strongest days with their breakdowns, strongest first
function monthDays(parts, from, to, now) {
  return strongestDays(from, to, now, DAYS).map((q) => Object.assign({t: q[0], kw: round(q[1])},
    breakdown(parts, q[0])));
}

// the finished months the archive lacks, newest first: those of this run's months as they are, older ones worked out,
// at most ARCHIVE_PER_RUN a run; a month without a record is written empty, so it is not looked for again. Returns
// what it wrote, by month.
function archive(months, parts, today, now) {
  const written = {};
  const tags = query(`SHOW TAG VALUES FROM "${ARCHIVE}" WITH KEY = "m"`)[0];
  const have = {};
  (tags ? tags.values : []).forEach((v) => { have[v[1]] = true; });
  const known = {};
  months.forEach((m) => { known[m.m] = m; });
  let worked = 0;
  for (let k = 1; ; k++) {
    const from = new Date(today.getFullYear(), today.getMonth() - k, 1).getTime();
    if (from < ARCHIVE_FROM.getTime()) {
      break;
    }
    const key = monthKey(from);
    if (have[key]) {
      continue;
    }
    let days = known[key] ? known[key].d : null;
    if (!days) {
      if (worked >= ARCHIVE_PER_RUN) {
        continue;
      }
      worked++;
      days = monthDays(parts, from, new Date(today.getFullYear(), today.getMonth() - k + 1, 1).getTime(), now);
    }
    const json = JSON.stringify(days).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
    const peak = days[0];
    const line = `${ARCHIVE},m=${key} kw=${peak ? peak.kw : 0},t=${peak ? peak.t : 0}i,days="${json}" ${from}`;
    const answer = actions.HTTP.sendHttpPostRequest(`${INFLUX}/write?db=openhab&precision=ms`, 'text/plain', line,
      10000);
    if (answer === null || answer === undefined || String(answer).indexOf('"error"') >= 0) {
      throw new Error(`the archive did not take ${key}`);
    }
    written[key] = days;
  }
  return written;
}

// the whole archive (and what this run wrote into it) into ARCHIVE_ITEM, newest first, months without a record left
// out; written only when it changed, about once a month
function publishArchive(written) {
  const series = query(`SELECT days FROM "${ARCHIVE}"`)[0];
  const byMonth = {};
  (series ? series.values : []).forEach((v) => {
    try {
      byMonth[monthKey(v[0])] = JSON.parse(v[1]);
    } catch (e) {
      // a broken point is left out
    }
  });
  Object.keys(written).forEach((key) => { byMonth[key] = written[key]; });
  const months = Object.keys(byMonth).sort().reverse().filter((key) => byMonth[key].length)
    .map((key) => ({m: key, max: round(Math.max(...byMonth[key].map(draw))), d: byMonth[key]}));
  const text = JSON.stringify({max: round(Math.max(0, ...months.map((m) => draw(m.d[0])))), months});
  if (items.getItem(ARCHIVE_ITEM).state !== text) {
    items.getItem(ARCHIVE_ITEM).postUpdate(text);
  }
}

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
    const days = monthDays(parts, from, to, now);
    if (days.length) {
      months.push({m: key, cur: k === 0, max: round(Math.max(...days.map(draw))), d: days});
    }
  }
  publishArchive(archive(months, parts, today, now));
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
