#!/usr/bin/env python3
"""A temporary page `proposals` with icon variants, each drawn as a node with its ring, running dots and live values
(user, 2026-10-03). First five variations of a ventilation unit for the energy flow's Lüftung (the first unit, with
two ducts on its top, looked like a battery; the user picked 5) and five alternatives to the hot water tank; now five
variations of the current tank, each keeping the Effect Heater beside it, lit while it heats, as the user asked. The
generator removes the page on its next run (OBSOLETE_PAGES).
Usage: proposals_icons.py BODY   (writes the REST body for ui_put.py; OPENHAB_JSONDB as for the generator)"""
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
TEAL, P = g.VENT_TEAL, g.VENT_POWER
RUNNING = f"Math.abs({P}) > 5"
EXHAUST = "#90a4ae"  # the used air leaving the house
s = g.stroke


def blades(cx, cy, scale=1.0, n=5):
    """The current icon's curved blades, scaled, turning while it runs."""
    k = lambda v: round(v * scale, 2)
    blade = (f"M{cx},{cy} C{cx + k(5)},{cy - k(3)} {cx + k(9)},{cy - k(11)} {cx + k(3)},{cy - k(17)} "
             f"C{cx - k(1)},{cy - k(12)} {cx - k(4)},{cy - k(6)} {cx},{cy} Z")
    out = [g.svg("path", d=blade, fill=TEAL, transform=f"rotate({360 / n * i} {cx} {cy})", **{"fill-opacity": "0.85"})
           for i in range(n)]
    out.append(g.spin(cx, cy, g.steps(P, [30, 60], ["2.4s", "1.5s", "0.9s"]), RUNNING))
    return g.svg("g", out)


def fan(cx, cy, scale):
    return [blades(cx, cy, scale), g.svg("circle", cx=cx, cy=cy, r=round(1 + 2 * scale, 1),
                                         style={"fill": "var(--f7-card-bg-color, #fff)"}, stroke=TEAL,
                                         **{"stroke-width": 1.4})]


def flowing(d, color, width=1.6):
    """A dashed air stream that flows along its path while the ventilation runs."""
    dur = g.steps(P, [30, 60], ["1.6s", "1s", "0.6s"])
    return g.svg("path", [g.dash_flow(dur, RUNNING, to="-12")], d=d, opacity=f"={RUNNING} ? '1' : '0.4'",
                 **s(width, color, **{"stroke-dasharray": "3 3", "stroke-linejoin": "round"}))


def arrow_head(x, y, direction, color):
    """A small filled arrow head at (x, y) pointing up (-1) or down (1)."""
    return g.svg("path", d=f"M{x - 3.5},{y - 3.5 * direction} L{x},{y} L{x + 3.5},{y - 3.5 * direction} Z", fill=color)


# ---- ventilation unit variations

def vent_c(cx, cy):
    """C, as first shown: a box with two ducts on its top, the fan left, the heat exchanger's cross right."""
    fx, fy = cx - 7, cy + 3
    return [g.svg("rect", x=cx - 12, y=cy - 17, width=7, height=7, rx=1, **s(1.4)),
            g.svg("rect", x=cx + 5, y=cy - 17, width=7, height=7, rx=1, **s(1.4)),
            g.svg("rect", x=cx - 18, y=cy - 10, width=36, height=25, rx=3, **s(1.6)), *fan(fx, fy, 0.5),
            g.svg("rect", x=cx + 3, y=cy - 4, width=11, height=13, rx=1, **s(1.1, opacity="0.8")),
            g.svg("path", d=f"M{cx + 3},{cy - 4} L{cx + 14},{cy + 9} M{cx + 14},{cy - 4} L{cx + 3},{cy + 9}",
                  **s(1.1, TEAL))]


def vent_1(cx, cy):
    """1: a flat unit with four round duct sockets on its top, as such units have, the fan in its middle."""
    sockets = [g.svg("rect", x=cx + x - 2.8, y=cy - 13, width=5.6, height=6, rx=2.8, **s(1.3)) for x in (-12, -4, 4, 12)]
    return [*sockets, g.svg("rect", x=cx - 18, y=cy - 8, width=36, height=22, rx=3, **s(1.6)), *fan(cx, cy + 3, 0.5)]


def vent_2(cx, cy):
    """2: the ducts leave at the sides, fresh air in on the left (teal), used air out on the right (grey), the fan
    between them."""
    return [g.svg("rect", x=cx - 13, y=cy - 13, width=26, height=26, rx=3, **s(1.6)), *fan(cx, cy, 0.6),
            flowing(f"M{cx - 25},{cy - 6} H{cx - 14}", TEAL, 2), flowing(f"M{cx + 14},{cy + 6} H{cx + 25}", EXHAUST, 2),
            g.svg("line", x1=cx - 25, y1=cy + 6, x2=cx - 14, y2=cy + 6, **s(2, EXHAUST, opacity="0.5")),
            g.svg("line", x1=cx + 14, y1=cy - 6, x2=cx + 25, y2=cy - 6, **s(2, TEAL, opacity="0.5"))]


