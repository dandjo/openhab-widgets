#!/usr/bin/env python3
"""A temporary page `proposals` with ten ways to show in the energy flow how long the battery needs, at the power of
the last 5 minutes (huawei_inverter_energy_storage_power_5min, rule battery_power_5min), until it is full or empty,
and at what time (user, 2026-10-04). Each variant is the overview's energy flow with one addition at the battery;
the tooltips, which would show on hover, stand here all the time, so the variants compare side by side.

The battery holds about 7 kWh (charged from 3 to 100 % with 6.98 kWh net on 2026-10-03, from 13 to 100 % with
5.93 kWh on 2026-10-02) and discharges down to 3 % (its floor on both days). It counts as charging or discharging
above 50 W; at rest it shows nothing (or "ruht").

Usage: proposals_battery.py OUTDIR   writes the REST body OUTDIR/page.json (POST to ui:page, DELETE when done; the
generator's next run removes the uid proposals too, OBSOLETE_PAGES)"""
import copy
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(os.path.dirname(HERE), "dashboard.py")
OUT = sys.argv[1]
sys.argv = [GEN, "check"]  # the generator's module code reads its mode; its main() is not run
ns = {"__file__": GEN, "__name__": "dashboard"}
exec(compile(open(GEN).read().replace("\nmain()\n", "\n"), GEN, "exec"), ns)
g = type("g", (), ns)

UID = "proposals"
CAP_PER_PERCENT, FLOOR, IDLE = 0.07, 3, 50  # kWh per per cent of charge, the discharge floor in %, W
P5 = g.num("huawei_inverter_energy_storage_power_5min")  # negative while charging
# for the proposals only: at rest an example of 1.5 kW charging, so every variant shows something to judge
P = f"(Math.abs({P5}) > {IDLE} ? {P5} : -1500)"
EXAMPLE = f"(Math.abs({P5}) <= {IDLE})"
SOC = g.num(g.SOC)
CHARGING, DISCHARGING = f"({P} < -{IDLE})", f"({P} > {IDLE})"
ACTIVE = f"({CHARGING} || {DISCHARGING})"
# hours until full or empty, -1 at rest
HOURS = (f"({CHARGING} ? Math.max(0, 100 - {SOC}) * {CAP_PER_PERCENT} / (-{P} / 1000) : {DISCHARGING} ? "
         f"Math.max(0, {SOC} - {FLOOR}) * {CAP_PER_PERCENT} / ({P} / 1000) : -1)")
MINUTES = f"Math.round({HOURS} * 60)"
VERB = f"({CHARGING} ? 'voll' : 'leer')"
DUR = (f"((m) => m < 0 ? '' : m >= 2880 ? 'über 2 Tage' : m < 60 ? Math.max(1, m) + ' min' : "
       f"Math.floor(m / 60) + ':' + ('0' + m % 60).slice(-2) + ' h')({MINUTES})")
CLOCK = (f"((m) => m < 0 ? '' : dayjs().add(m, 'minute').isSame(dayjs(), 'day') ? "
         f"dayjs().add(m, 'minute').format('HH:mm') : dayjs().add(m, 'minute').format('dd HH:mm'))({MINUTES})")
KW5 = f"({P} / 1000).toFixed(2).replace('.', ',') + ' kW'"
GREEN = g.BATTERY_GREEN
BX, BY = g.BATT_XY
TIP_BG = "=themeOptions.dark === 'dark' ? '#2b2b2c' : '#ffffff'"
TIP_FG = "currentColor"


def flow(additions=(), html=(), edit=None):
    """The overview's energy flow (star only) with additions in its svg and html overlays over it."""
    star = copy.deepcopy(g.energy_flow()[0])
    inner = star["slots"]["default"][0]
    drawing = inner["slots"]["default"][0]
    if edit:
        edit(drawing)
    drawing["slots"]["default"].extend(additions)
    inner["slots"]["default"].extend(html)
    return star


def text(x, y, content, size, weight="normal", anchor="middle", fill=TIP_FG, opacity="1"):
    return g.svg("text", x=x, y=y, content=content, fill=fill,
                 **{"font-size": size, "font-weight": weight, "text-anchor": anchor, "opacity": opacity})


