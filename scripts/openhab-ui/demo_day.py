#!/usr/bin/env python3
"""Every item's state at a past moment, read from InfluxDB persistence, as the states a screenshot browser sets in
MainUI's store (pinia setItemState) or ui_proxy.py serves, plus the tile_history JSON as the rule would have written it
then and the price extrema as their rule would have set them; for screenshots of a past day, its charts loaded with
the browser's clock set back to it. Usage: demo_day.py ISO_TIME OUT.json   (on homepi, ISO_TIME with its offset, e.g.
2026-10-06T23:59:00+02:00; reads the REST API with the token in ~/.openhab_token, never printed)"""
import bisect
import datetime
import json
import re
import sys
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8080/rest"
T = datetime.datetime.fromisoformat(sys.argv[1])  # with offset
OUT = sys.argv[2]
FMT = "%Y-%m-%dT%H:%M:%S.000%z"
DAYS = ["So.", "Mo.", "Di.", "Mi.", "Do.", "Fr.", "Sa."]  # Java's German short weekdays


TOKEN = open(__import__("os").path.expanduser("~/.openhab_token")).read().strip()


def get(path):
    req = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + TOKEN})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def iso(t):
    s = t.strftime(FMT)
    return s[:-2] + ":" + s[-2:]


def points(item, start, end):
    q = urllib.parse.urlencode({"serviceId": "influxdb", "starttime": iso(start), "endtime": iso(end)})
    d = get(f"/persistence/items/{item}?{q}")
    out = []
    for p in d.get("data", []):
        out.append((p["time"] / 1000, p["state"]))
    return sorted(out)


def at(item, t, windows=(6, 72, 24 * 30)):
    """The persisted state at time t: the last point at or before it."""
    for hours in windows:
        pts = points(item, t - datetime.timedelta(hours=hours), t)
        if pts:
            return pts[-1][1]
    return None


def fnum(state):
    try:
        return float(str(state).split()[0])
    except (ValueError, IndexError):
        return None


def fmt_number(value, digits):
    return f"{value:.{digits}f}".replace(".", ",")


# a pattern with a unit of its own shows the state converted into it, as openHAB does (water in l, its state in m³)
CONVERT = {("m³", "l"): 1000, ("m³/min", "l/min"): 1000, ("W", "kW"): 0.001, ("kW", "W"): 1000, ("Wh", "kWh"): 0.001,
           ("kWh", "Wh"): 1000}


def display(state, pattern, unit, options, type_):
    """MainUI's displayState as openHAB would format it in German: the pattern's number with a decimal comma and
    the unit, an option's label, a date in the patterns this installation uses."""
    if options:  # an option's label; a number's option by its integer too ("2.0" persisted, option "2")
        v = fnum(state)
        for key in (state, None if v is None or v != int(v) else str(int(v))):
            if key in options:
                return options[key]
    m = re.match(r"JS\(\|\(parseFloat\(input\)\*100\)\.toFixed\((\d)\)\.replace\('\.', ','\) \+ '([^']*)'\)", pattern or "")
    if m and fnum(state) is not None:  # the prices' inline JS: EUR/kWh as ct/kWh
        return fmt_number(fnum(state) * 100, int(m.group(1))) + m.group(2)
    if not pattern or pattern.startswith("JS("):
        return None
    if type_ == "DateTime":
        try:
            d = datetime.datetime.fromisoformat(state.replace("Z", "+00:00"))
        except ValueError:
            return None
        wd = DAYS[int(d.strftime("%w"))]
        return (pattern.replace("%1$ta", wd).replace("%1$tF", d.strftime("%Y-%m-%d")).replace("%1$tR", d.strftime("%H:%M"))
                .replace("%1$tY", d.strftime("%Y")).replace("%1$tm", d.strftime("%m")).replace("%1$td", d.strftime("%d"))
                .replace("%1$tH", d.strftime("%H")).replace("%1$tM", d.strftime("%M")).replace("%1$tS", d.strftime("%S")))
    v = fnum(state)
    shown_unit = re.sub(r"^%[-+ 0#]*[\d.]*[dfs]\s*", "", pattern).strip()
    if v is not None and unit and shown_unit and (unit, shown_unit) in CONVERT:
        v *= CONVERT[(unit, shown_unit)]
    m = re.match(r"%\.(\d+)f", pattern)
    if m and v is not None:
        text = re.sub(r"%\.\d+f", fmt_number(v, int(m.group(1))), pattern, count=1)
    elif "%d" in pattern and v is not None:
        text = pattern.replace("%d", str(int(round(v))))
    elif "%s" in pattern:
        text = pattern.replace("%s", str(state).split()[0] if unit else str(state))
    else:
        return None
    return text.replace("%unit%", unit or "").replace("%%", "%").strip()


