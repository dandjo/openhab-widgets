#!/usr/bin/env python3
"""Temporary proposals for the overview (user, 2026-10-06: "für die Übersicht mach mir Vorschläge", then "mit
allen"): page proposals_overview is the whole overview with every proposal in its cards, using the value forms
of the device pages (dashboard.py, section 9b): comparisons with yesterday under the energy flow's tiles and the
heating card's bars, the heat pump's figures as a flow band, the price rated in words with its hours ahead, the
temperatures with their trend, the room climate and the airing hint, the day's consumption per consumer against
yesterday. The generator stays untouched; the history of the extra items comes from the rule tile_history, whose
item list this script extends while the proposals are up.

Usage (on homepi, as pi):
  proposals_overview.py build OUTDIR    OUTDIR/body.json (the page, for ui_put.py) and OUTDIR/remove.json
  proposals_overview.py history         puts tile_history with the generator's items plus the proposals'
  (to take them down: ui_put.py apply OUTDIR/remove.json, then tile_history.py apply restores the rule)
"""
import copy
import datetime
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(os.path.dirname(HERE), "dashboard.py")
MODE = sys.argv[1:]
sys.argv = [GEN, "check"]
ns = {"__file__": GEN, "__name__": "dashboard"}
exec(compile(open(GEN).read().replace("\nmain()\n", "\n"), GEN, "exec"), ns)

UID = "proposals_overview"
num, fixed, disp, label, div, comp = ns["num"], ns["fixed"], ns["disp"], ns["label"], ns["div"], ns["comp"]
chip, hv, has, cls_color, track = ns["vt_chip"], ns["vt_hv"], ns["vt_has"], ns["cls_color"], ns["track_history"]
SUB = {"font-size": "11px", "opacity": "0.65"}


def walk(v, parent=None):
    """Every component with its parent list."""
    if isinstance(v, dict):
        for slot in v.get("slots", {}).values():
            for i, c in enumerate(slot):
                yield c, slot, i
                yield from walk(c)
    elif isinstance(v, list):
        for i, c in enumerate(v):
            yield c, v, i
            yield from walk(c)


def change_chip(item, better="less", label_=" zu gestern"):
    """Today's day counter against yesterday at this time as a chip, green where it moved the good way."""
    track(item, c=True)
    y = f"Number({hv(item, 'y')})"
    d = f"(({num(item)} - {y}) / {y} * 100)"
    good = "false" if better == "less" else "true"
    cls = f"(Math.abs({d}) < 3 ? 'neutral' : ({d} > 0) === {good} ? 'good' : 'warn')"
    return chip(f"=(Math.abs({d}) < 0.5 ? '±0' : ({d} > 0 ? '+' : '−') + Math.round(Math.abs({d}))) + ' %{label_}'",
                cls, visible=f"={has(hv(item, 'y'))} && {y} > 0")


def points_chip(own, base, label_=" zu gestern"):
    """A share today (own / base) against yesterday's at this time, in percentage points; more is better."""
    for i in (own, base):
        track(i, c=True)
    today = f"({num(own)} / Math.max({num(base)}, 0.001) * 100)"
    yday = f"(Number({hv(own, 'y')}) / Math.max(Number({hv(base, 'y')}), 0.001) * 100)"
    d = f"({today} - {yday})"
    cls = f"(Math.abs({d}) < 2 ? 'neutral' : {d} > 0 ? 'good' : 'warn')"
    return chip(f"=(Math.abs({d}) < 0.5 ? '±0' : ({d} > 0 ? '+' : '−') + Math.round(Math.abs({d}))) + ' Pkt.{label_}'",
                cls, visible=f"={has(hv(own, 'y'))} && {has(hv(base, 'y'))} && Number({hv(base, 'y')}) > 0")


def pad(*children):
    return div(list(children), **{"padding": "4px 16px 16px"})


# ---------------------------------------------------------------- the proposals


def flow_tiles():
    """Under the energy flow: house, self-consumption and self-sufficiency, each with today against yesterday."""
    now = ns["house_tiles"]()
    proposal = copy.deepcopy(now)
    chips = [change_chip("home_ec_day", "less"),
             points_chip("photovoltaics_own_ec_day", "huawei_inverter_e_day"),
             points_chip("photovoltaics_own_ec_day", "home_ec_day")]
    for tile_, c in zip(proposal["slots"]["default"], chips):
        inner = tile_["slots"]["default"][1]
        inner["slots"]["default"].append(div([c], **{"margin": "2px 0 0 4px"}))
    return now, proposal


