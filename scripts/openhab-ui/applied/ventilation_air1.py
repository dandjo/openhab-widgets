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
says more than its level), sooner over once it is back within 20 of where it rose from. The boost outranks the CO2,
the dry air's level 1 and, since the user asked for it the same night, the hot outdoor air's; it waits for a running
timer as every automatic level does and does not start in the AIR-1's first hour after a restart, while the index
learns anew. It has a switch of its own, ventilation_voc_management (VOC-Automatik, user, the same night), a member of
the automatic's group as the CO2's, on when it is created; while it is off no boost starts and a running one ends. It
stands under the CO2's in the sitemap; the page's row is the generator's (dashboard.py).
The boost's clock is the ventilation's timer (user, the same night): at its start the rule sets the timer to 60
minutes, so the page shows how long level 3 holds, and its early end puts the timer back to 0, as long as the timer
is still the boost's own (it shows about what the boost has left and the level is 3); a timer or level the user
changed stands. Before, the hour lived in cache.private, the timer showed its usual 30 minutes and the early end
came only after them. A boost starts at once over any running timer, whoever set it (user, the same day: a level
chosen by hand loses against the boost; the way out is the switch VOC-Automatik); before, it waited for the timer
and took what was left of its hour, which on its first real morning cost 12 minutes. The rule keeps no clock of its
own any more.
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
# the VOC boost over the hot outdoor air's level 1 as well (user, 2026-11-12), on top of VOC
VOC_HEAT = [
    ("""  // the VOC boost outranks the CO2 and the dry air, not the hot outdoor air below
  if (voc_boost) {
    level_to_set = 3;
  }
  if (
    items.getItem('ventilation_temperature_management').state === 'ON'
    && items.getItem('espaltherma_ext_ambient_temp').numericState >= 30
    && items.getItem('faikout_perfera_switch').state === 'OFF'
  ) {
    level_to_set = 1;
  }""",
     """  if (
    items.getItem('ventilation_temperature_management').state === 'ON'
    && items.getItem('espaltherma_ext_ambient_temp').numericState >= 30
    && items.getItem('faikout_perfera_switch').state === 'OFF'
  ) {
    level_to_set = 1;
  }
  // the VOC boost outranks them all: the CO2, the dry air and the hot outdoor air (user, 2026-11-12)
  if (voc_boost) {
    level_to_set = 3;
  }"""),
]
# the VOC boost's own switch (user, 2026-11-12), on top of VOC_HEAT
VOC_ITEM = "ventilation_voc_management"
VOC_NEW_ITEM = {"type": "Switch", "name": VOC_ITEM, "label": "Lüftung VOC-Automatik", "category": "material:tune",
                "groupNames": ["mapdb_change_restore", "influxdb_change", "ventilation", "ventilation_management"],
                "tags": ["Switch"]}
VOC_SITEMAP = {"component": "Switch", "config": {"icon": "material:bubble_chart", "item": VOC_ITEM,
                                                 "label": "VOC-Automatik"}}
