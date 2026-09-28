#!/usr/bin/env python3
"""E-Car rules, second version: a small rest goes to the running air conditioner, energy is the integrated power.
Usage: e_car_fix2.py check|apply   (run as root with openHAB stopped for apply)
"""
import sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)

POWER_SCRIPT = """// The E-Car charges behind the air conditioning's plug. Faikin reports the power of the outdoor unit only,
// so the rest of the plug's measurement is the car, plus a few watts of standby and an LED light.
// While the air conditioner is on, a small rest is its indoor unit (fan and electronics, about 20 W in fan
// mode): the car never charges below 1.4 kW. The air conditioner's share is taken as purely active power.
const num = (name) => items.getItem(name).numericState;
const plug = num('air_conditioning_power');
const ac = num('faikout_perfera_power') ?? 0;
const acOn = items.getItem('faikout_perfera_switch').state === 'ON';
if (plug !== null) {
  const rest = Math.max(0, plug - ac);
  const power = acOn && rest < 300 ? 0 : rest;
  const plugApparent = num('air_conditioning_apparent_power');
  const apparent = power === 0 ? 0 : plugApparent !== null ? Math.max(power, plugApparent - ac) : power;
  const reactive = Math.sign(num('air_conditioning_reactive_power') ?? 0) * Math.sqrt(Math.max(0, apparent * apparent - power * power));
  const voltage = num('air_conditioning_voltage');
  items.getItem('e_car_power').postUpdate(Quantity(power.toFixed(2) + ' W'));
  items.getItem('e_car_apparent_power').postUpdate(Quantity(apparent.toFixed(2) + ' VA'));
  items.getItem('e_car_reactive_power').postUpdate(Quantity(reactive.toFixed(2) + ' var'));
  items.getItem('e_car_power_factor').postUpdate((apparent > 0 ? power / apparent : 0).toFixed(2));
  if (voltage !== null && voltage > 0) {
    items.getItem('e_car_voltage').postUpdate(Quantity(voltage.toFixed(2) + ' V'));
    items.getItem('e_car_current').postUpdate(Quantity((apparent / voltage).toFixed(3) + ' A'));
  }
}
// the car has no switch of its own; this mirrors the plug, which also cuts the air conditioner
const plugSwitch = items.getItem('air_conditioning_switch').state;
if (plugSwitch === 'ON' || plugSwitch === 'OFF') {
  items.getItem('e_car_switch').postUpdate(plugSwitch);
}"""

ENERGY_SCRIPT = """const persistEnergy = function(item, value, unit = null, precision = null) {
  const u = unit !== null ? ' ' + unit : ' Wh';
  const p = precision !== null ? precision : 3;
  const v = Quantity(value.toFixed(p) + u);
  const last_update = items.getItem(item).persistence.lastUpdate();
  if (last_update === null || last_update.isBefore(time.toZDT('00:00'))) {
    items.getItem(item).persistence.persist(time.toZDT('00:00'), Quantity('0' + u), 'influxdb');
    items.getItem(item).postUpdate(v);
    return;
  }
  items.getItem(item).postUpdate(v);
};

// E-Car energy today: its power integrated since midnight (the time-weighted average times the hours elapsed)
const midnight = time.toZDT('00:00');
const minutes = time.Duration.between(midnight, time.toZDT()).toMillis() / 60000;
if (minutes >= 2) {
  const average = items.getItem('e_car_power').persistence.averageSince(midnight, 'influxdb');
  if (average !== null && average.numericState !== null) {
    const today = average.numericState * minutes / 60 / 1000;
    // the total is the last total stored before midnight plus today, the same on every run and after restarts
    const totalItem = items.getItem('e_car_energy_total');
    const atMidnight = totalItem.persistence.persistedState(midnight, 'influxdb');
    const base = atMidnight !== null && atMidnight.numericState !== null ? atMidnight.numericState : 0;
    persistEnergy('e_car_energy_today', today, 'kWh');
    totalItem.postUpdate(Quantity((base + today).toFixed(3) + ' kWh'));
  }
}"""


def migrate_rules(d):
    p = d["e_car_power"]["value"]
    p["actions"][0]["configuration"]["script"] = POWER_SCRIPT
    p["triggers"] = [{"id": str(i + 1), "configuration": {"itemName": n}, "type": "core.ItemStateChangeTrigger"}
                     for i, n in enumerate(["air_conditioning_power", "faikout_perfera_power", "faikout_perfera_switch",
                                            "air_conditioning_switch"])]
    p["actions"][0]["id"] = str(len(p["triggers"]) + 1)
    p["description"] = ("Fills the E-Car's power items from the air conditioning's plug minus Faikin's power, a small "
                        "rest going to the running air conditioner, and mirrors the plug's switch.")
    e = d["e_car_energy"]["value"]
    e["actions"][0]["configuration"]["script"] = ENERGY_SCRIPT
    e["description"] = "E-Car energy today, its power integrated since midnight, and the total on top of yesterday's."
    return d


if __name__ == "__main__":
    data, enc = m.detect(m.DB + "automation_rules.json")
    text = m.encode(migrate_rules(data), *enc)
    print("automation_rules.json encoder", enc, "ok")
    if sys.argv[1] == "apply":
        open(m.DB + "automation_rules.json", "w", encoding="utf-8").write(text)
        print("written")
