// The weather for the overview's weather bar and its forecast popup, from Open-Meteo (free, no key; CC BY 4.0) for
// Vienna at city level, as the sitemap's Meteoblue widget: the present weather as a WMO code with day or night, today's
// and the next two days' minimum and maximum, and as JSON the next 61 hours from the running one and the five days
// from today. The model is GeoSphere's AROME Austria (2.5 km); it reaches about two and a half days ahead, so an hour
// or a day it does not cover comes from Open-Meteo's best match, a second request, which also gives the probability of
// precipitation that AROME lacks. The bar takes the present temperature from the heat pump's own sensor.
//
// Open-Meteo is overloaded for a few seconds at every full and half hour and then answers 503 with {error: true}, so
// the rule runs at :07 and :37, checks every answer and asks again up to twice. Hours and days are merged with the last
// run's by their time: what this run brings replaces the old, and an hour or a day it lacks keeps the last run's
// value, so a failed request never shortens the forecast; days before today are dropped.
//
// The weather is drawn from WMO codes, but not from Open-Meteo's as they come: its sky counts thin high clouds (cirrus)
// as overcast though the sun shines through them, and a day's code is the worst of its hours, the night's included.
// So a day's sky follows the share of its daylight the sun shines, and fog, precipitation or a thunderstorm replaces
// it only when it marks the day: fog below 30 % of sunshine, precipitation and thunder from 1 mm, a precipitation day.
// The present sky and each hour's follow the cloud layers, the high ones counted half; precipitation or thunder shows
// only while some falls.
//
// weather_hourly: [[epoch seconds, temperature °C, precipitation of the hour before in mm, wind km/h,
//                   wind direction ° (where it comes from, 0 north, 90 east), WMO code, 1 by day or 0 by night], ...]
// weather_daily: [{t: epoch seconds of the day's midnight, c: WMO code, lo, hi: °C, p: precipitation mm,
//                  pp: probability of precipitation % (best match) or null, w: maximum wind km/h,
//                  wd: the day's dominant wind direction °}, ...]
const BASE = 'https://api.open-meteo.com/v1/forecast?latitude=48.21&longitude=16.37&timezone=Europe%2FVienna'
  + '&forecast_days=5&timeformat=unixtime'
  + '&current=weather_code,is_day,precipitation,cloud_cover_low,cloud_cover_mid,cloud_cover_high'
  + '&hourly=temperature_2m,precipitation,wind_speed_10m,wind_direction_10m,weather_code,is_day'
  + ',cloud_cover_low,cloud_cover_mid,cloud_cover_high';
const DAILY = '&daily=weather_code,temperature_2m_min,temperature_2m_max,precipitation_sum,wind_speed_10m_max'
  + ',wind_direction_10m_dominant,sunshine_duration,daylight_duration';
const HOURS = 61;
const DAYS = 5;
const TRIES = 3;
const Thread = Java.type('java.lang.Thread');

// an answer of Open-Meteo, or null: an error answer ({error: true, reason}) or one without its data is asked again,
// after 5 and 10 seconds
function get(name, query) {
  let reason = 'no answer';
  for (let n = 0; n < TRIES; n++) {
    if (n > 0) {
      Thread.sleep(5000 * n);
    }
    let answer = null;
    try {
      answer = JSON.parse(actions.HTTP.sendHttpGetRequest(BASE + query, 20000));
    } catch (e) {
      answer = null;
    }
    if (answer && !answer.error && answer.daily && answer.hourly) {
      return answer;
    }
    reason = (answer && answer.reason) || 'no answer';
  }
  console.warn('weather_forecast: ' + name + ' failed ' + TRIES + ' times: ' + reason);
  return null;
}

const round = (v, digits) => (v == null ? null : Math.round(v * 10 ** digits) / 10 ** digits);

// a field's value at time t, from the first model that has it
function value(models, part, field, t) {
  for (const model of models) {
    const block = model && model[part];
    const i = block && block.time ? block.time.indexOf(t) : -1;
    if (i >= 0 && block[field] && block[field][i] != null) {
      return block[field][i];
    }
  }
  return null;
}

// a sky by its cloud cover in %: clear, mainly clear, partly cloudy, overcast
const skyByCover = (cover) => (cover < 20 ? 0 : cover < 50 ? 1 : cover < 80 ? 2 : 3);
// a day's sky by the share of its daylight the sun shines
const skyBySun = (share) => (share >= 0.85 ? 0 : share >= 0.6 ? 1 : share >= 0.3 ? 2 : 3);

// the present's or an hour's WMO code: the sky from the cloud layers, the high ones counted half, as the sun shines
// through them; fog as it comes, precipitation and thunder only while some falls (wet), or as they come while that is
// unknown (null)
function hourCode(code, wet, low, mid, high) {
  if (code == null) {
    return null;
  }
  if (code <= 3 || (code >= 51 && wet === false)) {
    return low == null || mid == null || high == null ? Math.min(code, 3)
      : skyByCover(Math.max(low, mid, high / 2));
  }
  return code;
}