VOC_SWITCH = [
    ("""const voc = items.getItem('apollo_air_1_voc_index').numericState;""",
     """// Only while the VOC automatic is switched on: off, no boost starts and a running one ends.
const voc_on = items.getItem('ventilation_voc_management').state === 'ON';
const voc = items.getItem('apollo_air_1_voc_index').numericState;"""),
    ("""  if (!voc_boost && (voc - low >= 50 || (last < 250 && voc >= 250))) {""",
     """  if (voc_on && !voc_boost && (voc - low >= 50 || (last < 250 && voc >= 250))) {"""),
    ("""if (voc_boost && (Date.now() - voc_boost.since >= 60 * 60000 || (voc_ok && voc <= voc_boost.base + 20))) {""",
     """if (voc_boost && (!voc_on || Date.now() - voc_boost.since >= 60 * 60000
  || (voc_ok && voc <= voc_boost.base + 20))) {"""),
]
# the ventilation's timer as the VOC boost's clock (user, 2026-11-12), on top of VOC_SWITCH: the whole part from the
# boost to the level is replaced
VOC_TIMER = [
    ("""}

// VOC boost (user, 2026-11-12): cooking and the like show as a fast rise of the AIR-1's VOC index, which is relative
// to its last day, so its rise says more than its level. A rise of 50 within 5 minutes, or the index crossing 250,
// starts a boost: level 3 for up to 60 minutes, sooner over once the index is back within 20 of where it rose from.
// Not in the AIR-1's first hour after a restart, while its index learns anew, nor on a reading older than 3 minutes.
// Only while the VOC automatic is switched on: off, no boost starts and a running one ends.
const voc_on = items.getItem('ventilation_voc_management').state === 'ON';
const voc = items.getItem('apollo_air_1_voc_index').numericState;
const voc_ok = voc !== null && air1_fresh('apollo_air_1_voc_index')
  && items.getItem('apollo_air_1_uptime').numericState >= 3600;
let voc_hist = JSON.parse(cache.private.get('voc_hist') || '[]').filter((h) => Date.now() - h[0] <= 5.5 * 60000);
let voc_boost = JSON.parse(cache.private.get('voc_boost') || 'null');
if (voc_ok) {
  const low = voc_hist.reduce((a, h) => Math.min(a, h[1]), voc);
  const last = voc_hist.length ? voc_hist[voc_hist.length - 1][1] : voc;
  if (voc_on && !voc_boost && (voc - low >= 50 || (last < 250 && voc >= 250))) {
    // where it rose from; for an index that crept over 250, at least 50 below it, or the boost would end at once
    voc_boost = { since: Date.now(), base: Math.min(low, voc - 50) };
  }
  voc_hist.push([Date.now(), voc]);
} else {
  voc_hist = [];
}
if (voc_boost && (!voc_on || Date.now() - voc_boost.since >= 60 * 60000
  || (voc_ok && voc <= voc_boost.base + 20))) {
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
  let level_to_set = 2;
  if (items.getItem('ventilation_co2_management').state === 'ON') {
    if (co2_item.numericState >= 1000) {
      level_to_set = 3;
    }
    if (co2_item.numericState < 500) {
      level_to_set = 1;
    }
  }
  if (
    items.getItem('ventilation_humidity_management').state === 'ON'
    && items.getItem('apollo_air_1_humidity').numericState <= 35
  ) {
    level_to_set = 1;
  }
  if (
    items.getItem('ventilation_temperature_management').state === 'ON'
    && items.getItem('espaltherma_ext_ambient_temp').numericState >= 30
    && items.getItem('faikout_perfera_switch').state === 'OFF'
  ) {
    level_to_set = 1;
  }
  // the VOC boost outranks them all: the CO2, the dry air and the hot outdoor air (user, 2026-11-12)
  if (voc_boost) {
    level_to_set = 3;
  }
  items.getItem('esplyfterl_level').sendCommandIfDifferent(String(level_to_set));
}""",
     """}

// VOC boost (user, 2026-11-12): cooking and the like show as a fast rise of the AIR-1's VOC index, which is relative
// to its last day, so its rise says more than its level. A rise of 50 within 5 minutes, or the index crossing 250,
// starts a boost: level 3 with the ventilation's timer set to 60 minutes, so the page shows how long it holds (the
// timer's own rule lifts a timer only up to 30 minutes and leaves a longer one). It is over sooner, the timer back
// at 0, once the index is back within 20 of where it rose from or the VOC automatic is switched off, but only while
// the timer is still the boost's own: it shows about what the boost has left and the level is still 3. A timer or
// a level the user changed stands. A rise during a running timer waits for it and takes what is left of its hour,
// at least the 30 minutes every level change holds.
// Not in the AIR-1's first hour after a restart, while its index learns anew, nor on a reading older than 3 minutes.
const voc_on = items.getItem('ventilation_voc_management').state === 'ON';
const voc = items.getItem('apollo_air_1_voc_index').numericState;
const voc_ok = voc !== null && air1_fresh('apollo_air_1_voc_index')
  && items.getItem('apollo_air_1_uptime').numericState >= 3600;
const timer_item = items.getItem('ventilation_timer');
const timer_min = timer_item.numericState;
let voc_hist = JSON.parse(cache.private.get('voc_hist') || '[]').filter((h) => Date.now() - h[0] <= 5.5 * 60000);
let voc_boost = JSON.parse(cache.private.get('voc_boost') || 'null');
if (voc_ok) {
  const low = voc_hist.reduce((a, h) => Math.min(a, h[1]), voc);
  const last = voc_hist.length ? voc_hist[voc_hist.length - 1][1] : voc;
  if (voc_on && !voc_boost && (voc - low >= 50 || (last < 250 && voc >= 250))) {
    // where it rose from; for an index that crept over 250, at least 50 below it, or the boost would end at once
    voc_boost = { since: Date.now(), base: Math.min(low, voc - 50) };
  }
  voc_hist.push([Date.now(), voc]);
} else {
  voc_hist = [];
}
let voc_start = false;
if (voc_boost) {
  const back = !voc_on || (voc_ok && voc <= voc_boost.base + 20);
  if (voc_boost.timer_from) {
    // started: the timer is its clock
    const left = voc_boost.minutes - Math.floor((Date.now() - voc_boost.timer_from) / 60000);
    const own = timer_min > 0 && Math.abs(timer_min - left) <= 2 && items.getItem('esplyfterl_level').state === '3';
    if (!own) {
      voc_boost = null;  // run out, or the user took the timer or the level over
    } else if (back) {
      // again every minute until the timer shows 0: its countdown, which runs at the same second, may overwrite this
      timer_item.postUpdate(Quantity('0 min'));
    }
  } else if (back || Date.now() - voc_boost.since >= 60 * 60000) {
    voc_boost = null;  // waited for a timer until it was no longer needed
  } else if (auto_on && timer_min <= 0 && !missing) {
    voc_start = true;
  }
}

if (auto_on && timer_min <= 0 && !missing) {
  let level_to_set = 2;
  if (items.getItem('ventilation_co2_management').state === 'ON') {
    if (co2_item.numericState >= 1000) {
      level_to_set = 3;
    }
    if (co2_item.numericState < 500) {
      level_to_set = 1;
    }
  }
  if (
    items.getItem('ventilation_humidity_management').state === 'ON'
    && items.getItem('apollo_air_1_humidity').numericState <= 35
  ) {
    level_to_set = 1;
  }
  if (
    items.getItem('ventilation_temperature_management').state === 'ON'
    && items.getItem('espaltherma_ext_ambient_temp').numericState >= 30
    && items.getItem('faikout_perfera_switch').state === 'OFF'
  ) {
    level_to_set = 1;
  }
  // the VOC boost outranks them all: the CO2, the dry air and the hot outdoor air (user, 2026-11-12)
  if (voc_start) {
    level_to_set = 3;
    // what is left of the boost's hour, at least the 30 minutes every level change holds; the timer first, so that
    // its own rule, which runs on the level's change, finds it set and leaves it
    voc_boost.minutes = Math.max(30, 60 - Math.floor((Date.now() - voc_boost.since) / 60000));
    voc_boost.timer_from = Date.now();
    timer_item.postUpdate(Quantity(voc_boost.minutes + ' min'));
  }
  items.getItem('esplyfterl_level').sendCommandIfDifferent(String(level_to_set));
}
cache.private.put('voc_hist', JSON.stringify(voc_hist));
if (voc_boost) {
  cache.private.put('voc_boost', JSON.stringify(voc_boost));
} else {
  cache.private.remove('voc_boost');
}"""),
]
VOC_TIMER_DESCRIPTION = [("gilt mit eingeschalteter VOC-Automatik bis zu 60 Minuten Stufe 3,",
                          "setzt die Regel mit eingeschalteter VOC-Automatik Stufe 3 und den Timer auf 60 Minuten "
                          "(früher zurück auf 0, sobald der Index wieder beim Ausgangswert ist und Timer und Stufe "
                          "noch die des Schubs sind),")]
