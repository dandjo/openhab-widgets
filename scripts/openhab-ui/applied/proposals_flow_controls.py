#!/usr/bin/env python3
"""A temporary page `proposals` with four ways to show the energy flow and the controls in one card, each with the
flow at full size and every main control, timers included, one or two taps away:

A  controls at the nodes: badges on heat pump and air conditioner (boost, on/off, the timer as a ring of its own around
   the air conditioner), in a star a little wider than the overview's, so ring and texts have room; a tap on either
   opens a compact popup with its quick controls; ventilation and the switches in a slim row under the flow.
B  the flow with a device choice: a tap on a node or a tab shows that device's quick controls inside the card.
C  the flow with a control list: one line per device beside the flow (below it on a phone), the air conditioner's
   mode as a bar under its line, timers as chips that open their slider in a compact popup.
E  a poster of tiles: PV, battery and grid above the house, the consumers below it with their main actions, every flow
   as a labelled arrow, the day's balance at the bottom.

Built from the generator's own parts, with real items: the controls switch for real. The quick panels are widgets
tagged generated and proposal, so the generator's next run removes them, and the page too (OBSOLETE_PAGES).
Usage: proposals_flow_controls.py OUTDIR   writes the REST bodies: OUTDIR/page.json and OUTDIR/widget-<uid>.json"""
import copy
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(os.path.dirname(HERE), "dashboard.py")
OUT = sys.argv[1]
sys.argv = [GEN, "check"]  # the generator's module code reads its mode; its main() is not run
SRC = open(GEN).read().replace("\nmain()\n", "\n")


def load(src):
    ns = {"__file__": GEN, "__name__": "dashboard"}
    exec(compile(src, GEN, "exec"), ns)
    return type("g", (), ns)


g = load(SRC)
# the generator once more with a wider star for A: 20 more units from the house to every node, so the grey rings
# around the nodes, the badges and the texts keep clear of each other; the texts below the nodes 10 lower. PV moves
# to the eighth place, top left, its texts to the left of it, where the line to the house leaves them free, as the
# ventilation's stand to the right of it in the top place
WIDER = {"SPOKE = 176  # distance of every node from the house": "SPOKE = 196",
         "FLOW_W, FLOW_H = 470, 460": "FLOW_W, FLOW_H = 510, 516", "HOME_XY = (245.5, 208.3)": "HOME_XY = (265.5, 236)",
         "node[1] + 52": "node[1] + 62", "node[1] + 68 + 15 * i": "node[1] + 78 + 15 * i",
         "PV_XY, HP_XY, AC_XY, ECAR_XY, APPL_XY, BATT_XY, GRID_XY = (at(-90 + TURN + k * STEP) for k in range(7))":
             "HP_XY, AC_XY, ECAR_XY, APPL_XY, BATT_XY, GRID_XY, PV_XY = (at(-90 + TURN + k * STEP) for k in range(1, 8))",
         "svg_text(PV_XY[0] + 42, PV_XY[1] + 1, f\"={kw(PV)}\", 18, \"700\", anchor=\"start\")":
             "svg_text(PV_XY[0] - 50, PV_XY[1] + 1, f\"={kw(PV)}\", 18, \"700\", anchor=\"end\")",
         "svg_text(PV_XY[0] + 42, PV_XY[1] + 18, f\"={disp('huawei_inverter_e_day')} + ' heute'\", 12, anchor=\"start\",":
             "svg_text(PV_XY[0] - 50, PV_XY[1] + 18, f\"={disp('huawei_inverter_e_day')} + ' heute'\", 12, anchor=\"end\","}
for a, b in WIDER.items():
    assert a in SRC, a
gw = load(__import__("functools").reduce(lambda t, ab: t.replace(*ab), WIDER.items(), SRC))

UID = "proposals"
HP_C, AC_C, VENT_C, PLUG_C = g.HP_ORANGE, g.AC_BLUE, g.VENT_TEAL, "#78909c"
AC_ON, BOOST_ON = g.AC_ON_STATE, g.is_on("pyaltherma_dhw_powerful")
M_AC, M_VENT = g.num("air_conditioning_timer"), g.num("ventilation_timer")
NARROW = g.NARROW
# a quick panel opens as a compact popup instead of Framework7's 630 × 630 px; MainUI puts the widget's style on the
# popup's page, where the mark tells it from other popups; ":root" keeps the rule unscoped while the panel is shown
QUICK_SIZES = {"panel": ("420px", "min(640px, calc(100vh - 64px))"), "timer": ("420px", "240px")}
QUICK_RULES = "\n".join(f':root .popup:has(> .oh-popup[style*="--quick-popup: {k}"]) {{ --f7-popup-tablet-width: {w}; '
                        f"--f7-popup-tablet-height: {h}; }}" for k, (w, h) in QUICK_SIZES.items())


def quick_root(children, title, size="panel"):
    root = g.div(children)
    root["config"].update({"label": title, "style": {"--quick-popup": size}, "stylesheet": QUICK_RULES})
    return root


BATTERY = g.BATTERY_GREEN


def kw_text(expr):
    """A power in W as kW to three decimals, with a decimal comma."""
    return f"({expr} / 1000).toFixed(3).replace('.', ',') + ' kW'"


def hm(m):
    """Minutes as 1:30 h, or 45 min below an hour; MainUI's expressions know no String()."""
    return (f"({m} >= 60 ? Math.floor({m} / 60) + ':' + (Math.floor({m} % 60) < 10 ? '0' : '') + "
            f"Math.floor({m} % 60) + ' h' : Math.round({m}) + ' min')")


# ---- quick panels: the main controls of one device and a way to its page

def details_button(page, color):
    return g.div([g.comp("oh-button", {"text": "Alle Details", "action": "popup", "actionModal": f"page:{page}",
                                       "outline": True, "small": True,
                                       "style": {"color": color, "border-color": color, "width": "auto",
                                                 "padding": "0 12px"}})],
                 **{"display": "flex", "justify-content": "flex-end", "padding-top": "4px"})


def quick(icon, title, color, state, children, page):
    """A device's quick controls under a small head; the popup's bar names the device, inline the head does."""
    head = g.div([g.div([g.comp("oh-icon", {"icon": icon, "width": 20, "height": 20})],
                        **{"width": "34px", "height": "34px", "flex": "0 0 auto", "border-radius": "50%",
                           "display": "flex", "align-items": "center", "justify-content": "center",
                           "background": f"color-mix(in srgb, {color} 22%, transparent)"}),
                  g.div([g.label(title, **{"font-size": "15px", "font-weight": "600"}),
                         g.label(f"={state}", **{"font-size": "12px", "opacity": "0.7", "white-space": "nowrap",
                                                 "overflow": "hidden", "text-overflow": "ellipsis"})],
                        **{"display": "flex", "flex-direction": "column", "min-width": "0"})],
                 **{"display": "flex", "align-items": "center", "gap": "10px", "padding-bottom": "4px"})
    body = g.div([head, *children, details_button(page, color)],
                 **{"display": "flex", "flex-direction": "column", "gap": "6px", "padding": "12px 14px"})
    return quick_root([body], title)


