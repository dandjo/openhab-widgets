#!/usr/bin/env python3
"""Design proposals for the overview (user, 2026-10-08: "bau mir für die Übersicht ein paar alternative Designs auf
Vorschlagsseiten, damit die ganzen Widgets harmonischer wirken, fast wie aus einem Guss"): every widget the overview
places is copied once as harmony-<uid>, its surfaces, radii, pills, watermarks, large figures and accent bars turned
into CSS custom properties whose fallbacks are today's values (an unset token renders exactly as the overview does);
each card also carries its icon and colour (--h-icon, --h-hue). Each proposal page is the overview placing these
copies, with a stylesheet that sets the tokens and restyles the card shells: one design language per page. The
generator and the live overview stay untouched; its next run removes the copies (tagged generated) and remove.json
removes the pages.

Usage: proposals_harmony.py PAGES.json WIDGETS.json OUTDIR   (the live ui:page / ui:widget lists, e.g. from the REST API)
writes OUTDIR/body.json (for ui_put.py) and OUTDIR/remove.json."""
import copy
import json
import os
import re
import sys

PAGES, WIDGETS, OUT = sys.argv[1:4]
P = {c["uid"]: c for c in json.load(open(PAGES))}
W = {c["uid"]: c for c in json.load(open(WIDGETS))}
PREFIX = "harmony-"
GREY_TILE = "rgba(127, 127, 127, 0.08)"

# each card's icon (Material) and colour; the colour families: energy amber, heat red-orange, household blue,
# weather and climate light blue, market green
CARDS = {
    "weather-card": ("partly_cloudy_day", "#29b6f6"),
    "energy-flow-card": ("bolt", "#ffb300"),
    "switches-card": ("toggle_on", "#ffb300"),
    "appliances-card": ("local_laundry_service", "#42a5f5"),
    "heating-card": ("local_fire_department", "#ff7043"),
    "heatpump-card": ("cyclone", "#ff7043"),
    "consumption-card": ("donut_large", "#ffb300"),
    "energy-days-card": ("bar_chart", "#ffb300"),
    "electricity-price-card": ("euro", "#66bb6a"),
    "temperatures-card": ("thermostat", "#29b6f6"),
    "pv-days-card": ("solar_power", "#ffb300"),
}


def children(c):
    for slot in (c.get("slots") or {}).values():
        for x in slot:
            if isinstance(x, dict):
                yield x


def walk(c):
    yield c
    for x in children(c):
        yield from walk(x)


def closure(root):
    """The widgets placed (not opened as popups) below a component, transitively."""
    seen, todo = set(), [root]
    while todo:
        for c in walk(todo.pop()):
            comp = c.get("component", "")
            if comp.startswith("widget:") and comp[7:] not in seen and comp[7:] in W:
                seen.add(comp[7:])
                todo.append(W[comp[7:]])
    return seen


def var(name, fallback):
    """A token with today's value as fallback: an expression stays an expression."""
    if isinstance(fallback, str) and fallback.startswith("="):
        return f"='var({name}, ' + ({fallback[1:]}) + ')'"
    return f"var({name}, {fallback})"


def px(v):
    return float(v[:-2]) if isinstance(v, str) and re.fullmatch(r"[\d.]+px", v) else None


