#!/usr/bin/env python3
"""The heating curve as the controller runs it, learnt from the data (user, 2026-10-09): the rule heatpump_heating_curve
fits the leaving water setpoint against the outdoor temperature it is made of (espaltherma_ext_ambient_temp_avg, see
outdoor_avg.py) every day at 03:00 (a run takes about 8 s; between the downsampler at 01:00 and Monday's backup at
04:00) from the last year's heating and writes the curve as JSON into
heatpump_heating_curve for the heat pump page's tile. Quarter hours count where the house was heated (space heating
heat above 300 W on average), no hot water was made, no leaving water offset was set and the Smart Grid was normal,
by heatpump_metering's split, which judges valve, pump, compressor and heaters; the raw signals (valve on the heating
circuit, compressor and pump running, no defrost, heating on, all through) gave the same curve to the hundredth with
ten series instead of six, so the faster split stays (user, 2026-10-09);
the medians of their setpoints per half kelvin are fitted with the controller's curve, flat, sloping, flat between two
knees (least squares, knees on the bins, a plateau at least 2 K of data wide). A knee the data does not reach stays open: there the line runs on, and the
tile draws it dashed. Without a day of heating in the year (96 quarter hours) the item keeps its curve.
JSON: p the polyline [[x, y], ...] of six points, the axis' left end, the data's cold end, knee 1, knee 2, the data's
warm end, the axis' right end (the first and last segment beyond the data); k the two knees; b the bins fitted, [x,
median setpoint, quarter hours]; rms the fit's error over the bins (K); n the heating quarter hours; from, to their first and last day (UTC); at when it was computed.
Usage: heating_curve.py check|apply   (on homepi, as pi; the API token from ~/.openhab_token)"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080/rest"
TOKEN = open(os.path.expanduser("~/.openhab_token")).read().strip()
ITEM = "heatpump_heating_curve"
ITEM_DTO = {"type": "String", "name": ITEM, "label": "Wärmepumpe Heizkurve", "category": "material:show_chart",
            "tags": [], "groupNames": ["mapdb_change_restore"]}
SCRIPT = r"""// the heating curve as the controller runs it, learnt every day from the last year's heating: the leaving water
// setpoint against the outdoor temperature it is made of (espaltherma_ext_ambient_temp_avg), for the heat pump page's
// tile. Quarter hours count where the house was heated (space heating heat above 300 W, from heatpump_metering's
// split of valve, pump, compressor and heaters), no hot water was made, no offset was set and the Smart Grid was
// normal; the medians of their setpoints per half kelvin are fitted with the
// controller's curve, flat, sloping, flat between two knees. A knee the data does not reach stays open and the line
// runs on. Without a day of heating in the year the curve stays as it was.
const Q = (agg, item) => `SELECT ${agg}(value) FROM "${item}" WHERE time > now() - 365d GROUP BY time(15m) fill(previous)`;
const SERIES = [['heat', 'mean', 'espaltherma_heating_power_space'], ['dhw', 'max', 'espaltherma_heating_power_dhw'],
  ['set', 'mean', 'espaltherma_leaving_water_setpoint'], ['out', 'last', 'espaltherma_ext_ambient_temp_avg'],
  ['offset', 'max', 'pyaltherma_leaving_water_temp_offset_heating'], ['sg', 'last', 'espaltherma_smart_grid']];
const round = (v, d) => Math.round(v * 10 ** d) / 10 ** d;

function fitCurve(points) {
  if (points.length < 96) {
    return null;
  }
  const bins = new Map();
  for (const [x, y] of points) {
    const b = Math.round(x * 2) / 2;
    if (!bins.has(b)) {
      bins.set(b, []);
    }
    bins.get(b).push(y);
  }
  const pts = [...bins.entries()].filter(([, ys]) => ys.length >= 4).map(([b, ys]) => {
    ys.sort((a, c) => a - c);
    const k = ys.length;
    return [b, k % 2 ? ys[(k - 1) / 2] : (ys[k / 2 - 1] + ys[k / 2]) / 2, k];
  }).sort((a, c) => a[0] - c[0]);
  if (pts.length < 6 || pts[pts.length - 1][0] - pts[0][0] < 3) {
    return null;
  }
  const xs = pts.map((p) => p[0]);
  const share = (x, x1, x2) => Math.min(1, Math.max(0, (x - x1) / (x2 - x1)));
  // a knee inside the data needs a plateau of at least 4 bins (2 K) beyond it, else it stays at the data's end (open)
  const last = xs.length - 1;
  let best = null;
  for (let i = 0; i < xs.length; i++) {
    for (let j = i + 1; j < xs.length; j++) {
      const x1 = xs[i];
      const x2 = xs[j];
      if (x2 - x1 < 2 || (i > 0 && i < 4) || (j < last && j > last - 4)) {
        continue;
      }
      let s00 = 0, s01 = 0, s11 = 0, t0 = 0, t1 = 0;
      for (const [x, y] of pts) {
        const u = share(x, x1, x2);
        s00 += (1 - u) * (1 - u); s01 += (1 - u) * u; s11 += u * u; t0 += (1 - u) * y; t1 += u * y;
      }
      const det = s00 * s11 - s01 * s01;
      if (Math.abs(det) < 1e-9) {
        continue;
      }
      const y1 = (t0 * s11 - t1 * s01) / det;
      const y2 = (s00 * t1 - s01 * t0) / det;
      let sse = 0;
      for (const [x, y] of pts) {
        const e = y - (y1 + (y2 - y1) * share(x, x1, x2));
        sse += e * e;
      }
      if (best === null || sse < best.sse - 1e-9) {
        best = { x1, x2, y1, y2, sse };
      }
    }
  }
  if (best === null) {
    return null;
  }
  const { x1, x2, y1, y2 } = best;
  const xmin = xs[0], xmax = xs[last];
  const open1 = x1 === xmin, open2 = x2 === xmax;
  const slope = (y2 - y1) / (x2 - x1);
  const f = (x) => x <= x1 ? (open1 ? y1 + slope * (x - x1) : y1) :
    x >= x2 ? (open2 ? y2 + slope * (x - x2) : y2) : y1 + slope * (x - x1);
  const left = Math.min(-15, Math.floor(xmin) - 1), right = Math.max(20, Math.ceil(xmax) + 1);
  const pt = (x) => [round(x, 2), round(f(x), 2)];
  return { p: [pt(left), pt(xmin), pt(x1), pt(x2), pt(xmax), pt(right)], k: [pt(x1), pt(x2)],
           b: pts.map(([x, y, n]) => [x, round(y, 2), n]), rms: round(Math.sqrt(best.sse / pts.length), 3) };
}