def heating_bars():
    """The heating card: today's electricity and heat each with its change against yesterday beside the title."""
    now = ns["heating"]()[0]  # the card's content is a list of one
    proposal = copy.deepcopy(now)
    marks = {"Electricity Today": "espaltherma_energy_today", "Heat Today": "espaltherma_heating_energy_today"}
    for c, parent, i in list(walk(proposal)):
        if c.get("component") == "Label" and c.get("config", {}).get("text") in marks:
            item = marks[c["config"]["text"]]
            parent.insert(i + 1, change_chip(item, "less" if item == "espaltherma_energy_today" else "more"))
            c["config"].setdefault("style", {})["flex"] = "1 1 auto"
    # the title rows: title, chip, total with a gap
    for c, parent, i in walk(proposal):
        if c.get("component") == "div" and any(x.get("config", {}).get("text") in marks
                                              for x in c.get("slots", {}).get("default", []) if isinstance(x, dict)):
            c["config"]["style"].update({"gap": "8px", "align-items": "center"})
    return now, proposal


def hp_figures():
    """The heat pump card's three figures as the conversion: now while the compressor runs, the day's otherwise."""
    now = ns["hp_stats"]()
    HP = ns["HPX"]
    e, h = f"({num(ns['HP_POWER_ALL'])} * 0.001)", f"({num(HP['heat'])} * 0.001)"
    running = f"({h} > {e} && {e} > 0)"
    live = ns["hp_flow"]("", HP["heat"])
    day = ns["hp_day_flow"]("", "espaltherma_dcop")
    day["config"]["visible"] = f"=!{running}"
    return now, div([live, day], **{"display": "grid", "gap": "8px"})


def price_head():
    """The price: rated in words beside it, a band under it, the cheapest and dearest hours with how long until."""
    now = div(copy.deepcopy(ns["price"][:2]))
    P = ns["PRICE"]
    lo, hi, segs = ns["VT_SCALES"]["price"]
    word, band = ns["rating_parts"](num(P), lo, hi, segs)
    big = div([label(f"={disp(P)}", **{"font-size": "32px", "font-weight": "700", "color": ns["price_color"]}),
               word], **{"display": "flex", "flex-wrap": "wrap", "align-items": "center", "gap": "4px 12px"})

    def until(item, word_):
        left = f"Math.max(0, dayjs(items.{item}.state).diff(dayjs(), 'minute'))"
        return label(f"='{word_} ' + dayjs(items.{item}.state).format('dd HH:mm') + (({left}) > 0 ? ' · in ' + "
                     f"Math.floor(({left}) / 60) + ':' + ('0' + ({left}) % 60).slice(-2) + ' h' : ' · jetzt')",
                     **{"font-size": "13px", "opacity": "0.75"})
    hours = div([until("epex_spot_awattar_cheapest_hour", "Günstigste"),
                 until("epex_spot_awattar_priciest_hour", "Teuerste")],
                **{"display": "flex", "flex-wrap": "wrap", "gap": "2px 18px", "margin-top": "8px"})
    return now, div([big, div([band], **{"max-width": "360px"}), hours], **{"padding": "0 16px 12px"})


def temperatures():
    """Indoors and outdoors: the value with its trend; indoors the room's climate in a word (Netatmo's humidity),
    outdoors whether airing dries the rooms."""
    now = div(copy.deepcopy(ns["temps"][:1]))
    lo, hi, segs = ns["VT_SCALES"]["humidity"]
    climate, _ = ns["rating_parts"](num("netatmo_weatherstation_atmospheric_humidity"), lo, hi, segs)
    climate_line = div([label(f"='Raumklima · Feuchte ' + {disp('netatmo_weatherstation_atmospheric_humidity')}",
                              **{"font-size": "12px", "opacity": "0.7"}), climate],
                       **{"display": "flex", "flex-wrap": "wrap", "align-items": "center", "gap": "4px 8px",
                          "margin-top": "6px"})

    def stat(title, item, color, extra):
        track(item, t=1)
        return div([label(title, **{"font-size": "13px", "opacity": "0.7"}),
                    div([label(f"={disp(item)}", **{"font-size": "30px", "font-weight": "700", "line-height": "36px"}),
                         ns["trend_chip"](item, 1, "K")],
                        **{"display": "flex", "flex-wrap": "wrap", "align-items": "center", "gap": "4px 10px"}),
                    label("Fühler der Wärmepumpe", **{"font-size": "12px", "opacity": "0.6"}), extra],
                   **{"border-left": f"4px solid {color}", "padding": "4px 12px", "min-width": "0"})
    proposal = div([stat("Innen", ns["INDOOR"], "#fb8c00", climate_line),
                    stat("Außen", ns["OUTDOOR"], "#29b6f6", ns["airing_line"]())],
                   **{"display": "grid", "grid-template-columns": "1fr 1fr", "gap": "12px", "padding": "4px 16px 16px"})
    return now, proposal