# the VOC boost over any running timer, without waiting (user, 2026-11-12), on top of VOC_TIMER: the same part again
VOC_OVERRIDE = [
    ("""}

// VOC boost (user, 2026-11-12): cooking and the like show as a fast rise of the AIR-1's VOC index, which is relative
// to its last day, so its rise says more than its level. A rise of 50 within 5 minutes, or the index crossing 250,
// starts a boost: level 3 with the ventilation's timer set to 60 minutes, so the page shows how long it holds (the
// timer's own rule lifts a timer only up to 30 minutes and leaves a longer one). It is over sooner, the timer back
// at 0, once the index is back within 20 of where it rose from or the VOC automatic is switched off, but only while
// the timer is still the boost's own: it shows about what the boost has left and the level is still 3. A timer or
// a level the user changed stands. A rise during a running timer waits for it and takes what is left of its hour,
// at least the 30 minutes every level change holds.
// Not in the AIR-1's first hour after a restart, while its index learns anew, nor on a reading older than 3 minutes.
const voc_on = items.getItem('ventilation_voc_management').state === 'ON';
const voc = items.getItem('apollo_air_1_voc_index').numericState;
const voc_ok = voc !== null && air1_fresh('apollo_air_1_voc_index')
  && items.getItem('apollo_air_1_uptime').numericState >= 3600;
const timer_item = items.getItem('ventilation_timer');
const timer_min = timer_item.numericState;
let voc_hist = JSON.parse(cache.private.get('voc_hist') || '[]').filter((h) => Date.now() - h[0] <= 5.5 * 60000);
let voc_boost = JSON.parse(cache.private.get('voc_boost') || 'null');
if (voc_ok) {
  const low = voc_hist.reduce((a, h) => Math.min(a, h[1]), voc);
  const last = voc_hist.length ? voc_hist[voc_hist.length - 1][1] : voc;
  if (voc_on && !voc_boost && (voc - low >= 50 || (last < 250 && voc >= 250))) {
    // where it rose from; for an index that crept over 250, at least 50 below it, or the boost would end at once
    voc_boost = { since: Date.now(), base: Math.min(low, voc - 50) };
  }
  voc_hist.push([Date.now(), voc]);
} else {
  voc_hist = [];
}
let voc_start = false;
if (voc_boost) {
  const back = !voc_on || (voc_ok && voc <= voc_boost.base + 20);
  if (voc_boost.timer_from) {
    // started: the timer is its clock
    const left = voc_boost.minutes - Math.floor((Date.now() - voc_boost.timer_from) / 60000);
    const own = timer_min > 0 && Math.abs(timer_min - left) <= 2 && items.getItem('esplyfterl_level').state === '3';
    if (!own) {
      voc_boost = null;  // run out, or the user took the timer or the level over
    } else if (back) {
      // again every minute until the timer shows 0: its countdown, which runs at the same second, may overwrite this
      timer_item.postUpdate(Quantity('0 min'));
    }
  } else if (back || Date.now() - voc_boost.since >= 60 * 60000) {
    voc_boost = null;  // waited for a timer until it was no longer needed
  } else if (auto_on && timer_min <= 0 && !missing) {
    voc_start = true;
  }
}

if (auto_on && timer_min <= 0 && !missing) {
  let level_to_set = 2;
  if (items.getItem('ventilation_co2_management').state === 'ON') {
    if (co2_item.numericState >= 1000) {
      level_to_set = 3;
    }
    if (co2_item.numericState < 500) {
      level_to_set = 1;
    }
  }
  if (
    items.getItem('ventilation_humidity_management').state === 'ON'
    && items.getItem('apollo_air_1_humidity').numericState <= 35
  ) {
    level_to_set = 1;
  }
  if (
    items.getItem('ventilation_temperature_management').state === 'ON'
    && items.getItem('espaltherma_ext_ambient_temp').numericState >= 30
    && items.getItem('faikout_perfera_switch').state === 'OFF'
  ) {
    level_to_set = 1;
  }
  // the VOC boost outranks them all: the CO2, the dry air and the hot outdoor air (user, 2026-11-12)
  if (voc_start) {
    level_to_set = 3;
    // what is left of the boost's hour, at least the 30 minutes every level change holds; the timer first, so that
    // its own rule, which runs on the level's change, finds it set and leaves it
    voc_boost.minutes = Math.max(30, 60 - Math.floor((Date.now() - voc_boost.since) / 60000));
    voc_boost.timer_from = Date.now();
    timer_item.postUpdate(Quantity(voc_boost.minutes + ' min'));
  }
  items.getItem('esplyfterl_level').sendCommandIfDifferent(String(level_to_set));
}
cache.private.put('voc_hist', JSON.stringify(voc_hist));
if (voc_boost) {
  cache.private.put('voc_boost', JSON.stringify(voc_boost));
} else {
  cache.private.remove('voc_boost');
}""",
     """}

// VOC boost (user, 2026-11-12): cooking and the like show as a fast rise of the AIR-1's VOC index, which is relative
// to its last day, so its rise says more than its level. A rise of 50 within 5 minutes, or the index crossing 250,
// starts a boost at once: the ventilation's timer to 60 minutes and level 3, over any running timer, whoever set
// it, by hand or the automatic with its 30 minutes (user, the same day: a level chosen by hand loses against the
// boost; the way out is the switch VOC-Automatik). The timer is the boost's only clock, and the page shows how long
// it holds (the timer's own rule lifts a timer only up to 30 minutes and leaves a longer one). It is over sooner,
// the timer back at 0, once the index is back within 20 of where it rose from or the VOC automatic is switched
// off, but only while the timer is still the boost's own: it shows about what the boost has left and the level is
// still 3. A timer or a level the user changed during the boost stands. No second boost during one.
// Only with the automatic on and no enabled automatic lacking its reading, not in the AIR-1's first hour after a
// restart, while its index learns anew, nor on a reading older than 3 minutes.
const voc_on = items.getItem('ventilation_voc_management').state === 'ON';
const voc = items.getItem('apollo_air_1_voc_index').numericState;
const voc_ok = voc !== null && air1_fresh('apollo_air_1_voc_index')
  && items.getItem('apollo_air_1_uptime').numericState >= 3600;
const timer_item = items.getItem('ventilation_timer');
const timer_min = timer_item.numericState;
let voc_hist = JSON.parse(cache.private.get('voc_hist') || '[]').filter((h) => Date.now() - h[0] <= 5.5 * 60000);
let voc_boost = JSON.parse(cache.private.get('voc_boost') || 'null');
let voc_start = false;
if (voc_boost) {
  const left = voc_boost.minutes - Math.floor((Date.now() - voc_boost.timer_from) / 60000);
  const own = timer_min > 0 && Math.abs(timer_min - left) <= 2 && items.getItem('esplyfterl_level').state === '3';
  if (!own) {
    voc_boost = null;  // run out, or the user took the timer or the level over
  } else if (!voc_on || (voc_ok && voc <= voc_boost.base + 20)) {
    // again every minute until the timer shows 0: its countdown, which runs at the same second, may overwrite this
    timer_item.postUpdate(Quantity('0 min'));
  }
} else if (voc_ok && voc_on && auto_on && !missing) {
  const low = voc_hist.reduce((a, h) => Math.min(a, h[1]), voc);
  const last = voc_hist.length ? voc_hist[voc_hist.length - 1][1] : voc;
  if (voc - low >= 50 || (last < 250 && voc >= 250)) {
    // where it rose from; for an index that crept over 250, at least 50 below it, or the boost would end at once
    voc_boost = { base: Math.min(low, voc - 50), timer_from: Date.now(), minutes: 60 };
    voc_start = true;
  }
}
if (voc_ok) {
  voc_hist.push([Date.now(), voc]);
} else {
  voc_hist = [];
}
cache.private.put('voc_hist', JSON.stringify(voc_hist));
if (voc_boost) {
  cache.private.put('voc_boost', JSON.stringify(voc_boost));
} else {
  cache.private.remove('voc_boost');
}

if (voc_start) {
  // the timer first, so that its own rule, which runs on the level's change, finds it set and leaves it
  timer_item.postUpdate(Quantity('60 min'));
  items.getItem('esplyfterl_level').sendCommandIfDifferent('3');
} else if (auto_on && timer_min <= 0 && !missing) {
  let level_to_set = 2;
  if (items.getItem('ventilation_co2_management').state === 'ON') {
    if (co2_item.numericState >= 1000) {
      level_to_set = 3;
    }
    if (co2_item.numericState < 500) {
      level_to_set = 1;
    }
  }
  if (
    items.getItem('ventilation_humidity_management').state === 'ON'
    && items.getItem('apollo_air_1_humidity').numericState <= 35
  ) {
    level_to_set = 1;
  }
  if (
    items.getItem('ventilation_temperature_management').state === 'ON'
    && items.getItem('espaltherma_ext_ambient_temp').numericState >= 30
    && items.getItem('faikout_perfera_switch').state === 'OFF'
  ) {
    level_to_set = 1;
  }
  items.getItem('esplyfterl_level').sendCommandIfDifferent(String(level_to_set));
}"""),
]
VOC_OVERRIDE_DESCRIPTION = [("auch bei trockener Luft und ab 30 °C außen, nicht in der ersten Stunde",
                             "auch bei trockener Luft, ab 30 °C außen und über jeden laufenden Timer hinweg, also "
                             "auch über eine von Hand gewählte Stufe (Ausweg: VOC-Automatik aus), nicht in der "
                             "ersten Stunde")]
