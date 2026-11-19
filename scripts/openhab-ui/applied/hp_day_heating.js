// day heating (user, 2026-10-13): in the transition season the house needs less heat at night than the heat pump gives
// at its lowest speed, so it cycles however long its pauses are; the same heat given in a day window, with the leaving
// water offset a little higher (+2 K by default), is enough load for long runs, and the house's mass carries it through
// the night, during which the rule keeps the heating off (offset −10 K: the setpoint stays at its minimum of 20 °C, so
// the controller never calls for heat). The season is decided at two fixed points (user, 2026-10-25), the window's
// start for the window and its end for the night after it (user, 2026-11-19, after a night in normal operation that
// cycled while the mean had passed 8 °C by noon), by the weather forecast's mean of the 24 hours from the point (user,
// 2026-11-19): from SEASON_AVG on the window or the night is day mode, below it normal operation until the next point.
// Replayed over two heating seasons (1171 points) against the heat pump's own reading of the 24 hours that followed,
// a forecast a day old decided wrongly by 1 K or more twice, the 24-hour mean behind the point (the heating curve's
// basis, the rule's measure until then) 48 times. The heat pump's sensor reads FORECAST_OFFSET warmer than the models
// over a day, so that is added. Without a fresh forecast for the 24 hours the mean behind the point decides, from
// InfluxDB. A threshold checked all the time would switch back and forth on days around it; two fixed points never do
// within a window or a night. The decision is kept in DECISION, which MapDB restores, so a restart keeps it.
// In day mode the offset is the rule's: it sets it again whenever it differs, so a change by hand needs the switch off.
// Only the cycle guard lowers it for a while in the window, after a hot-water charge or a short run (user, 2026-10-13:
// a hot compressor's start ends within minutes); the rule waits for its lock to go, and at night the guard leaves its
// lock to the rule as it stands. In normal operation the offset goes back to 0 once and the cycle guard works as
// before. Offset, start and end of the window are items, so they can be changed without touching the rule. Switched off
// alone, while the rest of the heat pump's automation stays on, day heating pauses until the next window's start.
// back to 8 °C since 2026-10-30 (user): the trial at 6 °C (from 2026-10-26) let the rooms fall about 0.5 K on the
// cold days (27./28.10.: mornings 22.2 °C in the living room), at 8 to 9 °C the window held them within 0.1 K a day
const SEASON_AVG = 8;    // °C 24-hour mean outdoors at a decision point from which the window or night is day mode
const FORECAST_OFFSET = 0.8;  // K the heat pump's outdoor sensor reads above the forecast over a day (0.8 to 1.0 K in
                              // two seasons, Open-Meteo's best match and ECMWF alike)
const FRESH = 2;         // hours: an older forecast is not used (the weather rule renews it every 30 minutes)
const NIGHT = -10;       // K offset outside the window: the setpoint at its minimum, no call for heat
const SETTLE = 60;       // seconds after a write or a change of the guard's lock before the offset is checked, and
                         // written again if it still differs
const OFFSET_MIN = -10;  // the controller's offset range is −10..+10
const OFFSET_MAX = 10;

const SWITCH = 'heatpump_day_heating';
const AUTOMATIK = 'heatpump_management';  // the group of the heat pump's automations, OR: on while one of them is
const STATE = 'heatpump_day_heating_state';
const AVG = 'espaltherma_ext_ambient_temp_avg';
const DECISION = 'heatpump_day_heating_decision';  // JSON: {at, source: forecast or mean, forecast (°C, raw), mean}
const HOURLY = 'weather_hourly';  // [[epoch seconds, °C, ...], ...] hourly from the running hour, 61 hours
const offsetItem = items.getItem('pyaltherma_leaving_water_temp_offset_heating');
const num = (name) => items.getItem(name).numericState;
const state = (name) => items.getItem(name).state;
const now = Date.now();
const clock = time.ZonedDateTime.now();
const hour = clock.hour() + clock.minute() / 60;

const offset = num('pyaltherma_leaving_water_temp_offset_heating');
const lock = num('heatpump_cycle_lock') || 0;
const setting = (name, fallback, lo, hi) => {
  const v = num(name);
  return v === null || Number.isNaN(v) ? fallback : Math.min(hi, Math.max(lo, v));
};
// the controller takes the offset in whole kelvins only
const dayOffset = Math.round(setting('heatpump_day_heating_offset', 2, OFFSET_MIN, OFFSET_MAX));
const start = setting('heatpump_day_heating_start', 9, 0, 24);
const end = setting('heatpump_day_heating_end', 19, 0, 24);
// while the offset is missing (NULL after a restart) it would compare as 0, so nothing is written on it
const missing = offset === null;

// the season, decided at the latest decision point: the window's start for the window, its end for the night after
// it, each today's once it has come, before that yesterday's
const previous = state(STATE);
const wasDay = previous === 'day' || previous === 'night';
const point = (h) => clock.withHour(Math.floor(h) % 24).withMinute(Math.min(59, Math.round((h % 1) * 60)))
  .withSecond(0).withNano(0).minusDays(hour >= h ? 0 : 1);