items = get("/items?fields=name,type,state,stateDescription,groupNames")
demo = {}
persisted = 0
for it in items:
    name, type_ = it["name"], it["type"]
    groups = it.get("groupNames", [])
    if type_ == "Group" or not any(g.startswith("influxdb") for g in groups):
        continue
    state = at(name, T)
    if state is None:
        continue
    persisted += 1
    sd = it.get("stateDescription") or {}
    options = {o["value"]: o["label"] for o in sd.get("options", [])}
    current = it.get("state", "")
    unit = None
    if type_.startswith("Number:"):
        parts = str(state).split()
        unit = parts[1] if len(parts) > 1 else (current.split()[1] if len(current.split()) > 1 else "")
        v = fnum(state)
        s = {"state": f"{v} {unit}".strip(), "numericState": v, "unit": unit, "type": "Quantity"}
    elif type_ in ("Number", "Dimmer"):
        v = fnum(state)
        s = {"state": str(int(v)) if v is not None and v == int(v) else str(v), "numericState": v, "type": "Decimal"}
    elif type_ in ("Switch", "Contact"):
        s = {"state": state, "type": "OnOff" if type_ == "Switch" else "OpenClosed"}
    else:
        s = {"state": state, "type": "String"}
    shown = display(s["state"], sd.get("pattern"), unit, options, type_)
    if shown is not None:
        s["displayState"] = shown
    demo[name] = s

# the price extrema as the rule epex_spot_awattar_extrema would have set them at T: over the market price's slots
# from the current one to two days ahead (these items are not persisted)
byname = {it["name"]: it for it in items}
slots = points("epex_spot_awattar", T - datetime.timedelta(hours=2), T + datetime.timedelta(days=2))
slots = [(t, fnum(v)) for t, v in slots if fnum(v) is not None]
current = [k for k, (t, _) in enumerate(slots) if t <= T.timestamp()]
slots = slots[current[-1]:] if current else []
if slots:
    for word, pick in (("cheapest", min), ("priciest", max)):
        t, v = pick(slots, key=lambda x: x[1])
        it = byname[f"epex_spot_awattar_{word}"]
        s = {"state": f"{v} EUR/kWh", "numericState": v, "unit": "EUR/kWh", "type": "Quantity"}
        s["displayState"] = display(s["state"], (it.get("stateDescription") or {}).get("pattern"), "EUR/kWh", {}, it["type"])
        demo[it["name"]] = s
        it = byname[f"epex_spot_awattar_{word}_hour"]
        when = datetime.datetime.fromtimestamp(t, T.tzinfo).strftime("%Y-%m-%dT%H:%M:%S.000%z")
        s = {"state": when, "type": "DateTime"}
        s["displayState"] = display(when, (it.get("stateDescription") or {}).get("pattern"), None, {}, "DateTime")
        demo[it["name"]] = s
    print("extrema:", {k: demo[k]["displayState"] for k in demo if k.startswith("epex_spot_awattar_") and
                       ("cheapest" in k or "priciest" in k)})