VOC_SWITCH_DESCRIPTION = [("oder über 250, gilt bis zu 60 Minuten Stufe 3,",
                           "oder über 250, gilt mit eingeschalteter VOC-Automatik bis zu 60 Minuten Stufe 3,")]
VOC_HEAT_DESCRIPTION = [("auch bei trockener Luft, nicht ab 30 °C außen und nicht in der ersten Stunde",
                         "auch bei trockener Luft und ab 30 °C außen, nicht in der ersten Stunde")]
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
    script = action["configuration"]["script"] = replaced(script, VOC, "script")
    rule["description"] = replaced(rule["description"], VOC_DESCRIPTION, "description")
voc_heat = "outranks them all" in script
print(f"rule {RULE}:", "VOC boost over the heat too" if voc_heat
      else f"{len(VOC_HEAT)} replacement for the boost over the heat")
if not voc_heat:
    script = action["configuration"]["script"] = replaced(script, VOC_HEAT, "script")
    rule["description"] = replaced(rule["description"], VOC_HEAT_DESCRIPTION, "description")
voc_switch = VOC_ITEM in script
print(f"rule {RULE}:", "asks the VOC switch" if voc_switch else f"{len(VOC_SWITCH)} replacements for the VOC switch")
if not voc_switch:
    script = action["configuration"]["script"] = replaced(script, VOC_SWITCH, "script")
    rule["description"] = replaced(rule["description"], VOC_SWITCH_DESCRIPTION, "description")
