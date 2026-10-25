// The optimizers on string 2 of the Huawei inverter (user, 2026-10-20): 14 SUN2000-450W-P2, 8 on the west plane and 6
// on the north plane, each at the address FusionSolar shows as 1.0.<address> in its physical layout (north 1.0.1 to
// 1.0.6, west 1.0.7 to 1.0.14; string 1, east, has none). The inverter keeps their readings per 5 minutes for about a
// month in a file (Huawei's file transfer over Modbus, function 0x41, file 0x44), which openHAB's Modbus binding cannot
// read. This rule reads it through huawei_modbus_proxy (127.0.0.1:5502; the SDongle serves one connection only, see
// /opt/huawei_modbus_proxy/README.md), every minute at :30:
// - live, at 2, 7, ... past the hour, once the inverter has written its next 5 minutes: the readings since the newest
//   stored (huawei_optimizers_updated) or, while string 2 has no voltage, since a live read last found none, at most
//   the last 30 minutes;
// - a gap (at the first start the last 31 days, then what an outage left; not the night, which the live reads that
//   found none cover) is filled apart from that, a 30-minute piece
//   every minute at night (20 to 6 h) and every 5 minutes by day: each frame of the file costs the dongle about 2 s,
//   which openHAB's polling waits for. The gap still open is kept in huawei_optimizers_state;
// - each reading persisted with its own time; the series are in no persistence group, so openHAB does not store them
//   again with the time they arrived. Per optimizer its power, temperature and lifetime energy, per plane the power and
//   the day's energy, and the hottest optimizer's temperature. The newest reading sets the items' states, with each
//   optimizer's energy today (not persisted);
// - huawei_optimizers_status: how many run, which do not, alarms; huawei_optimizers_east_energy_total: string 1's
//   lifetime yield estimated from the optimizers' counters by the strings' measured ratio (string 1 has none);
// - a broadcast when an optimizer fails, that is, it does not run while at least half of its plane does and delivers
//   MIN_PLANE_POWER on average, or it reports an alarm, in two readings in a row; once, until it runs again in two
//   readings, which is reported too. Not running in weaker light counts neither way. A broadcast as well when no
//   reading comes in for an hour while string 2 produces;
// - once a day the optimizers' system information (file 0x45): a serial number that changed at an address is reported,
//   as the plane of each address is fixed here.
const HOST = '127.0.0.1';
const PORT = 5502;
const UNIT = 1;
const PLANES = { west: [7, 8, 9, 10, 11, 12, 13, 14], north: [1, 2, 3, 4, 5, 6] };
const PLANE_DE = { west: 'West', north: 'Nord' };
const P = 'huawei_optimizers_';
const HISTORY = 31 * 86400; // s the inverter keeps, about a month
const PIECE = 1800; // s of readings per request while behind
const BEHIND = 900; // s after the newest reading from which the rule counts as behind
const LATE = 900; // s by which the inverter may write a reading after its time (it does within 2.5 minutes)
const STATUS_DE = { 0: 'offline', 1: 'Standby', 3: 'Fehler', 4: 'in Betrieb', 12: 'aus' };
const RUNNING = 4;
// W the running optimizers of a plane deliver on average at least before one that does not run counts as failed: at
// dawn and dusk some start later or stop earlier, the others then at 3.5 W on average at most (19 September to 23
// October 2026; 1.0.2 offline at dawn on 23 October was reported as failed)
const MIN_PLANE_POWER = 10;
// the alarm bits as huawei-solar knows them; bit 31 is set in every reading of all optimizers (a flag, not an alarm)
// and, like any other bit not listed, ignored
const ALARMS_DE = [[0x1, 'Eingangsüberspannung'], [0x2, 'Eingangsunterspannung'], [0x8, 'Ausgangsüberspannung'],
  [0x10, 'Übertemperatur'], [0x20, 'Ausgangskurzschluss'], [0x40, 'EEPROM-Fehler'], [0x80, 'Hardwarefehler'],
  [0x100, 'Spannung gegen Erde abnormal'], [0x200, 'Abschaltung nach Heartbeat-Timeout'], [0x400, 'Schnellabschaltung'],
  [0x800, 'Escape-Anforderung'], [0x1000, 'Versionskonflikt'], [0x8000, 'Eingangsüberspannung'],
  [0x10000, 'Übertemperatur'], [0x20000, 'Ausgangskurzschluss'], [0x40000, 'Hardwarefehler'],
  [0x80000, 'Versionskonflikt'], [0x100000, 'Rückspeisung'], [0x200000, 'Ausgangsspannung abnormal'],
  [0x400000, 'Update fehlgeschlagen']];

