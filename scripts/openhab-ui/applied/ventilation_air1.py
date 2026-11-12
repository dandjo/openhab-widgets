#!/usr/bin/env python3
"""The ventilation's automatics on the Apollo AIR-1 (user, 2026-11-11): the rule ventilation_management takes CO2 and
humidity from the AIR-1 instead of the Netatmo station. While the AIR-1 is offline its items keep their last value,
so an enabled CO2 or humidity automatic then counts as lacking its reading and the level stays, and the CO2 alert
waits. The alert's flag moves to the new item apollo_air_1_co2_alert (the old netatmo_weatherstation_co2_alert hung
in the Netatmo's group), its pushes name the AIR-1, and in the sitemap it moves from the Netatmo's frame Innen to the
ventilation's. The AIR-1's state topics are retained, so after a restart its readings are back at once.
Since the evening of 2026-11-11 (user) an AIR-1 reading also counts as lacking when its last update is more than 3
minutes old (CO2 comes every 60 s, humidity every 10 s, each as an update even when unchanged): a reading that stopped
with the device online, as a sensor that stopped measuring, would otherwise steer the level and the alert.
Instead of holding the level for as long as readings lack, the rule sets level 2 (Mittel) once they have lacked for
30 minutes and no timer holds a level, with a push naming them, and pushes again once they are back (user, same
evening); it keeps the episode in its cache.private, which a PUT of the rule empties.
Since 2026-11-12 (user) the AIR-1's VOC index boosts the ventilation: a rise of 50 within 5 minutes or the index
crossing 250 means level 3 for up to 60 minutes (cooking, toasting; the index is relative to its last day, so its rise
says more than its level), sooner over once it is back within 20 of where it rose from. The boost outranks the CO2 and
the dry air's level 1, not the hot outdoor air's, and waits for a running timer as every automatic level does; it does
not start in the AIR-1's first hour after a restart, while the index learns anew.
apply creates the new item with the old one's state, PUTs the rule and the sitemap, then removes the old item; its
history stays in InfluxDB.
Usage: ventilation_air1.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
import copy
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8080/rest"
TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
RULE = "ventilation_management"
OLD, NEW = "netatmo_weatherstation_co2_alert", "apollo_air_1_co2_alert"
SITEMAP = "/ui/components/system:sitemap/default"
NEW_ITEM = {"type": "Switch", "name": NEW, "label": "Apollo AIR-1 CO2-Warnung",
            "category": "material:notification_important",
            "groupNames": ["apollo_air_1", "influxdb_change", "mapdb_change_restore"], "tags": ["Switch"]}
STATE_DESCRIPTION = {"value": " ", "config": {"pattern": "%s", "options": "ON=An,OFF=Aus", "readOnly": True}}
REPLACE = [
    ("""const co2_item = items.getItem('netatmo_weatherstation_co2');
const co2_alert_item = items.getItem('netatmo_weatherstation_co2_alert');

// calculate level and debounce; while an enabled automatic lacks its reading (NULL after a restart, UNDEF while the
// Netatmo cloud fails) the level stays, as a missing value would compare as 0

const lacks = (management, item) => items.getItem(management).state === 'ON'
  && items.getItem(item).numericState === null;
const missing = lacks('ventilation_co2_management', 'netatmo_weatherstation_co2')
  || lacks('ventilation_humidity_management', 'netatmo_weatherstation_atmospheric_humidity')
  || lacks('ventilation_temperature_management', 'espaltherma_ext_ambient_temp');""",
     """const co2_item = items.getItem('apollo_air_1_co2');
const co2_alert_item = items.getItem('apollo_air_1_co2_alert');

// calculate level and debounce; while an enabled automatic lacks its reading (NULL or UNDEF, or the Apollo AIR-1
// offline, whose items keep their last value) the level stays, as a missing value would compare as 0

const air1_online = items.getItem('apollo_air_1_online').state === 'ON';
const lacks = (management, item, air1) => items.getItem(management).state === 'ON'
  && (items.getItem(item).numericState === null || (air1 && !air1_online));
const missing = lacks('ventilation_co2_management', 'apollo_air_1_co2', true)
  || lacks('ventilation_humidity_management', 'apollo_air_1_humidity', true)
  || lacks('ventilation_temperature_management', 'espaltherma_ext_ambient_temp', false);"""),
    ("items.getItem('netatmo_weatherstation_atmospheric_humidity').numericState <= 35",
     "items.getItem('apollo_air_1_humidity').numericState <= 35"),
    ("""// alert CO2 level and debounce, only with a reading

