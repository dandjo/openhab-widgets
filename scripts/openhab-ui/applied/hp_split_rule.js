const persistPower = function(item, value, unit = null, precision = null) {
  const u = unit !== null ? ' ' + unit : ' W';
  const p = precision !== null ? precision : 2;
  items.getItem(item).postUpdate(Quantity(value.toFixed(p) + u));
};

const persistCop = function(item, value) {
  if (value <= 10) {
    items.getItem(item).postUpdate(Quantity(value.toFixed(2)));
  }  
};

const isInverter =
  items.getItem('heatpump_power').numericState > 70  // assume that inverter is active above this level
    || items.getItem('espaltherma_inv_frequency').numericState > 0
    || items.getItem('espaltherma_inv_primary_current').numericState > 0;

const isWaterPump =
  items.getItem('espaltherma_water_pump_operation').state === 'ON';

// the valve mode is the command, not the position: the ESBE MBA130 needs 40 s for 90°, and
// for about the first 30 s after switching back to Space the water still goes to the tank
const valve_travel_seconds = 30;
const valve = items.getItem('espaltherma_3way_valve_mode');
const isDhwTravel =
  valve.state === 'Space'
    && valve.lastStateChangeTimestamp !== null
    && time.Duration.between(valve.lastStateChangeTimestamp, time.toZDT()).toMillis() < valve_travel_seconds * 1000;

let isDhw = valve.state === 'DHW' || isDhwTravel;
let isSpace = valve.state === 'Space' && !isDhwTravel;

// with the pump off, a running-down inverter belongs to the mode the pump last ran in, unless the valve already
// reports DHW: a hot-water cycle can start with a short pump run while the valve is still on Space and then run
// the compressor for minutes with the pump off
if (isWaterPump && (isDhw || isSpace)) {
  cache.private.put('pump_mode', isDhw ? 'DHW' : 'Space');
} else if (!isWaterPump && isInverter && valve.state !== 'DHW') {
  const pump_mode = cache.private.get('pump_mode');
  if (pump_mode === 'DHW' || pump_mode === 'Space') {
    isDhw = pump_mode === 'DHW';
    isSpace = pump_mode === 'Space';
  }
}

const isBsh =
  items.getItem('espaltherma_bsh_mode').state === 'ON';

const isBuh =
  items.getItem('espaltherma_buh_step1_mode').state === 'ON'
    || items.getItem('espaltherma_buh_step2_mode').state === 'ON';

// with space heating switched off (the controller's switch and ESPAltherma's flag both off) nothing is space
// heating: what runs on Space is the start or the end of a hot-water cycle, and a run of the pump alone, without
// the compressor or the backup heater (a pre-run, the anti-seize run), is standby
const isHeatingOff =
  items.getItem('pyaltherma_climate_control_power').state === 'OFF'
    && items.getItem('espaltherma_space_heating_operation').state === 'OFF';
let isPumpOnly = false;
if (isHeatingOff && isSpace) {
  isSpace = false;
  isDhw = true;
  isPumpOnly = !isInverter && !isBuh;
}

const buh1_power = 2000;  // 2kW
const buh2_power = 4000;  // 4kW
const bsh_power = 2000;  // 2kW

const heatpump_power = items.getItem('heatpump_power').numericState;

// calculate electrical power

let electrical_power_space = 0;
let electrical_power_dhw = 0;
let electrical_power_standby = 0;

if (isSpace && (isInverter || isWaterPump)) {
  electrical_power_space += heatpump_power;
}
if (isDhw && (isInverter || isWaterPump) && !isPumpOnly) {
  electrical_power_dhw += heatpump_power;
}

if ((!isInverter && !isWaterPump) || isPumpOnly) {
  electrical_power_standby += heatpump_power;
}

if (items.getItem('espaltherma_buh_step1_mode').state === 'ON') {
  if (isSpace) {
    electrical_power_space += buh1_power;
  }
  if (isDhw) {
    electrical_power_dhw += buh1_power;
  }
}
if (items.getItem('espaltherma_buh_step2_mode').state === 'ON') {
  if (isSpace) {
    electrical_power_space += buh2_power;
  }
  if (isDhw) {
    electrical_power_dhw += buh2_power;
  }
}
if (isBsh) {
  electrical_power_dhw += bsh_power;
}

const electrical_power = electrical_power_space + electrical_power_dhw + electrical_power_standby;

persistPower('espaltherma_electrical_power_space', electrical_power_space);
persistPower('espaltherma_electrical_power_dhw', electrical_power_dhw);
persistPower('espaltherma_electrical_power_standby', electrical_power_standby);
persistPower('espaltherma_electrical_power', electrical_power);

// calculate heating power

let heating_power_before_buh = 0;
let heating_power_after_buh = 0;
let heating_power_space = 0;
let heating_power_dhw = 0;

