#!/usr/bin/env python3
"""Temporary proposals (user, 2026-10-06): every device page once more as page proposals_<uid>, its value tiles
replaced by the form that fits each value best, picked from the variants of the value-tile canvas
(a private design canvas). The user rejected 01 (semicircle), 09 (dials), 10 (one
temperature scale) and the COP energy label; liked the ratings in words (12) and the comparison with yesterday (15);
no preference for the rest; combinations allowed. A page proposals lists them all.

The page builders of dashboard.py run unchanged; only wide_grid(), phase_table() and plug_cards() are swapped, so
each proposal page is its device page with new value grids. The plug cards come as two temporary widgets,
proposals-plug-card and proposals-plug-electric-card (tagged generated, the generator's next run removes them).

Comparisons, courses and the price strip need history no item holds: the temporary rule proposals_history writes
it every 10 minutes as JSON into the String item proposals_history (yesterday at this time, the mean of the last
7 days at this time, the value some hours ago, 24 hourly means, the hourly prices ahead).

Usage (on homepi, as pi):
  proposals_values.py build OUTDIR          OUTDIR/body.json (pages and widgets, for ui_put.py), OUTDIR/remove.json
  proposals_values.py history check|apply   the item and the rule (API token from ~/.openhab_token, never printed)
  proposals_values.py history remove        deletes rule and item again
"""
import copy
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(os.path.dirname(HERE), "dashboard.py")
MODE = sys.argv[1:]
sys.argv = [GEN, "check"]  # the generator's module code reads its mode; its main() is not run
ns = {"__file__": GEN, "__name__": "dashboard"}
exec(compile(open(GEN).read().replace("\nmain()\n", "\n"), GEN, "exec"), ns)
g = type("g", (), ns)

HIST_ITEM = "proposals_history"
RULE_UID = "proposals_history"
REST = "http://127.0.0.1:8080/rest"
TRACK = {}  # item: what the history rule keeps of it


def track(item, **want):
    if item.startswith("zzpfx"):
        for prefix in PLUG_PREFIXES:
            track(prefix + item[5:], **want)
        return
    TRACK.setdefault(item, {}).update(want)


PLUG_PREFIXES = set()

# ---------------------------------------------------------------- expression helpers

num, fixed, disp, label, div, svg, comp = g.num, g.fixed, g.disp, g.label, g.div, g.svg, g.comp
DARK = "(themeOptions.dark === 'dark')"
HS = f"items.{HIST_ITEM}.state"
H = f"((({HS}) || '').charAt(0) === '{{' ? JSON.parse({HS}) : {{}})"


def hv(item, key):
    """A value of the history JSON, undefined where it has none."""
    return f"((({H})['{item}'] || {{}}).{key})"


def has(expr):
    return f"({expr} !== undefined && {expr} !== null)"


def js(text):
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


# text colours for a class, (dark theme, light theme), at least 4.5:1 on the tile and on their own tint
CLS = {"good": ("#81c784", "#2e7d32"), "ok": ("#c5e1a5", "#558b2f"), "caution": ("#fff176", "#8d6e00"), "warn": ("#ffb74d", "#e65100"),
       "bad": ("#ef9a9a", "#c62828"), "info": ("#81d4fa", "#0277bd"), "neutral": ("#c7c7cc", "#5f6368")}
CLS_TABLE = "({" + ", ".join(f"{k}: [{js(v[1])}, {js(v[0])}]" for k, v in CLS.items()) + "})"


def cls_color(cls_expr):
    return f"(({CLS_TABLE})[{cls_expr}] || ({CLS_TABLE}).neutral)[{DARK} ? 1 : 0]"



TILE = {"position": "relative", "box-sizing": "border-box", "min-width": "0", "border-radius": "12px",
        "padding": "10px 12px", "background": "rgba(127, 127, 127, 0.08)", "overflow": "hidden"}
TITLE = {"font-size": "12px", "opacity": "0.65", "white-space": "nowrap", "overflow": "hidden",
         "text-overflow": "ellipsis"}
VALUE = {"font-size": "20px", "font-weight": "700", "line-height": "1.3", "white-space": "nowrap"}
SUB = {"font-size": "11px", "opacity": "0.65"}
WIDE = {"grid-column": "1 / -1"}


def chip(text, cls_expr="'neutral'", visible=None):
    color = cls_color(cls_expr)
    return label(text, visible, **{"font-size": "11px", "font-weight": "600", "padding": "2px 8px",
                                   "border-radius": "9px", "white-space": "nowrap", "width": "fit-content", "color": "=" + color,
                                   "background": f"='color-mix(in srgb, ' + {color} + ' 16%, transparent)'"})


def head(title, right=None):
    kids = [label(title, **{**TITLE, "flex": "1 1 auto"})]
    if right is not None:
        kids += right if isinstance(right, list) else [right]
    return div(kids, **{"display": "flex", "align-items": "center", "gap": "8px"})


def tile(children, item=None, title="", color=None, wide=False, visible=None, **style):
    kids = list(children)
    if item:
        kids.append(g.link_over(item, title=title, color=color))
    return div(kids, visible, **{**TILE, **(WIDE if wide else {}), **style})


def value(expr, color=None, right=None, **style):
    """A tile's value large; with right a chip beside it at the row's end."""
    lbl = label(expr, **{**VALUE, **({"color": color} if color else {}), **style})
    if right is None:
        return lbl
    # where both do not fit beside each other, the chip goes below the value
    return div([lbl, *(right if isinstance(right, list) else [right])],
               **{"display": "flex", "flex-wrap": "wrap", "align-items": "center", "justify-content": "space-between",
                  "gap": "2px 8px"})


def clamp(expr, lo=0, hi=100):
    return f"Math.max({lo}, Math.min({hi}, {expr}))"


def pct(expr, lo, hi):
    """Where a value lies between lo and hi, in per cent, clamped."""
    return clamp(f"(({expr}) - ({lo})) / (({hi}) - ({lo})) * 100")


def signed(expr, digits, unit):
    return (f"(({expr}) >= 0 ? '+' : '−') + {fixed(f'Math.abs({expr})', digits)} + ' {unit}'")


def bar(width_expr, color, height=8, opacity=None, visible=None, **style):
    st = {"position": "absolute", "left": "0", "top": "0", "height": f"{height}px", "border-radius": f"{height // 2}px",
          "background": color, "width": f"={width_expr} + '%'", **style}
    if opacity:
        st["opacity"] = opacity
    return div([], visible, **st)


def track_bar(children, height=8, **style):
    return div([div([], **{"position": "absolute", "inset": "0", "border-radius": f"{height // 2}px",
                           "background": "rgba(127, 127, 127, 0.18)"}), *children],
               **{"position": "relative", "height": f"{height}px", **style})


def legend_dot(color):
    return div([], **{"width": "9px", "height": "9px", "border-radius": "50%", "background": color, "flex": "0 0 auto"})


# ---------------------------------------------------------------- 15 · comparison with yesterday and the last 7 days


def compare(title, item, color, better=None, digits=2, unit="kWh", factor=1, value_expr=None, extra=(), tap=True):
    """Today's value over yesterday's at this time and the mean of the last 7 days at this time, as three bars, the
    difference to yesterday as a chip, green or orange where more (or less) is better."""
    track(item, c=True)
    v = f"({num(item)} * {factor})"
    y, a = f"(Number({hv(item, 'y')}) * {factor})", f"(Number({hv(item, 'a')}) * {factor})"
    top = f"(Math.max({v}, {has(hv(item, 'y'))} ? {y} : 0, {has(hv(item, 'a'))} ? {a} : 0) * 1.08 || 1)"
    d = f"(({v} - {y}) / {y} * 100)"
    cls = ("'neutral'" if better is None else
           f"(Math.abs({d}) < 3 ? 'neutral' : ({d} > 0) === {'true' if better == 'more' else 'false'} ? 'good' : 'warn')")
    diff = chip(f"={d} >= 300 ? '×' + {fixed(f'{v} / {y}', 0)} + ' zu gestern' : (Math.abs({d}) < 0.5 ? '±0' : "
                f"({d} > 0 ? '+' : '−') + Math.round(Math.abs({d}))) + ' % zu gestern'",
                cls, visible=f"={has(hv(item, 'y'))} && {y} > 0")
    rows = []
    for name, expr, color_, dashed, known in (("heute", v, color, False, "true"),
                                             ("gestern", y, "rgba(127, 127, 127, 0.55)", False, has(hv(item, 'y'))),
                                             ("Ø 7 Tage", a, None, True, has(hv(item, 'a')))):
        fill = ({"border": "1.5px dashed rgba(127, 127, 127, 0.7)", "box-sizing": "border-box"} if dashed else
                {"background": color_})
        rows += [label(name, **{"font-size": "11px", "opacity": "0.65"}),
                 div([div([], **{"height": "8px", "border-radius": "4px", "width": f"={known} ? {clamp(f'{expr} / {top} * 100')} + '%' : '0%'", **fill})],
                     **{"height": "8px", "border-radius": "4px", "background": "rgba(127, 127, 127, 0.1)"}),
                 label(f"={known} ? {fixed(expr, digits)} : '–'",
                       **{"font-size": "11px", "text-align": "right", "white-space": "nowrap",
                          **({"font-weight": "600"} if name == "heute" else {"opacity": "0.75"})})]
    grid = div(rows, **{"display": "grid", "grid-template-columns": "58px minmax(0, 1fr) auto", "align-items": "center",
                        "gap": "4px 8px", "margin-top": "6px"})
    shown = value_expr or f"={g.dash(disp(item))}"
    return tile([label(title, **TITLE), value(shown, color, diff), grid, *extra], item if tap else None, title, color)


# ---------------------------------------------------------------- 03 · sparkline and trend


def series_points(item, span, factor=1, w=196, x0=2, top=6, bottom=40):
    """The 24 hourly means as 'x y' points of a sparkline (nulls skipped), scaled to at least span."""
    s = f"(({hv(item, 's')}) || [])"
    lo, hi = "f.reduce((a, b) => Math.min(a, b), 1e12)", "f.reduce((a, b) => Math.max(a, b), -1e12)"
    L = f"((lo + hi) / 2 - Math.max({span}, hi - lo) / 2)"
    R = f"Math.max({span}, hi - lo)"
    pts = (f"s.map((v, i) => v === null ? null : ({x0} + {w} * i / Math.max(1, s.length - 1)).toFixed(1) + ' ' + "
           f"({bottom} - {bottom - top} * (v * {factor} - L) / R).toFixed(1)).filter((p) => p !== null)")
    return (f"((s) => ((f) => ((lo, hi) => ((L, R) => {pts})({L}, {R}))({lo}, {hi}))"
            f"(s.filter((v) => v !== null).map((v) => v * {factor})))({s})"), s


def sparkline(item, color, span, factor=1, threshold=None, threshold_label=None):
    """The day's course as a line over its area, its last point marked; a dashed line at a threshold."""
    pts, s = series_points(item, span, factor)
    line_d = f"=((p) => p.length > 1 ? 'M' + p.join(' L') : '')({pts})"
    area_d = (f"=((p) => p.length > 1 ? 'M' + p[0].split(' ')[0] + ' 44 L' + p.join(' L') + ' L' + "
              f"p[p.length - 1].split(' ')[0] + ' 44 Z' : '')({pts})")
    last_x = f"=((p) => p.length ? p[p.length - 1].split(' ')[0] : -10)({pts})"
    last_y = f"=((p) => p.length ? p[p.length - 1].split(' ')[1] : -10)({pts})"
    kids = [svg("path", d=area_d, fill=color, **{"fill-opacity": "0.14"}),
            svg("path", d=line_d, fill="none", stroke=color,
                **{"stroke-width": "1.6", "stroke-linejoin": "round", "stroke-linecap": "round"})]
    if threshold is not None:
        # where the threshold lies on the line's own scale, shown only inside it
        f = f"(({s}).filter((v) => v !== null).map((v) => v * {factor}))"
        lo, hi = f"{f}.reduce((a, b) => Math.min(a, b), 1e12)", f"{f}.reduce((a, b) => Math.max(a, b), -1e12)"
        y = (f"((lo, hi) => ((L, R) => 40 - 34 * ({threshold} - L) / R)((lo + hi) / 2 - Math.max({span}, hi - lo) / 2, "
             f"Math.max({span}, hi - lo)))({lo}, {hi})")
        inside = f"(({y}) >= 4 && ({y}) <= 42)"
        kids = [svg("line", x1=2, x2=198, y1=f"=({y}).toFixed(1)", y2=f"=({y}).toFixed(1)", visible=f"={inside}",
                    stroke="currentColor", **{"stroke-opacity": "0.45", "stroke-width": "0.8", "stroke-dasharray": "3 3"}),
                svg("text", x=3, y=f"=({y} - 2.5).toFixed(1)", content=threshold_label or str(threshold),
                    visible=f"={inside}", fill="currentColor", **{"font-size": "7", "opacity": "0.6"}),
                *kids]
    kids.append(svg("circle", cx=last_x, cy=last_y, r=2.8, fill=color, style={"stroke": "var(--f7-card-bg-color, #fff)"},
                    **{"stroke-width": "1.5"}))
    return svg("svg", kids, viewBox="0 0 200 46", style={"display": "block", "width": "100%", "height": "auto",
                                                        "margin-top": "4px"},
               visible=f"=({s}).length > 1")


def trend_chip(item, digits, unit, hours=1, factor=1, small=None):
    """The change since some hours ago as an arrow and amount."""
    then = f"(Number({hv(item, 'h')}) * {factor})"
    d = f"({num(item)} * {factor} - {then})"
    small = small if small is not None else 0.5 * 10 ** -digits
    text = (f"=(Math.abs({d}) < {small} ? '→ ' : {d} > 0 ? '▲ ' : '▼ ') + {fixed(f'Math.abs({d})', digits)} + "
            f"' {unit} / {hours} h'")
    return chip(text, "'neutral'", visible=f"={has(hv(item, 'h'))}")


def minmax_line(item, digits, factor=1, unit=""):
    s = f"((({hv(item, 's')}) || []).filter((v) => v !== null).map((v) => v * {factor}))"
    lo, hi = f"{s}.reduce((a, b) => Math.min(a, b), 1e12)", f"{s}.reduce((a, b) => Math.max(a, b), -1e12)"
    return label(f"='24 h · min ' + {fixed(lo, digits)} + ' · max ' + {fixed(hi, digits)} + '{unit}'",
                 visible=f"={s}.length > 1", **{**SUB, "margin-top": "2px"})


def spark(title, item, color, unit, digits=1, span=4, factor=1, trend_h=1, threshold=None, threshold_label=None,
          value_expr=None, extra_top=(), wide=False):
    track(item, s=True, t=trend_h)
    return tile([label(title, **TITLE),
                 value(value_expr or f"={g.dash(disp(item))}", None, trend_chip(item, digits, unit, trend_h, factor)),
                 *extra_top,
                 sparkline(item, color, span, factor, threshold, threshold_label),
                 minmax_line(item, digits, factor)], item, title, color, wide)


# ---------------------------------------------------------------- 12 · rating in words


def rating_parts(expr, lo, hi, segs, digits=None):
    """A segment band with the value's place marked and the segment's word: segs = [(upper, word, cls, colour)], the
    last upper ends the scale (hi). Under the band the bounds between the segments. Returns (chip, band)."""
    idx = " : ".join(f"({expr}) < {u} ? {i}" for i, (u, *_ ) in enumerate(segs[:-1])) + f" : {len(segs) - 1}"
    idx = f"({idx})"
    words = "[" + ", ".join(js(w) for _, w, _, _ in segs) + "]"
    classes = "[" + ", ".join(js(c) for _, _, c, _ in segs) + "]"
    word = chip(f"={words}[{idx}]", f"{classes}[{idx}]")
    bounds = [lo] + [u for u, *_ in segs[:-1]] + [hi]
    parts = []
    for i, (_, w, _, colour) in enumerate(segs):
        share = round((bounds[i + 1] - bounds[i]) / (hi - lo) * 100, 2)
        parts.append(div([], **{"flex": f"{share} 1 0", "height": "8px", "border-radius": "4px", "background": colour,
                                "opacity": f"={idx} === {i} ? 1 : 0.28"}))
    fmt = lambda x: (f"{x:.{digits}f}" if digits is not None else f"{x:g}").replace(".", ",")
    ticks = [label(fmt(u), **{"position": "absolute", "top": "0", "transform": "translateX(-50%)",
                              "left": f"{(u - lo) / (hi - lo) * 100:.2f}%"}) for u, *_ in segs[:-1]]
    marker = svg("svg", [svg("path", d="M0 0 H10 L5 6 Z", fill="currentColor")], viewBox="0 0 10 6",
                 style={"position": "absolute", "top": "0", "width": "10px", "height": "6px",
                        "left": f"='calc(' + {pct(expr, lo, hi)} + '% - 5px)'"})
    band = div([div([marker, div(parts, **{"position": "absolute", "left": "0", "right": "0", "top": "8px",
                                          "display": "flex", "gap": "3px"})],
                    **{"position": "relative", "height": "16px", "margin-top": "6px"}),
                div(ticks, **{"position": "relative", "height": "13px", "margin-top": "3px", **SUB})])
    return word, band