def bubble(x, y, w, h, pointer, visible=f"={ACTIVE}"):
    """A tooltip bubble in the svg: rounded box from (x, y), with a pointer on the side named (down, left)."""
    if pointer == "down":
        tip = f"M{x + w / 2 - 7},{y + h} L{x + w / 2},{y + h + 8} L{x + w / 2 + 7},{y + h} Z"
    else:
        tip = f"M{x},{y + h / 2 - 7} L{x - 8},{y + h / 2} L{x},{y + h / 2 + 7} Z"
    style = {"fill": TIP_BG, "stroke": "rgba(127, 127, 127, 0.35)", "stroke-width": 1}
    return [g.svg("path", d=tip, visible=visible, **style),
            g.svg("rect", x=x, y=y, width=w, height=h, rx=8, visible=visible, **style),
            g.svg("path", d=tip.replace("Z", ""), visible=visible, fill=style["fill"])]


def variant_a():
    """Tooltip above the battery: what and when in two lines."""
    x, y, w, h = BX - 62, BY - 30 - 8 - 46 - 4, 124, 46
    return flow([*bubble(x, y, w, h, "down"),
                 text(BX, y + 19, f"={VERB} + ' in ' + {DUR}", 14, "700", fill=GREEN, opacity="1"),
                 text(BX, y + 36, f"='um ' + {CLOCK} + ' Uhr'", 12, opacity="0.75")])


def variant_b():
    """Tooltip beside the battery, to its right, with the 5-minute power."""
    x, y, w, h = BX + 30 + 12, BY - 34, 132, 64
    return flow([*bubble(x, y, w, h, "left"),
                 text(x + 10, y + 20, f"={VERB} + ' in ' + {DUR}", 14, "700", anchor="start", fill=GREEN),
                 text(x + 10, y + 37, f"='um ' + {CLOCK} + ' Uhr'", 12, anchor="start"),
                 text(x + 10, y + 54, f"='Ø 5 min ' + {KW5}", 11, anchor="start", opacity="0.6")])


def variant_c():
    """A badge on the ring, lower right, with the clock time; the duration in a tooltip of the badge."""
    cx, cy = round(BX + g.ON_RING, 1), round(BY + g.ON_RING, 1)
    w = 52
    return flow([g.svg("rect", x=cx - w / 2, y=cy - 10, width=w, height=20, rx=10, fill=GREEN, visible=f"={ACTIVE}"),
                 text(cx, cy + 4.5, f"={CLOCK}", 12, "700", fill="#ffffff"),
                 *bubble(cx + w / 2 + 10, cy - 15, 84, 30, "left"),
                 text(cx + w / 2 + 52, cy + 4.5, f"={VERB} + ' in ' + {DUR}", 12, "700", fill=GREEN)])


def variant_d():
    """A third line under the battery, always shown while it charges or discharges."""
    return flow([text(BX, BY + 30 + 44 + 15, f"={ACTIVE} ? {VERB} + ' ' + {CLOCK} + ' · ' + {DUR} : ''", 12, "700",
                      fill=GREEN)])


def variant_e():
    """The second line under the battery becomes the time while it charges or discharges, the day's energies at
    rest."""
    def edit(drawing):
        for el in drawing["slots"]["default"]:
            c = el.get("config", {})
            if el.get("component") == "text" and c.get("x") == BX and c.get("y") == BY + 30 + 44:
                c["content"] = f"={ACTIVE} ? {VERB} + ' ' + {CLOCK} + ' (' + {DUR} + ')' : {c['content'][1:]}"
                c["fill"] = f"={ACTIVE} ? '{GREEN}' : 'currentColor'"
                c["opacity"] = f"={ACTIVE} ? '1' : '0.7'"
    return flow(edit=edit)


def variant_f():
    """Along the ring: the time written on an arc over the battery's ring."""
    r = 30 + 7
    arc = f"M{BX - r},{BY} A{r},{r} 0 0,1 {BX + r},{BY}"
    return flow([g.svg("path", id="battEtaArc", d=arc, fill="none"),
                 g.svg("text", [g.svg("textPath", href="#battEtaArc", startOffset="50%",
                                      content=f"={ACTIVE} ? {VERB} + ' ' + {CLOCK} : ''")],
                       fill=GREEN, **{"font-size": 11, "font-weight": "700", "text-anchor": "middle"})])