const windowStart = point(start);
const nightStart = point(end);
const atNight = windowStart.isBefore(nightStart);
const decidedAt = atNight ? nightStart : windowStart;
const where = atNight ? "the night's start" : "the window's start";
// a pause (user, 2026-10-30: "Pause bis 9 Uhr"): the switch off alone, while another of Automatik's automations stays
// on (the group, OR, reads ON), gives normal operation round the clock until the next window start; once a window
// start lies after the moment it went off, the rule switches it on again. With all of them off (Automatik off) it
// stays off. Without a time of its last change (never changed since a restart) the pause ends, so it cannot hang on.
// The night's decision point does not end it.
let switchedOn = state(SWITCH) === 'ON';
if (!switchedOn && state(AUTOMATIK) === 'ON') {
  const off = items.getItem(SWITCH).lastStateChangeTimestamp;
  if (off === null || off.isBefore(windowStart)) {
    items.getItem(SWITCH).sendCommand('ON');
    switchedOn = true;
    console.info(`day heating: pause over at the window's start ${windowStart}, on again`);
  }
}
const enabled = switchedOn && state('pyaltherma_climate_control_power') === 'ON';
// the forecast's mean of the 24 hours from the point, if the forecast was renewed within FRESH hours and gives at least
// 23 of them, else null
const ahead = () => {
  const forecast = items.getItem(HOURLY);
  const updated = forecast.lastStateUpdateTimestamp;
  if (updated === null || now - updated.toInstant().toEpochMilli() > FRESH * 3600000) {
    return null;
  }
  let rows;
  try {
    rows = JSON.parse(forecast.state);
  } catch (e) {
    return null;
  }
  const from = decidedAt.toEpochSecond();
  const temps = (Array.isArray(rows) ? rows : [])
    .filter((r) => Array.isArray(r) && r[0] >= from && r[0] < from + 86400 && typeof r[1] === 'number')
    .map((r) => r[1]);
  return temps.length >= 23 ? temps.reduce((a, b) => a + b, 0) / temps.length : null;
};
const round = (v) => Math.round(v * 100) / 100;
// the decision at the point: the forecast plus FORECAST_OFFSET, else the 24-hour mean behind it, else null
const decide = () => {
  const forecast = ahead();
  if (forecast !== null) {
    return { at: decidedAt.toString(), source: 'forecast', forecast: round(forecast),
      mean: round(forecast + FORECAST_OFFSET) };
  }
  const persisted = items.getItem(AVG).persistence.persistedState(decidedAt, 'influxdb');
  return persisted === null ? null : { at: decidedAt.toString(), source: 'mean', mean: persisted.numericState };
};
const told = (d) => (d.source === 'forecast' ? `forecast ${d.mean} °C for the 24 hours from ${where}`
  : `24-hour mean ${d.mean} °C at ${where}`);
let decision;
try {
  decision = JSON.parse(state(DECISION));
} catch (e) {
  decision = null;
}
if (decision === null || typeof decision !== 'object' || decision.at !== decidedAt.toString()
    || typeof decision.mean !== 'number') {
  decision = decide();
  if (decision !== null) {
    items.getItem(DECISION).postUpdate(JSON.stringify(decision));
    console.info(`day heating: ${told(decision)} ${decision.at}` +
      (decision.source === 'forecast' ? ` (${decision.forecast} °C + ${FORECAST_OFFSET} K)` : ', no fresh forecast') +
      `, ${decision.mean >= SEASON_AVG ? (atNight ? 'night mode' : 'day mode') : 'normal operation'}` +
      ' until the next decision');
  }
}
// without a forecast and a reading at the decision point (InfluxDB away) the mode stays as it is
const season = decision !== null ? decision.mean >= SEASON_AVG : wasDay;
const inWindow = start <= end ? hour >= start && hour < end : hour >= start || hour < end;
const phase = !enabled ? 'off' : !season ? 'normal' : inWindow ? 'day' : 'night';

const write = (value, why) => {
  // a bare number: the item is a plain Number in K (user, 2026-11-01), which the MQTT channel takes in its °C, as a
  // difference; a quantity in K sent to a °C item would have been an absolute temperature (−272.15 °C)
  offsetItem.sendCommand(value);
  cache.private.put('write', now);
  console.info(`day heating: offset ${offset} -> ${value}, ${why}`);
};
if (phase !== previous) {
  items.getItem(STATE).postUpdate(phase);
  console.info(`day heating: ${previous} -> ${phase}` + (decision !== null ? `, ${told(decision)}` : ''));
}

const target = phase === 'day' ? dayOffset : phase === 'night' ? NIGHT : 0;
// the guard's release writes the offset itself, so the rule waits after a change of the lock as after its own write
if (cache.private.get('lockSeen') !== lock) {
  cache.private.put('lockSeen', lock);
  cache.private.put('lockChanged', now);
}
const settled = now - Math.max(cache.private.get('write') || 0, cache.private.get('lockChanged') || 0) >= SETTLE * 1000;
// leaving day mode: the offset goes back to 0 once, remembered until it has arrived, as the write may have to wait
if (phase === 'day' || phase === 'night') {
  cache.private.remove('release');
} else if (wasDay) {
  cache.private.put('release', true);
}
if (!missing && settled) {
  if (phase === 'day' || phase === 'night') {
    // the offset is the rule's: set again whenever it differs, once the cycle guard has let go of a lock
    if (lock === 0 && Math.abs(offset - target) > 0.25) {
      write(target, phase === 'day' ? `day window ${start}–${end} h` : 'outside the day window');
    }
  } else if (cache.private.get('release')) {
    // the offset back to 0, once; afterwards it belongs to the cycle guard and to hand settings
    if (Math.abs(offset) <= 0.25) {
      cache.private.remove('release');
    } else if (lock === 0) {
      write(0, phase === 'off' ? 'day heating off' : 'normal operation');
    }
  } else if (lock === 0 && Math.abs(offset - NIGHT) <= 0.25 && ['normal', 'off'].includes(previous)) {
    // the night's offset never belongs to normal operation (a release lost in a restart): back to 0
    write(0, 'night offset left over');
  }
}