def tokenize(c, uid):
    cfg = c.setdefault("config", {})
    comp = c.get("component", "")
    st = cfg.get("style")
    if comp.startswith("widget:") and comp[7:] in COPIED:
        c["component"] = f"widget:{PREFIX}{comp[7:]}"
    if comp == "rect" and str(cfg.get("rx")) in ("12", "12.0") and isinstance(cfg.get("fill"), str) \
            and GREY_TILE in cfg["fill"]:
        # the heat pump drawing's tiles: idle fill and edge as tokens, the active tint stays
        st = cfg.setdefault("style", {}) if isinstance(cfg.get("style"), dict) else cfg.setdefault("style", {})
        st["fill"] = cfg["fill"].replace(f"'{GREY_TILE}'", f"'var(--h-svg-tile-bg, {GREY_TILE})'")
        if isinstance(cfg.get("stroke"), str):
            st["stroke"] = cfg["stroke"].replace("'none'", "'var(--h-svg-tile-edge, none)'")
        st["rx"] = "var(--h-svg-tile-radius, 12px)"
        st["ry"] = "var(--h-svg-tile-radius, 12px)"
        return
    if comp == "rect" and _num(cfg.get("height")) and _num(cfg.get("rx")) == _num(cfg.get("height")) / 2 <= 10:
        # a pill drawn in SVG (the energy flow's shares, the comparisons under its tiles and the COP tiles): its
        # corner as a token, one for the small ones (13 high) and one for the large (18 high)
        h, rx = _num(cfg["height"]), _num(cfg["rx"])
        name = "--h-svg-pill-radius" if h >= 16 else "--h-svg-pill-radius-s"
        st = cfg.setdefault("style", {}) if isinstance(cfg.get("style"), dict) else cfg.setdefault("style", {})
        st["rx"] = st["ry"] = f"var({name}, {rx:g}px)"
        return
    if not isinstance(st, dict):
        return
    bg = st.get("background")
    tile = isinstance(bg, str) and GREY_TILE in bg
    if tile:
        st["background"] = bg.replace(GREY_TILE, f"var(--h-tile-bg, {GREY_TILE})")
        sh = st.get("box-shadow")
        if sh is None:
            st["box-shadow"] = "var(--h-tile-edge, none)"
        elif isinstance(sh, str) and sh.startswith("=") and "'none'" in sh:
            st["box-shadow"] = sh.replace("'none'", "'var(--h-tile-edge, none)'")
    rad = st.get("border-radius")
    pill = st.get("white-space") == "nowrap" and rad in ("9px", "10px") and ("background" in st or "border" in st)
    if uid == "weather-card" and rad == "14px" and "background" in st:
        st["border-radius"] = var("--h-pill-radius", rad)  # the warning's pill
    elif rad in ("12px", "0.8571em"):
        st["border-radius"] = var("--h-tile-radius", rad)
    elif pill:
        st["border-radius"] = var("--h-pill-radius", rad)
    if comp == "oh-icon" and st.get("opacity") == "0.16" and st.get("position") == "absolute":
        st["opacity"] = "var(--h-watermark, 0.16)"
    if comp == "Label":
        size = px(st.get("font-size"))
        if size and size >= 22:  # a card's main figure
            st["font-size"] = var("--h-hero-fs", st["font-size"])
            if "line-height" in st:
                st["line-height"] = var("--h-hero-lh", st["line-height"])
            if "color" in st:
                st["color"] = var("--h-hero-color", st["color"])
            st["letter-spacing"] = "var(--h-hero-ls, normal)"
            st["white-space"] = var("--h-hero-ws", st.get("white-space", "normal"))
        if uid == "value-tile" and st.get("color") == "=props.color || ''":
            st["color"] = "='var(--h-value-color, ' + (props.color || 'inherit') + ')'"
    bl = st.get("border-left")
    if isinstance(bl, str) and re.fullmatch(r"4px solid #[0-9a-f]{6}", bl):
        col = bl.split()[-1]
        st.update({"border-left": f"var(--h-accent-border-w, 4px) solid {col}",
                   "box-shadow": f"inset var(--h-accent-inset, 0px) 0 0 {col}",
                   "background": "var(--h-accent-bg, transparent)",
                   "border-radius": "var(--h-accent-radius, 0)", "--h-accent": col})
    if st.get("display") == "grid" and st.get("gap") in ("8px", "10px"):
        st["gap"] = var("--h-gap", st["gap"])


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def copy_widget(uid):
    w = copy.deepcopy(W[uid])
    w["uid"] = PREFIX + uid
    w["tags"] = sorted(set(w.get("tags", [])) | {"generated", "proposal"})
    w.pop("timestamp", None)
    w.pop("editable", None)
    for c in walk(w):
        tokenize(c, uid)
    if uid in CARDS:
        icon, hue = CARDS[uid]
        st = w.setdefault("config", {}).setdefault("style", {})
        st.update({"--h-icon": f"'{icon}'", "--h-hue": hue})
    kpi(w, uid)
    return w