GOOD, OK_, WARN, BAD, INFO = "#66bb6a", "#aed581", "#ffa726", "#ef5350", "#42a5f5"
SCALES = {
    # Umweltbundesamt: below 1000 ppm harmless, up to 2000 conspicuous, above unacceptable
    "co2": (400, 2400, [(1000, "unbedenklich", "good", GOOD), (2000, "auffällig", "warn", WARN),
                        (2400, "zu hoch", "bad", BAD)]),
    "humidity": (20, 80, [(30, "zu trocken", "warn", WARN), (40, "trocken", "caution", "#fdd835"),
                          (60, "behaglich", "good", GOOD), (70, "feucht", "info", "#4fc3f7"),
                          (80, "zu feucht", "bad", INFO)]),
    # outdoor air: dry, usual, damp, near saturation (fog, dew)
    "humidity_out": (20, 100, [(40, "trocken", "caution", "#fdd835"), (70, "normal", "good", GOOD),
                               (90, "feucht", "info", "#4fc3f7"), (100, "gesättigt", "info", INFO)]),
    # the classic barometer's words on the pressure reduced to sea level
    "air_pressure": (960, 1050, [(980, "Sturm", "bad", BAD), (1000, "Regen", "info", INFO),
                                 (1020, "veränderlich", "caution", "#fdd835"), (1035, "schön", "good", GOOD),
                                 (1050, "beständig", "good", "#43a047")]),
    "noise": (30, 75, [(45, "ruhig", "good", GOOD), (60, "normal", "caution", "#fdd835"), (75, "laut", "warn", WARN)]),
    "heat_index": (10, 45, [(27, "unbedenklich", "good", GOOD), (32, "Vorsicht", "caution", "#fdd835"),
                            (41, "erhöhte Vorsicht", "warn", WARN), (45, "Gefahr", "bad", BAD)]),
    "pressure": (0, 3, [(1, "zu niedrig", "bad", BAD), (2.5, "normal", "good", GOOD), (3, "zu hoch", "bad", BAD)]),
    "power_factor": (0, 1, [(0.7, "gering", "warn", WARN), (0.9, "mäßig", "caution", "#fdd835"),
                            (1, "gut", "good", GOOD)]),
    "battery_temp": (0, 50, [(10, "kalt", "info", INFO), (30, "ideal", "good", GOOD), (40, "warm", "caution", "#fdd835"),
                             (50, "heiß", "bad", BAD)]),
    "price": (0.1, 0.5, [(0.2, "günstig", "good", "#43a047"), (0.3, "mittel", "warn", "#fb8c00"),
                         (0.5, "teuer", "bad", "#e53935")]),
}


def rating(title, item, scale, expr=None, value_expr=None, color=None, spark_of=None, extra=()):
    """The value with its word and a segment band; with spark_of=(colour, span, unit, digits, threshold) its day's
    course below as well (12 + 03), the change of the last hour beside the value."""
    lo, hi, segs = SCALES[scale]
    word, band = rating_parts(expr or num(item), lo, hi, segs)
    shown = value_expr or f"={g.dash(disp(item))}"
    if not spark_of:
        return tile([head(title, word), value(shown, color), band, *extra], item, title, color)
    colour, span, unit, digits, threshold, *rest = spark_of
    hours = rest[0] if rest else 1
    track(item, s=True, t=hours)
    return tile([head(title, word), value(shown, color, trend_chip(item, digits, unit, hours)), band, *extra,
                 sparkline(item, colour, span, threshold=threshold), minmax_line(item, digits)], item, title, color)


# ---------------------------------------------------------------- 02 · setpoint bar and normal band


def setpoint(title, item, set_expr, set_text, lo, hi, color, tol=1, unit="K", digits=1, value_expr=None, valid=None):
    """The actual value as a bar, the setpoint as a tick, the difference beside; past the setpoint the bar pales.
    valid: when the setpoint counts (else the bar alone, 'kein Soll')."""
    v, s_ = num(item), set_expr
    ok = valid or "true"
    d = f"({v} - {s_})"
    cls = f"(Math.abs({d}) <= {tol} ? 'good' : 'warn')"
    bars = track_bar([bar(pct(v, lo, hi), color, opacity=f"={ok} ? 0.45 : 1"),
                      bar(f"Math.min({pct(v, lo, hi)}, {pct(s_, lo, hi)})", color, visible=f"={ok}"),
                      div([], visible=f"={ok}", **{"position": "absolute", "top": "-6px", "height": "20px",
                                                     "width": "2px", "margin-left": "-1px", "border-radius": "1px",
                                                     "background": "currentColor", "left": f"={pct(s_, lo, hi)} + '%'"})],
                     **{"margin": "14px 0 4px"})
    scale = div([label(str(lo).replace(".", ",")), label(f"={ok} ? 'Soll ' + {set_text} : 'kein Soll'"),
                 label(str(hi).replace(".", ","))],
                **{"display": "flex", "justify-content": "space-between", **SUB, "margin-top": "6px"})
    delta = label(f"={signed(d, digits, unit)}", visible=f"={ok}",
                  **{"font-size": "14px", "font-weight": "700", "color": "=" + cls_color(cls), "white-space": "nowrap"})
    return tile([label(title, **TITLE), value(value_expr or f"={g.dash(disp(item))}", None, delta), bars, scale],
                item, title, color)


def band_bar(title, item, lo, hi, ok_lo, ok_hi, color, nominal=None, ok_text="im Bereich", value_expr=None):
    """The value on a scale with its normal range shaded; the word says whether it lies inside."""
    v = num(item)
    inside = f"({v} >= {ok_lo} && {v} <= {ok_hi})"
    word = chip(f"={inside} ? '{ok_text}' : 'außerhalb'", f"{inside} ? 'good' : 'bad'")
    kids = [div([], **{"position": "absolute", "top": "-5px", "height": "18px", "border-radius": "5px",
                       "background": "rgba(102, 187, 106, 0.28)", "left": f"{(ok_lo - lo) / (hi - lo) * 100:.2f}%",
                       "width": f"{(ok_hi - ok_lo) / (hi - lo) * 100:.2f}%"})]
    if nominal is not None:
        kids.append(div([], **{"position": "absolute", "top": "-5px", "height": "18px", "width": "1px",
                               "background": "currentColor", "opacity": "0.5",
                               "left": f"{(nominal - lo) / (hi - lo) * 100:.2f}%"}))
    kids.append(div([], **{"position": "absolute", "top": "-3px", "width": "14px", "height": "14px",
                           "margin-left": "-7px", "border-radius": "50%", "box-sizing": "border-box",
                           "background": color, "border": "2px solid var(--f7-card-bg-color, #fff)",
                           "left": f"={pct(v, lo, hi)} + '%'"}))
    fmt = lambda x: f"{x:g}".replace(".", ",")
    scale = div([label(fmt(lo)), label(f"{fmt(ok_lo)}–{fmt(ok_hi)}"), label(fmt(hi))],
                **{"display": "flex", "justify-content": "space-between", **SUB, "margin-top": "8px"})
    return tile([head(title, word), value(value_expr or f"={g.dash(disp(item))}"),
                 track_bar(kids, **{"margin": "10px 0 0"}), scale], item, title, color)


def socket_load(title, item, limit=16):
    """A plug's current against what the socket carries."""
    v = num(item)
    p = clamp(f"{v} / {limit} * 100")
    cls = f"({p} < 60 ? 'good' : {p} < 85 ? 'warn' : 'bad')"
    return tile([head(title, chip(f"={fixed(p, 0)} + ' % von {limit} A'", cls)), value(f"={g.dash(disp(item))}"),
                 track_bar([bar(p, "=" + cls_color(cls))], **{"margin": "10px 0 2px"})], item, title)


# ---------------------------------------------------------------- 04 · rings


def ring_svg(pct_expr, color, size=46, width=7):
    return svg("svg", [svg("circle", cx=32, cy=32, r=26, fill="none", stroke="rgba(127, 127, 127, 0.22)",
                           **{"stroke-width": width}),
                       svg("circle", cx=32, cy=32, r=26, fill="none", stroke=color, pathLength=100,
                           transform="rotate(-90 32 32)",
                           **{"stroke-width": width, "stroke-linecap": "round",
                              "stroke-dasharray": f"=({clamp(pct_expr)}).toFixed(1) + ' 100'"})],
               viewBox="0 0 64 64", style={"width": f"{size}px", "height": f"{size}px", "flex": "0 0 auto"})


def ring(title, item, color, pct_expr=None, value_expr=None, sub=None):
    p = pct_expr or num(item)
    texts = [label(title, **TITLE), value(value_expr or f"={g.dash(disp(item))}")]
    if sub:
        texts.append(label(sub, **SUB))
    return tile([div([ring_svg(p, color), div(texts, **{"min-width": "0"})],
                     **{"display": "flex", "align-items": "center", "gap": "12px"})], item, title, color)


# ---------------------------------------------------------------- 05 · donut, 06 · 100 % bar and balance


def donut(title, item, parts, total_expr, center_expr, unit, color=None, footer=None):
    """Parts of a whole as a donut with the whole in its middle, each part with value and share beside it:
    parts = [(name, expr, colour)]."""
    rings, rows, before = [], [], "0"
    total = f"(Math.max({total_expr}, 0.0001))"
    for name, expr, colour in parts:
        share = clamp(f"({expr}) / {total} * 100")
        rings.append(svg("circle", cx=50, cy=50, r=35.5, fill="none", stroke=colour, pathLength=100,
                         transform="rotate(-90 50 50)",
                         **{"stroke-width": 23, "stroke-dasharray": f"=Math.max(0, {share} - 0.6).toFixed(2) + ' 100'",
                            "stroke-dashoffset": f"=(-({before})).toFixed(2)"}))
        before = f"{before} + {share}"
        rows.append(div([legend_dot(colour), label(name, **{"flex": "1 1 auto"}),
                         label(f"={fixed(expr, 2)}", **{"font-weight": "700"}),
                         label(f"=Math.round({share}) + ' %'", **{"width": "36px", "text-align": "right",
                                                                   "opacity": "0.65"})],
                        **{"display": "flex", "align-items": "center", "gap": "7px", "font-size": "12px"}))
    if footer:
        rows.append(footer)
    pie = svg("svg", [svg("circle", cx=50, cy=50, r=35.5, fill="none", stroke="rgba(127, 127, 127, 0.15)",
                          **{"stroke-width": 23}), *rings,
                      svg("text", x=50, y=52, content=f"={center_expr}", fill="currentColor",
                          **{"font-size": "14", "font-weight": "700", "text-anchor": "middle"}),
                      svg("text", x=50, y=63, content=unit, fill="currentColor",
                          **{"font-size": "8", "text-anchor": "middle", "opacity": "0.65"})],
              viewBox="0 0 100 100", style={"width": "112px", "height": "112px", "flex": "0 0 auto"})
    return tile([label(title, **TITLE),
                 div([pie, div(rows, **{"display": "flex", "flex-direction": "column", "gap": "8px", "flex": "1 1 auto",
                                        "min-width": "0", "max-width": "320px"})],
                     **{"display": "flex", "align-items": "center", "gap": "14px", "margin-top": "6px"})],
                item, title, color, wide=True)


def split_bar(parts, total_expr, height=16):
    """Parts of a whole as one bar of segments, each with its share inside where it fits."""
    total = f"(Math.max({total_expr}, 0.0001))"
    segs = []
    for name, expr, colour in parts:
        share = clamp(f"({expr}) / {total} * 100")
        segs.append(div([label(f"={share} >= 14 ? Math.round({share}) + ' %' : ''")],
                        **{"flex": f"=({share}).toFixed(2) + ' 1 0'", "background": colour, "text-align": "center",
                           "font-size": "10px", "font-weight": "700", "color": "#1a1a1a",
                           "line-height": f"{height}px", "overflow": "hidden"}))
    return div(segs, **{"display": "flex", "gap": "2px", "height": f"{height}px", "border-radius": "6px",
                        "overflow": "hidden", "margin-top": "8px", "background": "rgba(127, 127, 127, 0.12)"})


def split_legend(parts, digits=2):
    return div([div([legend_dot(c), label(f"='{n} ' + {fixed(e, digits)}")],
                    **{"display": "inline-flex", "align-items": "center", "gap": "5px"}) for n, e, c in parts],
               **{"display": "flex", "flex-wrap": "wrap", "gap": "4px 14px", "font-size": "11px", "opacity": "0.8",
                  "margin-top": "6px"})


def split(title, item, parts, total_expr, value_expr, color=None, right=None):
    return tile([head(title, right), value(value_expr, color), split_bar(parts, total_expr), split_legend(parts)],
                item, title, color)


def balance(title, item, left, right, unit="kWh", digits=2, net_words=("eingespeist", "bezogen"), extra=()):
    """Two opposing amounts around a middle line: left = (name, expr, colour), right likewise; the net below."""
    (ln, le, lc), (rn, re_, rc) = left, right
    top = f"(Math.max(Math.abs({le}), Math.abs({re_}), 0.0001) * 1.1)"
    net = f"({re_} - {le})"
    bars = div([div([], **{"position": "absolute", "left": "0", "right": "0", "top": "9px", "height": "8px",
                           "border-radius": "4px", "background": "rgba(127, 127, 127, 0.12)"}),
                div([], **{"position": "absolute", "right": "50%", "top": "6px", "height": "14px",
                           "border-radius": "7px 0 0 7px", "background": lc,
                           "width": f"=({clamp(f'Math.abs({le}) / {top} * 50', 0, 50)}).toFixed(2) + '%'"}),
                div([], **{"position": "absolute", "left": "50%", "top": "6px", "height": "14px",
                           "border-radius": "0 7px 7px 0", "background": rc,
                           "width": f"=({clamp(f'Math.abs({re_}) / {top} * 50', 0, 50)}).toFixed(2) + '%'"}),
                div([], **{"position": "absolute", "left": "50%", "top": "0", "width": "2px", "height": "26px",
                           "margin-left": "-1px", "background": "currentColor", "opacity": "0.8"})],
               **{"position": "relative", "height": "26px", "margin-top": "4px"})
    ends = div([div([label(ln, **SUB), label(f"={fixed(f'Math.abs({le})', digits)} + ' {unit}'",
                                             **{"font-size": "15px", "font-weight": "700"})]),
                label(title, **{**TITLE, "align-self": "flex-start"}),
                div([label(rn, **{**SUB, "text-align": "right"}),
                     label(f"={fixed(f'Math.abs({re_})', digits)} + ' {unit}'",
                           **{"font-size": "15px", "font-weight": "700", "text-align": "right"})])],
               **{"display": "flex", "justify-content": "space-between", "align-items": "flex-end", "gap": "8px"})
    words = f"({net} >= 0 ? '{net_words[0]}' : '{net_words[1]}')"
    saldo = label(f"='Saldo ' + {fixed(f'Math.abs({net})', digits)} + ' {unit} ' + {words}",
                  **{"text-align": "center", "font-size": "12px", "font-weight": "600", "opacity": "0.8"})
    return tile([ends, bars, saldo, *extra], item, title, wide=True)


# ---------------------------------------------------------------- 07 · pairs


def spread(title, hot, cold, hot_name, cold_name, color_hot="#e57373", color_cold="#64b5f6", sub=None):
    """Two temperatures of one flow, the hot on the left, the cold on the right, a pipe shading from one into the
    other below them, the difference beside the title."""
    d = f"({num(hot)} - {num(cold)})"
    side = lambda name, item, color, align: div([label(name, **SUB),
                                                 value(f"={fixed(num(item), 1)} + ' °C'", color,
                                                       **{"text-align": align})], **{"min-width": "0"})
    pipe = div([label("›  ›  ›", **{"font-size": "13px", "line-height": "10px", "color": "#ffffff", "opacity": "0.85",
                                    "letter-spacing": "18px", "text-align": "center"})],
               **{"height": "10px", "border-radius": "5px", "margin-top": "8px", "overflow": "hidden",
                  "background": f"linear-gradient(90deg, {color_hot}, {color_cold})"})
    kids = [head(title, chip(f"='ΔT ' + {fixed(d, 1)} + ' K'")),
            div([side(hot_name, hot, color_hot, "left"), side(cold_name, cold, color_cold, "right")],
                **{"display": "flex", "justify-content": "space-between", "gap": "8px", "margin-top": "4px"}),
            pipe]
    if sub:
        kids.append(label(sub, **{**SUB, "margin-top": "6px"}))
    return tile(kids, hot, title)


def pair(title, a, b, a_name, b_name, digits=1, unit="K", a_color=None, b_color=None, delta_text=None,
         a_expr=None, b_expr=None, sub=None, value_unit=""):
    """Two values that belong together side by side, their difference as a chip beside the title."""
    av, bv = a_expr or num(a), b_expr or num(b)
    d = f"({av} - {bv})"
    def side(name, item, expr, color, align):
        shown = f"={g.dash(disp(item))}" if item and not expr else f"={fixed(expr, digits)} + '{value_unit}'"
        return div([label(name, **{**SUB, "text-align": align}),
                    value(shown, color, **{"font-size": "18px", "text-align": align})], **{"min-width": "0"})
    right = None if delta_text is False else chip(f"={delta_text or signed(d, digits, unit)}")
    kids = [head(title, right),
            div([side(a_name, a, a_expr, a_color, "left"), side(b_name, b, b_expr, b_color, "right")],
                **{"display": "flex", "align-items": "flex-end", "justify-content": "space-between", "gap": "8px",
                   "margin-top": "4px"})]
    if sub:
        kids.append(label(sub, **{**SUB, "margin-top": "4px"}))
    return tile(kids, a, title)


