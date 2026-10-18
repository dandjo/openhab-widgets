#!/usr/bin/env python3
"""A temporary page `proposals` with the heat pump's page tidied up (user, 2026-10-18: "noch sehr überladen"), built
from the generator's own parts with live items beside the page as it is:
- every value once: Jetzt, Betrieb, Temperaturen and Sollwerte as one card Jetzt of actual against setpoint (the
  heating circuit in one tile with its spread, setpoint and flow, the tank, the room, outdoors, the compressor, the
  water pressure, the heating curve); what the operation cards said goes into the head as chips, shown only while
  something special happens (defrost, heaters, cycle pause, error, quiet modes, oil return ...);
- Leistung aufgeteilt gone: the heat pump serves one purpose at a time, the head names it;
- Energie heute without its two flows (they repeated the tiles' numbers), the day's COPs in one row;
- the charts' tile sparklines gone where a chart shows the course; Heizbetrieb heute with the heaters as bands instead
  of a panel, without the water's flow; Strom nach Zweck pro Tag gone (the heat pump card's Elektrisch popup has it);
- Wärmepumpe pro Tag up beside COP nach Zweck pro Tag, right under the cards of today whose days they are, and the
  COPs per purpose as lines that leave out the days without the purpose (user, 2026-10-18);
- the day's courses under them, then the modes, the refrigerant and the rest of the operation in a card Diagnose;
- the Shelly EM cards as they are, at the foot (user, 2026-10-18).
The generator removes the page on its next run (OBSOLETE_PAGES).
Usage: proposals_heatpump.py BODY   (writes the REST body for ui_put.py; OPENHAB_JSONDB as for the generator)"""
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
P = g.HPX
num, disp, dash, fixed = g.num, g.disp, g.dash, g.fixed
ERROR = "espaltherma_error_code"
NO_ERROR = f"['0', '', 'NULL', 'UNDEF'].includes(items.{ERROR}.state)"
on = lambda item: f"items.{item}.state === 'ON'"
kw = lambda item: fixed(f"{num(item)} / 1000", 1) + " + ' kW'"

# what the head says only while it happens: (text, while, colour)
SPECIAL = [("'Abtauen'", on(P["defrost"]), "#4fc3f7"),
           (f"'Heizstab ' + {kw(P['buh_power'])}", f"{num(P['buh_power'])} > 0", g.HEATER_RED),
           (f"'Zusatzheizung ' + {kw(P['bsh_power'])}", f"{num(P['bsh_power'])} > 0", g.HP_ORANGE),
           (f"'Taktschutz −' + {fixed(num('heatpump_cycle_lock'), 0)} + ' K'", f"{num('heatpump_cycle_lock')} > 0",
            "#78909c"),
           (f"'Fehler ' + items.{ERROR}.state", f"!{NO_ERROR}", "#e53935"),
           ("'Flüstermodus'", on("espaltherma_silent_mode"), "#7e57c2"),
           ("'Geräuscharm'", on("espaltherma_low_noise_control"), "#7e57c2"),
           ("'Frostschutz'", on("espaltherma_freeze_protection"), "#29b6f6"),
           ("'Notbetrieb'", on("espaltherma_emergency_active"), "#e53935"),
           ("'System aus'", on("espaltherma_system_off"), "#78909c"),
           ("'Ölrückführung'", on("espaltherma_oil_return_operation"), "#78909c"),
           ("'Druckausgleich'", on("espaltherma_pressure_equalizing_operation"), "#78909c")]


def special_chip(text, while_, color):
    c = g.chip(f"={text}", color)
    c["config"]["visible"] = f"={while_}"
    return c


