#!/usr/bin/env python3
"""A temporary page `proposals` with five ways to show in the energy flow how much of the house's power each consumer
draws now: heat pump, air conditioner, E-Car, the household appliances and the ventilation, as a share of
home_active_power (user, 2026-10-05). Each variant is the overview's energy flow with one addition. A consumer below
its line's threshold counts as idle: its share stays visible for comparing, in grey.

Usage: proposals_share.py OUTDIR   writes the REST body OUTDIR/body.json for ui_put.py (POST to ui:page; DELETE when
done, the generator's next run removes the uid proposals too, OBSOLETE_PAGES)"""
import copy
import datetime
import json
import math
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
HOME = g.num(g.HOME)
GREY = "#9e9e9e"
# the consumers clockwise from the top: key, short name, node, power, threshold, colour
CONSUMERS = [("vent", "Lüftung", g.VENT_XY, g.VENT_POWER, 5, g.VENT_TEAL),
             ("hp", "Wärmepumpe", g.HP_XY, g.num(g.HP), g.HP_ON, g.HP_ORANGE),
             ("ac", "Klima", g.AC_XY, g.AC_FLOW, g.AC_ON, g.AC_BLUE),
             ("ecar", "E-Auto", g.ECAR_XY, g.num(g.ECAR), g.ECAR_ON, g.ECAR_COLOR),
             ("appl", "Geräte", g.APPL_XY, g.APPL_POWER, g.APPL_ON, g.APPL_COLOR)]


def share(power):
    """A consumer's share of the house's power now, in per cent (0 to 100)."""
    return f"Math.min(100, Math.max(0, {power}) / Math.max(1, {HOME}) * 100)"


def pct(power):
    """The share as text: whole per cent, '<1 %' for a trace."""
    return f"((v) => v > 0 && v < 1 ? '<1 %' : Math.round(v) + ' %')({share(power)})"


def active(power, threshold):
    return f"(Math.abs({power}) > {threshold})"


def segments():
    """Each consumer's part of the house's power, clamped so they never add up beyond 100: (cumulated before, own)."""
    out, before = [], "0"
    for _, _, _, power, _, _ in CONSUMERS:
        own = f"Math.max(0, Math.min({share(power)}, 100 - ({before})))"
        out.append((before, own))
        before = f"({before} + {own})"
    return out, before


def flow(additions=(), under=(), html=(), below=()):
    """The overview's energy flow with additions over its drawing, under its nodes (after the links), html overlays
    over it and content between the star and the house's tiles."""
    star, strip = copy.deepcopy(g.energy_flow())
    inner = star["slots"]["default"][0]
    drawing = inner["slots"]["default"][0]
    parts = drawing["slots"]["default"]
    links = sum(1 for p in parts if p.get("component") == "widget:flow-link")
    parts[links:links] = list(under)
    parts.extend(additions)
    inner["slots"]["default"].extend(html)
    return g.div([star, *below, strip], **{"display": "flex", "flex-direction": "column"})


def text(x, y, content, size, weight="700", anchor="middle", fill="currentColor", outline=False, **extra):
    style = {"font-size": size, "font-weight": weight, "text-anchor": anchor}
    if outline:  # outlined in the card colour, so it reads over lines and dots
        style.update({"paint-order": "stroke", "stroke": "var(--f7-card-bg-color, #fff)", "stroke-width": 3,
                      "stroke-linejoin": "round"})
    return g.svg("text", x=x, y=y, content=content, fill=fill, **style, **extra)


def pill(cx, cy, w, content, color, on, h=18, size=11):
    """A pill centred at (cx, cy) on an opaque face: filled in the colour while on, grey tinted while idle."""
    box = {"x": round(cx - w / 2, 1), "y": round(cy - h / 2, 1), "width": w, "height": h, "rx": h / 2}
    return [g.svg("rect", **box, style={"fill": "var(--f7-card-bg-color, #fff)"}),
            g.svg("rect", **box, fill=f"={on} ? '{color}' : 'rgba(158, 158, 158, 0.18)'",
                  stroke=f"={on} ? '{color}' : '{GREY}'", **{"stroke-width": 1}),
            text(cx, round(cy + size * 0.36, 1), f"={content}", size, fill=f"={on} ? '#ffffff' : '{GREY}'")]