voc_timer = "voc_start" in script
print(f"rule {RULE}:", "the timer is the VOC boost's clock" if voc_timer else "1 replacement for the boost's timer")
if not voc_timer:
    script = action["configuration"]["script"] = replaced(script, VOC_TIMER, "script")
    rule["description"] = replaced(rule["description"], VOC_TIMER_DESCRIPTION, "description")
voc_override = "whoever set" in script
print(f"rule {RULE}:", "the VOC boost overrides a running timer" if voc_override
      else "1 replacement for the boost over a timer")
if not voc_override:
    action["configuration"]["script"] = replaced(script, VOC_OVERRIDE, "script")
    rule["description"] = replaced(rule["description"], VOC_OVERRIDE_DESCRIPTION, "description")
voc_trigger = any(t["configuration"].get("itemName") == VOC_ITEM for t in rule["triggers"])
if not voc_trigger:
    rule["triggers"].append({"id": str(max(int(t["id"]) for t in rule["triggers"]) + 1),
                             "type": "core.ItemStateChangeTrigger", "configuration": {"itemName": VOC_ITEM}})
voc_item = call("GET", f"/items/{VOC_ITEM}")[0] == 200
print(f"item {VOC_ITEM}:", "exists" if voc_item else "missing", "| trigger:", "there" if voc_trigger else "to add")
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
voc_in_sitemap = VOC_ITEM in json.dumps(sitemap)
print("sitemap:", "VOC switch there" if voc_in_sitemap else "VOC switch to add under the CO2's")
if not voc_in_sitemap:
    for _, frame in frames(sitemap, []):
        ws = frame["slots"]["widgets"]
        at = [i for i, w in enumerate(ws) if w.get("config", {}).get("item") == "ventilation_co2_management"]
        if at:
            ws.insert(at[0] + 1, copy.deepcopy(VOC_SITEMAP))
            break
    else:
        raise SystemExit("CO2-Automatik not in the sitemap")