def inout(title, inside, outside, in_color="#fb8c00", out_color="#29b6f6", in_name="innen", out_name="außen"):
    """Inside and outside side by side in their colours, the difference beside the title."""
    return pair(title, inside, outside, in_name, out_name, digits=1, unit="K", a_color=in_color, b_color=out_color)


def dew(title, dewpoint, temp, temp_name, inside=True):
    """The distance between a temperature and its dew point: both as dots on a 0–30 °C bar, the distance large."""
    d = f"({num(temp)} - {num(dewpoint)})"
    risk = f"({d} > 3)"
    word = chip(f"={risk} ? '{'kein Kondensat' if inside else 'kein Tau'}' : "
                f"'{'Kondensat möglich' if inside else 'Tau oder Nebel möglich'}'", f"{risk} ? 'good' : 'warn'")
    p = lambda e: pct(e, 0, 30)
    dot = lambda e, color: div([], **{"position": "absolute", "top": "-4px", "width": "16px", "height": "16px",
                                     "margin-left": "-8px", "border-radius": "50%", "box-sizing": "border-box",
                                     "background": color, "border": "2px solid var(--f7-card-bg-color, #fff)",
                                     "left": f"={p(e)} + '%'"})
    span_ = div([], **{"position": "absolute", "top": "0", "height": "8px", "background": "rgba(127, 127, 127, 0.45)",
                       "left": f"={p(num(dewpoint))} + '%'", "width": f"=({p(num(temp))} - {p(num(dewpoint))}) + '%'"})
    bar_ = track_bar([span_, dot(num(dewpoint), "#4fc3f7"), dot(num(temp), "#fb8c00")], **{"margin": "12px 6px 6px"})
    ends = div([label(f"='Taupunkt ' + {g.dash(disp(dewpoint))}", **{"color": "#4fc3f7"}),
                label(f"='{temp_name} ' + {g.dash(disp(temp))}", **{"color": "#fb8c00"})],
               **{"display": "flex", "justify-content": "space-between", "gap": "8px", "font-size": "11px"})
    return tile([head(title, word), value(f"={fixed(d, 1)} + ' K'"), bar_, ends], dewpoint, title)


def day_range(title, lo_item, hi_item, now_item, color):
    """Today's lowest and highest value as a bar, the present value as a dot on it."""
    lo, hi, v = num(lo_item), num(hi_item), num(now_item)
    span = f"Math.max(4, {hi} - {lo})"
    a, b = f"({lo} - ({span} - ({hi} - {lo})) / 2)", f"({lo} - ({span} - ({hi} - {lo})) / 2 + {span})"
    p = lambda e: pct(e, a, b)
    bar_ = div([div([], **{"position": "absolute", "top": "0", "height": "10px", "border-radius": "5px",
                           "background": color, "opacity": "0.35", "left": f"={p(lo)} + '%'",
                           "width": f"=({p(hi)} - {p(lo)}) + '%'"}),
                div([], **{"position": "absolute", "top": "-3px", "width": "16px", "height": "16px",
                           "margin-left": "-8px", "border-radius": "50%", "box-sizing": "border-box",
                           "background": color, "border": "2px solid var(--f7-card-bg-color, #fff)",
                           "left": f"={p(v)} + '%'"})],
               **{"position": "relative", "height": "10px", "margin": "12px 4px 6px"})
    ends = div([label(f"='min ' + {g.dash(disp(lo_item))}"), label(f"='jetzt ' + {g.dash(disp(now_item))}"),
                label(f"='max ' + {g.dash(disp(hi_item))}")],
               **{"display": "flex", "justify-content": "space-between", **SUB})
    return tile([label(title, **TITLE), bar_, ends], lo_item, title, color)


def strings(title, items_, names, volts, amps, colors):
    """Strings side by side on one scale, the weaker one's shortfall named."""
    vals = [num(i) for i in items_]
    top = f"(Math.max({', '.join(vals)}, 1) * 1.08)"
    hi, lo = f"Math.max({', '.join(vals)})", f"Math.min({', '.join(vals)})"
    gap = f"(({hi} - {lo}) / Math.max({hi}, 1) * 100)"
    weak = " : ".join(f"{v} === {lo} ? '{n}'" for v, n in zip(vals[:-1], names[:-1])) + f" : '{names[-1]}'"
    word = chip(f"={hi} < 50 ? 'keine Leistung' : ({weak}) + ' ' + Math.round({gap}) + ' % schwächer'",
                f"({hi} < 50 || {gap} < 10) ? 'neutral' : 'warn'")
    rows = []
    for item, name, volt, amp, color in zip(items_, names, volts, amps, colors):
        rows += [label(name, **{"font-size": "12px", "opacity": "0.65"}),
                 track_bar([bar(clamp(f"{num(item)} / {top} * 100"), color, height=14)], height=14),
                 label(f"={g.dash(disp(item))}", **{"font-size": "12px", "font-weight": "700", "text-align": "right",
                                                    "white-space": "nowrap"}),
                 label(""), label(f"={g.dash(disp(volt))} + ' · ' + {g.dash(disp(amp))}",
                                  **{**SUB, "margin-top": "-2px"}), label("")]
    return tile([head(title, word), div(rows, **{"display": "grid", "grid-template-columns": "40px minmax(0, 1fr) auto",
                                                "align-items": "center", "gap": "4px 8px", "margin-top": "8px"})],
                items_[0], title, wide=True)


# ---------------------------------------------------------------- 08 · flow bands


def flow_cop(title, power, heat, cop_expr, unit="kW", factor=0.001, digits=2, footer=None, still="steht",
             hide_idle=False, side=None):
    """Electricity plus ambient heat become heat: band widths by amount, the electricity's share of the heat's
    height, so the widening is the COP."""
    e, h = f"({num(power)} * {factor})", f"({num(heat)} * {factor})"
    hs = f"({clamp(f'{e} / Math.max({h}, {e}, 0.0001) * 92', 6, 92)})"
    f1 = lambda e_: f"({e_}).toFixed(1)"
    strom = (f"='M70 10 C160 10 160 17 250 17 L250 ' + {f1(f'17 + {hs}')} + ' C160 ' + {f1(f'17 + {hs}')} + "
             f"' 160 ' + {f1(f'10 + {hs}')} + ' 70 ' + {f1(f'10 + {hs}')} + ' Z'")
    umwelt = (f"='M70 ' + {f1(f'24 + {hs}')} + ' C160 ' + {f1(f'24 + {hs}')} + ' 160 ' + {f1(f'17 + {hs}')} + "
              f"' 250 ' + {f1(f'17 + {hs}')} + ' L250 109 C160 109 160 116 70 116 Z'")
    amb = f"Math.max(0, {h} - {e})"
    texts = [svg("text", x=56, y=f"={f1(f'10 + {hs} / 2 - 1')}", content="Strom", fill="currentColor",
                 **{"font-size": "10.5", "text-anchor": "end", "opacity": "0.65"}),
             svg("text", x=56, y=f"={f1(f'10 + {hs} / 2 + 12')}", content=f"={fixed(e, digits)}", fill="#ffb74d",
                 **{"font-size": "13", "font-weight": "700", "text-anchor": "end"}),
             svg("text", x=56, y=f"={f1(f'24 + {hs} + (92 - {hs}) / 2 - 3')}", content="Umwelt", fill="currentColor",
                 **{"font-size": "10.5", "text-anchor": "end", "opacity": "0.65"}),
             svg("text", x=56, y=f"={f1(f'24 + {hs} + (92 - {hs}) / 2 + 11')}", content=f"={fixed(amb, digits)}",
                 fill="#4db6ac", **{"font-size": "13", "font-weight": "700", "text-anchor": "end"}),
             g.svg_text(264, 58, "Wärme", 10.5, anchor="start", opacity="0.65"),
             svg("text", x=264, y=72, content=f"={fixed(h, digits)} + ' {unit}'", fill="#ef5350",
                 **{"font-size": "13", "font-weight": "700"})]
    drawing = svg("svg", [svg("path", d=strom, fill="#fb8c00", **{"fill-opacity": "0.45"}),
                          svg("path", d=umwelt, fill="#26a69a", **{"fill-opacity": "0.4"}),
                          svg("rect", x=62, y=10, width=8, height=f"={f1(hs)}", rx=2, fill="#fb8c00"),
                          svg("rect", x=62, y=f"={f1(f'24 + {hs}')}", width=8, height=f"={f1(f'92 - {hs}')}", rx=2,
                              fill="#26a69a"),
                          svg("rect", x=250, y=17, width=8, height=92, rx=2, fill="#e53935"), *texts],
                  viewBox="0 0 340 126", style={"display": "block", "width": "100%", "height": "auto",
                                                "max-width": "460px", "margin-top": "4px"},
                  visible=f"={h} > {e} && {e} > 0")
    idle = label(still, visible=f"=!({h} > {e} && {e} > 0)", **{**SUB, "margin": "18px 0", "text-align": "center"})
    right = label(f"='COP ' + {cop_expr}", **{"font-size": "15px", "font-weight": "700", "white-space": "nowrap"})
    if side is not None:  # the title over the COP large, the parts' COPs beside them at the top right
        top_ = div([div([label(title, **TITLE), value(f"='COP ' + {cop_expr}", **{"font-size": "18px"})],
                        **{"min-width": "0"}), side],
                   **{"display": "flex", "justify-content": "space-between", "align-items": "flex-start", "gap": "8px"})
    else:
        top_ = head(title, right)
    kids = [top_, drawing] + ([] if hide_idle else [idle])
    if footer:
        kids.append(footer)
    return tile(kids, heat, title, "#e53935", wide=True,
                visible=f"={h} > {e} && {e} > 0" if hide_idle else None)


def flow_split(title, item, parts, unit="kWh", digits=2, source_name="", source_color="#e53935"):
    """A whole fanning out into its two parts, band widths by amount: parts = [(name, expr, colour)]."""
    (an, ae, ac), (bn, be, bc) = parts
    total = f"Math.max({ae} + {be}, 0.0001)"
    ha = f"({clamp(f'{ae} / {total} * 90', 4, 86)})"
    f1 = lambda e_: f"({e_}).toFixed(1)"
    band_a = (f"='M70 17 C160 17 160 10 250 10 L250 ' + {f1(f'10 + {ha}')} + ' C160 ' + {f1(f'10 + {ha}')} + "
              f"' 160 ' + {f1(f'17 + {ha}')} + ' 70 ' + {f1(f'17 + {ha}')} + ' Z'")
    band_b = (f"='M70 ' + {f1(f'17 + {ha}')} + ' C160 ' + {f1(f'17 + {ha}')} + ' 160 ' + {f1(f'24 + {ha}')} + "
              f"' 250 ' + {f1(f'24 + {ha}')} + ' L250 114 C160 114 160 107 70 107 Z'")
    pct_ = lambda e_: f"Math.round({e_} / {total} * 100) + ' %'"
    texts = [g.svg_text(56, 58, source_name, 10.5, anchor="end", opacity="0.65"),
             svg("text", x=56, y=72, content=f"={fixed(f'{ae} + {be}', digits)}", fill=source_color,
                 **{"font-size": "13", "font-weight": "700", "text-anchor": "end"}),
             svg("text", x=264, y=f"={f1(f'10 + {ha} / 2 - 1')}", content=f"='{an} · ' + {pct_(ae)}", fill="currentColor",
                 **{"font-size": "10.5", "opacity": "0.65"}),
             svg("text", x=264, y=f"={f1(f'10 + {ha} / 2 + 13')}", content=f"={fixed(ae, digits)} + ' {unit}'",
                 fill=ac, **{"font-size": "13", "font-weight": "700"}),
             svg("text", x=264, y=f"={f1(f'24 + {ha} + (90 - {ha}) / 2 - 1')}", content=f"='{bn} · ' + {pct_(be)}",
                 fill="currentColor", **{"font-size": "10.5", "opacity": "0.65"}),
             svg("text", x=264, y=f"={f1(f'24 + {ha} + (90 - {ha}) / 2 + 13')}",
                 content=f"={fixed(be, digits)} + ' {unit}'", fill=bc, **{"font-size": "13", "font-weight": "700"})]
    drawing = svg("svg", [svg("path", d=band_a, fill=ac, **{"fill-opacity": "0.45"}),
                          svg("path", d=band_b, fill=bc, **{"fill-opacity": "0.45"}),
                          svg("rect", x=62, y=17, width=8, height=90, rx=2, fill=source_color),
                          svg("rect", x=250, y=10, width=8, height=f"={f1(ha)}", rx=2, fill=ac),
                          svg("rect", x=250, y=f"={f1(f'24 + {ha}')}", width=8, height=f"={f1(f'90 - {ha}')}", rx=2,
                              fill=bc), *texts],
                  viewBox="0 0 360 124", style={"display": "block", "width": "100%", "height": "auto",
                                                "max-width": "480px", "margin-top": "4px"},
                  visible=f"={ae} + {be} > 0.01")
    idle = label("noch keine Wärme heute", visible=f"=!({ae} + {be} > 0.01)",
                 **{**SUB, "margin": "18px 0", "text-align": "center"})
    return tile([label(title, **TITLE), drawing, idle], item, title, source_color, wide=True)


# ---------------------------------------------------------------- 11 · pictures


def cells(title, item, color, n=10, sub=None, pct_expr=None):
    """A battery of n cells, as many lit as its charge fills, the last one partly."""
    p = pct_expr or num(item)
    w = 238 / n
    rects = [svg("rect", x=round(8 + i * w, 1), y=8, width=round(w - 4, 1), height=32, rx=3, fill=color,
                 **{"fill-opacity": f"={p} >= {(i + 1) * 100 / n:g} ? 1 : {p} > {i * 100 / n:g} ? 0.55 : 0.15"})
             for i in range(n)]
    drawing = svg("svg", [svg("rect", x=1, y=2, width=250, height=44, rx=8, fill="none", stroke=color,
                              **{"stroke-width": "2"}),
                          svg("rect", x=253, y=16, width=6, height=16, rx=2, fill=color), *rects],
                  viewBox="0 0 262 48", style={"display": "block", "width": "100%", "height": "auto",
                                               "max-width": "300px", "margin-top": "8px"})
    kids = [head(title, value(f"={g.dash(disp(item))}", **{"font-size": "18px"})), drawing]
    if sub:
        kids.append(label(sub, **{**SUB, "margin-top": "6px"}))
    return tile(kids, item, title, color)


def tank_color(expr):
    return f"({expr} > 50 ? '#e57373' : {expr} >= 40 ? '#fb8c00' : {expr} >= 35 ? '#fbc02d' : '#64b5f6')"


def tank(title, item, set_item):
    """The hot water tank in layers, its top in the colour of its temperature (as in the heating card), the
    setpoint beside it."""
    t = num(item)
    gid = "tk-" + item
    top = tank_color(t)
    drawing = svg("svg", [svg("defs", [svg("linearGradient", [
        svg("stop", offset="0", **{"stop-color": f"={top}"}), svg("stop", offset="0.52", **{"stop-color": f"={top}"}),
        svg("stop", offset="0.52", **{"stop-color": "#ffcc80"}), svg("stop", offset="0.76", **{"stop-color": "#ffcc80"}),
        svg("stop", offset="0.76", **{"stop-color": "#bbdefb"}), svg("stop", offset="1", **{"stop-color": "#bbdefb"})],
        id=gid, x1="0", x2="0", y1="0", y2="1")]),
        svg("rect", x=8, y=6, width=54, height=108, rx=16, fill=f"url(#{gid})", stroke="currentColor",
            **{"fill-opacity": "0.85", "stroke-opacity": "0.3", "stroke-width": "1.5"})],
        viewBox="0 0 70 120", style={"width": "44px", "height": "auto", "flex": "0 0 auto"})
    d = f"({t} - {num(set_item)})"
    word = chip(f"={d} >= 0 ? 'über Soll' : 'unter Soll'", f"{d} >= 0 ? 'good' : 'warn'")
    texts = div([label(title, **TITLE), value(f"={g.dash(disp(item))}"),
                 label(f"='Soll ' + {g.dash(disp(set_item))} + ' · ' + {signed(d, 1, 'K')}", **SUB),
                 div([word], **{"margin-top": "6px"})], **{"min-width": "0"})
    return tile([div([drawing, texts], **{"display": "flex", "align-items": "center", "gap": "14px"})], item, title)


def levels(title, item, names, color, sub=None, value_expr=None):
    """A level as rising bars, as many lit as the level: names = [(state, word)] from the lowest."""
    n = len(names)
    idx = " : ".join(f"items.{item}.state === '{s_}' ? {i + 1}" for i, (s_, _) in enumerate(names)) + " : 0"
    idx = f"({idx})"
    word = "[" + ", ".join(["'–'"] + [js(w) for _, w in names]) + f"][{idx}]"
    w, gap = 12, 5
    bars = [svg("rect", x=2 + i * (w + gap), y=round(40 - 10 - 26 * (i + 1) / n, 1), width=w,
                height=round(10 + 26 * (i + 1) / n, 1), rx=3, fill=color,
                **{"fill-opacity": f"={idx} > {i} ? 1 : 0.18"}) for i in range(n)]
    kids = [label(title, **TITLE), value(value_expr or f"={word}", **{"font-size": "17px", "overflow": "hidden",
                                                                       "text-overflow": "ellipsis"})]
    if sub:
        kids.append(label(sub, **SUB))
    vw = 4 + n * (w + gap)
    return tile([div([svg("svg", bars, viewBox=f"0 0 {vw} 42", style={"width": f"{vw}px", "height": "auto",
                                                                       "flex": "0 0 auto"}),
                      div(kids, **{"min-width": "0"})], **{"display": "flex", "align-items": "center", "gap": "12px"})],
                item, title, color)