def consumption():
    """Today's consumption: the total and every consumer against yesterday at this time."""
    now = copy.deepcopy(ns["consumption"][0])
    groups = [(n, list(its), c) for n, its, c in ns["parts"]]
    groups[1] = ("Klimaanlage", ["air_conditioning_unit_energy_today"], groups[1][2])
    groups.insert(1, ("E-Auto", ["e_car_energy_today"], "#26a69a"))
    home = "home_ec_day"
    rows = []
    for name, its, color in groups + [("Nicht gemessen", None, "#e0e0e0")]:
        if its is None:  # the house less every meter
            all_ = [i for _, g, _ in groups for i in g]
            v = f"Math.max(0, {num(home)} - ({' + '.join(num(i) for i in all_)}))"
            ys = " + ".join(f"(Number({hv(i, 'y')}) || 0)" for i in all_)
            y = f"Math.max(0, Number({hv(home, 'y')}) - ({ys}))"
            known = has(hv(home, "y"))
        else:
            for i in its:
                track(i, c=True)
            v = "(" + " + ".join(num(i) for i in its) + ")"
            y = "(" + " + ".join(f"(Number({hv(i, 'y')}) || 0)" for i in its) + ")"
            known = " || ".join(has(hv(i, "y")) for i in its)
        d = f"({v} - {y})"
        cls = f"(Math.abs({d}) < 0.05 ? 'neutral' : {d} > 0 ? 'warn' : 'good')"
        rows.append(div([div([], **{"width": "9px", "height": "9px", "border-radius": "50%", "background": color,
                                     "flex": "0 0 auto"}),
                         label(name, **{"flex": "1", "min-width": "0", "white-space": "nowrap", "overflow": "hidden",
                                        "text-overflow": "ellipsis"}),
                         label(f"={fixed(v, 2)} + ' kWh'", **{"font-weight": "600", "white-space": "nowrap"}),
                         label(f"=({known}) ? (Math.abs({d}) < 0.005 ? '±0' : ({d} > 0 ? '+' : '−') + "
                               f"{fixed(f'Math.abs({d})', 2)}) : '–'",
                               **{"min-width": "50px", "text-align": "right", "font-size": "12px", "font-weight": "600",
                                  "color": "=" + cls_color(cls)})],
                        **{"display": "flex", "align-items": "center", "gap": "8px", "font-size": "13px",
                           "break-inside": "avoid", "margin-bottom": "3px"}))
    track(home, c=True)
    # the card's title names today's total already: only its change under it
    total = div([change_chip(home, "less")],
                **{"display": "flex", "flex-wrap": "wrap", "align-items": "center", "gap": "4px 10px",
                   "margin-bottom": "10px"})
    note = label("rechts je Verbraucher: kWh mehr (orange) oder weniger (grün) als gestern bis zu dieser Uhrzeit",
                 **{**SUB, "margin-top": "8px"})
    listing = div(rows, **{"columns": "2 230px", "column-gap": "24px", "margin-top": "12px"})
    # the card as it is, its consumers' list replaced by the one with the change, the total's change on top
    proposal = copy.deepcopy(now)
    for c, parent, i in list(walk(proposal)):
        if c.get("component") == "div" and "columns" in c.get("config", {}).get("style", {}):
            parent[i] = listing
            parent.insert(i + 1, note)
            break
    proposal["slots"]["default"].insert(0, total)
    return now, proposal


PROPOSALS = [("Energiefluss · Kacheln unter dem Stern", flow_tiles),
             ("Heizung & Warmwasser", heating_bars),
             ("Wärmepumpe · Kennzahlen", hp_figures),
             ("Strompreis · Kopf", price_head),
             ("Temperaturen · Kopf", temperatures),
             ("Verbrauch heute", consumption)]


ORIGINAL = {name: ns[name] for name in ("house_tiles", "heating", "hp_stats", "price", "temps", "consumption")}


