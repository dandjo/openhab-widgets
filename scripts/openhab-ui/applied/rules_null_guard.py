#!/usr/bin/env python3
"""Keep the rules from acting on missing readings: after a restart every item that is not restored is NULL until its
source reports (MQTT and Modbus within about two minutes, the clouds later or not at all), and a missing value
compares as 0 in JavaScript while its state is the text NULL or UNDEF. The same audit as ventilation_null_guard.py,
for the other rules:
- heatpump_dhw_management no longer takes a missing heat pump power, inverter frequency or current for an idle
  compressor (and so no longer moves the hot-water setpoint in the middle of a cycle), nor a missing battery state
  of charge for a battery that is not full: it waits for its readings;
- heatpump_metering no longer integrates a missing heat pump power as 0 W, nor a missing inlet or leaving
  temperature as 0 °C (a jump of the heating power): it skips the run, and the next one bridges the gap as it does;
- heatpump_dcop no longer writes a COP of 0 while the energies of today are still unset after a restart;
- heatpump_error and water_meter_error no longer report the text NULL or UNDEF as an error;
- air_conditioning_circuit_power no longer takes the outdoor unit for off while the air conditioner is on and Faikin
  has not reported yet, which booked the air conditioner's power to the E-Car after a restart.
And items whose change a rule reports join mapdb_change_restore, so a restart does not report them again: the heat
pump's error type and codes, the water meter's error and its last report's time (so the watchdog does not call it
offline before its first report), and the Miele finished flags.
Usage: rules_null_guard.py check|apply   (with openHAB stopped for apply)"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "..", "awattar_migrate.py")).read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)

RESTORE = ["espaltherma_error_type", "espaltherma_error_code", "espaltherma_error_detailed_code", "water_meter_error",
           "water_meter_timestamp", "miele_dishwasher_g7465_finished", "miele_tumble_dryer_twc560wp_finished",
           "miele_washing_machine_wwg360_finished"]

REPLACE = {
    "heatpump_dhw_management": [
        ("""// domestic hot water

if (
  items.getItem('heatpump_dhw_management').state === 'ON'
  && items.getItem('pyaltherma_dhw_power').state === 'ON'
) {""",
         """// the readings the management decides on; while one is missing (NULL after a restart) it would compare as 0,
// taking a running compressor for idle and a full battery for not full, so the management waits for them
const missing = ['heatpump_power', 'espaltherma_inv_frequency', 'espaltherma_inv_primary_current',
  'huawei_inverter_energy_storage_soc', 'pyaltherma_dhw_temp_heating']
  .some((n) => items.getItem(n).numericState === null)
  || ['espaltherma_3way_valve_mode', 'espaltherma_bsh_mode']
    .some((n) => ['NULL', 'UNDEF'].includes(items.getItem(n).state));

// domestic hot water

if (
  items.getItem('heatpump_dhw_management').state === 'ON'
  && items.getItem('pyaltherma_dhw_power').state === 'ON'
  && !missing
) {"""),
    ],
    "heatpump_metering": [
        ("""const persistPower = function(item, value, unit = null, precision = null) {
  const u = unit !== null ? ' ' + unit : ' W';""",
         """// a missing heat pump power adds as 0 W, a missing temperature as 0 °C (a jump of the heating power); such a run
// writes nothing and integrates nothing, and the next one bridges the gap as after any short silence
const missing = items.getItem('heatpump_power').numericState === null
  || (items.getItem('espaltherma_operation_mode').state === 'Heating'
    && ['espaltherma_flow_sensor', 'espaltherma_inlet_water_temp', 'espaltherma_leaving_water_temp_before_buh',
      'espaltherma_leaving_water_temp_after_buh'].some((n) => items.getItem(n).numericState === null));

const persistPower = function(item, value, unit = null, precision = null) {
  if (missing) {
    return;
  }
  const u = unit !== null ? ' ' + unit : ' W';"""),
        ("""const persistCop = function(item, value) {
  if (value <= 10) {""",
         """const persistCop = function(item, value) {
  if (!missing && value <= 10) {"""),
        ("""if (Object.values(powers).every(Number.isFinite)) {""",
         """if (!missing && Object.values(powers).every(Number.isFinite)) {"""),
    ],
    "heatpump_dcop": [
        ("""  return q !== null ? q.toUnit('Wh').float : 0;
};

const persistCop = function(item, value) {
  if (value <= 12 && """,
         """  return q !== null ? q.toUnit('Wh').float : null;
};

const persistCop = function(item, value) {
  if (!missing && value <= 12 && """),
        ("""const heating_energy_today = energyWh('espaltherma_heating_energy_today');
""",
         """const heating_energy_today = energyWh('espaltherma_heating_energy_today');
// right after a restart the energies are unset until heatpump_metering writes them; a COP of them would be 0
const missing = [energy_space_today, energy_dhw_today, energy_today, heating_energy_space_today,
  heating_energy_dhw_today, heating_energy_today].some((v) => v === null);
"""),
    ],
    "heatpump_error": [
        ("""if (error_type !== 'Normal') {""",
         """// NULL or UNDEF is no error, only a missing report
if (error_type !== 'Normal' && error_type !== 'NULL' && error_type !== 'UNDEF') {"""),
    ],
    "water_meter_error": [
        ("""if (error && error !== 'no error') {""",
         """// NULL or UNDEF is no error, only a missing report
if (error && error !== 'no error' && error !== 'NULL' && error !== 'UNDEF') {"""),
    ],
    "air_conditioning_circuit_power": [
        ("""if (plug !== null) {""",
         """// the outdoor unit counts as 0 W only while the air conditioner is off; while it is on and Faikin has not reported
// (after a restart), its power would go to the E-Car
if (plug !== null && !(acOn && num('faikout_perfera_power') === null)) {"""),
    ],
}

ITEMS, RULES = "org.openhab.core.items.Item.json", "automation_rules.json"
files = {name: m.detect(m.DB + name) for name in (ITEMS, RULES)}
items, rules = files[ITEMS][0], files[RULES][0]
for n in RESTORE:
    groups = items[n]["value"]["groupNames"]
    assert "mapdb_change_restore" not in groups, n
    groups.append("mapdb_change_restore")
    print(f"{n}: + mapdb_change_restore")
for uid, pairs in REPLACE.items():
    (action,) = rules[uid]["value"]["actions"]
    script = action["configuration"]["script"]
    for old, new in pairs:
        assert script.count(old) == 1, (uid, old[:60])
        script = script.replace(old, new)
    action["configuration"]["script"] = script
    print(f"{uid}: {len(pairs)} replacement(s), script {len(script)} chars")
texts = {ITEMS: m.encode(items, *files[ITEMS][1]), RULES: m.encode(rules, *files[RULES][1])}
if sys.argv[1] == "apply":
    for name, text in texts.items():
        open(m.DB + name, "w", encoding="utf-8").write(text)
    print("written")