def tub(x, fill_expr, cid):
    body = "M4 14 H56 V22 C56 31 49 36 40 36 H20 C11 36 4 31 4 22 Z"
    return svg("g", [svg("rect", x=4, y=f"=(36 - 22 * {clamp(fill_expr, 0, 1)}).toFixed(1)", width=52,
                         height=f"=(22 * {clamp(fill_expr, 0, 1)}).toFixed(1)", fill="#42a5f5",
                         **{"fill-opacity": "0.8", "clip-path": f"url(#{cid})"}),
                     svg("path", d=body, fill="none", stroke="#64b5f6", **{"stroke-width": "1.6"}),
                     svg("path", d="M2 14 H58 M12 14 V7 C12 4 15 3 18 4 M14 36 L12 41 M46 36 L48 41", fill="none",
                         stroke="#64b5f6", **{"stroke-width": "1.6", "stroke-linecap": "round"})],
               transform=f"translate({x} 0)")


def tubs(liters_expr, per=150, n=6):
    """Bath tubs of per litres, filled as far as the litres reach (n drawn)."""
    cid = "tub-clip"
    body = "M4 14 H56 V22 C56 31 49 36 40 36 H20 C11 36 4 31 4 22 Z"
    return svg("svg", [svg("defs", [svg("clipPath", [svg("path", d=body)], id=cid)]),
                       *[tub(i * 66, f"({liters_expr} / {per} - {i})", cid) for i in range(n)]],
               viewBox=f"0 0 {n * 66} 44", style={"display": "block", "width": "100%", "height": "auto",
                                                  "max-width": "360px", "margin-top": "8px"})


def counter(title, item, ints, decs, unit, factor=1, sub=None, size=24, wide=False):
    """A meter's reading on rollers, black for the whole, red for the fraction."""
    v = f"({num(item)} * {factor})"
    whole = f"('0000000000' + Math.floor({v})).slice(-{ints})"
    frac = f"({v} - Math.floor({v})).toFixed({decs}).slice(2)"
    w, h = round(size * 1.08), round(size * 1.58)
    def roller(text, red):
        bg = ("linear-gradient(#3a0606, #8e1b1b 28%, #8e1b1b 72%, #3a0606)" if red else
              "linear-gradient(#050505, #2b2b2e 28%, #2b2b2e 72%, #050505)")
        return label(text, **{"width": f"{w}px", "height": f"{h}px", "line-height": f"{h}px", "text-align": "center",
                              "border-radius": "3px", "background": bg, "color": "#ffffff", "font-weight": "700",
                              "font-size": f"{size}px", "font-variant-numeric": "tabular-nums"})
    rollers = [roller(f"={whole}.charAt({k})", False) for k in range(ints)]
    rollers.append(div([], **{"width": "3px"}))
    rollers += [roller(f"={frac}.charAt({k})", True) for k in range(decs)]
    meter = div([div(rollers, **{"display": "inline-flex", "gap": "3px", "padding": "5px", "background": "#0b0b0c",
                                 "border-radius": "8px", "border": "1px solid rgba(127, 127, 127, 0.35)"}),
                 label(unit, **{"font-size": "13px", "opacity": "0.7"})],
                **{"display": "flex", "align-items": "center", "gap": "8px", "margin-top": "8px", "flex-wrap": "wrap"})
    kids = [label(title, **TITLE), meter]
    if sub:
        kids.append(label(sub, **{**SUB, "margin-top": "6px"}))
    # wider than a column of about 200 px: the whole row
    return tile(kids, item, title, wide=wide or (ints + decs) * (w + 3) + 16 > 200)


def counters(title, a, b, a_name, b_name, ints, decs, unit, sub):
    """Two meters side by side, as charged and discharged."""
    def one(item, name):
        c = counter(name, item, ints, decs, unit, size=17)
        c["config"]["style"] = {"min-width": "0"}
        return c
    return tile([label(title, **TITLE), div([one(a, a_name), one(b, b_name)],
                                             **{"display": "flex", "flex-wrap": "wrap", "gap": "6px 18px"}),
                 label(sub, **{**SUB, "margin-top": "6px"})], a, title, wide=True)


def dots(title, online, total, color):
    """Optimizers as dots, lit while online."""
    n = 14
    ds = [svg("circle", cx=8 + i * 16, cy=8, r=5.5, fill=color,
              **{"fill-opacity": f"={num(online)} > {i} ? 1 : 0.16"},
              visible=f"={num(total)} > {i}") for i in range(n)]
    return tile([head(title, value(f"={g.dash(disp(online))} + ' / ' + {g.dash(disp(total))}", **{"font-size": "18px"})),
                 svg("svg", ds, viewBox=f"0 0 {n * 16} 16", style={"display": "block", "width": "100%", "height": "auto",
                                                                  "max-width": "300px", "margin-top": "10px"})],
                online, title, color)


def ok_tile(title, item, ok_expr):
    good = f"({ok_expr})"
    return tile([head(title, chip(f"={good} ? 'kein Fehler' : 'Fehler'", f"{good} ? 'good' : 'bad'")),
                 value(f"={good} ? '–' : {g.dash(disp(item))}", **{"font-size": "16px", "white-space": "normal"})],
                item, title)


# ---------------------------------------------------------------- 13 · time


def age_tile(title, item, interval):
    """How long ago a time stamp lies, its ring emptying over the interval in which a new one is due."""
    ok = f"(!['NULL', 'UNDEF'].includes(items.{item}.state))"
    age = f"Math.max(0, dayjs().diff(dayjs(items.{item}.state), 'minute'))"
    text = (f"={ok} ? (({age}) < 1 ? 'gerade eben' : ({age}) < 60 ? 'vor ' + ({age}) + ' min' : ({age}) < 1440 ? "
            f"'vor ' + Math.floor(({age}) / 60) + ':' + ('0' + ({age}) % 60).slice(-2) + ' h' : "
            f"dayjs(items.{item}.state).format('dd D.M. HH:mm')) : '–'")
    fresh = f"({ok} ? 100 - {clamp(f'{age} / {interval} * 100')} : 0)"
    cls = f"(({age}) <= {interval} * 1.5 ? 'good' : 'warn')"
    texts = [label(title, **TITLE), value(text, **{"font-size": "18px"}),
             label(f"={ok} ? dayjs(items.{item}.state).format('HH:mm') + ' Uhr' : ''", **SUB)]
    return tile([div([ring_svg(fresh, "=" + cls_color(cls), size=40), div(texts, **{"min-width": "0"})],
                     **{"display": "flex", "align-items": "center", "gap": "12px"})], item, title)


def countdown(title, item, none_text="keine"):
    ok = f"(!['NULL', 'UNDEF'].includes(items.{item}.state) && dayjs(items.{item}.state).isAfter(dayjs()))"
    left = f"Math.max(0, dayjs(items.{item}.state).diff(dayjs(), 'minute'))"
    text = (f"={ok} ? 'in ' + (({left}) < 60 ? ({left}) + ' min' : Math.floor(({left}) / 60) + ':' + "
            f"('0' + ({left}) % 60).slice(-2) + ' h') : '{none_text}'")
    return tile([label(title, **TITLE), value(text, **{"font-size": "18px"}),
                 label(f"={ok} ? 'um ' + dayjs(items.{item}.state).format('dd HH:mm') : ''", **SUB)], item, title)


SOLAR_NOON = None  # minutes after midnight UTC, set from openHAB's location


def sun(title, start, stop, peak, power_item):
    """The inverter's day as a sun arc from its start to its end (estimated mirror-symmetric around the solar noon
    while it runs), the sun at the present with the power beside it, the day's peak named."""
    ok = lambda i: f"(!['NULL', 'UNDEF'].includes(items.{i}.state) && dayjs(items.{i}.state).isSame(dayjs(), 'day'))"
    mins = lambda d: f"({d}.hour() * 60 + {d}.minute())"
    t0 = f"({ok(start)} ? {mins(f'dayjs(items.{start}.state)')} : 420)"
    noon = f"({SOLAR_NOON} + dayjs().utcOffset())"
    t1 = f"({ok(stop)} ? {mins(f'dayjs(items.{stop}.state)')} : 2 * {noon} - {t0})"
    now = mins("dayjs()")
    X = lambda m: f"(14 + 432 * ({m}) / 1440)"
    cx, rx = f"(({X(t0)} + {X(t1)}) / 2)", f"(({X(t1)} - {X(t0)}) / 2)"
    xn = f"Math.max({X(t0)}, Math.min({X(t1)}, {X(now)}))"
    yn = f"(96 - 64 * Math.sqrt(Math.max(0, 1 - Math.pow(({xn} - {cx}) / {rx}, 2))))"
    f1 = lambda e: f"({e}).toFixed(1)"
    done = f"'M' + {f1(X(t0))} + ' 96 A' + {f1(rx)} + ' 64 0 0 1 ' + {f1(xn)} + ' ' + {f1(yn)}"
    rest = f"='M' + {f1(xn)} + ' ' + {f1(yn)} + ' A' + {f1(rx)} + ' 64 0 0 1 ' + {f1(X(t1))} + ' 96'"
    hm_ = lambda m: f"(Math.floor(({m}) / 60) + ':' + ('0' + Math.round(({m}) % 60)).slice(-2))"
    up = f"({ok(start)} && {now} < {t1})"
    right_side = f"({xn} > 300)"
    kids = [svg("path", d=f"={done} + ' L' + {f1(xn)} + ' 96 Z'", fill="#ffb300", **{"fill-opacity": "0.12"},
                visible=f"={ok(start)}"),
            svg("path", d=f"={done}", fill="none", stroke="#ffb300", **{"stroke-width": "2.5", "stroke-linecap": "round"},
                visible=f"={ok(start)}"),
            svg("path", d=rest, fill="none", stroke="#ffb300",
                **{"stroke-opacity": "0.5", "stroke-width": "2", "stroke-dasharray": "3 4"}, visible=f"={ok(start)}"),
            svg("line", x1=14, y1=96, x2=446, y2=96, stroke="currentColor", **{"stroke-opacity": "0.2",
                                                                             "stroke-width": "1.5"}),
            *[g.svg_text(14 + 108 * k, 114, f"{6 * k}" + (" Uhr" if k == 4 else ""), 11, opacity="0.5",
                         anchor="start" if k == 0 else "end" if k == 4 else "middle") for k in range(5)],
            g.svg_text(f"={f1(f'{X(t0)} + 4')}", 90, f"='Start ' + {hm_(t0)}", 12, anchor="start", opacity="0.85"),
            g.svg_text(f"={f1(f'{X(t1)} - 4')}", 90, f"=({ok(stop)} ? 'Ende ' : 'Ende ≈ ') + {hm_(t1)}", 12,
                       anchor="end", opacity="0.7"),
            svg("circle", cx=f"={f1(xn)}", cy=f"={f1(yn)}", r=13, fill="#ffb300", **{"fill-opacity": "0.22"},
                visible=f"={up}"),
            svg("circle", cx=f"={f1(xn)}", cy=f"={f1(yn)}", r=8, fill="#ffb300", visible=f"={up}"),
            g.svg_text(f"={f1(f'{xn} + ({right_side} ? -18 : 18)')}", f"={f1(f'{yn} + 4')}",
                       f"={g.dash(disp(power_item))}", 13, weight="700", anchor=f"={right_side} ? 'end' : 'start'")]
    kids[-1]["config"]["visible"] = f"={up}"
    word = chip(f"='Spitze ' + {g.dash(disp(peak))}", "'neutral'")
    return tile([head(title, word), svg("svg", kids, viewBox="0 0 460 118",
                                        style={"display": "block", "width": "100%", "height": "auto",
                                               "max-width": "560px", "margin": "4px auto 0"})], start, title, wide=True)


def price_strip(title, price, cheap_hour, dear_hour):
    """The hourly prices ahead as bars in the price colours, the present dashed, the cheapest and dearest hours
    named with how long until them."""
    track(price, f=[2, 40])
    rows = f"((({hv(price, 'f')}) || []))"
    n = 42
    count = f"Math.max(1, {rows}.length)"
    slot = f"(432 / {count})"
    bars = []
    for i in range(n):
        r_ = f"({rows}[{i}] || [0, 0])"
        v = f"({r_}[1])"
        h = f"({clamp(f'{v} / 0.55 * 50', 1, 50)})"
        bars.append(svg("rect", x=f"=(14 + {i} * {slot} + 0.6).toFixed(2)", y=f"=(66 - {h}).toFixed(1)",
                        width=f"=Math.max(1, {slot} - 1.2).toFixed(2)", height=f"=({h}).toFixed(1)", rx=1.5,
                        fill=f"={v} < 0.2 ? '#43a047' : {v} < 0.3 ? '#fb8c00' : '#e53935'",
                        **{"fill-opacity": f"=dayjs.unix({r_}[0]).add(1, 'hour').isBefore(dayjs()) ? 0.4 : 1"},
                        visible=f"={rows}.length > {i}"))
    t0 = f"({rows}.length ? {rows}[0][0] : 0)"
    X = lambda unix: f"(14 + 432 * (({unix}) - {t0}) / ({count} * 3600))"
    now_x = X("dayjs().unix()")
    def mark(item, color, word):
        x = X(f"dayjs(items.{item}.state).unix() + 1800")
        return svg("text", x=f"=Math.max(30, Math.min(430, {x})).toFixed(1)", y=12,
                   content=f"='{word} ' + dayjs(items.{item}.state).format('HH:mm')", fill=color,
                   **{"font-size": "12", "font-weight": "700", "text-anchor": "middle"},
                   visible=f"={rows}.length > 0 && dayjs(items.{item}.state).unix() >= {t0}")
    midnight = X("dayjs().add(1, 'day').startOf('day').unix()")
    kids = [*bars,
            svg("line", x1=f"={midnight}.toFixed(1)", x2=f"={midnight}.toFixed(1)", y1=16, y2=68,
                stroke="currentColor", **{"stroke-opacity": "0.25"}),
            g.svg_text(f"=({midnight} + 4).toFixed(1)", 82, "=dayjs().add(1, 'day').format('dddd')", 11,
                       anchor="start", opacity="0.6"),
            g.svg_text(14, 82, "heute", 11, anchor="start", opacity="0.6"),
            svg("line", x1=f"={now_x}.toFixed(1)", x2=f"={now_x}.toFixed(1)", y1=16, y2=68, stroke="currentColor",
                **{"stroke-width": "1.2", "stroke-dasharray": "3 2"}),
            mark(cheap_hour, "#43a047", "↓"), mark(dear_hour, "#e53935", "↑")]
    def until(item, word):
        left = f"Math.max(0, dayjs(items.{item}.state).diff(dayjs(), 'minute'))"
        return label(f"='{word} ' + dayjs(items.{item}.state).format('dd HH:mm') + (({left}) > 0 ? ' · in ' + "
                     f"Math.floor(({left}) / 60) + ':' + ('0' + ({left}) % 60).slice(-2) + ' h' : ' · jetzt')",
                     **{"font-size": "12px"})
    return tile([label(title, **TITLE),
                 svg("svg", kids, viewBox="0 0 460 88", style={"display": "block", "width": "100%", "height": "auto",
                                                               "max-width": "560px", "margin": "6px auto 0"}),
                 div([until(cheap_hour, "Günstigste Stunde"), until(dear_hour, "Teuerste Stunde")],
                     **{"display": "flex", "flex-wrap": "wrap", "gap": "4px 20px", "opacity": "0.85"})],
                price, title, wide=True)


def program(title, p):
    """A Miele programme from its start to its end as a bar, the present as a dot, elapsed and remaining time below,
    its end large."""
    running = f"(['NULL', 'UNDEF'].includes(items.{p}_program_finished_time.state) === false && {num(p + '_program_remaining_time')} > 0)"
    el, rest = num(p + "_program_elapsed_time"), num(p + "_program_remaining_time")
    share = f"({clamp(f'{el} / Math.max(1, {el} + {rest}) * 100')})"
    d = lambda s: (f"(({s}) >= 3600 ? Math.floor(({s}) / 3600) + ':' + ('0' + Math.floor(({s}) % 3600 / 60)).slice(-2) "
                   f"+ ' h' : Math.ceil(({s}) / 60) + ' min')")
    bar_ = div([bar(share, "#42a5f5", height=10),
                div([], **{"position": "absolute", "top": "-3px", "width": "16px", "height": "16px",
                           "margin-left": "-8px", "border-radius": "50%", "box-sizing": "border-box",
                           "background": "#42a5f5", "border": "2px solid var(--f7-card-bg-color, #fff)",
                           "left": f"={share} + '%'"})],
               **{"position": "relative", "height": "10px", "margin": "12px 4px 6px",
                  "background": "rgba(127, 127, 127, 0.18)", "border-radius": "5px"})
    ends = div([label(f"='Start ' + dayjs().subtract({el}, 'second').format('HH:mm')"),
                label(f"='seit ' + {d(el)} + ' · noch ' + {d(rest)}"),
                label(f"='Ende ' + dayjs(items.{p}_program_finished_time.state).format('HH:mm')")],
               **{"display": "flex", "justify-content": "space-between", "gap": "8px", **SUB})
    kids = [head(title, chip(f"=Math.round({share}) + ' %'", "'info'")),
            value(f"='fertig um ' + dayjs(items.{p}_program_finished_time.state).format('HH:mm')"), bar_, ends]
    idle = [label(title, **TITLE), value("kein Programm", **{"font-size": "16px", "opacity": "0.6"})]
    return [tile(kids, p + "_program_progress", title, wide=True, visible=f"={running}"),
            tile(idle, p + "_program_progress", title, visible=f"=!{running}")]


