// The E-Car charges on the air conditioning's circuit. Faikin measures the outdoor unit; what the circuit's meter
// shows beyond that is the indoor unit (about 20–30 W while the air conditioner is on, standby and an LED light
// of about 10 W while it is off) and the car while it charges. The indoor unit's share is learned per state of
// the air conditioner while the car is idle and the outdoor unit is off.
// Whether the car charges is a state, not a threshold. A charge starts when the circuit rises by at least
// 1.2 kW within its last two reports beyond what Faikin explains (the outdoor unit never ramps that fast) and
// leaves a rest of at least 1.2 kW. It ends when the circuit drops by as much beyond Faikin and leaves less
// than 1.2 kW, when the rest falls under 300 W, or when it stays under 1 kW, below the car's lowest charging
// power, for 10 s. A charge whose start was missed is picked up after a minute of a rest of at least 1.2 kW at
// a power factor of 0.95 or more (the car's; the air conditioner stays below); after a restart the state
// follows the rest alone.
// While the car charges it gets the rest, the circuit less Faikin and the indoor unit, but never more than its
// charging current allows at the circuit's voltage (plus 1.5 %, the current's own spread): the car draws a
// constant current, taken over the charger's first 30 s and measured exactly whenever the outdoor unit is off.
// So Faikin's lag or an error above the car's power stays with the air conditioner, and the air conditioner never
// gets less than Faikin measures. The current follows a lasting change: a drop over three reports, a rise over
// three reports while the outdoor unit is off. The air conditioner's share is taken as purely active power.
const split = (plug, outdoor, acOn, pf, voltage, now, s) => {
  const rest = Math.max(0, plug - outdoor);
  const key = acOn ? 'on' : 'off';
  const base = s.base[key];
  const report = s.history.length === 0 || s.history[s.history.length - 1][0] !== plug;
  const start = () => {
    s.charging = true;
    s.lowSince = 0;
    s.startedAt = now;
    s.own = 0;
    s.devSign = 0;
    s.devN = 0;
  };
  if (s.charging === null) {
    s.charging = false;
    if (rest >= 1200) {
      start();
    }
  } else if (report && s.history.length > 0) {
    // the circuit's change against each of its last two reports, less what Faikin explains
    const recent = s.history.slice(-2);
    const rise = Math.max(...recent.map(([p, f]) => plug - p - Math.max(0, outdoor - f)));
    const drop = Math.min(...recent.map(([p, f]) => plug - p - Math.min(0, outdoor - f)));
    if (!s.charging && rise >= 1200 && rest >= 1200) {
      start();
    } else if (s.charging && drop <= -1200 && rest < 1200) {
      s.charging = false;
    }
  }
  if (report) {
    s.history = [...s.history, [plug, outdoor]].slice(-3);
  }
  if (s.charging) {
    if (rest < 300) {
      s.charging = false;
    } else if (rest - base < 1000) {
      s.lowSince = s.lowSince || now;
      if (now - s.lowSince >= 10000) {
        s.charging = false;
      }
    } else {
      s.lowSince = 0;
    }
  } else if (rest >= 1200 && pf >= 0.95) {
    s.steadySince = s.steadySince || now;
    if (now - s.steadySince >= 60000) {
      start();
    }
  } else {
    s.steadySince = 0;
  }
  if (!s.charging) {
    s.lowSince = 0;
    if (outdoor === 0 && rest < 150) {
      // slowly, so a single odd reading moves it little; the ramp of a charge starting stays out
      s.base[key] = base + 0.1 * (rest - base);
    }
    return 0;
  }
  s.steadySince = 0;
  const volts = voltage > 150 ? voltage : 230;
  const amps = (rest - base) / volts;
  let car = rest - base;
  if (!s.own || now - s.startedAt < 30000) {
    s.own = Math.max(s.own, Math.min(amps, 2300 / volts));
  } else {
    const dev = amps - s.own;
    if (report) {
      const sign = dev > 0.015 * s.own ? 1 : dev < -0.015 * s.own ? -1 : 0;
      s.devN = sign !== 0 && sign === s.devSign ? s.devN + 1 : sign !== 0 ? 1 : 0;
      s.devSign = sign;
    }
    const lasting = s.devN >= 3;
    if ((outdoor === 0 && (dev <= 0.015 * s.own || (s.devSign > 0 && lasting))) || (outdoor !== 0 && s.devSign < 0 && lasting)) {
      s.own = amps;
    }
    car = Math.min(rest - base, s.own * volts * 1.015);
  }
  return Math.max(0, Math.min(car, 2300, plug - base));
};

