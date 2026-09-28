#!/usr/bin/env python3
"""E-Car items built like the Nous (Tasmota) plug items, without thing and links, and the two rules that fill them.

The car charges behind the air conditioning's plug; Faikin reports the air conditioner's own power, the rest is the car.
Usage: e_car.py check|apply   (run as root with openHAB stopped for apply)
"""
import copy
import sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)

PLUG, CAR = "air_conditioning", "e_car"
SUFFIXES = ["apparent_power", "current", "energy_today", "energy_total", "power", "power_factor", "reactive_power",
            "switch", "voltage"]

POWER_SCRIPT = """// The E-Car charges behind the air conditioning's plug. Faikin reports the air conditioner's own power,
// so the rest of the plug's measurement is the car, plus a few watts of standby and an LED light.
// The air conditioner's share is taken as purely active power, Faikin reports nothing else.
const num = (name) => items.getItem(name).numericState;
const plug = num('air_conditioning_power');
const ac = num('faikout_perfera_power') ?? 0;
if (plug !== null) {
  const power = Math.max(0, plug - ac);
  const plugApparent = num('air_conditioning_apparent_power');
  const apparent = plugApparent !== null ? Math.max(power, plugApparent - ac) : power;
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

// E-Car energy today: the plug's energy today minus the air conditioner's, which is Faikin's power
// integrated since midnight (its time-weighted average times the hours elapsed)
const midnight = time.toZDT('00:00');
const minutes = time.Duration.between(midnight, time.toZDT()).toMillis() / 60000;
const plugToday = items.getItem('air_conditioning_energy_today').numericState;

// the plug resets its counter at midnight a few seconds apart from this clock
if (minutes >= 2 && plugToday !== null) {
  const average = items.getItem('faikout_perfera_power').persistence.averageSince(midnight, 'influxdb');
  const acToday = average !== null && average.numericState !== null ? average.numericState * minutes / 60 / 1000 : 0;
  const today = Math.max(0, plugToday - acToday);

  // the total is the last total stored before midnight plus today, the same on every run and after restarts
  const totalItem = items.getItem('e_car_energy_total');
  const atMidnight = totalItem.persistence.persistedState(midnight, 'influxdb');
  const base = atMidnight !== null && atMidnight.numericState !== null ? atMidnight.numericState : 0;
  persistEnergy('e_car_energy_today', today, 'kWh');
  totalItem.postUpdate(Quantity((base + today).toFixed(3) + ' kWh'));
}"""


def rule(uid, name, description, triggers, script):
    return {"class": "org.openhab.core.automation.dto.RuleDTO", "value": {
        "triggers": [{"id": str(i + 1), **t} for i, t in enumerate(triggers)],
        "conditions": [],
        "actions": [{"inputs": {}, "id": str(len(triggers) + 1),
                     "configuration": {"script": script, "type": "application/javascript"},
                     "type": "script.ScriptAction"}],
        "configuration": {}, "configDescriptions": [], "templateState": "no-template", "uid": uid, "name": name,
        "tags": [], "visibility": "VISIBLE", "description": description}}


def changed(item):
    return {"configuration": {"itemName": item}, "type": "core.ItemStateChangeTrigger"}


def migrate_items(d):
    group = copy.deepcopy(d[PLUG])
    group["value"].update(label="E-Car", tags=["Car"], category="garage")
    assert CAR not in d
    d = m.insert(d, CAR, group)
    for suffix in SUFFIXES:
        item = copy.deepcopy(d[f"{PLUG}_{suffix}"])
        v = item["value"]
        v["groupNames"] = [CAR if g == PLUG else g for g in v["groupNames"]]
        v["label"] = v["label"].replace("Air Conditioning", "E-Car")
        assert f"{CAR}_{suffix}" not in d
        d = m.insert(d, f"{CAR}_{suffix}", item)
    return d


def migrate_metadata(d):
    for key in [k for k in d if k.split(":", 1)[1] in {f"{PLUG}_{s}" for s in SUFFIXES}]:
        ns, item = key.split(":", 1)
        new_item = CAR + item[len(PLUG):]
        md = copy.deepcopy(d[key])
        md["value"]["key"] = {"segments": [ns, new_item], "uid": f"{ns}:{new_item}"}
        assert f"{ns}:{new_item}" not in d
        d = m.insert(d, f"{ns}:{new_item}", md)
    key = f"stateDescription:{CAR}_switch"  # a mirror of the plug: not switchable on its own
    assert key not in d
    return m.insert(d, key, {"class": "org.openhab.core.items.Metadata",
                             "value": {"key": {"segments": ["stateDescription", f"{CAR}_switch"], "uid": key},
                                       "value": " ", "configuration": {"readOnly": True}}})


def migrate_rules(d):
    for uid in ("e_car_power", "e_car_energy"):
        assert uid not in d
    d = m.insert(d, "e_car_power", rule(
        "e_car_power", "E-Car Power",
        "Fills the E-Car's power items from the air conditioning's plug minus Faikin's power, and mirrors the plug's switch.",
        [changed("air_conditioning_power"), changed("faikout_perfera_power"), changed("air_conditioning_switch")],
        POWER_SCRIPT))
    return m.insert(d, "e_car_energy", rule(
        "e_car_energy", "E-Car Energy",
        "E-Car energy today and total: the air conditioning plug's energy today minus Faikin's power integrated since midnight.",
        [{"configuration": {"cronExpression": "0 * * * * ? *"}, "type": "timer.GenericCronTrigger"}],
        ENERGY_SCRIPT))


FILES = {"org.openhab.core.items.Item.json": migrate_items,
         "org.openhab.core.items.Metadata.json": migrate_metadata,
         "automation_rules.json": migrate_rules}
results = {}
for name, fn in FILES.items():
    data, enc = m.detect(m.DB + name)
    new = fn(data)
    print(name, "encoder", enc, "entries", len(data), "->", len(new))
    results[name] = m.encode(new, *enc)
if sys.argv[1] == "apply":
    for name, text in results.items():
        open(m.DB + name, "w", encoding="utf-8").write(text)
    print("written")