# a card's head figures as one tile (tokens unset: as today)
KPI = {"background": "var(--h-kpi-bg, transparent)", "border-radius": "var(--h-tile-radius, 0)",
       "box-shadow": "var(--h-kpi-edge, none)"}


def kpi(w, uid):
    content = w.get("slots", {}).get("content", [])
    if uid == "electricity-price-card":
        # the price and its cheapest/dearest line, wrapped
        head, line = content[0], content[1]
        head["config"]["style"]["padding"] = "var(--h-kpi-inner, 0 16px)"
        line["config"]["style"]["padding"] = "var(--h-kpi-inner, 0 16px)"
        line["config"]["style"]["margin-bottom"] = "var(--h-kpi-line-mb, 12px)"
        wrap = {"component": "div", "config": {"style": {**KPI, "margin": "var(--h-kpi-margin, 0)",
                                                         "padding": "var(--h-kpi-pad, 0)"}},
                "slots": {"default": [head, line]}}
        content[0:2] = [wrap]
    elif uid == "consumption-card":
        head = content[0]["slots"]["default"][0]
        head["config"]["style"].update({**KPI, "padding": "var(--h-kpi-pad, 0)"})


# ---------------------------------------------------------------- the design languages

HEAD_ICON = """content: var(--h-icon, none); font-family: 'Material Icons'; font-weight: normal; font-style: normal;
  font-feature-settings: 'liga'; -webkit-font-smoothing: antialiased; text-transform: none; letter-spacing: normal;
  white-space: nowrap; direction: ltr; flex: 0 0 auto; display: inline-flex; align-items: center;
  justify-content: center;"""

COMMON = """
.card-header { justify-content: flex-start; min-height: 0; }
.card-header::after { display: none !important; }
.oh-chart-container > .menu .menu-item { background: color-mix(in srgb, var(--f7-text-color) 8%, transparent);
  color: inherit; border-radius: var(--h-pill-radius, 999px); min-width: 32px; }
.oh-chart-container > .menu .menu-item + .menu-item { margin-left: 6px; }
.segmented-strong { border-radius: var(--h-pill-radius, 999px);
  background: color-mix(in srgb, var(--f7-text-color) 8%, transparent); }
.segmented-strong .button { border-radius: calc(var(--h-pill-radius, 999px) - 2px) !important; }
"""

# phones: the large figures one step smaller and the head tiles narrower inside, so the heads keep their lines
PHONE = """
@media (max-width: 599px) { :host { --h-hero-fs: 26px; --h-hero-lh: 32px; --h-kpi-pad: 10px 8px; } }
"""

KPI_TILE = """--h-hero-ws: nowrap; --h-kpi-margin: 2px 16px 14px; --h-kpi-pad: 12px 14px; --h-kpi-inner: 0; --h-kpi-line-mb: 0;"""

