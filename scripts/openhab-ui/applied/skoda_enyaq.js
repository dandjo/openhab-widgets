// The Škoda Enyaq through the official MyŠkoda Public API (https://public.api.connect.skoda-auto.cz/docs), read only:
// what the car last reported to Škoda's backend, each part with the time the car captured it. A request does not wake
// the car, so a sleeping car's values stay as they were until it reports again by itself. The API key (created in the
// MyŠkoda app; it expires) and the VIN come from a JSON file, {"apiKey": "...", "vin": "..."}, so that neither stands
// in this script and a new key needs no change here.
// Requests are limited per vehicle (20 an hour, every request counts, failed ones too): every 5 minutes while the car
// charges or drives, otherwise every 15, and none while the quota is down to a reserve left for the app's API users.
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
const store = cache.private;
const nowMs = Date.now();

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

// one GET of the vehicle with its status code and the headers that tell the quota and the key's expiry
function fetchVehicle(credentials) {
  const HttpClient = Java.type('java.net.http.HttpClient');
  const HttpRequest = Java.type('java.net.http.HttpRequest');
  const BodyHandlers = Java.type('java.net.http.HttpResponse$BodyHandlers');
  const Duration = Java.type('java.time.Duration');
  const URI = Java.type('java.net.URI');
  const client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(15)).build();
  try {
    const request = HttpRequest.newBuilder(URI.create(VEHICLE_URL + credentials.vin))
      .header('X-API-Key', credentials.apiKey)
      .header('Accept', 'application/json')
      .timeout(Duration.ofSeconds(30))
      .GET()
      .build();
    const response = client.send(request, BodyHandlers.ofString());
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

function applyCharging(charging) {
  const status = charging.status || {};
  const battery = status.battery || {};
  const settings = charging.settings || {};
  postQuantity('soc', battery.stateOfChargeInPercent, '%');
  const meters = battery.remainingCruisingRangeInMeters;
  postQuantity('range', typeof meters === 'number' ? Math.round(meters / 1000) : null, 'km');
  // left out when the reported combination has no name (plugged in and unlocked without charging, after a drive)
  post('charging_state', status.state);
  postQuantity('charge_power', status.chargePowerInKw, 'kW');
  post('charge_type', status.chargeType);
  post('plug', onOff(status.plugConnectionState, 'CONNECTED', 'DISCONNECTED'));
  post('plug_locked', onOff(status.plugLockState, 'LOCKED', 'UNLOCKED'));
  let full = null;
  if (status.state === 'CHARGING') {
    if (status.fullyChargedAt) {
      full = status.fullyChargedAt;
    } else if (typeof status.remainingTimeToFullyChargedInMinutes === 'number' && charging.carCapturedTimestamp) {
      const capturedMs = Date.parse(charging.carCapturedTimestamp);
      full = new Date(capturedMs + status.remainingTimeToFullyChargedInMinutes * 60000).toISOString();
    }
  }
  postTime('full_at', full);
  // with battery care on the car stops at its care target (80 %) whatever the target set beside it says
  const care = onOff(settings.chargingCareMode, 'ACTIVATED', 'DEACTIVATED');
  post('battery_care', care);
  let limit = settings.targetStateOfChargeInPercent;
  if (care === 'ON' && typeof settings.batteryCareModeTargetValueInPercent === 'number') {
    limit = typeof limit === 'number' ? Math.min(limit, settings.batteryCareModeTargetValueInPercent)
      : settings.batteryCareModeTargetValueInPercent;
  }
  postQuantity('charge_limit', limit, '%');
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

function applyAirConditioning(air) {
  post('climate_state', air.state);
  const target = air.targetTemperature || {};
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

function due() {
  const active = state('charging_state') === 'CHARGING' || state('parking_state') === 'IN_MOTION' ||
    (items.getItem('e_car_power').numericState || 0) > HOME_CHARGING_WATTS;
  const minutes = active ? ACTIVE_MINUTES : IDLE_MINUTES;
  // a minute's slack, so the cron's own jitter does not skip a turn
  if (nowMs - (store.get('lastRequest') || 0) < (minutes - 1) * 60000) {
    return false;
  }
  if (nowMs < (store.get('retryAt') || 0)) {
    return false;
  }
  const remaining = store.get('remaining');
  return remaining === null || remaining === undefined || remaining > QUOTA_RESERVE ||
    nowMs >= (store.get('resetAt') || 0);
}

function run() {
  if (!due()) {
    return;
  }
  const credentials = readCredentials();
  if (credentials === null) {
    setApiStatus('NO_CREDENTIALS', `keine Zugangsdaten in ${CREDENTIALS}`);
    return;
  }
  store.put('lastRequest', nowMs);
  const response = fetchVehicle(credentials);
  if (response.remaining !== null && response.remaining !== undefined) {
    const remaining = Number(response.remaining);
    store.put('remaining', remaining);
    store.put('resetAt', nowMs + Number(response.reset || 3600) * 1000);
    post('api_requests_left', remaining);
  }
  if (response.keyExpiresAt) {
    postTime('api_key_expiry', response.keyExpiresAt);
  }
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
    apply(body.vehicle || {});
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
    setApiStatus('KEY_EXPIRED', 'API-Schlüssel abgelaufen oder ungültig (401)');
    if (!store.get('keyAlarm')) {
      store.put('keyAlarm', true);
      notify('Škoda: Der API-Schlüssel ist abgelaufen oder ungültig. Bitte in der MyŠkoda-App einen neuen erstellen und in openHAB eintragen.');
    }
  } else if (response.status === 403) {
    setApiStatus('NOT_AUTHORIZED', 'der API-Schlüssel gilt nicht für dieses Fahrzeug (403)');
  } else if (response.status === 429) {
    store.put('retryAt', nowMs + Number(response.retryAfter || 600) * 1000);
    setApiStatus('RATE_LIMITED', `Anfragelimit erreicht, nächster Versuch in ${response.retryAfter || 600} s`);
  } else {
    setApiStatus('ERROR', response.status === 0 ? `nicht erreichbar: ${response.error}` : `HTTP ${response.status}`);
  }
}

run();