// one query per series: openHAB's HTTP action buffers at most 2 MB, a year of all six is 3.7 MB
const cols = {};
let missing = false;
for (const [key, agg, item] of SERIES) {
  const body = actions.HTTP.sendHttpGetRequest('http://127.0.0.1:8086/query?db=openhab&epoch=s&q=' +
                                               encodeURIComponent(Q(agg, item)), 120000);
  const result = body ? (JSON.parse(body).results || [])[0] : null;
  const s = result && result.series && result.series[0];
  missing = missing || !result;
  cols[key] = new Map(s ? s.values : []);
}
if (missing) {
  console.warn('heating curve: InfluxDB did not answer; curve kept');
} else {
  const points = [];
  let first = null, last = null;
  for (const [t, set] of cols.set) {
    const heat = cols.heat.get(t), out = cols.out.get(t);
    if (set === null || out === null || out === undefined || !(heat > 300) || (cols.dhw.get(t) || 0) !== 0 ||
        (cols.offset.get(t) || 0) !== 0 || String(cols.sg.get(t)) !== '0') {
      continue;
    }
    points.push([out, set]);
    first = first === null ? t : first;
    last = t;
  }
  const curve = fitCurve(points);
  if (curve === null) {
    console.info(`heating curve: ${points.length} heating quarter hours in the last year, too few; curve kept`);
  } else {
    const day = (t) => new Date(t * 1000).toISOString().slice(0, 10);
    Object.assign(curve, { n: points.length, from: day(first), to: day(last), at: new Date().toISOString().slice(0, 16) });
    items.getItem('heatpump_heating_curve').postUpdate(JSON.stringify(curve));
  }
}
"""
RULE = {
    "uid": "heatpump_heating_curve",
    "name": "Wärmepumpe Heizkurve",
    "description": "Lernt jeden Tag um 03:00 die Heizkurve aus dem letzten Jahr: Vorlauf-Sollwert gegen die "
                   "gemittelte Außentemperatur (espaltherma_ext_ambient_temp_avg), nur Viertelstunden mit Heizwärme "
                   "über 300 W ohne Warmwasser, Offset und Smart-Grid-Eingriff; schreibt sie als JSON nach "
                   "heatpump_heating_curve "
                   "für die Kachel der Wärmepumpen-Seite. Ohne einen Tag Heizbetrieb im Jahr bleibt die Kurve, wie sie war.",
    "tags": [],
    "triggers": [{"id": "1", "type": "timer.GenericCronTrigger", "configuration": {"cronExpression": "0 0 3 * * ? *"}}],
    "conditions": [],
    "actions": [{"id": "2", "type": "script.ScriptAction",
                 "configuration": {"type": "application/javascript", "script": SCRIPT}}],
}


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


print(f"item {ITEM}:", "exists" if call("GET", f"/items/{ITEM}") == 200 else "missing")
print("rule heatpump_heating_curve:", "exists" if call("GET", "/rules/heatpump_heating_curve") == 200 else "missing")
if sys.argv[1] == "apply":
    print(ITEM, "PUT", call("PUT", f"/items/{ITEM}", ITEM_DTO))
    exists = call("GET", "/rules/heatpump_heating_curve") == 200
    print("rule", "PUT " + str(call("PUT", "/rules/heatpump_heating_curve", RULE)) if exists else
          "POST " + str(call("POST", "/rules", RULE)))
    print("run now:", call("POST", "/rules/heatpump_heating_curve/runnow", {}))