VARIANTS = {
    # one surface for every figure: cards with a round icon head, every value in a tile of one kind
    "a": ("Kacheln", "f7:square_grid_2x2", """
:host { --h-tile-bg: color-mix(in srgb, var(--f7-text-color) 6%, transparent); --h-tile-radius: 16px;
  --h-svg-tile-radius: 16px; --h-svg-tile-bg: color-mix(in srgb, var(--f7-text-color) 6%, transparent);
  --h-pill-radius: 999px; --h-watermark: 0; --h-hero-fs: 28px; --h-hero-lh: 34px; --h-gap: 10px;
  --h-accent-border-w: 0px; --h-accent-inset: 4px; --h-accent-radius: 16px;
  --h-accent-bg: color-mix(in srgb, var(--f7-text-color) 6%, transparent);
  --h-kpi-bg: color-mix(in srgb, var(--f7-text-color) 6%, transparent); """ + KPI_TILE + """ }
.card { border-radius: 24px; box-shadow: none; }
.card-header { font-size: 15px; font-weight: 600; padding: 16px 18px 8px; gap: 10px; }
"""),
    # little ink: hairlines instead of surfaces, quiet titles, values in the text colour, no watermarks
    "b": ("Ruhig", "f7:circle_lefthalf_fill", """
:host { --h-tile-bg: transparent; --h-tile-radius: 12px; --h-svg-tile-radius: 12px;
  --h-tile-edge: inset 0 0 0 1px color-mix(in srgb, var(--f7-text-color) 11%, transparent);
  --h-svg-tile-bg: transparent; --h-svg-tile-edge: color-mix(in srgb, var(--f7-text-color) 14%, transparent);
  --h-pill-radius: 6px; --h-svg-pill-radius: 6px; --h-svg-pill-radius-s: 4px; --h-watermark: 0; --h-value-color: inherit; --h-hero-fs: 28px; --h-hero-lh: 34px;
  --h-hero-ls: -0.01em; --h-accent-border-w: 2px; }
.card { border-radius: 14px; box-shadow: 0 0 0 1px color-mix(in srgb, var(--f7-text-color) 8%, transparent); }
.card-header { font-size: 13px; font-weight: 600; padding: 16px 16px 4px; opacity: 0.6; letter-spacing: 0.02em; }
"""),
    # colour says the topic: energy amber, heat red-orange, household blue, climate light blue, market green
    "c": ("Farbfamilien", "f7:paintbrush", """
:host { --h-surface: var(--f7-card-bg-color); --h-tile-radius: 16px; --h-svg-tile-radius: 16px;
  --h-pill-radius: 999px; --h-watermark: 0.14; --h-hero-fs: 28px; --h-hero-lh: 34px; --h-gap: 10px;
  --h-accent-border-w: 0px; --h-accent-inset: 4px; --h-accent-radius: 16px; """ + KPI_TILE + """ }
.card { --f7-card-bg-color: color-mix(in srgb, var(--h-hue, #9e9e9e) 5%, var(--h-surface));
  --h-tile-bg: color-mix(in srgb, var(--h-hue, #9e9e9e) 9%, transparent);
  --h-svg-tile-bg: color-mix(in srgb, var(--h-hue, #9e9e9e) 9%, transparent);
  --h-accent-bg: color-mix(in srgb, var(--h-hue, #9e9e9e) 9%, transparent);
  --h-kpi-bg: color-mix(in srgb, var(--h-hue, #9e9e9e) 9%, transparent);
  background: var(--f7-card-bg-color); border-radius: 24px;
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--h-hue, #9e9e9e) 20%, transparent); }
.card-header { font-size: 15px; font-weight: 600; padding: 16px 18px 8px; gap: 10px;
  color: color-mix(in srgb, var(--h-hue) 60%, var(--f7-text-color)); }
.card-header::before { """ + HEAD_ICON + """ font-size: 17px; width: 30px; height: 30px; border-radius: 50%;
  color: var(--h-surface); background: var(--h-hue); }
"""),
    # no boxes around boxes: sections on the page ground under large titles, the tiles the only surfaces
    "d": ("Offen", "f7:rectangle_split_3x1", """
:host { --h-surface: var(--f7-card-bg-color); --h-tile-bg: var(--h-surface); --h-tile-radius: 18px;
  --h-svg-tile-radius: 16px; --h-svg-tile-bg: var(--h-surface); --h-pill-radius: 999px; --h-watermark: 0.12;
  --h-hero-fs: 34px; --h-hero-lh: 40px; --h-hero-ls: -0.02em; --h-gap: 12px; --h-accent-border-w: 0px;
  --h-accent-inset: 0px; --h-accent-bg: var(--h-surface); --h-accent-radius: 18px;
  --h-kpi-bg: var(--h-surface); """ + KPI_TILE + """ }
.card { --f7-card-bg-color: var(--f7-page-bg-color); background: transparent; box-shadow: none; border-radius: 0; }
.card-header { font-size: 20px; font-weight: 700; padding: 18px 16px 6px; gap: 10px; letter-spacing: -0.01em; }
.card-header::before { """ + HEAD_ICON + """ font-size: 22px; color: var(--h-hue); }
"""),
    # depth instead of lines: a soft colour glow on the page ground, translucent cards and tiles over it
    "e": ("Glas", "f7:sparkles", """
:host { --h-surface: var(--f7-card-bg-color); --h-tile-radius: 16px; --h-svg-tile-radius: 16px;
  --h-pill-radius: 999px; --h-watermark: 0.12; --h-hero-fs: 30px; --h-hero-lh: 36px; --h-hero-ls: -0.01em;
  --h-gap: 10px; --h-accent-border-w: 0px; --h-accent-inset: 3px; --h-accent-radius: 16px;
  --h-tile-bg: color-mix(in srgb, var(--f7-text-color) 5%, transparent);
  --h-svg-tile-bg: color-mix(in srgb, var(--f7-text-color) 5%, transparent);
  --h-tile-edge: inset 0 0 0 1px color-mix(in srgb, var(--f7-text-color) 7%, transparent);
  --h-accent-bg: color-mix(in srgb, var(--f7-text-color) 5%, transparent);
  --h-kpi-bg: color-mix(in srgb, var(--f7-text-color) 5%, transparent);
  --h-kpi-edge: inset 0 0 0 1px color-mix(in srgb, var(--f7-text-color) 7%, transparent); """ + KPI_TILE + """
  display: block; position: relative; isolation: isolate; }
:host::before { content: ''; position: fixed; inset: 0; z-index: -1; pointer-events: none;
  background: radial-gradient(900px 600px at 12% 8%, color-mix(in srgb, #ffb300 24%, transparent), transparent 70%),
    radial-gradient(800px 600px at 88% 40%, color-mix(in srgb, #29b6f6 20%, transparent), transparent 70%),
    radial-gradient(900px 700px at 30% 95%, color-mix(in srgb, #ff7043 18%, transparent), transparent 70%); }
.card { background: color-mix(in srgb, var(--h-surface) 80%, transparent); border-radius: 22px; backdrop-filter: blur(24px) saturate(1.3);
  -webkit-backdrop-filter: blur(24px) saturate(1.3);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--f7-text-color) 9%, transparent), 0 8px 28px rgba(0, 0, 0, 0.18); }
.card-header { font-size: 15px; font-weight: 600; padding: 16px 18px 8px; gap: 10px; }
.card-header::before { """ + HEAD_ICON + """ font-size: 18px; width: 30px; height: 30px; border-radius: 10px;
  color: #fff; background: linear-gradient(135deg, var(--h-hue), color-mix(in srgb, var(--h-hue) 60%, #000)); }
"""),
}