def head():
    """The page's head as now: the heat pump drawn, its power, the valve's purpose and a tank charge's timer, plus
    the chips of SPECIAL."""
    icon = g.node_icon("heat-pump-split", g.HP_ORANGE, g.flowing(num(g.HP), g.HP_FLOW), share=g.DHW_PROGRESS,
                       badges=g.hp_mode_badges(0, 0), power=num(g.HP), frequency=num(P["hz"]))
    chips = g.chips(g.chip(f"={disp(P['valve'])}", "#ffa726"),
                    g.timer_chip(f"={g.hm(g.DHW_LEFT)}", f"={g.DHW_ETA_OK}", tint=g.HP_ORANGE),
                    *[special_chip(*s) for s in SPECIAL])
    chips["config"]["style"]["justify-content"] = "flex-start"
    since = f"Math.max(0, dayjs().diff(dayjs(items.{g.DHW_SINCE}.state), 'minute'))"
    return [g.hero("material:heat_pump", "#fb8c00", "Elektrische Leistung", f"={disp(P['power'])}",
                   [chips, g.label(f"='fertig um ' + {g.DHW_DONE}", f"={g.DHW_ETA_OK}",
                                   **{"font-size": "22px", "font-weight": "700"})], picture=icon),
            g.bar(f"100 * {g.DHW_PROGRESS}", g.HP_ORANGE, f"={g.hm(since)} + ' vergangen'",
                  f"={g.hm(g.DHW_LEFT)} + ' übrig'", f"={g.DHW_ETA_OK}")]


def circuit_tile():
    """The heating circuit in one tile: leaving and inlet water with their spread between them as the page's tile
    Vorlauf → Rücklauf, the leaving water against its setpoint in the head, the target spread, the flow and the
    pump's signal under the pipe."""
    sup, ret, setp = P["supply"], P["return"], "espaltherma_leaving_water_setpoint"
    d, off = f"({num(sup)} - {num(ret)})", f"({num(sup)} - {num(setp)})"
    side = lambda name, item, color, align: g.div([g.label(name, **{**g.VT_SUB, "text-align": align}),
                                                   g.vt_value(f"={fixed(num(item), 1)} + ' °C'", color, ident=True,
                                                              **{"text-align": align})], **{"min-width": "0"})
    delta = g.vt_chip(f"='ΔT ' + {fixed(d, 1)} + ' K'")
    delta["config"]["style"].update({"justify-self": "center", "margin-bottom": "4px"})
    delta["config"]["class"] = "spread-delta"
    row_ = g.div([side("Vorlauf", sup, g.SUPPLY, "left"), delta, side("Rücklauf", ret, g.RETURN, "right")],
                 **{"display": "grid", "grid-template-columns": "1fr auto 1fr", "align-items": "end",
                    "gap": "4px 8px", "margin-top": "4px"})
    row_["config"]["class"] = "spread-row"
    narrow = g.div([row_], **{"container-type": "inline-size"})
    narrow["config"]["stylesheet"] = (
        "@container (max-width: 235px) { .spread-row { grid-template-columns: 1fr 1fr !important; }\n"
        "  .spread-delta { grid-column: 1 / -1; grid-row: 2; margin: 0 !important; } }")
    pipe = g.div([g.vt_icon("chevron_right", 12) for _ in range(3)],
                 **{"display": "flex", "justify-content": "space-around", "align-items": "center",
                    "color": "#ffffff", "height": "10px", "border-radius": "5px", "margin-top": "8px",
                    "overflow": "hidden", "background": f"linear-gradient(90deg, {g.SUPPLY}, {g.RETURN})"})
    chip = g.vt_chip(f"={g.vt_signed(off, 1, 'K')} + ' zum Soll'", f"(Math.abs({off}) <= 1 ? 'good' : 'warn')")
    lines = [g.label(f"='Vorlauf-Soll ' + {fixed(num(setp), 1)} + ' °C · ΔT-Soll ' + "
                     f"{fixed(num('espaltherma_target_delta_t_heating'), 1)} + ' K'", **{**g.VT_SUB, "margin-top": "8px"}),
             g.label(f"='Durchfluss ' + {dash(disp(P['flow']))} + ' · Pumpe ' + "
                     f"{dash(disp('espaltherma_water_pump_signal'))}", **{**g.VT_SUB, "margin-top": "2px"})]
    # a tap shows the leaving water, its setpoint dashed in its colour and the inlet water (user, 2026-10-18: a
    # comparison's popup shows both sides)
    return g.vt_tile([g.vt_head("Heizkreis", chip), narrow, pipe, *lines], sup, "Heizkreis",
                     second={"item2": setp, "name": "Vorlauf", "name2": "Soll", "color": g.SUPPLY,
                             "color2": g.SUPPLY, "dashed2": True, "item3": ret, "name3": "Rücklauf",
                             "color3": g.RETURN, "scale": True})