def vent_3(cx, cy):
    """3: the unit on the floor with its two ducts running up to the ceiling, louvres on the right, the fan on the
    left."""
    fx, fy = cx - 8, cy + 6
    louvres = [g.svg("line", x1=cx + 3, y1=cy + y, x2=cx + 14, y2=cy + y, **s(1.2, opacity="0.75")) for y in (1, 5, 9)]
    return [g.svg("line", x1=cx - 8, y1=cy - 25, x2=cx - 8, y2=cy - 4, **s(4, TEAL, opacity="0.7")),
            g.svg("line", x1=cx + 8, y1=cy - 25, x2=cx + 8, y2=cy - 4, **s(4, EXHAUST, opacity="0.7")),
            g.svg("rect", x=cx - 18, y=cy - 4, width=36, height=20, rx=3, **s(1.6)), *fan(fx, fy, 0.45), *louvres]


def vent_4(cx, cy):
    """4: the heat recovery itself, the cross-flow exchanger as a diamond in the unit, two air streams crossing in
    it, flowing while the ventilation runs."""
    return [g.svg("rect", x=cx - 19, y=cy - 14, width=38, height=28, rx=3, **s(1.6)),
            g.svg("polygon", points=f"{cx},{cy - 10} {cx + 10},{cy} {cx},{cy + 10} {cx - 10},{cy}",
                  **s(1.3, fill=g.rgba(TEAL, 0.15))),
            flowing(f"M{cx - 16},{cy - 11} L{cx + 16},{cy + 11}", TEAL),
            flowing(f"M{cx + 16},{cy - 11} L{cx - 16},{cy + 11}", EXHAUST)]


def vent_5(cx, cy):
    """5: the unit with its fan and two arrows on its top, fresh air coming in (teal), used air going out (grey)."""
    return [g.svg("rect", x=cx - 16, y=cy - 6, width=32, height=21, rx=3, **s(1.6)), *fan(cx, cy + 4.5, 0.5),
            flowing(f"M{cx - 8},{cy - 24} V{cy - 10}", TEAL, 1.8), arrow_head(cx - 8, cy - 8, 1, TEAL),
            flowing(f"M{cx + 8},{cy - 7} V{cy - 21}", EXHAUST, 1.8), arrow_head(cx + 8, cy - 24, -1, EXHAUST)]


VENTS = [("C", "bisher", vent_c), ("1", "vier Stutzen", vent_1), ("2", "Rohre seitlich", vent_2),
         ("3", "Rohre zur Decke", vent_3), ("4", "Kreuzstrom", vent_4), ("5", "Luftpfeile", vent_5)]


# ---- hot water tank alternatives

TANK_C = "#e57373"
TANK_ON = f"({g.TANK_FLOW} || {g.BSH_ON})"
COIL_ON = f"({g.TANK_FLOW} && {g.COMPRESSOR})"
TEMP = g.num(g.HPX["tank"])
TANK_TEMP_C = (f"={TEMP} > 50 ? '#e57373' : {TEMP} >= 40 ? '#fb8c00' : {TEMP} >= 35 ? '#fbc02d' : '#64b5f6'")


def tank_body(cx, cy, w=22, h=40, x=None, fill="url(#propTank)"):
    x = cx - w / 2 if x is None else x
    return g.svg("rect", x=x, y=cy - h / 2, width=w, height=h, rx=w / 2, **s(1.5, fill=fill))


def tank_current(cx, cy):
    return g.tank_node(cx, cy, "propTank")[1:]


def effect_heater(cx, cy, wire=False):
    """The Effect Heater beside the tank as on the current icon: its two pipes, cold from the tank's bottom into its
    foot and hot from its head back into the tank's top, blue and red while it heats, its body lit then; with wire, a
    heating wire inside it that glows and pulses red while it heats."""
    on = g.BSH_ON
    out = [g.svg("path", d=f"M{cx + 1},{cy + 9} H{cx + 8}", **s(1.4, f"={on} ? '{g.RETURN}' : 'currentColor'")),
           g.svg("path", d=f"M{cx + 11.5},{cy - 6} V{cy - 12} H{cx + 0.5}",
                 **s(1.4, f"={on} ? '{g.SUPPLY}' : 'currentColor'", **{"stroke-linejoin": "round"})),
           g.svg("rect", x=cx + 8, y=cy - 6, width=7, height=18, rx=3.5,
                 **s(1.2, fill=f"={on} ? '{'#ffccbc' if wire else '#ff8a65'}' : 'none'"))]
    if wire:
        out.append(g.svg("path", [g.svg("animate", attributeName="opacity", values="1;0.35;1", dur="1.4s",
                                        repeatCount="indefinite", visible=f"={on}")],
                         d=f"M{cx + 11.5},{cy - 3} l-1.6,2 l3.2,2 l-3.2,2 l3.2,2 l-3.2,2 l3.2,2 l-1.6,1",
                         **s(1.1, f"={on} ? '{g.HEATER_RED}' : '#9e9e9e'")))
    return out


def tank_shell(cx, cy, fill="url(#propTank)"):
    """The current icon's tank."""
    return g.svg("rect", x=cx - 15, y=cy - 17, width=16, height=34, rx=8, **s(1.5, fill=fill))


