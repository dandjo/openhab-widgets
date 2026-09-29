#!/usr/bin/env python3
"""Give every push notification of the rules a German text: the appliances' finished messages, the refrigerator's and
the water meter's warnings, the heat pump's and the water meter's errors and the ventilation's CO2 alerts. Numbers are
formatted as the items show them (whole degrees, U/min, ppm); texts the devices send (Miele programmes and drying
targets, set to German by the account's locale; the water meter's error text) pass through as they come.
Usage: notifications_de_update.py check|apply   (with openHAB stopped for apply)"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "..", "awattar_migrate.py")).read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
NAME = "automation_rules.json"
REPLACE = {
    "dishwasher_finished": [
        ("'Dishwasher is ready!'", "'Geschirrspüler ist fertig!'")],
    "tumble_dryer_finished": [
        ("'Tumble Dryer is ready!'", "'Wäschetrockner ist fertig!'")],
    "washing_machine_1_finished": [
        ("'Washing Machine 1 is ready!'", "'Waschmaschine 1 ist fertig!'")],
    "washing_machine_2_finished": [
        ("'Washing Machine 2 is ready!'", "'Waschmaschine 2 ist fertig!'")],
    "miele_dishwasher_finished": [
        ("'Miele Dishwasher is ready!\\nProgram: '", "'Miele Geschirrspüler ist fertig!\\nProgramm: '")],
    "miele_tumble_dryer_finished": [
        ("'Miele Tumble Dryer is ready!\\nProgram: '", "'Miele Wäschetrockner ist fertig!\\nProgramm: '"),
        ("'\\nDrying Target: '", "'\\nTrocknungsziel: '")],
    "miele_washing_machine_finished": [
        ("'Miele Washing Machine is ready!\\nProgram: '", "'Miele Waschmaschine ist fertig!\\nProgramm: '"),
        ("message += '\\nTarget Temperature: ' + target_temp_item.state;",
         "message += '\\nZieltemperatur: ' + Math.round(target_temp_item.numericState) + ' °C';"),
        ("message += '\\nSpinning Speed: ' + spinning_speed_item.state;",
         "message += '\\nSchleuderdrehzahl: ' + Math.round(spinning_speed_item.numericState) + ' U/min';")],
    "refrigerator_watchdog": [
        ("'Warning: Refrigerator power consumption is above normal, the door is possibly open!'",
         "'Warnung: Der Kühlschrank verbraucht mehr Strom als üblich, die Tür steht möglicherweise offen!'")],
    "ventilation_management": [
        ("'Netatmo Weatherstation: CO2 high at ' + co2_item.state",
         "'Netatmo Wetterstation: CO2 hoch, ' + Math.round(co2_item.numericState) + ' ppm'"),
        ("'Netatmo Weatherstation: CO2 back to normal at ' + co2_item.state",
         "'Netatmo Wetterstation: CO2 wieder normal, ' + Math.round(co2_item.numericState) + ' ppm'")],
    "heatpump_error": [
        ("'Heatpump Error!\\nType: ' + error_type + '\\nCode: '",
         "'Wärmepumpe meldet einen Fehler!\\nTyp: ' + ({Warning: 'Warnung', Error: 'Fehler'}[error_type] || error_type)\n"
         "        + '\\nCode: '")],
    "water_meter_error": [
        ("'Water Meter Error!\\n' + error", "'Wasserzähler meldet einen Fehler!\\n' + error")],
    "water_meter_watchdog": [
        ("'Warning: Water meter is offline!'", "'Warnung: Der Wasserzähler ist offline!'"),
        ("'Warning: Constant flow measured at water meter for ' + threshold_flow_minutes + ' minutes.\\nCheck for leaks!'",
         "'Warnung: Der Wasserzähler misst seit ' + threshold_flow_minutes + ' Minuten ununterbrochen Durchfluss.\\n'\n"
         "        + 'Bitte auf Lecks prüfen!'")],
}
data, enc = m.detect(m.DB + NAME)
for uid, pairs in REPLACE.items():
    (action,) = data[uid]["value"]["actions"]
    script = action["configuration"]["script"]
    for old, new in pairs:
        assert script.count(old) == 1, (uid, old)
        script = script.replace(old, new)
    action["configuration"]["script"] = script
    print(f"{uid}: {len(pairs)} text(s)")
text = m.encode(data, *enc)
print(f"{NAME}: encoder html={enc[0]} newline={enc[1]} ok; {len(REPLACE)} rules")
if sys.argv[1] == "apply":
    open(m.DB + NAME, "w", encoding="utf-8").write(text)
    print("written")