if (co2_item.numericState !== null && !co2_alert_item""",
     """// alert CO2 level and debounce, only with a reading of the AIR-1 online

if (co2_item.numericState !== null && air1_online && !co2_alert_item"""),
    ("'Netatmo Wetterstation: CO2 hoch, '", "'Apollo AIR-1: CO2 hoch, '"),
    ("'Netatmo Wetterstation: CO2 wieder normal, '", "'Apollo AIR-1: CO2 wieder normal, '"),
]
# the readings' age, on top of REPLACE
FRESH = [
    ("""// offline, whose items keep their last value) the level stays, as a missing value would compare as 0""",
     """// offline, whose items keep their last value, or its reading not updated for more than 3 minutes, as a sensor
// that stopped measuring with the device online; CO2 comes every 60 s, humidity every 10 s) the level stays, as a
// missing value would compare as 0"""),
    ("""const air1_online = items.getItem('apollo_air_1_online').state === 'ON';
const lacks = (management, item, air1) => items.getItem(management).state === 'ON'
  && (items.getItem(item).numericState === null || (air1 && !air1_online));""",
     """const air1_online = items.getItem('apollo_air_1_online').state === 'ON';
const air1_since = time.ZonedDateTime.now().minusMinutes(3);
const air1_fresh = (name) => {
  const at = items.getItem(name).lastStateUpdateTimestamp;
  return air1_online && at !== null && at !== undefined && !at.isBefore(air1_since);
};
const lacks = (management, item, air1) => items.getItem(management).state === 'ON'
  && (items.getItem(item).numericState === null || (air1 && !air1_fresh(item)));"""),
    ("""// alert CO2 level and debounce, only with a reading of the AIR-1 online

if (co2_item.numericState !== null && air1_online && !co2_alert_item""",
     """// alert CO2 level and debounce, only with a current reading of the AIR-1 online

if (co2_item.numericState !== null && air1_fresh('apollo_air_1_co2') && !co2_alert_item"""),
]
# the fallback after 30 minutes of lacking readings, on top of FRESH
FALLBACK = [
    ("""const missing = lacks('ventilation_co2_management', 'apollo_air_1_co2', true)
  || lacks('ventilation_humidity_management', 'apollo_air_1_humidity', true)
  || lacks('ventilation_temperature_management', 'espaltherma_ext_ambient_temp', false);""",
     """const lacking = [['ventilation_co2_management', 'apollo_air_1_co2', true, 'Apollo AIR-1 CO2'],
  ['ventilation_humidity_management', 'apollo_air_1_humidity', true, 'Apollo AIR-1 Feuchte'],
  ['ventilation_temperature_management', 'espaltherma_ext_ambient_temp', false, 'Außentemperatur']]
  .filter((r) => lacks(r[0], r[1], r[2])).map((r) => r[3]);
const missing = lacking.length > 0;

// readings lacking for 30 minutes: rather than hold the level for as long as they lack, level 2 (Mittel) once no
// timer holds a level, with a push naming them; another push once they are back (user, 2026-11-11)
const auto_on = items.getItem('ventilation_management').state === 'ON';
if (!auto_on || !missing) {
  if (auto_on && cache.private.get('lacking_fallback')) {
    actions.NotificationAction.sendBroadcastNotification('Lüftung: Werte wieder da, die Automatik regelt wieder');
  }
  cache.private.remove('lacking_since');
  cache.private.remove('lacking_fallback');
} else if (!cache.private.get('lacking_since')) {
  cache.private.put('lacking_since', Date.now());
} else if (!cache.private.get('lacking_fallback') && Date.now() - cache.private.get('lacking_since') >= 30 * 60000
  && items.getItem('ventilation_timer').numericState <= 0) {
  cache.private.put('lacking_fallback', true);
  items.getItem('esplyfterl_level').sendCommandIfDifferent('2');
  actions.NotificationAction.sendBroadcastNotification('Lüftung: seit '
    + Math.round((Date.now() - cache.private.get('lacking_since')) / 60000) + ' Minuten fehlen Werte ('
    + lacking.join(', ') + '), Stufe Mittel');
}"""),
]
# the VOC boost, on top of FALLBACK
VOC = [
    ("""}

if (items.getItem('ventilation_management').state === 'ON' && items.getItem('ventilation_timer').numericState <= 0
  && !missing) {
  let level_to_set = 2;""",
     """}

// VOC boost (user, 2026-11-12): cooking and the like show as a fast rise of the AIR-1's VOC index, which is relative
// to its last day, so its rise says more than its level. A rise of 50 within 5 minutes, or the index crossing 250,
// starts a boost: level 3 for up to 60 minutes, sooner over once the index is back within 20 of where it rose from.
// Not in the AIR-1's first hour after a restart, while its index learns anew, nor on a reading older than 3 minutes.
const voc = items.getItem('apollo_air_1_voc_index').numericState;
const voc_ok = voc !== null && air1_fresh('apollo_air_1_voc_index')
  && items.getItem('apollo_air_1_uptime').numericState >= 3600;
let voc_hist = JSON.parse(cache.private.get('voc_hist') || '[]').filter((h) => Date.now() - h[0] <= 5.5 * 60000);
let voc_boost = JSON.parse(cache.private.get('voc_boost') || 'null');
if (voc_ok) {
  const low = voc_hist.reduce((a, h) => Math.min(a, h[1]), voc);
  const last = voc_hist.length ? voc_hist[voc_hist.length - 1][1] : voc;
  if (!voc_boost && (voc - low >= 50 || (last < 250 && voc >= 250))) {
    // where it rose from; for an index that crept over 250, at least 50 below it, or the boost would end at once
    voc_boost = { since: Date.now(), base: Math.min(low, voc - 50) };
  }
  voc_hist.push([Date.now(), voc]);
} else {
  voc_hist = [];
}
if (voc_boost && (Date.now() - voc_boost.since >= 60 * 60000 || (voc_ok && voc <= voc_boost.base + 20))) {
  voc_boost = null;
}
cache.private.put('voc_hist', JSON.stringify(voc_hist));
if (voc_boost) {
  cache.private.put('voc_boost', JSON.stringify(voc_boost));
} else {
  cache.private.remove('voc_boost');
}

if (items.getItem('ventilation_management').state === 'ON' && items.getItem('ventilation_timer').numericState <= 0
  && !missing) {
  let level_to_set = 2;"""),
    ("""    level_to_set = 1;
  }
  if (
    items.getItem('ventilation_temperature_management').state === 'ON'""",
     """    level_to_set = 1;
  }
  // the VOC boost outranks the CO2 and the dry air, not the hot outdoor air below
  if (voc_boost) {
    level_to_set = 3;
  }
  if (
    items.getItem('ventilation_temperature_management').state === 'ON'"""),
]
VOC_DESCRIPTION = [("ebenso wenn die Werte wieder da sind.",
                    "ebenso wenn die Werte wieder da sind. Steigt der VOC-Index des AIR-1 in 5 Minuten um 50 oder über "
                    "250, gilt bis zu 60 Minuten Stufe 3, auch bei trockener Luft, nicht ab 30 °C außen und nicht in "
                    "der ersten Stunde nach einem Neustart des AIR-1.")]
