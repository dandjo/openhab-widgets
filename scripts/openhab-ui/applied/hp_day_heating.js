// day heating (user, 2026-10-13): in the transition season the house needs less heat at night than the heat pump gives
// at its lowest speed, so it cycles however long its pauses are; the same heat given in a day window, with the leaving
// water offset a little higher (+1 K by default), is enough load for long runs, and the house's mass carries it through
// the night, during which the rule keeps the heating off (offset −10 K: the setpoint stays at its minimum of 20 °C, so
// the controller never calls for heat). Day mode while the 24-hour mean outdoor temperature, the heating curve's basis,
// is 10 °C or more, until it falls below 8 °C, or when the heating never reached its own stop in two whole windows in a
// row while running for at least 70 % of the window's time without hot-water charges (the window then gives the
// house too little; a day the house needs nothing has no stop either, but no heating); after that it comes back only once the 24-hour mean has risen 2 K
// above the value it ended at. A stop counts as the heating's own only after 10 minutes of space heating (the valve on
// the heating, so a hot-water charge and the short runs right after it never count), with the leaving water at its stop
// (2 K or more above the setpoint) and no restart within 3 minutes (a defrost). In day mode the offset is the rule's:
// it sets it again whenever it differs, so a change by hand needs the switch off; the cycle guard keeps out then. In
// normal operation the offset goes back to 0 once and the cycle guard takes over. Offset, start and end of the window
// are items, so they can be changed without touching the rule.
const ON_AVG = 10;       // °C 24-hour mean outdoors from which day mode starts
const OFF_AVG = 8;       // °C below which it ends
const RESUME_RISE = 2;   // K the 24-hour mean must rise above its value at a fallback before day mode returns
const NIGHT = -10;       // K offset outside the window: the setpoint at its minimum, no call for heat
const FULL_DAYS = 2;     // whole windows in a row without the heating's own stop that end day mode
const FULL_SHARE = 0.7;  // ... in which the heating also ran this share of the window's time without hot water
const SPACE_RUN = 10;    // minutes of space heating before a stop counts as the heating's own
const AT_STOP = 2;       // K above the setpoint the leaving water must have reached in the run's last 2 minutes
const RESTART = 3;       // minutes after a stop without a restart (a defrost restarts within 30–90 s)
const DEFROST_GAP = 5;   // minutes around a defrost in which a stop does not count
const SETTLE = 30;       // seconds after a write before the offset is checked
const RETRY = 5;         // minutes between writes once 3 quick ones did not arrive
const OFFSET_MIN = -10;  // the controller's offset range is −10..+10
const OFFSET_MAX = 10;

const SWITCH = 'heatpump_day_heating';
const STATE = 'heatpump_day_heating_state';
const FULL = 'heatpump_day_heating_full_days';
const RESUME = 'heatpump_day_heating_resume';
const offsetItem = items.getItem('pyaltherma_leaving_water_temp_offset_heating');
const num = (name) => items.getItem(name).numericState;
const state = (name) => items.getItem(name).state;
const now = Date.now();
const clock = time.ZonedDateTime.now();
const hour = clock.hour() + clock.minute() / 60;
const today = clock.toLocalDate().toString();

const avg = num('espaltherma_ext_ambient_temp_avg');
const offset = num('pyaltherma_leaving_water_temp_offset_heating');
const freq = num('espaltherma_inv_frequency');
const valve = state('espaltherma_3way_valve_mode');
const leaving = num('espaltherma_leaving_water_temp_after_buh');
const setpoint = num('espaltherma_leaving_water_setpoint');
const lock = num('heatpump_cycle_lock') || 0;
const setting = (name, fallback, lo, hi) => {
  const v = num(name);
  return v === null || Number.isNaN(v) ? fallback : Math.min(hi, Math.max(lo, v));
};
// the controller takes the offset in whole kelvins only
const dayOffset = Math.round(setting('heatpump_day_heating_offset', 1, OFFSET_MIN, OFFSET_MAX));
const start = setting('heatpump_day_heating_start', 9, 0, 24);
const end = setting('heatpump_day_heating_end', 19, 0, 24);
const enabled = state(SWITCH) === 'ON' && state('pyaltherma_climate_control_power') === 'ON';
// while a reading is missing (NULL after a restart) it would compare as 0, so nothing is decided on it
const missing = [offset, freq].some((v) => v === null) || ['NULL', 'UNDEF'].includes(valve);
if (state('espaltherma_defrost_operaton') === 'ON') {
  cache.private.put('defrost', now);
}
const defrostAt = cache.private.get('defrost') || 0;
// a stop near a defrost (from DEFROST_GAP minutes before it until now) is the defrost's, not the heating's
const nearDefrost = (at) => defrostAt >= at - DEFROST_GAP * 60000;