# ---------------------------------------------------------------- 14 · phases


def direction_rows(vals, names, top, unit, digits, one_sided=False):
    """Values per phase as bars around a middle line: export (negative) to the left in green, import to the right in
    red; one_sided: amounts only, to the right in the neutral colour."""
    rows = []
    for v, n in zip(vals, names):
        share = f"({clamp(f'Math.abs({v}) / {top} * 100')}).toFixed(1)"
        right = div([div([], **{"height": "14px", "border-radius": "0 4px 4px 0",
                                "background": "#7986cb" if one_sided else "#e57373",
                                "width": f"={share} + '%'" if one_sided else f"={v} > 0 ? {share} + '%' : '0%'"})],
                    **{"border-left": "1.5px solid rgba(127, 127, 127, 0.7)"})
        shown = f"={fixed(f'Math.abs({v})', digits)} + ' {unit}'" if one_sided else f"={signed(v, digits, unit)}"
        cells = [label(n, **{"font-size": "11px", "opacity": "0.65"})]
        if not one_sided:
            cells.append(div([div([], **{"height": "14px", "border-radius": "4px 0 0 4px", "background": "#81c784",
                                         "width": f"={v} < 0 ? {share} + '%' : '0%'"})],
                             **{"display": "flex", "justify-content": "flex-end"}))
        cells += [right, label(shown, **{"font-size": "11px", "font-weight": "600", "text-align": "right",
                                         "white-space": "nowrap"})]
        rows += cells
    columns = "24px 1fr 64px" if one_sided else "24px 1fr 1fr 64px"
    return div(rows, **{"display": "grid", "grid-template-columns": columns, "align-items": "center",
                        "gap": "6px 0", "column-gap": "6px"})


def direction_words():
    return div([label("← Einspeisung", **{"color": "=" + cls_color("'good'")}),
                label("Bezug →", **{"color": "=" + cls_color("'bad'")})],
               **{"display": "flex", "justify-content": "space-around", "font-size": "10.5px", "margin": "6px 0 2px"})


def phase_power(title, items_, names):
    """Power per phase around a middle line, its sum beside the title: values only, the currents judge imbalance."""
    vals = [num(i) for i in items_]
    top = f"(Math.max(50, {', '.join(f'Math.abs({v})' for v in vals)}) * 1.15)"
    total = " + ".join(vals)
    return tile([head(title, chip(f"='Σ ' + {signed(f'({total})', 0, 'W')}")), direction_words(),
                 direction_rows(vals, names, top, "W", 0)], items_[0], title)


def phase_volts(title, items_, names):
    lo, hi = 200, 260
    y = lambda e: f"(110 - {clamp(f'(({e}) - {lo}) / {hi - lo} * 100', 0, 100)})"
    kids = [svg("rect", x=14, y=21.7, width=100, height=76.6, rx=4, fill="#66bb6a", **{"fill-opacity": "0.12"}),
            svg("line", x1=14, y1=60, x2=114, y2=60, stroke="currentColor",
                **{"stroke-opacity": "0.4", "stroke-dasharray": "3 3"}),
            g.svg_text(117, 63, "230", 8.5, anchor="start", opacity="0.6"),
            g.svg_text(117, 25, "253", 8, anchor="start", opacity="0.6"),
            g.svg_text(117, 101, "207", 8, anchor="start", opacity="0.6")]
    ok = []
    for k, (item, n) in enumerate(zip(items_, names)):
        x = 28 + 32 * k
        v = num(item)
        ok.append(f"({v} >= 207 && {v} <= 253)")
        kids += [svg("rect", x=x, y=f"={y(v)}.toFixed(1)", width=22, height=f"=(110 - {y(v)}).toFixed(1)", rx=3,
                     fill="#7986cb"),
                 g.svg_text(x + 11, f"=({y(v)} - 5).toFixed(1)", f"={fixed(v, 1)}", 9),
                 g.svg_text(x + 11, 122, n, 9, opacity="0.65")]
    inside = " && ".join(ok)
    return tile([head(title, chip(f"={inside} ? 'im Band ± 10 %' : 'außerhalb'", f"{inside} ? 'good' : 'bad'")),
                 svg("svg", kids, viewBox="0 0 140 126", style={"display": "block", "width": "100%", "height": "auto",
                                                               "max-width": "220px", "margin": "4px auto 0"})],
                items_[0], title)


def phase_amps(title, items_, names, neutral=None, powers=None):
    """Current per phase. With the phases' active powers (a meter) each current carries their direction, |I| with
    the sign of P (the Huawei meter signs currents, SmartPi gives amounts; the sign of SmartPi's cos φ contradicts its
    power's in 5-8 % of readings), drawn around a middle line like the power; imbalance is the spread of these signed
    currents: below 10 A even, below 20 A raised, from 20 A (about 4.6 kVA) an imbalance. Without powers (the PV
    inverter, which only feeds in) amounts to one side and their spread without a verdict."""
    if powers:
        vals = [f"(Math.abs({num(i)}) * ({num(p_)} < 0 ? -1 : 1))" for i, p_ in zip(items_, powers)]
    else:
        vals = [f"Math.abs({num(i)})" for i in items_]
    top = f"(Math.max(1, {', '.join(f'Math.abs({v})' for v in vals)}) * 1.15)"
    spread_ = f"(Math.max({', '.join(vals)}) - Math.min({', '.join(vals)}))"
    spread_text = f"'Spanne ' + {fixed(spread_, 2 if not powers else 1)} + ' A'"
    if powers:
        word = chip(f"={spread_} < 10 ? 'ausgeglichen' : {spread_} < 20 ? 'erhöht' : 'Schieflast'",
                    f"{spread_} < 10 ? 'good' : {spread_} < 20 ? 'warn' : 'bad'")
        kids = [head(title, word), direction_words(), direction_rows(vals, names, top, "A", 2)]
    else:
        kids = [head(title, chip(f"={spread_text}")), direction_rows(vals, names, top, "A", 2, one_sided=True)]
    foot = [f"={spread_text}"] if powers else []
    if neutral:
        foot.append(f"='N ' + {fixed(num(neutral), 2)} + ' A'")
    if foot:
        kids.append(div([label(t) for t in foot], **{"display": "flex", "justify-content": "space-between",
                                                     **SUB, "margin-top": "8px"}))
    return tile(kids, items_[0], title)


def pill_text(x, y, text, fill="#48484a", color="#ffffff", weight="normal"):
    """A value in a dark grey pill: the pill as wide as its text (about 5.5 units a character at 10)."""
    w = f"((({text}).length * 5.5 + 12))"
    return svg("g", [svg("rect", x=f"=({x} - {w} / 2).toFixed(1)", y=round(y - 10.5, 1), width=f"={w}.toFixed(1)",
                         height=14, rx=7, fill=fill),
                     svg("text", x=x, y=y, fill=color, content=f"={text}",
                         **{"font-size": "10", "font-weight": weight, "text-anchor": "middle"})])


def phase_load(title, items_, names, neutral=None):
    """How much current each line carries, as a triangle of the amounts (direction does not matter to a wire), each
    value in a dark grey pill at its outer corner, the measured neutral (SmartPi) as a dashed circle on the same scale,
    warned where it carries more than the most loaded phase. The scale follows the largest current, so a strong
    imbalance draws a spike towards its phase and the neutral's circle grows with it."""
    import math
    cx, cy, R = 85, 70, 50
    vals = [f"Math.abs({num(i)})" for i in items_]
    n = f"Math.abs({num(neutral)})" if neutral else None
    top = f"(Math.max(1, {', '.join(vals + ([n] if n else []))}) * 1.12)"
    angles = (90, -30, 210)
    def xy(v, ang, r=R):
        c, s_ = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        return f"({cx} + {c:.4f} * {r} * {v} / {top})", f"({cy} - {s_:.4f} * {r} * {v} / {top})"
    grid_ = []
    for k in (1, 2 / 3, 1 / 3):
        pts = " ".join(f"{cx + math.cos(math.radians(ang)) * R * k:.1f},{cy - math.sin(math.radians(ang)) * R * k:.1f}"
                       for ang in angles)
        grid_.append(svg("polygon", points=pts, fill="none", stroke="currentColor", **{"stroke-opacity": "0.14"}))
    corners = [xy(v, ang) for v, ang in zip(vals, angles)]
    poly = "=" + " + ' ' + ".join(f"{x}.toFixed(1) + ',' + {y}.toFixed(1)" for x, y in corners)
    hi = f"Math.max({', '.join(vals)})"
    def corner_label(k, dy):
        # at the grid's outer corner, where no corner of the triangle and no circle can reach past it
        ang = math.radians(angles[k])
        return pill_text(round(cx + math.cos(ang) * R, 1), round(cy - math.sin(ang) * R + dy, 1),
                         f"'{names[k]} ' + {fixed(vals[k], 2)} + ' A'")
    kids = [*grid_]
    if n:
        over = f"({n} > {hi} * 1.1)"
        kids.append(svg("circle", cx=cx, cy=cy, r=f"=({R} * {n} / {top}).toFixed(1)", fill="none",
                        stroke="=" + cls_color(f"{over} ? 'warn' : 'neutral'"),
                        **{"stroke-width": "1.6", "stroke-dasharray": "3 3", "stroke-opacity": "0.9"}))
    kids += [svg("polygon", points=poly, fill="#7986cb", stroke="#9fa8da",
                 **{"fill-opacity": "0.32", "stroke-width": "1.8", "stroke-linejoin": "round"}),
             corner_label(0, -6), corner_label(1, 15), corner_label(2, 15)]
    if n:
        kids.append(pill_text(cx, cy + R + 18, f"'N ' + {fixed(n, 2)} + ' A'", weight="700",
                              fill=f"={over} ? '#a35200' : '#48484a'"))
    most = " : ".join(f"{v} === {hi} ? '{nm}'" for v, nm in zip(vals[:-1], names[:-1])) + f" : '{names[-1]}'"
    word = chip(f"='max. ' + ({most}) + ' ' + {fixed(hi, 2)} + ' A'")
    if n:
        word = chip(f"={n} > {hi} * 1.1 ? 'N über allen Phasen' : 'max. ' + ({most}) + ' ' + {fixed(hi, 2)} + ' A'",
                    f"{n} > {hi} * 1.1 ? 'warn' : 'neutral'")
    # the neutral's pill reaches down to cy + R + 21.5 (141.5): the drawing ends a little below it
    return tile([head(title, word), svg("svg", kids, viewBox=f"0 4 170 {142 if n else 118}",
                                        style={"display": "block", "width": "100%", "height": "auto",
                                               "max-width": "240px", "margin": "4px auto 0"})], items_[0], title)


def phase_cos(title, items_, names):
    import math
    kids = []
    for k, (item, n) in enumerate(zip(items_, names)):
        cx = 27 + 53 * k
        c = f"Math.max(-1, Math.min(1, {num(item)}))"
        kids += [svg("path", d=f"M{cx - 18} 32 A18 18 0 0 1 {cx + 18} 32", fill="none", stroke="currentColor",
                     **{"stroke-opacity": "0.22", "stroke-width": "2"}),
                 svg("line", x1=cx, y1=32, x2=f"=({cx} + 17 * {c}).toFixed(1)",
                     y2=f"=(32 - 17 * Math.sqrt(1 - Math.pow({c}, 2))).toFixed(1)", stroke="#9fa8da",
                     **{"stroke-width": "2", "stroke-linecap": "round"}),
                 svg("circle", cx=cx, cy=32, r=2.5, fill="currentColor"),
                 g.svg_text(cx, 45, f"='{n} ' + {fixed(num(item), 2)}", 8.5, opacity="0.75")]
    return tile([label(title, **TITLE), svg("svg", kids, viewBox="0 0 160 48",
                                            style={"display": "block", "width": "100%", "height": "auto",
                                                   "max-width": "260px", "margin-top": "6px"})], items_[0], title)


NEUTRAL = {"smartpi_i1": "smartpi_i4"}


def phase_table(heads, rows):
    """Phases as pictures: power by direction, voltages in their band, currents as a triangle (Schieflast), cos φ as
    needles, frequency on its band; two PV strings side by side."""
    tiles = []
    if len(heads) == 2:  # the PV strings
        by = dict(rows)
        tiles.append(strings("Leistung je String", by["Leistung"], heads, by["Spannung"], by["Strom"],
                             ["#ffca28", "#ff8f00"]))
    else:
        for title, items_ in rows:
            if title in ("Leistung", "Wirkleistung"):
                tiles.append(phase_power("Leistung je Phase", items_, heads))
            elif title == "Spannung":
                tiles.append(phase_volts("Spannung", items_, heads))
            elif title == "Strom":
                by = dict(rows)
                powers = by.get("Leistung") or by.get("Wirkleistung")
                # with the meters' powers the currents get their direction; the triangle shows what the lines
                # carry, as amounts (user, 2026-10-06), the neutral there
                tiles.append(phase_amps("Strom je Phase", items_, heads, None if powers else NEUTRAL.get(items_[0]),
                                        powers))
                if powers:
                    tiles.append(phase_load("Leitungsbelastung", items_, heads, NEUTRAL.get(items_[0])))
            elif title == "Frequenz":
                tiles.append(band_bar("Frequenz", items_[0], 49.8, 50.2, 49.9, 50.1, "#7986cb", nominal=50))
            elif title.startswith("cos"):
                tiles.append(phase_cos("cos φ", items_, heads))
            else:
                tiles += [g.vtile(f"{title} {h}", i) for i, h in zip(items_, heads)]
    return grid(tiles)


# ---------------------------------------------------------------- the electric card: power triangle


def triangle(title, prefix):
    """Active, reactive and apparent power as a right triangle centred in its tile, its angle φ, the power factor
    named."""
    P, Q, S, pf = (num(f"{prefix}_power"), num(f"{prefix}_reactive_power"), num(f"{prefix}_apparent_power"),
                   num(f"{prefix}_power_factor"))
    phi = f"Math.acos(Math.max(0, Math.min(1, Math.abs({pf}))))"
    L = f"Math.min(200 / Math.max(Math.cos({phi}), 0.05), 58 / Math.max(Math.sin({phi}), 0.05))"
    w, h = f"({L} * Math.cos({phi}))", f"({L} * Math.sin({phi}))"
    x0 = f"(140 - {w} / 2)"
    xp, yq = f"({x0} + {w})", f"(72 - {h})"
    f1 = lambda e: f"({e}).toFixed(1)"
    loaded = f"({S} > 1)"
    kids = [svg("path", d=f"='M' + {f1(x0)} + ' 72 L' + {f1(xp)} + ' 72 L' + {f1(xp)} + ' ' + {f1(yq)} + ' Z'",
                fill="#7986cb", stroke="#9fa8da", **{"fill-opacity": "0.2", "stroke-width": "1.6",
                                                     "stroke-linejoin": "round"}),
            svg("line", x1=f"={f1(x0)}", y1=72, x2=f"={f1(xp)}", y2=72, stroke="#fb8c00", **{"stroke-width": "3"}),
            svg("line", x1=f"={f1(xp)}", y1=72, x2=f"={f1(xp)}", y2=f"={f1(yq)}", stroke="#90a4ae",
                **{"stroke-width": "3"}),
            g.svg_text(f"={f1(f'{x0} + {w} / 2')}", 88, f"='P ' + {fixed(P, 0)} + ' W'", 11, weight="700"),
            g.svg_text(f"={f1(f'{xp} + 7')}", f"={f1(f'72 - {h} / 2 + 4')}", f"='Q ' + {fixed(Q, 0)} + ' var'", 11,
                       anchor="start"),
            g.svg_text(f"={f1(f'{x0} + {w} / 2 - 8')}", f"={f1(f'72 - {h} / 2 - 4')}",
                       f"='S ' + {fixed(S, 0)} + ' VA'", 11, anchor="end", opacity="0.8")]
    lo, hi, segs = SCALES["power_factor"]
    word, _ = rating_parts(f"Math.abs({pf})", lo, hi, segs)
    drawing = svg("svg", kids, viewBox="0 0 280 94", style={"display": "block", "width": "100%", "height": "auto",
                                                           "max-width": "380px", "margin": "4px auto 0"},
                  visible=f"={loaded}")
    return tile([head(title, [label(f"='cos φ ' + {fixed(f'Math.abs({pf})', 2)}", **{"font-size": "13px",
                                                                                    "font-weight": "700"}), word]),
                 drawing, label("keine Last", visible=f"=!{loaded}", **{**SUB, "margin": "12px 0"})],
                f"{prefix}_power_factor", title, wide=True)


# ---------------------------------------------------------------- the grids


def grid(tiles):
    return div(tiles, **{"display": "grid", "grid-template-columns": "repeat(auto-fill, minmax(220px, 1fr))",
                         "gap": "10px", "padding": "4px 16px 16px"})


def plain(t):
    return t["tile"]


DROP = object()


