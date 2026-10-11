// cycle guard: the controller stops the compressor once the leaving water after the backup heater reaches the setpoint
// + 3 K, and while it modulates it holds the water about 1.5 K above the setpoint, hunting by a kelvin. Below about
// 9 °C outdoors a start's start-up control (42–48 Hz, ~4 kW) takes the water to the stop within 4 to 5 minutes, before
// the compressor can modulate down: 4.5 minutes on, 7 off. So when the water comes 2 K above the setpoint during the
// start-up control of a start on the heating circuits, the rule lifts the leaving water offset by 2 K, which moves
// the stop above the overshoot. The controller then holds the water as far above the lifted setpoint, so once the
// start-up control has ended the rule takes the lift back a kelvin at a time, each time the compressor is at its
// lowest speed and the water has come down to 0.5 K above the lifted setpoint (1.5 K below the stop after the step; a
// step while it speeds up would carry the water past the stop). What is left goes 20 minutes after the start, and all
// of it at once when the run ends, the valve turns to hot water, or heating, Smart Grid or the automation leave their
// normal state. heatpump_cycle_raise holds the lift (MapDB restores it, so the rule knows its share of the offset
// after a restart); a value set by hand meanwhile stands.
const LIFT = 2;              // K the offset is lifted by
const LIFT_MAX = 3;          // K at most: one more step if the water still comes within 0.5 K of the lifted stop
const LIFT_AT = 2.0;         // K above the setpoint during the start-up control that lift it
const STEP_DOWN = 0.5;       // K above the lifted setpoint at most to take a kelvin of the lift back
const FREQ_LOW = 12;         // Hz at most for that: its lowest speeds (8–12 Hz); speeding up it jumps to 16–20
const MAX_HOLD = 20;         // minutes after the start at which what is left of the lift goes
const SETTLE = 20;           // seconds after a write before the next decision (offset and setpoint report back in ~5 s)
const MISSING = 5;           // minutes without readings after which a lift goes
const OFFSET_MAX = 10;       // the controller's offset range is −10..+10

const offsetItem = items.getItem('pyaltherma_leaving_water_temp_offset_heating');
const liftItem = items.getItem('heatpump_cycle_raise');
const num = (name) => items.getItem(name).numericState;
const state = (name) => items.getItem(name).state;
const now = Date.now();

const freq = num('espaltherma_inv_frequency');
const water = num('espaltherma_leaving_water_temp_after_buh');
const setpoint = num('espaltherma_leaving_water_setpoint');
const offset = num('pyaltherma_leaving_water_temp_offset_heating');
const valve = state('espaltherma_3way_valve_mode');
const startup = state('espaltherma_startup_control') === 'ON';
// while a reading is missing (NULL after a restart) it would compare as 0, so the guard waits for them
const missing = [freq, water, setpoint, offset].some((v) => v === null) || ['NULL', 'UNDEF'].includes(valve);
if (!missing) {
  cache.private.remove('missing');
} else if (!cache.private.get('missing')) {
  cache.private.put('missing', now);
}

// the compressor's runs: a run starts with the compressor, and only one that starts on the heating circuits is
// guarded; once the valve turns to hot water it stays unguarded until the compressor stops
let run = cache.private.get('run') || null;
if (!missing) {
  if (freq > 0 && run === null) {
    run = { start: now, space: valve === 'Space', manual: false };
  } else if (freq === 0) {
    run = null;
  }
  if (run !== null && valve !== 'Space') {
    run.space = false;
  }
  if (run !== null) {
    cache.private.put('run', run);
  } else {
    cache.private.remove('run');
  }
}
const age = run !== null ? (now - run.start) / 60000 : 0;
const guarded = run !== null && run.space && !run.manual
  && state('heatpump_cycle_management') === 'ON'
  && state('pyaltherma_climate_control_power') === 'ON'
  && state('espaltherma_space_heating_operation') === 'ON'
  && state('espaltherma_smart_grid') === '0';

const lift = liftItem.numericState || 0;
const settled = now - (cache.private.get('write') || 0) >= SETTLE * 1000;
const above = (water - setpoint).toFixed(1);

const write = (value, newLift, why) => {
  // in °C like the item: a quantity in K would be taken as an absolute temperature (−272.15 °C)
  offsetItem.sendCommand(Quantity(value + ' °C'));
  liftItem.postUpdate(newLift);
  cache.private.put('write', now);
  cache.private.put('previous', offset);
  cache.private.put('expected', value);
  console.info(`cycle guard: offset ${offset} -> ${value} (lift ${newLift} K), ${why}`);
};

if (missing) {
  if (lift > 0 && offset !== null && settled && now - cache.private.get('missing') >= MISSING * 60000) {
    write(offset - lift, 0, `readings missing for ${MISSING} min`);
  }
} else if (settled) {
  const expected = cache.private.get('expected');
  if (lift > 0 && expected !== null && expected !== undefined && Math.abs(offset - expected) > 0.5) {
    if (Math.abs(offset - cache.private.get('previous')) < 0.5) {
      write(expected, lift, 'last write had not arrived');
    } else {
      // set by hand meanwhile: that value stands, without a lift, and this run is left alone
      liftItem.postUpdate(0);
      cache.private.put('write', now);
      cache.private.remove('expected');
      if (run !== null) {
        run.manual = true;
        cache.private.put('run', run);
      }
      console.info(`cycle guard: offset set to ${offset} meanwhile, the guard leaves this run alone`);
    }
  } else if (lift > 0) {
    const base = offset - lift;  // the offset without the lift
    if (!guarded) {
      write(base, 0, run !== null ? 'run no longer guarded' : 'compressor stopped');
    } else if (age >= MAX_HOLD) {
      write(base, 0, `${Math.round(age)} min after the start`);
    } else if (startup) {
      if (lift < LIFT_MAX && water - setpoint >= LIFT_AT + 0.5 && base + LIFT_MAX <= OFFSET_MAX) {
        write(base + LIFT_MAX, LIFT_MAX, `water ${above} K above the lifted setpoint during the start-up control`);
      }
    } else if (freq <= FREQ_LOW && water - setpoint <= STEP_DOWN) {
      write(offset - 1, lift - 1, `water ${above} K above the lifted setpoint after ${Math.round(age)} min`);
    }
  } else if (guarded && startup && age < MAX_HOLD && offset + LIFT <= OFFSET_MAX && water - setpoint >= LIFT_AT) {
    write(offset + LIFT, LIFT, `water ${above} K above the setpoint after ${Math.round(age)} min of start-up control`);
  }
}