def hp_quick():
    state = f"'Speicher ' + {g.disp(g.HPX['tank'])} + ' · ' + {g.kw(g.HPX['power'])}"
    return quick("material:heat_pump", "Wärmepumpe", HP_C, state,
                 [g.dhw_boost(), g.operation_section(row=True), g.dhw_setpoint(row=True)], "heatpump")


def ac_quick():
    state = (f"({AC_ON} ? 'An · ' : 'Aus · ') + {g.disp('faikout_perfera_mode')} + ' · Raum ' + "
             f"{g.disp('faikout_perfera_temperature')}")
    return quick("material:ac_unit", "Klimaanlage", AC_C, state,
                 [g.ac_power(), g.ac_mode_section(row=True), g.ac_setpoint(row=True), g.ac_timer(row=True),
                  g.ac_boost()], "air_conditioning")


def vent_quick():
    state = f"'Stufe ' + {g.disp('esplyfterl_level')} + ' · CO₂ ' + {g.disp('netatmo_weatherstation_co2')}"
    level = g.section("material:air", "Stufe", VENT_C, [g.state_bar("esplyfterl_level", g.VENT_LEVELS, VENT_C)],
                      row=True)
    return quick("material:air", "Lüftung", VENT_C, state,
                 [level, g.vent_timer(row=True),
                  g.switch_row("Automatik", "material:tune", "ventilation_management", VENT_C)], "ventilation")


def timer_only(slider, title):
    return lambda: quick_root([g.div([slider()], **{"padding": "8px 14px 10px"})], title, "timer")


QUICK = {"proposal-hp-quick": hp_quick, "proposal-ac-quick": ac_quick, "proposal-vent-quick": vent_quick,
         "proposal-ac-timer": timer_only(lambda: g.ac_timer(row=True), "Klimaanlage · Timer"),
         "proposal-vent-timer": timer_only(lambda: g.vent_timer(row=True), "Lüftung · Timer")}
INSTANCES = {uid: g.role_widget(uid, builder) for uid, builder in QUICK.items()}  # widget:<uid> with its items


def quick_link(uid, **style):
    """A transparent link that opens the quick panel uid as a compact popup. A popover beside the node would be nicer,
    but MainUI 5.3 opens every popover in the window's top left corner: its action loses the clicked element."""
    inst = INSTANCES[uid]
    return g.comp("oh-link", {"action": "popup", "actionModal": inst["component"],
                              "actionModalConfig": dict(inst["config"]),
                              "style": {"position": "absolute", "display": "block", **style}})


# ---- the flow, its badges and the small round switches

def flow_with(links, extra_svg, m=g, edit=None):
    """The energy flow of the generator m with other links over its nodes and more drawn into its svg; edit may change
    the svg's own children first."""
    f = copy.deepcopy(m.flow)
    inner = f["slots"]["default"][0]
    drawing = inner["slots"]["default"][0]
    if edit:
        edit(drawing["slots"]["default"])
    drawing["slots"]["default"].extend(extra_svg)
    inner["slots"]["default"] = [drawing, *links]
    return f


def node_box(xy, size=68, m=g):
    cx, cy = xy
    return {"border-radius": "50%", "left": f"{(cx - size / 2) / m.FLOW_W * 100:.2f}%",
            "top": f"{(cy - size / 2) / m.FLOW_H * 100:.2f}%", "width": f"{size / m.FLOW_W * 100:.2f}%",
            "height": f"{size / m.FLOW_H * 100:.2f}%"}


def page_links(skip, m=g):
    return [m.node_link(cx, cy, p) for cx, cy, p in m.NODE_POPUPS if p not in skip]


def glyph(x, y, name, size, fill):
    """A Material Icons glyph in the svg, by its ligature."""
    return g.svg("text", x=x, y=y, content=name, fill=fill, **{
        "font-size": size, "text-anchor": "middle", "dominant-baseline": "central",
        "style": {"font-family": "'Material Icons'", "font-feature-settings": "'liga'"}})


def badge_at(x, y, name, color, on, r=12):
    """A small round badge with a glyph (name may be an expression): filled in the colour while on, only tinted with
    it while off; an opaque disc below keeps the ring it sits on from showing through."""
    return g.svg("g", [g.svg("circle", cx=x, cy=y, r=r, style={"fill": "var(--f7-card-bg-color, #fff)"}),
                       g.svg("circle", cx=x, cy=y, r=r, fill=f"={on} ? '{color}' : '{g.rgba(color, 0.14)}'",
                             stroke=color, **{"stroke-width": 2}),
                       glyph(x, y + 0.5, name, round(r * 1.25), f"={on} ? '#ffffff' : '{color}'")])


def node_badge(xy, name, color, on):
    return badge_at(xy[0] + 23, xy[1] - 23, name, color, on)


def timer_ring(xy, m, high, color, r=36, width=3, track=False):
    """The time left as an arc around a node, full at high minutes, from the top clockwise; with track the whole
    circle faintly under it while the timer runs."""
    c = round(2 * 3.14159265 * r, 1)
    arc = g.svg("circle", visible=f"={m} > 0", cx=xy[0], cy=xy[1], r=r, fill="none", stroke=color,
                transform=f"rotate(-90 {xy[0]} {xy[1]})", **{
                    "stroke-width": width, "stroke-linecap": "round", "opacity": "0.9",
                    "stroke-dasharray": f"=(Math.min(1, {m} / {high}) * {c}).toFixed(1) + ' {c}'"})
    if not track:
        return arc
    return g.svg("g", [g.svg("circle", visible=f"={m} > 0", cx=xy[0], cy=xy[1], r=r, fill="none",
                             stroke="rgba(127, 127, 127, 0.22)", **{"stroke-width": width}), arc])


