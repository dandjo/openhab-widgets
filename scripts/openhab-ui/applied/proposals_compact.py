#!/usr/bin/env python3
"""A temporary page `proposals` with variant B of the overview's controls card: per device a head of three lines with
its main action on the right (Boost, An/Aus, level 1 to 3) and the details folded out on a tap, shown twice, folded
and unfolded. Built from the generator's own parts; folding is a MainUI page variable, so a tap on it sends no
command. The generator removes the page on its next run (OBSOLETE_PAGES).
Usage: proposals_compact.py check|apply   (as root, with openHAB stopped for apply)"""
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(os.path.dirname(HERE), "dashboard.py")
MODE = sys.argv[1]
sys.argv = [GEN, "check"]  # the generator's module code reads its mode; its main() is not run
ns = {"__file__": GEN, "__name__": "dashboard"}
exec(compile(open(GEN).read().replace("\nmain()\n", "\n"), GEN, "exec"), ns)
g = type("g", (), ns)

UID = "proposals"
AC_ON, M_AC, M_VENT = g.AC_ON_STATE, g.num("air_conditioning_timer"), g.num("ventilation_timer")


def tinted_panel(children, color, active):
    return g.div(children, **{"display": "flex", "flex-direction": "column", "gap": "8px", "padding": "10px 12px",
                              "margin-top": "8px", "border-radius": "14px",
                              "background": f"={active} ? '{g.rgba(color, 0.12)}' : 'rgba(127, 127, 127, 0.08)'"})


def shown(var, open_default):
    return f"vars.{var} !== false" if open_default else f"!!vars.{var}"


def head(icon, title, lines, color, active, var, action, open_default=False):
    """A device in three lines: its icon (26 px, as on the switch tiles) in a tinted circle; beside it the name with a
    chevron and the main action, and under them two lines of state that run the whole width, under the action too, so
    they stay readable on a phone. A tap anywhere folds the details in or out (the page variable var); the action lies
    above that and takes its own taps."""
    open_ = shown(var, open_default)
    badge = g.div([g.comp("oh-icon", {"icon": icon, "width": 26, "height": 26})],
                  **{"width": "44px", "height": "44px", "flex": "0 0 auto", "border-radius": "50%", "display": "flex",
                     "align-items": "center", "justify-content": "center",
                     "background": f"={active} ? '{g.rgba(color, 0.25)}' : 'rgba(127, 127, 127, 0.12)'"})
    chevron = g.comp("oh-icon", {"icon": "f7:chevron_down", "width": 16, "height": 16, "style": {
        "flex": "0 0 auto", "transition": "transform 0.25s ease",
        "transform": f"=({open_}) ? 'rotate(180deg)' : 'none'", "opacity": "0.6"}})
    top = g.div([g.label(title, **{"flex": "1", "min-width": "0", "font-size": "15px", "font-weight": "600",
                                   "white-space": "nowrap", "overflow": "hidden", "text-overflow": "ellipsis"}),
                 chevron,
                 g.div([action], **{"flex": "0 0 104px", "position": "relative", "z-index": "2"})],
                **{"display": "flex", "align-items": "center", "gap": "8px"})
    info = [g.label(f"={line}", **{"font-size": "12px", "opacity": "0.7", "line-height": "16px", "white-space": "nowrap",
                                   "overflow": "hidden", "text-overflow": "ellipsis"}) for line in lines]
    body = g.div([top, *info], **{"flex": "1", "min-width": "0", "display": "flex", "flex-direction": "column",
                                  "gap": "2px"})
    link = g.comp("oh-link", {"action": "variable", "actionVariable": var, "actionVariableValue": f"=!({open_})",
                              "style": {"position": "absolute", "inset": "0", "display": "block", "border-radius": "10px",
                                        "z-index": "1"}})
    return g.div([badge, body, link], **{"position": "relative", "display": "flex", "align-items": "center",
                                         "gap": "10px"})


def details(var, children, open_default=False):
    return g.div(children, visible=f"={shown(var, open_default)}",
                 **{"display": "flex", "flex-direction": "column", "gap": "8px", "padding-top": "4px"})


def fan_bar(dim):
    return g.div([g.label("Lüfter", **{"font-size": "13px", "min-width": "60px"}),
                  g.comp("f7-segmented", {"strong": True, "style": {"flex": "1 1 240px"}}, default=[
                      g.seg_button(text, "faikout_perfera_fan", cmd, f"items.faikout_perfera_fan.state === '{cmd}'",
                                   f"={AC_ON} ? '{g.AC_BLUE}' : '#90a4ae'") for cmd, text in g.AC_FAN])],
                 **{"display": "flex", "flex-wrap": "wrap", "align-items": "center", "gap": "6px 10px", **dim})