def variant_g():
    """In the battery itself: its charge and the time take turns every 3 seconds."""
    cover = g.svg("rect", x=BX - 18, y=BY - 7, width=34, height=14, rx=1, style={"fill": "var(--f7-card-bg-color, #fff)"})
    turn = {"attributeName": "opacity", "values": "0;0;1;1;0", "keyTimes": "0;0.45;0.5;0.95;1", "dur": "6s",
            "repeatCount": "indefinite"}
    return flow([g.svg("g", [cover, text(BX - 1, BY + 4, f"={CLOCK}", 11, "700", fill=GREEN),
                             g.svg("animate", **turn)], opacity="0", visible=f"={ACTIVE}")])


def variant_h():
    """On the battery's line to the house: a pill with an arrow and the clock time."""
    mx, my = (BX + g.HOME_XY[0]) / 2, (BY + g.HOME_XY[1]) / 2
    return flow([g.svg("rect", x=mx - 34, y=my - 11, width=68, height=22, rx=11, fill=GREEN, visible=f"={ACTIVE}"),
                 text(mx, my + 4.5, f"=({CHARGING} ? '▲ ' : '▼ ') + {CLOCK}", 12, "700", fill="#ffffff")])


def variant_i():
    """An HTML tooltip over the battery as the charts' tooltips look: title, charge, 5-minute power, time."""
    row = lambda name, value, color=None: g.div([g.label(name, **{"opacity": "0.7"}),
                                                g.label(value, **{"font-weight": "700",
                                                                  **({"color": color} if color else {})})],
                                               **{"display": "flex", "justify-content": "space-between", "gap": "14px"})
    tip = g.div([g.label("Batteriespeicher", **{"font-weight": "700", "margin-bottom": "4px"}),
                 row("Ladestand", f"={g.disp(g.SOC)}"),
                 row("Ø 5 min", f"={KW5}"),
                 row(f"={CHARGING} ? 'Voll in' : 'Leer in'", f"={DUR}", GREEN),
                 row("Um", f"={CLOCK} + ' Uhr'", GREEN)],
                visible=f"={ACTIVE}",
                **{"position": "absolute", "left": f"{BX / g.FLOW_W * 100:.2f}%", "top": f"{(BY - 34) / g.FLOW_H * 100:.2f}%",
                   "transform": "translate(-50%, -100%)", "background": TIP_BG, "border-radius": "6px",
                   "box-shadow": "0 2px 10px rgba(0, 0, 0, 0.3)", "padding": "8px 10px", "font-size": "12px",
                   "line-height": "18px", "min-width": "150px", "pointer-events": "none"})
    return flow(html=[tip])


def variant_j():
    """A bar under the battery's texts from its charge to full or empty, the clock time at its end."""
    y, w = BY + 30 + 60, 96
    x = BX - w / 2
    fill = f"={CHARGING} ? (({SOC}) / 100 * {w}).toFixed(1) : ((({SOC}) - {FLOOR}) / (100 - {FLOOR}) * {w}).toFixed(1)"
    return flow([g.svg("rect", x=x, y=y, width=w, height=6, rx=3, fill="rgba(127, 127, 127, 0.25)", visible=f"={ACTIVE}"),
                 g.svg("rect", x=x, y=y, width=fill, height=6, rx=3, fill=GREEN, visible=f"={ACTIVE}"),
                 text(BX, y + 20, f"={ACTIVE} ? {VERB} + ' um ' + {CLOCK} : ''", 11, "700", fill=GREEN)])


VARIANTS = [("A · Sprechblase über dem Akku (Tooltip)", variant_a), ("B · Sprechblase daneben, mit Ø 5 min (Tooltip)", variant_b),
            ("C · Uhrzeit als Abzeichen am Ring, Dauer als Tooltip", variant_c), ("D · Dritte Zeile unter dem Akku", variant_d),
            ("E · Zweite Zeile wird zur Zeit, solange er lädt oder entlädt", variant_e), ("F · Schrift am Ring entlang", variant_f),
            ("G · Im Akku abwechselnd Ladestand und Uhrzeit", variant_g), ("H · Abzeichen auf der Linie zum Haus", variant_h),
            ("I · Tooltip wie bei den Diagrammen, mit Details", variant_i), ("J · Balken bis voll oder leer mit Uhrzeit", variant_j)]


# ---- the second round (user, 2026-10-04): C's pills, a red one for today's discharge at the lower left of the ring
# and a green one for today's charge at the lower right; the time until full or empty takes the second line under the
# power, in the style of every node's second line. B stays the reference.

