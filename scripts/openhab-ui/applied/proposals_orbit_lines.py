#!/usr/bin/env python3
"""A temporary page `proposals` with ways to animate a node's ring with lines instead of the running dots (user,
2026-10-03), each on three nodes of the energy flow with fixed demo values, so every animation runs: the heat pump,
the battery with its charge as an arc and the air conditioner. The generator removes the page on its next run
(OBSOLETE_PAGES).
Usage: proposals_orbit_lines.py BODY   (writes the REST body for ui_put.py; OPENHAB_JSONDB as for the generator)"""
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
C = round(2 * math.pi * g.ORBIT, 1)  # the ring's length
NODES = [("heat-pump", g.HP_ORANGE, {"power": "1500", "frequency": "48"}, None),
         ("battery", "#7cb342", {"soc": "70"}, 0.7),
         ("air-conditioner", g.AC_BLUE, {"power": "600"}, None)]


def orbit(xy, color, dash, cap, width=None, dur=5.5):
    """The ring's animation: a dashed circle in the node's colour turning clockwise, as flow_orbit does."""
    return g.svg("circle", cx=xy[0], cy=xy[1], r=g.ORBIT, fill="none", stroke=color, **{
        "stroke-width": width or g.RING_W, "stroke-linecap": cap, "stroke-dasharray": dash,
        "style": {"transform-box": "fill-box", "transform-origin": "center",
                  "animation": f"flowOrbit {dur}s linear infinite"}})


VARIANTS = [
    ("bisher", "Punkte", lambda xy, c: orbit(xy, c, f"0 {round(C / g.DOTS, 2)}", "round")),
    ("A", "kurze Striche", lambda xy, c: orbit(xy, c, "6 4", "butt")),
    ("B", "lange Striche", lambda xy, c: orbit(xy, c, "14 7", "butt")),
    ("C", "runde Striche", lambda xy, c: orbit(xy, c, "7 9", "round")),
    ("D", "zwei Bögen", lambda xy, c: orbit(xy, c, f"{round(C * 0.22, 1)} {round(C * 0.28, 1)}", "round")),
    ("E", "ein Bogen", lambda xy, c: orbit(xy, c, f"{round(C * 0.3, 1)} {round(C * 0.7, 1)}", "round", dur=4)),
    ("F", "feine Striche", lambda xy, c: orbit(xy, c, "4 3", "butt", width=2.5)),
]


def drawing():
    row_h, col_w, x0 = 96, 96, 150
    parts = []
    for r, (name, note, build) in enumerate(VARIANTS):
        y = 48 + row_h * r
        parts += [g.svg_text(16, y - 2, name, 15, "700", anchor="start"),
                  g.svg_text(16, y + 16, note, 12, anchor="start", opacity="0.7")]
        for k, (kind, color, props, share) in enumerate(NODES):
            x = x0 + col_w * k
            parts += [g.track(x, y), build((x, y), color)]
            if share:
                parts.append(g.share_orbit((x, y), str(share), color))
            parts.append(g.comp("widget:flow-node", {"kind": kind, "x": x, "y": y,
                                                    **{k_: f"={v}" for k_, v in props.items()}}))
    w, h = x0 + col_w * (len(NODES) - 1) + 50, row_h * len(VARIANTS)
    svg = g.svg("svg", parts, viewBox=f"0 0 {w} {h}", width="100%",
                style={"display": "block", "overflow": "visible", "max-width": f"{round(w * 1.3)}px", "margin": "0 auto"})
    box = g.div([svg], **{"padding": "16px 12px"})
    box["config"]["stylesheet"] = "@keyframes flowOrbit { to { transform: rotate(360deg); } }"
    return [box]


blocks = [g.block(g.row(g.full(g.card("Ring-Animation · Linien statt Punkte", drawing()))))]
page = g.layout_page(UID, {"label": "Vorschläge Ringe", "sidebar": True, "order": "0", "icon": "f7:lightbulb"},
                     blocks, datetime.datetime.now())
with open(OUT, "w", encoding="utf-8") as f:
    json.dump({"ui:page": {UID: page["value"]}}, f, ensure_ascii=False)
print(f"page {UID}: {len(VARIANTS) - 1} variants -> {OUT}")
