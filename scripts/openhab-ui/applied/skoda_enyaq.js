// The Škoda Enyaq through the official MyŠkoda Public API (https://public.api.connect.skoda-auto.cz/docs): what the car
// last reported to Škoda's backend, each part with the time the car captured it, and its commands for charging (the
// charge target, starting or stopping a charge) and for the air conditioning (on or off, the target temperature it
// starts with). A read does not wake the car, so a sleeping car's values stay as they were until
// it reports again by itself; a command goes to the car. The API key (created in the MyŠkoda app; it expires) and the
// VIN come from a JSON file, {"apiKey": "...", "vin": "..."}, so that neither stands in this script and a new key
// needs no change here.
// Requests are limited per vehicle (20 an hour, every request counts, failed ones and commands too): reads every 5
// minutes while the car charges or drives, otherwise every 15, and none while the quota is down to a reserve, which
// is left for commands. A command checks what it can first (a cable to charge, a valid value) and is not sent when
// it could not succeed or would change nothing; 90 seconds after a command the state is read again.
const CREDENTIALS = '/var/lib/openhab/credentials/skoda-api.json';
const VEHICLE_URL = 'https://public.api.connect.skoda-auto.cz/api/v1/vehicles/';
const P = 'skoda_enyaq_';
const ACTIVE_MINUTES = 5;
const IDLE_MINUTES = 15;
const QUOTA_RESERVE = 4;
// watts on the car's circuit (rule air_conditioning_circuit_power) from which it counts as charging at home
const HOME_CHARGING_WATTS = 100;
const HOME_RADIUS_METERS = 200;
const KEY_WARNING_DAYS = 7;
const REFRESH_AFTER_COMMAND_MS = 90000;
// the charge limits the car takes: 50 to 100 % in steps of 10
const LIMIT_MIN = 50;
const LIMIT_MAX = 100;
const LIMIT_STEP = 10;
// the target temperatures the MyŠkoda app offers: LO, 16 to 29.5 °C in steps of 0.5, and HI; LO and HI as the values
// VW group integrations send for them, 15.5 and 30 °C (the API names no range; the car rejects what it does not take)
const CLIMATE_MIN = 15.5; // LO
const CLIMATE_MAX = 30; // HI
const CLIMATE_STEP = 0.5;
// the states in which the air conditioning works
const CLIMATE_RUNNING = ['COOLING', 'HEATING', 'HEATING_AUXILIARY', 'VENTILATION'];
const PROBLEM_VEHICLE_DECLINED = 'vehicle-not-accepting-requests';
const store = cache.private;

function state(suffix) {
  return items.getItem(P + suffix).state;
}

// sets an item to value (a string as openHAB parses it), or UNDEF for a value the car did not report
function post(suffix, value) {
  const item = items.getItem(P + suffix);
  const text = value === null || value === undefined ? 'UNDEF' : String(value);
  if (item.state !== text) {
    item.postUpdate(text);
  }
}

function postQuantity(suffix, value, unit) {
  post(suffix, typeof value === 'number' ? `${value} ${unit}` : null);
}

function postTime(suffix, iso) {
  const item = items.getItem(P + suffix);
  if (!iso) {
    if (item.state !== 'UNDEF') {
      item.postUpdate('UNDEF');
    }
    return;
  }
  const when = time.toZDT(iso);
  const before = ['NULL', 'UNDEF'].includes(item.state) ? null : time.toZDT(item.state).toInstant().toEpochMilli();
  if (before !== when.toInstant().toEpochMilli()) {
    item.postUpdate(when);
  }
}

// ON for on, OFF for off, UNDEF for anything else the API reports (UNKNOWN, UNSUPPORTED) or leaves out
function onOff(value, on, off) {
  return value === on ? 'ON' : value === off ? 'OFF' : null;
}

function openClosed(value) {
  return value === 'OPEN' || value === 'CLOSED' ? value : null;
}

function clock(ms) {
  return time.toZDT(new Date(ms).toISOString()).withZoneSameInstant(time.toZDT().zone())
    .format(time.DateTimeFormatter.ofPattern('HH:mm'));
}

function readCredentials() {
  try {
    const Files = Java.type('java.nio.file.Files');
    const Paths = Java.type('java.nio.file.Paths');
    const parsed = JSON.parse(String(Files.readString(Paths.get(CREDENTIALS))));
    return parsed.apiKey && parsed.vin ? parsed : null;
  } catch (e) {
    return null;
  }
}