if not apply:
    sys.exit(0)

if not new_exists:
    print("PUT item", NEW, call("PUT", f"/items/{NEW}", NEW_ITEM)[0])
    print("PUT stateDescription", call("PUT", f"/items/{NEW}/metadata/stateDescription", STATE_DESCRIPTION)[0])
    state = old_item["state"] if old_status == 200 and old_item["state"] in ("ON", "OFF") else "OFF"
    print("state", state, put_text(f"/items/{NEW}/state", state))
if not voc_item:
    print("PUT item", VOC_ITEM, call("PUT", f"/items/{VOC_ITEM}", VOC_NEW_ITEM)[0])
    print("PUT stateDescription", call("PUT", f"/items/{VOC_ITEM}/metadata/stateDescription",
                                       {"value": " ", "config": {"pattern": "%s"}})[0])
    print("state ON", put_text(f"/items/{VOC_ITEM}/state", "ON"))
if not (done and fresh and fallback and voc and voc_heat and voc_switch and voc_trigger and voc_timer and voc_override):
    body = {k: v for k, v in rule.items() if k not in ("status", "editable", "templateState")}
    print("PUT rule", call("PUT", f"/rules/{RULE}", body)[0])
if not moved or not voc_in_sitemap:
    print("PUT sitemap", call("PUT", SITEMAP, sitemap)[0])
if old_status == 200:
    print("DELETE item", OLD, call("DELETE", f"/items/{OLD}")[0])