// a day's WMO code: the sky from its sunshine, fog only below 30 % of it, precipitation and thunder from 1 mm; the
// code as it comes while the sunshine is unknown
function dayCode(code, precipitation, sunshine, daylight) {
  if (code == null || sunshine == null || !daylight) {
    return code;
  }
  const sky = skyBySun(sunshine / daylight);
  if (code <= 3) {
    return sky;
  }
  if (code <= 48) {
    return sky === 3 ? code : sky;
  }
  return precipitation == null || precipitation >= 1 ? code : sky;
}

// an hour's WMO code and whether it is day, both from the first model with a code for it, the layers from that model
function hourSky(models, t) {
  for (const model of models) {
    const code = value([model], 'hourly', 'weather_code', t);
    if (code != null) {
      const v = (field) => value([model], 'hourly', field, t);
      const precipitation = v('precipitation');
      return [hourCode(code, precipitation == null ? null : round(precipitation, 1) > 0, v('cloud_cover_low'),
                       v('cloud_cover_mid'), v('cloud_cover_high')), v('is_day')];
    }
  }
  return [null, null];
}

// a whole day from one model: AROME while it covers the day's minimum and maximum, else the best match
function day(arome, best, t) {
  const complete = (model) => model && model.daily && model.daily.time
    && value([model], 'daily', 'temperature_2m_min', t) != null && value([model], 'daily', 'temperature_2m_max', t) != null;
  const model = complete(arome) ? arome : complete(best) ? best : null;
  if (!model) {
    return null;
  }
  const v = (field) => value([model], 'daily', field, t);
  return {t: t, c: dayCode(v('weather_code'), v('precipitation_sum'), v('sunshine_duration'), v('daylight_duration')),
          lo: round(v('temperature_2m_min'), 1), hi: round(v('temperature_2m_max'), 1),
          p: round(v('precipitation_sum'), 1), pp: value([best], 'daily', 'precipitation_probability_max', t),
          w: round(v('wind_speed_10m_max'), 0),
          wd: round(value([model, best], 'daily', 'wind_direction_10m_dominant', t), 0)};
}

// the last run's list of an item, or none
function last(item) {
  try {
    const state = String(items.getItem(item).state);
    return state.startsWith('[') ? JSON.parse(state) : [];
  } catch (e) {
    return [];
  }
}

// this run's entries over the last run's, by their time, from `from` on, sorted, at most `count`
function merged(fresh, old, time, from, count) {
  const byTime = new Map();
  old.forEach((e) => byTime.set(time(e), e));
  fresh.forEach((e) => byTime.set(time(e), e));
  return [...byTime.values()].filter((e) => time(e) >= from).sort((a, b) => time(a) - time(b)).slice(0, count);
}

const arome = get('AROME', '&models=geosphere_arome_austria' + DAILY);
const best = get('best match', DAILY + ',precipitation_probability_max');
const models = [arome, best];

const current = models.map((m) => m && m.current).find((c) => c && c.weather_code != null);
if (current) {
  items.weather_code.postUpdate(hourCode(current.weather_code, current.precipitation == null ? null
    : current.precipitation > 0, current.cloud_cover_low, current.cloud_cover_mid, current.cloud_cover_high));
  items.weather_is_day.postUpdate(current.is_day ? 'ON' : 'OFF');
}

if (arome || best) {
  const hour = Math.floor(Date.now() / 3600000) * 3600;
  const fresh = [];
  for (let k = 0; k < HOURS; k++) {
    const t = hour + k * 3600;
    const temp = value(models, 'hourly', 'temperature_2m', t);
    if (temp != null) {
      const [code, isDay] = hourSky(models, t);
      fresh.push([t, round(temp, 1), round(value(models, 'hourly', 'precipitation', t), 1),
                  round(value(models, 'hourly', 'wind_speed_10m', t), 0),
                  round(value(models, 'hourly', 'wind_direction_10m', t), 0), code, isDay]);
    }
  }
  const hourly = merged(fresh, last('weather_hourly'), (h) => h[0], hour, HOURS);
  if (hourly.length) {
    items.weather_hourly.postUpdate(JSON.stringify(hourly));
  }

  // the days from today's midnight, as the answer gives it
  const times = ((best && best.daily) || arome.daily).time.slice(0, DAYS);
  const today = times[0];
  const daily = merged(times.map((t) => day(arome, best, t)).filter((d) => d), last('weather_daily'), (d) => d.t,
                       today, DAYS);
  if (daily.length) {
    items.weather_daily.postUpdate(JSON.stringify(daily));
  }
  // the bar's three days by their date: today, tomorrow and the day after
  for (let i = 0; i < 3; i++) {
    const d = daily.find((x) => x.t === times[i]);
    if (d && d.lo != null && d.hi != null) {
      items['weather_day' + i + '_min'].postUpdate(d.lo + ' °C');
      items['weather_day' + i + '_max'].postUpdate(d.hi + ' °C');
    }
  }
} else {
  console.warn('weather_forecast: no forecast from Open-Meteo, the last one stays');
}