// one request to the vehicle's URL (path appended) with its status code, body and the headers that tell the quota,
// the key's expiry and how long to wait; a command waits for the car's answer, so it gets more time
function request(credentials, method, path, body, timeoutSeconds) {
  const HttpClient = Java.type('java.net.http.HttpClient');
  const HttpRequest = Java.type('java.net.http.HttpRequest');
  const BodyHandlers = Java.type('java.net.http.HttpResponse$BodyHandlers');
  const BodyPublishers = Java.type('java.net.http.HttpRequest$BodyPublishers');
  const Duration = Java.type('java.time.Duration');
  const URI = Java.type('java.net.URI');
  const client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(15)).build();
  try {
    const builder = HttpRequest.newBuilder(URI.create(VEHICLE_URL + credentials.vin + path))
      .header('X-API-Key', credentials.apiKey)
      .header('Accept', 'application/json')
      .timeout(Duration.ofSeconds(timeoutSeconds));
    if (method === 'GET') {
      builder.GET();
    } else {
      builder.header('Content-Type', 'application/json')
        .method(method, body === null ? BodyPublishers.noBody() : BodyPublishers.ofString(JSON.stringify(body)));
    }
    const response = client.send(builder.build(), BodyHandlers.ofString());
    const header = (name) => {
      const value = response.headers().firstValue(name);
      return value.isPresent() ? String(value.get()) : null;
    };
    return {
      status: response.statusCode(),
      body: String(response.body()),
      remaining: header('ratelimit-remaining'),
      reset: header('ratelimit-reset'),
      retryAfter: header('retry-after'),
      keyExpiresAt: header('x-api-key-expires-at'),
    };
  } catch (e) {
    return { status: 0, error: String(e) };
  } finally {
    client.close();
  }
}

// what every answer tells: the quota, the key's expiry, how long to wait after a 429
function noteHeaders(response) {
  const now = Date.now();
  if (response.remaining !== null && response.remaining !== undefined) {
    const remaining = Number(response.remaining);
    store.put('remaining', remaining);
    const resetAt = now + Number(response.reset || 3600) * 1000;
    store.put('resetAt', resetAt);
    post('api_requests_left', remaining);
    // when the hour's quota is full again, for the page's "Reset in … min"; to the second, as the header gives seconds
    postTime('api_quota_reset_at', new Date(Math.round(resetAt / 1000) * 1000).toISOString());
  }
  if (response.keyExpiresAt) {
    postTime('api_key_expiry', response.keyExpiresAt);
  }
  if (response.status === 429) {
    store.put('retryAt', now + Number(response.retryAfter || 600) * 1000);
  }
}

// the problem type's last part of an error answer (RFC 9457), e.g. vehicle-not-accepting-requests
function problemType(response) {
  try {
    return String(JSON.parse(response.body).type || '').split('/').pop();
  } catch (e) {
    return '';
  }
}

function applyCharging(charging) {
  const status = charging.status || {};
  const battery = status.battery || {};
  const settings = charging.settings || {};
  postQuantity('soc', battery.stateOfChargeInPercent, '%');
  const meters = battery.remainingCruisingRangeInMeters;
  postQuantity('range', typeof meters === 'number' ? Math.round(meters / 1000) : null, 'km');
  // left out when the reported combination has no name (plugged in and unlocked without charging, after a drive)
  post('charging_state', status.state);
  post('charging', status.state === 'CHARGING' ? 'ON' : 'OFF');
  postQuantity('charge_power', status.chargePowerInKw, 'kW');
  postQuantity('charge_rate', status.chargingRateInKilometersPerHour, 'km/h');
  post('charge_type', status.chargeType);
  post('plug', onOff(status.plugConnectionState, 'CONNECTED', 'DISCONNECTED'));
  post('plug_locked', onOff(status.plugLockState, 'LOCKED', 'UNLOCKED'));
  // when the charge target will be reached, while it charges: the car charges to the target, not to full (the API
  // still calls it fullyChargedAt and remainingTimeToFullyChargedInMinutes)
  let reached = null;
  if (status.state === 'CHARGING') {
    if (status.fullyChargedAt) {
      reached = status.fullyChargedAt;
    } else if (typeof status.remainingTimeToFullyChargedInMinutes === 'number' && charging.carCapturedTimestamp) {
      const capturedMs = Date.parse(charging.carCapturedTimestamp);
      reached = new Date(capturedMs + status.remainingTimeToFullyChargedInMinutes * 60000).toISOString();
    }
  }
  postTime('target_reached_at', reached);
  // the charge target (Ladeziel) is the value set in the car, the one it charges to, with battery care on too (user,
  // 2026-10-26: a 50 % target stayed 50 %); the battery care target is that mode's value as the API reports it
  post('battery_care', onOff(settings.chargingCareMode, 'ACTIVATED', 'DEACTIVATED'));
  postQuantity('charge_target', settings.targetStateOfChargeInPercent, '%');
  postQuantity('battery_care_target', settings.batteryCareModeTargetValueInPercent, '%');
}

function applyStatus(vehicleStatus) {
  const overall = vehicleStatus.overall || {};
  const detail = vehicleStatus.detail || {};
  post('locked', onOff(overall.locked, 'YES', 'NO'));
  post('doors', openClosed(overall.doors));
  post('windows', openClosed(overall.windows));
  post('trunk', openClosed(detail.trunk));
  post('bonnet', openClosed(detail.bonnet));
  post('lights', onOff(overall.lights, 'ON', 'OFF'));
}