def round_switch(title, icon, item, color, value=None):
    """A plug as a round button with its name, power and today's energy below; a tap switches it, tinted while on."""
    on = f"items.{item}.state === 'ON'"
    energy = g.num(item.replace("_switch", "_energy_today"))
    button = g.div([g.comp("oh-icon", {"icon": icon, "width": 22, "height": 22}), g.toggle_link(item, "50%")],
                   **{"position": "relative", "width": "44px", "height": "44px", "border-radius": "50%",
                      "display": "flex", "align-items": "center", "justify-content": "center",
                      "background": f"={on} ? 'color-mix(in srgb, {color} 28%, transparent)' : "
                                    "'rgba(127, 127, 127, 0.1)'",
                      "box-shadow": f"={on} ? 'inset 0 0 0 2px {color}' : 'none'"})
    small = {"font-size": "10px", "white-space": "nowrap", "line-height": "13px"}
    lines = [g.label(title, **{**small, "opacity": "0.75", "max-width": "64px", "overflow": "hidden",
                               "text-overflow": "ellipsis"})]
    if value:
        lines += [g.label(value, **{**small, "font-weight": "700"}),
                  g.label(f"={g.fixed(energy, 2)} + ' kWh'", **{**small, "opacity": "0.6"})]
    return g.div([button, *lines], **{"display": "flex", "flex-direction": "column", "align-items": "center",
                                      "gap": "2px", "width": "62px"})


SHORT = {"Kaffeemaschine": "Kaffee", "Fahrradakkus": "E-Bikes", "Terrassenlicht": "Terrasse"}  # fit under a button


def switch_row():
    return g.div([round_switch(SHORT.get(t, t), icon, item, color, value) for t, icon, item, color, value in g.SWITCHES],
                 **{"display": "flex", "flex-wrap": "wrap", "justify-content": "center", "gap": "4px 6px"})


def timer_chip(m, high, color, uid):
    """A timer as a small ring with the time left below; a tap opens its slider in a compact popup."""
    c = round(2 * 3.14159265 * 17, 1)
    ring_ = g.svg("svg", [g.svg("circle", cx=20, cy=20, r=17, fill="none", stroke="rgba(127, 127, 127, 0.25)",
                                **{"stroke-width": 3}),
                          g.svg("circle", cx=20, cy=20, r=17, fill="none", stroke=color, transform="rotate(-90 20 20)",
                                **{"stroke-width": 3, "stroke-linecap": "round",
                                   "stroke-dasharray": f"=(Math.min(1, {m} / {high}) * {c}).toFixed(1) + ' {c}'"}),
                          glyph(20, 20, "timer", 16, f"={m} > 0 ? '{color}' : 'currentColor'")],
                  viewBox="0 0 40 40", width=40, height=40, style={"display": "block"})
    text = g.label(f"={m} > 0 ? {hm(m)} : 'Timer'", **{"font-size": "10px", "opacity": "0.75", "white-space": "nowrap"})
    return g.div([ring_, text, quick_link(uid, inset="0", **{"border-radius": "10px"})],
                 **{"position": "relative", "display": "flex", "flex-direction": "column", "align-items": "center",
                    "gap": "1px", "flex": "0 0 auto", "width": "48px", "z-index": "2"})


def caption(text):
    return g.label(text, **{"font-size": "12px", "opacity": "0.6", "padding": "0 16px 12px", "line-height": "17px"})


# ---- A: controls at the nodes

ORBIT = 38  # the grey ring around every node, clear of its own ring (30) and of the texts below; timers fill it
VENT_POWER = g.num("ventilation_power")


def vent_node(xy, m=gw):
    """The ventilation as a node of the star: a ring in its colour with the air glyph, swaying while it runs."""
    x, y = xy
    sway = g.svg("animateTransform", attributeName="transform", type="translate", values="-2 0;2 0;-2 0",
                 dur=f"=({g.num('esplyfterl_level')} >= 3 ? '1.2s' : {g.num('esplyfterl_level')} >= 2 ? '2s' : '3s')",
                 repeatCount="indefinite", visible=f"={VENT_POWER} > 5")
    return g.svg("g", [m.ring(x, y, VENT_C), g.svg("g", [glyph(x, y, "air", 30, VENT_C), sway])])


def a_edit(children, m=gw):
    """The wider star's svg for A: the ventilation as its top node with its link from the house; the share rings
    and the house's values leave the star for the line below it, as no wedge between eight ringed nodes holds them;
    the air conditioner's and the ventilation's second line shows the time left while their timer runs."""
    vxy = m.at(-90 + m.TURN)
    keep = []
    for c in children:
        cfg = c.get("config", {})
        if c.get("component") == "widget:flow-share-ring" or cfg.get("x") == m.HOUSE_LABEL_X:
            continue
        if c.get("component") == "text" and cfg.get("x") == m.AC_XY[0] and cfg.get("y") == m.AC_XY[1] + 78:
            cfg["content"] = f"={M_AC} > 0 ? 'Timer ' + {hm(M_AC)} : ({cfg['content'][1:]})"
            cfg["fill"] = f"={M_AC} > 0 ? '{AC_C}' : 'currentColor'"
            cfg["opacity"] = f"={M_AC} > 0 ? '1' : '0.7'"
        keep.append(c)
    # its texts to the right of it, as PV's stood there: below it the line to the house would cross them
    vx, vy = vxy
    children[:] = [*m.spoke(vxy, VENT_C, VENT_POWER, "false", threshold=5), *keep, vent_node(vxy, m),
                   m.svg_text(vx + 50, vy + 1, f"={kw_text(VENT_POWER)}", 18, "700", anchor="start"),
                   m.svg_text(vx + 50, vy + 18, "", 12, anchor="start", opacity="0.7")]
    # the ventilation's second line: its level, or the time left
    children[-1]["config"].update({
        "content": f"={M_VENT} > 0 ? 'Timer ' + {hm(M_VENT)} : 'Stufe ' + {g.disp('esplyfterl_level')}",
        "fill": f"={M_VENT} > 0 ? '{VENT_C}' : 'currentColor'", "opacity": f"={M_VENT} > 0 ? '1' : '0.7'"})


HP_DEFROST = f"items.{g.HPX['defrost']}.state === 'ON'"
# what the heat pump does: defrosting, else what its valve serves; the badge fills while it draws more than 50 W
HP_OPERATION = f"={HP_DEFROST} ? 'ac_unit' : {g.DHW_MODE} ? 'shower' : 'local_fire_department'"


def flow_orbit(xy, color, power, toward, threshold, unless=None):
    """A node's grey ring while power flows through it: dots in its colour run round, clockwise while the power
    flows towards the house, the other way while it flows away, a little faster the more it is. A CSS animation, not
    SMIL: a changed duration does not restart it. unless hides it, e.g. while a timer fills the ring."""
    p = f"Math.abs({power})"
    dur = f"({p} < 300 ? 9 : {p} < 1000 ? 7 : {p} < 2500 ? 5.5 : 4)"
    c = round(2 * 3.14159265 * ORBIT, 1)
    shown = f"={p} > {threshold}" + (f" && !({unless})" if unless else "")
    return g.svg("circle", visible=shown, cx=xy[0], cy=xy[1], r=ORBIT, fill="none", stroke=color, **{
        "stroke-width": 3, "stroke-linecap": "round", "stroke-dasharray": f"0 {round(c / 24, 2)}",
        "style": {"transform-box": "fill-box", "transform-origin": "center",
                  "animation": f"='propOrbitSpin ' + {dur} + 's linear infinite' + (({toward}) ? '' : ' reverse')"}})