const ADDRESSES = [...PLANES.north, ...PLANES.west];
const planeOf = (a) => (PLANES.west.includes(a) ? 'west' : 'north');
const nameOf = (a) => `${PLANE_DE[planeOf(a)]} 1.0.${a}`;
const itemOf = (a, what) => `huawei_optimizer_${String(a).padStart(2, '0')}_${what}`;
const round = (v, d) => Math.round(v * 10 ** d) / 10 ** d;

// ------------------------------------------------------------------ the files (bytes as numbers 0 to 255)

function crc16(bytes) {
  let crc = 0xffff;
  for (const b of bytes) {
    crc ^= b;
    for (let i = 0; i < 8; i++) {
      crc = crc & 1 ? (crc >>> 1) ^ 0xa001 : crc >>> 1;
    }
  }
  return crc;
}

const u16le = (b, i) => b[i] | (b[i + 1] << 8);
const i16le = (b, i) => (u16le(b, i) << 16) >> 16;
const u32le = (b, i) => (b[i] | (b[i + 1] << 8) | (b[i + 2] << 16) | (b[i + 3] << 24)) >>> 0;
const i32le = (b, i) => b[i] | (b[i + 1] << 8) | (b[i + 2] << 16) | (b[i + 3] << 24);
const u16be = (b, i) => (b[i] << 8) | b[i + 1];
const u32be = (b, i) => ((b[i] << 24) | (b[i + 1] << 16) | (b[i + 2] << 8) | b[i + 3]) >>> 0;
const be32 = (v) => [(v >>> 24) & 255, (v >>> 16) & 255, (v >>> 8) & 255, v & 255];

// file 0x44: a 12-byte head, then per 5 minutes the time (the inverter's local seconds), 4 bytes, the length and the
// number of optimizers, and per optimizer 26 bytes, little-endian; the readings oldest first
function parseReadings(b) {
  const out = [];
  let i = 12;
  while (i + 12 <= b.length) {
    const t = i32le(b, i);
    const n = i16le(b, i + 10);
    i += 12;
    if (n < 0 || i + 26 * n > b.length) {
      break;
    }
    const opt = {};
    for (let k = 0; k < n; k++, i += 26) {
      opt[i16le(b, i)] = {
        power: i16le(b, i + 2) / 10, alarm: u32le(b, i + 6), vout: i16le(b, i + 10) / 10, iout: i16le(b, i + 12) / 100,
        vin: i16le(b, i + 14) / 10, iin: i16le(b, i + 16) / 100, temp: i16le(b, i + 18) / 10, status: i16le(b, i + 20),
        energy: u32le(b, i + 22) / 1000,
      };
    }
    out.push({ t, opt });
  }
  return out.sort((x, y) => x.t - y.t);
}

// file 0x44 whole and as asked for, by what its head and records say of themselves (from, to: the window in the
// inverter's local seconds): the version V101 and the number of records, each record as long as its optimizers (the
// length after the time, 2 + 26 per optimizer), each optimizer a known address once, its time inside the window, the
// last record ending at the file's end. Needed since the inverter's CRC for this file cannot be trusted: from 24
// October 2026 about 15:40 its completion reports 0xFFFF or another wrong value, while the data are unchanged (the
// same readings as stored the day before with a valid CRC); file 0x45's CRC stays right
function wellFormed(b, from, to) {
  if (b.length < 12 || String.fromCharCode(...b.slice(0, 4)) !== 'V101') {
    return false;
  }
  let i = 12;
  let records = 0;
  while (i < b.length) {
    if (i + 12 > b.length) {
      return false;
    }
    const t = i32le(b, i);
    const n = i16le(b, i + 10);
    if (n < 1 || n > ADDRESSES.length || u16le(b, i + 8) !== 2 + 26 * n || i + 12 + 26 * n > b.length || t < from
      || t > to) {
      return false;
    }
    const seen = new Set();
    for (let k = 0; k < n; k++) {
      const a = i16le(b, i + 12 + 26 * k);
      if (!ADDRESSES.includes(a) || seen.has(a)) {
        return false;
      }
      seen.add(a);
    }
    i += 12 + 26 * n;
    records++;
  }
  return records === u32le(b, 4);
}