// the position only while parked; while driving it keeps where the car last stood, which is then not home
function applyParking(parking) {
  post('parking_state', parking.state);
  if (parking.state === 'IN_MOTION') {
    post('at_home', 'OFF');
    return;
  }
  const gps = parking.gpsCoordinates;
  if (parking.state !== 'PARKED' || !gps || typeof gps.latitude !== 'number' || typeof gps.longitude !== 'number') {
    return;
  }
  const PointType = Java.type('org.openhab.core.library.types.PointType');
  const position = new PointType(`${gps.latitude},${gps.longitude}`);
  const item = items.getItem(P + 'parking_position');
  const before = ['NULL', 'UNDEF'].includes(item.state) ? null : new PointType(item.state);
  if (before === null || before.distanceFrom(position).doubleValue() > 1) {
    item.postUpdate(position.toString());
  }
  post('parking_address', parking.formattedAddress);
  const home = osgi.getService('org.openhab.core.i18n.LocationProvider').getLocation();
  if (home !== null) {
    post('at_home', home.distanceFrom(position).doubleValue() <= HOME_RADIUS_METERS ? 'ON' : 'OFF');
  }
}

// the target temperature as the car reports it, unless one was chosen while the air conditioning was off: that one
// stays until the car reports it, once it started with it
function applyAirConditioning(air) {
  post('climate_state', air.state);
  post('climate', CLIMATE_RUNNING.includes(air.state) ? 'ON' : 'OFF');
  const target = air.targetTemperature || {};
  const chosen = store.get('climateChosen');
  if (chosen !== null && chosen !== undefined && target.value !== chosen) {
    return;
  }
  store.remove('climateChosen');
  postQuantity('climate_target', target.value, target.unit === 'FAHRENHEIT' ? '°F' : '°C');
}

function apply(vehicle) {
  if (vehicle.charging) {
    applyCharging(vehicle.charging);
  }
  if (vehicle.status) {
    applyStatus(vehicle.status);
  }
  if (vehicle.odometer) {
    postQuantity('odometer', vehicle.odometer.mileageInKm, 'km');
  }
  if (vehicle.parkingPosition) {
    applyParking(vehicle.parkingPosition);
  }
  if (vehicle.airConditioning) {
    applyAirConditioning(vehicle.airConditioning);
  }
  // when the car last reported anything: the newest of its parts' capture times
  const captured = [vehicle.charging, vehicle.status, vehicle.odometer, vehicle.airConditioning]
    .map((part) => (part && part.carCapturedTimestamp ? Date.parse(part.carCapturedTimestamp) : NaN))
    .filter((ms) => !Number.isNaN(ms));
  if (captured.length > 0) {
    postTime('updated', new Date(Math.max(...captured)).toISOString());
  }
}

function notify(message) {
  actions.NotificationAction.sendBroadcastNotification(message);
  console.info(`Škoda: Benachrichtigung gesendet: ${message}`);
}

function setApiStatus(status, logText) {
  const before = state('api_status');
  if (before !== status) {
    if (status === 'OK') {
      console.info(['NULL', 'UNDEF'].includes(before) ? 'Škoda: Abruf läuft' : 'Škoda: Abruf wieder in Ordnung');
    } else {
      console.warn(`Škoda: ${logText}`);
    }
  }
  post('api_status', status);
}

function keyExpired() {
  setApiStatus('KEY_EXPIRED', 'API-Schlüssel abgelaufen oder ungültig (401)');
  if (!store.get('keyAlarm')) {
    store.put('keyAlarm', true);
    notify('Škoda: Der API-Schlüssel ist abgelaufen oder ungültig. Bitte in der MyŠkoda-App einen neuen erstellen und in openHAB eintragen.');
  }
}

// once a day from 9 o'clock while the key has a week or less left
function remindKeyExpiry(expiresAt) {
  const now = time.toZDT();
  const expiry = time.toZDT(expiresAt).withZoneSameInstant(now.zone());
  const today = now.toLocalDate().toString();
  if (now.hour() < 9 || store.get('keyReminder') === today || expiry.isAfter(now.plusDays(KEY_WARNING_DAYS))) {
    return;
  }
  store.put('keyReminder', today);
  const date = expiry.format(time.DateTimeFormatter.ofPattern('dd.MM.yyyy'));
  notify(`Škoda: Der API-Schlüssel läuft am ${date} ab. Bitte in der MyŠkoda-App einen neuen erstellen und in openHAB eintragen.`);
}

// why no request may go out now, or null: a 429's wait, or the quota down to reserve requests left
function blocked(reserve) {
  const now = Date.now();
  if (now < (store.get('retryAt') || 0)) {
    return `Anfragelimit erreicht, wieder ab ${clock(store.get('retryAt'))}`;
  }
  const remaining = store.get('remaining');
  const resetAt = store.get('resetAt') || 0;
  if (remaining !== null && remaining !== undefined && remaining <= reserve && now < resetAt) {
    return `Stundenkontingent aufgebraucht, wieder ab ${clock(resetAt)}`;
  }
  return null;
}