TILE_BG = "rgba(127, 127, 127, 0.08)"


def info_tiles():
    """The house's power and energy today, today's self-consumption and self-sufficiency, as three small cards under
    the star; the house's opens its popup. Three abreast, on a phone the house above the two rings."""
    home = g.div([g.comp("oh-icon", {"icon": "material:home", "width": 24, "height": 24,
                                     "style": {"color": "#1e88e5", "flex": "0 0 auto"}}),
                  g.div([g.label(f"={g.kw(g.HOME)}", **{"font-size": "16px", "font-weight": "700",
                                                        "line-height": "20px", "white-space": "nowrap"}),
                         g.label(g.kwh(g.num("home_ec_day")), **{"font-size": "11px", "opacity": "0.7",
                                                                 "white-space": "nowrap"})],
                        **{"display": "flex", "flex-direction": "column", "min-width": "0"}),
                  g.comp("oh-link", {"action": "popup", "actionModal": "page:flow_home",
                                     "style": {"position": "absolute", "inset": "0", "display": "block",
                                               "border-radius": "12px"}})],
                 **{"position": "relative", "display": "flex", "align-items": "center", "gap": "8px"})

    def ring_tile(ring):
        return g.svg("svg", [g.flow_share_ring((24, 25), *ring)], viewBox="0 0 150 50", width="100%",
                     style={"display": "block", "overflow": "visible", "max-width": "170px"})

    tile = lambda child, **extra: g.div([child], **{"padding": "8px 10px", "border-radius": "12px",
                                                    "background": TILE_BG, "min-width": "0", "display": "flex",
                                                    "align-items": "center", **extra})
    # a phone: the house across the row, the two rings side by side below it
    return g.div([tile(home, **{"grid-column": f"={NARROW} ? '1 / -1' : 'auto'"}),
                  tile(ring_tile(g.SELF_CONSUMPTION)), tile(ring_tile(g.SELF_SUFFICIENCY))],
                 **{"display": "grid", "grid-template-columns": f"={NARROW} ? 'repeat(2, minmax(0, 1fr))' : "
                                                               "'repeat(3, minmax(0, 1fr))'", "gap": "8px"})


def switch_card(title, icon, item, color, value):
    """A plug as a small card, like the overview's switch tiles and in their type sizes: icon and An or Aus, name,
    power and today's energy; a tap anywhere switches it, tinted and outlined in its colour while on."""
    on = f"items.{item}.state === 'ON'"
    energy = g.num(item.replace("_switch", "_energy_today"))
    line = {"white-space": "nowrap", "overflow": "hidden", "text-overflow": "ellipsis"}
    return g.div([g.div([g.comp("oh-icon", {"icon": icon, "width": 22, "height": 22}),
                         g.label(f"={on} ? 'An' : 'Aus'", **{"font-size": "11px", "font-weight": "700",
                                                             "opacity": "0.7"})],
                        **{"display": "flex", "justify-content": "space-between", "align-items": "flex-start"}),
                  g.label(title, **{**line, "font-size": "13px", "font-weight": "600", "margin-top": "5px",
                                    "line-height": "16px"}),
                  g.label(value, **{**line, "font-size": "12px", "opacity": "0.7", "line-height": "15px"}),
                  g.label(f"={g.fixed(energy, 2)} + ' kWh'", **{**line, "font-size": "11px", "opacity": "0.55",
                                                                  "line-height": "14px"}),
                  g.toggle_link(item, "12px")],
                 **{"--tile-color": color, "position": "relative", "padding": "8px 9px", "border-radius": "12px",
                    "min-width": "0", "display": "flex", "flex-direction": "column",
                    "background": f"={on} ? 'color-mix(in srgb, var(--tile-color) 20%, transparent)' : '{TILE_BG}'",
                    "box-shadow": f"={on} ? 'inset 0 0 0 1.5px color-mix(in srgb, var(--tile-color) 60%, "
                                  "transparent)' : 'none'"})


def switch_cards():
    """The switches in a row, three abreast on a phone, where five would leave too little width for the type."""
    return g.div([switch_card(SHORT.get(t, t), icon, item, color, value) for t, icon, item, color, value in g.SWITCHES],
                 **{"display": "grid", "gap": "6px",
                    "grid-template-columns": f"={NARROW} ? 'repeat(3, minmax(0, 1fr))' : "
                                             f"'repeat({len(g.SWITCHES)}, minmax(0, 1fr))'"})