// the season: day mode from ON_AVG, kept down to OFF_AVG; after a fallback only from the value it waits for
const previous = state(STATE);
const wasDay = previous === 'day' || previous === 'night';
let resume = num(RESUME);
if (avg !== null && resume !== null && (avg < OFF_AVG || avg >= resume)) {
  // a cold spell ends the wait as the ordinary season boundary takes over; reaching the value ends it too
  items.getItem(RESUME).postUpdate('UNDEF');
  resume = null;
}
let season = avg === null ? wasDay : wasDay ? avg >= OFF_AVG : avg >= Math.max(ON_AVG, resume ?? -99);
const inWindow = start <= end ? hour >= start && hour < end : hour >= start || hour < end;

// the heating's own stops: a run remembers since when it heats the house (the valve on Space) and how far the leaving
// water rose above the setpoint in its last 2 minutes; a stop is decided RESTART minutes later
let run = cache.private.get('run') || null;
let stop = cache.private.get('stop') || null;
let win = cache.private.get('window') || null;
if (!missing) {
  if (freq > 0) {
    if (stop !== null && !stop.decided) {
      // restarted at once: a defrost or the controller's own restart, not a stop; the run goes on where it was
      stop.decided = true;
      stop.counts = false;
      run = run ?? stop.run ?? null;
      delete stop.run;
      cache.private.put('stop', stop);
    }
    if (run === null) {
      run = { start: now, space: null, rise: [] };
    }
    run.space = valve === 'Space' ? (run.space ?? now) : null;
    if (leaving !== null && setpoint !== null) {
      run.rise = run.rise.filter((r) => now - r[0] <= 120000).concat([[now, leaving - setpoint]]);
    }
    cache.private.put('run', run);
  } else if (run !== null) {
    const heated = run.space !== null && now - run.space >= SPACE_RUN * 60000;
    stop = { at: now, own: heated && run.rise.some((r) => r[1] >= AT_STOP), decided: false, counts: false, run };
    run = null;
    cache.private.remove('run');
    cache.private.put('stop', stop);
  }
  if (stop !== null && !stop.decided && freq === 0 && now - stop.at >= RESTART * 60000) {
    stop.decided = true;
    stop.counts = stop.own && !nearDefrost(stop.at);
    delete stop.run;
    cache.private.put('stop', stop);
  }
}
// a stop of today's window, decided or, at the window's end, still waiting for its restart check
const ownStop = (s) => s !== null && (s.decided ? s.counts : s.own && !nearDefrost(s.at));