function due() {
  const active = state('charging_state') === 'CHARGING' || state('parking_state') === 'IN_MOTION' ||
    (items.getItem('e_car_power').numericState || 0) > HOME_CHARGING_WATTS;
  const minutes = active ? ACTIVE_MINUTES : IDLE_MINUTES;
  // a minute's slack, so the cron's own jitter does not skip a turn
  return Date.now() - (store.get('lastRequest') || 0) >= (minutes - 1) * 60000;
}

// reads the vehicle: when due, or forced after a command (then the reserve may be used, not the last request)
function poll(force) {
  if ((!force && !due()) || blocked(force ? 0 : QUOTA_RESERVE) !== null) {
    return;
  }
  const credentials = readCredentials();
  if (credentials === null) {
    setApiStatus('NO_CREDENTIALS', `keine Zugangsdaten in ${CREDENTIALS}`);
    return;
  }
  store.put('lastRequest', Date.now());
  const response = request(credentials, 'GET', '', null, 30);
  noteHeaders(response);
  if (response.status === 200) {
    let body = null;
    try {
      body = JSON.parse(response.body);
    } catch (e) {
      setApiStatus('ERROR', 'Antwort ist kein JSON');
      return;
    }
    store.remove('keyAlarm');
    setApiStatus('OK');
    const previous = tripPrevious();
    apply(body.vehicle || {});
    try {
      trackTrips(body.vehicle || {}, previous, Date.now());
    } catch (e) {
      console.warn(`Škoda: Fahrten: ${e}`);
    }
    const errors = (body.errors || []).map((e) => e.type).sort().join(', ');
    if (errors !== (store.get('errors') || '')) {
      if (errors) {
        console.info(`Škoda: Teile fehlen in der Antwort: ${errors}`);
      }
      store.put('errors', errors);
    }
    if (response.keyExpiresAt) {
      remindKeyExpiry(response.keyExpiresAt);
    }
  } else if (response.status === 401) {
    keyExpired();
  } else if (response.status === 403) {
    setApiStatus('NOT_AUTHORIZED', 'der API-Schlüssel gilt nicht für dieses Fahrzeug (403)');
  } else if (response.status === 429) {
    setApiStatus('RATE_LIMITED', `Anfragelimit erreicht, nächster Versuch in ${response.retryAfter || 600} s`);
  } else {
    setApiStatus('ERROR', response.status === 0 ? `nicht erreichbar: ${response.error}` : `HTTP ${response.status}`);
  }
}

// ---- trips (user, 2026-10-26): the API keeps no trips, so the rule finds them in what it reads, as the MyŠkoda app's
// Reiseverlauf lists them. A trip runs from a parked place to the next: the place before a read is what the items
// held before it (parking position, address, odometer, charge), so nothing is kept twice. Its end is when the car
// reported the odometer at the new place, its start lies between the last read that saw it parked and the first that
// saw it gone ("ca.", off by up to half a read interval). Trips less than 2 hours apart are one session, as in the
// app, its places numbered in order for its map; a charge away from home after an arrival is a charging stop there.
// skoda_enyaq_trip_state holds what the finding needs between reads (since when the car stands, an open session).
// Finished sessions go to InfluxDB as one point each in TRIP_MEASUREMENT, with the fields of the app's export, which
// applied/skoda_trips.py imports in place of the found trips of its span. No item may carry that name: the nightly
// downsampler leaves only measurements without an item alone. skoda_enyaq_trips holds the last TRIP_DAYS days for
// the location popup and each trip's popup, by day, newest first.
const TRIP_MEASUREMENT = 'skoda_trips';
const INFLUX = 'http://127.0.0.1:8086';
const SESSION_GAP_MS = 2 * 3600000;  // trips closer than this are one session, as in the app
const MOVED_METERS = 200;            // a parked place this far from the last one is a new one
const BATTERY_KWH = 77;              // the Enyaq 80x's usable battery, for the energy a found trip took
const TRIP_DAYS = 30;                // days the popup lists (user, 2026-10-26)
const WEEKDAYS = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];
const VIENNA_DISTRICTS = ['Innere Stadt', 'Leopoldstadt', 'Landstraße', 'Wieden', 'Margareten', 'Mariahilf', 'Neubau',
  'Josefstadt', 'Alsergrund', 'Favoriten', 'Simmering', 'Meidling', 'Hietzing', 'Penzing', 'Rudolfsheim-Fünfhaus',
  'Ottakring', 'Hernals', 'Währing', 'Döbling', 'Brigittenau', 'Floridsdorf', 'Donaustadt', 'Liesing'];

// a point in time in the local zone: its day, its clock and its weekday
function local(ms) {
  const z = time.toZDT(new Date(ms).toISOString()).withZoneSameInstant(time.toZDT().zone());
  return { day: z.format(time.DateTimeFormatter.ofPattern('yyyy-MM-dd')),
    hm: z.format(time.DateTimeFormatter.ofPattern('HH:mm')), wd: z.dayOfWeek().value() % 7 };
}