const num = (name) => items.getItem(name).numericState;
const plug = num('air_conditioning_power');
const acOn = items.getItem('faikout_perfera_switch').state === 'ON';
// Faikin reads 0 W while the unit is off, except while its compressor runs down after switching off
const outdoor = num('faikout_perfera_power') ?? 0;
if (plug !== null) {
  const s = {
    charging: cache.private.exists('charging') ? cache.private.get('charging') : null,
    history: JSON.parse(cache.private.get('history', () => '[]')),
    lowSince: cache.private.get('lowSince', () => 0),
    steadySince: cache.private.get('steadySince', () => 0),
    startedAt: cache.private.get('startedAt', () => 0),
    own: cache.private.get('own', () => 0),
    devSign: cache.private.get('devSign', () => 0),
    devN: cache.private.get('devN', () => 0),
    base: { on: cache.private.get('base_on', () => 20), off: cache.private.get('base_off', () => 10) },
  };
  const voltage = num('air_conditioning_voltage');
  const power = split(plug, outdoor, acOn, num('air_conditioning_power_factor') ?? 0, voltage, Date.now(), s);
  cache.private.put('charging', s.charging);
  cache.private.put('history', JSON.stringify(s.history));
  cache.private.put('lowSince', s.lowSince);
  cache.private.put('steadySince', s.steadySince);
  cache.private.put('startedAt', s.startedAt);
  cache.private.put('own', s.own);
  cache.private.put('devSign', s.devSign);
  cache.private.put('devN', s.devN);
  cache.private.put('base_on', s.base.on);
  cache.private.put('base_off', s.base.off);
  const base = s.base[acOn ? 'on' : 'off'];
  // the two always add up to the plug
  items.getItem('air_conditioning_unit_power').postUpdate(Quantity(Math.max(0, plug - power).toFixed(2) + ' W'));
  const plugApparent = num('air_conditioning_apparent_power');
  // the car's power factor stays near 1; the circuit's reactive part beyond that is the air conditioner's
  const apparent = power === 0 ? 0 : plugApparent !== null ? Math.min(power / 0.95, Math.max(power, plugApparent - outdoor - base)) : power;
  const reactive = Math.sign(num('air_conditioning_reactive_power') ?? 0) * Math.sqrt(Math.max(0, apparent * apparent - power * power));
  items.getItem('e_car_power').postUpdate(Quantity(power.toFixed(2) + ' W'));
  items.getItem('e_car_apparent_power').postUpdate(Quantity(apparent.toFixed(2) + ' VA'));
  items.getItem('e_car_reactive_power').postUpdate(Quantity(reactive.toFixed(2) + ' var'));
  items.getItem('e_car_power_factor').postUpdate((apparent > 0 ? power / apparent : 0).toFixed(2));
  if (voltage !== null && voltage > 0) {
    items.getItem('e_car_voltage').postUpdate(Quantity(voltage.toFixed(2) + ' V'));
    items.getItem('e_car_current').postUpdate(Quantity((apparent / voltage).toFixed(3) + ' A'));
  }
}
// the car has no switch of its own; this mirrors the relay of the air conditioning's Shelly EM, which is
// wired to nothing
const plugSwitch = items.getItem('air_conditioning_switch').state;
if (plugSwitch === 'ON' || plugSwitch === 'OFF') {
  items.getItem('e_car_switch').postUpdate(plugSwitch);
}
