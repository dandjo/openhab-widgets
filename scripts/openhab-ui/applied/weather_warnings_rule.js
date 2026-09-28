// The official weather warnings of GeoSphere Austria (warnungen.zamg.at, free, no key) for Vienna at city level, for
// the overview's weather bar and its forecast popup: the highest level of the warnings in effect now or beginning
// within the next 24 hours (0 none, 1 yellow, 2 orange, 3 red), that warning as a short German text ("Gewitter bis
// 20:00", "Wind ab morgen 06:00"), and as JSON every warning that has not ended yet, by its start. When GeoSphere does
// not answer, the warnings of the last answer are kept until they end. From orange on a rising level goes out as a
// broadcast notification.
//
// weather_warning_list: [{type: German name, level: 1-3, start, end: epoch seconds, text: GeoSphere's text}, ...]
const URL = 'https://warnungen.zamg.at/wsapp/api/getWarningsForCoords?lon=16.37&lat=48.21&lang=de';
const TYPES = {1: 'Wind', 2: 'Regen', 3: 'Schnee', 4: 'Glatteis', 5: 'Gewitter', 6: 'Hitze', 7: 'Kälte'};
const WEEKDAYS = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];
const AHEAD = 24 * 3600;

// GeoSphere's warnings, or null without an answer; rawinfo carries type, level and period as numbers
function fetched() {
  try {
    const answer = JSON.parse(actions.HTTP.sendHttpGetRequest(URL, 20000));
    return answer.properties.warnings.map((w) => {
      const p = w.properties;
      const raw = p.rawinfo || {};
      const type = Number(raw.wtype != null ? raw.wtype : p.warntypid);
      return {type: TYPES[type] || 'Warnung', level: Number(raw.wlevel != null ? raw.wlevel : p.warnstufeid),
              start: Number(raw.start), end: Number(raw.end), text: (p.text || '').trim()};
    }).filter((w) => w.level >= 1 && w.level <= 3 && w.end > 0);
  } catch (e) {
    return null;
  }
}

function kept() {
  try {
    const state = String(items.weather_warning_list.state);
    return state.startsWith('[') ? JSON.parse(state) : [];
  } catch (e) {
    return [];
  }
}

// a time as the bar says it: 20:00 today, morgen 06:00, Mi 12:00
function when(t) {
  const d = new Date(t * 1000);
  const now = new Date();
  const midnight = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const days = Math.round((midnight(d) - midnight(now)) / 86400000);
  const hm = String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
  return days <= 0 ? hm : days === 1 ? 'morgen ' + hm : WEEKDAYS[d.getDay()] + ' ' + hm;
}

const now = Date.now() / 1000;
let warnings = fetched();
if (warnings === null) {
  console.warn('weather_warnings: no answer from GeoSphere');
  warnings = kept();
}
warnings = warnings.filter((w) => w.end > now).sort((a, b) => a.start - b.start || b.level - a.level);
const top = warnings.filter((w) => w.start < now + AHEAD).reduce((m, w) => (!m || w.level > m.level ? w : m), null);
const level = top ? top.level : 0;
const summary = top ? top.type + (top.start <= now ? ' bis ' + when(top.end) : ' ab ' + when(top.start)) : 'Keine Warnung';

// a broadcast from orange on, when the level rises to orange or red: a new warning (also one beginning within the
// next 24 hours) or one made worse, not again while the level stays; not after a restart either, as the level is
// restored then and does not rise, and not when the level before is unknown
const before = items.weather_warning_level.numericState;
if (level >= 2 && before !== null && before !== undefined && level > before) {
  actions.NotificationAction.sendBroadcastNotification(
    'Wetterwarnung, Warnstufe ' + level + ' von 3: ' + summary + (top.text ? '\n' + top.text : ''));
}

items.weather_warning_level.postUpdate(level);
items.weather_warning_text.postUpdate(summary);
items.weather_warning_list.postUpdate(JSON.stringify(warnings));