// an address as the app lists it: the street without its number and the place, Vienna's districts by name
function shortAddress(address) {
  const parts = String(address || '').split(',').map((p) => p.trim()).filter((p) => p !== '');
  if (parts.length < 2) {
    return parts[0] || '';
  }
  const street = parts[0].replace(/\s+\d+[\w/-]*$/, '');
  const m = parts[1].match(/^(\d{4,5})\s+(.+)$/);
  let place = m ? m[2] : parts[1];
  if (m && place === 'Wien' && /^1\d\d0$/.test(m[1])) {
    place = VIENNA_DISTRICTS[Number(m[1].slice(1, 3)) - 1] || place;
  }
  return `${street}, ${place}`;
}

function metersBetween(a, b) {
  const rad = Math.PI / 180;
  const x = (b[1] - a[1]) * rad * Math.cos((a[0] + b[0]) / 2 * rad);
  const y = (b[0] - a[0]) * rad;
  return Math.sqrt(x * x + y * y) * 6371000;
}

function atHome(pos) {
  const home = osgi.getService('org.openhab.core.i18n.LocationProvider').getLocation();
  if (home === null || pos === null) {
    return false;
  }
  const PointType = Java.type('org.openhab.core.library.types.PointType');
  return home.distanceFrom(new PointType(`${pos[0]},${pos[1]}`)).doubleValue() <= HOME_RADIUS_METERS;
}

// where the car stood before this read, as the items held it: read before the read is applied to them
function tripPrevious() {
  const pos = String(state('parking_position')).split(',').slice(0, 2).map(Number);
  const odo = items.getItem(P + 'odometer').numericState;
  const soc = items.getItem(P + 'soc').numericState;
  const address = state('parking_address');
  return { pos: pos.length === 2 && pos.every(Number.isFinite) ? pos : null, odo: typeof odo === 'number' ? odo : null,
    soc: typeof soc === 'number' ? soc : null, address: ['NULL', 'UNDEF'].includes(address) ? null : address };
}

// what a read says about where the car is
function tripReading(vehicle) {
  const parking = vehicle.parkingPosition || {};
  const gps = parking.gpsCoordinates || {};
  const odometer = vehicle.odometer || {};
  const status = (vehicle.charging || {}).status || {};
  const battery = status.battery || {};
  const pos = typeof gps.latitude === 'number' && typeof gps.longitude === 'number'
    ? [gps.latitude, gps.longitude] : null;
  return { parked: parking.state === 'PARKED' && pos !== null, moving: parking.state === 'IN_MOTION', pos,
    address: parking.formattedAddress || null,
    odo: typeof odometer.mileageInKm === 'number' ? odometer.mileageInKm : null,
    odoAt: odometer.carCapturedTimestamp ? Date.parse(odometer.carCapturedTimestamp) : NaN,
    soc: typeof battery.stateOfChargeInPercent === 'number' ? battery.stateOfChargeInPercent : null,
    charging: status.state === 'CHARGING' };
}

function tripState() {
  try {
    const s = JSON.parse(state('trip_state'));
    return s !== null && typeof s === 'object' ? s : {};
  } catch (e) {
    return {};
  }
}

// a session as a trip in the export's fields; its places as [latitude, longitude, time, address, charge gained there]
function sessionTrip(session) {
  const open = session.chargeFrom !== undefined && session.chargeFrom !== null && session.socNow !== null
    ? Math.max(0, session.socNow - session.chargeFrom) : 0;
  const gained = session.gained + open;
  const used = session.socStart !== null && session.socEnd !== null && session.socEnd !== undefined
    ? session.socStart - session.socEnd + gained : null;
  const points = session.points.map((p, i) => i === session.points.length - 1 && open > 0
    ? [p[0], p[1], p[2], p[3], p[4] + open] : p);
  return { time: session.start, source: 'auto', end: session.end === undefined ? null : session.end, approx: true,
    from: points[0][3], to: session.end === undefined ? null : points[points.length - 1][3],
    km: session.odoEnd === undefined ? null : session.odoEnd - session.odoStart, odoStart: session.odoStart,
    odoEnd: session.odoEnd === undefined ? null : session.odoEnd,
    travel: session.end === undefined ? null : Math.round((session.end - session.start) / 60000),
    socStart: session.socStart, socEnd: session.socEnd === undefined ? null : session.socEnd, stops: session.stops,
    gained, kwh: used === null ? null : Math.round(Math.max(0, used) * BATTERY_KWH) / 100,
    points: JSON.stringify(points) };
}

// one point of InfluxDB's line protocol at the trip's start, in ms: numbers as floats, texts quoted
function tripLine(trip) {
  const fields = Object.entries(trip).filter(([k, v]) => !['time', 'source'].includes(k) && v !== null &&
    v !== undefined && !(typeof v === 'number' && !Number.isFinite(v)))
    .map(([k, v]) => typeof v === 'string' ? `${k}="${v.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"` : `${k}=${v}`);
  return `${TRIP_MEASUREMENT},source=${trip.source} ${fields.join(',')} ${trip.time}`;
}