def plain(title, item, value=None):
    """A value without the renderer's form (a course a chart on this page draws already)."""
    return g.vt_tile([g.vt_head(title), g.vt_value(value or f"={dash(disp(item))}")], item, title)


def now_card():
    tiles = g.value_grid([
        g.vtile("Heizleistung", P["heat"], color="#e53935"),  # Strom → Wärme jetzt, only while it runs
        circuit_tile(),
        g.vtile("Warmwasser", P["tank"]),  # the tank against its setpoint
        g.vtile("Raum Sollwert", "espaltherma_room_temp_setpoint"),  # Raum gegen Soll
        g.pair_tile("Außen", P["outdoor"], "espaltherma_outdoor_air_temp", "Außentemperatur", "Außenluft",
                    digits=1, unit="K", a_color="#26a69a", b_color="#90a4ae"),
        g.ring_tile("Verdichter", P["hz"], "#fb8c00", pct_expr=f"{num(P['hz'])} / {g.HZ_FULL} * 100",
                    sub=f"='von {g.HZ_FULL} Hz · Inverter ' + {dash(disp('espaltherma_inv_primary_current'))}"),
        g.vtile("Wasserdruck", "espaltherma_water_pressure"),
        g.heating_curve_tile("Heizkurve", P["outdoor_avg"], "espaltherma_leaving_water_setpoint",
                             f"Außen {g.HP_AVG_NAME}", "Vorlauf-Soll", "#26a69a", g.SUPPLY)])
    return g.card("Jetzt", head() + [tiles])


def today_card():
    """Electricity and heat today against yesterday, each split by purpose, and the day's COPs under them."""
    tiles = g.value_grid([g.vtile("Elektrisch heute", "espaltherma_energy_today"),
                          g.vtile("Heizung", "espaltherma_energy_space_today"),
                          g.vtile("Warmwasser", "espaltherma_energy_dhw_today"),
                          g.vtile("Standby", "espaltherma_energy_standby_today"),
                          g.vtile("Wärme heute", "espaltherma_heating_energy_today", color="#e53935"),
                          g.vtile("Wärme Heizung", "espaltherma_heating_energy_space_today"),
                          g.vtile("Wärme Warmwasser", "espaltherma_heating_energy_dhw_today"),
                          g.vt_tile([g.vt_head("COP heute"),
                                     g.cop_row("espaltherma_dcop", "espaltherma_dcop_space", "espaltherma_dcop_dhw")],
                                    "espaltherma_dcop", "Tages-COP", wide=True)])
    return g.card("Heute", [tiles])


def run_panels():
    """Heizbetrieb heute: the valve, the defrosts and the two electric heaters as bands, electricity against heat,
    the COP and the compressor."""
    heaters = [g.band_panel("Heizstab", P["buh1"], [("ON", "An", g.HEATER_RED)], "Aus",
                            extra=[g.on_off_series("Heizstab", P["buh_power"], g.HEATER_RED)]),
               g.band_panel("Zusatzheizung", P["bsh"], [("ON", "An", g.HP_ORANGE)], "Aus",
                            extra=[g.on_off_series("Zusatzheizung", P["bsh_power"], g.HP_ORANGE)])]
    return g.hp_bands() + heaters + [
        ([("Strom", g.ELECTRIC_C), ("Wärme", "#e53935")],
         [g.area("Wärme", P["heat"], "#e53935"), g.area("Strom", P["power"], g.ELECTRIC_C)], g.value_axis("W")),
        ("COP", [g.area("COP", P["cop"], g.COP_C)], g.value_axis("COP", min=0)),
        ("Verdichter", [g.line("Verdichter", P["hz"], "#78909c")], g.value_axis("Hz", min=0))]