const sameBytes = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);

// a window w (UTC seconds) in the inverter's local seconds (local(t): t and the offset at t): when the clocks go back
// an hour, a window across the switch would start later than it ends in local time, which the inverter rejects (25
// October 2026, 02:12 to 02:35: exception 3 on the start); it then starts its length before its local end, a little
// more than asked for, which only reads readings again
function localWindow(w, local) {
  const to = local(w.to);
  return { from: Math.min(local(w.from), to - (w.to - w.from)), to };
}

// file 0x45: a 14-byte head (version, sequence, length, a flag, 3 bytes, the number of optimizers), then per optimizer
// 106 (V102) or 116 bytes (V103), big-endian: address, online, a byte, string, position, serial number (20 bytes), ...
function parseSerials(b) {
  const version = String.fromCharCode(...b.slice(0, 4));
  const size = version === 'V103' ? 116 : version === 'V102' ? 106 : 0;
  const n = u16be(b, 12);
  const out = {};
  for (let k = 0, i = 14; size && k < n && i + size <= b.length; k++, i += size) {
    out[u16be(b, i)] = String.fromCharCode(...b.slice(i + 8, i + 28).filter((c) => c > 32 && c < 127));
  }
  return out;
}

// ------------------------------------------------------------------ what to read, what to make of it

// the time up to which no reading is missing but those in the gap: the newest stored (updated) or, when later, quiet,
// which the live reads advance; null for neither
const knownUntil = (updated, quiet) => (updated === null ? quiet : quiet === null ? updated : Math.max(updated, quiet));

// the live window [from, to] (UTC seconds) of this run, or null, and the gap it leaves when the time up to which no
// reading is missing (known, null at the first start) lies further back than a piece; minute local
function planLive(now, known, minute) {
  if (minute % 5 !== 2) {
    return null;
  }
  const from = known === null ? now - PIECE : Math.max(known + 1, now - PIECE);
  const gap = known === null ? [now - HISTORY, from - 1] : known + 1 < from ? [known + 1, from - 1] : null;
  return { from, to: now, gap };
}

// quiet after a live read that found no readings while string 2 has no voltage (the optimizers report from a few minutes
// before it has one to a few after): its window, but for the last LATE seconds, which the inverter may still write
const quietAfter = (quiet, live) => Math.max(quiet === null ? 0 : quiet, live.to - LATE);

// the next piece of a gap [from, to]
const pieceOf = (gap) => ({ from: gap[0], to: Math.min(gap[1], gap[0] + PIECE) });

// the piece of the gap to fill in this run, or null: every minute at night but at the live runs' minutes, at 4, 9, ...
// past the hour by day
function planFill(gap, hour, minute) {
  const slot = hour >= 20 || hour < 6 ? minute % 5 !== 2 : minute % 5 === 4;
  return gap && slot ? pieceOf(gap) : null;
}

// a gap with another one, as one: what lies between them is read again, which only overwrites equal points
function mergeGap(gap, more) {
  return !gap ? more : !more ? gap : [Math.min(gap[0], more[0]), Math.max(gap[1], more[1])];
}