def variant_a():
    """A badge on each consumer's ring, lower right (the ventilation's lower left, clear of its texts)."""
    adds = []
    for key, _, (x, y), power, threshold, color in CONSUMERS:
        side = -1 if key == "vent" else 1
        adds += pill(round(x + side * g.ON_RING, 1), round(y + g.ON_RING, 1), 38, pct(power), color,
                     active(power, threshold))
    return flow(adds)


def spoke_point(node, t):
    """A point on the line from the house's rim (t 0) to the node's rim (t 1)."""
    (hx, hy), (nx, ny) = g.HOME_XY, node
    d = math.hypot(nx - hx, ny - hy)
    ux, uy = (nx - hx) / d, (ny - hy) / d
    a, b = 30, d - 30
    r = a + (b - a) * t
    return round(hx + r * ux, 1), round(hy + r * uy, 1), ux, uy


def variant_b():
    """A pill in the middle of each consumer's line to the house; the dots run on under it."""
    adds = []
    for _, _, node, power, threshold, color in CONSUMERS:
        x, y, _, _ = spoke_point(node, 0.5)
        adds += pill(x, y, 40, pct(power), color, active(power, threshold))
    return flow(adds)


def variant_c():
    """Each consumer's line as thick as its share (3 to 15 units), the share beside it near the node."""
    under, adds = [], []
    for _, _, node, power, threshold, color in CONSUMERS:
        x1, y1, ux, uy = spoke_point(node, 0)
        x2, y2, _, _ = spoke_point(node, 1)
        on = active(power, threshold)
        under.append(g.svg("line", x1=x1, y1=y1, x2=x2, y2=y2, stroke=f"={on} ? '{color}' : '{GREY}'",
                           **{"stroke-width": f"=(3 + 12 * {share(power)} / 100).toFixed(1)",
                              "stroke-linecap": "round", "opacity": "0.35"}))
        x, y, _, _ = spoke_point(node, 0.62)
        # beside the line, on the side away from the house's other lines (perpendicular, clockwise)
        adds.append(text(round(x - uy * 16, 1), round(y + ux * 16 + 4, 1), f"={pct(power)}", 12, outline=True,
                         fill=f"={on} ? '{color}' : '{GREY}'"))
    return flow(adds, under)


def variant_d():
    """The house's ring as a pie of its power: each consumer's share as an arc in its colour, clockwise from the top in
    the order of the nodes, the rest of the ring grey for everything else; the shares of 6 % and more at their arcs,
    outlined so they read over the lines."""
    (hx, hy), r = g.HOME_XY, g.RING_R
    segs, _ = segments()
    adds = [g.svg("circle", cx=hx, cy=hy, r=r, fill="none", stroke="var(--f7-card-bg-color, #fff)",
                  **{"stroke-width": g.RING_MAX + 1})]
    labels = []
    for (before, own), (_, _, _, power, _, color) in zip(segs, CONSUMERS):
        adds.append(g.svg("circle", cx=hx, cy=hy, r=r, fill="none", stroke=color, pathLength=100,
                          transform=f"rotate(-90 {hx} {hy})",
                          **{"stroke-width": g.RING_MAX, "stroke-dasharray": f"=({own}).toFixed(2) + ' 100'",
                             "stroke-dashoffset": f"=(-({before})).toFixed(2)"}))
        mid = f"(({before}) + ({own}) / 2) / 100 * 2 * Math.PI - Math.PI / 2"
        labels.append(text(f"=({hx} + 47 * Math.cos({mid})).toFixed(1)", f"=({hy} + 47 * Math.sin({mid}) + 4).toFixed(1)",
                           f"={pct(power)}", 12, outline=True, fill=color, visible=f"=({own}) >= 6"))
    # the grey rest under the arcs
    adds.insert(1, g.svg("circle", cx=hx, cy=hy, r=r, fill="none", stroke="rgba(127, 127, 127, 0.28)",
                         **{"stroke-width": g.RING_MAX}))
    return flow([*adds, *labels])