def mode_tile(title, item, color="#fb8c00"):
    """status_tile() whose name wraps instead of being cut, for two abreast on a phone."""
    t = g.status_tile(title, item, color)
    t["slots"]["default"][0]["config"]["style"].update({"white-space": "normal", "overflow": "visible",
                                                         "line-height": "1.25"})
    return t


def two_on_phone(grid, least):
    """A grid of tiles two abreast on a phone (one each, they made the card some 2,500 px long there)."""
    grid["config"]["style"]["grid-template-columns"] = (f"={g.NARROW} ? 'repeat(2, minmax(0, 1fr))' : "
                                                        f"'repeat(auto-fill, minmax({least}px, 1fr))'")
    return grid


def cop_lines():
    """The day's COPs per purpose over the month as lines (user, 2026-10-18: lines instead of columns). A day without
    the purpose stands at 0 (no heating that day, today before its first run), where a plain line would plunge: a
    custom series draws each line at its last day through the days above 0 only, a dot on each, so such a day shows
    as a missing dot (MainUI's expressions know no loop: the points come from a string of as many spaces)."""
    def series(name, item, color):
        pts = ("' '.repeat(params.dataInsideLength).split('').map((s, i) => [api.value(0, i), api.value(1, i)])"
               ".filter((v) => v[1] > 0).map((v) => api.coord(v))")
        render = (f"=(params, api) => params.dataIndexInside === params.dataInsideLength - 1 ? ((pts) => "
                  f"({{type: 'group', children: [{{type: 'polyline', shape: {{points: pts}}, style: {{fill: 'none', "
                  f"stroke: '{color}', lineWidth: 2}}}}].concat(pts.map((p) => ({{type: 'circle', shape: "
                  f"{{cx: p[0], cy: p[1], r: 3}}, style: {{fill: '{color}'}}}})))}}))({pts}) : null")
        return g.daily(name, item, color, type="custom", renderItem=render, encode={"x": 0, "y": 1}, progressive=0)
    chart_ = g.month_chart([series("Heizung", "espaltherma_dcop_space", g.SPACE_C),
                            series("Warmwasser", "espaltherma_dcop_dhw", g.DHW_C)], "COP", height="300px")
    # the tooltip gives such a day a dash, not "0" (MainUI's smart formatter would override valueFormatter)
    chart_["slots"]["tooltip"][0]["config"].update(
        smartFormatter=False, valueFormatter="=(v) => v == null || Number(v) <= 0 ? '–' : "
                                             "Number(v).toLocaleString('de-AT', {minimumFractionDigits: 2, "
                                             "maximumFractionDigits: 2})")
    return chart_


