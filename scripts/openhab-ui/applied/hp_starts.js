// compressor runs per day, for the badges of the overview's Heizung & Warmwasser: every stretch in which the compressor
// (espaltherma_inv_frequency above 0 Hz) runs with the valve on one side counts once for that side, for hot water while
// the valve stands on DHW, else for the heating (user, 2026-10-19). A heating run whose valve turns to hot water and
// back to the heating counts once for hot water and twice for the heating. A stretch counts once it has lasted 2
// minutes, so the seconds on Space with which a charge may begin or end count for nothing, and a turn of the valve for
// less than that and back continues the stretch before it; a run that stops with no stretch of 2 minutes counts once,
// for hot water when its valve stood on DHW at any time. During a defrost the compressor stops for about a minute,
// twice, and starts again: a start at most 2 minutes after a stop, with the defrost flag on at any time from 2 minutes
// before that stop, continues the run and its stretch. A stretch not yet counted counts at 23:59:59, so it counts on
// the day it began. The counts start at 0 at midnight, local time; MapDB restores them after a restart, and a count
// with no point in InfluxDB since midnight is yesterday's and starts at 0 again. A run going on when the rule first
// runs is taken as counted; a later turn of its valve counts.
const MIN = 120;      // s a stretch lasts before it counts
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
const side = valve === 'DHW' ? DHW : valve === 'Space' ? HEATING : null;  // null while NULL/UNDEF
const defrost = items.getItem('espaltherma_defrost_operaton').state === 'ON';

const add = (name, why) => {
  const item = items.getItem(name);
  const n = (item.numericState || 0) + 1;
  item.postUpdate(n);
  console.info(`runs today: ${name === DHW ? 'hot water' : 'heating'} ${n} (${why})`);
};
// a run: when it started, the side and start of its current stretch, whether that stretch and whether any stretch of
// the run counted, the side of the last stretch that counted, and whether its valve stood on DHW at any time
const newRun = (counted) => ({ start: now, side: side, since: now, counted: counted, any: counted,
                               last: counted ? side : null, dhw: side === DHW });

let s = cache.private.get('s');
if (s === null || s === undefined) {
  // the first run after a start of openHAB or of the rule: MapDB restored the counts, which are today's only if
  // InfluxDB has a point of them since midnight (the reset at midnight writes one, a restore does not)
  const midnight = time.toZDT('00:00');
  for (const name of [DHW, HEATING]) {
    const item = items.getItem(name);
    if (item.numericState === null) {
      item.postUpdate(0);
    } else if (item.numericState > 0 && item.persistence.countSince(midnight, 'influxdb') === 0) {
      console.info(`runs today: ${name} ${item.numericState} is from before midnight, back to 0`);
      item.postUpdate(0);
    }
  }
  s = { day: today, freq: freq, stop: null, run: freq > 0 ? newRun(true) : null, prev: null, cont: null,
        defrostAt: null, defrost: false };
}

// when the defrost flag was last seen on: now while it is on, and now when it has just gone off
if (defrost || s.defrost) {
  s.defrostAt = now;
}
s.defrost = defrost;

if (s.day !== today) {
  for (const name of [DHW, HEATING]) {
    items.getItem(name).postUpdate(0);
  }
  s.day = today;
}

// a start soon after a stop (s.cont: the stopped run and its stop) is the defrost's restart once the defrost flag
// shows, and a run of its own when it has run 2 minutes without it, stops, or the day ends
const resolve = (stopped) => {
  if (s.cont === null) {
    return;
  }
  if (s.defrostAt !== null && s.defrostAt >= s.cont.stop - LEAD * 1000) {
    s.run = s.cont.run;
    s.cont = null;
  } else if (stopped || lastSeconds || now - s.run.start >= MIN * 1000) {
    s.cont = null;
  }
};
const count = (run, why) => {
  run.counted = true;
  run.any = true;
  run.last = run.side;
  add(run.side, why);
};
// the run's stretch: a new one when the valve turns, the old one counted if it lasted 2 minutes before that; back
// to the side of the last stretch that counted from one that did not, that stretch goes on
const follow = (run) => {
  const lasted = now - run.since >= MIN * 1000;
  if (side !== null && side !== run.side) {
    if (run.side !== null && !run.counted && lasted) {
      count(run, 'valve turned');
    }
    Object.assign(run, { side: side, since: now, counted: !run.counted && side === run.last });
  } else if (run.side !== null && !run.counted && (lasted || lastSeconds)) {
    count(run, lasted ? '2 min' : 'end of the day');
  }
  if (side === DHW) {
    run.dhw = true;
  }
};

if (freq !== null) {
  if (s.freq === 0 && freq > 0) {
    const soon = s.prev !== null && s.stop !== null && now - s.stop <= GAP * 1000;
    s.cont = soon ? { run: s.prev, stop: s.stop } : null;
    s.run = newRun(false);
    s.prev = null;
  } else if (s.freq !== null && s.freq > 0 && freq === 0 && s.run !== null) {
    resolve(true);
    follow(s.run);
    if (!s.run.any) {
      s.run.any = true;
      add(s.run.dhw ? DHW : HEATING, 'stopped within 2 min');
    }
    s.prev = s.run;
    s.run = null;
    s.stop = now;
  }
  s.freq = freq;
}
if (s.run !== null) {
  resolve(false);
  if (s.cont === null) {
    follow(s.run);
  }
}
cache.private.put('s', s);