function influxWrite(line) {
  const answer = actions.HTTP.sendHttpPostRequest(`${INFLUX}/write?db=openhab&precision=ms`, 'text/plain', line, 10000);
  return answer !== null && answer !== undefined && String(answer).indexOf('"error"') < 0;
}

// after a read: a departure opens a session (or a leg of the open one), an arrival closes the leg; 2 hours after the
// last arrival without a new departure the session goes to InfluxDB (kept open while InfluxDB does not take it)
function trackTrips(vehicle, prev, now) {
  const r = tripReading(vehicle);
  if (r.odo === null || (!r.parked && !r.moving)) {
    return;
  }
  const s = tripState();
  const finish = () => {
    if (influxWrite(tripLine(sessionTrip(s.session)))) {
      console.info(`Škoda: Fahrt gespeichert, ${s.session.odoEnd - s.session.odoStart} km`);
      delete s.session;
    } else {
      console.warn('Škoda: Fahrt nicht in InfluxDB geschrieben, nächster Versuch beim nächsten Lesen');
    }
  };
  if (prev.pos === null || prev.odo === null) {
    // nothing known of the place before: it starts here
    if (r.parked) {
      s.seen = now;
    }
  } else if (!(r.odo > prev.odo || r.moving || (r.parked && metersBetween(prev.pos, r.pos) > MOVED_METERS))) {
    // still where it stood: a charge away from home after an arrival of the open session is a charging stop there
    const sess = s.session;
    if (sess && sess.end !== undefined && !sess.departing && r.soc !== null) {
      const last = sess.points[sess.points.length - 1];
      if (r.charging && !atHome(r.pos) && (sess.chargeFrom === undefined || sess.chargeFrom === null)) {
        sess.chargeFrom = prev.soc !== null ? prev.soc : r.soc;
        sess.stops += 1;
      } else if (!r.charging && sess.chargeFrom !== undefined && sess.chargeFrom !== null) {
        const gain = Math.max(0, r.soc - sess.chargeFrom);
        sess.gained += gain;
        last[4] += gain;
        sess.chargeFrom = null;
      }
      sess.socNow = r.soc;
    }
    s.seen = now;
  } else {
    // gone: a session whose last arrival lies 2 hours or more before the car was last seen there is over
    if (s.session && s.session.end !== undefined && !s.session.departing &&
        (s.seen || now) - s.session.end >= SESSION_GAP_MS) {
      finish();
    }
    if (!s.session) {
      s.session = { start: null, odoStart: prev.odo, socStart: prev.soc, stops: 0, gained: 0,
        points: [[prev.pos[0], prev.pos[1], null, prev.address, 0]] };
    }
    const sess = s.session;
    if (sess.chargeFrom !== undefined && sess.chargeFrom !== null) {
      const gain = Math.max(0, (prev.soc !== null ? prev.soc : sess.chargeFrom) - sess.chargeFrom);
      sess.gained += gain;
      sess.points[sess.points.length - 1][4] += gain;
      sess.chargeFrom = null;
    }
    // the departure lies between the last read that saw it parked and the first that saw it gone
    if (!sess.departing) {
      sess.departing = { after: s.seen || now, by: now };
    }
    if (r.parked) {
      const arrived = Number.isNaN(r.odoAt) ? now : Math.min(now, Math.max(r.odoAt, sess.departing.after));
      if (sess.start === null) {
        const by = Math.min(sess.departing.by, arrived);
        sess.start = Math.round(sess.departing.after + (by - sess.departing.after) / 2);
        sess.points[0][2] = sess.start;
      }
      sess.points.push([r.pos[0], r.pos[1], arrived, r.address, 0]);
      Object.assign(sess, { end: arrived, odoEnd: r.odo, socEnd: r.soc, socNow: r.soc });
      delete sess.departing;
      s.seen = now;
    } else if (sess.start === null) {
      sess.start = Math.round(sess.departing.after + (now - sess.departing.after) / 2);
      sess.points[0][2] = sess.start;
    }
  }
  if (s.session && s.session.end !== undefined && !s.session.departing && now - s.session.end >= SESSION_GAP_MS) {
    finish();
  }
  post('trip_state', JSON.stringify(s));
}

// the trips of the last days from InfluxDB, as records of the export's fields, or null while it does not answer
function influxTrips(days) {
  const q = `SELECT * FROM ${TRIP_MEASUREMENT} WHERE time > now() - ${days}d`;
  const body = actions.HTTP.sendHttpGetRequest(`${INFLUX}/query?db=openhab&epoch=ms&q=${encodeURIComponent(q)}`,
    10000);
  if (!body) {
    return null;
  }
  const result = (JSON.parse(body).results || [])[0] || {};
  if (result.error) {
    return null;
  }
  const series = (result.series || [])[0];
  return series ? series.values.map((v) => {
    const rec = {};
    series.columns.forEach((c, i) => { rec[c] = v[i]; });
    return rec;
  }) : [];
}