// readings (oldest first) to the points to persist per item ([UTC seconds, state]), the newest's states, and the
// optimizers' energy today; memory carries the day, each optimizer's energy at the day's start and last; baseOf(a,
// day) asks persistence for an optimizer's lifetime energy before a local day when memory has none; toUtc(t) turns the
// inverter's local seconds into UTC seconds
function evaluate(readings, memory, baseOf, toUtc) {
  const points = {};
  const states = {};
  const add = (item, t, state) => (points[item] = points[item] || []).push([t, state]);
  for (const r of readings) {
    const t = toUtc(r.t);
    const day = Math.floor(r.t / 86400);
    // a new day starts from the lifetime energies the day before ended with (nothing is made at night), when memory
    // holds the day before; else (after a restart, or a gap filled out of order) from those persistence holds
    if (memory.day !== day) {
      memory.base = memory.day === day - 1 ? { ...memory.last } : {};
      memory.day = day;
      memory.today = {};
    }
    const planes = { west: { power: 0 }, north: { power: 0 } };
    let hottest = null;
    for (const a of ADDRESSES) {
      const o = r.opt[a];
      if (!o) {
        continue;
      }
      if (memory.base[a] === undefined) {
        const base = baseOf(a, day);
        memory.base[a] = base !== null && base <= o.energy ? base : o.energy;
      }
      memory.last[a] = o.energy;
      memory.today[a] = Math.max(0, o.energy - memory.base[a]);
      planes[planeOf(a)].power += o.power;
      hottest = hottest === null ? o.temp : Math.max(hottest, o.temp);
      add(itemOf(a, 'power'), t, `${round(o.power, 1)} W`);
      add(itemOf(a, 'temperature'), t, `${round(o.temp, 1)} °C`);
      add(itemOf(a, 'energy'), t, `${round(o.energy, 3)} kWh`);
    }
    for (const plane of Object.keys(PLANES)) {
      const today = PLANES[plane].reduce((s, a) => s + (memory.today[a] || 0), 0);
      add(`${P}${plane}_power`, t, `${round(planes[plane].power, 1)} W`);
      add(`${P}${plane}_energy_day`, t, `${round(today, 3)} kWh`);
    }
    if (hottest !== null) {
      add(`${P}temperature_max`, t, `${round(hottest, 1)} °C`);
    }
  }
  for (const [item, list] of Object.entries(points)) {
    states[item] = list[list.length - 1][1];
  }
  for (const a of ADDRESSES) {
    if (memory.today[a] !== undefined) {
      states[itemOf(a, 'energy_day')] = `${round(memory.today[a], 3)} kWh`;
    }
  }
  return { points, states };
}

function alarmsOf(o) {
  return ALARMS_DE.filter(([bit]) => o.alarm & bit).map(([, text]) => text)
    .filter((text, i, all) => all.indexOf(text) === i);
}

// the newest reading's summary for huawei_optimizers_status
function statusOf(r) {
  const running = ADDRESSES.filter((a) => r.opt[a] && r.opt[a].status === RUNNING);
  const others = ADDRESSES.filter((a) => !running.includes(a));
  let text = running.length === ADDRESSES.length ? `alle ${ADDRESSES.length} in Betrieb`
    : `${running.length} von ${ADDRESSES.length} in Betrieb`;
  if (others.length > 0 && others.length <= 4) {
    text += ' · ' + others.map((a) => `${nameOf(a)} ${r.opt[a] ? STATUS_DE[r.opt[a].status] || r.opt[a].status : 'fehlt'}`)
      .join(', ');
  }
  const alarms = ADDRESSES.filter((a) => r.opt[a] && alarmsOf(r.opt[a]).length > 0);
  if (alarms.length > 0) {
    text += ' · Alarm ' + alarms.map((a) => `${nameOf(a)}: ${alarmsOf(r.opt[a]).join(', ')}`).join('; ');
  }
  return text;
}

// an optimizer's problem in a reading: an alarm, or not running while at least half of its plane runs and delivers
// MIN_PLANE_POWER on average; null when it runs; undefined when it does not run in weaker light, which tells nothing
function problemOf(r, a) {
  const o = r.opt[a];
  if (o && alarmsOf(o).length > 0) {
    return `Alarm ${alarmsOf(o).join(', ')}`;
  }
  if (o && o.status === RUNNING) {
    return null;
  }
  const plane = PLANES[planeOf(a)];
  const running = plane.filter((x) => r.opt[x] && r.opt[x].status === RUNNING);
  const mean = running.length ? running.reduce((s, x) => s + r.opt[x].power, 0) / running.length : 0;
  if (running.length * 2 >= plane.length && mean >= MIN_PLANE_POWER) {
    return o ? STATUS_DE[o.status] || `Status ${o.status}` : 'keine Daten';
  }
  return undefined;
}

