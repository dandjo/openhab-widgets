// cycle guard (user, 2026-10-11, start lock since 2026-10-12): the controller stops the compressor once the leaving
// water after the backup heater reaches the setpoint + 3 K and calls for heat again at setpoint − 1 K. A start's
// start-up control runs at a fixed speed for 4.5 to 7.5 minutes, at 42–48 Hz (~4 kW) below about 9 °C outdoors, which
// lifts the water about 4.5 K above the return: with the return less than 3 K below the curve such a start reaches the
// stop within minutes, the 7 minutes off do not cool the circuit, and the next start fails the same way (heating
// season 2025/26: 312 such short runs in 32 series, 21 of them begun within 20 minutes after a hot-water charge,
// whereas all 200 starts with the return 3 K or more below the curve came through and ran for hours). Within an hour
// after a hot-water charge or a short run the compressor is still hot, and above 9 °C most starts then end in the
// first minute (141 in 2025/26), unless its discharge pipe has cooled below 38 °C, the return is 2.5 K below the
// curve or an hour has passed. So when the compressor has stopped (below 9 °C after every run, above only after a hot-water charge or a run
// shorter than 10 minutes) the rule lowers the leaving water offset by 5 K, which keeps the controller from calling
// for heat, and gives the start free again once the return, read while the pump circulates, has stayed far enough
// below the curve for 2 minutes (or, above 9 °C, the compressor has cooled), 2 hours after the stop at the latest.
// During a run it changes nothing. The controller keeps its setpoint at or above its minimum leaving water temperature
// (25 °C here), whatever the offset, so a lock only works where the curve lies at least a kelvin above that: the rule
// remembers the curve from before a lock and the minimum it meets, and leaves stops alone where a lock would not lower
// the setpoint. heatpump_cycle_lock holds the kelvins the offset is lowered by (MapDB restores it, so the rule knows its
// share of the offset after a restart); a value set by hand meanwhile stands. The return's marks lie below the setpoint
// without the lock, the curve plus the offset the lock was taken from. In the day heating's window (heatpump_day_heating,
// user, 2026-10-13) the guard locks only after a hot-water charge or a short run, as above 9 °C, whatever the outdoor
// air, so the window's own runs go on; in its night it keeps out and leaves a lock to it as it stands, as a release to
// the day offset would call for heat until the night's offset arrives.
const LOCK = 5;              // K the offset is lowered by while starts are locked
const COLD = 9;              // °C outdoor air below which a start's start-up control runs at 42–48 Hz
const RETURN_COLD = 3.2;     // K below the curve the return must be below 9 °C, with a hot compressor
const RETURN_COOL = 2.8;     // ... and once the compressor has cooled below COOL_AT
const COOL_AT = 45;          // °C at the discharge pipe
const RETURN_MILD = 2.5;     // K below the curve that let a start with a hot compressor come through above 9 °C
const DISCHARGE = 38;        // °C at the discharge pipe below which the compressor has cooled down
const MILD_PAUSE = 60;       // minutes after which a compressor has cooled anyway (its reading freezes on warm days)
const SHORT = 10;            // minutes: a shorter run leaves a hot compressor behind (above 9 °C)
const HOLD = 2;              // minutes the return must stay at or below its mark
const DELAY = 100;           // seconds the compressor must stand before a lock; defrost restarts come within 30–90 s
const DEFROST_GAP = 5;       // minutes after a defrost in which a stop locks nothing
const MIN_PAUSE = 5;         // minutes after the stop before a lock goes (the return settles after a hot-water charge)
const MAX_PAUSE = 120;       // minutes after the stop after which a lock goes in any case
const SETTLE = 20;           // seconds after a write before the next decision (offset and setpoint report back in ~5 s)
const MISSING = 5;           // minutes without readings after which a lock goes
const FLOW = 5;              // l/min at least for the return reading to be the circuit's
const OFFSET_MIN = -10;      // the controller's offset range is −10..+10
const EFFECT = 1;            // K at least by which a lock must lower the setpoint to be worth it
const FLOOR_AGE = 6;         // hours after which a minimum met is tried again (the installer setting may have changed)

const offsetItem = items.getItem('pyaltherma_leaving_water_temp_offset_heating');
const lockItem = items.getItem('heatpump_cycle_lock');
const num = (name) => items.getItem(name).numericState;
const state = (name) => items.getItem(name).state;
const now = Date.now();

const freq = num('espaltherma_inv_frequency');
const setpoint = num('espaltherma_leaving_water_setpoint');
const offset = num('pyaltherma_leaving_water_temp_offset_heating');
const valve = state('espaltherma_3way_valve_mode');
const returnTemp = num('espaltherma_inlet_water_temp');
const flow = num('espaltherma_flow_sensor');
const discharge = num('espaltherma_discharge_pipe_temp');
const outdoor = num('espaltherma_outdoor_air_temp');
if (state('espaltherma_defrost_operaton') === 'ON') {
  cache.private.put('defrost', now);
}
// while a reading is missing (NULL after a restart) it would compare as 0, so the guard waits for them
const missing = [freq, setpoint, offset, returnTemp, flow, discharge, outdoor].some((v) => v === null)
  || ['NULL', 'UNDEF'].includes(valve);