def diagnose_card():
    """What one looks at when something seems off: the refrigerant, the units' own operation words, the cycle guard,
    the error code, the leaving water before the backup heater, the second setpoint, all the modes, and the
    refrigerant's day."""
    tiles = g.value_grid([
        plain("Wärmetauscher Mitte", "espaltherma_heat_exchanger_mid_temp"),
        plain("Kältemittel flüssig", "espaltherma_refrig_temp_liquid_side"),
        g.vtile("Soll-Heißgas", "espaltherma_target_discharge_temp"),  # Heißgas gegen Soll
        plain("Kältemitteldruck", P["pressure"]),
        plain("Drucksensor-Temp.", "espaltherma_pressure_sensor_temp"),
        # the leaving water before and after the backup heater, what it adds as the chip (short titles: two abreast
        # on a phone cut the longer ones)
        g.pair_tile("Heizstab", "espaltherma_leaving_water_temp_before_buh", P["supply"], "Vorlauf vor", "nach",
                    digits=1, unit="K", a_color="#ffb74d", b_color=g.SUPPLY,
                    delta_text=g.vt_signed(f"{num(P['supply'])} - {num('espaltherma_leaving_water_temp_before_buh')}",
                                           1, "K")),
        plain("Vorlauf-Soll Zusatz", "espaltherma_leaving_water_setpoint_add"),
        plain("Außengerät Betrieb", "espaltherma_operation_mode"),
        plain("Innengerät Betrieb", "espaltherma_i_u_operation_mode"),
        g.vtile("Taktschutz", "heatpump_cycle_lock"),
        g.vtile("Fehler", ERROR)])
    modes = g.status_grid([mode_tile(t, i) for t, i in [
        ("Umwälzpumpe", P["pump"]), ("Heizstab Stufe 1", P["buh1"]), ("Heizstab Stufe 2", P["buh2"]),
        ("Warmwasser-Boost", "espaltherma_powerful_dhw_operation"), ("Zusatz\u00adheizung Speicher", P["bsh"]),
        ("Heizbetrieb", "espaltherma_space_heating_operation"), ("Flüstermodus", "espaltherma_silent_mode"),
        ("Speicher Komfort\u00admodus", "espaltherma_storage_comfort_mode"), ("Speicher Eco-Modus", "espaltherma_storage_eco_mode"),
        ("Nachheizen", "espaltherma_reheat"), ("System aus", "espaltherma_system_off"),
        ("Thermostat\u00adschalter", "espaltherma_thermostat_switch"), ("Frostschutz", "espaltherma_freeze_protection"),
        ("Thermoschutz Heizstab", "espaltherma_thermal_protector_buh"),
        ("Thermoschutz Zusatz\u00adheizung", "espaltherma_thermal_protector_bsh"), ("Notbetrieb", "espaltherma_emergency_active"),
        ("Abtauen", P["defrost"]), ("Geräusch\u00adarmer Betrieb", "espaltherma_low_noise_control"),
        ("Anforderungs\u00adsignal", "espaltherma_demand_signal"), ("Neustart-Standby", "espaltherma_restart_standby"),
        ("Anlauf\u00adsteuerung", "espaltherma_startup_control"), ("Öl\u00adrück\u00adführung", "espaltherma_oil_return_operation"),
        ("Druck\u00adausgleich", "espaltherma_pressure_equalizing_operation")]])
    sub = lambda text: g.label(text, **{"font-size": "13px", "font-weight": "600", "opacity": "0.6",
                                        "padding": "8px 16px 4px"})
    chart_ = g.stacked_chart([pn for pn in g.hp_refrigerant_panels() if pn[0] != "Wärmetauscher"], g.HP_SIDE_H)
    return g.card("Diagnose", [two_on_phone(tiles, 220), sub("Modi"), two_on_phone(modes, 210),
                               sub("Kältemittel heute"), chart_])


def blocks():
    g.VT_SEEN.clear()
    controls = g.controls_box(g.smart_grid_section(row=True), g.operation_section(row=True),
                              g.dhw_setpoint(row=True), g.dhw_boost(), g.lw_offset(row=True))
    plug, _, _, electric = g.plug_refs("heatpump", "material:heat_pump", "#fb8c00", title="Shelly EM",
                                       kind="heat-pump-split", active=g.flowing(num(g.HP), g.HP_FLOW),
                                       frequency=num(P["hz"]))
    return g.plots_below_controls([
        g.two(g.stack(g.card("Steuerung", [controls]), today_card()), now_card()),
        g.two(g.card("Wärmepumpe pro Tag", [g.hp_days()]), g.card("COP nach Zweck pro Tag", [cop_lines()])),
        g.two(g.card("Heizbetrieb heute", [g.stacked_chart(run_panels(), DAY_H)]),
              g.card("Temperaturen heute", [g.stacked_chart(g.hp_temp_panels(), DAY_H)])),
        g.one(diagnose_card()),
        g.two(plug, electric)])


DAY_H = int(os.environ.get("DAY_H", "700"))  # Heizbetrieb heute and Temperaturen heute beside it as high
config = {"label": "Vorschlag Wärmepumpe", "sidebar": True, "order": "0", "icon": "f7:lightbulb",
          "style": g.WIDE_POPUP_MARK, "stylesheet": g.WIDE_POPUP}
page = g.layout_page(UID, config, blocks(), datetime.datetime.now())
with open(OUT, "w", encoding="utf-8") as f:
    json.dump({"ui:page": {UID: page["value"]}}, f, ensure_ascii=False)
print(f"page {UID} -> {OUT}")