def proposal_a():
    m = gw
    vxy = m.at(-90 + m.TURN)
    nodes = [m.PV_XY, m.GRID_XY, m.HP_XY, m.AC_XY, m.BATT_XY, m.ECAR_XY, m.APPL_XY, vxy]
    box = 2 * ORBIT + 8
    links = [*page_links({"heatpump", "air_conditioning"}, m),
             quick_link("proposal-hp-quick", **node_box(m.HP_XY, box, m=m)),
             quick_link("proposal-ac-quick", **node_box(m.AC_XY, box, m=m)),
             quick_link("proposal-vent-quick", **node_box(vxy, box, m=m))]
    d = round(ORBIT / 2 ** 0.5, 1)  # badges sit on the grey ring: upper right, or upper left where a timer's arc ends
    ax, ay = m.AC_XY
    vx, vy = vxy
    rings = [g.svg("circle", cx=x, cy=y, r=ORBIT, fill="none", stroke="rgba(127, 127, 127, 0.28)",
                   **{"stroke-width": 3}) for x, y in [*nodes, m.HOME_XY]]
    level = g.svg("g", [g.svg("circle", cx=round(vx - d, 1), cy=round(vy - d, 1), r=12, fill=VENT_C),
                        g.svg("text", x=round(vx - d, 1), y=round(vy - d, 1), content="=items.esplyfterl_level.state",
                              fill="#ffffff", **{"font-size": 13, "font-weight": "700", "text-anchor": "middle",
                                                 "dominant-baseline": "central"})])
    batt, grid = g.num(g.BATT), g.num(g.GRID)
    orbits = [flow_orbit(m.PV_XY, "#ffb300", g.num(g.PV), "true", 10),
              flow_orbit(m.GRID_XY, g.GRID_COLOR, grid, f"{grid} > 0", 10),
              flow_orbit(m.BATT_XY, BATTERY, batt, f"{batt} > 0", 10),
              flow_orbit(m.HP_XY, HP_C, g.num(g.HP), "false", g.HP_ON),
              flow_orbit(m.ECAR_XY, g.ECAR_COLOR, g.num(g.ECAR), "false", g.ECAR_ON),
              flow_orbit(m.APPL_XY, g.APPL_COLOR, g.APPL_POWER, "false", g.APPL_ON),
              flow_orbit(m.HOME_XY, "#1e88e5", g.num(g.HOME), "true", 10),
              # air conditioner and ventilation the same while their timer is off; a running timer fills the ring
              flow_orbit(m.AC_XY, AC_C, g.AC_FLOW, "false", g.AC_ON, f"{M_AC} > 0"),
              flow_orbit(vxy, VENT_C, VENT_POWER, "false", 5, f"{M_VENT} > 0")]
    extras = [*rings, *orbits,
              timer_ring(m.AC_XY, M_AC, 720, AC_C, r=ORBIT, width=3.5),
              timer_ring(vxy, M_VENT, 360, VENT_C, r=ORBIT, width=3.5),
              badge_at(round(m.HP_XY[0] + d, 1), round(m.HP_XY[1] - d, 1), HP_OPERATION, HP_C, g.HP_RUNNING),
              badge_at(round(ax - d, 1), round(ay - d, 1), "power_settings_new", AC_C, AC_ON), level]
    strip = g.div([info_tiles(), switch_cards()], **{"display": "flex", "flex-direction": "column", "gap": "10px",
                                                      "padding": "8px 12px 14px"})
    star = flow_with(links, extras, m, a_edit)
    star["config"]["stylesheet"] = "@keyframes propOrbitSpin { to { transform: rotate(360deg); } }"
    return g.card("Vorschlag A · Steuerung am Knoten", [
        star, strip,
        caption("Acht Knoten im Stern, die Lüftung oben, PV oben links; jeder Kreis hat einen grauen Ring, den bei Klimaanlage "
                "und Lüftung der Timer füllt, die Werte stehen darunter (bei Lüftung und PV daneben, frei von ihrer "
                "Linie zum Haus), während eines Timers mit der Restzeit. "
                "Sonst laufen Punkte in der Farbe des Knotens um den Ring, solange Strom fließt, im "
                "Uhrzeigersinn zum Haus hin, gegen ihn vom Haus weg. Abzeichen zeigen den Betrieb der Wärmepumpe "
                "(Heizung, Warmwasser oder Abtauen, gefüllt solange sie läuft), An/Aus der Klimaanlage (gefüllt oder "
                "nur getönt) und die Lüfterstufe. Ein Tipp auf Wärmepumpe, Klimaanlage oder Lüftung "
                "öffnet ihre Schnellbedienung mit Timer und dem Weg zur Hauptseite als kleines Popup; die anderen "
                "Knoten öffnen ihre Seite wie bisher. Hausverbrauch, Eigenverbrauch und Autarkie stehen als Karten unter "
                "dem Stern, da zwischen acht Knoten mit Ring kein Platz am Haus bleibt; darunter die Schalter als kleine "
                "Karten mit Leistung und Energie von heute.")])


# ---- B: the flow with a device choice

SEL = f"(vars.flowSel || ({AC_ON} ? 'ac' : 'hp'))"
TABS = [("hp", "Wärmepumpe", HP_C), ("ac", "Klima", AC_C), ("vent", "Lüftung", VENT_C), ("plugs", "Schalter", PLUG_C)]


def select_link(xy, key):
    return g.comp("oh-link", {"action": "variable", "actionVariable": "flowSel", "actionVariableValue": key,
                              "style": {"position": "absolute", "display": "block", **node_box(xy)}})


def proposal_b():
    links = [*page_links({"heatpump", "air_conditioning"}), select_link(g.HP_XY, "hp"), select_link(g.AC_XY, "ac")]
    marks = [g.svg("circle", visible=f"={SEL} === '{k}'", cx=xy[0], cy=xy[1], r=37, fill="none", stroke=c,
                   **{"stroke-width": 2.5, "stroke-dasharray": "5 4", "opacity": "0.9"})
             for k, xy, c in (("hp", g.HP_XY, HP_C), ("ac", g.AC_XY, AC_C))]
    active = f"{SEL} === '{{}}'"
    buttons = [g.comp("oh-button", {"text": text, "action": "variable", "actionVariable": "flowSel",
                                    "actionVariableValue": key, "small": True, "active": f"={active.format(key)}",
                                    "style": {"font-size": "12px", "flex": "1 1 auto", "width": "auto",
                                              "padding": "0 6px",
                                              "background-color": f"=({active.format(key)}) ? '{color}' : ''",
                                              "color": f"=({active.format(key)}) ? '#ffffff' : ''"}})
               for key, text, color in TABS]
    bar = g.div([g.comp("f7-segmented", {"strong": True, "stylesheet": g.BY_TEXT_BAR, "style": {"width": "100%"}},
                        default=buttons)], **{"padding": "0 12px"})
    panels = [g.div([INSTANCES[f"proposal-{k}-quick"]], visible=f"={SEL} === '{k}'") for k in ("hp", "ac", "vent")]
    tiles = [g.switch_tile(t, icon, item, color, value) for t, icon, item, color, value in g.SWITCHES]
    panels.append(g.div([g.div(tiles, **{"display": "grid", "grid-template-columns": "repeat(auto-fill, minmax(110px, 1fr))",
                                         "gap": "8px", "padding": "12px 14px"})], visible=f"={SEL} === 'plugs'"))
    body = g.comp("oh-context", {"variables": {"flowSel": ""}},
                  default=[g.div([flow_with(links, marks), bar, *panels], **{"display": "flex", "flex-direction": "column"})])
    return g.card("Vorschlag B · Fluss mit Gerätewahl", [
        body,
        caption("Unter dem Fluss wählt eine Leiste das Gerät; ein Tipp auf Wärmepumpe oder Klimaanlage im Fluss wählt "
                "sie auch und markiert den Knoten. Die Bedienung des gewählten Geräts steht mit Timer direkt in der "
                "Karte, die Hauptseite eine Schaltfläche weiter. Ohne Wahl zeigt sie die Klimaanlage, solange sie "
                "läuft, sonst die Wärmepumpe.")])


# ---- C: the flow with a control list