// the last TRIP_DAYS days for the popups: days newest first with their km and a mark on the first of each month, each
// day's trips newest first with what the list shows and what a trip's popup shows, the open session among them
function tripWindow(records, session, now) {
  const from = local(now - TRIP_DAYS * 86400000).day;
  const trips = records.filter((t) => local(t.time).day > from);
  if (session && session.start !== null && session.start !== undefined) {
    trips.push(sessionTrip(session));
  }
  const num = (v, digits) => typeof v === 'number' && Number.isFinite(v) ? Math.round(v * 10 ** digits) / 10 ** digits
    : null;
  const days = [];
  trips.sort((a, b) => b.time - a.time).forEach((t) => {
    const start = local(t.time);
    const end = t.end ? local(t.end) : null;
    const when = (ms) => {
      const l = local(ms);
      return l.day === start.day ? l.hm : `${WEEKDAYS[l.wd]} ${l.hm}`;
    };
    let day = days.length > 0 && days[days.length - 1].d === start.day ? days[days.length - 1] : null;
    if (day === null) {
      day = { d: start.day, km: 0, t: [] };
      if (days.length === 0 || days[days.length - 1].d.slice(0, 7) !== start.day.slice(0, 7)) {
        day.m = 1;
      }
      days.push(day);
    }
    day.km += num(t.km, 0) || 0;
    let points = [];
    try {
      points = JSON.parse(t.points || '[]');
    } catch (e) {
      points = [];
    }
    day.t.push({ id: t.time, s: start.hm, e: end === null ? null : when(t.end), x: t.approx ? 1 : 0,
      a: shortAddress(t.from), b: t.to ? shortAddress(t.to) : '', km: num(t.km, 0), kwh: num(t.kwh, 1),
      s0: num(t.socStart, 0), s1: num(t.socEnd, 0), c: num(t.stops, 0) || 0, g: num(t.gained, 0) || 0,
      dr: num(t.drive, 0), tr: num(t.travel, 0), sp: num(t.speed, 0), k1: num(t.kwh100, 1), o0: num(t.odoStart, 0),
      o1: num(t.odoEnd, 0),
      p: points.map((p) => [num(p[0], 6), num(p[1], 6), typeof p[2] === 'number' ? when(p[2]) : '', shortAddress(p[3]),
        num(p[4], 0) || 0]) });
  });
  return days;
}

// the popups' trips from InfluxDB and the open session, on every run (a light query); unchanged while InfluxDB is away
function publishTrips() {
  const records = influxTrips(TRIP_DAYS + 1);
  if (records === null) {
    return;
  }
  post('trips', JSON.stringify(tripWindow(records, tripState().session || null, Date.now())));
}

// ---- commands

function result(text) {
  post('command_result', text);
  console.info(`Škoda: ${text}`);
}

// the item and command of the event that triggered the run, for a command to one of the two command items, else null;
// read as openhab-js passes UI rules their event or as openHAB's own event object
function receivedCommand() {
  if (typeof event === 'undefined' || event === null) {
    return null;
  }
  const read = (...keys) => {
    for (const key of keys) {
      try {
        const value = typeof event[key] === 'function' ? event[key]() : event[key];
        if (value !== undefined && value !== null && String(value) !== '') {
          return String(value);
        }
      } catch (e) {
        // not this form
      }
    }
    return null;
  };
  const item = read('itemName', 'getItemName');
  const command = read('receivedCommand', 'itemCommand', 'getItemCommand');
  return item && command && [P + 'charge_target', P + 'charging', P + 'climate', P + 'climate_target'].includes(item)
    ? { item, command } : null;
}

// a command to the car as German text for its result, or null when it was not sent
function commandText(response, what) {
  if (response.status === 202 || response.status === 200) {
    return null;
  }
  if (response.status === 401) {
    keyExpired();
    return `${what}: API-Schlüssel abgelaufen oder ungültig`;
  }
  if (response.status === 403) {
    return `${what}: nicht erlaubt (Schlüssel oder Benutzerrechte)`;
  }
  if (response.status === 400) {
    return `${what}: vom Auto nicht angenommen`;
  }
  if (response.status === 422) {
    return `${what}: das Auto kann das gerade nicht`;
  }
  if (response.status === 429) {
    return problemType(response) === PROBLEM_VEHICLE_DECLINED ? `${what}: das Auto nimmt gerade keine Befehle an`
      : `${what}: Anfragelimit erreicht`;
  }
  if (response.status === 504) {
    return `${what}: das Auto hat nicht rechtzeitig geantwortet`;
  }
  return response.status === 0 ? `${what}: Škoda nicht erreichbar` : `${what}: Fehler (HTTP ${response.status})`;
}

function sendToCar(method, path, body, what, accepted) {
  const credentials = readCredentials();
  if (credentials === null) {
    setApiStatus('NO_CREDENTIALS', `keine Zugangsdaten in ${CREDENTIALS}`);
    result(`${what}: keine Zugangsdaten`);
    return;
  }
  const wait = blocked(0);
  if (wait !== null) {
    result(`${what}: ${wait}`);
    return;
  }
  result(`${what}: wird gesendet …`);
  const response = request(credentials, method, path, body, 90);
  noteHeaders(response);
  const failed = commandText(response, what);
  if (failed === null) {
    accepted();
    result(`${what} · ${clock(Date.now())}`);
  } else {
    result(failed);
  }
  // the car's new state, once it had time to act on the command; one read for several commands in a row
  if (store.get('refreshTimer')) {
    clearTimeout(store.get('refreshTimer'));
  }
  store.put('refreshTimer', setTimeout(() => {
    store.remove('refreshTimer');
    poll(true);
  }, REFRESH_AFTER_COMMAND_MS));
}