RED, GREEN_PILL = "#e53935", "#43a047"
DIS, CHG = g.num("huawei_inverter_energy_storage_day_discharge"), g.num("huawei_inverter_energy_storage_day_charge")
ETA_IN = f"={ACTIVE} ? {VERB} + ' in ' + {DUR} + ' · ' + {CLOCK} : 'ruht'"
ETA_AT = f"={ACTIVE} ? {VERB} + ' um ' + {CLOCK} + ' (' + {DUR} + ')' : 'ruht'"
ETA_LEFT = f"={ACTIVE} ? {DUR} + ' bis ' + {VERB} + ' · ' + {CLOCK} : 'ruht'"
LOWER = round(g.ON_RING, 1)  # the ring's lower 45° points, where C's badge stood


def eta_line(content):
    """The battery's second line under its power becomes the time until full or empty, styled as before."""
    def edit(drawing):
        for el in drawing["slots"]["default"]:
            c = el.get("config", {})
            if el.get("component") == "text" and c.get("x") == BX and c.get("y") == BY + 30 + 44:
                c["content"] = content
    return edit


def pill(cx, cy, w, content, color, style="filled", size=11, h=18):
    """A pill centred at (cx, cy) on an opaque face, so the ring under it does not show: filled in the colour with
    white text, or tinted with an outline and text in the colour."""
    face = g.svg("rect", x=round(cx - w / 2, 1), y=round(cy - h / 2, 1), width=w, height=h, rx=h / 2,
                 style={"fill": "var(--f7-card-bg-color, #fff)"})
    if style == "filled":
        body = g.svg("rect", x=round(cx - w / 2, 1), y=round(cy - h / 2, 1), width=w, height=h, rx=h / 2, fill=color)
        fg = "#ffffff"
    else:
        body = g.svg("rect", x=round(cx - w / 2, 1), y=round(cy - h / 2, 1), width=w, height=h, rx=h / 2,
                     fill=g.rgba(color, 0.18), stroke=color, **{"stroke-width": 1.2})
        fg = color
    return [face, body, text(cx, round(cy + size * 0.36, 1), content, size, "700", fill=fg)]


def kwh2(expr, digits=2):
    return f"{g.fixed(expr, digits)}"


def pills(style="filled", fmt=lambda v: kwh2(v), dx=LOWER, dy=LOWER, w=36, size=11, arrows=False, active=False,
          h=18):
    """The two pills: discharge red at the lower left, charge green at the lower right."""
    out = []
    for sign, value, color, arrow, mine in ((-1, DIS, RED, "↓ ", DISCHARGING), (1, CHG, GREEN_PILL, "↑ ", CHARGING)):
        content = f"={(chr(39) + arrow + chr(39) + ' + ') if arrows else ''}{fmt(value)}"
        if active:  # the one at work filled, the other tinted
            out += [g.svg("g", pill(BX + sign * dx, BY + dy, w, content, color, "filled", size, h), visible=f"={mine}"),
                    g.svg("g", pill(BX + sign * dx, BY + dy, w, content, color, "tinted", size, h),
                          visible=f"=!{mine}")]
        else:
            out += pill(BX + sign * dx, BY + dy, w, content, color, style, size, h)
    return out


def variant_k():
    """Filled pills with the day's energies, the time under the power."""
    return flow(pills(), edit=eta_line(ETA_IN))


def variant_l():
    """Filled pills with arrows: down for what went out, up for what came in."""
    return flow(pills(arrows=True, w=46), edit=eta_line(ETA_IN))


def variant_m():
    """Tinted, outlined pills with arrows."""
    return flow(pills(style="tinted", arrows=True, w=46), edit=eta_line(ETA_IN))


def variant_n():
    """Wider pills with the unit, further out beside the ring's lower half."""
    return flow(pills(fmt=lambda v: f"{kwh2(v)} + ' kWh'", dx=44, dy=22, w=60), edit=eta_line(ETA_IN))


def variant_o():
    """Filled pills; the time as clock time first, the duration in brackets."""
    return flow(pills(), edit=eta_line(ETA_AT))


def variant_p():
    """Small tinted pills to one decimal; the duration first."""
    return flow(pills(style="tinted", fmt=lambda v: kwh2(v, 1), w=30, size=10, h=16), edit=eta_line(ETA_LEFT))