def control_line(icon, title, state, color, active, actions, page, below=None):
    """One device in one line: icon, name and state, its actions on the right, and a second row of controls below
    where it has one; a tap elsewhere opens its page."""
    top = g.div([g.div([g.comp("oh-icon", {"icon": icon, "width": 20, "height": 20})],
                       **{"width": "36px", "height": "36px", "flex": "0 0 auto", "border-radius": "50%",
                          "display": "flex", "align-items": "center", "justify-content": "center",
                          "background": f"={active} ? 'color-mix(in srgb, {color} 25%, transparent)' : "
                                        "'rgba(127, 127, 127, 0.12)'"}),
                 g.div([g.label(title, **{"font-size": "14px", "font-weight": "600"}),
                        g.label(f"={state}", **{"font-size": "11px", "opacity": "0.7", "white-space": "nowrap",
                                                "overflow": "hidden", "text-overflow": "ellipsis"})],
                       **{"flex": "1", "min-width": "0", "display": "flex", "flex-direction": "column"}),
                 g.div(actions, **{"display": "flex", "align-items": "center", "gap": "6px", "position": "relative",
                                   "z-index": "2", "flex": "0 0 auto"})],
                **{"display": "flex", "align-items": "center", "gap": "10px"})
    rows = [top] + ([g.div([below], **{"position": "relative", "z-index": "2"})] if below else [])
    return g.div([*rows, g.comp("oh-link", {"action": "popup", "actionModal": f"page:{page}",
                                            "style": {"position": "absolute", "inset": "0", "display": "block",
                                                      "border-radius": "12px", "z-index": "1"}})],
                 **{"position": "relative", "display": "flex", "flex-direction": "column", "gap": "8px",
                    "padding": "8px 10px", "border-radius": "12px",
                    "background": f"={active} ? 'color-mix(in srgb, {color} 12%, transparent)' : "
                                  "'rgba(127, 127, 127, 0.06)'"})


def action_box(child, width="96px"):
    return g.div([child], **{"width": width})


def proposal_c():
    lines = [
        control_line("material:heat_pump", "Wärmepumpe",
                     f"'Speicher ' + {g.disp(g.HPX['tank'])} + ' · ' + {g.kw(g.HPX['power'])}", HP_C, g.HP_RUNNING,
                     [action_box(g.boost_button("Boost", "pyaltherma_dhw_powerful", HP_C))], "heatpump"),
        # the mode as a quick switch below, choosable while the unit is off (grey then, blue while it runs)
        control_line("material:ac_unit", "Klimaanlage",
                     f"'Soll ' + {g.degrees('faikout_perfera_temperature_setpoint')} + ' · Raum ' + "
                     f"{g.disp('faikout_perfera_temperature')}",
                     AC_C, AC_ON,
                     [action_box(g.pill_switch("An/Aus", "faikout_perfera_switch", AC_C)),
                      timer_chip(M_AC, 720, AC_C, "proposal-ac-timer")], "air_conditioning", below=g.ac_mode_bar()),
        control_line("material:air", "Lüftung", f"'CO₂ ' + {g.disp('netatmo_weatherstation_co2')}", VENT_C, "true",
                     [action_box(g.state_bar("esplyfterl_level", [("1", "1"), ("2", "2"), ("3", "3")], VENT_C)),
                      timer_chip(M_VENT, 360, VENT_C, "proposal-vent-timer")], "ventilation"),
    ]
    side = g.div([*lines, g.div([switch_row()], **{"padding-top": "6px"})],
                 **{"flex": "1 1 300px", "min-width": "280px", "max-width": "460px", "display": "flex",
                    "flex-direction": "column", "gap": "8px", "align-self": "center"})
    f = flow_with(page_links(set()), [])
    f["config"]["style"].update({"flex": "1 1 380px", "max-width": f"{g.FLOW_W}px", "min-width": "300px"})
    body = g.div([f, side], **{"display": "flex", "flex-wrap": "wrap", "justify-content": "space-evenly",
                               "align-items": "center", "gap": "8px 16px", "padding": "0 12px 8px"})
    return g.card("Vorschlag C · Fluss mit Steuerleiste", [
        body,
        caption("Der Fluss wie bisher, daneben je Gerät eine Zeile mit Zustand und Hauptaktion, bei der Klimaanlage "
                "darunter der Modus; die Timer sind Ringe mit der Restzeit, ein Tipp öffnet ihren Regler. Ein Tipp auf eine Zeile öffnet die Hauptseite. Auf dem "
                "Handy steht die Liste unter dem Fluss.")], fill=True)


# ---- E: a poster of tiles

def kv(label_, value, color=None):
    """A line of a tile: its label left, the value right."""
    style = {"font-weight": "700", "white-space": "nowrap"}
    if color:
        style["color"] = color
    return g.div([g.label(label_, **{"opacity": "0.7", "white-space": "nowrap", "overflow": "hidden",
                                     "text-overflow": "ellipsis"}), g.label(value, **style)],
                 **{"display": "flex", "justify-content": "space-between", "gap": "8px", "font-size": "12px",
                    "line-height": "17px"})


def poster_tile(icon, title, color, lines, target, actions=None, flow=None, out=None):
    """A tile of the poster: pale in its colour with a frame of it, icon and title, the lines, actions below; a tap
    elsewhere opens the quick panel or the page target. flow is a line at the top for what flows into it, out one at
    the bottom for what flows out of it, so the arrows wrap with their tiles."""
    head = g.div([g.comp("oh-icon", {"icon": icon, "width": 22, "height": 22}),
                  g.label(title, **{"font-size": "14px", "font-weight": "700", "white-space": "nowrap",
                                    "overflow": "hidden", "text-overflow": "ellipsis"})],
                 **{"display": "flex", "align-items": "center", "gap": "8px", "color": color})
    rows = ([flow] if flow else []) + [head, *lines] + ([out] if out else [])
    if actions:
        rows.append(g.div(actions, **{"display": "flex", "align-items": "center", "gap": "6px", "position": "relative",
                                      "z-index": "2", "margin-top": "4px"}))
    link = (quick_link(target, inset="0", **{"border-radius": "12px", "z-index": "1"}) if target in INSTANCES else
            g.comp("oh-link", {"action": "popup", "actionModal": f"page:{target}",
                               "style": {"position": "absolute", "inset": "0", "display": "block",
                                         "border-radius": "12px", "z-index": "1"}}))
    return g.div([*rows, link], **{"position": "relative", "display": "flex", "flex-direction": "column", "gap": "5px",
                                   "padding": "9px 10px", "border-radius": "12px", "min-width": "0",
                                   "background": f"color-mix(in srgb, {color} 9%, transparent)",
                                   "box-shadow": f"inset 0 0 0 1.5px color-mix(in srgb, {color} 55%, transparent)"})