let phase = !enabled ? 'off' : !season ? 'normal' : inWindow ? 'day' : 'night';
const fullItem = items.getItem(FULL);
let full = fullItem.numericState || 0;
if (phase === 'day' && previous !== 'day') {
  cache.private.put('dayFrom', now);
}
const dayFrom = cache.private.get('dayFrom') || now;
if (phase === 'day') {
  if (win === null || win.date !== today) {
    // a window counts only when the rule held it from its start (not after a restart, switching on or a season change)
    win = { date: today, whole: previous === 'night', stopped: false, heating: 0, dhw: 0, seen: now };
  }
  // the heating's and the tank's time in the window, between two runs of the rule (at most a minute counted)
  const step = Math.min(60000, Math.max(0, now - win.seen));
  if (!missing && freq > 0 && valve === 'Space') {
    win.heating += step;
  } else if (!missing && valve !== 'Space') {
    win.dhw += step;
  }
  win.seen = now;
  // during the window only decided stops count, so a defrost right after a stop is seen first
  if (stop !== null && stop.decided && stop.counts && stop.at >= dayFrom) {
    win.stopped = true;
  }
  cache.private.put('window', win);
} else if (previous === 'day' && win !== null && win.date === today && phase === 'night') {
  // the window's end: whether the heating reached its own stop in it
  if (ownStop(stop) && stop.at >= dayFrom) {
    win.stopped = true;
  }
  if (win.whole) {
    const free = Math.max(1, now - dayFrom - win.dhw);  // the window's time without hot water
    const share = win.heating / free;
    const ranThrough = !win.stopped && share >= FULL_SHARE;
    full = ranThrough ? full + 1 : 0;
    console.info(`day heating: window of ${today} ${win.stopped ? 'reached the heating\'s own stop' :
      ranThrough ? 'ran through without the heating\'s own stop' : 'had no stop but little heating'}, heating ` +
      `${Math.round(share * 100)} % of ${Math.round(free / 60000)} min without hot water (${full} in a row)`);
    if (full >= FULL_DAYS) {
      resume = Math.max(ON_AVG, Math.round(((avg ?? ON_AVG) + RESUME_RISE) * 10) / 10);
      items.getItem(RESUME).postUpdate(resume);
      console.info(`day heating: ${full} windows in a row without a stop, normal operation until the 24-hour mean ` +
        `reaches ${resume} °C`);
      full = 0;
      season = false;
      phase = 'normal';
    }
    fullItem.postUpdate(full);
  }
  cache.private.remove('window');
  win = null;
}
const write = (value, why) => {
  // in °C like the item: a quantity in K would be taken as an absolute temperature (−272.15 °C)
  offsetItem.sendCommand(Quantity(value + ' °C'));
  cache.private.put('write', now);
  cache.private.put('expected', value);
  console.info(`day heating: offset ${offset} -> ${value}, ${why}`);
};
if (phase !== previous) {
  items.getItem(STATE).postUpdate(phase);
  console.info(`day heating: ${previous} -> ${phase}` + (avg !== null ? `, 24-hour mean ${avg} °C` : ''));
  cache.private.remove('attempts');
}

const target = phase === 'day' ? dayOffset : phase === 'night' ? NIGHT : 0;
const settled = now - (cache.private.get('write') || 0) >= SETTLE * 1000;
if (!missing && settled) {
  if (phase === 'day' || phase === 'night') {
    // the offset is the rule's: set again whenever it differs, once the cycle guard has let go of a lock
    if (lock === 0 && Math.abs(offset - target) > 0.25) {
      const attempts = (cache.private.get('attempts') || 0) + 1;
      if (attempts <= 3 || now - (cache.private.get('write') || 0) >= RETRY * 60000) {
        write(target, phase === 'day' ? `day window ${start}–${end} h` : 'outside the day window');
        cache.private.put('attempts', attempts);
        if (attempts === 4) {
          console.warn(`day heating: offset writes do not arrive, trying every ${RETRY} min`);
        }
      }
    } else if (Math.abs(offset - target) <= 0.25) {
      cache.private.remove('attempts');
    }
  } else if (wasDay || cache.private.get('release')) {
    // leaving day mode: the offset back to 0, once; afterwards it belongs to the cycle guard and to hand settings
    cache.private.put('release', true);
    if (Math.abs(offset) <= 0.25) {
      cache.private.remove('release');
      cache.private.remove('attempts');
    } else if (lock === 0) {
      const attempts = (cache.private.get('attempts') || 0) + 1;
      if (attempts <= 3 || now - (cache.private.get('write') || 0) >= RETRY * 60000) {
        write(0, phase === 'off' ? 'day heating off' : 'normal operation');
        cache.private.put('attempts', attempts);
      }
    }
  } else if (lock === 0 && Math.abs(offset - NIGHT) <= 0.25 && previous !== null && ['normal', 'off'].includes(previous)) {
    // the night's offset never belongs to normal operation (a release lost in a restart): back to 0
    write(0, 'night offset left over');
  }
}