# B with A's filled grey tiles instead of hairlines (user, 2026-10-08), everything else as B
VARIANTS["b2"] = ("Ruhig gefüllt", "f7:circle_lefthalf_fill", VARIANTS["b"][2] + """:host {
  --h-tile-bg: color-mix(in srgb, var(--f7-text-color) 6%, transparent); --h-tile-edge: none;
  --h-svg-tile-bg: color-mix(in srgb, var(--f7-text-color) 6%, transparent); --h-svg-tile-edge: none; }
""")

ov = P["overview"]
COPIED = closure(ov)
body = {"ui:widget": {}, "ui:page": {}}
for uid in sorted(COPIED):
    body["ui:widget"][PREFIX + uid] = copy_widget(uid)
for key, (name, icon, css) in VARIANTS.items():
    page = copy.deepcopy(ov)
    page["uid"] = f"harmony_{key}"
    page.pop("timestamp", None)
    page.pop("editable", None)
    page["tags"] = ["proposal"]
    page["config"].update({"label": f"Vorschlag {key.upper()} · {name}", "sidebar": True, "order": "0",
                           "icon": icon})
    page["config"]["stylesheet"] = ov["config"]["stylesheet"] + "\n" + COMMON + css + PHONE
    for c in walk(page):
        comp = c.get("component", "")
        if comp.startswith("widget:") and comp[7:] in COPIED:
            c["component"] = f"widget:{PREFIX}{comp[7:]}"
    body["ui:page"][page["uid"]] = page

os.makedirs(OUT, exist_ok=True)
json.dump(body, open(os.path.join(OUT, "body.json"), "w"), ensure_ascii=False)
remove = {"ui:page": {u: None for u in body["ui:page"]}, "ui:widget": {u: None for u in body["ui:widget"]}}
json.dump(remove, open(os.path.join(OUT, "remove.json"), "w"), ensure_ascii=False, indent=1)
print(len(body["ui:widget"]), "widgets,", len(body["ui:page"]), "pages,",
      sum(len(json.dumps(v)) for v in body["ui:widget"].values()) // 1024, "KiB of widgets")
