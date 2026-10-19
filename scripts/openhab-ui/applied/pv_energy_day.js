// The day's PV and battery figures the inverter's own counters do not give (user, 2026-10-19), from InfluxDB since
// midnight every minute, so a restart loses nothing:
// - photovoltaics_generation_day: the strings' energy since midnight (their time-weighted mean power times the hours);
//   the inverter's yield huawei_inverter_e_day counts the battery's discharge and leaves out what the strings charge
//   it with, and in winter the battery's charge from the grid comes back out through it too;
// - photovoltaics_peak_day: the strings' highest input power since midnight; the inverter's active power peak counts
//   the battery's discharge;
// - energy_storage_grid_charge_day: what the inverter draws from the house's AC side to charge the battery from the
//   grid, its active power below zero, each reading held until the next (the house consumption leaves it out).
const midnight = time.toZDT('00:00');
const now = time.toZDT();
const hours = time.Duration.between(midnight, now).toMillis() / 3600000;

// posted every minute, changed or not, so the rules reading them can tell today's from yesterday's by the update's time
// (InfluxDB stores a change only)
const post = (name, value, unit, digits) => {
  items.getItem(name).postUpdate(`${Number(value.toFixed(digits))} ${unit}`);
};
const numberOf = (s) => (s === null || s === undefined ? null : s.numericState);

const p1 = numberOf(items.getItem('huawei_inverter_pv1_power').persistence.averageSince(midnight, 'influxdb'));
const p2 = numberOf(items.getItem('huawei_inverter_pv2_power').persistence.averageSince(midnight, 'influxdb'));
if (p1 !== null && p2 !== null) {
  post('photovoltaics_generation_day', Math.max(0, p1 + p2) * hours / 1000, 'kWh', 3);
}

const peak = numberOf(items.getItem('huawei_inverter_input_power').persistence.maximumSince(midnight, 'influxdb'));
if (peak !== null) {
  post('photovoltaics_peak_day', Math.max(0, peak), 'W', 0);
}

// the active power's readings since midnight, the one before midnight holding until the first
const active = items.getItem('huawei_inverter_active_power').persistence;
const first = numberOf(active.persistedState(midnight, 'influxdb'));
const states = active.getAllStatesSince(midnight, 'influxdb');
if (states !== null && states !== undefined) {
  let wattSeconds = 0;
  let at = midnight.toInstant().toEpochMilli();
  let watts = first === null ? 0 : first;
  for (const s of states) {
    const t = s.timestamp.toInstant().toEpochMilli();
    if (watts < 0) {
      wattSeconds -= watts * (t - at) / 1000;
    }
    at = t;
    watts = s.numericState === null ? 0 : s.numericState;
  }
  if (watts < 0) {
    wattSeconds -= watts * (now.toInstant().toEpochMilli() - at) / 1000;
  }
  post('energy_storage_grid_charge_day', wattSeconds / 3600000, 'kWh', 3);
}
