// day heating (user, 2026-10-13): in the transition season the house needs less heat at night than the heat pump gives
// at its lowest speed, so it cycles however long its pauses are; the same heat given in a day window, with the leaving
// water offset a little higher (+2 K by default), is enough load for long runs, and the house's mass carries it through
// the night, during which the rule keeps the heating off (offset −10 K: the setpoint stays at its minimum of 20 °C, so
// the controller never calls for heat). The season is decided once a day (user, 2026-10-25): the 24-hour mean outdoor
// temperature, the heating curve's basis, at the window's start makes that day and the night after it day mode from
// SEASON_AVG on, and normal operation below it until the next window's start. The mean swings by about 2 K within a
// day, so a threshold checked all the time would switch back and forth on days around it; one decision a day never
// does. The mean at the window's start comes from InfluxDB, so a restart keeps the day's decision. In day mode the
// offset is the rule's: it sets it again whenever it differs, so a change by hand needs the switch off. Only the cycle
// guard lowers it for a while in the window, after a hot-water charge or a short run (user, 2026-10-13: a hot
// compressor's start ends within minutes); the rule waits for its lock to go, and at night the guard leaves its lock to
// the rule as it stands. In normal operation the offset goes back to 0 once and the cycle guard works as before.
// Offset, start and end of the window are items, so they can be changed without touching the rule.
// back to 8 °C since 2026-10-30 (user): the trial at 6 °C (from 2026-10-26) let the rooms fall about 0.5 K on the
// cold days (27./28.10.: mornings 22.2 °C in the living room), at 8 to 9 °C the window held them within 0.1 K a day
const SEASON_AVG = 8;    // °C 24-hour mean outdoors at the window's start from which the day is in day mode
const NIGHT = -10;       // K offset outside the window: the setpoint at its minimum, no call for heat
const SETTLE = 60;       // seconds after a write or a change of the guard's lock before the offset is checked, and
                         // written again if it still differs
const OFFSET_MIN = -10;  // the controller's offset range is −10..+10
const OFFSET_MAX = 10;

const SWITCH = 'heatpump_day_heating';
const STATE = 'heatpump_day_heating_state';
const AVG = 'espaltherma_ext_ambient_temp_avg';
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
const enabled = state(SWITCH) === 'ON' && state('pyaltherma_climate_control_power') === 'ON';
// while the offset is missing (NULL after a restart) it would compare as 0, so nothing is written on it
const missing = offset === null;

// the season, decided at the latest window start: today's once it has come, before that yesterday's
const previous = state(STATE);
const wasDay = previous === 'day' || previous === 'night';
const decidedAt = clock.withHour(Math.floor(start) % 24).withMinute(Math.min(59, Math.round((start % 1) * 60)))
  .withSecond(0).withNano(0).minusDays(hour >= start ? 0 : 1);
let decision = cache.private.get('decision');
if (decision === null || decision.at !== decidedAt.toString()) {
  const persisted = items.getItem(AVG).persistence.persistedState(decidedAt, 'influxdb');
  decision = { at: decidedAt.toString(), mean: persisted === null ? null : persisted.numericState };
  if (decision.mean !== null) {
    cache.private.put('decision', decision);
    console.info(`day heating: 24-hour mean ${decision.mean} °C at the window's start ${decision.at}, ` +
      (decision.mean >= SEASON_AVG ? 'day mode' : 'normal operation') + ' until the next one');
  }
}
// without a reading at the window's start (InfluxDB away) the mode stays as it is
const season = decision.mean !== null ? decision.mean >= SEASON_AVG : wasDay;
const inWindow = start <= end ? hour >= start && hour < end : hour >= start || hour < end;
const phase = !enabled ? 'off' : !season ? 'normal' : inWindow ? 'day' : 'night';

const write = (value, why) => {
  // in °C like the item: a quantity in K would be taken as an absolute temperature (−272.15 °C)
  offsetItem.sendCommand(Quantity(value + ' °C'));
  cache.private.put('write', now);
  console.info(`day heating: offset ${offset} -> ${value}, ${why}`);
};
if (phase !== previous) {
  items.getItem(STATE).postUpdate(phase);
  console.info(`day heating: ${previous} -> ${phase}` +
    (decision.mean !== null ? `, 24-hour mean ${decision.mean} °C at the window's start` : ''));
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