FALLBACK_DESCRIPTION = [("seit über 3 Minuten nicht aktualisiert, bleibt die Stufe.",
                         "seit über 3 Minuten nicht aktualisiert, bleibt die Stufe; fehlen Werte 30 Minuten lang, "
                         "setzt die Regel Stufe 2, sobald kein Timer läuft, und meldet das per Push, ebenso wenn die "
                         "Werte wieder da sind.")]
FRESH_DESCRIPTION = [("Fehlt eine Messung oder ist der AIR-1 offline, bleibt die Stufe.",
                      "Fehlt eine Messung, ist der AIR-1 offline oder ein Wert von ihm seit über 3 Minuten nicht "
                      "aktualisiert, bleibt die Stufe.")]
DESCRIPTION = [("nach CO2, Feuchte und Außentemperatur",
                "nach CO2 und Feuchte des Apollo AIR-1 und der Außentemperatur"),
               ("Fehlt eine Messung, bleibt die Stufe.",
                "Fehlt eine Messung oder ist der AIR-1 offline, bleibt die Stufe.")]


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


def put_text(path, text):
    req = urllib.request.Request(BASE + path, method="PUT", data=text.encode(),
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "text/plain"})
    with urllib.request.urlopen(req) as r:
        return r.status


def replaced(text, pairs, what):
    for old, new in pairs:
        assert text.count(old) == 1, f"{what}: {old[:70]!r} found {text.count(old)} times"
        text = text.replace(old, new)
    return text


def frames(node, found):
    """Every Frame of the sitemap with the label of the widget it belongs to."""
    for slot in (node.get("slots") or {}).values():
        for child in slot:
            if child.get("component") == "Frame":
                found.append((node.get("config", {}).get("label"), child))
            frames(child, found)
    return found