// the broadcasts for a live reading; fail carries per optimizer the readings in a row with and without a problem and
// whether its failure was reported
function failures(r, fail) {
  const notices = [];
  for (const a of ADDRESSES) {
    const f = fail[a] || (fail[a] = { bad: 0, good: 0, told: false });
    const problem = problemOf(r, a);
    if (problem === undefined) {
      continue;
    }
    if (problem) {
      f.bad++;
      f.good = 0;
      if (f.bad >= 2 && !f.told) {
        const plane = PLANES[planeOf(a)].filter((x) => x !== a && r.opt[x] && r.opt[x].status === RUNNING);
        const mean = plane.length ? Math.round(plane.reduce((s, x) => s + r.opt[x].power, 0) / plane.length) : 0;
        notices.push(`PV-Optimierer ${nameOf(a)} ausgefallen: ${problem}. Die übrigen Module ${PLANE_DE[planeOf(a)]} `
          + `liefern im Schnitt ${mean} W.`);
        f.told = true;
      }
    } else {
      f.good++;
      f.bad = 0;
      if (f.good >= 2 && f.told) {
        notices.push(`PV-Optimierer ${nameOf(a)} läuft wieder.`);
        f.told = false;
      }
    }
  }
  return notices;
}

// ------------------------------------------------------------------ openHAB and the proxy

