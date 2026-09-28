#!/usr/bin/env python3
"""A temporary page `widget_gallery` for the screenshots of the widget repository: the energy flow's and the
appliances' widgets with fixed demo values, every one of them running, and the controls' small widgets with their
real items. Built from the generator's own parts; the generator removes the page on its next run (OBSOLETE_PAGES).
Usage: widget_gallery.py check|apply   (as root, with openHAB stopped for apply)"""
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(HERE, "dashboard.py")
MODE = sys.argv[1]
sys.argv = [GEN, "check"]  # the generator's module code reads its mode; its main() is not run
ns = {"__file__": GEN, "__name__": "dashboard"}
exec(compile(open(GEN).read().replace("\nmain()\n", "\n"), GEN, "exec"), ns)
g = type("g", (), ns)

UID = "widget_gallery"
SVG_STYLE = {"display": "block", "overflow": "visible"}


def drawing(children, w, h, max_width):
    return g.div([g.svg("svg", children, viewBox=f"0 0 {w} {h}", width="100%", style=SVG_STYLE)],
                 **{"max-width": f"{max_width}px", "margin": "0 auto", "padding": "12px 16px"})


def caption(x, y, text):
    return g.svg_text(x, y, text, 12, opacity="0.7")


NODES = [("pv", 5200, None), ("grid", -800, None), ("home", 2400, None), ("heat-pump", 1500, None),
         ("air-conditioner", 600, None), ("e-car", 2000, None), ("battery", None, 72), ("appliances", 1950, None)]


def nodes_card():
    items = []
    for i, (kind, power, soc) in enumerate(NODES):
        x = 45 + 85 * i
        items += [g.flow_node(kind, (x, 45), None if power is None else str(power), None if soc is None else str(soc)),
                  caption(x, 100, kind)]
    width = 90 + 85 * (len(NODES) - 1)
    return g.card("flow-node", [drawing(items, width, 110, round(width * 1.2))])


def links_card():
    """PV feeds the house, the house charges the car: two links between three nodes, as a flow of one's own."""
    pv, home, car = (50, 45), (220, 45), (390, 45)
    return g.card("flow-link", [drawing([
        g.flow_link(pv[0] + 30, 45, home[0] - 30, 45, "#ffb300", "3200", "true"),
        g.flow_link(home[0] + 30, 45, car[0] - 30, 45, g.ECAR_COLOR, "2000", "true"),
        g.flow_node("pv", pv, "3200"), g.flow_node("home", home, "1200"), g.flow_node("e-car", car, "2000"),
        g.svg_text(pv[0], 97, "3,2 kW", 16, "700"), g.svg_text(home[0], 97, "1,2 kW", 16, "700"),
        g.svg_text(car[0], 97, "2,0 kW", 16, "700")], 440, 110, 560)])


def rings_card():
    return g.card("flow-share-ring", [drawing([g.flow_share_ring((40, 40), "Self-consumption", "72", "100"),
                                               g.flow_share_ring((230, 40), "Self-sufficiency", "41", "100")],
                                              360, 80, 480)])


def appliance_icons_card():
    demo = [("washer", True, 45, "läuft · 45 %"), ("dryer", True, 70, "läuft · 70 %"),
            ("dish-washer", True, None, "läuft, ohne Fortschritt"), ("washer", False, None, "aus")]
    icons = []
    for kind, running, progress, text in demo:
        cfg = {"kind": kind, "running": running}
        if progress is not None:
            cfg["progress"] = progress
        icons.append(g.div([g.comp("widget:appliance-icon", cfg), g.label(text, **{"font-size": "12px", "opacity": "0.7"})],
                           **{"display": "flex", "flex-direction": "column", "align-items": "center", "gap": "6px"}))
    return g.card("appliance-icon", [g.div(icons, **{"display": "flex", "justify-content": "space-around",
                                                      "flex-wrap": "wrap", "gap": "12px", "padding": "12px 16px 16px"})])


def column(children):
    return g.div(children, **{"display": "flex", "flex-direction": "column", "gap": "10px", "padding": "12px 16px 16px"})


def pills_card():
    return g.card("power-pill · boost-pill · boost-button", [column([
        g.ac_power(), g.dhw_boost(), g.ac_boost(),
        g.div([g.boost_button("Boost", "pyaltherma_dhw_powerful", g.HP_ORANGE)], **{"width": "104px"})])])


def bars_card():
    return g.card("state-bar", [column([
        g.smart_grid_bar(), g.ac_mode_bar(),
        g.state_bar("faikout_perfera_fan", g.AC_FAN, g.AC_BLUE),
        g.div([g.state_bar("esplyfterl_level", [("1", "1"), ("2", "2"), ("3", "3")], g.VENT_TEAL)],
              **{"width": "104px"})])])


def tiles_card():
    tiles = g.control_tiles()[0]["slots"]["default"][3]
    return g.card("switch-tile", [g.div([tiles], **{"padding": "4px 16px 14px"})])


def gallery_page(now):
    blocks = [g.two(nodes_card(), links_card()), g.two(rings_card(), appliance_icons_card()),
              g.two(pills_card(), bars_card()), g.one(tiles_card())]
    return g.layout_page(UID, {"label": "Widget-Galerie", "sidebar": False}, blocks, now)


name = "uicomponents_ui_page.json"
data, enc = g.m.detect(g.m.DB + name)
data.pop(UID, None)
data = g.m.insert(data, UID, gallery_page(datetime.datetime.now()))
text = g.m.encode(data, *enc)
print(f"{name}: encoder html={enc[0]} newline={enc[1]} ok; page {UID}")
if MODE == "apply":
    with open(g.m.DB + name, "w", encoding="utf-8") as f:
        f.write(text)
    print("written")