def variant_q():
    """Filled pills with arrow glyphs of the icon font."""
    out = []
    for sign, value, color, icon in ((-1, DIS, RED, "south"), (1, CHG, GREEN_PILL, "north")):
        cx, cy, w = BX + sign * LOWER, BY + LOWER, 48
        out += pill(cx + 0, cy, w, "", color)
        out += [g.svg("text", x=round(cx - w / 2 + 10, 1), y=cy, content=icon, fill="#ffffff",
                      **{"font-size": 12, "text-anchor": "middle", "dominant-baseline": "central",
                         "style": {"font-family": "'Material Icons'", "font-feature-settings": "'liga'"}}),
                text(round(cx + 6, 1), round(cy + 4, 1), f"={kwh2(value)}", 11, "700", fill="#ffffff")]
    return flow(out, edit=eta_line(ETA_IN))


def variant_r():
    """K with B's bubble beside the battery (hover), for the details: the 5-minute power."""
    x, y, w, h = BX + 30 + 34, BY - 34, 132, 64
    return flow([*pills(), *bubble(x, y, w, h, "left"),
                 text(x + 10, y + 20, f"={VERB} + ' in ' + {DUR}", 14, "700", anchor="start", fill=GREEN),
                 text(x + 10, y + 37, f"='um ' + {CLOCK} + ' Uhr'", 12, anchor="start"),
                 text(x + 10, y + 54, f"='Ø 5 min ' + {KW5}", 11, anchor="start", opacity="0.6")],
                edit=eta_line(ETA_IN))


def variant_s():
    """The pills hang under the ring, close together, between the ring and the power."""
    return flow(pills(dx=20, dy=36, w=36, size=10, h=16), edit=eta_line(ETA_IN))


def variant_t():
    """The pill at work filled (red while discharging, green while charging), the other one tinted."""
    return flow(pills(active=True), edit=eta_line(ETA_IN))


VARIANTS2 = [("B · Sprechblase daneben, mit Ø 5 min (bisheriger Favorit)", variant_b),
             ("C · Uhrzeit als Abzeichen am Ring (Ausgangspunkt)", variant_c),
             ("K · Gefüllte Pillen, Zeit unter der Leistung", variant_k),
             ("L · Gefüllte Pillen mit Pfeilen", variant_l),
             ("M · Umrandete Pillen mit Pfeilen", variant_m),
             ("N · Breitere Pillen mit Einheit, weiter außen", variant_n),
             ("O · Gefüllte Pillen, Uhrzeit zuerst", variant_o),
             ("P · Kleine umrandete Pillen, eine Nachkommastelle, Dauer zuerst", variant_p),
             ("Q · Gefüllte Pillen mit Pfeil-Symbolen", variant_q),
             ("R · K mit der Sprechblase aus B (Tooltip)", variant_r),
             ("S · Pillen unter dem Ring, eng beisammen", variant_s),
             ("T · Die aktive Pille gefüllt, die andere umrandet", variant_t)]


def page(now):
    note = g.card("Batterie: Zeit bis voll oder leer · Runde 2", [g.label(
        "=('Zehn Varianten (K bis T) auf Basis von C: links unten eine rote Pille mit der Entladung, rechts unten eine "
        "grüne mit der Ladung heute (kWh); die Zeit bis voll oder leer steht unter der Leistung, wie die zweite Zeile "
        "der anderen Knoten. Gerechnet mit der Leistung der letzten 5 Minuten (gerade ' + "
        f"{KW5} + ({EXAMPLE} ? ' als Beispiel, der Akku ruht' : '') + ', Ladestand ' + Math.round({SOC}) + "
        "' %) und rund 7 kWh nutzbarer Kapazität, entladen bis 3 %. B und C stehen zum Vergleich voran.')",
        **{"padding": "4px 16px 14px", "font-size": "14px"})])
    cards = [g.card(title, [build()]) for title, build in VARIANTS2]
    rows = [g.row(g.full(note))] + [g.row(g.col([a]), g.col([b])) for a, b in zip(cards[::2], cards[1::2])]
    entry = g.layout_page(UID, {"label": "Vorschläge", "sidebar": False}, [g.block(*rows)], now)
    return entry["value"]


now = datetime.datetime.now()
os.makedirs(OUT, exist_ok=True)
json.dump(page(now), open(os.path.join(OUT, "page.json"), "w"), ensure_ascii=False)
print("written", os.path.join(OUT, "page.json"))