def full_overview(now_):
    """The overview as the generator lays it out (page()), with all six proposals in its cards: the parts are swapped
    in the generator's namespace while its cards are built, and the cards stand inline instead of as widgets (their
    items named directly, which a page may)."""
    parts = {name: fn() for name, fn in (("house_tiles", flow_tiles), ("heating", heating_bars),
                                         ("hp_stats", hp_figures), ("price", price_head), ("temps", temperatures),
                                         ("consumption", consumption))}
    try:
        ns["house_tiles"] = lambda: parts["house_tiles"][1]
        ns["heating"] = lambda tile=None: [parts["heating"][1]]
        ns["hp_stats"] = lambda: parts["hp_stats"][1]
        ns["price"] = [parts["price"][1], ORIGINAL["price"][2]]
        ns["temps"] = [parts["temps"][1], ORIGINAL["temps"][1]]
        ns["consumption"] = [parts["consumption"][1]]
        cards = {uid: ns["plots_below_controls"](card_) for uid, card_ in ns["overview_cards"]().items()}
    finally:
        ns.update(ORIGINAL)
    w = lambda uid: cards[uid]
    ws, block, row, col, full = ns["widget_stack"], ns["block"], ns["row"], ns["col"], ns["full"]
    return ns["layout_page"](UID, {"label": "Vorschlag Übersicht", "sidebar": False,
                                   "stylesheet": ns["SCROLLBAR"] + "\n" + ns["ONE_COLUMN"]}, [
        block(row(col([ws(w("weather-card"), w("energy-flow-card"), w("switches-card"), grow=2)]),
                  col([ws(w("appliances-card"), w("heating-card"))])),
              row(col([w("heatpump-card")]), col([ws(w("consumption-card"), w("energy-days-card"))])),
              row(col([w("electricity-price-card")]), col([w("temperatures-card")])),
              row(full(w("pv-days-card"))))], now_)


def build(outdir):
    now_ = datetime.datetime.now()
    page = full_overview(now_)
    os.makedirs(outdir, exist_ok=True)
    json.dump({"ui:page": {UID: page["value"]}}, open(os.path.join(outdir, "body.json"), "w"), ensure_ascii=False)
    json.dump({"ui:page": {UID: None}}, open(os.path.join(outdir, "remove.json"), "w"))
    extra = {k: v for k, v in ns["TRACK"].items()}
    json.dump(extra, open(os.path.join(outdir, "extra_track.json"), "w"), indent=1)
    print("page", UID, "->", outdir, "| items with history:", len(extra))


def history(outdir):
    """tile_history with the generator's items plus those the proposals need."""
    src = open(os.path.join(HERE, "tile_history.py")).read().replace("\nmain()\n", "\n")
    th = {"__file__": os.path.join(HERE, "tile_history.py"), "__name__": "tile_history"}
    saved = sys.argv
    sys.argv = [th["__file__"], "check"]
    exec(compile(src, th["__file__"], "exec"), th)
    sys.argv = saved
    tracked = th["ns"]["tile_history_track"]()
    for k, v in json.load(open(os.path.join(outdir, "extra_track.json"))).items():
        tracked.setdefault(k, {}).update(v)
    rule = {"uid": th["RULE_UID"], "name": "Kachel-Verlauf",
            "description": "Schreibt alle 10 Minuten in tile_history, was die Werte-Kacheln zeigen (gerade erweitert "
                           "um die Vorschläge für die Übersicht, proposals_overview.py; tile_history.py apply stellt "
                           "die Liste des Generators wieder her).",
            "tags": [], "conditions": [],
            "triggers": [{"id": "1", "type": "timer.GenericCronTrigger",
                          "configuration": {"cronExpression": "0 0/10 * * * ? *"}}],
            "actions": [{"id": "2", "type": "script.ScriptAction",
                         "configuration": {"type": "application/javascript",
                                           "script": th["SCRIPT"].replace("__TRACK__",
                                                                          json.dumps(tracked, separators=(",", ":")))}}]}
    print("rule PUT", th["call"]("PUT", f"/rules/{th['RULE_UID']}", rule), f"({len(tracked)} items)")
    print("run now:", th["call"]("POST", f"/rules/{th['RULE_UID']}/runnow", {}))


if __name__ == "__main__":
    if MODE[:1] == ["build"]:
        build(MODE[1])
    elif MODE[:1] == ["history"]:
        history(MODE[1])
    else:
        sys.exit(__doc__)