def variant_e():
    """A bar between the star and the house's tiles: the house's power split by consumer in their colours, the rest
    grey, with each share and name under it."""
    segs, total = segments()
    parts, legend = [], []
    for (_, own), (_, name, _, power, threshold, color) in zip(segs, CONSUMERS):
        parts.append(g.div([], **{"width": f"=({own}).toFixed(2) + '%'", "background": color}))
        legend.append(g.div([g.div([], **{"width": "8px", "height": "8px", "border-radius": "50%", "background": color}),
                             g.label(f"='{name} ' + {pct(power)}")],
                            **{"display": "inline-flex", "align-items": "center", "gap": "5px",
                               "opacity": f"={active(power, threshold)} ? '1' : '0.45'"}))
    rest = f"Math.max(0, 100 - {total})"
    parts.append(g.div([], **{"width": f"=({rest}).toFixed(2) + '%'", "background": "rgba(127, 127, 127, 0.25)"}))
    legend.append(g.div([g.div([], **{"width": "8px", "height": "8px", "border-radius": "50%",
                                      "background": "rgba(127, 127, 127, 0.5)"}),
                         g.label(f"='Sonstiges ' + Math.round({rest}) + ' %'")],
                        **{"display": "inline-flex", "align-items": "center", "gap": "5px"}))
    box = g.div([g.label("Wohin die Leistung des Hauses jetzt geht", **{"font-size": "13px", "opacity": "0.7"}),
                 g.div(parts, **{"display": "flex", "height": "10px", "border-radius": "5px", "overflow": "hidden",
                                 "margin": "6px 0"}),
                 g.div(legend, **{"display": "flex", "flex-wrap": "wrap", "gap": "4px 14px", "font-size": "12px"})],
                **{"padding": "4px 16px 4px"})
    return flow(below=[box])


VARIANTS = [("A · Abzeichen am Ring", variant_a), ("B · Pille auf der Leitung", variant_b),
            ("C · Linienstärke nach Anteil", variant_c), ("D · Haus-Ring als Torte", variant_d),
            ("E · Balken unter dem Stern", variant_e)]


def page(now):
    note = g.card("Verbraucher: Anteil an der Leistung des Hauses", [g.label(
        f"='Fünf Varianten, wie viel Prozent der Leistung des Hauses (gerade ' + {g.fixed(f'{HOME} / 1000', 2)} + "
        "' kW) jeder Verbraucher jetzt zieht: Wärmepumpe, Klimaanlage, E-Auto, Haushaltsgeräte und Lüftung. Ein "
        "Verbraucher unter seiner Schwelle (wie im Energiefluss) zählt als ruhend und steht hier zum Vergleich grau "
        "da; im Energiefluss könnte er dann ganz entfallen.'",
        **{"padding": "4px 16px 14px", "font-size": "14px"})])
    cards = [g.card(title, [build()]) for title, build in VARIANTS]
    rows = [g.row(g.full(note))] + [g.row(*(g.col([c]) for c in cards[i:i + 2])) for i in range(0, len(cards), 2)]
    entry = g.layout_page(UID, {"label": "Vorschläge", "sidebar": False}, [g.block(*rows)], now)
    return entry["value"]


now = datetime.datetime.now()
os.makedirs(OUT, exist_ok=True)
json.dump({"ui:page": {UID: page(now)}}, open(os.path.join(OUT, "body.json"), "w"), ensure_ascii=False)
print("written", os.path.join(OUT, "body.json"))