def move_alert(sitemap):
    """The CO2-Warnung entry out of the frame under Innen (the Netatmo) into the ventilation's first frame, after its
    automatics, on the new item."""
    fs = frames(sitemap, [])
    (inner,) = [f for parent, f in fs if parent == "Innen"
                and any(w.get("config", {}).get("item") == OLD for w in f["slots"]["widgets"])]
    vent = [f for parent, f in fs if parent == "Lüftung"][0]
    widgets = inner["slots"]["widgets"]
    (entry,) = [w for w in widgets if w.get("config", {}).get("item") == OLD]
    widgets.remove(entry)
    entry = copy.deepcopy(entry)
    text = json.dumps(entry)
    entry = json.loads(text.replace(f'"{OLD}"', f'"{NEW}"'))
    target = vent["slots"]["widgets"]
    after = [i for i, w in enumerate(target) if w.get("config", {}).get("item") == "ventilation_temperature_management"]
    assert after, "Temperatur-Automatik not in the ventilation's frame"
    target.insert(after[0] + 1, entry)
    return sitemap


apply = sys.argv[1] == "apply"
for n in ("apollo_air_1", "apollo_air_1_co2", "apollo_air_1_humidity", "apollo_air_1_online", "apollo_air_1_voc_index",
          "apollo_air_1_uptime", "influxdb_change",
          "mapdb_change_restore"):
    assert call("GET", f"/items/{n}")[0] == 200, f"item {n} missing"
status, rule = call("GET", f"/rules/{RULE}")
assert status == 200, f"rule {RULE}: {status}"
(action,) = rule["actions"]
script = action["configuration"]["script"]
done = "apollo_air_1_co2_alert" in script
print(f"rule {RULE}:", "already on the AIR-1" if done else f"{len(REPLACE)} replacements")
if not done:
    script = action["configuration"]["script"] = replaced(script, REPLACE, "script")
    rule["description"] = replaced(rule["description"], DESCRIPTION, "description")
fresh = "air1_fresh" in script
print(f"rule {RULE}:", "checks the readings' age" if fresh else f"{len(FRESH)} replacements for the readings' age")
if not fresh:
    script = action["configuration"]["script"] = replaced(script, FRESH, "script")
    rule["description"] = replaced(rule["description"], FRESH_DESCRIPTION, "description")
fallback = "lacking_since" in script
print(f"rule {RULE}:", "falls back after 30 minutes" if fallback else f"{len(FALLBACK)} replacement for the fallback")
if not fallback:
    script = action["configuration"]["script"] = replaced(script, FALLBACK, "script")
    rule["description"] = replaced(rule["description"], FALLBACK_DESCRIPTION, "description")
voc = "voc_boost" in script
print(f"rule {RULE}:", "has the VOC boost" if voc else f"{len(VOC)} replacements for the VOC boost")
if not voc:
    action["configuration"]["script"] = replaced(script, VOC, "script")
    rule["description"] = replaced(rule["description"], VOC_DESCRIPTION, "description")
old_status, old_item = call("GET", f"/items/{OLD}")
new_exists = call("GET", f"/items/{NEW}")[0] == 200
print(f"item {NEW}:", "exists" if new_exists else "missing", f"| item {OLD}:",
      old_item["state"] if old_status == 200 else "gone")
status, sitemap = call("GET", SITEMAP)
assert status == 200, f"sitemap: {status}"
moved = NEW in json.dumps(sitemap)
print("sitemap:", "alert in the ventilation's frame" if moved else "alert to move")
if not moved:
    sitemap = move_alert(sitemap)
if not apply:
    sys.exit(0)

if not new_exists:
    print("PUT item", NEW, call("PUT", f"/items/{NEW}", NEW_ITEM)[0])
    print("PUT stateDescription", call("PUT", f"/items/{NEW}/metadata/stateDescription", STATE_DESCRIPTION)[0])
    state = old_item["state"] if old_status == 200 and old_item["state"] in ("ON", "OFF") else "OFF"
    print("state", state, put_text(f"/items/{NEW}/state", state))
if not done or not fresh or not fallback or not voc:
    body = {k: v for k, v in rule.items() if k not in ("status", "editable", "templateState")}
    print("PUT rule", call("PUT", f"/rules/{RULE}", body)[0])
if not moved:
    print("PUT sitemap", call("PUT", SITEMAP, sitemap)[0])
if old_status == 200:
    print("DELETE item", OLD, call("DELETE", f"/items/{OLD}")[0])