def wide_grid(tiles):
    """The proposal's grid of a device page's tiles: each item's renderer, consumed items left out."""
    present = [t["config"].get("item") for t in tiles]
    out, used = [], set()
    for t in tiles:
        item = t["config"].get("item")
        if item in used:
            continue
        rule = RENDER.get(item)
        if isinstance(rule, list):
            n = SEEN.get(item, 0)
            SEEN[item] = n + 1
            rule = rule[min(n, len(rule) - 1)]
        if rule is DROP:
            continue
        if rule is None:
            out.append(t)
            continue
        made, consumed = rule(dict(title=t["config"]["title"], item=item, tile=t, present=present))
        used |= set(consumed)
        out += made if isinstance(made, list) else [made]
    return grid(out)


SEEN = {}


def r(fn, *consumes):
    """A renderer from a function of the tile's title and item that consumes the items named (from this grid)."""
    return lambda t: (fn(t["title"], t["item"]), consumes)


# ---------------------------------------------------------------- what each value becomes

HP = g.HPX
W, O = "netatmo_weatherstation_", "netatmo_outdoor_"
HPWR = HP["power"]  # the heat pump's electrical power, incl. its heaters
kw = lambda item, d=2: f"={fixed(f'{num(item)} / 1000', d)} + ' kW'"
STORE = "huawei_inverter_energy_storage_"
UNIT1 = STORE + "unit_1_"
PV_DAY, PV_OWN = "huawei_inverter_e_day", "photovoltaics_own_ec_day"


def absolute_humidity(temp, rh):
    """Grams of water per cubic metre of air at a temperature (°C) and relative humidity (%), Magnus formula."""
    return (f"(6.112 * Math.exp(17.67 * {num(temp)} / ({num(temp)} + 243.5)) * {num(rh)} * 2.1674 / "
            f"(273.15 + {num(temp)}))")


def airing_line():
    """Whether outdoor air brought in dries or dampens the rooms: its absolute humidity against the indoor air's."""
    out = absolute_humidity(O + "temperature", O + "atmospheric_humidity")
    inn = absolute_humidity(W + "temperature", W + "atmospheric_humidity")
    d = f"({out} - {inn})"
    cls = f"({d} < -1 ? 'good' : {d} > 1 ? 'warn' : 'neutral')"
    word = chip(f"={d} < -1 ? 'Lüften trocknet' : {d} > 1 ? 'Lüften befeuchtet' : 'Lüften neutral'", cls)
    text = label(f"='absolut ' + {fixed(out, 1)} + ' g/m³ · innen ' + {fixed(inn, 1)} + ' g/m³'",
                 **{**SUB, "flex": "1 1 auto"})
    return div([text, word], **{"display": "flex", "flex-wrap": "wrap", "align-items": "center",
                                "justify-content": "space-between", "gap": "4px 8px", "margin-top": "6px"})


def battery_power(title, item):
    return balance(title, item, ("Entladen", f"Math.max(0, {num(item)} / 1000)", "#c5e1a5"),
                   ("Laden", f"Math.max(0, -{num(item)} / 1000)", "#7cb342"), unit="kW", digits=2,
                   net_words=("lädt", "entlädt"))


def battery_day(title, item, other):
    return balance("Heute", item, ("Entladen", num(other), "#c5e1a5"), ("Geladen", num(item), "#7cb342"),
                   net_words=("in den Akku", "aus dem Akku"))


def battery_totals(title, item, other):
    eff = f"({num(other)} / Math.max({num(item)}, 0.001) * 100)"
    return counters("Seit Inbetriebnahme", item, other, "geladen", "entladen", 5, 1, "kWh",
                    f"='Wirkungsgrad ' + {fixed(eff, 1)} + ' %'")


def grid_day(ec, ep):
    def make(title, item):
        def cmp_chip(i, better):
            track(i, c=True)
            y = f"Number({hv(i, 'y')})"
            dd = f"(({num(i)} - {y}) / {y} * 100)"
            cls = f"(Math.abs({dd}) < 3 ? 'neutral' : ({dd} > 0) === {better} ? 'good' : 'warn')"
            return chip(f"={dd} >= 300 ? '×' + {fixed(f'{num(i)} / {y}', 0)} + ' zu gestern' : "
                        f"({dd} >= 0 ? '+' : '−') + Math.round(Math.abs({dd})) + ' % zu gestern'", cls,
                        visible=f"={has(hv(i, 'y'))} && {y} > 0")
        chips_ = div([cmp_chip(ec, "false"), cmp_chip(ep, "true")],
                     **{"display": "flex", "justify-content": "space-between", "margin-top": "8px"})
        return balance("Netz heute", ec, ("Bezug", num(ec), "#e57373"), ("Einspeisung", num(ep), "#81c784"),
                       extra=[chips_])
    return lambda t: (make(t["title"], t["item"]), {ep})


def price_mix(title, item):
    """The gross price split into what it consists of: market, the rest of the net price, VAT."""
    market, net, gross = num("epex_spot_awattar"), num("epex_spot_awattar_total_net"), num(g.PRICE)
    parts = [("Markt", market, "#fb8c00"), ("Netz & Abgaben", f"Math.max(0, {net} - {market})", "#7986cb"),
             ("USt.", f"Math.max(0, {gross} - {net})", "#90a4ae")]
    return tile([head("Zusammensetzung brutto", value(f"={fixed(gross, 3)} + ' €'", **{"font-size": "16px"})),
                 split_bar(parts, gross, 18), split_legend(parts, 3),
                 label(f"='netto ' + {fixed(net, 3)} + ' € · Markt brutto ' + {fixed(num('epex_spot_awattar_market_gross'), 3)} + ' €'",
                       **{**SUB, "margin-top": "6px"})], item, title, wide=True)


def price_now(title, item):
    return rating("Strompreis jetzt", g.PRICE, "price", value_expr=f"={fixed(num(g.PRICE), 3)} + ' €/kWh'")


def hp_flow(title, item):
    # only while it runs: the day's conversion stands right under Jetzt anyway
    return flow_cop("Strom → Wärme jetzt", HPWR, HP["heat"],
                    f"({num(HP['cop'])} > 0 ? {fixed(num(HP['cop']), 2)} : '–')", hide_idle=True)


def cop_badge(name, item, color, icon, full=6):
    """A part's COP: a small ring filled to COP / full in the part's colour, its icon inside, the value beside."""
    ring_ = div([ring_svg(f"{num(item)} / {full} * 100", color, size=26, width=8),
                 comp("oh-icon", {"icon": icon, "width": 12, "height": 12,
                                  "style": {"position": "absolute", "left": "50%", "top": "50%", "width": "12px",
                                            "height": "12px", "transform": "translate(-50%, -50%)", "color": color}})],
                **{"position": "relative", "width": "26px", "height": "26px", "flex": "0 0 auto"})
    return div([ring_, label(f"='{name} ' + ({num(item)} > 0 ? {fixed(num(item), 2)} : '–')",
                             **{"font-size": "12px", "font-weight": "600", "white-space": "nowrap"})],
               **{"display": "flex", "align-items": "center", "gap": "6px"})


def hp_day_flow(title, item):
    # the purposes' COPs at the top right, one under the other, each with a ring filled by its value (user, 2026-10-06)
    side = div([cop_badge("COP Heizung", "espaltherma_dcop_space", g.SPACE_C, "material:local_fire_department"),
                cop_badge("COP WW", "espaltherma_dcop_dhw", g.DHW_C, "material:water_drop")],
               **{"display": "flex", "flex-direction": "column", "gap": "4px", "align-items": "flex-start"})
    return flow_cop("Strom → Wärme heute", "espaltherma_energy_today", "espaltherma_heating_energy_today",
                    g.dash(disp("espaltherma_dcop")), unit="kWh", factor=1, still="noch kein Betrieb heute", side=side)


def hp_heat_flow():
    return flow_split("Wärme heute: wohin", "espaltherma_heating_energy_today",
                      [("Heizung", num("espaltherma_heating_energy_space_today"), g.SPACE_C),
                       ("Warmwasser", num("espaltherma_heating_energy_dhw_today"), g.DHW_C)], source_name="Wärme")


def hp_energy(title, item):
    parts = [("Heizung", num("espaltherma_energy_space_today"), g.SPACE_C),
             ("Warmwasser", num("espaltherma_energy_dhw_today"), g.DHW_C),
             ("Standby", num("espaltherma_energy_standby_today"), g.STANDBY_C)]
    return compare("Strom heute", item, "#ffa726", better="less",
                   extra=[split_bar(parts, num(item)), split_legend(parts)])


def hp_heat(title, item):
    parts = [("Heizung", num("espaltherma_heating_energy_space_today"), g.SPACE_C),
             ("Warmwasser", num("espaltherma_heating_energy_dhw_today"), g.DHW_C)]
    return compare("Wärme heute", item, "#e53935", extra=[split_bar(parts, num(item)), split_legend(parts)])


def hp_split_power(title, item):
    parts = [("Heizung", num("espaltherma_electrical_power_space"), g.SPACE_C),
             ("Warmwasser", num("espaltherma_electrical_power_dhw"), g.DHW_C),
             ("Standby", num("espaltherma_electrical_power_standby"), g.STANDBY_C)]
    total = " + ".join(e for _, e, _ in parts)
    return split("Strom nach Zweck jetzt", item, parts, total, f"={fixed(f'({total}) / 1000', 2)} + ' kW'")


def hp_split_heat(title, item):
    parts = [("Heizung", num("espaltherma_heating_power_space"), g.SPACE_C),
             ("Warmwasser", num("espaltherma_heating_power_dhw"), g.DHW_C)]
    total = " + ".join(e for _, e, _ in parts)
    return split("Wärme nach Zweck jetzt", item, parts, total, f"={fixed(f'({total}) / 1000', 2)} + ' kW'", "#e53935")


def pump(title, item):
    return ring("Umwälzpumpe", item, "#42a5f5", pct_expr=num("espaltherma_water_pump_signal"),
                value_expr=f"={g.dash(disp(item))}", sub=f"='Signal ' + {g.dash(disp('espaltherma_water_pump_signal'))}")


WATER_RATE_L = f"({num('water_meter_rate')} * 1000)"


def water_today(title, item):
    liters = f"({num('water_meter_value_day')} * 1000)"
    return compare("Verbrauch heute", "water_meter_value_day", "#42a5f5", factor=1000, digits=0, unit="l",
                   value_expr=f"=Math.round({liters}) + ' l'",
                   extra=[tubs(liters), label(f"='≈ ' + {fixed(f'{liters} / 150', 1)} + ' Badewannen à 150 l'",
                                              **{**SUB, "margin-top": "4px"})])


def own_use(title, item):
    parts = [("Eigenverbrauch", num(PV_OWN), "#43a047"),
             ("Einspeisung", f"Math.max(0, {num(PV_DAY)} - {num(PV_OWN)})", "#a5d6a7")]
    return donut("Ertrag heute: wohin", item, parts, num(PV_DAY), fixed(num(PV_DAY), 1), "kWh")


def pv_power(title, item):
    """The inverter's output against the day's peak: the bar to now, the peak as a tick."""
    peak = "huawei_inverter_active_peak_of_current_day"
    top = f"Math.max({num(peak)}, {num(item)}, 1)"
    bars = track_bar([bar(clamp(f"{num(item)} / {top} * 100"), "#5c6bc0", height=10),
                      div([], **{"position": "absolute", "right": "0", "top": "-5px", "height": "20px", "width": "2px",
                                 "background": "currentColor"})], height=10, **{"margin": "12px 0 4px"})
    sub = div([label("0"), label(f"='Spitze heute ' + {kw(peak, 3)[1:]}")],
              **{"display": "flex", "justify-content": "space-between", **SUB, "margin-top": "6px"})
    return tile([head(title, chip(f"=Math.round({num(item)} / {top} * 100) + ' % der Spitze'")),
                 value(kw(item, 3)), bars, sub], item, title, "#5c6bc0")


def plug_energy(title, item):
    return compare(title, item, "#ffa726")


def plug_total(title, item):
    return counter(title, item, 5, 1, "kWh")


def socket_volt(title, item):
    return band_bar(title, item, 200, 260, 207, 253, "#7986cb", nominal=230, ok_text="230 V ± 10 %")


