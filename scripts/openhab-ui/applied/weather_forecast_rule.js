// The weather for the overview's weather bar: the present weather as a WMO code with day or night, and today's and
// the next two days' minimum and maximum, from Open-Meteo (free, no key; CC BY 4.0) for Vienna at city level, as the
// sitemap's Meteoblue widget. The model is GeoSphere's AROME Austria (2.5 km); it reaches about two and a half days
// ahead, so a day it does not cover yet comes from Open-Meteo's best match. The bar takes the present temperature
// from the heat pump's own sensor.
const BASE = 'https://api.open-meteo.com/v1/forecast?latitude=48.21&longitude=16.37&timezone=Europe%2FVienna'
  + '&forecast_days=3';
const DAILY = '&daily=temperature_2m_min,temperature_2m_max';

function get(query) {
  try {
    return JSON.parse(actions.HTTP.sendHttpGetRequest(BASE + query, 20000));
  } catch (e) {
    return null;
  }
}

const missing = (daily, i) => daily.temperature_2m_min[i] == null || daily.temperature_2m_max[i] == null;
const arome = get('&models=geosphere_arome_austria&current=weather_code,is_day' + DAILY);
if (!arome || !arome.current || !arome.daily) {
  console.warn('weather_forecast: no forecast from Open-Meteo');
} else {
  const fallback = [0, 1, 2].some(i => missing(arome.daily, i)) ? get(DAILY) : null;
  items.weather_code.postUpdate(arome.current.weather_code);
  items.weather_is_day.postUpdate(arome.current.is_day ? 'ON' : 'OFF');
  for (let i = 0; i < 3; i++) {
    for (const key of ['min', 'max']) {
      const field = 'temperature_2m_' + key;
      let value = arome.daily[field][i];
      if (value == null && fallback && fallback.daily) {
        value = fallback.daily[field][i];
      }
      if (value != null) {
        items['weather_day' + i + '_' + key].postUpdate(value + ' °C');
      }
    }
  }
}