# timestamps that are not persisted: those saying how recent something is (last seen, last reading) keep their age,
# moved back to T; the inverter's start that day from its persisted input power (the sun arc needs it)
now = datetime.datetime.now(T.tzinfo)
for it in items:
    if it["type"] != "DateTime" or it["name"] in demo or it["name"].startswith("epex_spot_awattar_"):
        continue
    try:
        live = datetime.datetime.fromisoformat(it["state"])
    except ValueError:
        continue
    if datetime.timedelta(0) <= now - live <= datetime.timedelta(hours=6):
        when = (T - (now - live)).strftime("%Y-%m-%dT%H:%M:%S.000%z")
        demo[it["name"]] = {"state": when, "type": "DateTime"}
day0 = T.replace(hour=0, minute=0, second=0, microsecond=0)
pv = [(t, fnum(v)) for t, v in points("huawei_inverter_input_power", day0, T)]
start = next((t for t, v in pv if v is not None and v > 0.01), None)
if start is not None and "huawei_inverter_startup_time" in byname:
    demo["huawei_inverter_startup_time"] = {
        "state": datetime.datetime.fromtimestamp(start, T.tzinfo).strftime("%Y-%m-%dT%H:%M:%S.000%z"), "type": "DateTime"}
for name in [n for n, it in byname.items() if it["type"] == "DateTime" and n in demo and "displayState" not in demo[n]]:
    sd = byname[name].get("stateDescription") or {}
    shown = display(demo[name]["state"], sd.get("pattern"), None, {}, "DateTime")
    if shown is not None:
        demo[name]["displayState"] = shown

# tile_history as the rule would have written it at T
rule = get("/rules/tile_history")
script = rule["actions"][0]["configuration"]["script"]
track = json.loads(re.search(r"const TRACK = (\{.*?\});", script, re.S).group(1))
hour0 = T.replace(minute=0, second=0, microsecond=0)
hist = {}
for name, want in track.items():
    r = {}
    if want.get("c"):
        r["y"] = fnum(at(name, T - datetime.timedelta(days=1)))
        xs = [fnum(at(name, T - datetime.timedelta(days=k))) for k in range(1, 8)]
        xs = [x for x in xs if x is not None]
        r["a"] = round(sum(xs) / len(xs), 3) if xs else None
        r["d"] = fnum(at(name, T.replace(hour=0, minute=0, second=0, microsecond=0) - datetime.timedelta(seconds=1)))
    if want.get("t"):
        r["h"] = fnum(at(name, T - datetime.timedelta(hours=want["t"])))
    if want.get("s"):
        pts = [(t, fnum(v)) for t, v in points(name, hour0 - datetime.timedelta(hours=24), T)]
        pts = [(t, v) for t, v in pts if v is not None]
        before = fnum(at(name, hour0 - datetime.timedelta(hours=23)))
        s = []
        for i in range(23, -1, -1):
            b = (hour0 - datetime.timedelta(hours=i)).timestamp()
            e = min(b + 3600, T.timestamp())
            # time-weighted mean: each point holds until the next
            ts = [t for t, _ in pts]
            j = bisect.bisect_right(ts, b) - 1
            cur = pts[j][1] if j >= 0 else before
            acc, last = 0.0, b
            k = j + 1
            total = 0.0
            while k < len(pts) and pts[k][0] < e:
                if cur is not None:
                    acc += cur * (pts[k][0] - last)
                    total += pts[k][0] - last
                last, cur = pts[k][0], pts[k][1]
                k += 1
            if cur is not None:
                acc += cur * (e - last)
                total += e - last
            s.append(round(acc / total, 3) if total > 0 else None)
        r["s"] = s
    if want.get("f"):
        lo, hi = want["f"]
        pts = points(name, hour0 - datetime.timedelta(hours=lo), hour0 + datetime.timedelta(hours=hi))
        r["f"] = [[int(t), round(fnum(v), 4)] for t, v in pts if fnum(v) is not None]
    hist[name] = r
demo["tile_history"] = {"state": json.dumps(hist, separators=(",", ":")), "type": "String"}
json.dump({"time_ms": int(T.timestamp() * 1000), "states": demo}, open(OUT, "w"), ensure_ascii=False)
print(f"{persisted} items at {T.isoformat()}, history for {len(hist)} items -> {OUT}")