RENDER = {
    # Netatmo
    W + "atmospheric_humidity": r(lambda t, i: rating(t, i, "humidity", spark_of=("#29b6f6", 10, "%", 0, None))),
    W + "co2": r(lambda t, i: rating("CO₂", i, "co2", spark_of=("#90a4ae", 200, "ppm", 0, 1000))),
    W + "noise": r(lambda t, i: rating(t, i, "noise", spark_of=("#9575cd", 10, "dB", 0, None))),
    W + "barometric_pressure": r(lambda t, i: rating(t, i, "air_pressure", spark_of=("#7986cb", 6, "hPa", 1, None, 3))),
    O + "atmospheric_humidity": r(lambda t, i: rating(t, i, "humidity_out", spark_of=("#80deea", 10, "%", 0, None),
                                                      extra=[airing_line()])),
    O + "battery_level": r(lambda t, i: cells(t, i, "#90a4ae", 5, sub="Außenmodul")),
    W + "last_seen": r(lambda t, i: age_tile(t, i, 10)), O + "last_seen": r(lambda t, i: age_tile(t, i, 10)),
    W + "measures_timestamp": r(lambda t, i: age_tile(t, i, 10)),
    O + "measures_timestamp": r(lambda t, i: age_tile(t, i, 10)),
    W + "signal": r(lambda t, i: levels("Funksignal", W + "signal_strength",
                                        [("1", "schwach"), ("2", "mittel"), ("3", "gut"), ("4", "sehr gut")],
                                        "#7986cb", sub=f"={g.dash(disp(i))}"), W + "signal_strength"),
    O + "signal": r(lambda t, i: levels("Funksignal", O + "signal_strength",
                                        [("1", "schwach"), ("2", "mittel"), ("3", "gut"), ("4", "sehr gut")],
                                        "#7986cb", sub=f"={g.dash(disp(i))}"), O + "signal_strength"),
    W + "dewpoint": r(lambda t, i: dew("Taupunktabstand", i, W + "temperature", "Raum")),
    O + "dewpoint": r(lambda t, i: dew("Taupunktabstand", i, O + "temperature", "Luft", inside=False)),
    W + "heat_index": r(lambda t, i: rating(t, i, "heat_index")),
    O + "heat_index": r(lambda t, i: rating(t, i, "heat_index")),
    W + "min_temp": r(lambda t, i: day_range("Temperatur heute", i, W + "max_temp", W + "temperature", "#fb8c00"),
                      W + "max_temp"),
    O + "min_temp": r(lambda t, i: day_range("Temperatur heute", i, O + "max_temp", O + "temperature", "#29b6f6"),
                      O + "max_temp"),
    # SmartPi and the Huawei power meter
    "smartpi_ecday": grid_day("smartpi_ecday", "smartpi_epday"),
    "smartpi_i4": DROP,  # in the current triangle
    "huawei_inverter_power_meter_ec_day": grid_day("huawei_inverter_power_meter_ec_day",
                                                   "huawei_inverter_power_meter_ep_day"),
    "huawei_inverter_power_meter_power_factor": r(lambda t, i: rating(t, i, "power_factor")),
    "huawei_inverter_power_meter_frequency": r(lambda t, i: band_bar(t, i, 49.8, 50.2, 49.9, 50.1, "#7986cb",
                                                                     nominal=50)),
    # photovoltaics
    "huawei_inverter_active_power": r(pv_power, "huawei_inverter_active_peak_of_current_day"),
    "huawei_inverter_efficiency": r(lambda t, i: ring(t, i, "#ffb300", sub="Wechselrichter")),
    PV_DAY: r(lambda t, i: compare("Ertrag heute", i, "#ffb300", better="more")),
    PV_OWN: r(own_use),
    "huawei_inverter_e_total": r(lambda t, i: counter("Ertrag gesamt", i, 6, 1, "kWh")),
    "huawei_inverter_startup_time": r(lambda t, i: sun("Sonnenbogen des Wechselrichters", i,
                                                       "huawei_inverter_shutdown_time",
                                                       "huawei_inverter_active_peak_of_current_day", g.PV),
                                      "huawei_inverter_shutdown_time"),
    "huawei_inverter_internal_temperature": r(lambda t, i: spark(t, i, "#ff7043", "K", 1, span=6)),
    "huawei_inverter_error_code": r(lambda t, i: ok_tile(t, i, f"{num(i)} === 0")),
    "huawei_inverter_optimizers_online": r(lambda t, i: dots("Optimierer online", i, "huawei_inverter_optimizers_total",
                                                             "#ffb300"), "huawei_inverter_optimizers_total"),
    # battery
    STORE + "power": r(battery_power),
    STORE + "day_charge": r(lambda t, i: battery_day(t, i, STORE + "day_discharge"), STORE + "day_discharge"),
    STORE + "soc": r(lambda t, i: cells(t, i, "#7cb342",
                                        sub=f"={fixed(f'Math.max(0, {num(i)} - 3) * 0.07', 2)} + ' kWh nutzbar'")),
    STORE + "total_charge": r(lambda t, i: battery_totals(t, i, STORE + "total_discharge"), STORE + "total_discharge"),
    UNIT1 + "soc": r(lambda t, i: cells(t, i, "#7cb342")),
    UNIT1 + "power": r(battery_power),
    UNIT1 + "day_charge": r(lambda t, i: battery_day(t, i, UNIT1 + "day_discharge"), UNIT1 + "day_discharge"),
    UNIT1 + "total_charge": r(lambda t, i: battery_totals(t, i, UNIT1 + "total_discharge"), UNIT1 + "total_discharge"),
    UNIT1 + "temperature": r(lambda t, i: rating(t, i, "battery_temp")),
    # air conditioner
    "air_conditioning_unit_power": r(lambda t, i: spark(t, i, g.AC_BLUE, "W", 0, span=200)),
    "faikout_perfera_outdoor_temperature": r(lambda t, i: inout("Raum und außen", "faikout_perfera_temperature", i)),
    "faikout_perfera_temperature_setpoint": r(lambda t, i: setpoint("Raum gegen Soll", "faikout_perfera_temperature",
                                                                   num(i), g.dash(disp(i)), 16, 30, g.AC_BLUE,
                                                                   tol=0.5)),
    "faikout_perfera_compressor_frequency": r(lambda t, i: spark(t, i, "#78909c", "Hz", 0, span=20)),
    # the liquid line and the indoor fan with their day's course too, as the compressor (user, 2026-10-06)
    "faikout_perfera_liquid_temperature": r(lambda t, i: spark(t, i, "#29b6f6", "K", 1, span=4)),
    "faikout_perfera_fan_speed": r(lambda t, i: spark(t, i, "#26a69a", "Hz", 1, span=5)),
    # heat pump
    HP["heat"]: r(hp_flow, HP["cop"]),
    HP["supply"]: r(lambda t, i: spread("Vorlauf → Rücklauf", i, HP["return"], "Vorlauf", "Rücklauf",
                                        sub=f"='Durchfluss ' + {g.dash(disp(HP['flow']))}"), HP["return"]),
    HP["tank"]: [r(lambda t, i: tank("Warmwasserspeicher", i, HP["tank_set"])),
                 r(lambda t, i: spark(t, i, "#ef5350", "K", 1, span=4, threshold=num(HP["tank_set"]),
                                      threshold_label="Soll"))],
    HP["outdoor"]: r(lambda t, i: spark(t, i, "#26a69a", "K", 1, span=4)),
    HP["hz"]: r(lambda t, i: spark(t, i, "#fb8c00", "Hz", 0, span=20)),
    HP["flow"]: r(pump, "espaltherma_water_pump_signal"),
    "espaltherma_water_pressure": r(lambda t, i: rating(t, i, "pressure")),
    "espaltherma_energy_today": r(hp_energy, "espaltherma_energy_space_today", "espaltherma_energy_dhw_today",
                                  "espaltherma_energy_standby_today"),
    "espaltherma_heating_energy_today": r(hp_heat, "espaltherma_heating_energy_space_today",
                                          "espaltherma_heating_energy_dhw_today"),
    # the day's conversion, and right under it where its heat went (user, 2026-10-06)
    "espaltherma_dcop": r(lambda t, i: [hp_day_flow(t, i), hp_heat_flow()], "espaltherma_dcop_space",
                          "espaltherma_dcop_dhw"),
    "espaltherma_electrical_power_space": r(hp_split_power, "espaltherma_electrical_power_dhw",
                                            "espaltherma_electrical_power_standby"),
    "espaltherma_heating_power_space": r(hp_split_heat, "espaltherma_heating_power_dhw"),
    "espaltherma_heating_power_before_buh": r(lambda t, i: pair("Heizleistung vor · nach Heizstab", i,
                                                                "espaltherma_heating_power_after_buh", "vor",
                                                                "nach", digits=2, unit="kW",
                                                                a_expr=f"{num(i)} / 1000",
                                                                b_expr=f"{num('espaltherma_heating_power_after_buh')} / 1000",
                                                                delta_text=f"'Heizstab ' + {fixed(f'Math.max(0, {num('espaltherma_heating_power_after_buh')} - {num(i)}) / 1000', 2)} + ' kW'",
                                                                value_unit=" kW"),
                                              "espaltherma_heating_power_after_buh"),
    "espaltherma_cop_space": r(lambda t, i: pair("COP Heizung · Warmwasser", i, "espaltherma_cop_dhw", "Heizung",
                                                 "Warmwasser", digits=2, unit="",
                                                 delta_text=False), "espaltherma_cop_dhw"),
    HP["indoor"]: r(lambda t, i: spark(t, i, "#ff8a65", "K", 1, span=2)),
    "espaltherma_outdoor_air_temp": r(lambda t, i: pair("Außen · zwei Fühler", HP["outdoor"], i, "Außentemperatur",
                                                        "Außenluft", digits=1, unit="K"), HP["outdoor"]),
    "espaltherma_leaving_water_temp_before_buh": r(lambda t, i: pair("Vorlauf vor · nach Heizstab", i, HP["supply"],
                                                                     "vor", "nach", digits=1, unit="K",
                                                                     delta_text=f"'Heizstab ' + {signed(f'{num(HP['supply'])} - {num(i)}', 1, 'K')}"),
                                                   HP["supply"]),
    HP["return"]: r(lambda t, i: spark(t, i, "#64b5f6", "K", 1, span=4)),
    "espaltherma_leaving_water_setpoint": r(lambda t, i: setpoint("Vorlauf gegen Soll", HP["supply"], num(i),
                                                                 g.dash(disp(i)), 20, 50, "#e57373")),
    "espaltherma_room_temp_setpoint": r(lambda t, i: setpoint("Raum gegen Soll", HP["indoor"], num(i), g.dash(disp(i)),
                                                             18, 26, "#ff8a65", tol=0.5)),
    HP["tank_set"]: r(lambda t, i: setpoint("Warmwasser gegen Soll", HP["tank"], num(i), g.dash(disp(i)), 20, 60,
                                            "#ef5350", tol=2)),
    "espaltherma_target_delta_t_heating": r(lambda t, i: pair("Spreizung Soll · Ist", i, None, "Soll", "Ist",
                                                              digits=1, unit="K",
                                                              b_expr=f"({num(HP['supply'])} - {num(HP['return'])})",
                                                              value_unit=" K")),
    "espaltherma_target_discharge_temp": r(lambda t, i: setpoint("Heißgas gegen Soll", HP["hot_gas"], num(i),
                                                                g.dash(disp(i)), 0, 100, "#ba68c8", tol=3,
                                                                valid=f"{num(i)} > 0"),
                                           HP["hot_gas"]),
    HP["pressure"]: r(lambda t, i: spark(t, i, "#ba68c8", "bar", 1, span=2)),
    "espaltherma_error_code": r(lambda t, i: ok_tile(t, i, f"['0', '', 'NULL', 'UNDEF'].includes(items.{i}.state)")),
    # ventilation
    "ventilation_power": r(lambda t, i: spark(t, i, g.VENT_TEAL, "W", 1, span=20)),
    "ventilation_energy_today": r(lambda t, i: compare("Energie heute", i, g.VENT_TEAL)),
    # water meter
    "water_meter_value": r(lambda t, i: [water_today(t, i),
                                         counter("Zählerstand", i, 5, 3, "m³",
                                                 sub=f"='Durchfluss ' + {fixed(WATER_RATE_L, 1)} + ' l/min'")]),
    "water_meter_rate": r(lambda t, i: spark("Durchfluss", i, "#42a5f5", "l/min", 1, span=2, factor=1000,
                                             value_expr=f"={fixed(f'{num(i)} * 1000', 1)} + ' l/min'")),
    "water_meter_timestamp": r(lambda t, i: age_tile("Letzte Ablesung", i, 5)),
    "water_meter_error": r(lambda t, i: ok_tile(t, i, f"['no error', '', 'NULL', 'UNDEF'].includes(items.{i}.state)")),
    # electricity price
    "epex_spot_awattar_total_net": r(lambda t, i: [price_now(t, i), price_mix(t, i)], "epex_spot_awattar_market_gross",
                                     "epex_spot_awattar"),
    "epex_spot_awattar_cheapest_hour": r(lambda t, i: price_strip("Preise der nächsten Stunden", g.PRICE, i,
                                                                  "epex_spot_awattar_priciest_hour"),
                                         "epex_spot_awattar_cheapest", "epex_spot_awattar_priciest_hour",
                                         "epex_spot_awattar_priciest"),
    # plugs (the widgets' placeholders)
    "zzpfx_energy_today": r(plug_energy),
    "zzpfx_energy_total": r(plug_total),
    "zzpfx_voltage": r(socket_volt),
    "zzpfx_current": r(lambda t, i: socket_load(t, i)),
    "zzpfx_power_factor": r(lambda t, i: triangle("Leistungsdreieck", "zzpfx"), "zzpfx_apparent_power",
                            "zzpfx_reactive_power"),
}
for miele in ("miele_washing_machine_wwg360", "miele_tumble_dryer_twc560wp", "miele_dishwasher_g7465"):
    RENDER[miele + "_program_progress"] = (lambda p: (lambda t: (program("Programmablauf", p), {
        p + "_program_elapsed_time", p + "_program_remaining_time", p + "_program_finished_time"})))(miele)
    RENDER[miele + "_delayed_start_time_absolute"] = r(lambda t, i: countdown("Startvorwahl", i))


# ---------------------------------------------------------------- the plug cards as temporary widgets

ORIGINAL_PLUG_CARDS = g.plug_cards


def plug_cards(prefix, icon, color, title="Nous Steckdose", controllable=True, note=None, switch=None,
               electric_prefix=None, electric_title=None, **kw):
    PLUG_PREFIXES.add(prefix)
    cards = ORIGINAL_PLUG_CARDS(prefix, icon, color, title, controllable, note, switch, electric_prefix,
                                electric_title, **kw)
    for c in json_walk(cards):
        if c.get("component") == "widget:plug-card":
            c["component"] = "widget:proposals-plug-card"
            if prefix == "e_car":  # its charge as range (user, 2026-10-06: at 20 kWh/100 km)
                c["config"]["range"] = 20
        elif c.get("component") == "widget:plug-electric-card":
            c["component"] = "widget:proposals-plug-electric-card"
    return cards


def json_walk(v):
    if isinstance(v, dict):
        yield v
        for x in v.values():
            yield from json_walk(x)
    elif isinstance(v, list):
        for x in v:
            yield from json_walk(x)


def range_tile(prefix):
    """What the energy charged today means in kilometres at props.range kWh per 100 km: a road with the car where
    the charge takes it, the total since the meter started below."""
    per = "(Number(props.range) || 20)"
    km = f"({num(prefix + '_energy_today')} / {per} * 100)"
    total_km = f"({num(prefix + '_energy_total')} / {per} * 100)"
    top = f"Math.max(50, Math.ceil({km} * 1.25 / 50) * 50)"
    X = lambda e: f"(12 + 276 * {clamp(f'({e}) / {top}', 0, 1)})"
    car = svg("g", [svg("path", d="M-9 -9 L-5 -16 H6 L10 -9 Z", fill="#26a69a", stroke="#26a69a",
                        **{"fill-opacity": "0.35", "stroke-width": "1.4", "stroke-linejoin": "round"}),
                    svg("rect", x=-16, y=-9.5, width=32, height=9, rx=3, fill="#26a69a"),
                    svg("circle", cx=-9, cy=0, r=3.6, fill="#26a69a", style={"stroke": "var(--f7-card-bg-color, #fff)"},
                        **{"stroke-width": "1.6"}),
                    svg("circle", cx=9, cy=0, r=3.6, fill="#26a69a", style={"stroke": "var(--f7-card-bg-color, #fff)"},
                        **{"stroke-width": "1.6"})],
              transform=f"='translate(' + Math.max(28, {X(km)}).toFixed(1) + ' 30)'")
    ticks = [g.svg_text(f"={X(f'{top} * {k} / 5')}.toFixed(1)", 54, f"=Math.round({top} * {k} / 5) + ({k} === 5 ? ' km' : '')",
                        10, opacity="0.55", anchor="start" if k == 0 else "end" if k == 5 else "middle") for k in range(6)]
    road = svg("svg", [svg("line", x1=12, y1=38, x2=288, y2=38, stroke="currentColor",
                           **{"stroke-opacity": "0.14", "stroke-width": "6", "stroke-linecap": "round"}),
                       svg("line", x1=12, y1=38, x2=f"={X(km)}.toFixed(1)", y2=38, stroke="#26a69a",
                           **{"stroke-width": "6", "stroke-linecap": "round"}),
                       svg("line", x1=16, y1=38, x2=f"=Math.max(16, {X(km)} - 4).toFixed(1)", y2=38,
                           style={"stroke": "var(--f7-card-bg-color, #fff)"},
                           **{"stroke-width": "1.5", "stroke-dasharray": "6 6"}),
                       car, *ticks],
               viewBox="0 0 300 58", style={"display": "block", "width": "100%", "height": "auto", "max-width": "460px",
                                            "margin-top": "4px"})
    return tile([head("Reichweite der Ladung heute", chip(f"={per} + ' kWh / 100 km'")),
                 value(f"='≈ ' + Math.round({km}) + ' km'", "#26a69a"), road,
                 label(f"='seit Zählerbeginn ' + {fixed(num(prefix + '_energy_total'), 0)} + ' kWh ≈ ' + "
                       f"Math.round({total_km}).toLocaleString('de-DE') + ' km'", **{**SUB, "margin-top": "4px"})],
                wide=True, visible="=Number(props.range) > 0")


def plug_widgets(now):
    ph = g.PLUG_PLACEHOLDERS
    plug_card = g.plug_now_card(ph["prefix"], ph["icon"], ph["color"], ph["title"], ph["note"], ph["switch"])
    for c in json_walk(plug_card):  # the grid of energy today and total gets the range tile
        if c.get("component") == "div" and "grid-template-columns" in c.get("config", {}).get("style", {}):
            c["slots"]["default"].append(range_tile(ph["prefix"]))
            break
    built = {"proposals-plug-card": (plug_card, g.PLUG_PARAMS + [g.param("range", "Range", "kWh per 100 km; set for a "
                                                                          "car, shows the range of today's charge",
                                                                          "DECIMAL")]),
             "proposals-plug-electric-card": (g.plug_electric_card(ph["prefix"], ph["title"]),
                                              [g.PREFIX, g.param("title", "Title", "Card title", default="Elektrisch")])}
    out = {}
    for uid, (card_, params) in built.items():
        tree = g.own_time_axes(g.templated(g.plots_below_controls(card_)))
        g.germanize(tree, g.MISSING_DE)
        text = json.dumps(tree)
        assert not any(tok in text for tok, _ in g.PLACEHOLDER_JS), uid
        out[uid] = {"uid": uid, "tags": ["generated", "proposals"], "props": {"parameters": params, "parameterGroups": []},
                    "timestamp": g.timestamp(now), "component": tree["component"], "config": tree["config"],
                    "slots": tree.get("slots", {})}
    return out


# ---------------------------------------------------------------- layouts of the proposals


def pv_blocks():
    """The PV page as the generator builds it (photovoltaics_blocks), laid out anew (user, 2026-10-06): strings and grid
    top right beside Jetzt, the yield per day under them filling the rest of that column; below the day's power as
    high as the inverter beside it, so neither side stands with empty card space."""
    PV = g.PV
    now = [g.hero("material:solar_power", "#ffb300", "Eingangsleistung", g.kwc(PV),
                  picture=g.node_icon("pv", "#ffb300", g.flowing(num(PV), 10), power=num(PV))),
           wide_grid([g.vtile("Wirkleistung", "huawei_inverter_active_power", g.kwc("huawei_inverter_active_power")),
                        g.vtile("Spitze heute", "huawei_inverter_active_peak_of_current_day",
                                g.kwc("huawei_inverter_active_peak_of_current_day")),
                        g.vtile("Blindleistung", "huawei_inverter_reactive_power"),
                        g.vtile("Wirkungsgrad", "huawei_inverter_efficiency"),
                        g.vtile("Energie heute", "huawei_inverter_e_day", color="#ffb300"),
                        g.vtile("Eigenverbrauch heute", "photovoltaics_own_ec_day", color="#43a047"),
                        g.vtile("Energie gesamt", "huawei_inverter_e_total")])]
    chart_ = g.stacked_chart([("Eingang", [g.area("Eingang", PV, "#ffb300")], g.value_axis("W")),
                              ("Wirkleistung", [g.area("Wirkleistung", "huawei_inverter_active_power", "#5c6bc0")],
                               g.value_axis("W")),
                              ("String PV1", [g.area("PV1", "huawei_inverter_pv1_power", "#ffca28")], g.value_axis("W")),
                              ("String PV2", [g.area("PV2", "huawei_inverter_pv2_power", "#ff8f00")], g.value_axis("W"))],
                             470)  # as high as the inverter's card beside it
    strings_ = phase_table(["PV1", "PV2"], [("Leistung", ["huawei_inverter_pv1_power", "huawei_inverter_pv2_power"]),
                                              ("Spannung", ["huawei_inverter_pv1_voltage", "huawei_inverter_pv2_voltage"]),
                                              ("Strom", ["huawei_inverter_pv1_current", "huawei_inverter_pv2_current"])])
    grid_ = phase_table(["A", "B", "C"], [("Spannung", [f"huawei_inverter_phase_{x}_voltage" for x in "abc"]),
                                             ("Strom", [f"huawei_inverter_phase_{x}_current" for x in "abc"])])
    inverter = wide_grid([g.vtile("Gerätestatus", "huawei_inverter_device_status"),
                            g.vtile("Startzeit", "huawei_inverter_startup_time"),
                            g.vtile("Abschaltzeit", "huawei_inverter_shutdown_time"),
                            g.vtile("Innentemperatur", "huawei_inverter_internal_temperature"),
                            g.vtile("Fehlercode", "huawei_inverter_error_code"),
                            g.vtile("Optimierer online", "huawei_inverter_optimizers_online"),
                            g.vtile("Optimierer gesamt", "huawei_inverter_optimizers_total")])
    days = g.month_bars("PV-Ertrag", "energy_daily_pv", "#ffb300")
    days["config"]["height"] = "100%"
    return [g.two(g.card("Jetzt", now), g.stack(g.card("Strings (DC)", [strings_]), g.card("Netz (AC)", [grid_]),
                                                g.card("Ertrag pro Tag", [g.fill_chart(days, "180px")], fill=True))),
            g.two(g.card("Leistung heute", [chart_]), g.card("Wechselrichter", [inverter]))]