if (!missing) {
  cache.private.remove('missing');
} else if (!cache.private.get('missing')) {
  cache.private.put('missing', now);
}

// the compressor's runs and stops: a run remembers whether it charged the tank, a stop when it came and what ran before
let run = cache.private.get('run') || null;
let stop = cache.private.get('stop') || null;
if (!missing) {
  if (freq > 0) {
    if (run === null) {
      run = { start: now, dhw: false };
    }
    run.dhw = run.dhw || valve !== 'Space';
    cache.private.put('run', run);
  } else if (run !== null || stop === null) {
    // a stop; after a restart of openHAB the rule takes a standing compressor as stopped now
    stop = { at: now, dhw: run !== null && run.dhw, minutes: run !== null ? (now - run.start) / 60000 : null,
             done: false, manual: false };
    run = null;
    cache.private.remove('run');
    cache.private.remove('below');
  }
  if (stop !== null) {
    cache.private.put('stop', stop);
  }
}
const pause = stop !== null ? (now - stop.at) / 60000 : 0;
// the day heating's night keeps the heating off, the guard keeps out then; in its window it locks as on a mild day.
// Smart Grid does not matter (user, 2026-10-13): forced on (3) only charges the tank to 60 °C, the heating's setpoint
// stays, and the short heating runs after those charges are what the lock is for
const dayState = state('heatpump_day_heating_state');
const night = dayState === 'night';
const enabled = state('heatpump_cycle_management') === 'ON'
  && state('pyaltherma_climate_control_power') === 'ON'
  && !night;

// a stop is locked only while the controller's own space heating is on (it reads ON all season, OFF in summer)
const heating = state('espaltherma_space_heating_operation') === 'ON';
const lock = lockItem.numericState || 0;
// a decision waits SETTLE seconds after the guard's own write and after any change of the offset (the day heating's
// writes too), as the setpoint reports back about 5 seconds after the offset
if (offset !== null && cache.private.get('seen') !== offset) {
  cache.private.put('seen', offset);
  cache.private.put('changed', now);
}
const settled = now - Math.max(cache.private.get('write') || 0, cache.private.get('changed') || 0) >= SETTLE * 1000;
// the curve is the setpoint without the offset, taken while no lock holds and no write is on its way; during a lock the
// controller may hold the setpoint at its minimum, so the curve from before the lock is used (and the day heating's
// night is left out, as its offset keeps the setpoint at the minimum)
if (!missing && lock === 0 && settled && !night && cache.private.get('expected') == null) {
  cache.private.put('curve', setpoint - offset);
}
const curve = cache.private.get('curve') ?? null;
const base = offset !== null ? offset + lock : null;  // the offset without the lock
const ref = curve !== null && base !== null ? curve + base : null;  // the setpoint without the lock
const cold = outdoor < COLD;
// a start-up control that lifts the water less (above 9 °C), or the day heating's window: lock only a hot compressor
const mild = !cold || dayState === 'day';

const write = (value, newLock, why) => {
  // in °C like the item: a quantity in K would be taken as an absolute temperature (−272.15 °C)
  offsetItem.sendCommand(Quantity(value + ' °C'));
  lockItem.postUpdate(newLock);
  cache.private.put('write', now);
  cache.private.put('previous', offset);
  cache.private.put('expected', value);
  cache.private.remove('attempts');
  console.info(`cycle guard: offset ${offset} -> ${value} (lock ${newLock} K), ${why}`);
};

// whether a start may come now: the return, read while the pump circulates the heating water and the compressor
// stands, has stayed at or below its mark for HOLD minutes; above 9 °C a cooled compressor is enough (the valve may
// then still stand on the tank, with no reading of the return), or an hour, as the outdoor unit's readings freeze
// while it idles on warm days
const reading = !missing && ref !== null && freq === 0 && valve === 'Space' && flow >= FLOW;
const mark = mild ? RETURN_MILD : discharge < COOL_AT ? RETURN_COOL : RETURN_COLD;
if (reading && settled) {
  if (returnTemp <= ref - mark) {
    if (!cache.private.get('below')) {
      cache.private.put('below', now);
    }
  } else {
    cache.private.remove('below');
  }
}
const below = cache.private.get('below');
const held = reading && below && now - below >= HOLD * 60000;
const cooled = !missing && mild && freq === 0 && (discharge <= DISCHARGE || pause >= MILD_PAUSE);
const free = settled && (held || cooled);

