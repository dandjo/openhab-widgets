#!/usr/bin/env python3
"""e_car_power: a rest under 300 W is never the car, also while the air conditioner is off (its standby was
counted as charging), and the air conditioner's learned base load comes off the rest while the car charges.
Usage: e_car_standby.py check|apply   (with openHAB stopped for apply)"""
import sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)

OLD_HEAD = """// The E-Car charges behind the air conditioning's plug. Faikin reports the power of the outdoor unit only,
// so the rest of the plug's measurement is the car, plus a few watts of standby and an LED light.
// While the air conditioner is on, a small rest is its indoor unit (fan and electronics, about 20 W in fan
// mode): the car never charges below 1.4 kW. The air conditioner's share is taken as purely active power.
const num = (name) => items.getItem(name).numericState;
const plug = num('air_conditioning_power');
const ac = num('faikout_perfera_power') ?? 0;
const acOn = items.getItem('faikout_perfera_switch').state === 'ON';
if (plug !== null) {
  // while the air conditioner is off the whole plug is the car; the two always add up to the plug
  const rest = Math.max(0, plug - ac);
  const power = !acOn ? plug : rest < 300 ? 0 : rest;
  items.getItem('air_conditioning_unit_power').postUpdate(Quantity(Math.max(0, plug - power).toFixed(2) + ' W'));
  const plugApparent = num('air_conditioning_apparent_power');
  const apparent = power === 0 ? 0 : plugApparent !== null ? Math.max(power, plugApparent - ac) : power;"""
NEW_HEAD = """// The E-Car charges behind the air conditioning's plug. Faikin reports the power of the outdoor unit only;
// the rest of the plug's measurement is the car while it charges, otherwise the air conditioner's own base
// load: standby and an LED light of about 10 W while it is off, the indoor unit (fan and electronics, about
// 20 W in fan mode) while it runs. The car never charges below 1.4 kW, so a rest under 300 W is never the car.
// The base load is learned per state of the air conditioner while the car is idle and comes off the rest
// while it charges. The air conditioner's share is taken as purely active power.
const num = (name) => items.getItem(name).numericState;
const plug = num('air_conditioning_power');
const acOn = items.getItem('faikout_perfera_switch').state === 'ON';
const outdoor = acOn ? (num('faikout_perfera_power') ?? 0) : 0;
if (plug !== null) {
  const rest = Math.max(0, plug - outdoor);
  const key = acOn ? 'base_on' : 'base_off';
  const base = cache.private.get(key, () => (acOn ? 20 : 10));
  let power = 0;
  if (rest >= 300) {
    power = Math.max(0, rest - base);
  } else if (rest < 150) {
    // slowly, so a single odd reading moves it little; the ramp of a charge starting stays out
    cache.private.put(key, base + 0.1 * (rest - base));
  }
  // the two always add up to the plug
  items.getItem('air_conditioning_unit_power').postUpdate(Quantity(Math.max(0, plug - power).toFixed(2) + ' W'));
  const plugApparent = num('air_conditioning_apparent_power');
  const apparent = power === 0 ? 0 : plugApparent !== null ? Math.max(power, plugApparent - outdoor - base) : power;"""
OLD_DESC = ("Teilt die Steckdose der Klimaanlage in E-Auto und Klimaanlage selbst (air_conditioning_unit_power) auf, "
            "nach Leistung und Schalter von Faikin, und spiegelt den Schalter der Steckdose.")
NEW_DESC = ("Teilt die Steckdose der Klimaanlage in E-Auto und Klimaanlage selbst (air_conditioning_unit_power) auf, "
            "nach Leistung und Schalter von Faikin, und spiegelt den Schalter der Steckdose. Unter 300 W lädt das Auto "
            "nicht; die gelernte Grundlast der Klimaanlage (Standby, Innengerät) wird beim Laden abgezogen.")

data, enc = m.detect(m.DB + "automation_rules.json")
r = data["e_car_power"]["value"]
cfg = r["actions"][0]["configuration"]
assert cfg["script"].count(OLD_HEAD) == 1 and r["description"] == OLD_DESC
cfg["script"] = cfg["script"].replace(OLD_HEAD, NEW_HEAD)
r["description"] = NEW_DESC
text = m.encode(data, *enc)
print("e_car_power ok")
if sys.argv[1] == "apply":
    open(m.DB + "automation_rules.json", "w", encoding="utf-8").write(text)
    print("written")