def arrow(text, value, color, up, visible="true"):
    """A labelled flow between the rows: an arrow glyph, which way it flows, and the power."""
    return g.div([g.comp("oh-icon", {"icon": f"=({up}) ? 'material:north' : 'material:south'", "width": 18,
                                     "height": 18, "style": {"animation": "propPosterNudge 1.6s ease-in-out infinite"}}),
                  g.div([g.label(text, **{"font-size": "11px", "opacity": "0.85", "white-space": "nowrap"}),
                         g.label(value, **{"font-size": "14px", "font-weight": "700", "white-space": "nowrap"})],
                        **{"display": "flex", "flex-direction": "column", "line-height": "16px"})],
                 visible=f"={visible}", **{"display": "flex", "align-items": "center", "justify-content": "center",
                                           "gap": "4px", "color": color, "min-width": "0"})


def proposal_e():
    num, disp = g.num, g.disp
    pv, batt, grid, home = num(g.PV), num(g.BATT), num(g.GRID), num(g.HOME)
    kw = lambda e: f"={kw_text(e)}"
    pv_home = f"Math.max(0, {home} - Math.max(0, {batt}) - Math.max(0, {grid}))"
    sources = g.div([
        poster_tile("material:solar_power", "PV-Anlage", "#ffb300", [
            kv("Leistung", kw(pv)), kv("Heute", f"={disp('huawei_inverter_e_day')}"),
            kv("Status", f"={pv} > 10 ? 'erzeugt' : 'ruht'", "#43a047")], "photovoltaics",
            out=arrow("PV → Haus", kw(pv_home), "#ffb300", "false", f"{pv_home} > 5")),
        poster_tile("material:battery_charging_full", "Akku", BATTERY, [
            kv("Ladestand", f"={disp(g.SOC)}"), kv("Leistung", kw(f"Math.abs({batt})")),
            kv("Heute", f"='+' + {g.fixed(num('huawei_inverter_energy_storage_day_charge'), 1)} + ' / −' + "
                        f"{g.fixed(num('huawei_inverter_energy_storage_day_discharge'), 1)} + ' kWh'")], "energy_storage",
            out=g.div([arrow("Akku → Haus", kw(f"Math.max(0, {batt})"), BATTERY, "false", f"{batt} > 10"),
                       arrow("Haus → Akku", kw(f"Math.max(0, -{batt})"), BATTERY, "true", f"{batt} < -10"),
                       g.label("Akku ruht", visible=f"=Math.abs({batt}) <= 10",
                               **{"font-size": "11px", "opacity": "0.6", "text-align": "center"})])),
        poster_tile("material:electric_meter", "Netz", "#e53935", [
            kv("Leistung", kw(f"Math.abs({grid})")), kv("Bezug", f"={disp('huawei_inverter_power_meter_ec_day')}"),
            kv("Einspeisung", f"={disp('huawei_inverter_power_meter_ep_day')}"),
            kv("Preis", f"={disp(g.PRICE)}")], "power_meter",
            out=g.div([arrow("Netz → Haus", kw(f"Math.max(0, {grid})"), "#e53935", "false", f"{grid} > 10"),
                       arrow("Haus → Netz", kw(f"Math.max(0, -{grid})"), "#78909c", "true", f"{grid} < -10"),
                       g.label("Netz ruht", visible=f"=Math.abs({grid}) <= 10",
                               **{"font-size": "11px", "opacity": "0.6", "text-align": "center"})]))],
        **{"display": "grid", "grid-template-columns": "repeat(auto-fit, minmax(150px, 1fr))", "gap": "8px"})
    hub = g.div([g.comp("oh-icon", {"icon": "material:home", "width": 34, "height": 34}),
                 g.div([g.label("Haus", **{"font-size": "13px", "opacity": "0.85"}),
                        g.label(kw(home), **{"font-size": "22px", "font-weight": "700", "line-height": "26px"}),
                        g.label(f"='Autarkie heute ' + {g.pct('photovoltaics_own_ec_day', 'home_ec_day')[1:]} + "
                                f"' · Eigenverbrauch ' + {g.pct('photovoltaics_own_ec_day', 'huawei_inverter_e_day')[1:]}",
                                **{"font-size": "11px", "opacity": "0.85"})],
                       **{"display": "flex", "flex-direction": "column", "min-width": "0"}),
                 g.comp("oh-link", {"action": "popup", "actionModal": "page:flow_home",
                                    "style": {"position": "absolute", "inset": "0", "display": "block",
                                              "border-radius": "14px"}})],
                **{"position": "relative", "display": "flex", "align-items": "center", "gap": "12px",
                   "padding": "10px 14px", "border-radius": "14px", "color": "#ffffff",
                   "background": "linear-gradient(135deg, #1565c0, #0d47a1)"})
    to = lambda name, power, color: g.div(
        [g.comp("oh-icon", {"icon": "material:south", "width": 14, "height": 14}),
         g.label(f"='Haus → ' + {kw_text(power)}", **{"font-size": "11px", "font-weight": "700", "white-space": "nowrap"})],
        **{"display": "flex", "align-items": "center", "gap": "2px", "color": color, "opacity": "0.9"})
    appl_running = (f"[{', '.join(num(p + '_power') for p, _, _ in g.FLOW_APPLIANCES)}].filter((w) => w > "
                    f"{g.APPL_ON}).length")
    consumers = g.div([
        poster_tile("material:heat_pump", "Wärmepumpe", HP_C, [
            kv("Heute", f"={disp('espaltherma_energy_today')}"), kv("Speicher", f"={disp(g.HPX['tank'])}")],
            "proposal-hp-quick", [g.div([g.boost_button("Boost", "pyaltherma_dhw_powerful", HP_C)], **{"width": "96px"})],
            to("hp", g.num(g.HP), HP_C)),
        poster_tile("material:ac_unit", "Klimaanlage", AC_C, [
            kv("Heute", f"={disp('air_conditioning_unit_energy_today')}"),
            kv("Soll", f"={g.degrees('faikout_perfera_temperature_setpoint')}"),
            kv("Raum", f"={disp('faikout_perfera_temperature')}")],
            "proposal-ac-quick", [g.div([g.pill_switch("An/Aus", "faikout_perfera_switch", AC_C)], **{"width": "96px"}),
                                  timer_chip(M_AC, 720, AC_C, "proposal-ac-timer")], to("ac", g.AC_FLOW, AC_C)),
        poster_tile("material:electric_car", "E-Auto", g.ECAR_COLOR, [
            kv("Heute", f"={disp('e_car_energy_today')}"),
            kv("Status", f"={num(g.ECAR)} > {g.ECAR_CHARGING} ? 'lädt' : 'lädt nicht'")], "e_car",
            flow=to("ecar", num(g.ECAR), g.ECAR_COLOR)),
        poster_tile("material:local_laundry_service", "Geräte", g.APPL_COLOR, [
            kv("Heute", f"={g.fixed(g.APPL_DAY, 2)} + ' kWh'"),
            kv("Status", f"=((n) => n === 0 ? 'alle aus' : n === 1 ? '1 läuft' : n + ' laufen')({appl_running})")],
            "flow_appliances", flow=to("appl", g.APPL_POWER, g.APPL_COLOR)),
        poster_tile("material:air", "Lüftung", VENT_C, [
            kv("CO₂", f"={disp('netatmo_weatherstation_co2')}")], "proposal-vent-quick",
            [g.div([g.state_bar("esplyfterl_level", [("1", "1"), ("2", "2"), ("3", "3")], VENT_C)], **{"width": "96px"}),
             timer_chip(M_VENT, 360, VENT_C, "proposal-vent-timer")], to("vent", num("ventilation_power"), VENT_C))],
        **{"display": "grid", "grid-template-columns": "repeat(auto-fill, minmax(150px, 1fr))", "gap": "8px"})
    own, made, home_day = num("photovoltaics_own_ec_day"), num("huawei_inverter_e_day"), num("home_ec_day")
    autarky = f"({home_day} > 0 ? Math.min(100, Math.round(100 * {own} / {home_day})) : 0)"
    stat = lambda icon, color, title, value, sub=None: g.div(
        [g.comp("oh-icon", {"icon": icon, "width": 20, "height": 20, "style": {"color": color}}),
         g.div([g.label(title, **{"font-size": "11px", "opacity": "0.7"}),
                g.label(value, **{"font-size": "15px", "font-weight": "700", "white-space": "nowrap"}),
                *([g.label(sub, **{"font-size": "10px", "opacity": "0.6"})] if sub else [])],
               **{"display": "flex", "flex-direction": "column", "min-width": "0"})],
        **{"display": "flex", "align-items": "flex-start", "gap": "6px", "min-width": "0"})
    balance = g.div([
        g.label("Tagesbilanz", **{"font-size": "13px", "font-weight": "700"}),
        g.div([stat("material:solar_power", "#ffb300", "PV-Ertrag", f"={g.fixed(made, 1)} + ' kWh'"),
               stat("material:home", "#43a047", "Eigenverbrauch", f"={g.fixed(own, 1)} + ' kWh'",
                    f"={g.pct('photovoltaics_own_ec_day', 'huawei_inverter_e_day')[1:]} + ' des Ertrags'"),
               stat("material:upload", "#78909c", "Einspeisung", f"={disp('huawei_inverter_power_meter_ep_day')}"),
               stat("material:bolt", "#1e88e5", "Verbrauch", f"={g.fixed(home_day, 1)} + ' kWh'")],
              **{"display": "grid", "grid-template-columns": "repeat(auto-fit, minmax(105px, 1fr))", "gap": "8px"}),
        g.div([g.label(f"='Autarkie ' + {autarky} + ' %'", **{"font-size": "12px", "font-weight": "700",
                                                               "white-space": "nowrap"}),
               g.div([g.div([], **{"width": f"={autarky} + '%'", "height": "100%", "border-radius": "4px",
                                   "background": "#43a047"})],
                     **{"flex": "1", "height": "8px", "border-radius": "4px", "background": "rgba(127, 127, 127, 0.2)",
                        "overflow": "hidden"})],
              **{"display": "flex", "align-items": "center", "gap": "10px"})],
        **{"display": "flex", "flex-direction": "column", "gap": "8px", "padding": "10px 12px", "border-radius": "12px",
           "box-shadow": "inset 0 0 0 1px rgba(127, 127, 127, 0.25)"})
    body = g.div([sources, hub, consumers, g.div([switch_row()], **{"padding-top": "2px"}), balance],
                 **{"display": "flex", "flex-direction": "column", "gap": "8px", "padding": "4px 12px 12px"})
    body["config"]["stylesheet"] = "@keyframes propPosterNudge { 50% { transform: translateY(3px); } }"
    return g.card("Vorschlag E · Poster", [
        body,
        caption("Wie das Poster: PV, Akku und Netz als Kacheln über dem Haus, die Flüsse als beschriftete Pfeile, darunter "
                "die Verbraucher mit ihrer Hauptaktion, jede mit dem, was gerade aus dem Haus zu ihr fließt; unten die "
                "Tagesbilanz. Ein Tipp auf eine Kachel öffnet die Schnellbedienung oder die Seite.")])