if (missing) {
  if (lock > 0 && offset !== null && settled && now - cache.private.get('missing') >= MISSING * 60000) {
    write(offset + lock, 0, `readings missing for ${MISSING} min`);
  }
} else if (settled) {
  const expected = cache.private.get('expected');
  if (expected !== null && expected !== undefined && Math.abs(offset - expected) > 0.5) {
    if (Math.abs(offset - cache.private.get('previous')) < 0.5) {
      // a lock that does not arrive after 3 tries is given up; a release is tried on every 5 minutes
      const attempts = (cache.private.get('attempts') || 0) + 1;
      if (attempts <= 3) {
        write(expected, lock, 'last write had not arrived');
        cache.private.put('attempts', attempts);
      } else if (lock > 0) {
        lockItem.postUpdate(0);
        cache.private.remove('expected');
        if (stop !== null) {
          stop.done = true;
          cache.private.put('stop', stop);
        }
        console.warn(`cycle guard: offset writes do not arrive, no lock for this pause`);
      } else if (now - (cache.private.get('write') || 0) >= 300000) {
        write(expected, lock, `release has not arrived after ${attempts} tries`);
        cache.private.put('attempts', attempts);
      }
    } else {
      // set by hand meanwhile: that value stands, without a lock, and this pause is left alone
      lockItem.postUpdate(0);
      cache.private.put('write', now);
      cache.private.remove('expected');
      if (stop !== null) {
        stop.manual = true;
        stop.done = true;
        cache.private.put('stop', stop);
      }
      console.info(`cycle guard: offset set to ${offset} meanwhile, the guard leaves this pause alone`);
    }
  } else {
    // a confirmed write is forgotten once no lock is left, so a change by hand during a lock is noticed
    if (expected !== null && expected !== undefined && lock === 0) {
      cache.private.remove('expected');
    }
    if (lock > 0 && night) {
      // the day heating's night takes the offset over as it stands: no write, the lock is only forgotten
      lockItem.postUpdate(0);
      cache.private.remove('expected');
      if (stop !== null) {
        stop.done = true;
        cache.private.put('stop', stop);
      }
      console.info(`cycle guard: lock of ${lock} K left to the day heating's night at offset ${offset}`);
    } else if (lock > 0) {
      let why = null;
      if (ref !== null && setpoint > ref - LOCK + 0.5) {
        cache.private.put('floor', { value: setpoint, at: now });
      } else if (ref !== null) {
        cache.private.remove('floor');
      }
      if (!enabled) {
        why = 'guard off';
      } else if (curve === null) {
        why = 'curve unknown after a restart';
      } else if (ref - setpoint < EFFECT) {
        why = `the controller keeps the setpoint at ${setpoint} °C, its minimum`;
      } else if (freq > 0 && valve === 'Space') {
        why = 'the compressor runs for the heating';
      } else if (pause >= MAX_PAUSE) {
        why = `${MAX_PAUSE} min after the stop`;
      } else if (free && pause >= MIN_PAUSE) {
        why = held
          ? `return ${returnTemp} °C, ${(ref - returnTemp).toFixed(1)} K below the curve` +
            (base !== 0 ? ` ${base > 0 ? '+' : '−'} ${Math.abs(base)} K` : '') + `, after ${Math.round(pause)} min`
          : discharge <= DISCHARGE ? `compressor cooled to ${discharge} °C after ${Math.round(pause)} min`
            : `${Math.round(pause)} min after the stop`;
      }
      if (why !== null) {
        write(base, 0, why);
        if (stop !== null) {
          stop.done = true;
          cache.private.put('stop', stop);
        }
      }
    } else if (stop !== null && !stop.done && freq === 0) {
      const defrost = cache.private.get('defrost') || 0;
      const hot = stop.dhw || (stop.minutes !== null && stop.minutes < SHORT);
      if (!enabled || !heating || now - defrost < DEFROST_GAP * 60000 || pause >= MAX_PAUSE || (mild && !hot)) {
        // nothing to lock for this stop (a defrost's stop is followed by its restart)
        if (now - defrost >= DEFROST_GAP * 60000 && pause * 60 >= DELAY) {
          stop.done = true;
          cache.private.put('stop', stop);
        }
      } else if (pause * 60 >= DELAY) {
        stop.done = true;
        cache.private.put('stop', stop);
        const lowered = Math.max(OFFSET_MIN, base - LOCK);
        const met = cache.private.get('floor') ?? null;
        const floor = met !== null && now - met.at < FLOOR_AGE * 3600000 ? met.value : -99;
        const reach = curve === null ? 0 : (curve + base) - Math.max(curve + lowered, floor);
        if (base - lowered >= 1 && reach >= EFFECT) {
          write(lowered, base - lowered, `compressor stopped ${Math.round(pause * 60)} s ago after ` +
            (stop.dhw ? 'a hot-water charge' : `a ${stop.minutes === null ? 'run' : Math.round(stop.minutes) + '-min run'}`) +
            `, outdoor ${outdoor} °C, return ${returnTemp} °C, discharge ${discharge} °C`);
        }
      }
    }
  }
}