function setLimit(command) {
  const percent = parseFloat(command);
  if (Number.isNaN(percent) || percent < LIMIT_MIN || percent > LIMIT_MAX || percent % LIMIT_STEP !== 0) {
    result(`Ladeziel ${command}: geht nicht, nur ${LIMIT_MIN} bis ${LIMIT_MAX} % in Zehnerschritten`);
    return;
  }
  const current = items.getItem(P + 'charge_target').numericState;
  if (current === percent) {
    result(`Ladeziel ist schon ${percent} %`);
    return;
  }
  sendToCar('PUT', '/charging/limit', { targetStateOfChargeInPercent: percent }, `Ladeziel ${percent} % gesetzt`,
    () => post('charge_target', `${percent} %`));
}

function setCharging(command) {
  const charging = state('charging_state') === 'CHARGING' || state('charging') === 'ON';
  if (command === 'ON') {
    if (state('plug') === 'OFF') {
      result('Laden: kein Ladekabel eingesteckt');
    } else if (charging) {
      result('Laden: lädt bereits');
    } else {
      sendToCar('POST', '/charging/start', null, 'Laden gestartet', () => post('charging', 'ON'));
    }
  } else if (command === 'OFF') {
    if (!charging) {
      result('Laden: lädt gerade nicht');
    } else {
      sendToCar('POST', '/charging/stop', null, 'Laden gestoppt', () => post('charging', 'OFF'));
    }
  }
}

// a target temperature as the app names it: LO and HI at the ends, else in degrees with a decimal comma
function celsius(value) {
  if (value <= CLIMATE_MIN) {
    return 'LO';
  }
  if (value >= CLIMATE_MAX) {
    return 'HI';
  }
  return `${String(value).replace('.', ',')} °C`;
}

// the air conditioning starts with the target temperature and may run on the battery, so it starts away from a
// charger too
function startClimate(target, what, accepted) {
  sendToCar('POST', '/air-conditioning/start',
    { targetTemperature: { value: target, unit: 'CELSIUS' }, airConditioningWithoutExternalPower: true }, what,
    accepted);
}

function setClimate(command) {
  const running = CLIMATE_RUNNING.includes(state('climate_state')) || state('climate') === 'ON';
  if (command === 'ON') {
    const target = items.getItem(P + 'climate_target').numericState;
    if (running) {
      result('Klimatisierung: läuft bereits');
    } else if (target === null) {
      result('Klimatisierung: keine Zieltemperatur bekannt');
    } else {
      startClimate(target, `Klimatisierung auf ${celsius(target)} gestartet`, () => post('climate', 'ON'));
    }
  } else if (command === 'OFF') {
    if (!running) {
      result('Klimatisierung: läuft gerade nicht');
    } else {
      sendToCar('POST', '/air-conditioning/stop', null, 'Klimatisierung gestoppt', () => post('climate', 'OFF'));
    }
  }
}

// a new target temperature: while the air conditioning runs it starts again with it; while it is off the value is
// kept for its next start
function setClimateTarget(command) {
  const target = parseFloat(command);
  if (Number.isNaN(target) || target < CLIMATE_MIN || target > CLIMATE_MAX ||
      Math.round(target / CLIMATE_STEP) * CLIMATE_STEP !== target) {
    result(`Zieltemperatur ${command}: geht nicht, nur LO, 16 bis 29,5 °C in halben Grad oder HI`);
    return;
  }
  if (items.getItem(P + 'climate_target').numericState === target) {
    result(`Zieltemperatur ist schon ${celsius(target)}`);
    return;
  }
  const running = CLIMATE_RUNNING.includes(state('climate_state')) || state('climate') === 'ON';
  if (running) {
    startClimate(target, `Zieltemperatur ${celsius(target)} gesetzt`, () => {
      store.put('climateChosen', target);
      post('climate_target', `${target} °C`);
    });
  } else {
    store.put('climateChosen', target);
    post('climate_target', `${target} °C`);
    result(`Zieltemperatur ${celsius(target)}: gilt beim nächsten Start`);
  }
}

function run() {
  const received = receivedCommand();
  if (received === null) {
    poll(typeof refresh !== 'undefined');
  } else if (received.item === P + 'charge_target') {
    setLimit(received.command);
  } else if (received.item === P + 'charging') {
    setCharging(received.command);
  } else if (received.item === P + 'climate') {
    setClimate(received.command);
  } else {
    setClimateTarget(received.command);
  }
  try {
    publishTrips();
  } catch (e) {
    console.warn(`Škoda: Fahrtenliste: ${e}`);
  }
}

run();