function run() {
  const Socket = Java.type('java.net.Socket');
  const InetSocketAddress = Java.type('java.net.InetSocketAddress');
  const DataInputStream = Java.type('java.io.DataInputStream');
  const ByteArray = Java.type('byte[]');
  const Thread = Java.type('java.lang.Thread');
  const JInstant = Java.type('java.time.Instant');
  const ZoneId = Java.type('java.time.ZoneId');
  const ZoneOffset = Java.type('java.time.ZoneOffset');
  const LocalDateTime = Java.type('java.time.LocalDateTime');
  const DateTimeFormatter = Java.type('java.time.format.DateTimeFormatter');
  const JTimeSeries = Java.type('org.openhab.core.types.TimeSeries');
  const QuantityType = Java.type('org.openhab.core.library.types.QuantityType');
  const Persistence = Java.type('org.openhab.core.persistence.extensions.PersistenceExtensions');
  const zone = ZoneId.of('Europe/Vienna');
  const store = cache.private;
  const now = Math.floor(Date.now() / 1000);
  const local = (t) => t + zone.getRules().getOffset(JInstant.ofEpochSecond(t)).getTotalSeconds();
  const toUtc = (t) => LocalDateTime.ofEpochSecond(t, 0, ZoneOffset.UTC).atZone(zone).toEpochSecond();
  const clock = LocalDateTime.ofEpochSecond(local(now), 0, ZoneOffset.UTC);
  const notify = (text) => {
    actions.NotificationAction.sendBroadcastNotification(text);
    console.info(`Optimierer: ${text}`);
  };

  const updated = items.getItem(P + 'updated');
  const stored = updated.isUninitialized ? null : updated.rawState.getInstant().getEpochSecond();
  const stateItem = items.getItem(P + 'state');
  const state = stateItem.isUninitialized ? {} : JSON.parse(stateItem.state);

  // no readings for an hour while string 2 produces
  const pv2 = items.getItem('huawei_inverter_pv2_power').numericState;
  if (stored !== null && now - stored > 3600 && pv2 !== null && pv2 > 100 && !store.get('silent')) {
    notify('PV-Optimierer: seit einer Stunde keine Daten vom Wechselrichter, obwohl String 2 Strom erzeugt.');
    store.put('silent', true);
  }
  // the day's energies back to 0 at midnight while today has no reading yet, not only with the morning's first
  // reading; the status once the readings stop in the evening
  const today = clock.toLocalDate().toString();
  const storedDay = stored === null ? null
    : LocalDateTime.ofEpochSecond(local(stored), 0, ZoneOffset.UTC).toLocalDate().toString();
  if (storedDay !== today && store.get('zeroDay') !== today) {
    for (const a of ADDRESSES) {
      items.getItem(itemOf(a, 'energy_day')).postUpdate('0 kWh');
    }
    for (const plane of Object.keys(PLANES)) {
      items.getItem(`${P}${plane}_energy_day`).postUpdate('0 kWh');
    }
    store.put('zeroDay', today);
  }
  if (stored !== null && now - stored > 1800) {
    const since = `keine Messung seit ${JInstant.ofEpochSecond(stored).atZone(zone).toLocalTime().toString().slice(0, 5)}`;
    if (items.getItem(P + 'status').state !== since) {
      items.getItem(P + 'status').postUpdate(since);
    }
  }

  const quiet = typeof state.quiet === 'number' ? state.quiet : null;
  const live = planLive(now, knownUntil(stored, quiet), clock.getMinute());
  const fill = live ? null : planFill(state.gap || null, clock.getHour(), clock.getMinute());
  if (!live && !fill) {
    return;
  }

  let c = null;
  const exchange = (pdu) => {
    c.tid = (c.tid % 0xffff) + 1;
    const frame = [c.tid >> 8, c.tid & 255, 0, 0, (pdu.length + 1) >> 8, (pdu.length + 1) & 255, UNIT, ...pdu];
    c.out.write(Java.to(frame.map((b) => (b << 24) >> 24), 'byte[]'));
    c.out.flush();
    for (;;) {
      const head = new ByteArray(7);
      c.in.readFully(head);
      const h = [];
      for (let i = 0; i < 7; i++) h.push(head[i] & 255);
      const body = new ByteArray(((h[4] << 8) | h[5]) - 1);
      c.in.readFully(body);
      if (((h[0] << 8) | h[1]) === c.tid) {
        const out = [];
        for (let i = 0; i < body.length; i++) out.push(body[i] & 255);
        return out;
      }
    }
  };
  // a file: start (with the window for 0x44), its frames, completion with the CRC; a frame the dongle did not answer
  // (0x0B from the proxy) or was too busy for (0x06) is asked for again, twice at most
  const patiently = (pdu, what) => {
    let r = null;
    for (let attempt = 0; attempt < 3; attempt++) {
      r = exchange(pdu);
      if (!(r[0] & 0x80) || ![0x06, 0x0b].includes(r[1])) {
        break;
      }
      Thread.sleep(1000);
    }
    if (r[0] & 0x80) {
      throw new Error(`Datei ${pdu[3].toString(16)}: ${what} abgelehnt (Ausnahme ${r[1]})`);
    }
    return r;
  };
  // { data, trusted }: trusted when the CRC the inverter reports fits (or the file is empty); a wrong CRC throws
  // when strict
  const readOnce = (type, custom, strict) => {
    const start = patiently([0x41, 0x05, 1 + custom.length, type, ...custom], 'Start');
    const length = u32be(start, 4);
    const size = start[8];
    const data = [];
    for (let n = 0; n * size < length; n++) {
      data.push(...patiently([0x41, 0x06, 3, type, n >> 8, n & 255], `Teil ${n}`).slice(6));
    }
    const done = patiently([0x41, 0x0c, 1, type], 'Abschluss');
    // an empty file (a window without readings) has no CRC worth checking
    const trusted = length === 0 || crc16(data) === u16be(done, 4);
    if (!trusted && strict) {
      throw new Error(`Datei ${type.toString(16)}: Prüfsumme falsch`);
    }
    return { data, trusted };
  };
  // the dongle now and then rejects a frame in the middle of a file (exception 3, 20 October 2026: in one of a few
  // files of 10 frames, of any age): the upload is closed and read again from its start, twice at most
  const readFile = (type, custom, strict = true) => {
    for (let attempt = 0; ; attempt++) {
      try {
        return readOnce(type, custom, strict);
      } catch (e) {
        if (attempt >= 2) {
          throw e;
        }
        exchange([0x41, 0x0c, 1, type]);
        console.debug(`Optimierer: ${e.message}, neuer Versuch`);
        Thread.sleep(2000);
      }
    }
  };

  try {
    const s = new Socket();
    s.connect(new InetSocketAddress(HOST, PORT), 5000);
    // the proxy answers within 8 s for a frame of a file, behind at most one other client's request
    s.setSoTimeout(20000);
    c = { s, in: new DataInputStream(s.getInputStream()), out: s.getOutputStream(), tid: 0 };

    // an optimizer's lifetime energy before a local day: the reading persistence holds from the day before or the
    // night before (one weeks old, as the gap fill writes them, is none), else the day's first reading stored
    const baseOf = (a, day) => {
      const item = items.getItem(itemOf(a, 'energy')).rawItem;
      const midnight = LocalDateTime.ofEpochSecond(day * 86400, 0, ZoneOffset.UTC).atZone(zone);
      const h = Persistence.persistedState(item, midnight, 'influxdb');
      if (h !== null && h.getTimestamp().toEpochSecond() >= midnight.toEpochSecond() - 30 * 3600) {
        return parseFloat(h.getState().toString());
      }
      const first = Persistence.getAllStatesBetween(item, midnight, midnight.plusDays(1), 'influxdb').iterator();
      return first.hasNext() ? parseFloat(first.next().getState().toString()) : null;
    };
    // the readings of a window; with a CRC that does not fit (see wellFormed) the data count only when they hold
    // together and a second upload brings the same bytes, as a frame of another file would fit in among the readings'
    // values unnoticed
    const read = (w) => {
      const lw = localWindow(w, local);
      const custom = [0x10, 12, ...be32(lw.from), ...be32(lw.to), 0, 0, 0, 0];
      const first = readFile(0x44, custom, false);
      if (first.trusted) {
        return parseReadings(first.data);
      }
      if (!wellFormed(first.data, lw.from, lw.to)) {
        throw new Error('Datei 44: Prüfsumme falsch und Aufbau fehlerhaft');
      }
      const second = readFile(0x44, custom, false);
      if (!second.trusted && !sameBytes(first.data, second.data)) {
        throw new Error('Datei 44: Prüfsumme falsch, zwei Lesungen verschieden');
      }
      console.debug(`Optimierer: Datei 44 ohne passende Prüfsumme, ${second.trusted ? 'zweite Lesung mit passender'
        : 'Aufbau und zweite Lesung stimmen'}`);
      return parseReadings(second.trusted ? second.data : first.data);
    };
    const persist = (points) => {
      for (const [item, list] of Object.entries(points)) {
        const series = new JTimeSeries(JTimeSeries.Policy.ADD);
        for (const [t, value] of list) {
          series.add(JInstant.ofEpochSecond(t), new QuantityType(value));
        }
        Persistence.persist(items.getItem(item).rawItem, series, 'influxdb');
      }
    };

    if (live) {
      const readings = read(live);
      // an empty answer is believed only while string 2 has no voltage (unknown right after a start, null): by day the
      // next live reads look back again, and only readings show what lies behind
      const volts = items.getItem('huawei_inverter_pv2_voltage').numericState;
      const dark = readings.length === 0 && volts !== null && volts < 1;
      if (readings.length > 0 || dark) {
        // what lies between the time up to which no reading is missing and this window is filled apart
        state.gap = mergeGap(state.gap || null, live.gap);
      }
      if (dark) {
        state.quiet = quietAfter(quiet, live);
        // the powers read 0 once no reading can come any more: the inverter does not always end the day with a
        // reading of 0 W (24 October 2026: 18:05 with 33 W was the last), and the panels showed it until the morning;
        // states only, the readings stay as the inverter wrote them
        if (stored === null || now - stored > LATE) {
          const powers = [...ADDRESSES.map((a) => itemOf(a, 'power')), ...Object.keys(PLANES).map((p) => `${P}${p}_power`)];
          for (const name of powers) {
            if (items.getItem(name).numericState !== 0) {
              items.getItem(name).postUpdate('0 W');
            }
          }
        }
      } else if (readings.length > 0) {
        const memory = store.get('memory') || { last: {} };
        const { points, states } = evaluate(readings, memory, baseOf, toUtc);
        persist(points);
        const newest = readings[readings.length - 1];
        if (now - toUtc(newest.t) <= BEHIND) {
          for (const [item, value] of Object.entries(states)) {
            items.getItem(item).postUpdate(value);
          }
          items.getItem(P + 'status').postUpdate(statusOf(newest));
          // string 1 (east) has no optimizers: its lifetime yield estimated as the optimizers' lifetime counters times
          // the strings' measured ratio (energy_daily_pv1_generation / _pv2_, from the first readings of 30 September
          // 2024; the counters run since the plant started, years before), for the east modules' estimate on the
          // Photovoltaik page (user, 2026-10-20)
          const since = LocalDateTime.of(2024, 9, 30, 0, 0).atZone(zone);
          const sumOf = (name) => {
            const v = Persistence.sumSince(items.getItem(name).rawItem, since, 'influxdb');
            return v === null ? null : parseFloat(v.toString());
          };
          const lifetime = ADDRESSES.every((a) => newest.opt[a])
            ? ADDRESSES.reduce((sum, a) => sum + newest.opt[a].energy, 0) : null;
          const s1 = sumOf('energy_daily_pv1_generation');
          const s2 = sumOf('energy_daily_pv2_generation');
          if (lifetime !== null && s1 > 0 && s2 > 0) {
            items.getItem(P + 'east_energy_total').postUpdate(`${round(lifetime * s1 / s2, 1)} kWh`);
          }
        }
        updated.postUpdate(JInstant.ofEpochSecond(toUtc(newest.t)).atZone(zone)
          .format(DateTimeFormatter.ISO_OFFSET_DATE_TIME));
        store.put('memory', memory);
        store.put('silent', false);
        // failures only from live readings
        const fail = store.get('fail') || {};
        for (const r of readings.filter((x) => now - toUtc(x.t) <= BEHIND)) {
          failures(r, fail).forEach(notify);
        }
        store.put('fail', fail);
      }
    } else {
      // a piece of the gap, oldest first; empty pieces (nights) are skipped, up to 8 in a run. A piece that fails in
      // three runs in a row is given up, so that the gap does not stick at it
      let w = fill;
      for (let k = 0; k < 8 && w; k++) {
        let readings;
        try {
          readings = read(w);
          store.remove('fails');
        } catch (e) {
          const fails = (store.get('fails') || 0) + 1;
          store.put('fails', fails);
          if (fails < 3) {
            throw e;
          }
          console.warn(`Optimierer: ${e.message}; die Messungen ab ${JInstant.ofEpochSecond(w.from).atZone(zone)
            .toLocalDateTime().toString().replace('T', ' ')} bleiben aus`);
          store.remove('fails');
          readings = [];
        }
        if (readings.length > 0) {
          const memory = store.get('fillMemory') || { last: {} };
          persist(evaluate(readings, memory, baseOf, toUtc).points);
          store.put('fillMemory', memory);
        }
        state.gap = w.to >= state.gap[1] ? null : [w.to + 1, state.gap[1]];
        stateItem.postUpdate(JSON.stringify(state));
        if (readings.length > 0 || !state.gap) {
          break;
        }
        w = pieceOf(state.gap);
      }
      if (!state.gap) {
        console.info('Optimierer: Lücke nachgeladen');
        store.remove('fillMemory');
      }
    }

    // the serial numbers once a day, in a live run
    if (live && store.get('serialsDay') !== today) {
      const found = parseSerials(readFile(0x45, []).data);
      const known = state.serials || {};
      const changed = Object.keys(known).length > 0
        ? ADDRESSES.filter((a) => (found[a] || '') !== (known[a] || '')) : [];
      if (Object.keys(found).length !== ADDRESSES.length) {
        notify(`PV-Optimierer: der Wechselrichter meldet ${Object.keys(found).length} statt ${ADDRESSES.length} Optimierer.`);
      }
      for (const a of changed) {
        notify(`PV-Optimierer an Adresse 1.0.${a} (${nameOf(a)}) getauscht oder neu: Seriennummer …${(found[a] || '–')
          .slice(-4)} statt …${(known[a] || '–').slice(-4)}. Die Zuordnung West/Nord in der Regel prüfen.`);
      }
      state.serials = found;
      store.put('serialsDay', today);
    }
    stateItem.postUpdate(JSON.stringify(state));
  } catch (e) {
    console.warn(`Optimierer: ${e.message || e}`);
  } finally {
    if (c !== null) {
      c.s.close();
    }
  }
}

if (typeof TESTING === 'undefined') {
  run();
}
