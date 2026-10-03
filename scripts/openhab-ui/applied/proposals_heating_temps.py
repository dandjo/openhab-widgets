#!/usr/bin/env python3
"""A temporary page `proposals` with five ways to show the tank's temperature and the leaving water more prominently
in the heating card's two tiles, built from the generator's own parts with live items; the tiles open the heat pump's
quick panel as on the overview. The generator removes the page on its next run (OBSOLETE_PAGES).
Usage: proposals_heating_temps.py BODY   (writes the REST body for ui_put.py; OPENHAB_JSONDB as for the generator)"""
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
# the variants as first shown: the tank titled in full, a second figure for D
FULL = {"Warmwasser": "Warmwasserspeicher"}
CONTEXT = {"Warmwasser": ("Soll", f"={g.disp(g.HPX['tank_set'])}"),
           "Heizung": ("Rücklauf", f"={g.disp(g.HPX['return'])}")}


def specs():
    return [{**spec, "title": FULL.get(spec["title"], spec["title"]), "context": CONTEXT[spec["title"]]}
            for spec in g.heat_specs()]


def pill(on, working, color):
    return g.chips(g.chip(f"={on} ? 'An' : 'Aus'", f"={working} ? '{color}' : '#9e9e9e'"))


def link():
    return g.hp_popup_link(g.TILE_LINK, "heatpump-quick")


def small(text, **style):
    return g.label(text, **{"font-size": "12px", "opacity": "0.7", "white-space": "nowrap", **style})


def big(value, color, size):
    return g.label(value, **{"font-size": f"{size}px", "font-weight": "700", "line-height": f"{size + 4}px",
                             "color": color, "white-space": "nowrap"})


def variant_a(icon, title, on, working, color, name, value, value_color, **_):
    """A: the temperature large under the title, its name small below it, the pill last."""
    return g.tile([icon, g.label(title, **{"font-weight": "600"}),
                   g.div([big(value, value_color, 26), small(name)],
                         **{"display": "flex", "flex-direction": "column", "align-items": "center"}),
                   pill(on, working, color)], None, link())


def variant_b(icon, title, on, working, color, name, value, value_color, **_):
    """B: the temperature as a capsule in its colour on the foot of the icon's ring, the name small under the
    title."""
    capsule = g.label(value, **{"position": "absolute", "left": "50%", "bottom": "-8px", "transform": "translateX(-50%)",
                                "background": value_color, "color": "#ffffff", "font-size": "16px",
                                "font-weight": "700", "padding": "2px 11px", "border-radius": "13px",
                                "white-space": "nowrap", "box-shadow": "0 1px 4px rgba(0, 0, 0, 0.35)"})
    return g.tile([g.div([icon, capsule], **{"position": "relative", "margin-bottom": "8px"}),
                   g.label(title, **{"font-weight": "600"}), small(name, **{"margin-top": "-4px"}),
                   pill(on, working, color)], None, link())


def variant_c(icon, title, on, working, color, name, value, value_color, **_):
    """C: lying, the icon on the left, beside it title, name, the temperature large and the pill; the tank titled
    Warmwasser, so both lie on a desktop; on a phone's narrow tile the texts wrap under the icon."""
    short = {"Warmwasserspeicher": "Warmwasser"}.get(title, title)
    texts = g.div([g.label(short, **{"font-weight": "600", "font-size": "13px"}), small(name),
                   big(value, value_color, 28), g.div([pill(on, working, color)], **{"margin-top": "4px"})],
                  **{"display": "flex", "flex-direction": "column", "align-items": "flex-start", "min-width": "0"})
    t = g.tile([g.div([icon, texts], **{"display": "flex", "flex-wrap": "wrap", "align-items": "center",
                                        "justify-content": "center", "gap": "10px 14px"})], None, link())
    return t


def variant_d(icon, title, on, working, color, name, value, value_color, context, **_):
    """D: as A, the temperature a little larger, with a second figure under it: the tank's setpoint, the inlet
    water."""
    second = g.label(f"='{context[0]} ' + {context[1][1:]}", **{"font-size": "12px", "opacity": "0.7",
                                                                 "white-space": "nowrap"})
    return g.tile([icon, g.label(title, **{"font-weight": "600"}),
                   g.div([small(name, **{"margin-bottom": "-2px"}), big(value, value_color, 28), second],
                         **{"display": "flex", "flex-direction": "column", "align-items": "center"}),
                   pill(on, working, color)], None, link())


def variant_e(icon, title, on, working, color, name, value, value_color, **_):
    """E: the earlier upright tile, the pill showing the temperature instead of An or Aus: filled in the tile's colour
    while switched on, only outlined in it while off; the temperature's name small below."""
    temperature = g.label(value, **{"background": f"={on} ? '{color}' : 'transparent'",
                                    "color": f"={on} ? '#ffffff' : '{color}'", "border": f"1.5px solid {color}",
                                    "border-radius": "12px", "padding": "1px 11px", "font-size": "15px",
                                    "font-weight": "700", "white-space": "nowrap"})
    return g.tile([icon, g.label(title, **{"font-weight": "600"}), g.chips(temperature), small(name)], None, link())


def tiles(builder):
    content = g.div([g.div([builder(**spec) for spec in specs()],
                           **{"display": "grid", "grid-template-columns": "1fr 1fr", "gap": "10px"})],
                    **{"padding": "12px 16px 16px", "font-size": "14px"})
    content["config"]["stylesheet"] = "@keyframes flowOrbit { to { transform: rotate(360deg); } }"
    return [content]


blocks = [g.two(g.card("Vorschlag A · groß unter dem Titel", tiles(variant_a)),
                g.card("Vorschlag B · Kapsel am Ring", tiles(variant_b))),
          g.two(g.card("Vorschlag C · quer", tiles(variant_c)),
                g.card("Vorschlag D · mit zweitem Wert", tiles(variant_d))),
          g.two(g.card("Vorschlag E · Temperatur in der Pille", tiles(variant_e)), g.div([]))]
page = g.layout_page(UID, {"label": "Vorschläge Heizung", "sidebar": True, "order": "0", "icon": "f7:lightbulb"},
                     blocks, datetime.datetime.now())
with open(OUT, "w", encoding="utf-8") as f:
    json.dump({"ui:page": {UID: page["value"]}}, f, ensure_ascii=False)
print(f"page {UID} with five variants -> {OUT}")