def storage_blocks():
    """The battery page as the generator builds it (energy_storage_blocks), laid out anew (user, 2026-10-06): the
    controls beside Jetzt, the storage over the day's power beside unit 1, the chart taking the height unit 1
    leaves, so no card stands with empty space."""
    BATT, SOC, GREEN_ = g.BATT, g.SOC, g.BATTERY_GREEN
    batt_state = f"{num(BATT)} < -10 ? 'lädt' : {num(BATT)} > 10 ? 'entlädt' : 'ruht'"
    charging, at_work, dur, clock = g.battery_eta_parts()
    soc = f"Math.max(0, Math.min(100, {num(SOC)}))"
    icon = g.node_icon("battery", GREEN_, g.flowing(num(BATT), 10), share=f"{num(SOC)} / 100", soc=num(SOC))
    now = [g.hero("material:battery_charging_full", GREEN_, "Ladestand", f"={disp(SOC)}",
                  [g.chips(g.chip(f"={fixed(f'{num(BATT)} / 1000', 3)} + ' kW · ' + ({batt_state})", GREEN_),
                           g.timer_chip(f"={dur}", f"={at_work}", tint=GREEN_)),
                   label(f"='Ø 5 min · ' + {fixed(f'{g.BATT_5MIN} / 1000', 2)} + ' kW'", **{"font-size": "14px"}),
                   label(f"=({charging} ? 'voll ca. ' : 'leer ca. ') + {clock}", f"={at_work}",
                         **{"font-size": "22px", "font-weight": "700"})], picture=icon),
           g.bar(soc, GREEN_,
                 f"={fixed(f'Math.max(0, {soc} - {g.BATT_FLOOR}) * {g.BATT_KWH_PER_PERCENT}', 2)} + ' kWh nutzbar'",
                 f"={fixed(f'(100 - {soc}) * {g.BATT_KWH_PER_PERCENT}', 2)} + ' kWh frei'"),
           wide_grid([g.vtile("Leistung", BATT, g.kw_signed(BATT)),
                      g.vtile("Status", "huawei_inverter_energy_storage_running_status"),
                      g.vtile("Geladen heute", "huawei_inverter_energy_storage_day_charge"),
                      g.vtile("Entladen heute", "huawei_inverter_energy_storage_day_discharge")])]
    control_items = [
        comp("oh-label-item", {"action": "options", "actionItem": "huawei_inverter_energy_storage_forcible_charge_discharge",
                               "icon": "material:battery_charging_full",
                               "item": "huawei_inverter_energy_storage_forcible_charge_discharge",
                               "title": "Zwangsladen/-entladen"}),
        comp("oh-label-item", {**g.item_modal("huawei_inverter_energy_storage_remaining_charge_discharge_time",
                                              "Restzeit Laden/Entladen"),
                               "icon": "material:hourglass_bottom",
                               "item": "huawei_inverter_energy_storage_remaining_charge_discharge_time",
                               "title": "Restzeit Laden/Entladen"})]
    controls = [comp("f7-list", {"style": {"margin": "0 0 8px"}}, default=control_items),
                g.controls_box(g.battery_power_slider("huawei_inverter_energy_storage_forcible_charge_power",
                                                      "Zwangsladeleistung", "beim Zwangsladen"),
                               g.battery_power_slider("huawei_inverter_energy_storage_forcible_discharge_power",
                                                      "Zwangsentladeleistung", "beim Zwangsentladen"),
                               g.battery_period_slider()),
                wide_grid([g.vtile("Zwangsladestatus", "huawei_inverter_energy_storage_forcible_status")])]
    totals = wide_grid([g.vtile("Ladestand", SOC), g.vtile("Geladen gesamt", "huawei_inverter_energy_storage_total_charge"),
                        g.vtile("Entladen gesamt", "huawei_inverter_energy_storage_total_discharge"),
                        g.vtile("Busspannung", "huawei_inverter_energy_storage_bus_voltage"),
                        g.vtile("Busstrom", "huawei_inverter_energy_storage_bus_current")])
    u = "huawei_inverter_energy_storage_unit_1_"
    unit = wide_grid([g.vtile("Status", u + "running_status"), g.vtile("Ladestand", u + "soc"),
                      g.vtile("Leistung", u + "power"), g.vtile("Geladen heute", u + "day_charge"),
                      g.vtile("Entladen heute", u + "day_discharge"), g.vtile("Geladen gesamt", u + "total_charge"),
                      g.vtile("Entladen gesamt", u + "total_discharge"), g.vtile("Busspannung", u + "bus_voltage"),
                      g.vtile("Busstrom", u + "bus_current"), g.vtile("Temperatur", u + "temperature")])
    chart_ = g.stacked_chart([((("Leistung", "#7cb342"), ("Ladestand", "#2e7d32")),
                               [g.area("Leistung", BATT, "#7cb342"), g.line("Ladestand", SOC, "#2e7d32", y=1)],
                               [g.value_axis("W"), g.value_axis("%", min=0, max=100)])], 400)
    return [g.two(g.card("Jetzt", now), g.card("Steuerung", controls)),
            g.two(g.stack(g.card("Speicher", [totals]),
                          g.card("Leistung heute", [g.fill_stacked(chart_, "250px")], fill=True)),
                  g.card("Einheit 1", [unit]))]


def cols(two_):
    """The two cards of a two() block."""
    return [c["slots"]["default"][0] for c in two_["slots"]["default"][0]["slots"]["default"]]


def unstacked(card_):
    """A card taken out of a stack(), with a card's own height again."""
    card_ = copy.deepcopy(card_)
    card_["config"]["style"] = {"height": "calc(100% - 2 * var(--f7-card-margin-vertical))"}
    return card_


def ac_blocks():
    """The air conditioner's page as the generator builds it, laid out anew in its two-column grid (user,
    2026-10-06): the controls beside Jetzt, the day's operation beside the plug card over the electrical values
    (its chart as high as they are), the plug's power of the day beside the energy per day."""
    built = g.DEVICE_PAGES["air_conditioning"]()  # its plots already below their controls
    controls, right = cols(built[0])
    now, _ = right["slots"]["default"]
    plug, power = cols(built[1])
    days, electric = cols(built[2])
    temps = g.stacked_chart([
        ((("Leistung", g.AC_BLUE), ("Verdichter", "#78909c")),
         [g.area("Leistung", "air_conditioning_unit_power", g.AC_BLUE),
          g.line("Verdichter", "faikout_perfera_compressor_frequency", "#78909c", y=1)],
         [g.value_axis("W", min=0), g.value_axis("Hz", min=0, minInterval=1)]),
        ((("Raum", "#fb8c00"), ("Außen", "#26a69a")),
         [g.line("Raum", "faikout_perfera_temperature", "#fb8c00"),
          g.line("Außen", "faikout_perfera_outdoor_temperature", "#26a69a")], g.span_axis("°C")),
        ("Flüssigkeit", [g.line("Flüssigkeit", "faikout_perfera_liquid_temperature", "#29b6f6")], g.span_axis("°C"))],
        720)  # as high as the plug card over the electrical values beside it
    return [g.two(controls, unstacked(now)),
            g.two(g.card("Betrieb heute", [temps]), g.widget_stack(plug, electric)),
            g.two(power, days)]


def hp_blocks():
    """The heat pump's page as the generator builds it, re-ordered in its two-column grid (user, 2026-10-06): Jetzt
    beside the controls and the operation, then the cards of values (today's energies with the conversion beside
    the split and the plug's electrical values, temperatures beside setpoints, the plug beside the refrigerant, the
    modes), the full charts below."""
    b = g.DEVICE_PAGES["heatpump"]()
    controls, now = cols(b[0])
    today, split_ = cols(b[5])
    temps, setpoints = cols(b[6])
    modes = b[7]
    refrigerant, operation = cols(b[8])
    plug, power = cols(b[9])
    days, electric = cols(b[10])
    # paired by height, so no card stands with much empty space (measured 2026-10-06)
    return [g.two(g.stack(controls, operation), now),
            g.two(today, g.widget_stack(split_, electric)),
            g.two(temps, setpoints),
            g.two(plug, refrigerant),
            modes,
            b[1], b[2], b[3], b[4],
            g.two(power, days)]


LAYOUTS = {"photovoltaics": pv_blocks, "energy_storage": storage_blocks, "air_conditioning": ac_blocks,
           "heatpump": hp_blocks}


# ---------------------------------------------------------------- pages


def page_labels():
    d = json.load(open("/var/lib/openhab/jsondb/uicomponents_ui_page.json"))
    return {uid: v["value"]["config"].get("label", uid) for uid, v in d.items()}


def solar_noon_utc():
    """The solar noon at openHAB's location in minutes after midnight UTC, without the equation of time (a few
    minutes), from its longitude."""
    req = urllib.request.Request(REST + "/services/org.openhab.i18n/config",
                                 headers={"Authorization": "Bearer " + token()})
    with urllib.request.urlopen(req) as r_:
        location = json.load(r_).get("location", "")
    lon = float(location.split(",")[1])
    return round(720 - 4 * lon)


def token():
    return open(os.path.expanduser("~/.openhab_token")).read().strip()


def build(outdir):
    global SOLAR_NOON
    SOLAR_NOON = solar_noon_utc()
    now = datetime.datetime.now()
    for name, fn in (("wide_grid", wide_grid), ("phase_table", phase_table), ("plug_cards", plug_cards)):
        ns[name] = fn
    labels = page_labels()
    pages, links = {}, []
    for uid, builder in ns["DEVICE_PAGES"].items():
        if uid == "weather":  # no value tiles
            continue
        SEEN.clear()
        blocks = g.plots_below_controls(LAYOUTS[uid]()) if uid in LAYOUTS else builder()
        puid = "proposals_" + uid
        config = {"label": "Vorschlag: " + labels.get(uid, uid), "sidebar": False,
                  "style": g.WIDE_POPUP_MARK, "stylesheet": g.WIDE_POPUP}
        pages[puid] = g.layout_page(puid, config, blocks, now)["value"]
        links.append((labels.get(uid, uid), puid))
    widgets = plug_widgets(now)
    # the list of all proposals
    rows = [comp("oh-label-item", {"title": name, "action": "navigate", "actionPage": f"page:{puid}",
                                   "icon": "material:auto_awesome", "after": f"/page/{puid}"}) for name, puid in links]
    note = g.label("Jede Geräteseite noch einmal, ihre Werte jeweils in der Form, die am besten passt "
                   "(Varianten der Entwurfsfläche). Vergleiche und Verläufe kommen aus der Regel proposals_history "
                   "(alle 10 Minuten).", **{"padding": "4px 16px 12px", "font-size": "14px", "opacity": "0.8"})
    index = g.card("Vorschläge: Werte auf den Geräteseiten",
                   [note, comp("f7-list", {"style": {"margin": "0 0 8px"}}, default=rows)])
    pages["proposals"] = g.layout_page("proposals", {"label": "Vorschläge", "sidebar": False},
                                       [g.block(g.row(g.full(index)))], now)["value"]
    # the tiles' history: plug items found while the pages were built, the placeholders resolved
    os.makedirs(outdir, exist_ok=True)
    json.dump({"ui:page": pages, "ui:widget": widgets}, open(os.path.join(outdir, "body.json"), "w"),
              ensure_ascii=False)
    json.dump({"ui:page": {u: None for u in pages}, "ui:widget": {u: None for u in widgets}},
              open(os.path.join(outdir, "remove.json"), "w"))
    json.dump({k: v for k, v in sorted(TRACK.items()) if not k.startswith("zzpfx")},
              open(os.path.join(outdir, "track.json"), "w"), indent=1)
    print(len(pages), "pages,", len(widgets), "widgets,", len(TRACK), "tracked items ->", outdir)


# ---------------------------------------------------------------- the history rule

RULE_SCRIPT = """// TEMPORARY (proposals of 2026-10-06): the history the value tile proposals (pages proposals_*) show, as JSON in
// proposals_history: per item y = its value yesterday at this time, a = the mean of the last 7 days at this time,
// h = its value some hours ago, s = 24 hourly means up to now, f = [unix, value] of the hours ahead
const TRACK = __TRACK__;
const svc = 'influxdb';
const now = time.toZDT();
const hour0 = now.withMinute(0).withSecond(0).withNano(0);
const store = cache.private.get('hourly', () => ({}));
const val = (s) => (s === null || s === undefined || s.numericState === null || s.numericState === undefined) ?
  null : Math.round(s.numericState * 1000) / 1000;
const out = {};
for (const name of Object.keys(TRACK)) {
  const want = TRACK[name];
  let p;
  try { p = items.getItem(name).persistence; } catch (e) { continue; }
  const r = {};
  try {
    if (want.c) {
      r.y = val(p.persistedState(now.minusDays(1), svc));
      const xs = [];
      for (let k = 1; k <= 7; k++) {
        const v = val(p.persistedState(now.minusDays(k), svc));
        if (v !== null) xs.push(v);
      }
      r.a = xs.length ? Math.round(xs.reduce((a, b) => a + b, 0) / xs.length * 1000) / 1000 : null;
    }
    if (want.t) r.h = val(p.persistedState(now.minusHours(want.t), svc));
    if (want.s) {
      const own = store[name] || {};
      const s = [];
      for (let i = 23; i >= 0; i--) {
        const begin = hour0.minusHours(i);
        const key = String(begin.toEpochSecond());
        let v = own[key];
        if (v === undefined || i === 0) {
          v = val(p.averageBetween(begin, i === 0 ? now : begin.plusHours(1), svc));
          if (i !== 0) own[key] = v;
        }
        s.push(v);
      }
      const oldest = hour0.minusHours(24).toEpochSecond();
      for (const k of Object.keys(own)) if (Number(k) < oldest) delete own[k];
      store[name] = own;
      r.s = s;
    }
    if (want.f) {
      const rows = p.getAllStatesBetween(hour0.minusHours(want.f[0]), hour0.plusHours(want.f[1]), svc);
      r.f = rows.map((x) => [x.timestamp.toEpochSecond(), Math.round(x.numericState * 10000) / 10000]);
    }
  } catch (e) {
    console.warn('proposals_history: ' + name + ': ' + e);
  }
  out[name] = r;
}
items.getItem('proposals_history').postUpdate(JSON.stringify(out));
"""


def call(method, path, body=None):
    req = urllib.request.Request(REST + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + token(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r_:
            return r_.status
    except urllib.error.HTTPError as e:
        return e.code


def history(action, track_file):
    item = {"type": "String", "name": HIST_ITEM, "label": "Vorschläge: Verlauf (temporär)", "category": "",
            "tags": [], "groupNames": []}
    if action == "remove":
        print("rule DELETE", call("DELETE", f"/rules/{RULE_UID}"))
        print("item DELETE", call("DELETE", f"/items/{HIST_ITEM}"))
        return
    tracked = json.load(open(track_file))
    script = RULE_SCRIPT.replace("__TRACK__", json.dumps(tracked, separators=(",", ":")))
    rule = {"uid": RULE_UID, "name": "Vorschläge: Verlauf (temporär)",
            "description": "TEMPORÄR für die Vorschlagsseiten proposals_* (2026-10-06): schreibt alle 10 Minuten "
                           "Vergleichswerte (gestern, Ø 7 Tage), Stundenmittel der letzten 24 h und die Preise der "
                           "nächsten Stunden als JSON in proposals_history. Mit den Vorschlägen wieder löschen.",
            "tags": ["proposals"],
            "triggers": [{"id": "1", "type": "timer.GenericCronTrigger",
                          "configuration": {"cronExpression": "0 0/10 * * * ? *"}}],
            "conditions": [],
            "actions": [{"id": "2", "type": "script.ScriptAction",
                         "configuration": {"type": "application/javascript", "script": script}}]}
    print(f"item {HIST_ITEM}:", "exists" if call("GET", f"/items/{HIST_ITEM}") == 200 else "missing")
    exists = call("GET", f"/rules/{RULE_UID}") == 200
    print(f"rule {RULE_UID}:", "exists" if exists else "missing", f"({len(tracked)} items tracked)")
    if action == "apply":
        print("item PUT", call("PUT", f"/items/{HIST_ITEM}", item))
        print("rule", ("PUT " + str(call("PUT", f"/rules/{RULE_UID}", rule))) if exists else
              ("POST " + str(call("POST", "/rules", rule))))
        print("run now:", call("POST", f"/rules/{RULE_UID}/runnow", {}))


if __name__ == "__main__":
    if MODE[:1] == ["build"]:
        build(MODE[1])
    elif MODE[:1] == ["history"]:
        history(MODE[1], MODE[2] if len(MODE) > 2 else None)
    else:
        sys.exit(__doc__)
