#!/usr/bin/env python3
"""The Apollo AIR-1 air quality sensor in openHAB (user, 2026-11-10): the MQTT topic thing apollo_air_1 on the broker
mosquitto, one channel per value the device publishes under its topic prefix (its ESPHome firmware with MQTT,
see ~/docs/air-1.md), and the items of the equipment apollo_air_1, linked one to one; apollo_air_1_last_seen is the
time of the device's last message, the uptime channel's timestamp-update. The measurements go into InfluxDB at most
once a minute (the device sends every 10 s to 5 min) and every quarter hour; the diagnostics are not persisted. Three
of the device's settings take commands (user, same day): the SEN55's fan in intervals or running all the time, which
value the LED shows and its brightness; the device sets their state once it took the command (autoupdate off). The
CO2 sensor's calibration to the local outdoor air (user, 2026-11-11): its target, the button and the outcome the
device names with its time; the device refuses unless its last readings are steady and near the target. Its
other settings (offsets, sleep) stay on its web interface; its MiCS-4514 gas values are not taken over, as all six
read NA.
apply creates the thing, or replaces it, then PUTs the items, their metadata and the links.
Usage: AIR1_TOPIC=<the device's topic prefix> apollo_air_1.py check|apply   (on homepi, as pi; the API token from
~/.openhab_token; the prefix, the device's name with its MAC suffix, stands in ~/docs/air-1.md, not here)"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8080/rest"
TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
BRIDGE = "mqtt:broker:mosquitto"
THING = "mqtt:topic:mosquitto:apollo_air_1"
GROUP = "apollo_air_1"
P = GROUP + "_"
TOPIC = os.environ["AIR1_TOPIC"].rstrip("/") + "/"  # the device's topic prefix, its name with the MAC suffix
STATUS_TOPIC = "apollo-air-1/status"  # its birth and last will, without the suffix (ESPHome adds it to the rest only)
UG = "\u00b5g/m\u00b3"  # µg/m³ with the micro sign, as openHAB knows the unit
# what the LED can show (the device's select), with its German labels
LED_SOURCES = {"Off": "Aus", "CO2": "CO₂", "NowCast AQI": "US-AQI", "VOC Index": "VOC-Index"}
LED_OPTIONS = ",".join(f"{k}={v}" for k, v in LED_SOURCES.items())

# the course at most once a minute and a floor of one point every quarter hour
COURSE = ["influxdb_change_at_most_minute", "influxdb_periodic"]


def state(pattern, **cfg):
    return {"stateDescription": {"value": " ", "config": {"pattern": pattern, "readOnly": True, **cfg}}}


def quantity(unit, pattern):
    return {"unit": {"value": unit}, **state(pattern)}


def command(pattern, **cfg):
    """A state description for an item that takes commands; its state comes from the device's answer (autoupdate
    off), not from the command."""
    return {"stateDescription": {"value": " ", "config": {"pattern": pattern, "readOnly": False, **cfg}},
            "autoupdate": {"value": "false"}}


def control(domain, name, **cfg):
    """A channel's configuration for one of the device's settings: its state and command topics."""
    return {"stateTopic": TOPIC + f"{domain}/{name}/state", "commandTopic": TOPIC + f"{domain}/{name}/command", **cfg}


def sensor(name):
    return TOPIC + f"sensor/{name}/state"


# the CO2 calibration's outcome, which the device names in English for its own interface (user, 2026-11-11), in German
# for openHAB's: a managed JS transformation as the item's display pattern; the item's state stays the device's text
CALIBRATION_JS = "config:js:apollo_air_1_co2_calibration"
CALIBRATION_JS_FUNCTION = r"""(function(data) {
  // the AIR-1's calibration outcome, which the device names in English, in German for the UI
  if (data === null || data === undefined || data === 'NULL' || data === 'UNDEF' || data === '') {
    return data;
  }
  var text = String(data);
  var when = '';
  var t = text.match(/ on (\d{4})-(\d\d)-(\d\d) at (\d\d:\d\d)/);
  if (t) {
    when = ' am ' + t[3] + '.' + t[2] + '.' + t[1] + ' ' + t[4];
    text = text.replace(t[0], '');
  }
  var m = text.match(/^Calibrated to (\d+) ppm \(was (\d+) ppm\)$/);
  if (m) {
    return 'Kalibriert auf ' + m[1] + ' ppm' + when + ' (vorher ' + m[2] + ' ppm)';
  }
  m = text.match(/^Not calibrated: (.*)$/);
  if (!m) {
    return String(data);
  }
  var why = m[1];
  var w;
  if (why === 'no target') {
    why = 'kein Zielwert';
  } else if (why === 'less than 3 minutes of readings') {
    why = 'noch keine 3 Minuten Messwerte';
  } else if ((w = why.match(/^readings not steady \((\d+)-(\d+) ppm\)$/))) {
    why = 'Werte schwanken (' + w[1] + ' bis ' + w[2] + ' ppm)';
  } else if ((w = why.match(/^(\d+) ppm is too far from (\d+) ppm$/))) {
    why = w[1] + ' ppm sind keine Außenluft nahe ' + w[2] + ' ppm';
  }
  return 'Nicht kalibriert' + when + ': ' + why;
})(input)
"""
TRANSFORMATION = {"uid": CALIBRATION_JS, "label": "Apollo AIR-1 CO2-Kalibrierung auf Deutsch", "type": "js",
                  "configuration": {"function": CALIBRATION_JS_FUNCTION}}

# suffix: (item type, label after "Apollo AIR-1 ", icon, tags, persistence groups, metadata, channel type, channel
# configuration); the channel's id is the item's name, as on the other MQTT things
POINTS = {
    "co2": ("Number:Dimensionless", "CO2", "co2", ["Measurement", "CO2"], COURSE, quantity("ppm", "%.0f ppm"),
            "number", {"stateTopic": sensor("co2"), "unit": "ppm"}),
    "temperature": ("Number:Temperature", "Temperatur", "thermostat", ["Measurement", "Temperature"], COURSE,
                    quantity("°C", "%.1f %unit%"), "number", {"stateTopic": sensor("sen55_temperature"), "unit": "°C"}),
    "humidity": ("Number:Dimensionless", "Luftfeuchtigkeit", "water_drop", ["Measurement", "Humidity"], COURSE,
                 quantity("%", "%.0f %unit%"), "number", {"stateTopic": sensor("sen55_humidity"), "unit": "%"}),
    "pressure": ("Number:Pressure", "Absoluter Luftdruck", "compress", ["Measurement", "Pressure"], COURSE,
                 quantity("hPa", "%.1f %unit%"), "number", {"stateTopic": sensor("dps310_pressure"), "unit": "hPa"}),
    "pm1": ("Number:Density", "Feinstaub PM1", "grain", ["Measurement", "ParticulateMatter"], COURSE,
            quantity(UG, "%.1f %unit%"), "number",
            {"stateTopic": sensor("pm__1__m_weight_concentration"), "unit": UG}),
    "pm2_5": ("Number:Density", "Feinstaub PM2,5", "grain", ["Measurement", "ParticulateMatter"], COURSE,
              quantity(UG, "%.1f %unit%"), "number",
              {"stateTopic": sensor("pm__2_5__m_weight_concentration"), "unit": UG}),
    "pm4": ("Number:Density", "Feinstaub PM4", "grain", ["Measurement", "ParticulateMatter"], COURSE,
            quantity(UG, "%.1f %unit%"), "number",
            {"stateTopic": sensor("pm__4__m_weight_concentration"), "unit": UG}),
    "pm10": ("Number:Density", "Feinstaub PM10", "grain", ["Measurement", "ParticulateMatter"], COURSE,
             quantity(UG, "%.1f %unit%"), "number",
             {"stateTopic": sensor("pm__10__m_weight_concentration"), "unit": UG}),
    "voc_index": ("Number", "VOC-Index", "air", ["Measurement", "VOC"], COURSE, state("%.0f"), "number",
                  {"stateTopic": sensor("sen55_voc")}),
    "nox_index": ("Number", "NOx-Index", "air", ["Measurement", "AirQuality"], COURSE, state("%.0f"), "number",
                  {"stateTopic": sensor("sen55_nox")}),
    "aqi": ("Number", "Luftqualitätsindex (US-AQI)", "masks", ["Measurement", "AQI"], COURSE, state("%.0f"), "number",
            {"stateTopic": sensor("nowcast_aqi")}),
    "online": ("Switch", "Verbindung", "wifi", ["Status"], [], state("%s", options="ON=Online,OFF=Offline"), "switch",
               {"stateTopic": STATUS_TOPIC, "on": "online", "off": "offline"}),
    "last_seen": ("DateTime", "Zuletzt gemeldet", "schedule", ["Point", "Timestamp"], [], state("%1$ta %1$tR"),
                  None, None),
    "rssi": ("Number:Power", "WLAN-Signal", "network_wifi", ["Measurement", "RSSI"], [], quantity("dBm", "%.0f %unit%"),
             "number", {"stateTopic": sensor("rssi"), "unit": "dBm"}),
    "uptime": ("Number:Time", "Laufzeit", "timer", ["Measurement", "Duration"], [], quantity("s", "%.0f %unit%"),
               "number", {"stateTopic": sensor("uptime"), "unit": "s"}),
    "esp_temperature": ("Number:Temperature", "Chiptemperatur", "memory", ["Measurement", "Temperature"], [],
                        quantity("°C", "%.1f %unit%"), "number",
                        {"stateTopic": sensor("esp_temperature"), "unit": "°C"}),
    "ip_address": ("String", "IP-Adresse", "lan", ["Status"], [], state("%s"), "string",
                   {"stateTopic": sensor("ip_address")}),
    "firmware_version": ("String", "Firmware-Version", "system_update", ["Status"], [], state("%s"), "string",
                         {"stateTopic": sensor("apollo_firmware_version")}),
    "esphome_version": ("String", "ESPHome-Version", "system_update", ["Status"], [], state("%s"), "string",
                        {"stateTopic": sensor("esphome_version")}),
    # the settings; their values as the device's MQTT discovery names them
    "fan_interval": ("Switch", "Lüfter-Intervall", "air", ["Switch"], [],
                     command("%s", options="ON=Intervall,OFF=Dauerbetrieb"), "switch",
                     control("switch", "sen55_fan_interval", on="ON", off="OFF")),
    "led_source": ("String", "LED-Anzeige", "lightbulb", ["Control"], [],
                   command("%s", options=LED_OPTIONS), "string",
                   control("select", "air_quality_led_source", allowedStates=",".join(LED_SOURCES))),
    "led_brightness": ("Number:Dimensionless", "LED-Helligkeit", "brightness_6", ["Setpoint"], [],
                       {"unit": {"value": "%"}, **command("%.0f %unit%", min=5, max=100, step=1)}, "number",
                       control("number", "air_quality_led_brightness", unit="%", min=5, max=100, step=1)),
    # the CO2 calibration (user, 2026-11-11): the target, the button (ESPHome takes PRESS) and the outcome, a text
    # sensor, which ESPHome publishes under sensor/
    "co2_calibration_target": ("Number:Dimensionless", "CO2-Kalibrierziel", "tune", ["Setpoint"], [],
                               {"unit": {"value": "ppm"}, **command("%.0f ppm", min=400, max=500, step=1)}, "number",
                               control("number", "co2_calibration_target", unit="ppm", min=400, max=500, step=1)),
    "co2_calibrate": ("String", "CO2 kalibrieren", "co2", ["Control"], [], command("%s", options="PRESS=Kalibrieren"),
                      "string", {"commandTopic": TOPIC + "button/calibrate_co2/command"}),
    "co2_calibration": ("String", "CO2-Kalibrierung", "co2", ["Status"], [], state(f"JS({CALIBRATION_JS}):%s"),
                        "string", {"stateTopic": sensor("co2_calibration")}),
}
# items linked to another item's channel with a profile: item suffix -> (channel suffix, profile)
PROFILE_LINKS = {"last_seen": ("uptime", "system:timestamp-update")}

ITEMS = {GROUP: {"name": GROUP, "type": "Group", "label": "Apollo AIR-1", "category": "material:co2",
                 "tags": ["AirQualitySensor"], "groupNames": []}}
METADATA = {GROUP: {}}
CHANNELS = []
LINKS = {}
for suffix, (type_, label, icon, tags, groups, meta, ch_type, ch_cfg) in POINTS.items():
    name = P + suffix
    ITEMS[name] = {"name": name, "type": type_, "label": f"Apollo AIR-1 {label}", "category": f"material:{icon}",
                   "tags": tags, "groupNames": [GROUP, *groups]}
    METADATA[name] = meta
    if ch_type:
        uid = f"{THING}:{name}"
        CHANNELS.append({"uid": uid, "id": name, "channelTypeUID": f"mqtt:{ch_type}", "itemType": type_,
                         "kind": "STATE", "label": f"Apollo AIR-1 {label}", "description": "", "defaultTags": [],
                         "properties": {}, "configuration": ch_cfg})
        LINKS[name] = (uid, {})
for suffix, (source, profile) in PROFILE_LINKS.items():
    LINKS[P + suffix] = (f"{THING}:{P}{source}", {"profile": profile})

THING_BODY = {"UID": THING, "thingTypeUID": "mqtt:topic", "bridgeUID": BRIDGE, "label": "Apollo AIR-1",
              "configuration": {}, "properties": {}, "channels": CHANNELS}


def call(method, path, body=None):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    req = urllib.request.Request(BASE + path, method=method, data=data,
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            text = r.read().decode()
            return r.status, json.loads(text) if text.startswith(("{", "[")) else text
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


def q(uid):
    return urllib.parse.quote(uid, safe="")


apply = sys.argv[1] == "apply"
for group in ("influxdb_change_at_most_minute", "influxdb_periodic"):
    assert call("GET", f"/items/{group}")[0] == 200, f"group {group} missing"
assert call("GET", f"/things/{q(BRIDGE)}")[0] == 200, "broker thing missing"
print(f"thing {THING}:", "exists" if call("GET", f"/things/{q(THING)}")[0] == 200 else "missing",
      f"({len(CHANNELS)} channels)")
for name in ITEMS:
    status, item = call("GET", f"/items/{name}")
    print(f"item {name}:", f"exists, state {item['state']}" if status == 200 else "missing")
print(f"transformation {CALIBRATION_JS}:",
      "exists" if call("GET", f"/transformations/{CALIBRATION_JS}")[0] == 200 else "missing")
if apply:
    print("transformation PUT", call("PUT", f"/transformations/{CALIBRATION_JS}", TRANSFORMATION)[0])
    if call("GET", f"/things/{q(THING)}")[0] == 200:
        print("thing PUT", call("PUT", f"/things/{q(THING)}", THING_BODY)[0])
    else:
        print("thing POST", call("POST", "/things", THING_BODY)[0])
    for name, item in ITEMS.items():
        print(f"item {name} PUT", call("PUT", f"/items/{name}", item)[0])
        for namespace, meta in METADATA[name].items():
            print(f"  metadata {namespace} PUT", call("PUT", f"/items/{name}/metadata/{namespace}", meta)[0])
    for name, (uid, cfg) in LINKS.items():
        body = {"itemName": name, "channelUID": uid, "configuration": cfg}
        print(f"link {name} -> {uid.rsplit(':', 1)[1]}{' ' + cfg['profile'] if cfg else ''} PUT",
              call("PUT", f"/links/{name}/{q(uid)}", body)[0])
