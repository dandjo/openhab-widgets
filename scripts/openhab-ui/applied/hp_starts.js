// compressor starts per day, for the badges of the overview's Heizung & Warmwasser: a start is the compressor
// (espaltherma_inv_frequency) leaving 0 Hz after a known 0 Hz. It counts for hot water when the valve stands on DHW
// at the start or within its first 2 minutes (a charge may begin with a few seconds on Space), else for the heating;
// a heating run whose valve turns to hot water later is no new start. During a defrost the compressor stops for
// about a minute, twice, and starts again: a start at most 2 minutes after a stop, with the defrost flag on at any
// time from 2 minutes before that stop, continues the run and does not count. A start is decided once its first
// 2 minutes are over (at once when it is plainly a hot-water start), when the compressor stops before that, or at
// 23:59:59, so it counts on the day it began. The counts start at 0 at midnight, local time; MapDB restores them
// after a restart, and a count with no point in InfluxDB since midnight is yesterday's and starts at 0 again.
const DECIDE = 120;   // s: a start's first seconds, in which the valve on DHW makes it a hot-water start
const GAP = 120;      // s: a start this soon after a stop may continue a defrost (seen: 30-90 s, other restarts >= 90 s)
const LEAD = 120;     // s before that stop from which the defrost flag counts
const DHW = 'heatpump_starts_dhw_today';
const HEATING = 'heatpump_starts_heating_today';

const now = Date.now();
const zdt = time.toZDT();
const today = zdt.toLocalDate().toString();
const lastSeconds = zdt.hour() === 23 && zdt.minute() === 59 && zdt.second() >= 50;
const freq = items.getItem('espaltherma_inv_frequency').numericState;  // null while NULL/UNDEF
const valve = items.getItem('espaltherma_3way_valve_mode').state;
const defrost = items.getItem('espaltherma_defrost_operaton').state === 'ON';

const add = (name, why) => {
  const item = items.getItem(name);
  const n = (item.numericState || 0) + 1;
  item.postUpdate(n);
  console.info(`starts today: ${name === DHW ? 'hot water' : 'heating'} ${n} (${why})`);
};

let s = cache.private.get('s');
if (s === null || s === undefined) {
  // the first run after a start of openHAB or of the rule: the frequency before it is unknown, so a run going on now
  // is not counted; MapDB restored the counts, which are today's only if InfluxDB has a point of them since midnight
  // (the reset at midnight writes one, a restore does not)
  const midnight = time.toZDT('00:00');
  for (const name of [DHW, HEATING]) {
    const item = items.getItem(name);
    if (item.numericState === null) {
      item.postUpdate(0);
    } else if (item.numericState > 0 && item.persistence.countSince(midnight, 'influxdb') === 0) {
      console.info(`starts today: ${name} ${item.numericState} is from before midnight, back to 0`);
      item.postUpdate(0);
    }
  }
  s = { day: today, freq: freq, stop: null, pending: null, defrostAt: null, defrost: false };
}

// when the defrost flag was last seen on: now while it is on, and now when it has just gone off
if (defrost || s.defrost) {
  s.defrostAt = now;
}
s.defrost = defrost;

const decide = (stopped) => {
  const p = s.pending;
  if (p.candidate && s.defrostAt !== null && s.defrostAt >= p.stop - LEAD * 1000) {
    s.pending = null;  // the defrost's restart: the run goes on
    return;
  }
  const over = stopped || lastSeconds || now - p.start >= DECIDE * 1000;
  if (p.dhw && (!p.candidate || over)) {
    s.pending = null;
    add(DHW, 'valve on DHW');
  } else if (over) {
    s.pending = null;
    add(HEATING, stopped ? 'stopped within 2 min' : 'valve on Space');
  }
};

if (s.day !== today) {
  for (const name of [DHW, HEATING]) {
    items.getItem(name).postUpdate(0);
  }
  s.day = today;
}

if (freq !== null) {
  if (s.freq === 0 && freq > 0) {
    s.pending = { start: now, dhw: false, stop: s.stop, candidate: s.stop !== null && now - s.stop <= GAP * 1000 };
  } else if (s.freq !== null && s.freq > 0 && freq === 0) {
    s.stop = now;
    if (s.pending !== null) {
      if (valve === 'DHW') {
        s.pending.dhw = true;
      }
      decide(true);
    }
  }
  s.freq = freq;
}
if (s.pending !== null) {
  if (valve === 'DHW') {
    s.pending.dhw = true;
  }
  decide(false);
}
cache.private.put('s', s);