# ---- the page and the widgets

def own_height(*cols):
    """A row whose cards keep their own height: B grows and shrinks with the chosen device, A stays compact."""
    r = g.row(*cols)
    r["config"]["stylesheet"] = ".row { align-items: flex-start; }"
    return r


def page(now):
    blocks = [g.block(own_height(g.col([proposal_a()]), g.col([proposal_b()])), g.row(g.full(proposal_c())),
                      own_height(g.col([proposal_e()])))]
    entry = g.layout_page(UID, {"label": "Vorschläge", "sidebar": False}, g.plots_below_controls(blocks), now)
    return entry["value"]


def widget_entries(now):
    names = g.known_items()
    out = {}
    for uid in QUICK:
        tree, props = g.ROLE_WIDGETS[uid]
        params = [dict(g.param(p, names.get(i, (p, ""))[0], f"{names.get(i, ('', 'Item'))[1]} item", required=True),
                       context="item") for i, p in props.items()]
        t = copy.deepcopy(g.itemized(tree, props))
        g.germanize(t, g.MISSING_DE)
        text = re.sub(r'"(widget:[a-z0-9-]+|page:[a-z0-9_]+)"', '""', json.dumps(t))
        left = [n for n in names if re.search(r"(?<![A-Za-z0-9_])" + re.escape(n) + r"(?![A-Za-z0-9_])", text)]
        assert not left, f"{uid} still names items: {left[:5]}"
        out[uid] = {"uid": uid, "tags": ["generated", "proposal"],
                    "props": {"parameters": params, "parameterGroups": []}, "timestamp": g.timestamp(now),
                    "component": t["component"], "config": t["config"], "slots": t.get("slots", {})}
    return out


now = datetime.datetime.now()
os.makedirs(OUT, exist_ok=True)
json.dump(page(now), open(os.path.join(OUT, "page.json"), "w"), ensure_ascii=False)
for uid, w in widget_entries(now).items():
    json.dump(w, open(os.path.join(OUT, f"widget-{uid}.json"), "w"), ensure_ascii=False)
print("written", sorted(os.listdir(OUT)))