if (items.getItem('espaltherma_operation_mode').state === 'Heating') {
  const flow_kg_h = items.getItem('espaltherma_flow_sensor').numericState * 60;  // converts l/min to kg/h for water
  const thermal_capacity = 1.1639;  // of water in Wh/(kg•K)
  const inlet_temp = items.getItem('espaltherma_inlet_water_temp').numericState;
  const diff_temp_before_buh = items.getItem('espaltherma_leaving_water_temp_before_buh').numericState - inlet_temp;
  heating_power_before_buh += flow_kg_h * thermal_capacity * diff_temp_before_buh;
  const diff_temp_after_buh = items.getItem('espaltherma_leaving_water_temp_after_buh').numericState - inlet_temp;
  heating_power_after_buh += flow_kg_h * thermal_capacity * diff_temp_after_buh;
  if (isSpace) {
    heating_power_space += heating_power_after_buh;
  }
  if (isDhw) {
    heating_power_dhw += heating_power_after_buh;
  }
}

if (isBsh) {
  heating_power_dhw += bsh_power;
}

const heating_power = heating_power_space + heating_power_dhw;

persistPower('espaltherma_heating_power_before_buh', heating_power_before_buh);
persistPower('espaltherma_heating_power_after_buh', heating_power_after_buh);
persistPower('espaltherma_heating_power_space', heating_power_space);
persistPower('espaltherma_heating_power_dhw', heating_power_dhw);
persistPower('espaltherma_heating_power', heating_power);

// calculate cop

let cop_space = 0;
let cop_dhw = 0;
let cop = 0;

if (heating_power_space > 0 && electrical_power_space > 0) {
  cop_space = heating_power_space / electrical_power_space;
}
if (heating_power_dhw > 0 && electrical_power_dhw > 0) {
  cop_dhw = heating_power_dhw / electrical_power_dhw;
}
if (heating_power > 0 && electrical_power > 0) {
  cop = heating_power / electrical_power;
}

persistCop('espaltherma_cop_space', cop_space);
persistCop('espaltherma_cop_dhw', cop_dhw);
persistCop('espaltherma_cop', cop);

// integrate energy since midnight: trapezoidal between consecutive runs with one shared
// time step, so the space/dhw/standby split sums exactly to the total

const max_gap_seconds = 300;  // a longer silence (restart, ESPAltherma offline) is not bridged
const post_interval_seconds = 60;  // accumulate on every run, write the items once a minute

const powers = {
  espaltherma_energy_space_today: electrical_power_space,
  espaltherma_energy_dhw_today: electrical_power_dhw,
  espaltherma_energy_standby_today: electrical_power_standby,
  espaltherma_energy_today: electrical_power,
  espaltherma_heating_energy_space_today: heating_power_space,
  espaltherma_heating_energy_dhw_today: heating_power_dhw,
  espaltherma_heating_energy_today: heating_power
};

// sources are null right after startup; skip the run rather than integrate garbage
if (Object.values(powers).every(Number.isFinite)) {
  const now = time.toZDT();
  const midnight = time.toZDT('00:00');
  const prev = cache.private.get('energy') || null;
  const new_day = prev === null || prev.timestamp.isBefore(midnight);

  const energies = {};
  const write_midnight_zero = {};
  for (const item of Object.keys(powers)) {
    if (!new_day) {
      energies[item] = prev.energies[item];
      write_midnight_zero[item] = false;
    } else if (prev !== null) {
      energies[item] = 0;
      write_midnight_zero[item] = true;
    } else {
      // after a restart, continue from what InfluxDB holds for today
      const persisted = items.getItem(item).persistence.persistedState(now);
      const today = persisted !== null && persisted.quantityState !== null && !persisted.timestamp.isBefore(midnight);
      energies[item] = today ? persisted.quantityState.toUnit('Wh').float : 0;
      write_midnight_zero[item] = !today;
    }
  }

  if (prev !== null) {
    const gap = time.Duration.between(prev.timestamp, now).toMillis() / 1000;
    if (gap > 0 && gap <= max_gap_seconds) {
      const from = new_day ? midnight : prev.timestamp;
      const seconds = time.Duration.between(from, now).toMillis() / 1000;
      for (const [item, power] of Object.entries(powers)) {
        const prev_power = new_day ? power : prev.powers[item];
        energies[item] += (prev_power + power) / 2 * seconds / 3600;
      }
    }
  }

  const post_due = new_day || time.Duration.between(prev.posted, now).toMillis() / 1000 >= post_interval_seconds;
  if (post_due) {
    for (const item of Object.keys(powers)) {
      if (write_midnight_zero[item]) {
        items.getItem(item).persistence.persist(midnight, Quantity('0 Wh'), 'influxdb');
      }
      items.getItem(item).postUpdate(Quantity(energies[item].toFixed(3) + ' Wh'));
    }
  }

  cache.private.put('energy', {
    timestamp: now,
    powers: powers,
    energies: energies,
    posted: post_due ? now : prev.posted
  });
}