def level_buttons():
    """The ventilation level as three small segments, 1 to 3."""
    return g.comp("f7-segmented", {"strong": True, "style": {"width": "100%"}}, default=[
        g.seg_button(text, "esplyfterl_level", text, f"items.esplyfterl_level.state === '{text}'", g.VENT_TEAL)
        for text in ("1", "2", "3")])


def labelled(title, bar):
    return g.div([g.label(title, **{"font-size": "13px"}), bar],
                 **{"display": "flex", "flex-direction": "column", "gap": "6px"})


def on_off(item):
    return f"(items.{item}.state === 'ON' ? 'an' : items.{item}.state === 'OFF' ? 'aus' : '–')"


HP_LINES = [f"'Speicher ' + {g.disp(g.HPX['tank'])} + ' · ' + {g.kw(g.HPX['power'])}",
            f"'Heizung ' + {on_off('pyaltherma_climate_control_power')} + ' · Wasser ' + {on_off('pyaltherma_dhw_power')}"
            f" + ' · WW-Auto ' + {on_off('heatpump_dhw_management')}"]
AC_LINES = [f"({AC_ON} ? 'An · ' : 'Aus · ') + {g.disp('faikout_perfera_mode')} + ' · Soll ' + "
            f"{g.degrees('faikout_perfera_temperature_setpoint')}",
            f"'Raum ' + {g.disp('faikout_perfera_temperature')} + "
            f"({M_AC} > 0 ? ' · Timer noch ' + {g.minutes_text(M_AC)} : ' · kein Timer')"]
VENT_LINES = [f"'Stufe ' + {g.disp('esplyfterl_level')} + ' · ' + Math.round({g.num('ventilation_power')}) + ' W · CO₂ ' + "
              f"{g.disp('netatmo_weatherstation_co2')}",
              f"{M_VENT} > 0 ? ({g.is_on('ventilation_management')} ? 'Automatik pausiert bis ' : 'Timer bis ') + "
              f"{g.ends_at(M_VENT)} : ({g.is_on('ventilation_management')} ? 'Automatik regelt die Stufe' : 'Automatik aus')"]


def variant_b(suffix, open_default):
    dim_ac = {"opacity": f"={AC_ON} ? '1' : '0.6'"}
    var = lambda name: f"pB_{name}{suffix}"
    hp = tinted_panel([
        head("material:heat_pump", "Wärmepumpe", HP_LINES, g.HP_ORANGE, g.HP_RUNNING, var("hp"),
             g.pill_switch("Boost", "pyaltherma_dhw_powerful", g.HP_ORANGE), open_default),
        details(var("hp"), [labelled("Smart Grid", g.smart_grid_bar()), labelled("Betrieb", g.hp_switch_bar()),
                            g.dhw_setpoint({"opacity": f"={g.is_on('pyaltherma_dhw_power')} ? '1' : '0.6'"}),
                            g.lw_offset({"opacity": f"={g.is_on('pyaltherma_climate_control_power')} ? '1' : '0.6'"})],
                open_default)],
        g.HP_ORANGE, g.HP_RUNNING)
    ac = tinted_panel([
        head("material:ac_unit", "Klimaanlage", AC_LINES, g.AC_BLUE, AC_ON, var("ac"),
             g.pill_switch("An/Aus", "faikout_perfera_switch", g.AC_BLUE), open_default),
        details(var("ac"), [g.ac_mode_bar(), fan_bar(dim_ac), g.ac_boost(), g.ac_setpoint(dim_ac), g.ac_timer(dim_ac)],
                open_default)],
        g.AC_BLUE, AC_ON)
    vent = tinted_panel([
        head("material:air", "Lüftung", VENT_LINES, g.VENT_TEAL, "true", var("vent"), level_buttons(), open_default),
        details(var("vent"), [g.vent_timer()], open_default)],
        g.VENT_TEAL, "true")
    return [g.div([hp, ac, vent, TILES], **{"padding": "4px 16px 14px"})]


# the switch tiles as on the overview, the last child of its controls
TILES = g.control_tiles()[0]["slots"]["default"][3]


def proposals_page(now):
    blocks = [g.two(g.card("Variante B · zugeklappt", variant_b("", False)),
                    g.card("Variante B · aufgeklappt", variant_b("_open", True)))]
    return g.layout_page(UID, {"label": "Vorschläge Steuerung", "sidebar": True, "order": "0",
                               "icon": "f7:lightbulb"}, blocks, now)


name = "uicomponents_ui_page.json"
data, enc = g.m.detect(g.m.DB + name)
data.pop(UID, None)
data = g.m.insert(data, UID, proposals_page(datetime.datetime.now()))
text = g.m.encode(data, *enc)
print(f"{name}: encoder html={enc[0]} newline={enc[1]} ok; page {UID} with variant B, folded and unfolded")
if MODE == "apply":
    with open(g.m.DB + name, "w", encoding="utf-8") as f:
        f.write(text)
    print("written")