def tank_1(cx, cy):
    """1: as now, the Effect Heater with a heating wire inside that glows and pulses red while it heats."""
    return [tank_shell(cx, cy), *effect_heater(cx, cy, wire=True)]


def tank_2(cx, cy):
    """2: the tank in layers, warm at the top in its temperature's colour, cooler below."""
    return [tank_shell(cx, cy, "url(#propLayers)"),
            *[g.svg("line", x1=cx - 13, y1=cy + y, x2=cx - 1, y2=cy + y, **s(0.8, opacity="0.5")) for y in (-6, 5)],
            *effect_heater(cx, cy)]


def tank_3(cx, cy):
    """3: the heat pump's coil in the tank, orange while the compressor charges it."""
    coil = g.svg("polyline", points=" ".join(f"{cx + (-3 if i % 2 else -11)},{cy + 11 - 4 * i}" for i in range(6)),
                 **s(1.4, f"={COIL_ON} ? '#fb8c00' : '#9e9e9e'", **{"stroke-linejoin": "round"}))
    return [tank_shell(cx, cy, g.rgba(TANK_C, 0.1)), coil, *effect_heater(cx, cy)]


def tank_4(cx, cy):
    """4: the tank filled from its foot up to its temperature (of 60 °C), in the temperature's colour."""
    level = f"(Math.max(0, Math.min(1, {TEMP} / 60)) * 31)"
    return [g.svg("rect", x=cx - 13.5, width=13, rx=6.5, fill=TANK_TEMP_C, opacity="0.75",
                  y=f"={cy + 15.5} - {level}", height=f"={level}"),
            tank_shell(cx, cy, "none"), *effect_heater(cx, cy)]


def tank_5(cx, cy):
    """5: as now, and heat rising from the Effect Heater in small waves while it heats."""
    dur = "1.2s"
    waves = [g.svg("path", [g.dash_flow(dur, g.BSH_ON, to="-8")], d=f"M{cx + 19 + 3 * i},{cy + 8} q2,-3 0,-6 q-2,-3 0,-6",
                   visible=f"={g.BSH_ON}", **s(1.2, g.HEATER_RED, **{"stroke-dasharray": "2 2"})) for i in range(2)]
    return [tank_shell(cx, cy), *effect_heater(cx, cy), *waves]


TANKS = [("bisher", "Effect Heater daneben", tank_current), ("1", "Heizdraht", tank_1), ("2", "Schichtung", tank_2),
         ("3", "Heizschlange", tank_3), ("4", "Füllstand", tank_4), ("5", "Wärmewellen", tank_5)]


def row_svg(items, node):
    step, y = 92, 48
    parts = [g.svg("defs", [g.grad("propTank", [("0%", g.tank_top, "0.95"), ("100%", "#bbdefb", "0.85")]),
                            g.svg("linearGradient", [g.svg("stop", offset=o, **{"stop-color": c, "stop-opacity": "0.9"})
                                                     for o, c in [("0%", g.tank_top), ("33%", g.tank_top),
                                                                  ("33%", "#ffcc80"), ("66%", "#ffcc80"),
                                                                  ("66%", "#bbdefb"), ("100%", "#bbdefb")]],
                                  id="propLayers", x1="0", y1="0", x2="0", y2="1")])]
    for k, (name, note, build) in enumerate(items):
        x = 46 + step * k
        parts += [*node(x, y), *build(x, y), g.svg_text(x, y + 52, name, 14, "700"),
                  g.svg_text(x, y + 68, note, 11, opacity="0.7")]
        if node is tank_node:
            parts += g.tank_source_badge(x, y)
    svg = g.svg("svg", parts, viewBox=f"0 0 {46 * 2 + step * (len(items) - 1)} 126", width="100%",
                style={"display": "block", "overflow": "visible", "max-width": f"{(46 * 2 + step * 5) * 1.4}px",
                       "margin": "0 auto"})
    box = g.div([svg], **{"padding": "16px 12px"})
    box["config"]["stylesheet"] = "@keyframes flowOrbit { to { transform: rotate(360deg); } }"
    return [box]


def vent_node(x, y):
    return [g.track(x, y), g.flow_orbit((x, y), TEAL, P, f"{P} > 0", 5), g.ring(x, y, TEAL)]


def tank_node(x, y):
    return [*g.hp_orbit((x, y), TANK_C, TANK_ON, g.WATER_PACE, f"{TEMP} / {g.TANK_FULL}"), g.ring(x, y, TANK_C)]


blocks = [g.block(g.row(g.full(g.card("Warmwasserspeicher · Abwandlungen mit Effect Heater",
                                      row_svg(TANKS, tank_node)))))]
page = g.layout_page(UID, {"label": "Vorschläge Icons", "sidebar": True, "order": "0", "icon": "f7:lightbulb"},
                     blocks, datetime.datetime.now())
with open(OUT, "w", encoding="utf-8") as f:
    json.dump({"ui:page": {UID: page["value"]}}, f, ensure_ascii=False)
print(f"page {UID}: {len(TANKS) - 1} tanks -> {OUT}")
