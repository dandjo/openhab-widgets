#!/usr/bin/env python3
"""Generate homepi's MainUI pages and widgets: the overview with its popups, the device pages, and the widgets
they are built from; on first use also the daily energy total items and their rule.

Usage: dashboard.py update|update-apply   (update-apply as root with openHAB stopped)
"""
import base64
import copy
import datetime
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(globals().get("__file__", "dashboard.py")))
src = open(os.path.join(HERE, "awattar_migrate.py")).read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)

PAGE_UID = "overview"
DAILY = [
    # item, label, source counter
    ("energy_daily_pv", "Energy Daily PV", "huawei_inverter_e_day"),
    ("energy_daily_home", "Energy Daily Home", "home_ec_day"),
    ("energy_daily_grid_import", "Energy Daily Grid Import", "huawei_inverter_power_meter_ec_day"),
    ("energy_daily_grid_export", "Energy Daily Grid Export", "huawei_inverter_power_meter_ep_day"),
    ("energy_daily_self_use", "Energy Daily Self Use", "photovoltaics_own_ec_day"),
]
RULE_UID = "energy_daily_totals"
RULE_SCRIPT = """// One point per day at 23:59:59, overwritten every run, so charts over days and years load 365 points, not 700 000
const pairs = [
""" + "".join(f"  ['{src_}', '{item}'],\n" for item, _, src_ in DAILY) + """];

// the day counters glitch and reset during the first seconds after midnight
if (time.Duration.between(time.toZDT('00:00'), time.toZDT()).toMinutes() >= 2) {
  const endOfDay = time.toZDT('23:59:59');
  pairs.forEach(([source, target]) => {
    const value = items.getItem(source).numericState;
    if (value !== null) {
      const state = Quantity(value.toFixed(3) + ' kWh');
      items.getItem(target).postUpdate(state);
      items.getItem(target).persistence.persist(endOfDay, state, 'influxdb');
    }
  });
}"""


# ---------------------------------------------------------------- helpers

def num(item):
    return f"(Number(items.{item}.numericState) || 0)"


def fixed(expr, digits):
    """A number as text with a German decimal comma, as openHAB formats states; CSS and SVG values keep the dot."""
    return f"({expr}).toFixed({digits}).replace('.', ',')"


def disp(item):
    # after a restart some items are NULL for a while; show a dash instead of the raw word
    return (f"(['NULL', 'UNDEF'].includes(items.{item}.state) ? '–' : "
            f"(items.{item}.displayState || items.{item}.state))")


def kw(item):
    return f"{fixed(f'Math.abs({num(item)}) / 1000', 3)} + ' kW'"


def kw2(item, *plus):
    """A power item's state in kW to two decimals, a dash while it has none; plus: further power items added to it."""
    watts = num(item) if not plus else "(" + " + ".join(num(i) for i in (item, *plus)) + ")"
    return f"(['NULL', 'UNDEF'].includes(items.{item}.state) ? '–' : {fixed(f'{watts} / 1000', 2)} + ' kW')"


def comp(component, config=None, **slots):
    config = config or {}
    if component == "oh-label-cell":
        # an expanded label cell is empty; without this its ⋮ button only opens a black backdrop
        config = {**config, "expandable": False}
    c = {"component": component, "config": config}
    if slots:
        c["slots"] = slots
    return c


def label(text, visible=None, **style):
    cfg = {"text": text, "style": style} if style else {"text": text}
    if visible:
        cfg["visible"] = visible
    return comp("Label", cfg)


def div(children, visible=None, **style):
    cfg = {"style": style}
    if visible:
        cfg["visible"] = visible
    return comp("div", cfg, default=children)


def col(children, medium="100", large="50", xlarge="50"):
    return comp("oh-grid-col", {"width": "100", "xsmall": "100", "small": "100",
                                "medium": medium, "large": large, "xlarge": xlarge}, default=children)


def row(*cols):
    # stretch the columns so the cards of one row can share its height
    return comp("oh-grid-row", {"stylesheet": ".row { align-items: stretch; }"}, default=list(cols))


def block(*children, title=None):
    return comp("oh-block", {"title": title} if title else {}, default=list(children))


def stack(*cards):
    """Cards one above the other in a column: a flex column, so their margins do not collapse into one and they keep
    a card's gap, as in two rows. It fills the column, the last card takes the height the row leaves over."""
    cards = copy.deepcopy(list(cards))
    for c in cards:
        c["config"]["style"]["height"] = "auto"
    cards[-1]["config"]["style"]["flex"] = "1 1 auto"
    return div(cards, **{"display": "flex", "flex-direction": "column", "height": "100%"})


def card(title, content, fill=False):
    cfg = {"title": title, "style": {"height": "calc(100% - 2 * var(--f7-card-margin-vertical))"}}
    if fill:
        # the content grows into the height the row gives the card
        cfg["style"].update({"display": "flex", "flex-direction": "column"})
        cfg["contentStyle"] = {"flex": "1 1 auto", "display": "flex", "flex-direction": "column"}
    return comp("oh-card", cfg, content=content)


def widget_ref(uid, **props):
    """A card that is a widget of its own, placed with its props."""
    return comp(f"widget:{uid}", props)


def fill_chart(chart_, min_height):
    """A chart taking the rest of a filled card's height, at least min_height; the chart itself gets height 100%."""
    return div([div([chart_], **{"position": "absolute", "inset": "0"})],
               **{"position": "relative", "flex": "1 1 auto", "min-height": min_height})


# a value axis name right-aligned with the axis labels below it
AXIS_NAME = {"align": "right", "padding": [0, 8, 0, 0]}
RIGHT_AXIS_NAME = {"align": "left", "padding": [0, 0, 0, 8]}  # over the labels of an axis on the right, mirrored


def chart(config, **slots):
    base = {"chartType": "", "periodVisible": False}
    base.update(config)
    return comp("oh-chart", base, **slots)


def tooltip(**cfg):
    return [comp("oh-chart-tooltip", {"show": True, "confine": True, **cfg})]


def legend(**cfg):
    return [comp("oh-chart-legend", {"show": True, "bottom": "0", "type": "scroll", **cfg})]


def time_series(name, item, **cfg):
    return comp("oh-time-series", {"name": name, "gridIndex": 0, "xAxisIndex": 0, "yAxisIndex": 0,
                                   "type": "line", "item": item, **cfg})


def rgba(hex_, alpha):
    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r}, {g}, {b}, {alpha})"


def keyed(cls, children, **cfg):
    """A div that takes part in the hover highlight of its group: class 'k k-<key>' plus a role (seg or item)."""
    return comp("div", {"class": cls, **cfg}, default=children)


def hover_group(children, keys, **style):
    """Hovering a segment or a row lifts it and its partner with the same key; everything else in the group fades."""
    css = [".k { transition: opacity 0.15s, transform 0.15s, background-color 0.15s; }",
           ".item { border-radius: 6px; padding: 3px 6px; margin: 0 -6px; }",
           ":host:has(.k:hover) .k { opacity: 0.3; }"]
    for key, color in keys:
        css += [f":host:has(.k-{key}:hover) .k-{key} {{ opacity: 1; }}",
                f":host:has(.k-{key}:hover) .item.k-{key} {{ background-color: {rgba(color, 0.4)}; font-weight: 700; }}",
                f":host:has(.k-{key}:hover) .seg.k-{key} {{ transform: scaleY(1.5); }}"]
    return comp("div", {"stylesheet": "\n".join(css), "style": style}, default=children)


# No widget names an item: the overview's cards are built with their items, then every item they read becomes a
# prop named after its role, which the overview passes in. Vendor prefixes give the device, a few names are set.
ITEM_PROP_PREFIXES = [("huawei_inverter_power_meter_", "grid_"), ("huawei_inverter_energy_storage_", "battery_"),
                      ("huawei_inverter_", "pv_"), ("espaltherma_", "heatpump_"), ("pyaltherma_", "heatpump_"),
                      ("faikout_perfera_", "ac_"), ("esplyfterl_", "ventilation_"),
                      ("miele_washing_machine_wwg360_", "washer1_"), ("miele_tumble_dryer_twc560wp_", "dryer_"),
                      ("miele_dishwasher_g7465_", "dishwasher_"), ("epex_spot_awattar", "price"),
                      ("air_conditioning_unit_", "ac_unit_"), ("air_conditioning_", "ac_meter_"), ("e_car_", "ecar_"),
                      ("energy_daily_", "daily_")]
ITEM_PROP_NAMES = {
    "huawei_inverter_input_power": "pvPower", "huawei_inverter_e_day": "pvEnergyToday",
    "huawei_inverter_power_meter_active_power": "gridPower", "huawei_inverter_power_meter_ec_day": "gridImportToday",
    "huawei_inverter_power_meter_ep_day": "gridExportToday", "huawei_inverter_energy_storage_power": "batteryPower",
    "huawei_inverter_energy_storage_soc": "batterySoc", "huawei_inverter_energy_storage_day_charge": "batteryChargeToday",
    "huawei_inverter_energy_storage_day_discharge": "batteryDischargeToday", "home_active_power": "homePower",
    "home_ec_day": "homeEnergyToday", "photovoltaics_own_ec_day": "pvSelfUseToday", "epex_spot_awattar": "priceMarketNet",
    "espaltherma_electrical_power": "heatpumpPower", "espaltherma_heating_power": "heatpumpHeatPower",
    "heatpump_power": "heatpumpCircuitPower", "espaltherma_electrical_power_buh": "heatpumpBuhPower",
    "espaltherma_electrical_power_bsh": "heatpumpBshPower",
    "espaltherma_3way_valve_mode": "heatpumpValve", "pyaltherma_dhw_powerful": "heatpumpDhwBoost",
    "air_conditioning_timer": "acTimer", "air_conditioning_timer_set": "acTimerSet",
    "espaltherma_refrig_temp_liquid_side": "heatpumpRefrigerantTemp",
    "espaltherma_refrigerant_pressure_sensor": "heatpumpRefrigerantPressure",
}
ITEM_REF = re.compile(r"items\.([a-z][a-z0-9_]*)")
ITEM_KEYS = ("item", "actionItem")  # config keys that take an item's name


def item_prop(name):
    if name in ITEM_PROP_NAMES:
        return ITEM_PROP_NAMES[name]
    for prefix, role in ITEM_PROP_PREFIXES:
        if name.startswith(prefix):
            name = role + name[len(prefix):]
            break
    parts = [p for p in name.split("_") if p]
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def items_in(tree):
    """The items a component tree reads, in order of appearance."""
    found = []

    def walk(v, key=None):
        if isinstance(v, dict):
            if isinstance(v.get("config"), dict):
                keys = item_keys_of(v)
                for k, x in v["config"].items():
                    if k in keys and isinstance(x, str) and not x.startswith("=") and x not in found:
                        found.append(x)
                modal = v["config"].get("actionModalConfig")
                if isinstance(modal, dict):  # the items a popup widget is opened with
                    found.extend(x for k, x in modal.items() if k in modal_item_keys(v["config"])
                                 and isinstance(x, str) and not x.startswith("=") and x not in found)
            for k, x in v.items():
                walk(x, k)
        elif isinstance(v, list):
            for x in v:
                walk(x, key)
        elif isinstance(v, str):
            names = ITEM_REF.findall(v) if v.startswith("=") else ([v] if key in ITEM_KEYS else [])
            found.extend(n for n in names if n not in found)
    walk(tree)
    return found


def modal_item_keys(cfg):
    """The keys of a config's actionModalConfig that take an item: the item params of the widget it opens."""
    modal = cfg.get("actionModal", "")
    return ITEM_PARAMS.get(modal[len("widget:"):], set()) if isinstance(modal, str) and modal.startswith("widget:") \
        else set()


def item_keys_of(node):
    """The config keys of a component that take an item: item and actionItem, and the declared item params of a
    widget it places."""
    uid = node.get("component", "")
    return set(ITEM_KEYS) | (ITEM_PARAMS.get(uid[len("widget:"):], set()) if uid.startswith("widget:") else set())


def itemized(tree, props, keys=ITEM_KEYS):
    """The tree with every item read from the widget's props; props maps item name to prop name."""
    if isinstance(tree, dict):
        inner = item_keys_of(tree) if isinstance(tree.get("config"), dict) else set(ITEM_KEYS)
        if isinstance(tree.get("actionModalConfig"), dict):  # a config opening a popup widget with items
            tree = {**tree, "actionModalConfig": {k: ("=props." + props[x]) if k in modal_item_keys(tree) and
                                                  isinstance(x, str) and x in props else x
                                                  for k, x in tree["actionModalConfig"].items()}}
        return {k: (("=props." + props[x]) if k in keys and isinstance(x, str) and x in props
                    else itemized(x, props, inner) if k == "config" else itemized(x, props))
                for k, x in tree.items()}
    if isinstance(tree, list):
        return [itemized(x, props) for x in tree]
    if isinstance(tree, str) and tree.startswith("="):
        return "=" + ITEM_REF.sub(lambda m: f"items[props.{props[m.group(1)]}]", tree[1:])
    return tree



# ---------------------------------------------------------------- 1. key figures

GRID = "huawei_inverter_power_meter_active_power"
BATT = "huawei_inverter_energy_storage_power"
SOC = "huawei_inverter_energy_storage_soc"
PRICE = "epex_spot_awattar_total_gross"

price_color = (f"={num(PRICE)} < 0.2 ? '#43a047' : {num(PRICE)} < 0.3 ? '#fb8c00' : '#e53935'")

# ---------------------------------------------------------------- 2. energy flow


def svg(component, children=None, visible=None, **attrs):
    cfg = dict(attrs)
    if visible:
        cfg["visible"] = visible
    return comp(component, cfg, default=children) if children else comp(component, cfg)


def svg_text(x, y, content, size, weight="normal", anchor="middle", opacity="1"):
    return svg("text", x=x, y=y, content=content, fill="currentColor", **{
        "font-size": size, "font-weight": weight, "text-anchor": anchor, "opacity": opacity})


def ring(cx, cy, color):
    """A node's disc inside its grey ring, the only circle a node has (track(), with its dots, arcs and badges): an
    opaque disc in the card colour under a tint of the node's colour, ending where the ring's stroke begins."""
    r = ORBIT - RING_W / 2
    return svg("g", [svg("circle", cx=cx, cy=cy, r=r, style={"fill": "var(--f7-card-bg-color, #fff)"}),
                     svg("circle", cx=cx, cy=cy, r=r, fill=color, **{"fill-opacity": "0.12"})])


def track(cx, cy):
    """A node's grey ring of radius ORBIT, over an opaque disc in the card colour as wide as the ring's stroke, so
    the dots of a link or pipe running in under the node never show through the translucent ring."""
    return svg("g", [svg("circle", cx=cx, cy=cy, r=ORBIT + RING_W / 2, style={"fill": "var(--f7-card-bg-color, #fff)"}),
                     svg("circle", cx=cx, cy=cy, r=ORBIT, fill="none", stroke="rgba(127, 127, 127, 0.28)",
                         **{"stroke-width": RING_W})])


def stroke(width=1.6, color="currentColor", **extra):
    return {"stroke": color, "stroke-width": width, "stroke-linecap": "round", "fill": "none", **extra}


def steps(power, bins, values):
    """Expression picking an animation duration from a few power bins (fewer restarts than a smooth mapping)."""
    p = f"Math.abs({power})"
    expr = f"'{values[-1]}'"
    for limit, value in reversed(list(zip(bins, values))):
        expr = f"{p} < {limit} ? '{value}' : ({expr})"
    return "=" + expr


def spin(x, y, dur, active):
    return svg("animateTransform", attributeName="transform", type="rotate", **{"from": f"0 {x} {y}"},
               to=f"360 {x} {y}", dur=dur, repeatCount="indefinite", visible=f"={active}")


def dash_flow(dur, active, to="-12"):
    return svg("animate", attributeName="stroke-dashoffset", **{"from": "0"}, to=to, dur=dur,
               repeatCount="indefinite", visible=f"={active}")


def pylon_node(cx, cy, color, power):
    """High-voltage pylon; dashes run along its wires towards the house on import, away on export."""
    def leg_x(y, side):  # the legs run from (cx±10, cy+16) up to (cx±3, cy-16)
        return round(cx + side * (10 + (y - cy - 16) * 0.21875), 2)
    lines = [(leg_x(cy + 16, -1), cy + 16, leg_x(cy - 16, -1), cy - 16),
             (leg_x(cy + 16, 1), cy + 16, leg_x(cy - 16, 1), cy - 16),
             (cx - 15, cy - 10, cx + 15, cy - 10), (cx - 11, cy - 3, cx + 11, cy - 3),
             (leg_x(cy + 10, -1), cy + 10, leg_x(cy - 3, 1), cy - 3),
             (leg_x(cy + 10, 1), cy + 10, leg_x(cy - 3, -1), cy - 3),
             (leg_x(cy - 3, -1), cy - 3, leg_x(cy - 10, 1), cy - 10),
             (leg_x(cy - 3, 1), cy - 3, leg_x(cy - 10, -1), cy - 10),
             (cx - 15, cy - 10, cx - 15, cy - 7), (cx + 15, cy - 10, cx + 15, cy - 7),
             (cx - 11, cy - 3, cx - 11, cy), (cx + 11, cy - 3, cx + 11, cy)]
    active = f"Math.abs({power}) > 10"
    dur = steps(power, [500, 2000], ["2s", "1.2s", "0.7s"])
    wires = []
    for y_ins, sag in ((cy - 7, 4), (cy, 4)):
        d = (f"M{cx - 27},{y_ins + 2} Q{cx - 21},{y_ins + sag} {cx - 15 if y_ins == cy - 7 else cx - 11},{y_ins} "
             f"Q{cx},{y_ins + sag + 1} {cx + 15 if y_ins == cy - 7 else cx + 11},{y_ins} "
             f"Q{cx + 21},{y_ins + sag} {cx + 27},{y_ins + 2}")
        wires.append(svg("path", [dash_flow(dur, active, to=f"={power} > 0 ? '-12' : '12'")], d=d,
                         **stroke(1.4, color, **{"stroke-dasharray": "3 3"})))
    return [ring(cx, cy, color), *[svg("line", x1=a, y1=b, x2=c, y2=e, **stroke(1.5)) for a, b, c, e in lines],
            *wires]


def pv_node(cx, cy, power):
    """Tilted module under a sun; both brighten with the power, the rays turn faster the more it produces."""
    glow = f"=(0.25 + 0.75 * Math.min(1, Math.abs({power}) / 8000)).toFixed(2)"
    active = f"Math.abs({power}) > 10"
    sx, sy = cx + 6, cy - 13
    rays = []
    for k in range(8):
        a = math.radians(k * 45)
        rays.append(svg("line", x1=round(sx + 6.5 * math.cos(a), 2), y1=round(sy + 6.5 * math.sin(a), 2),
                        x2=round(sx + 9 * math.cos(a), 2), y2=round(sy + 9 * math.sin(a), 2),
                        **stroke(1.6, "#ffb300")))
    rays.append(spin(sx, sy, steps(power, [1000, 4000], ["12s", "7s", "4s"]), active))
    panel = f"{cx - 18},{cy + 15} {cx + 12},{cy + 15} {cx + 18},{cy - 1} {cx - 12},{cy - 1}"
    grid = [(cx - 18 + 30 * f, cy + 15, cx - 12 + 30 * f, cy - 1) for f in (0.25, 0.5, 0.75)]
    grid.append((cx - 15, cy + 7, cx + 15, cy + 7))
    return [ring(cx, cy, "#ffb300"),
            svg("g", rays, opacity=glow),
            svg("circle", cx=sx, cy=sy, r=5, fill="#ffb300", opacity=glow),
            svg("polygon", points=panel, **{"fill-opacity": glow}, **stroke(1.2, "currentColor", fill="#1e88e5")),
            *[svg("line", x1=round(a, 2), y1=b, x2=round(c, 2), y2=e, **stroke(0.8, "#e3f2fd")) for a, b, c, e in grid]]


def heatpump_node(cx, cy, hz):
    """Outdoor unit whose fan turns while its compressor runs (frequency above 0 Hz), faster the higher it runs; the
    heaters alone leave it still, their energy only flows."""
    fx, fy = cx - 5, cy
    active = f"{hz} > 0"
    blades = [svg("path", d=f"M{fx},{fy} q3.5,-3 0,-7.5 q-3.5,3 0,7.5", fill="#fb8c00",
                  transform=f"rotate({angle} {fx} {fy})") for angle in (0, 120, 240)]
    blades.append(spin(fx, fy, steps(hz, [30, 55], ["1.4s", "0.9s", "0.5s"]), active))
    grille = [svg("line", x1=cx + 7, y1=cy + dy, x2=cx + 14, y2=cy + dy, **stroke(1, opacity="0.7"))
              for dy in (-7, -3.5, 0, 3.5, 7)]
    return [ring(cx, cy, "#fb8c00"),
            svg("rect", x=cx - 17, y=cy - 12, width=34, height=24, rx=3, **stroke(1.6)),
            svg("circle", cx=fx, cy=fy, r=9, **stroke(1.2)),
            svg("g", blades),
            svg("circle", cx=fx, cy=fy, r=1.5, fill="currentColor"),
            *grille,
            svg("line", x1=cx - 12, y1=cy + 12, x2=cx - 12, y2=cy + 15, **stroke(1.6)),
            svg("line", x1=cx + 12, y1=cy + 12, x2=cx + 12, y2=cy + 15, **stroke(1.6))]


def ac_node(cx, cy, power):
    """Indoor split unit; its air streams flow and its LED lights while it draws more than AC_ON watts."""
    active = f"Math.abs({power}) > {AC_ON}"
    dur = steps(power, [300, 800], ["1.6s", "1s", "0.6s"])
    streams = [svg("path", [dash_flow(dur, active)], d=f"M{x},{cy + 3} q3,3.5 0,7 q-3,3.5 0,7",
                   opacity=f"={active} ? '1' : '0.25'", **stroke(1.6, "#29b6f6", **{"stroke-dasharray": "3 3"}))
               for x in (cx - 9, cx, cx + 9)]
    return [ring(cx, cy, "#29b6f6"),
            svg("rect", x=cx - 18, y=cy - 14, width=36, height=14, rx=4, **stroke(1.6)),
            svg("line", x1=cx - 13, y1=cy - 4, x2=cx + 13, y2=cy - 4, **stroke(1.2)),
            svg("circle", cx=cx + 13, cy=cy - 10, r=1.4, fill=f"={active} ? '#29b6f6' : '#9e9e9e'"),
            *streams]


def home_node(cx, cy, power):
    """House whose windows glow brighter with the consumption and pulse, faster the more it draws."""
    glow = f"=(0.3 + 0.7 * Math.min(1, Math.abs({power}) / 3000)).toFixed(2)"
    active = f"Math.abs({power}) > 50"
    pulse = svg("animate", attributeName="fill-opacity", values="0.35;1;0.35",
                dur=steps(power, [500, 1500], ["2.4s", "1.6s", "1s"]), repeatCount="indefinite", visible=f"={active}")
    windows = [svg("rect", [pulse], x=x, y=cy + 1, width=6, height=6, rx=1, fill="#ffd54f", **{"fill-opacity": glow})
               for x in (cx - 10, cx + 4)]
    return [ring(cx, cy, "#1e88e5"),
            svg("rect", x=cx + 6, y=cy - 15, width=4, height=7, **stroke(1.4)),
            svg("polygon", points=f"{cx - 17},{cy - 2} {cx},{cy - 16} {cx + 17},{cy - 2}",
                **stroke(1.8, **{"stroke-linejoin": "round"})),
            svg("rect", x=cx - 13, y=cy - 2, width=26, height=19, **stroke(1.8)),
            svg("rect", x=cx - 3, y=cy + 7, width=6, height=10, **stroke(1.4)),
            *windows]


def soc_color(soc):
    """The battery's colour by its state of charge: red below 20 %, orange below 50 %, green above."""
    return f"={soc} < 20 ? '#e53935' : {soc} < 50 ? '#fb8c00' : '#43a047'"


def battery_node(cx, cy, soc=None):
    soc = f"Math.max(0, Math.min(100, {soc or num(SOC)}))"
    fill = soc_color(soc)
    return [ring(cx, cy, "#7cb342"),
            svg("rect", x=cx - 21, y=cy - 10, width=40, height=20, rx=3, fill="none", stroke="currentColor",
                **{"stroke-width": 2}),
            svg("rect", x=cx + 19, y=cy - 4.5, width=3, height=9, rx=1, fill="currentColor"),
            svg("rect", x=cx - 18, y=cy - 7, width=f"=(34 * {soc} / 100).toFixed(1)", height=14, rx=1, fill=fill),
            # the state of charge on the bar, outlined in the card colour so it reads on red, orange and green
            svg("text", x=cx - 1, y=cy + 4, content=f"=Math.round({soc}) + ' %'", fill="currentColor",
                **{"font-size": 11, "font-weight": "700", "text-anchor": "middle", "paint-order": "stroke",
                   "stroke": "var(--f7-card-bg-color, #fff)", "stroke-width": 3, "stroke-linejoin": "round"})]


def ecar_node(cx, cy, power):
    """The Enyaq from the side, facing right, after a side photo: long flat bonnet, raked windscreen, long
    arched roof ending in a spoiler, short sloping tailgate, a narrow window band rising to a point at the
    rear, big wheels at the corners. While it charges, a bolt over the roof fades in and out, slowly."""
    charging = f"Math.abs({power}) > {ECAR_CHARGING}"
    k, ox, oy = 1.25, cx, cy + 0.5  # drawn in car units (36 long, roof at y -4.6, ground at 8), scaled, a little low

    def p(x, y):
        return f"{round(ox + k * x, 2)},{round(oy + k * y, 2)}"

    body = (f"M{p(17.9, 6)} L{p(18, 3.6)} Q{p(18, 1.2)} {p(17.2, 0.9)} Q{p(13.8, 0.1)} {p(8.9, -0.8)} "
            f"L{p(3, -4)} Q{p(-4.5, -4.9)} {p(-13.4, -4.2)} L{p(-16.5, -3.7)} L{p(-17.6, -0.8)} L{p(-18.1, 3.8)} "
            f"Q{p(-18.1, 5.6)} {p(-16.8, 6)} Z")
    window = (f"M{p(7.6, -0.8)} L{p(3.3, -3.4)} Q{p(-4.5, -4.2)} {p(-12.4, -3.4)} L{p(-13.6, -2)} "
              f"Q{p(-13, -1.3)} {p(-10, -1.2)} Z")
    wheels = []
    for wx in (11.9, -11.2):
        x, y = round(ox + k * wx, 2), round(oy + k * 5.3, 2)
        wheels += [svg("circle", cx=x, cy=y, r=round(k * 4.3, 2), style={"fill": "var(--f7-card-bg-color, #fff)"}),
                   svg("circle", cx=x, cy=y, r=round(k * 3.1, 2), **stroke(1.6)),
                   svg("circle", cx=x, cy=y, r=1, fill="currentColor")]
    bx, by = cx + 1, cy - 16  # the bolt stands over the roof
    bolt = svg("polygon", [svg("animate", attributeName="opacity", values="0;1;0", dur="2.4s",
                               repeatCount="indefinite")],
               points=" ".join(f"{round(bx + px, 2)},{round(by + py, 2)}" for px, py in
                               ((1.5, -8), (-4.5, 1.2), (-0.6, 1.2), (-1.8, 8), (4.5, -1.2), (0.6, -1.2))),
               fill=ECAR_COLOR, opacity="0", **{"stroke": ECAR_COLOR, "stroke-width": 0.8, "stroke-linejoin": "round"},
               visible=f"={charging}")
    return [ring(cx, cy, ECAR_COLOR),
            svg("path", d=body, **stroke(1.6, fill="#78909c", **{"fill-opacity": "0.3", "stroke-linejoin": "round"})),
            svg("path", d=window, **stroke(1.2, **{"stroke-linejoin": "round"})),
            *[svg("line", x1=round(ox + k * x, 2), y1=round(oy + k * y1, 2), x2=round(ox + k * x, 2),
                  y2=round(oy + k * y2, 2), **stroke(1.2)) for x, y1, y2 in ((-2.1, -4.1, -1.1), (-7.9, -3.9, -1.2))],
            svg("line", x1=round(ox + k * 8.2, 2), y1=round(oy + k * 4.8, 2), x2=round(ox + k * -7.4, 2),
                y2=round(oy + k * 4.8, 2), **stroke(1, opacity="0.5")),  # the dark sill between the wheels
            svg("line", x1=round(ox + k * 17.6, 2), y1=round(oy + k * 1.6, 2), x2=round(ox + k * 15.2, 2),
                y2=round(oy + k * 1.2, 2), **stroke(1.2, "#ffd54f")),  # LED headlight
            svg("line", x1=round(ox + k * -17.9, 2), y1=round(oy + k * 0.4, 2), x2=round(ox + k * -16.3, 2),
                y2=round(oy + k * 0.7, 2), **stroke(1.2, "#ef5350")),  # tail light
            *wheels, bolt]


def sparkle(x, y, size):
    """A four-pointed sparkle around (x, y), its points size away, its sides curved in."""
    k = size * 0.16
    p = [f"{round(x + dx, 2):g},{round(y + dy, 2):g}"
         for dx, dy in ((0, -size), (k, -k), (size, 0), (k, k), (0, size), (-k, k), (-size, 0), (-k, -k))]
    return f"M{p[0]} Q{p[1]} {p[2]} Q{p[3]} {p[4]} Q{p[5]} {p[6]} Q{p[7]} {p[0]} Z"


def appliances_node(cx, cy, power):
    """The household appliances together: the housing of the appliance tiles with sparkles for a front, as all of
    them clean something; while they draw more than APPL_ON watts together, the sparkles light up, the big one
    breathes and the small ones twinkle by turns, faster the more they draw."""
    active = f"Math.abs({power}) > {APPL_ON}"
    ease = {"calcMode": "spline", "keyTimes": "0;0.5;1", "keySplines": "0.42 0 0.58 1;0.42 0 0.58 1"}
    # the big one drawn around (0, 0), as SVG scales around the origin, then moved to (31, 36) of the tiles' 64 × 64
    # icon, which in turn is moved onto the node
    breathe = svg("animateTransform", attributeName="transform", type="scale", values="0.82;1.05;0.82",
                  dur=steps(power, [500, 1500], ["2.4s", "1.6s", "1s"]), repeatCount="indefinite",
                  visible=f"={active}", **ease)
    blink = steps(power, [500, 1500], ["1.8s", "1.2s", "0.75s"])
    small = [svg("path", [svg("animate", attributeName="opacity", values=values, dur=blink, repeatCount="indefinite",
                              visible=f"={active}", **ease)], d=sparkle(x, y, size), fill=APPL_COLOR)
             for x, y, size, values in ((38.6, 28, 2.9, "0.2;1;0.2"), (25.2, 43.2, 2.1, "1;0.2;1"))]
    big = svg("g", [svg("path", [breathe], d=sparkle(0, 0, 8), fill=APPL_COLOR)], transform="translate(31 36)")
    return [ring(cx, cy, APPL_COLOR),
            svg("g", machine_body([svg("g", [big, *small], opacity=f"={active} ? '1' : '0.45'")]),
                transform=f"translate({cx - 32} {cy - 32})")]


def ventilation_node(cx, cy, power):
    """The ventilation unit: a box with its fan, which turns while it draws more than 5 W, faster the more it draws,
    and two arrows on its top, fresh air coming in (teal) and used air going out (grey), flowing while it runs (the
    user's pick of the variants, 2026-10-03). The arrows stand 7 units off the middle, clear of the level's badge."""
    active = f"Math.abs({power}) > 5"
    fx, fy = cx, cy + 4.5
    blade = (f"M{fx},{fy} C{fx + 2.5},{fy - 1.5} {fx + 4.5},{fy - 5.5} {fx + 1.5},{fy - 8.5} "
             f"C{fx - 0.5},{fy - 6} {fx - 2},{fy - 3} {fx},{fy} Z")
    blades = [svg("path", d=blade, fill=VENT_TEAL, transform=f"rotate({72 * k} {fx} {fy})", **{"fill-opacity": "0.85"})
              for k in range(5)]
    blades.append(spin(fx, fy, steps(power, [30, 60], ["2.4s", "1.5s", "0.9s"]), active))
    dur = steps(power, [30, 60], ["1.6s", "1s", "0.6s"])

    def air(d, color):
        return svg("path", [dash_flow(dur, active, to="-12")], d=d, opacity=f"={active} ? '1' : '0.4'",
                   **stroke(1.8, color, **{"stroke-dasharray": "3 3"}))

    def head(x, y, down, color):
        return svg("path", d=f"M{x - 3.5},{y - 3.5 * down} L{x},{y} L{x + 3.5},{y - 3.5 * down} Z", fill=color)
    return [ring(cx, cy, VENT_TEAL),
            svg("rect", x=cx - 16, y=cy - 6, width=32, height=21, rx=3, **stroke(1.6)),
            svg("g", blades),
            # the hub over the blades' roots, in the card colour
            svg("circle", cx=fx, cy=fy, r=2, style={"fill": "var(--f7-card-bg-color, #fff)"}, stroke=VENT_TEAL,
                **{"stroke-width": 1.4}),
            air(f"M{cx - 7},{cy - 21} V{cy - 10}", VENT_TEAL), head(cx - 7, cy - 8, 1, VENT_TEAL),
            air(f"M{cx + 7},{cy - 7} V{cy - 18}", VENT_EXHAUST), head(cx + 7, cy - 21, -1, VENT_EXHAUST)]


PV = "huawei_inverter_input_power"
HP = "espaltherma_electrical_power"
ECAR = "e_car_power"
# the air conditioner's own power, the plug minus the car, split by the rule e_car_power (nothing while it is off)
AC_NET = num("air_conditioning_unit_power")
AC_ON_STATE = "items.faikout_perfera_switch.state === 'ON'"
# what flows to the A/C: only while Faikin reports it on, so its standby of about 10 W stays still; in fan mode
# it draws about 20 W
AC_FLOW = f"({AC_ON_STATE} ? {AC_NET} : 0)"
AC_ON = 5  # watts
ECAR_ON = 100  # watts; standby and an LED light behind the same plug draw a few watts
ECAR_CHARGING = 500  # it charges with 1.4 to 2.2 kW
ECAR_COLOR = "#26a69a"
VENT_TEAL = "#26a69a"
VENT_EXHAUST = "#90a4ae"  # the used air the ventilation unit blows out
# how the car's figures come about, under them on its page
ECAR_CALC = ("Berechnet aus der Messung der Klimaanlage (Shelly EM) abzüglich der Leistung laut Faikin und der "
             "Grundlast der Klimaanlage (Standby, Innengerät); unter 300 W lädt das Auto nicht.")
HP_ON = 50  # watts; the heat pump idles at about 20 W
HP_ORANGE = "#fb8c00"
HEATER_RED = "#e53935"  # the heat pump's electric heaters at work, as the wall unit's ring in the heat pump card
HOME = "home_active_power"
# the household appliances with a plug of their own, as on the appliance tiles; the fridge, running most of the day,
# and the coffee machine, a switch among the controls, stay out
FLOW_APPLIANCES = [("washing_machine_1", "Washing Machine 1", "#5c6bc0"),
                   ("washing_machine_2", "Washing Machine 2", "#9575cd"),
                   ("tumble_dryer", "Tumble Dryer", "#ffb74d"), ("dishwasher", "Dishwasher", "#4fc3f7")]
APPL_POWER = "(" + " + ".join(num(p + "_power") for p, _, _ in FLOW_APPLIANCES) + ")"
APPL_DAY = "(" + " + ".join(num(p + "_energy_today") for p, _, _ in FLOW_APPLIANCES) + ")"
APPL_ON = 10  # watts; together they idle at a few watts
APPL_COLOR = "#5c6bc0"
GRID_COLOR = f"={num(GRID)} < 0 ? '#43a047' : '#e53935'"
signed_kw = f"{fixed(f'{num(GRID)} / 1000', 3)} + ' kW'"

NARROW = "screen.width < 600"


def share_ring(cx, cy, title, part, whole, r=22, visible=None):
    """Ring filled to part / whole of today, with the percentage inside and the title beside it."""
    pct = f"({whole} > 0 ? Math.min(100, Math.round(100 * {part} / {whole})) : 0)"
    length = round(2 * math.pi * r, 2)
    return [svg("g", [svg("circle", cx=cx, cy=cy, r=r, **stroke(5, "#9e9e9e", **{"stroke-opacity": "0.25"})),
            svg("circle", cx=cx, cy=cy, r=r, transform=f"rotate(-90 {cx} {cy})",
                **stroke(5, "#43a047", **{"stroke-dasharray": f"=({length} * {pct} / 100).toFixed(1) + ' {length}'"})),
            svg_text(cx, cy + 5, f"={pct} + '%'", 13, "700"),
            svg_text(cx + 32, cy - 2, title, 12, anchor="start", opacity="0.7"),
            svg_text(cx + 32, cy + 14, "today", 11, anchor="start", opacity="0.5")], visible=visible)]


SELF_CONSUMPTION = ("Self-consumption", num("photovoltaics_own_ec_day"), num("huawei_inverter_e_day"))
SELF_SUFFICIENCY = ("Self-sufficiency", num("photovoltaics_own_ec_day"), num("home_ec_day"))
HOME_XY = (241.9, 210.2)
SPOKE = 170  # distance of every node from the house
FLOW_W, FLOW_H = 461, 461
STEP, TURN = 45, 8  # degrees between two nodes, and the star's turn clockwise from straight up
ORBIT = 30  # every node's one ring, around its drawing; its dots, arcs and badges say what the node does
RING_W = 4.5  # its stroke, the dots and arcs on it: as thick as the appliance icons' rings (4 of 64 units at 72 px)
# a working node's ring pulses beside an arc that shows a value (user, 2026-10-03: running dots, then dashes, were
# tried and replaced by this pulse), never stronger than half the arc's opacity, so the arc reads at the pulse's
# peak too; a fixed duration, as a SMIL animation restarts whenever an expression in it changes
PULSE = {"attributeName": "opacity", "values": "0.5;0.12;0.5", "dur": "2s", "repeatCount": "indefinite"}
# a working ring without an arc pulses as a whole and strongly, as the appliance icon of a machine without progress
# does (user, 2026-10-04)
PULSE_FULL = {**PULSE, "values": "1;0.3;1"}


def at(angle):
    """Position on the star around the house; 0° points right, angles grow clockwise."""
    a = math.radians(angle)
    return round(HOME_XY[0] + SPOKE * math.cos(a), 1), round(HOME_XY[1] + SPOKE * math.sin(a), 1)


# A regular star of eight nodes, 45° apart and turned by 8°: the ventilation at the top, then clockwise heat pump, air
# conditioner, E-Car, appliances, battery, grid, and PV at the top left. Every node has one ring (ORBIT); the texts
# stand below the rings, the ventilation's and PV's beside them, where the line to the house leaves them free. The
# radius is as small as the texts allow: at 170 the closest calls (the air conditioner's second line to the E-Car's
# ring, the heat pump's spoke to its value) keep about 9 units, as the star with two rings each kept at 196; the
# viewBox keeps the margins that star had around its rings, badges and texts (measured in the browser).
VENT_XY, HP_XY, AC_XY, ECAR_XY, APPL_XY, BATT_XY, GRID_XY, PV_XY = (at(-90 + TURN + k * STEP) for k in range(8))
TEXT_GAP = 12  # between a ring and the texts beside it
# the page each node opens as a popup: the device's page; house and appliances, which have none, a popup of their own;
# heat pump, air conditioner and ventilation open their quick controls instead (QUICK_NODES)
NODE_POPUPS = [(*PV_XY, "photovoltaics"), (*GRID_XY, "power_meter"), (*HOME_XY, "flow_home"),
               (*BATT_XY, "energy_storage"), (*ECAR_XY, "e_car"), (*APPL_XY, "flow_appliances")]


def node_box(cx, cy, size=2 * ORBIT + 8):
    """A node's box over the drawing, in percent of the FLOW_W × FLOW_H viewBox, ring included."""
    return {"position": "absolute", "display": "block", "border-radius": "50%",
            "left": f"{(cx - size / 2) / FLOW_W * 100:.2f}%", "top": f"{(cy - size / 2) / FLOW_H * 100:.2f}%",
            "width": f"{size / FLOW_W * 100:.2f}%", "height": f"{size / FLOW_H * 100:.2f}%"}


def node_link(cx, cy, popup):
    """Transparent link over a node that opens the page named by popup in a popup."""
    return comp("oh-link", {"action": "popup", "actionModal": f"page:{popup}", "style": node_box(cx, cy)})


def spoke(node, color, power, inward, threshold=10):
    """Link between the house and a node, rim to rim; the dots run towards the house while `inward` holds."""
    (hx, hy), (nx, ny) = HOME_XY, node
    d = math.hypot(nx - hx, ny - hy)
    ux, uy = (nx - hx) / d, (ny - hy) / d
    return [flow_link(round(nx - 30 * ux, 1), round(ny - 30 * uy, 1), round(hx + 30 * ux, 1), round(hy + 30 * uy, 1),
                      color, power, inward, threshold)]


def below(node, value, *lines):
    """Value and today's energy in one or two small lines under a node."""
    return [svg_text(node[0], node[1] + ORBIT + 28, value, 18, "700"),
            *[svg_text(node[0], node[1] + ORBIT + 44 + 15 * i, text, 12, opacity="0.7") for i, text in enumerate(lines)]]


def beside(node, value, line, side):
    """Value and one small line beside a node's ring, to its right (side 1) or left (side -1)."""
    x, anchor = node[0] + side * (ORBIT + TEXT_GAP), "start" if side > 0 else "end"
    return [svg_text(x, node[1] + 1, value, 18, "700", anchor=anchor),
            svg_text(x, node[1] + 18, line, 12, anchor=anchor, opacity="0.7")]


def kwh(expr, suffix=" kWh heute", prefix=""):
    return f"='{prefix}' + {fixed(expr, 2)} + '{suffix}'"


def into_out_of(into, out_of):
    """Today's energy into the house and out of it as one line, each amount after its short name, what came in first;
    into and out_of are (name, expression). Without a unit, as with it the grid's line would leave the drawing."""
    return f"='{into[0]} ' + {fixed(into[1], 2)} + ' · {out_of[0]} ' + {fixed(out_of[1], 2)}"


def flow_link_widget():
    """The widget every link of the energy flow is an instance of: a line from (x1, y1) to (x2, y2), and three dots
    that run along it while |power| exceeds threshold, towards (x2, y2) while forward holds, back otherwise, at four
    speeds. The dots run a dot radius past both ends, so they slide out from under one node's rim and back under the
    other's; the nodes are drawn after the links. The dots are spaced by their keyPoints: a changed speed or direction
    restarts all three together, and staggered begin times would bunch them up."""
    x1, y1, x2, y2 = (f"Number(props.{k})" for k in ("x1", "y1", "x2", "y2"))
    length = f"Math.hypot({x2} - {x1}, {y2} - {y1})"
    a = [f"({x1} - ({x2} - {x1}) / {length} * 5).toFixed(1)", f"({y1} - ({y2} - {y1}) / {length} * 5).toFixed(1)"]
    b = [f"({x2} + ({x2} - {x1}) / {length} * 5).toFixed(1)", f"({y2} + ({y2} - {y1}) / {length} * 5).toFixed(1)"]
    there = f"'M' + {a[0]} + ',' + {a[1]} + ' L' + {b[0]} + ',' + {b[1]}"
    back = f"'M' + {b[0]} + ',' + {b[1]} + ' L' + {a[0]} + ',' + {a[1]}"
    p = "Math.abs(Number(props.power))"
    active = f"{p} > Number(props.threshold !== undefined ? props.threshold : 10)"
    dur = f"=({p} < 300 ? '3.5s' : {p} < 1000 ? '2.5s' : {p} < 2500 ? '1.8s' : '1.2s')"
    dots = []
    for i in range(3):
        o = round(i / 3, 4)
        timing = ({"keyPoints": "0;1", "keyTimes": "0;1"} if i == 0 else
                  {"keyPoints": f"{o};1;0;{o}", "keyTimes": f"0;{round(1 - o, 4)};{round(1 - o, 4)};1"})
        dots.append(svg("circle", [svg("animateMotion", path=f"=props.forward ? {there} : {back}", dur=dur,
                                       repeatCount="indefinite", calcMode="linear", **timing)],
                        visible=f"={active}", r=4.5, fill="=props.color", cx=0, cy=0))
    return svg("g", [svg("line", x1="=props.x1", y1="=props.y1", x2="=props.x2", y2="=props.y2", stroke="=props.color",
                         **{"stroke-width": 3, "stroke-linecap": "round", "opacity": f"={active} ? '0.45' : '0.15'"}),
                     *dots])


def flow_link(x1, y1, x2, y2, color, power, forward, threshold=10):
    """An instance of the link widget; power and forward are expressions, evaluated where the link stands."""
    return comp("widget:flow-link", {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "color": color, "power": f"={power}",
                                     "forward": f"={forward}", "threshold": threshold})


FLOW_KINDS = {  # kind: (builder of the drawing around (0, 0) from the power expression, what it shows)
    "pv": (lambda p: pv_node(0, 0, p), "PV: a tilted module under a sun, both brighter with the power, rays turning"),
    "grid": (lambda p: pylon_node(0, 0, f"={p} < 0 ? '#43a047' : '#e53935'", p),
             "grid: a pylon, red on import, green on export, dashes along its wires"),
    "home": (lambda p: home_node(0, 0, p), "home: a house whose windows glow and pulse with the consumption"),
    "heat-pump": (lambda p: heatpump_node(0, 0, "Number(props.frequency)"),
                  "heat pump: an outdoor unit whose fan turns while its compressor runs (frequency)"),
    "air-conditioner": (lambda p: ac_node(0, 0, p), "air conditioner: an indoor unit whose air streams flow"),
    "e-car": (lambda p: ecar_node(0, 0, p), "E-Car: a car whose bolt fades in and out while it charges"),
    "battery": (lambda p: battery_node(0, 0, "Number(props.soc)"), "battery: filled to its state of charge"),
    "appliances": (lambda p: appliances_node(0, 0, p),
                   "appliances: an appliance with sparkles that breathe and twinkle while they run"),
    "ventilation": (lambda p: ventilation_node(0, 0, p),
                    "ventilation: a ventilation unit whose fan turns and whose air streams flow while it runs"),
}


def flow_node_widget():
    """The widget every node of the energy flow is an instance of: a device drawn in a ring of 30 around (x, y), its
    animations driven by power (the battery by soc, the heat pump's fan by frequency). kind: pv, grid, home, heat-pump,
    air-conditioner, e-car, battery,
    appliances or ventilation.
    The ring has an opaque disc in the card colour under its tint, so link dots slide under it."""
    power = "Number(props.power)"
    drawings = [svg("g", build(power), visible=f"=props.kind === '{kind}'") for kind, (build, _) in FLOW_KINDS.items()]
    return svg("g", drawings, transform="='translate(' + props.x + ' ' + props.y + ')'")


def flow_node(kind, xy, power=None, soc=None, frequency=None):
    cfg = {"kind": kind, "x": xy[0], "y": xy[1]}
    if power is not None:
        cfg["power"] = f"={power}"
    if soc is not None:
        cfg["soc"] = f"={soc}"
    if frequency is not None:
        cfg["frequency"] = f"={frequency}"
    return comp("widget:flow-node", cfg)


def share_ring_widget():
    """The widget every share ring is an instance of: a ring around (x, y) filled to part / whole, the percentage
    inside and the title beside it."""
    return svg("g", share_ring(0, 0, "=props.title", "Number(props.part)", "Number(props.whole)"),
               transform="='translate(' + props.x + ' ' + props.y + ')'")


def flow_share_ring(xy, title, part, whole):
    return comp("widget:flow-share-ring", {"x": xy[0], "y": xy[1], "title": title, "part": f"={part}",
                                           "whole": f"={whole}"})


def hm(m):
    """Minutes as 1:30 h, or 45 min below an hour; MainUI's expressions know no String()."""
    return (f"({m} >= 60 ? Math.floor({m} / 60) + ':' + (Math.floor({m} % 60) < 10 ? '0' : '') + "
            f"Math.floor({m} % 60) + ' h' : Math.round({m}) + ' min')")


def glyph(x, y, name, size, fill):
    """A Material Icons glyph in an svg, by its ligature; name may be an expression."""
    return svg("text", x=x, y=y, content=name, fill=fill, **{
        "font-size": size, "text-anchor": "middle", "dominant-baseline": "central",
        "style": {"font-family": "'Material Icons'", "font-feature-settings": "'liga'"}})


def shown(component, visible):
    """The component, shown only while visible (an expression) holds."""
    component["config"]["visible"] = visible
    return component


BADGE_OFF = "#9e9e9e"  # an inactive badge, grey like an idle ring (user, 2026-10-03)


def ring_badge(x, y, name, color, on, r=12, text=False):
    """A small round badge on a node's ring, with a glyph (or with name as a short bold text, text set): filled in
    the colour while on, grey while off (outline and glyph grey on a faint grey), as colour means that something is
    at work; an opaque disc below keeps the ring it sits on from showing through."""
    fill = f"={on} ? '#ffffff' : '{BADGE_OFF}'"
    mark = (svg("text", x=x, y=y + 0.5, content=name, fill=fill, **{
                "font-size": round(r * 0.9, 1), "font-weight": "700", "text-anchor": "middle",
                "dominant-baseline": "central"}) if text else glyph(x, y + 0.5, name, round(r * 1.25), fill))
    return svg("g", [svg("circle", cx=x, cy=y, r=r, style={"fill": "var(--f7-card-bg-color, #fff)"}),
                     svg("circle", cx=x, cy=y, r=r, fill=f"={on} ? '{color}' : '{rgba(BADGE_OFF, 0.14)}'",
                         stroke=f"={on} ? '{color}' : '{BADGE_OFF}'", **{"stroke-width": 2}),
                     mark])


def active_ring(xy, color, active, arc):
    """What a working node shows on its ring: the whole ring pulsing strongly in its colour (PULSE_FULL); where an arc
    on the ring shows a value (arc, an expression: a timer, the battery's charge, a frequency, power or temperature),
    a soft pulse (PULSE) instead, the arc standing still over it, so the value reads and the rest of the ring shows
    that the node works. Nothing while it rests."""
    ring_ = svg("circle", [svg("animate", visible=f"=({active}) && !({arc})", **PULSE_FULL)],
                visible=f"=({active}) && !({arc})", cx=xy[0], cy=xy[1], r=ORBIT, fill="none", stroke=color,
                **{"stroke-width": RING_W})
    pulse = svg("circle", [svg("animate", visible=f"=({active}) && ({arc})", **PULSE)],
                visible=f"=({active}) && ({arc})", cx=xy[0], cy=xy[1], r=ORBIT, fill="none", stroke=color,
                **{"stroke-width": RING_W})
    return svg("g", [ring_, pulse])


def flow_orbit(xy, color, power, threshold, share=None, least=0):
    """A node's ring while power flows through it (above threshold): pulsing in its colour, softly where a share
    stands on it (share, an expression, above least)."""
    return active_ring(xy, color, f"Math.abs({power}) > {threshold}", f"({share}) > {least}" if share else "false")


def share_orbit(xy, share, color, least=0):
    """A share as an arc on a node's ring, from the top clockwise, full at 1 (share an expression; shown above least):
    a timer's time left, the battery's charge, the heat pump's frequency, power or tank temperature. An underlay in
    the card colour hides the grey ring and the running dots under the arc, so they run on only where it leaves the
    ring free; it is a little wider and longer than the arc, so no dot peeps out at its edges."""
    c = round(2 * math.pi * ORBIT, 1)
    dash = f"=(Math.min(1, {share}) * {c}).toFixed(1) + ' {c}'"
    arc = {"cx": xy[0], "cy": xy[1], "r": ORBIT, "fill": "none", "transform": f"rotate(-90 {xy[0]} {xy[1]})",
           "stroke-linecap": "round", "stroke-dasharray": dash}
    return svg("g", [svg("circle", style={"stroke": "var(--f7-card-bg-color, #fff)"}, **arc,
                         **{"stroke-width": RING_W + 2}),
                     svg("circle", stroke=color, **arc, **{"stroke-width": RING_W, "opacity": "0.9"})],
               visible=f"={share} > {least}")


M_AC, M_VENT = num("air_conditioning_timer"), num("ventilation_timer")


def timer_full(item, high):
    """The minutes a full timer ring stands for: what the timer was last set to, by hand or by its automatic start
    (<item>_set, kept by the rule timer_set_value), high until it has been set once; never less than the time left."""
    return f"Math.max({num(item)}, {num(item + '_set')} || {high})"
VENT_POWER = num("ventilation_power")
# a badge's offset at 45°: a little outside its node's ring, where the second ring was, so it covers no drawing
ON_RING = round((ORBIT + 8) / math.sqrt(2), 1)


def timer_line(m, color, otherwise):
    """A node's second line: the time left while its timer runs, in the device's colour, otherwise as it was."""
    return {"content": f"={m} > 0 ? 'Timer ' + {hm(m)} : ({otherwise[1:]})", "fill": f"={m} > 0 ? '{color}' : 'currentColor'",
            "opacity": f"={m} > 0 ? '1' : '0.7'"}


def hp_mode_badges(cx, cy):
    """The heat pump's badge, upper right on the ring of its node at (cx, cy): defrosting, else what its valve serves,
    a flame for space heating, a shower for hot water; filled while it draws more than HP_ON watts. While only its
    heaters run, the compressor standing, a bolt in the backup heater's red instead."""
    defrost = f"items.{HPX['defrost']}.state === 'ON'"
    operation = f"={defrost} ? 'ac_unit' : {DHW_MODE} ? 'shower' : 'local_fire_department'"
    heaters_only = f"(({BUH_ON} || {BSH_ON}) && !({COMPRESSOR}))"
    xy = round(cx + ON_RING, 1), round(cy - ON_RING, 1)
    mode = ring_badge(*xy, operation, HP_ORANGE, HP_RUNNING)
    mode["config"]["visible"] = f"=!{heaters_only}"
    heater = ring_badge(*xy, "electric_bolt", HEATER_RED, "true")
    heater["config"]["visible"] = f"={heaters_only}"
    return [mode, heater]


def energy_flow():
    """The energy flow's card content: the star of eight nodes with their rings, timers, badges and links, and under
    it the house's figures; the switches have a card of their own below it (switches-card)."""
    ac_texts = below(AC_XY, f"={fixed(f'{AC_NET} / 1000', 3)} + ' kW'", kwh(num("air_conditioning_unit_energy_today")))
    ac_texts[1]["config"].update(timer_line(M_AC, AC_BLUE, ac_texts[1]["config"]["content"]))
    vent_texts = beside(VENT_XY, f"={fixed(f'{VENT_POWER} / 1000', 3)} + ' kW'",
                        f"='Stufe ' + {disp('esplyfterl_level')}", 1)
    vent_texts[1]["config"].update(timer_line(M_VENT, VENT_TEAL, vent_texts[1]["config"]["content"]))
    nodes = [VENT_XY, HP_XY, AC_XY, ECAR_XY, APPL_XY, BATT_XY, GRID_XY, PV_XY, HOME_XY]
    level = svg("g", [svg("circle", cx=round(VENT_XY[0] - ON_RING, 1), cy=round(VENT_XY[1] - ON_RING, 1), r=12,
                          fill=VENT_TEAL),
                      svg("text", x=round(VENT_XY[0] - ON_RING, 1), y=round(VENT_XY[1] - ON_RING, 1),
                          content="=items.esplyfterl_level.state", fill="#ffffff",
                          **{"font-size": 13, "font-weight": "700", "text-anchor": "middle",
                             "dominant-baseline": "central"})])
    drawing = svg("svg", [
        # connections first, so the nodes sit on top of the line ends
        *spoke(PV_XY, "#ffb300", num(PV), "true"),
        *spoke(GRID_XY, GRID_COLOR, num(GRID), f"{num(GRID)} > 0"),
        *spoke(HP_XY, "#fb8c00", num(HP), "false", threshold=HP_ON),
        *spoke(AC_XY, "#29b6f6", AC_FLOW, "false", threshold=AC_ON),
        *spoke(ECAR_XY, ECAR_COLOR, num(ECAR), "false", threshold=ECAR_ON),
        *spoke(APPL_XY, APPL_COLOR, APPL_POWER, "false", threshold=APPL_ON),
        *spoke(BATT_XY, "#7cb342", num(BATT), f"{num(BATT)} > 0"),
        *spoke(VENT_XY, VENT_TEAL, VENT_POWER, "false", threshold=5),
        # every circle's grey ring; while power flows it pulses in the node's colour, softly where an arc stands on
        # it: a running timer's time left on the air conditioner's and the ventilation's ring, the battery's charge
        # on its own
        *[track(x, y) for x, y in nodes],
        flow_orbit(PV_XY, "#ffb300", num(PV), 10),
        flow_orbit(GRID_XY, GRID_COLOR, num(GRID), 10),
        flow_orbit(BATT_XY, "#7cb342", num(BATT), 10, share=f"{num(SOC)} / 100"),
        flow_orbit(HP_XY, HP_ORANGE, num(HP), HP_ON),
        flow_orbit(ECAR_XY, ECAR_COLOR, num(ECAR), ECAR_ON),
        flow_orbit(APPL_XY, APPL_COLOR, APPL_POWER, APPL_ON),
        flow_orbit(HOME_XY, "#1e88e5", num(HOME), 10),
        flow_orbit(AC_XY, AC_BLUE, AC_FLOW, AC_ON,
                   share=f"{M_AC} / {timer_full('air_conditioning_timer', 720)}"),
        flow_orbit(VENT_XY, VENT_TEAL, VENT_POWER, 5,
                   share=f"{M_VENT} / {timer_full('ventilation_timer', 360)}"),
        share_orbit(AC_XY, f"{M_AC} / {timer_full('air_conditioning_timer', 720)}", AC_BLUE),
        share_orbit(VENT_XY, f"{M_VENT} / {timer_full('ventilation_timer', 360)}", VENT_TEAL),
        share_orbit(BATT_XY, f"{num(SOC)} / 100", "#7cb342"),
        flow_node("pv", PV_XY, num(PV)),
        flow_node("grid", GRID_XY, num(GRID)),
        flow_node("home", HOME_XY, num(HOME)),
        flow_node("heat-pump", HP_XY, num(HP), frequency=num(HPX["hz"])),
        flow_node("air-conditioner", AC_XY, AC_FLOW),
        flow_node("e-car", ECAR_XY, num(ECAR)),
        flow_node("appliances", APPL_XY, APPL_POWER),
        flow_node("battery", BATT_XY, soc=num(SOC)),
        flow_node("ventilation", VENT_XY, VENT_POWER),
        # badges on the rings: the heat pump's operation upper right; on/off and the level upper left, where a timer's
        # arc ends
        *hp_mode_badges(*HP_XY),
        ring_badge(round(AC_XY[0] - ON_RING, 1), round(AC_XY[1] - ON_RING, 1), "power_settings_new", AC_BLUE, AC_ON_STATE),
        level,
        *beside(PV_XY, f"={kw(PV)}", f"={disp('huawei_inverter_e_day')} + ' heute'", -1),
        *vent_texts,
        *below(GRID_XY, f"={signed_kw}", into_out_of(("Bezug", num("huawei_inverter_power_meter_ec_day")),
                                                   ("Einsp.", num("huawei_inverter_power_meter_ep_day")))),
        # the heat pump's texts 5 units right of its middle, so its spoke, coming in from the lower left, clears them
        *below((HP_XY[0] + 5, HP_XY[1]), f"={kw(HP)}", kwh(num("espaltherma_energy_today"))),
        *ac_texts,
        *below(ECAR_XY, f"={kw(ECAR)}", kwh(num("e_car_energy_today"))),
        *below(APPL_XY, f"={fixed(f'{APPL_POWER} / 1000', 3)} + ' kW'", kwh(APPL_DAY)),
        *below(BATT_XY, f"={fixed(f'{num(BATT)} / 1000', 3)} + ' kW'",  # negative while charging
               into_out_of(("Entl.", num("huawei_inverter_energy_storage_day_discharge")),
                           ("Gel.", num("huawei_inverter_energy_storage_day_charge")))),
    ], viewBox=f"0 0 {FLOW_W} {FLOW_H}", width="100%", style={"display": "block", "overflow": "visible"})
    quick = [(HP_XY, "heatpump-quick"), (AC_XY, "air-conditioner-quick"), (VENT_XY, "ventilation-quick")]
    links = [*[node_link(cx, cy, popup) for cx, cy, popup in NODE_POPUPS],
             *[comp("oh-link", {"action": "popup", "actionModal": quick_panel(uid)["component"],
                                "actionModalConfig": dict(quick_panel(uid)["config"]), "style": node_box(*xy)})
               for xy, uid in quick]]
    star = div([div([drawing, *links],
                    # at most at its own size, one unit a pixel, so its texts keep the UI's sizes on a wide screen
                    **{"position": "relative", "max-width": f"{FLOW_W}px", "width": "100%", "margin": "0 auto"})],
               # it centres itself in the height the row leaves, the cards below stay at the card's bottom
               **{"padding": f"={NARROW} ? '4px' : '12px'", "flex": "1 1 auto", "display": "flex",
                  "flex-direction": "column", "justify-content": "center"})
    strip = div([house_tiles()], **{"padding": "8px 12px 14px"})
    return [star, strip]


TILE_BG = "rgba(127, 127, 127, 0.08)"


def house_tiles():
    """The house's power and energy today, today's self-consumption and self-sufficiency, as three small cards under
    the star, each opening its popup with a tap anywhere on it: three abreast, on a phone the house above the two
    rings. Each has a large pale icon at its lower right, as the value tiles have."""
    home = div([comp("oh-icon", {"icon": "material:home", "width": 24, "height": 24,
                                 "style": {"color": "#1e88e5", "flex": "0 0 auto"}}),
                div([label(f"={kw(HOME)}", **{"font-size": "16px", "font-weight": "700", "line-height": "20px",
                                              "white-space": "nowrap"}),
                     label(kwh(num("home_ec_day")), **{"font-size": "11px", "opacity": "0.7", "white-space": "nowrap"})],
                    **{"display": "flex", "flex-direction": "column", "min-width": "0"})],
               **{"display": "flex", "align-items": "center", "gap": "8px"})
    ring_svg = lambda ring: svg("svg", [flow_share_ring((24, 25), *ring)], viewBox="0 0 150 50", width="100%",
                                style={"display": "block", "overflow": "visible", "max-width": "170px"})

    def tile(child, popup, icon, color, **extra):
        # the value tiles' watermark: 58 px, 6 px past the right edge and 10 past the bottom, at 16 %
        mark = comp("oh-icon", {"icon": f"material:{icon}", "width": 58, "height": 58, "style": {
            "position": "absolute", "right": "-6px", "bottom": "-10px", "opacity": "0.16", "color": color}})
        link = comp("oh-link", {"action": "popup", "actionModal": f"page:{popup}",
                                "style": {"position": "absolute", "inset": "0", "display": "block",
                                          "border-radius": "12px"}})
        return div([mark, div([child], **{"position": "relative", "min-width": "0", "flex": "1 1 auto"}), link],
                   **{"position": "relative", "overflow": "hidden", "padding": "8px 10px", "border-radius": "12px",
                      "background": TILE_BG, "min-width": "0", "display": "flex", "align-items": "center", **extra})
    return div([tile(home, "flow_home", "home", "#1e88e5", **{"grid-column": f"={NARROW} ? '1 / -1' : 'auto'"}),
                tile(ring_svg(SELF_CONSUMPTION), "flow_self_consumption", "solar_power", "#43a047"),
                tile(ring_svg(SELF_SUFFICIENCY), "flow_self_sufficiency", "energy_savings_leaf", "#43a047")],
               **{"display": "grid", "gap": "8px",
                  "grid-template-columns": f"={NARROW} ? 'repeat(2, minmax(0, 1fr))' : 'repeat(3, minmax(0, 1fr))'"})


# ---------------------------------------------------------------- 2a. weather, a slim bar at the top

# the rule weather_forecast fills these from Open-Meteo every 30 minutes, with GeoSphere's AROME Austria model: the
# present weather as a WMO code with day or night, today's and the next two days' minimum and maximum, and for the
# weather page the next 61 hours and five days as JSON; the rule weather_warnings fills the warning items from GeoSphere
# Austria every 15 minutes. The bar takes the present temperature from the heat pump's sensor, as the temperatures
# card does
WX_NOW, WX_DAY = "weather_symbol", "weather_is_day"
WX_HOURLY, WX_DAILY = "weather_hourly", "weather_daily"
WX_LEVEL, WX_WARNINGS = "weather_warning_level", "weather_warning_list"
WX_WARNING_TEXT = "weather_warning_text"
WX_DAYS = 3
WX_WEEKDAYS = "['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa']"
# the warning levels 0 to 3: none, yellow, orange, red, in GeoSphere's colours as Material shades
WX_LEVEL_COLORS = "['#9e9e9e', '#fdd835', '#fb8c00', '#e53935']"


def wx_item(day, key):
    return f"weather_day{day}_{key}"


def wx_json(item):
    """A String item holding a JSON list, parsed; an empty list while it holds none (NULL after a restart)."""
    return f"(('' + items.{item}.state).startsWith('[') ? JSON.parse(items.{item}.state) : [])"


WX_SYMBOLS = [("clear", "wolkenlos"), ("fair", "heiter"), ("partly", "wolkig"), ("mostly", "stark bewölkt"),
              ("overcast", "bedeckt"), ("veil", "Schleierwolken"), ("fog", "Nebel"), ("rain", "Regen"),
              ("snow", "Schnee"), ("thunder", "Gewitter"), ("rain_sun", "Regenschauer"),
              ("snow_sun", "Schneeschauer"), ("thunder_sun", "Gewitterschauer")]



WX_CLOUD = "M14,38 H34 A6,6 0 0,0 35.5,26.2 A9,9 0 0,0 18.6,24.4 A7,7 0 0,0 14,38 Z"
# a crescent: a circle of 10 around (24, 24) less one of 8.5 around (29.5, 18.5)
WX_MOON = "M22.19,14.17 A10,10 0 1,0 33.83,25.81 A8.5,8.5 0 1,1 22.19,14.17 Z"


def wx_sun():
    rays = [svg("line", x1=round(24 + 10.5 * math.cos(math.radians(k * 45)), 2),
                y1=round(24 + 10.5 * math.sin(math.radians(k * 45)), 2),
                x2=round(24 + 14.5 * math.cos(math.radians(k * 45)), 2),
                y2=round(24 + 14.5 * math.sin(math.radians(k * 45)), 2), **stroke(2.2, "#ffb300"))
            for k in range(8)]
    return [svg("g", [*rays, spin(24, 24, "24s", "true")]), svg("circle", cx=24, cy=24, r=7, fill="#ffb300")]


def wx_cloud(x, y, scale=1.0, fill="#cfd8dc", line="#90a4ae"):
    """The cloud, scaled about (27, 31) and moved so that point lands on (x, y); (27, 29) is where it stands alone."""
    return svg("path", d=WX_CLOUD, transform=f"translate({x} {y}) scale({scale}) translate(-27 -31)",
               **stroke(1.6, line, fill=fill, **{"stroke-linejoin": "round"}))


def wx_layers():
    """The weather drawing's layers in a box of 48, back to front, each with the symbols it belongs to and when: only
    by day (False), only by night (True) or both (None). The sky in five levels, the sun (moon) giving way to the cloud
    from fair to mostly, a darker second cloud behind from mostly on; veil as the sun behind three thin streaks; fog,
    rain, snow and thunder under a raised cloud, the showers with the sun (moon) peeking out at its top left."""
    back = {"fill": "#b0bec5", "line": "#78909c"}
    drops = [svg("line", [dash_flow("0.9s", "true", to="-6")], x1=x, y1=36, x2=x - 2, y2=42,
                 **stroke(2.2, "#42a5f5", **{"stroke-dasharray": "3 3"})) for x in (18, 25, 32)]
    # white flakes with a thin outline, so they stay visible on a white card
    flakes = [svg("circle", [svg("animate", attributeName="cy", values=f"{y};{y + 3};{y}", dur=f"{2 + i * 0.4:.1f}s",
                                 repeatCount="indefinite")], cx=x, cy=y, r=2.6, fill="#ffffff",
                  **{"stroke": "#90a4ae", "stroke-width": 1})
              for i, (x, y) in enumerate(((18, 38.5), (25.5, 42), (33, 38.5)))]
    bolt = svg("polygon", [svg("animate", attributeName="opacity", values="1;0.35;1;1", dur="1.8s",
                               repeatCount="indefinite")],
               points="26,31 20,40 24.5,40 22,47 30,37 25.5,37 28,31", fill="#ffca28",
               **{"stroke": "#f9a825", "stroke-width": 0.8, "stroke-linejoin": "round"})
    fog = [svg("line", x1=a, y1=y, x2=b, y2=y, **stroke(2.2, "#90a4ae")) for a, b, y in ((12, 36, 37), (15, 33, 42))]
    streaks = [svg("line", x1=a, y1=y, x2=b, y2=y, opacity=0.95, **stroke(2, "#b0bec5"))
               for a, b, y in ((8, 30, 27), (16, 40, 32), (10, 32, 37))]
    layers = []

    def add(symbols, parts, night=None):
        layers.append((tuple(symbols.split()), night, svg("g", parts)))

    def lum(symbols, day_at, night_at):
        """The sun by day and the moon by night, each at (x, y, scale)."""
        at = lambda x, y, k: f"translate({x} {y}) scale({k}) translate(-24 -24)"
        add(symbols, [svg("g", wx_sun(), transform=at(*day_at))], False)
        add(symbols, [svg("path", d=WX_MOON, fill="#9fa8da", transform=at(*night_at))], True)
    lum("clear", (24, 24, 1), (24, 24, 1))
    lum("fair", (21, 21, 0.85), (21, 20, 0.82))
    add("fair", [wx_cloud(34, 37, 0.55)])
    lum("partly", (17, 17, 0.72), (17, 16, 0.7))
    add("partly", [wx_cloud(27, 34, 0.9)])
    lum("mostly", (14, 13, 0.58), (14, 12, 0.55))
    add("mostly", [wx_cloud(33, 26, 0.72, **back), wx_cloud(24, 35, 0.95)])
    add("overcast", [wx_cloud(32, 25, 0.78, **back), wx_cloud(22, 35, 0.95)])
    lum("veil", (24, 21, 0.95), (24, 21, 0.95))
    add("veil", streaks)
    add("fog", [svg("path", d=WX_CLOUD, transform="translate(24 23) scale(0.9) translate(-24 -31)",
                    **stroke(1.6, "#90a4ae", fill="#cfd8dc", **{"stroke-linejoin": "round"})), *fog])
    lum("rain_sun snow_sun thunder_sun", (14, 12, 0.6), (14, 11, 0.58))
    add("rain rain_sun", [wx_cloud(27, 25), *drops])
    add("snow snow_sun", [wx_cloud(27, 25), *flakes])
    add("thunder thunder_sun", [wx_cloud(27, 23), bolt])
    return layers


def weather_icon_widget():
    """The widget the weather is drawn with, in the style of the energy flow's nodes: symbol is one of WX_SYMBOLS, day
    whether the sun is up (the moon while it is false). The sky in five levels from clear to overcast, the sun (its
    rays turning slowly) or the moon giving way to the cloud; veil clouds as three streaks through the sun; a cloud
    raised over fog, falling rain, drifting snow or a flickering bolt, with the sun peeking out for showers. Nothing
    while symbol is none of them."""
    symbol, night = "props.symbol", "props.day === false"
    layers = []
    for symbols, by_night, layer in wx_layers():
        which = " || ".join(f"{symbol} === '{k}'" for k in symbols)
        when = "" if by_night is None else f" && {night}" if by_night else f" && !({night})"
        layer["config"]["visible"] = f"=({which}){when}"
        layers.append(layer)
    size = "=props.size || 36"
    return svg("svg", layers, viewBox="0 0 48 48", width=size, height=size,
               style={"display": "block", "flex": "0 0 auto"})


def svg_markup(node):
    """svg() components as SVG markup, without their animations."""
    tag = node["component"]
    if tag.startswith("animate"):
        return ""
    attrs = "".join(f' {k}="{v}"' for k, v in node["config"].items() if k != "visible")
    inner = "".join(svg_markup(child) for child in node.get("slots", {}).get("default", []))
    return f"<{tag}{attrs}>{inner}</{tag}>"


def wx_symbols():
    """The weather drawings as images for a chart, standing still, by symbol; those drawn otherwise by night once more
    as <symbol>_night."""
    layers = wx_layers()
    symbols = {}
    for night in (False, True):
        for k, _ in WX_SYMBOLS:
            if night and all(by_night is None for keys, by_night, _ in layers if k in keys):
                continue
            drawn = "".join(svg_markup(layer) for keys, by_night, layer in layers
                            if k in keys and by_night in (None, night))
            markup = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="48" height="48">{drawn}</svg>'
            symbols[f"{k}_night" if night else k] = ("image://data:image/svg+xml;base64,"
                                                     + base64.b64encode(markup.encode()).decode())
    return symbols


def weather_icon(symbol, day, size):
    """An instance of the weather drawing; symbol and day are expressions, evaluated where it stands."""
    return comp("widget:weather-icon", {"symbol": f"={symbol}", "day": f"={day}", "size": size})


def wx_alert_parts(level):
    """A warning sign in a 28 box: a disc in the level's colour with an exclamation mark, white on orange and red and
    dark on yellow; level is an expression."""
    color = f"={WX_LEVEL_COLORS}[Number({level})] || '#9e9e9e'"
    mark = f"=Number({level}) === 1 ? '#3e2723' : '#ffffff'"
    return [svg("circle", cx=14, cy=14, r=9, fill=color),
            svg("rect", x=12.7, y=8.6, width=2.6, height=6.6, rx=1.3, fill=mark),
            svg("circle", cx=14, cy=18.17, r=1.35, fill=mark)]


def wx_alert(level, size, **style):
    """The warning sign on its own."""
    return svg("svg", wx_alert_parts(level), viewBox="0 0 28 28", width=size, height=size,
               style={"display": "block", "flex": "0 0 auto", **style})


def wx_teaser():
    """The warning teased beside the temperature while one is in effect or near: the sign with a ring pulsing out
    of it in the level's colour; on a wider screen in a pill tinted the same way, with the warning's short text
    (Gewitter bis 20:00)."""
    level = f"items.{WX_LEVEL}.state"
    color = f"({WX_LEVEL_COLORS}[Number({level})] || '#9e9e9e')"
    wide = "screen.width >= 600"
    pulse = svg("circle", [svg("animate", attributeName="r", values="9;13.5", dur="2.2s", repeatCount="indefinite"),
                           svg("animate", attributeName="opacity", values="0.7;0", dur="2.2s",
                               repeatCount="indefinite")],
                cx=14, cy=14, r=9, fill="none", stroke=f"={color}", **{"stroke-width": 1.6})
    size = f"={wide} ? 28 : 24"
    badge = svg("svg", [pulse, *wx_alert_parts(level)], viewBox="0 0 28 28", width=size, height=size,
                style={"display": "block", "flex": "0 0 auto"})
    text = label(f"=items.{WX_WARNING_TEXT}.state", visible=f"={wide}",
                 **{"font-size": "12px", "font-weight": "600", "white-space": "nowrap"})
    return div([badge, text], visible=f"=Number({level}) > 0",
               **{"display": "flex", "align-items": "center", "gap": "4px", "border-radius": "14px",
                  "padding": f"={wide} ? '0 10px 0 0' : '0'",
                  "background": f"={wide} ? 'color-mix(in srgb, ' + {color} + ' 16%, transparent)' : 'transparent'"})


def wx_degrees(item):
    return f"({ok(item)} ? Math.round(Number(items.{item}.numericState)) + '°' : '–')"


def wx_day(day):
    """A day of the bar: its name above the day's weather drawn beside its maximum bold over its minimum pale, as in
    the forecast's day rows; the drawing is the day's symbol from the forecast's days (weather_daily), by its date,
    and nothing while the forecast has no such day."""
    name = "'Heute'" if day == 0 else f"{WX_WEEKDAYS}[dayjs().add({day}, 'day').day()]"
    symbol = (f"({wx_json(WX_DAILY)}.find((d) => dayjs(d.t * 1000).isSame(dayjs().add({day}, 'day'), 'day')) "
              f"|| {{}}).sym")
    temps = div([label(f"={wx_degrees(wx_item(day, 'max'))}", **{"font-weight": "700", "line-height": "15px"}),
                 label(f"={wx_degrees(wx_item(day, 'min'))}",
                       **{"font-size": "11px", "opacity": "0.65", "line-height": "13px"})],
                **{"display": "flex", "flex-direction": "column", "font-size": "13px", "white-space": "nowrap"})
    return div([label(f"={name}", **{"font-size": "11px", "opacity": "0.65", "line-height": "14px"}),
                div([weather_icon(symbol, "true", 24), temps], **{"display": "flex", "align-items": "center", "gap": "3px"})],
               **{"display": "flex", "flex-direction": "column", "align-items": "center"})


# the weather page's sources: Meteoblue's widget as in the sitemap, in the theme's colours; ORF only allows frames on its own
# pages (Content-Security-Policy frame-ancestors), so it opens in a tab of its own
METEOBLUE = ("https://www.meteoblue.com/de/wetter/widget/daily/wien_%c3%96sterreich_2761369?geoloc=fixed&days=5"
             "&tempunit=CELSIUS&windunit=KILOMETER_PER_HOUR&precipunit=MILLIMETER&coloured=monochrome&pictoicon=0"
             "&pictoicon=1&maxtemperature=0&maxtemperature=1&mintemperature=0&mintemperature=1&windspeed=0"
             "&windspeed=1&windgust=0&windgust=1&winddirection=0&winddirection=1&uv=0&uv=1&humidity=0&humidity=1"
             "&precipitation=0&precipitation=1&precipitationprobability=0&precipitationprobability=1&spot=0&spot=1"
             "&pressure=0&pressure=1&layout=")
ORF_WEATHER = "https://wetter.orf.at/wien/prognose"
WEATHER_PAGE = "weather"


def weather_card():
    """The weather as a slim bar across the overview: the present weather drawn, the outdoor temperature with a
    warning teased beside it while one is in effect or near, and the minimum and maximum of today and the next two
    days, each with its weather drawn; a tap opens the weather page in a popup. On a phone the gaps narrow, and below 380 px
    the chevron goes, so the teaser fits beside the days."""
    narrow = "screen.width < 600"
    now = div([weather_icon(f"items.{WX_NOW}.state", f"items.{WX_DAY}.state !== 'OFF'", 36),
               div([label(f"={disp(OUTDOOR)}", **{"font-size": "18px", "font-weight": "700", "line-height": "22px",
                                                  "white-space": "nowrap"}),
                    label("Außen", **{"font-size": "11px", "opacity": "0.65", "line-height": "14px"})],
                   **{"display": "flex", "flex-direction": "column"}),
               wx_teaser()],
              **{"display": "flex", "align-items": "center", "gap": f"={narrow} ? '6px' : '8px'"})
    days = div([wx_day(d) for d in range(WX_DAYS)],
               **{"display": "flex", "align-items": "center", "gap": f"={narrow} ? '8px' : '14px'",
                  "margin-left": "auto"})
    chevron = comp("oh-icon", {"icon": "f7:chevron_right", "width": 14, "height": 14, "visible": "=screen.width >= 380",
                               "style": {"opacity": "0.45"}})
    link = comp("oh-link", {"action": "popup", "actionModal": f"page:{WEATHER_PAGE}", "style": {
        "position": "absolute", "inset": "0", "display": "block", "border-radius": "12px"}})
    bar = div([now, days, chevron, link], **{"position": "relative", "display": "flex", "align-items": "center",
                                             "gap": f"={narrow} ? '8px' : '12px'", "padding": "2px 4px"})
    return comp("oh-card", {"contentStyle": {"padding": "8px 14px"}}, content=[bar])


def wx_day_name(t):
    """Heute, morgen or the weekday of a time in epoch seconds."""
    d = f"dayjs({t} * 1000)"
    return (f"({d}.isSame(dayjs(), 'day') ? 'heute' : {d}.isSame(dayjs().add(1, 'day'), 'day') ? 'morgen' : "
            f"{WX_WEEKDAYS}[{d}.day()])")


def wx_when(t):
    return f"{wx_day_name(t)} + ' ' + dayjs({t} * 1000).format('HH:mm')"


def weather_warnings_card():
    """GeoSphere's warnings that have not ended, each in its level's colour: type and level, period and text."""
    w = "loop.warning"
    color = f"({WX_LEVEL_COLORS}[{w}.level] || '#9e9e9e')"
    chip = label(f"='Warnstufe ' + {w}.level + ' von 3'", **{
        "background": f"={color}", "color": f"={w}.level === 1 ? '#212121' : '#ffffff'", "border-radius": "10px",
        "padding": "1px 9px", "font-size": "12px", "font-weight": "600", "white-space": "nowrap"})
    head = div([wx_alert(f"{w}.level", 20), label(f"={w}.type", **{"font-size": "15px", "font-weight": "700"}), chip],
               **{"display": "flex", "align-items": "center", "gap": "8px"})
    period = label(f"={wx_when(w + '.start')} + ' – ' + {wx_when(w + '.end')}",
                   **{"font-size": "13px", "opacity": "0.7", "margin-top": "2px"})
    text = label(f"={w}.text", visible=f"=!!{w}.text",
                 **{"font-size": "13px", "line-height": "1.4", "margin-top": "6px", "overflow-wrap": "anywhere"})
    one = div([head, period, text], **{
        "border-left": f"=('4px solid ' + {color})", "background": f"='color-mix(in srgb, ' + {color} + ' 14%, transparent)'",
        "border-radius": "8px", "padding": "8px 12px", "margin": "0 12px 8px"})
    listed = div([comp("oh-repeater", {"for": "warning", "sourceType": "array", "in": f"={wx_json(WX_WARNINGS)}",
                                       "fragment": True}, default=[one])], **{"padding-top": "4px", "padding-bottom": "4px"})
    return card("Warnungen", [listed])


# the forecast chart's three series: temperature over precipitation in the upper grid, wind in the lower
WX_TEMP_COLOR, WX_RAIN_COLOR, WX_WIND_COLOR = "#f4511e", "#42a5f5", "#78909c"
WX_SUN_COLOR = "#ffb300"  # the sun's of the weather drawings
# the wind's direction as the forecast gives it, the degrees it comes from (0 north, 90 east), drawn as an arrow the way
# it blows, pointing up at 0 before it is turned; the 16 points of the compass in German, O for east
WX_ARROW = "M12,3 L18.5,19.5 L12,15.5 L5.5,19.5 Z"
WX_POINTS = "['N', 'NNO', 'NO', 'ONO', 'O', 'OSO', 'SO', 'SSO', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']"
WX_ARROW_COLOR = "=themeOptions.dark === 'dark' ? '#b0bec5' : '#546e7a'"  # lighter on the dark theme


def wx_compass(deg):
    """The compass point of a direction in degrees, NNW for 337.5."""
    return f"{WX_POINTS}[Math.round({deg} / 22.5) % 16]"


def wx_wind_arrow(deg, size, visible):
    return svg("svg", [svg("path", d=WX_ARROW, fill=WX_ARROW_COLOR, transform=f"='rotate(' + ({deg} + 180) + ' 12 12)'")],
               viewBox="0 0 24 24", width=size, height=size, visible=visible, style={"display": "block", "flex": "0 0 auto"})


def wx_wind_arrows():
    """The wind's direction along its line, every three hours, every four on a phone: arrows a little above it. Each
    stands over the strongest wind from two hours before to two after, as wide as an arrow is on the time axis, so
    a steep line beside it never touches it."""
    every = f"({NARROW} ? 4 : 3)"
    shown = f"r[3] != null && r[4] != null && dayjs(r[0] * 1000).hour() % {every} === 0"
    peak = "a.slice(Math.max(0, i - 2), i + 3).reduce((m, x) => Math.max(m, x[3] || 0), 0)"
    return {"symbol": f"path://{WX_ARROW}", "symbolSize": 11, "symbolKeepAspect": True, "symbolOffset": [0, -13],
            "silent": True, "label": {"show": False}, "itemStyle": {"color": WX_ARROW_COLOR},
            # ECharts turns a symbol counter-clockwise
            "data": f"={wx_json(WX_HOURLY)}.map((r, i, a) => {shown} ? ({{coord: [r[0] * 1000, {peak}], "
                    f"symbolRotate: -(r[4] + 180)}}) : null).filter((p) => p)"}


# the weather's drawings over the temperature, in a box of 24: the drawing fills about two thirds of it, so three
# hours apart they keep a gap in the weather page's column
WX_SYMBOL = 24
WX_SYMBOL_NARROW = 20


def wx_weather_symbols():
    """The weather along the temperature's line, as the wind's arrows along the wind's: every three hours, every four
    on a phone, a little above the warmest hour from two hours before to two after, drawn as the widget weather-icon
    draws it, standing still."""
    every = f"({NARROW} ? 4 : 3)"
    shown = f"r[1] != null && S[r[5]] && dayjs(r[0] * 1000).hour() % {every} === 0"
    peak = "a.slice(Math.max(0, i - 2), i + 3).reduce((m, x) => (x[1] == null ? m : Math.max(m, x[1])), r[1])"
    symbols = "{" + ", ".join(f"{k}: '{v}'" for k, v in wx_symbols().items()) + "}"
    symbol = "(r[6] === 0 && S[r[5] + '_night']) || S[r[5]]"
    # smaller on a phone, where four hours are 15 to 17 px
    return {"symbolSize": f"={NARROW} ? {WX_SYMBOL_NARROW} : {WX_SYMBOL}",
            "symbolOffset": f"={NARROW} ? [0, -10] : [0, -12]", "silent": True, "label": {"show": False},
            "data": f"=((S) => {wx_json(WX_HOURLY)}.map((r, i, a) => {shown} ? ({{coord: [r[0] * 1000, {peak}], "
                    f"symbol: {symbol}}}) : null).filter((p) => p))({symbols})"}


def wx_hourly(index):
    """One column of the hourly forecast as chart data, [time in ms, value]."""
    return f"={wx_json(WX_HOURLY)}.map((r) => [r[0] * 1000, r[{index}]])"


def wx_series(name, unit, index, color, x, y, **cfg):
    # the id carries the unit, which the chart's tooltip appends to the value, as for an item's series
    return comp("oh-data-series", {"id": f"oh-data-series#{index}#{unit}", "name": name, "xAxisIndex": x,
                                   "yAxisIndex": y, "data": wx_hourly(index),
                                   "itemStyle": {"color": color}, **cfg})


def wx_midnights():
    """Dashed lines at the next three midnights."""
    return {"symbol": ["none", "none"], "silent": True, "label": {"show": False},
            "lineStyle": {"color": "#888", "type": "dashed", "opacity": 0.5},
            "data": [{"xAxis": f"=dayjs().add({d}, 'day').startOf('day').valueOf()"} for d in (1, 2, 3)]}


# the time axis' labels: the weekday in bold at midnight, the hours between, on a phone only noon
WX_TIME_LABEL = (f"=(v) => dayjs(v).hour() === 0 && dayjs(v).minute() === 0 ? '{{day|' + {WX_WEEKDAYS}[dayjs(v).day()] "
                 f"+ '}}' : {NARROW} && dayjs(v).hour() % 12 !== 0 ? '' : dayjs(v).format('HH:mm')")


# a precipitation bar as a bar series of barMaxWidth 6 draws it: centred on its hour, 6 px wide at most and about
# two thirds of an hour where hours are narrower (a phone), its top corners rounded
WX_RAIN_BAR = ("=(params, api) => api.value(1) > 0 ? ((w, top, base) => ({type: 'rect', shape: {x: top[0] - w / 2, "
               "y: top[1], width: w, height: base[1] - top[1], r: [2, 2, 0, 0]}, style: {fill: '" + WX_RAIN_COLOR
               + "'}}))(Math.min(6, api.size([3600000, 0])[0] * 0.68), api.coord([api.value(0), api.value(1)]), "
               "api.coord([api.value(0), 0])) : null")


def weather_forecast_chart():
    """The next 60 hours: temperature as a line with the weather drawn above it, over the precipitation of each hour
    as bars, the wind below with arrows of its direction, one tooltip for all three."""
    # the wind's grid 75 px high, 55 px below the temperature's, room for its axis name and the arrows above it
    grids = [comp("oh-chart-grid", {"top": "35", "height": "140", "left": "45", "right": "45"}),
             comp("oh-chart-grid", {"top": "230", "bottom": "60", "left": "45", "right": "45"})]
    x_axes = [comp("oh-time-axis", {"gridIndex": 0, "axisLabel": {"show": False}}),
              comp("oh-time-axis", {"gridIndex": 1, "axisLabel": {"formatter": WX_TIME_LABEL,
                                                                   "rich": {"day": {"fontWeight": "bold"}}}})]
    dashed = {"splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.4}}}
    # a quarter of the temperature's span above its maximum, at least a degree, for the weather's drawings; the label
    # at that odd top would crowd the one below it
    y_axes = [value_axis("°C", scale=True, minInterval=1,
                         max="=(v) => Math.ceil(v.max + Math.max(1, (v.max - v.min) * 0.25))",
                         axisLabel={"showMaxLabel": False}),
              # up to 2 mm at least so a drizzle stays small, half as much again so the bars keep out of the top third,
              # where the weather's drawings stand over the warmer hours; no label at that odd top
              comp("oh-value-axis", {"gridIndex": 0, "name": "mm", "nameGap": 14, "min": 0,
                                     "max": "=(v) => Math.max(v.max, 2) * 1.5", "splitLine": {"show": False},
                                     "axisLabel": {"showMaxLabel": False},
                                     "nameTextStyle": {"align": "left", "padding": [0, 0, 0, 8]}}),
              comp("oh-value-axis", {"gridIndex": 1, "name": "km/h", "nameGap": 10, "nameTextStyle": AXIS_NAME,
                                     # up to the next 20, halved by splitNumber: the peak gets no label of its own
                                     "min": 0, "max": "=(v) => Math.max(20, Math.ceil(v.max / 20) * 20)", "splitNumber": 2,
                                     **dashed})]
    series = [wx_series("Temperatur", "°C", 1, WX_TEMP_COLOR, 0, 0, type="line", smooth=0.5, symbol="none",
                        lineStyle={"width": 2.5, "color": WX_TEMP_COLOR}, markLine=wx_midnights(),
                        markPoint=wx_weather_symbols(), z=3),
              # precipitation is the sum of the hour before its time; the bar stands on that time all the same, as
              # the axis tooltip lists only the series with a point at the time it snaps to. Drawn by a custom
              # series, not a bar series: a bar series widens its time axis by half an hour on each side for its
              # outer bars, so the upper grid would map time to x otherwise than the wind's below it
              wx_series("Niederschlag", "mm", 2, WX_RAIN_COLOR, 0, 1, type="custom", renderItem=WX_RAIN_BAR,
                        encode={"x": 0, "y": 1}, clip=True, itemStyle={"color": WX_RAIN_COLOR}),
              wx_series("Wind", "km/h", 3, WX_WIND_COLOR, 1, 2, type="line", smooth=0.5, symbol="none",
                        lineStyle={"width": 2, "color": WX_WIND_COLOR}, areaStyle={"color": gradient(rgb_of(WX_WIND_COLOR))},
                        markLine=wx_midnights(), markPoint=wx_wind_arrows())]
    return chart({"period": "60h", "future": 1, "height": "365px",
                  # one tooltip for both grids
                  "options": {"axisPointer": {"link": [{"xAxisIndex": "all"}]}}},
                 grid=grids, xAxis=x_axes, yAxis=y_axes, series=series,
                 tooltip=tooltip(trigger="axis", smartFormatter=True), legend=legend())


def wx_day_row():
    """A day of the forecast: its name, the weather drawn, minimum and maximum, the hours of sunshine with their share
    of the daylight under it, precipitation with its probability under it, and the strongest wind with an arrow of the
    day's main direction and its compass point under it. The maximum stands over the minimum, as every other cell
    stands its second value under its first; on a phone icons, type and gaps are a little smaller, so a day keeps its
    line down to 360 px."""
    d = "loop.day"
    n = NARROW
    name = f"(dayjs({d}.t * 1000).isSame(dayjs(), 'day') ? 'Heute' : {WX_WEEKDAYS}[dayjs({d}.t * 1000).day()])"
    degrees = lambda v: f"({v} == null ? '–' : Math.round({v}) + '°')"
    rain = f"({d}.p == null ? '–' : {d}.p < 0.05 ? '0 mm' : {fixed(d + '.p', 1)} + ' mm')"
    sun = f"({d}.s == null ? '–' : {fixed(d + '.s', 1)} + ' h')"
    icon_size = f"={n} ? 13 : 15"
    small_icon = lambda icon, color: comp("oh-icon", {"icon": icon, "width": icon_size, "height": icon_size,
                                                      "style": {"color": color, "flex": "0 0 auto"}})
    cell = {"display": "flex", "align-items": "center", "gap": f"={n} ? '4px' : '5px'",
            "font-size": f"={n} ? '12px' : '13px'", "white-space": "nowrap"}
    sub = {"font-size": "11px", "opacity": "0.65", "line-height": "13px"}

    def pair(first, second, second_visible):
        return div([label(f"={first}", **{"line-height": "16px"}), label(f"={second}", visible=second_visible, **sub)],
                   **{"display": "flex", "flex-direction": "column"})
    temps = div([label(f"={degrees(d + '.lo')}", **{"opacity": "0.65", "font-size": "11px", "line-height": "13px"}),
                 label(f"={degrees(d + '.hi')}", **{"font-weight": "700", "line-height": "16px"})],
                **{"display": "flex", "flex-direction": "column-reverse", "font-size": "14px", "white-space": "nowrap"})
    return div([
        label(f"={name}", **{"font-size": f"={n} ? '13px' : '14px'", "font-weight": "600"}),
        weather_icon(f"{d}.sym", "true", f"={n} ? 28 : 32"),
        temps,
        # the share of the daylight, from sunrise to sunset, the most the sun could shine
        div([small_icon("material:wb_sunny", WX_SUN_COLOR), pair(sun, f"{d}.sp + ' %'", f"={d}.sp != null")],
            **cell),
        div([small_icon("material:water_drop", WX_RAIN_COLOR), pair(rain, f"{d}.pp + ' %'", f"={d}.pp != null")],
            **{**cell, "opacity": f"=({d}.p || 0) < 0.05 ? '0.55' : '1'"}),
        # the plain wind icon until the forecast brings a direction
        div([wx_wind_arrow(f"{d}.wd", icon_size, f"={d}.wd != null"),
             comp("oh-icon", {"icon": "material:air", "width": icon_size, "height": icon_size,
                              "visible": f"={d}.wd == null", "style": {"color": WX_WIND_COLOR, "flex": "0 0 auto"}}),
             pair(f"({d}.w == null ? '–' : {d}.w) + ' km/h'", wx_compass(d + '.wd'), f"={d}.wd != null")],
            **{**cell, "justify-content": "flex-end"}),
    ], **{"display": "grid", "align-items": "center",
          # fixed columns but the precipitation's, so the days' cells stand under each other
          "grid-template-columns": f"={n} ? '38px 28px 30px 52px 1fr auto' : '40px 32px 30px 58px 1fr auto'",
          "column-gap": f"={n} ? '5px' : '8px'", "min-height": "40px", "padding": f"={n} ? '4px 12px' : '4px 16px'",
          "border-top": "1px solid rgba(127, 127, 127, 0.15)"})


def weather_forecast_card():
    # the days first, the chart of the next hours below them, a gap between the last day and the chart
    # from today on: after midnight a run that failed would leave yesterday first
    upcoming = f"{wx_json(WX_DAILY)}.filter((d) => d.t * 1000 >= dayjs().startOf('day').valueOf()).slice(0, 5)"
    days = div([comp("oh-repeater", {"for": "day", "sourceType": "array", "in": f"={upcoming}",
                                     "fragment": True}, default=[wx_day_row()])],
               **{"padding-top": "2px", "margin-bottom": "12px"})
    return card("Vorhersage", [days, div([weather_forecast_chart()], **{"padding": "0 4px 6px"})])


def weather_cards():
    """The weather page's cards: warnings, forecast, Meteoblue and the other sources."""
    # the widget's height follows its width, 434 px at 293 px wide and 0.36 px more per pixel (measured); the frame
    # is the card's width less 52 px on a phone and 507 px at most, in the middle of a wider card on a wider screen.
    # A page cannot read the height of a frame from another site, so it is worked out from the width
    width = "Math.min(507, screen.width - 52)"
    # the widget's document declares no color-scheme: in MainUI's dark theme Chrome would paint an opaque white
    # canvas behind it, and the dark layout's white text would vanish; a light scheme keeps the canvas transparent
    frame = comp("oh-webframe", {"src": f"='{METEOBLUE}' + (themeOptions.dark === 'dark' ? 'dark' : 'light')",
                                 "height": f"=Math.ceil(434 + ({width} - 293) * 0.36) + 8 + 'px'", "frameborder": "0",
                                 "scrolling": "no", "style": {"width": "100%", "max-width": "507px", "margin": "0 auto",
                                                              "border": "0", "display": "block",
                                                              "color-scheme": "light"}})
    orf = div([comp("oh-icon", {"icon": "material:open_in_new", "width": 22, "height": 22}),
               label("Prognose für Wien bei wetter.orf.at", **{"flex": "1", "font-size": "14px"}),
               comp("oh-button", {"text": "Öffnen", "action": "url", "actionUrl": ORF_WEATHER,
                                  "actionUrlSameWindow": False, "outline": True, "small": True})],
              **{"display": "flex", "align-items": "center", "gap": "10px", "padding": "6px 16px"})
    note = label("Die Außentemperatur der Leiste misst der Sensor der Wärmepumpe. Vorhersage von Open-Meteo.com "
                 "(CC BY 4.0), Modell GeoSphere AROME Austria, spätere Stunden und Tage sowie die "
                 "Regenwahrscheinlichkeit aus dem Best Match; Warnungen von GeoSphere Austria (warnungen.zamg.at).",
                 **{"font-size": "12px", "opacity": "0.6", "padding": "4px 16px 14px"})
    return (weather_warnings_card(), weather_forecast_card(),
            card("Meteoblue · 5 Tage", [div([frame], **{"padding": "4px 12px 12px"})]), card("Weitere Quellen", [orf, note]))


def wx_warnings_row(warnings):
    """The warnings across the page, only while there are any; without them the forecast stands at the top."""
    out = row(full(warnings))
    out["config"]["visible"] = f"={wx_json(WX_WARNINGS)}.length > 0"
    return out


def weather_blocks():
    """The weather's page, in the sidebar and the weather bar's popup: on a wider screen the forecast beside
    Meteoblue and the other sources, the warnings across both."""
    warnings, forecast, meteoblue, sources = weather_cards()
    return [block(wx_warnings_row(warnings), row(col([forecast]), col([stack(meteoblue, sources)])))]


# ---------------------------------------------------------------- 2b. heat pump, in the style of the energy flow

HPX = {  # heat pump items
    "valve": "espaltherma_3way_valve_mode", "pump": "espaltherma_water_pump_operation",
    "flow": "espaltherma_flow_sensor", "hz": "espaltherma_inv_frequency", "buh1": "espaltherma_buh_step1_mode",
    "buh2": "espaltherma_buh_step2_mode", "bsh": "espaltherma_bsh_mode", "tank": "espaltherma_dhw_tank_temp",
    "tank_set": "espaltherma_dhw_setpoint", "water_pressure": "espaltherma_water_pressure", "supply": "espaltherma_leaving_water_temp_after_buh",
    "return": "espaltherma_inlet_water_temp", "outdoor": "espaltherma_ext_ambient_temp",
    "indoor": "espaltherma_indoor_ambient_temp", "power": "espaltherma_electrical_power",
    "heat": "espaltherma_heating_power", "cop": "espaltherma_cop", "defrost": "espaltherma_defrost_operaton",
    "refrigerant": "espaltherma_refrig_temp_liquid_side", "pressure": "espaltherma_refrigerant_pressure_sensor",
    "hot_gas": "espaltherma_discharge_pipe_temp",
    # the middle of the outdoor unit's heat exchanger, which the refrigerant evaporates in
    "exchanger": "espaltherma_heat_exchanger_mid_temp",
    # each device's own draw: the measured circuit of the outdoor unit, the nominal powers of the backup heater in the
    # wall unit and of the booster heater in the tank; "power" is their sum
    "circuit": "heatpump_power", "buh_power": "espaltherma_electrical_power_buh",
    "bsh_power": "espaltherma_electrical_power_bsh",
    # the water's heat after the backup heater, what the pipe from the wall unit carries to the valve
    "water_heat": "espaltherma_heating_power_after_buh",
}
PUMP_ON = f"(items.{HPX['pump']}.state === 'ON' || {num(HPX['flow'])} > 0)"
# what fills a ring of the heat pump card: the compressor's top frequency, the highest draw persisted without the
# heaters (heatpump_power, 3578 W on 2026-03-26 13:50; its single 4670 W at 0 Hz on 2026-05-15 is a glitch of the
# meter), a hot tank, the highest leaving water the one heating circuit, floor heating, is set to ([9-00] 40 °C; its
# heating curve reaches 35 °C at the coldest, [1-02]). The rings stay in the nodes' colours, graded nowhere.
HZ_FULL, POWER_FULL, TANK_FULL, SUPPLY_FULL = 74, 3578, 60, 40
DHW_MODE = f"items.{HPX['valve']}.state === 'DHW'"
HEATING_FLOW = f"({PUMP_ON} && !({DHW_MODE}))"
# the heating circuits' rings: the leaving water against its highest setting, while they carry it
CIRCUIT_SHARE = f"({HEATING_FLOW} ? {num(HPX['supply'])} / {SUPPLY_FULL} : 0)"
TANK_FLOW = f"({PUMP_ON} && ({DHW_MODE}))"
COMPRESSOR = f"{num(HPX['hz'])} > 0"
# a defrost turns the refrigerant cycle round: heat goes from the water back to the outdoor unit
DEFROSTING = f"items.{HPX['defrost']}.state === 'ON'"
BUH_ON = f"(items.{HPX['buh1']}.state === 'ON' || items.{HPX['buh2']}.state === 'ON')"
BSH_ON = f"items.{HPX['bsh']}.state === 'ON'"
SUPPLY, RETURN, REFRIGERANT = "#e57373", "#64b5f6", "#ba68c8"
SPACE_C, DHW_C, STANDBY_C = "#ffb74d", "#e57373", "#b0bec5"
ELECTRIC_C, COP_C = "#ffa726", "#66bb6a"  # the heat pump card's electricity and COP


def grad(id_, stops, vertical=True):
    return svg("linearGradient", [svg("stop", offset=o, **{"stop-color": c, "stop-opacity": op}) for o, c, op in stops],
               id=id_, x1="0", y1="0", x2="0" if vertical else "1", y2="1" if vertical else "0")


def wall_unit_node(cx, cy):
    """Indoor unit: display, backup heater (lit on BUH step 1 or 2) and pump (lit while it runs)."""
    return [ring(cx, cy, "#64b5f6"),
            svg("rect", x=cx - 11, y=cy - 17, width=22, height=34, rx=3, **stroke(1.6)),
            svg("rect", x=cx - 7, y=cy - 13, width=14, height=6, rx=1, fill="#37474f"),
            svg("path", d=f"M{cx - 8},{cy + 1} l2.7,-3 l2.7,6 l2.7,-6 l2.7,6 l2.7,-6 l2.7,6 l1.1,-3",
                **stroke(1.6, f"={BUH_ON} ? '#ff8a65' : '#9e9e9e'")),
            svg("circle", cx=cx, cy=cy + 10, r=3.5, **stroke(1.4, f"={PUMP_ON} ? '#64b5f6' : '#9e9e9e'"))]


def valve_node(cx, cy):
    """The three-way valve: the inlet from the wall unit at the right, the port to the tank at the left, the port to
    the heating riser at the top. The open outlet is filled orange, the closed one hollow and faint, so its position
    shows: up to the heating circuits, or left to the tank for hot water."""
    to_tank, to_heating = f"={DHW_MODE} ? '#fb8c00' : 'none'", f"={DHW_MODE} ? 'none' : '#fb8c00'"
    faint = lambda tank: f"={DHW_MODE} ? '{1 if tank else 0.4}' : '{0.4 if tank else 1}'"
    return [ring(cx, cy, "#ffb74d"),
            svg("polygon", points=f"{cx - 12},{cy - 6} {cx},{cy} {cx - 12},{cy + 6}",
                **stroke(1.4, fill=to_tank, **{"stroke-opacity": faint(True)})),
            svg("polygon", points=f"{cx + 12},{cy - 6} {cx},{cy} {cx + 12},{cy + 6}", **stroke(1.4, fill="#ffe0b2")),
            # the third port points up to the heating riser, the actuator hangs below
            svg("polygon", points=f"{cx - 6},{cy - 12} {cx},{cy} {cx + 6},{cy - 12}",
                **stroke(1.4, fill=to_heating, **{"stroke-opacity": faint(False)})),
            svg("line", x1=cx, y1=cy, x2=cx, y2=cy + 11, **stroke(1.6)),
            svg("rect", x=cx - 5, y=cy + 11, width=10, height=5, rx=1, **stroke(1.4))]


tank_top = (f"={num(HPX['tank'])} >= 50 ? '#ef9a9a' : {num(HPX['tank'])} >= 40 ? '#ffab91' : "
            f"{num(HPX['tank'])} >= 30 ? '#ffe0b2' : '#bbdefb'")
# the tank's temperature below it: reddish above 50 °C, orange from 40, yellow from 35, bluish below
tank_text = (f"=['NULL', 'UNDEF'].includes(items.{HPX['tank']}.state) ? 'currentColor' : {num(HPX['tank'])} > 50 ? "
             f"'#e57373' : {num(HPX['tank'])} >= 40 ? '#fb8c00' : {num(HPX['tank'])} >= 35 ? '#fbc02d' : '#64b5f6'")


def tank_layers(id_):
    """The tank's water in three layers, as hot water stratifies: the top in its temperature's colour, a warm middle,
    cool blue below; hard steps, the svg's gradient of that id."""
    return grad(id_, [(o, c, "0.9") for o, c in [("0%", tank_top), ("33%", tank_top), ("33%", "#ffcc80"),
                                                   ("66%", "#ffcc80"), ("66%", "#bbdefb"), ("100%", "#bbdefb")]])


def tank_node(cx, cy, gradient="hpTank"):
    """TWL tank in layers (tank_layers, the svg's gradient of that id; the user's pick of the variants, 2026-10-03),
    faint lines between them; the Effect Heater stands beside it, as it is mounted, joined by its two pipes: cold water
    from the tank's bottom into its foot, hot water from its head back into the tank's top. While it heats it is lit
    and its pipes run blue and red."""
    on = BSH_ON
    return [ring(cx, cy, "#e57373"),
            svg("rect", x=cx - 15, y=cy - 17, width=16, height=34, rx=8, **stroke(1.5, fill=f"url(#{gradient})")),
            *[svg("line", x1=cx - 13, y1=cy + y, x2=cx - 1, y2=cy + y, **stroke(0.8, opacity="0.5")) for y in (-6, 5)],
            svg("path", d=f"M{cx + 1},{cy + 9} H{cx + 8}", **stroke(1.4, f"={on} ? '{RETURN}' : 'currentColor'")),
            svg("path", d=f"M{cx + 11.5},{cy - 6} V{cy - 12} H{cx + 0.5}",
                **stroke(1.4, f"={on} ? '{SUPPLY}' : 'currentColor'", **{"stroke-linejoin": "round"})),
            svg("rect", x=cx + 8, y=cy - 6, width=7, height=18, rx=3.5, **stroke(1.2, fill=f"={on} ? '#ff8a65' : 'none'"))]


def tank_source_badge(cx, cy):
    """The tank's badge, upper right on the ring of its node at (cx, cy): where its heat comes from, a bolt in the
    heater red while its booster heater heats, else the heat pump in the tank ring's own colour, filled while the
    compressor charges the tank, only tinted while neither does."""
    xy = round(cx + ON_RING, 1), round(cy - ON_RING, 1)
    pump = ring_badge(*xy, "heat_pump", "#e57373", f"({TANK_FLOW} && {COMPRESSOR})")
    pump["config"]["visible"] = f"=!({BSH_ON})"
    heater = ring_badge(*xy, "electric_bolt", HEATER_RED, "true")
    heater["config"]["visible"] = f"={BSH_ON}"
    return [pump, heater]


def floor_node(cx, cy):
    return [ring(cx, cy, "#f48fb1"),
            svg("path", d=f"M{cx - 15},{cy - 10} H{cx + 15} V{cy - 3} H{cx - 15} V{cy + 4} H{cx + 15} V{cy + 11} H{cx - 15}",
                **stroke(2, "url(#hpLoopV)", **{"stroke-linejoin": "round"}))]


def radiator_node(cx, cy):
    fins = [svg("line", x1=cx - 9 + 6 * i, y1=cy - 7, x2=cx - 9 + 6 * i, y2=cy + 7, **stroke(1.6)) for i in range(4)]
    return [ring(cx, cy, "#ffab91"),
            svg("rect", x=cx - 14, y=cy - 11, width=28, height=22, rx=4, **stroke(1.6)), *fins]


def hp_text(x, y, content, size, weight="normal", anchor="middle", opacity="1", color="currentColor"):
    return svg("text", x=x, y=y, content=content, fill=color,
               **{"font-size": size, "font-weight": weight, "text-anchor": anchor, "opacity": opacity})


def path_points(d):
    """The corners of a polyline of absolute M, L, H and V commands."""
    points, x, y = [], 0, 0
    for cmd, args in re.findall(r"([MLHV])\s*([-\d.,\s]+)", d):
        nums = [float(v) for v in re.split(r"[\s,]+", args.strip()) if v]
        if cmd in "ML":
            x, y = nums[0], nums[1]
        elif cmd == "H":
            x = nums[0]
        else:
            y = nums[0]
        points.append((x, y))
    return points


def reversed_path(d):
    """A polyline of absolute M, L, H and V commands, drawn from its other end."""
    return "M" + " L".join(f"{px:g},{py:g}" for px, py in reversed(path_points(d)))


# every pipe's dots keep the same spacing, so a long pipe has more of them, not further apart ones; they all run at
# the same speed, which follows the water's flow on the water pipes and the compressor's frequency on the
# refrigerant's, in steps, as a changed duration restarts the animation
DOT_SPACING = 40  # units between two dots
HP_ORBIT = ORBIT  # the ring round every device, as in the energy flow
DOT_SPEEDS = [20, 35, 50, 65, 80]  # units per second, one per step
FLOW_STEPS = [6, 12, 18, 24]  # l/min
FREQUENCY_STEPS = [30, 45, 60, 75]  # Hz


def hp_route(d, color, active, reverse=None, pace=None):
    """Pipe along a polyline with dots running in its drawing direction while `active`, the other way while `reverse`
    holds; one dot per DOT_SPACING of its length, at a speed from DOT_SPEEDS by `pace`, a (value, steps) pair. The
    dots are spaced by their keyPoints, as on the energy flow's links."""
    points = path_points(d)
    length = sum(math.hypot(bx - ax, by - ay) for (ax, ay), (bx, by) in zip(points, points[1:]))
    count = max(1, round(length / DOT_SPACING))
    value, bins = pace
    dur = steps(value, bins, [f"{round(length / speed, 2)}s" for speed in DOT_SPEEDS])
    path = f"={reverse} ? '{reversed_path(d)}' : '{d}'" if reverse else d
    dots = []
    for i in range(count):
        o = round(i / count, 4)
        timing = ({"keyPoints": "0;1", "keyTimes": "0;1"} if i == 0 else
                  {"keyPoints": f"{o};1;0;{o}", "keyTimes": f"0;{round(1 - o, 4)};{round(1 - o, 4)};1"})
        dots.append(svg("circle", [svg("animateMotion", path=path, dur=dur, repeatCount="indefinite",
                                       calcMode="linear", **timing)],
                        visible=f"={active}", r=4.5, fill=color, cx=0, cy=0))
    return [svg("path", d=d, **stroke(3, color, opacity=f"={active} ? '0.55' : '0.18'",
                                      **{"stroke-linejoin": "round"})), *dots]


def rounded_polygon(points, r):
    """Closed path through `points` with every corner rounded by a quadratic curve of about radius r."""
    n = len(points)
    parts = []
    for i in range(n):
        (px, py), (cx, cy), (nx, ny) = points[i - 1], points[i], points[(i + 1) % n]
        def toward(ax, ay):
            dx, dy = ax - cx, ay - cy
            length = math.hypot(dx, dy)
            return round(cx + dx / length * r, 2), round(cy + dy / length * r, 2)
        a, b = toward(px, py), toward(nx, ny)
        parts.append(f"{'M' if i == 0 else 'L'}{a[0]},{a[1]} Q{cx},{cy} {b[0]},{b[1]}")
    return " ".join(parts) + " Z"


# vertical layout: eaves 162 (ridge 137, a flat pitch), upper/ground floor at 270, ground level at 386; the floors'
# nodes sit in the middle of their level, the basement's below the radiators' branch that runs across its top.
# The house runs from 100 to 610 and bounds the drawing: the outdoor unit sits on the right slope of the roof
# with its values to its left, the refrigerant runs down inside the right wall to the wall unit.
EAVE, RIDGE, FLOOR_1, GROUND_LEVEL = 162, 137, 270, 386
UPPER_Y, GROUND_Y = (EAVE + FLOOR_1) // 2, (FLOOR_1 + GROUND_LEVEL) // 2
# the basement from the top: the radiators' branch with its dots (4.5) 10 units under the ground level's line, the
# devices' badges (39 units above their middle) 10 under those dots, the floor 18.5 under their rings
BRANCH_Y = GROUND_LEVEL + 16
BASEMENT_Y = BRANCH_Y + 54
BOTTOM = BASEMENT_Y + 50
LEFT, RIGHT = 100, 610
# the basement's four devices evenly spaced from the radiators to the wall unit beside the refrigerant line, the
# radiators' ring as far from the left wall as the wall unit's from the right one; the floor loops above, left of the
# riser
WALL_X = 532
RADIATORS_X = LEFT + RIGHT - WALL_X
RADIATORS, TANK, VALVE, WALL = ((round(RADIATORS_X + (WALL_X - RADIATORS_X) * k / 3), BASEMENT_Y) for k in range(4))
# the outdoor unit on the right slope of the roof, the refrigerant down inside the right wall from it
OUT, GROUND_FH, UPPER_FH = (575, 102), (337, GROUND_Y), (337, UPPER_Y)
REFRIGERANT_X = 588
HOUSE = 0.4  # outline opacity
HP_VB = (92, 15, 526, BOTTOM + 121 - 15)  # viewBox: x, y, width, height; 7 units beside the house on both sides

# the heating water's pressure outside the range of 1 to 2,5 bar (no value is not out of range)
WATER_PRESSURE_BAD = (f"(!['NULL', 'UNDEF'].includes(items.{HPX['water_pressure']}.state) && "
                      f"({num(HPX['water_pressure'])} < 1 || {num(HPX['water_pressure'])} > 2.5))")
ROOM_X = (VALVE[0] + REFRIGERANT_X) / 2  # the middle of the room right of the riser, where its tiles sit
# the ground floor's free middle, between the lower edge of its floor line (1.4 wide) and the upper edge of the
# green ground level (3 wide)
GROUND_MID = (FLOOR_1 + 0.7 + GROUND_LEVEL - 1.5) / 2
TILE_ROW = 17  # from one row of a tile to the next
# the floors' tiles, 170 wide, stand as far from the outer wall as the ground floor's (three rows) from its floor
# and ceiling lines, about 14; their floor loops 14 right of them
FLOOR_TILE_W = 170
FLOOR_TILE_X = round(LEFT + 1 + ((GROUND_LEVEL - 1.5) - (FLOOR_1 + 0.7) - (35 + 3 * TILE_ROW)) / 2)


def percent(item):
    """A humidity in whole per cent, as the Netatmo reports it; Tado's has two decimals."""
    return f"(['NULL', 'UNDEF'].includes(items.{item}.state) ? '–' : {fixed(num(item), 0)} + ' %')"


# the tiles' places (centre x, top, width): the outdoor unit's tile beside the unit, as far above the roof as the
# indoor unit's below the basement floor, the control's level with it, flush with the left wall; the refrigerant's and the heating circuit's between riser and refrigerant line; the
# floors' left of their loops; the tank's and the indoor unit's below the house, flush with its walls
TILE_GAP = 12  # between a tile and the house's outline next to it, as below the basement floor
OUTDOOR_RIGHT = OUT[0] - HP_ORBIT - TILE_GAP  # the outdoor unit's tile ends that far from the unit's grey ring


def roof_y(x):
    """The roof's outline at x."""
    return RIDGE + abs(x - (LEFT + RIGHT) / 2) / ((RIGHT - LEFT) / 2) * (EAVE - RIDGE)


OUTDOOR_TILE = (OUTDOOR_RIGHT - 176 / 2,
                round(roof_y(OUTDOOR_RIGHT - 176) - TILE_GAP - (35 + 4 * TILE_ROW)), 176)
CONTROL_TILE = (LEFT + 176 / 2, OUTDOOR_TILE[1], 176)
REFRIGERANT_TILE = (ROOM_X, 170, 136)
CIRCUIT_TILE = (ROOM_X, round(GROUND_MID - (35 + 3 * TILE_ROW) / 2), 136)
UPPER_TILE = (FLOOR_TILE_X + FLOOR_TILE_W / 2, round(UPPER_Y - (35 + 2 * TILE_ROW) / 2), FLOOR_TILE_W)
GROUND_TILE = (FLOOR_TILE_X + FLOOR_TILE_W / 2, round(GROUND_MID - (35 + 3 * TILE_ROW) / 2), FLOOR_TILE_W)
TANK_TILE = (LEFT + 214 / 2, BOTTOM + 12, 214)
INDOOR_TILE = (RIGHT - 156 / 2, BOTTOM + 12, 156)


def hp_tile(cx, y, w, title, icon, color, on, rows, state=None):
    """A tile of the drawing, built like the switch tiles under the energy flow: a rounded card, faintly grey, tinted
    and outlined in its colour while `on`; its icon and title at the top left, then a row
    per (name, value, colour), the name small at the left, raised so the middle of its capitals meets the middle of
    the value's digits, the value bold at the right. Centred on cx from y, w wide, 35 + 17 per row high; state, an
    expression, stands at the top right where given."""
    x = cx - w / 2
    out = [svg("rect", x=x, y=y, width=w, height=35 + TILE_ROW * len(rows), rx=12,
               fill=f"={on} ? '{rgba(color, 0.2)}' : 'rgba(127, 127, 127, 0.08)'",
               stroke=f"={on} ? '{rgba(color, 0.6)}' : 'none'", **{"stroke-width": 1.5}),
           glyph(x + 19, y + 16, icon, 18, f"={on} ? '{color}' : 'currentColor'"),
           hp_text(x + 34, y + 21, title, 13, "600", anchor="start"),
           *([hp_text(x + w - 10, y + 21, state, 11, "700", anchor="end", opacity="0.7")] if state else [])]
    for k, (name, value, value_color) in enumerate(rows):
        base = y + 42 + TILE_ROW * k
        out += [hp_text(x + 10, base - 1.85, name, 11, anchor="start", opacity="0.7"),
                hp_text(x + w - 10, base, value, 15, "700", anchor="end", color=value_color)]
    return out


WATER_PACE = (num(HPX["flow"]), FLOW_STEPS)


def hp_orbit(xy, color, active, share=None, share_color=None):
    """A node's ring as in the energy flow; while `active` pulsing in the node's colour, softly where a share fills
    part of it (from 1 % on, in share_color, an expression, or the node's colour)."""
    arc = f"({share}) > 0.01" if share else "false"
    return [track(*xy), active_ring(xy, color, active, arc)] + \
        ([share_orbit(xy, share, share_color or color, 0.01)] if share else [])


hp_svg = svg("svg", [
    svg("defs", [grad("hpLoopV", [("0%", SUPPLY, "1"), ("100%", RETURN, "1")]),
                 tank_layers("hpTank")]),
    # the house as one outline without eaves, corners rounded like the cards; ground level marked inside
    svg("path", d=rounded_polygon([(LEFT, BOTTOM), (LEFT, EAVE), ((LEFT + RIGHT) / 2, RIDGE), (RIGHT, EAVE),
                                   (RIGHT, BOTTOM)], 12),
        **stroke(2, opacity=str(HOUSE), **{"stroke-linejoin": "round"})),
    svg("line", x1=LEFT + 1, y1=FLOOR_1, x2=RIGHT - 1, y2=FLOOR_1, **stroke(1.4, opacity="0.25")),
    svg("line", x1=LEFT + 2, y1=GROUND_LEVEL, x2=RIGHT - 2, y2=GROUND_LEVEL, **stroke(3, "#a5d6a7")),
    # pipes, drawn in flow direction: refrigerant from the roof down inside the wall, supply riser with one
    # branch per level; during a defrost the dots run back, as the heat goes from the water to the outdoor unit
    *hp_route(f"M{REFRIGERANT_X},{OUT[1] + 27} V{WALL[1]} H{WALL[0] + 30}", REFRIGERANT, COMPRESSOR, reverse=DEFROSTING,
              pace=(num(HPX["hz"]), FREQUENCY_STEPS)),
    *hp_route(f"M{WALL[0] - 30},{WALL[1]} H{VALVE[0] + 30}", SUPPLY, PUMP_ON, reverse=DEFROSTING, pace=WATER_PACE),
    *hp_route(f"M{VALVE[0] - 30},{VALVE[1]} H{TANK[0] + 30}", SUPPLY, TANK_FLOW, reverse=DEFROSTING, pace=WATER_PACE),
    *hp_route(f"M{VALVE[0]},{VALVE[1] - 30} V{UPPER_FH[1]} H{UPPER_FH[0] + 30}", SUPPLY, HEATING_FLOW,
              reverse=DEFROSTING, pace=WATER_PACE),
    *hp_route(f"M{VALVE[0]},{GROUND_FH[1]} H{GROUND_FH[0] + 30}", SUPPLY, HEATING_FLOW, reverse=DEFROSTING,
              pace=WATER_PACE),
    *hp_route(f"M{VALVE[0]},{BRANCH_Y} H{RADIATORS[0]} V{RADIATORS[1] - 30}", SUPPLY, HEATING_FLOW,
              reverse=DEFROSTING, pace=WATER_PACE),
    # devices where they are, drawn like the energy flow nodes
    # every device's grey ring, its dots running while it works
    # the outdoor unit's ring filled by the compressor's frequency; the wall unit's by the heat pump's own draw (its
    # measured circuit, as POWER_FULL; the tank's booster heater sits in the tank, not here), full and red while its
    # backup heater runs; the tank's by its temperature; the heating circuits' by the leaving water while they carry it
    *hp_orbit(OUT, "#fb8c00", COMPRESSOR, f"{num(HPX['hz'])} / {HZ_FULL}"),
    *hp_orbit(WALL, "#64b5f6", PUMP_ON, f"({BUH_ON} ? 1 : {num(HPX['circuit'])} / {POWER_FULL})",
              f"={BUH_ON} ? '#e53935' : '#64b5f6'"),
    *hp_orbit(VALVE, "#ffb74d", PUMP_ON),
    *hp_orbit(TANK, "#e57373", f"({TANK_FLOW} || {BSH_ON})", f"{num(HPX['tank'])} / {TANK_FULL}"),
    *hp_orbit(RADIATORS, "#ffab91", HEATING_FLOW, CIRCUIT_SHARE),
    *hp_orbit(GROUND_FH, "#f48fb1", HEATING_FLOW, CIRCUIT_SHARE),
    *hp_orbit(UPPER_FH, "#f48fb1", HEATING_FLOW, CIRCUIT_SHARE),
    flow_node("heat-pump", OUT, num(HPX["circuit"]), frequency=num(HPX["hz"])),
    *wall_unit_node(*WALL), *valve_node(*VALVE), *tank_node(*TANK),
    *radiator_node(*RADIATORS), *floor_node(*GROUND_FH), *floor_node(*UPPER_FH),
    # badges upper right on the rings, clear of the pipes: what the outdoor unit's ring shows, the compressor's
    # frequency (Hz as text), filled while it runs; what the wall unit's shows, its electrical power, filled while it draws more
    # than HP_ON watts or its backup heater runs, red like its ring then; the tank's, as in the heating card, where
    # its heat comes from
    ring_badge(round(OUT[0] + ON_RING, 1), round(OUT[1] - ON_RING, 1), "Hz", HP_ORANGE, COMPRESSOR, text=True),
    shown(ring_badge(round(WALL[0] + ON_RING, 1), round(WALL[1] - ON_RING, 1), "bolt", "#64b5f6",
                     f"{num(HPX['circuit'])} > {HP_ON}"), f"=!{BUH_ON}"),
    shown(ring_badge(round(WALL[0] + ON_RING, 1), round(WALL[1] - ON_RING, 1), "bolt", HEATER_RED, "true"),
          f"={BUH_ON}"),
    *tank_source_badge(*TANK),
    # the outdoor unit's tile in the sky left of it, clear of the roof: the power of its own circuit, the compressor's
    # frequency, the outdoor temperature and the middle of its heat exchanger; Abtauen during a defrost. 176 wide, so
    # Abtauen at its top right clears the title
    *hp_tile(*OUTDOOR_TILE, "Außengerät", "heat_pump", "#fb8c00", COMPRESSOR, [
        ("Leistung", f"={kw2(HPX['circuit'])}", "#fb8c00"),
        ("Verdichter", f"={disp(HPX['hz'])}", "currentColor"),
        ("Außen", f"={disp(HPX['outdoor'])}", "currentColor"),
        ("Wärmetauscher", f"={disp(HPX['exchanger'])}", "currentColor")],
             state=f"=items.{HPX['defrost']}.state === 'ON' ? 'Abtauen' : ''"),
    # the control's tile flush with the left wall: whether heating and hot water are on (Boost while the powerful
    # mode runs), the Smart Grid state and the automation; tinted while the grid asks for something
    *hp_tile(*CONTROL_TILE, "Regelung", "tune", "#fb8c00", "items.espaltherma_smart_grid.state !== '0'", [
        ("Heizung", "=items.pyaltherma_climate_control_power.state === 'ON' ? 'An' : 'Aus'", "currentColor"),
        ("Warmwasser", "=items.pyaltherma_dhw_powerful.state === 'ON' ? 'Boost' : "
                       "items.pyaltherma_dhw_power.state === 'ON' ? 'An' : 'Aus'", "currentColor"),
        ("Smart Grid", "=(" + " : ".join(f"items.espaltherma_smart_grid.state === '{v}' ? '{t}'" for v, t in
                                          [("1", "Sperre"), ("2", "Empfehlung"), ("3", "Befehl")]) + " : 'Normal')",
         "currentColor"),
        ("Automatik", "=items.heatpump_management.state === 'ON' ? 'An' : 'Aus'", "currentColor")]),
    # right of the riser, centred between it and the refrigerant line: the refrigerant in the upper floor, between
    # its sloping ceiling and its floor, the heating circuit in the ground floor
    *hp_tile(*REFRIGERANT_TILE, "Kältemittel", "severe_cold", REFRIGERANT, COMPRESSOR, [
        ("Heißgas", f"={disp(HPX['hot_gas'])}", "currentColor"),
        ("Flüssig", f"={disp(HPX['refrigerant'])}", "currentColor"),
        ("Druck", f"={disp(HPX['pressure'])}", "currentColor")]),
    # the heating circuit's tile: the water's heat after the backup heater (what the pipe from the wall unit carries,
    # without the booster heater in the tank) over its leaving and inlet temperatures
    *hp_tile(*CIRCUIT_TILE, "Heizkreis", "waves", SUPPLY, HEATING_FLOW, [
        ("Wärme", f"={kw2(HPX['water_heat'])}", "currentColor"),
        ("Vorlauf", f"={disp(HPX['supply'])}", SUPPLY), ("Rücklauf", f"={disp(HPX['return'])}", RETURN)]),
    # the floors' climate left of their floor loops, tinted while those carry water:
    # the upper floor's from the air conditioner (temperature) and its Tado zone (humidity), the ground floor's from
    # the heat pump's room sensor (temperature) and the Netatmo station beside it (humidity, CO₂)
    *hp_tile(*UPPER_TILE, "Obergeschoss", "bed",
             "#f48fb1", HEATING_FLOW, [
        ("Temperatur", f"={disp('faikout_perfera_temperature')}", "currentColor"),
        ("Luftfeuchtigkeit", f"={percent('tado_humidity')}", "currentColor")]),
    *hp_tile(*GROUND_TILE, "Erdgeschoss", "weekend",
             "#f48fb1", HEATING_FLOW, [
        ("Temperatur", f"={disp(HPX['indoor'])}", "currentColor"),
        ("Luftfeuchtigkeit", f"={percent('netatmo_weatherstation_atmospheric_humidity')}", "currentColor"),
        ("CO₂", f"={disp('netatmo_weatherstation_co2')}", "currentColor")]),
    # below the house, flush with its walls, the tank's and the indoor unit's tiles: the tank's temperature,
    # its setpoint and its booster heater, at work while it charges or heats; the indoor unit's flow, the circuit's
    # pressure (red outside its range) and the backup heater, at work while the pump runs; over them its own draw:
    # the measured circuit (Shelly EM) and the backup heater's steps, without the tank's booster heater
    *hp_tile(*TANK_TILE, "Warmwasserspeicher", "propane_tank", DHW_C, f"({TANK_FLOW} || {BSH_ON})", [
        ("Temperatur", f"={disp(HPX['tank'])}", tank_text), ("Soll", f"={disp(HPX['tank_set'])}", "currentColor"),
        ("Zusatzheizung", f"={BSH_ON} ? {kw2(HPX['bsh_power'])} : 'Aus'", "currentColor")]),
    *hp_tile(*INDOOR_TILE, "Innengerät", "hvac", "#64b5f6", PUMP_ON, [
        ("Leistung", f"={kw2(HPX['circuit'], HPX['buh_power'])}", "#fb8c00"),
        ("Durchfluss", f"={disp(HPX['flow'])}", "currentColor"),
        ("Druck", f"={disp(HPX['water_pressure'])}", f"={WATER_PRESSURE_BAD} ? '#e57373' : 'currentColor'"),
        ("Heizstab", f"={BUH_ON} ? {kw2(HPX['buh_power'])} : 'Aus'", "currentColor")]),
], viewBox=" ".join(map(str, HP_VB)), width="100%", style={"display": "block", "overflow": "visible"})


def stat_tile(title, value, color, icon, popup):
    """A figure of the heat pump card: a value tile sized by the width of its row (a container): a tenth larger than
    elsewhere where the row is as wide as the drawing, smaller down to 11.9 px in a narrow card or on a phone, where a
    power in kW to two decimals still fits. A tap opens its quick popup."""
    tile = comp("widget:value-tile", {"title": title, "value": value, "icon": f"material:{icon}", "color": color,
                                      "fontSize": "clamp(11.9px, 2.93cqw, 15.4px)"})
    link = hp_popup_link({"position": "absolute", "inset": "0", "display": "block", "border-radius": "12px"}, popup)
    return div([tile, link], **{"position": "relative", "min-width": "0"})


def stacked_bar(title, total, parts):
    """Today's energy as one bar split into its parts, total on the right; the parts take part in the hover
    highlight of their group, keyed by their lower-case name."""
    segs = [keyed(f"seg k k-{name.lower()}", [], title=f"='{name} · ' + {fixed(num(i), 2)} + ' kWh'",
                  visible=f"={num(i)} > 0.005", style={
                      "width": f"=({total} > 0 ? 100 * {num(i)} / {total} : 0).toFixed(1) + '%'", "background": c,
                      "height": "100%", "border-radius": "4px"}) for name, i, c in parts]
    return div([div([label(title, **{"opacity": "0.7"}), label(f"={fixed(total, 1)} + ' kWh'", **{"font-weight": "700"})],
                    **{"display": "flex", "justify-content": "space-between", "margin-bottom": "4px"}),
                div(segs, **{"display": "flex", "gap": "2px", "height": "14px"})],
               **{"margin-bottom": "12px"})


def cop_tile(title, item, color, icon, width="100%", popup=None):
    """A day's COP as Eigenverbrauch and Autarkie stand under the energy flow, the ring the same size at the same
    width: a small card with a ring filled up to 6, the value inside, the title and heute beside it, a large pale icon
    at its lower right; width is the drawing's width in the card; a tap opens the quick panel popup, if given."""
    value = num(item)
    length = round(2 * math.pi * 22, 2)
    ring = svg("svg", [svg("circle", cx=24, cy=25, r=22, **stroke(5, "#9e9e9e", **{"stroke-opacity": "0.25"})),
                       svg("circle", cx=24, cy=25, r=22, transform="rotate(-90 24 25)",
                           **stroke(5, color, **{"stroke-dasharray":
                                                  f"=({length} * Math.min(1, {value} / 6)).toFixed(1) + ' {length}'"})),
                       svg_text(24, 30, f"={value} > 0 ? {fixed(value, 1)} : '–'", 13, "700"),
                       svg_text(56, 23, title, 12, anchor="start", opacity="0.7"),
                       svg_text(56, 39, "heute", 11, anchor="start", opacity="0.5")],
               viewBox="0 0 150 50", width="100%", style={"display": "block", "overflow": "visible", "max-width": "170px",
                                                          "width": width})
    mark = comp("oh-icon", {"icon": f"material:{icon}", "width": 58, "height": 58, "style": {
        "position": "absolute", "right": "-6px", "bottom": "-10px", "opacity": "0.16", "color": color}})
    link = [hp_popup_link({"position": "absolute", "inset": "0", "display": "block", "border-radius": "12px"},
                          popup)] if popup else []
    return div([mark, div([ring], **{"position": "relative", "min-width": "0", "flex": "1 1 auto"}), *link],
               **{"position": "relative", "overflow": "hidden", "padding": "8px 10px", "border-radius": "12px",
                  "background": TILE_BG, "min-width": "0", "display": "flex", "align-items": "center"})


legend_dot = lambda name, c: keyed(f"item k k-{name.lower()}", [
    div([], **{"width": "10px", "height": "10px", "border-radius": "3px", "background": c}),
    label(name, **{"font-size": "12px", "opacity": "0.75"})], style={"display": "flex", "align-items": "center", "gap": "5px"})
def hp_stats():
    """The figures above the drawing, built with it, as their tiles link to quick popups; the row is as wide as the
    house below it, whose walls stand 7 of the drawing's 526 units in from its edges."""
    return div([stat_tile("Electrical", f"={kw2(HPX['power'])}", ELECTRIC_C, "bolt", "heatpump-electric-quick"),
                stat_tile("Heat", f"={kw2(HPX['heat'])}", SUPPLY, "local_fire_department", "heatpump-heat-quick"),
                stat_tile("COP", f"={num(HPX['cop'])} > 0 ? {fixed(num(HPX['cop']), 2)} : '–'", COP_C, "eco",
                          "heatpump-cop-quick")],
               **{"display": "grid", "grid-template-columns": "repeat(3, minmax(0, 1fr))", "gap": "8px",
                  "padding": f"0 {7 / HP_VB[2] * 100:.2f}%", "font-size": "14px", "container-type": "inline-size"})


def hp_day_split():
    """Today's electricity and heat of the heat pump, each a bar split into space heating, hot water and standby, titled
    with "heute" (no heading over them, it saves height), with their legend; hovering a part lifts it, the same part
    in the other bar and its legend entry, as in Consumption Today."""
    return [hover_group([
        stacked_bar("Electricity Today", num("espaltherma_energy_today"),
                    [("Heizung", "espaltherma_energy_space_today", SPACE_C),
                     ("Warmwasser", "espaltherma_energy_dhw_today", DHW_C),
                     ("Standby", "espaltherma_energy_standby_today", STANDBY_C)]),
        stacked_bar("Heat Today", num("espaltherma_heating_energy_today"),
                    [("Heizung", "espaltherma_heating_energy_space_today", SPACE_C),
                     ("Warmwasser", "espaltherma_heating_energy_dhw_today", DHW_C)]),
        div([legend_dot("Heizung", SPACE_C), legend_dot("Warmwasser", DHW_C), legend_dot("Standby", STANDBY_C)],
            **{"display": "flex", "gap": "14px", "margin": "-4px 0 14px"})],
        [("heizung", SPACE_C), ("warmwasser", DHW_C), ("standby", STANDBY_C)])]


def hp_box(x, y, w, h, radius):
    """A link's place over the heat pump drawing, in percent of its viewBox."""
    x0, y0, vw, vh = HP_VB
    return {"position": "absolute", "display": "block", "border-radius": radius,
            "left": f"{(x - x0) / vw * 100:.2f}%", "top": f"{(y - y0) / vh * 100:.2f}%",
            "width": f"{w / vw * 100:.2f}%", "height": f"{h / vh * 100:.2f}%"}


def hp_popup_link(style, uid):
    """Transparent link that opens a quick popup with the items it reads."""
    panel = quick_panel(uid)
    return comp("oh-link", {"action": "popup", "actionModal": panel["component"],
                            "actionModalConfig": dict(panel["config"]), "style": style})


# what a tap opens: a tile its popup, the wall unit and the outdoor unit theirs; valve, tank, radiators and floor loops
# open nothing
HP_TILE_POPUPS = [(CONTROL_TILE, 4, "heatpump-control-quick"), (OUTDOOR_TILE, 4, "heatpump-outdoor-quick"),
                  (REFRIGERANT_TILE, 3, "heatpump-refrigerant-quick"),
                  (CIRCUIT_TILE, 3, "heatpump-circuit-quick"), (UPPER_TILE, 2, "upper-floor-quick"),
                  (GROUND_TILE, 3, "ground-floor-quick"), (INDOOR_TILE, 4, "heatpump-indoor-quick")]
HP_NODE_POPUPS = [(WALL, "heatpump-indoor-quick"), (OUT, "heatpump-outdoor-quick")]


def heatpump_content():
    """The heat pump card's content, built when the card is, as its links need the quick popups: the three figures as
    a row directly above the drawing, both as wide as the drawing. The drawing takes the card's width up to its own
    size, one unit a pixel, so its texts keep the sizes of the rest of the UI instead of growing with the card; the
    column stands centred in a wider card, and in the middle of a higher one (a filled card, its auto margins)."""
    links = [*[hp_popup_link(hp_box(cx - w / 2, y, w, 35 + TILE_ROW * rows, "12px"), uid)
               for (cx, y, w), rows, uid in HP_TILE_POPUPS],
             *[hp_popup_link(hp_box(cx - HP_ORBIT, cy - HP_ORBIT, 2 * HP_ORBIT, 2 * HP_ORBIT, "50%"), uid)
               for (cx, cy), uid in HP_NODE_POPUPS]]
    drawing = div([hp_svg, *links], **{"position": "relative"})
    return [div([hp_stats(), drawing],
                **{"display": "flex", "flex-direction": "column", "gap": "12px", "width": "100%",
                   "max-width": f"{HP_VB[2]}px", "margin": "auto",
                   "padding": f"={NARROW} ? '8px 4px 12px' : '8px 0 16px'"})]

# ---------------------------------------------------------------- 3. price

price = [
    div([label(f"={disp(PRICE)}", **{"font-size": "32px", "font-weight": "700", "color": price_color}),
         label("per kWh all-in", **{"opacity": "0.7"})],
        **{"display": "flex", "flex-wrap": "wrap", "align-items": "baseline", "column-gap": "8px", "padding": "0 16px"}),
    label("='Günstigste ' + items.epex_spot_awattar_cheapest_hour.displayState + ' · teuerste ' + "
          "items.epex_spot_awattar_priciest_hour.displayState",
          **{"padding": "0 16px", "opacity": "0.7", "font-size": "13px", "margin-bottom": "12px"}),
    fill_chart(chart({"period": "2D", "future": "0.75", "height": "100%"},
          grid=[comp("oh-chart-grid", {"top": "45", "bottom": "30", "left": "45", "right": "15"})],
          xAxis=[comp("oh-time-axis", {"gridIndex": 0})],
          yAxis=[comp("oh-value-axis", {"gridIndex": 0, "name": "EUR/kWh", "nameGap": 14, "nameTextStyle": AXIS_NAME})],
          series=[time_series("All-in price", PRICE, step="end", areaStyle={"opacity": 0.25},
                              markLine={"symbol": ["none", "none"], "silent": True, "label": {"show": False},
                                        "lineStyle": {"color": "#888", "type": "dashed"},
                                        "data": [{"xAxis": "=dayjs().valueOf()"}]}),
                  # invisible, same timestamps: the axis tooltip lists all four prices together
                  *[time_series(n, i, lineStyle={"opacity": 0}, itemStyle={"color": c}, symbol="none")
                    for n, i, c in (("Total Net", "epex_spot_awattar_total_net", "#fb8c00"),
                                    ("Market Gross", "epex_spot_awattar_market_gross", "#ffb74d"),
                                    ("Market Net", "epex_spot_awattar", "#ffe0b2"))]],
          visualMap=[comp("oh-chart-visualmap", {"show": False, "type": "piecewise", "dimension": 1, "seriesIndex": 0,
                                                 "pieces": [{"lt": 0.2, "color": "#43a047"},
                                                            {"gte": 0.2, "lt": 0.3, "color": "#fb8c00"},
                                                            {"gte": 0.3, "color": "#e53935"}]})],
          tooltip=tooltip(trigger="axis", smartFormatter=True)), "=screen.width < 600 ? '260px' : '280px'"),
]

# ---------------------------------------------------------------- 4. controls


def switch_row_widget():
    """The widget every switch row is an instance of: icon, name, An or Aus and a switch in the card's colour. The
    switch is drawn, not Framework7's: a track that fills with the colour while on and a white knob that slides over;
    the icon sits in a circle tinted in the colour while on, as on the sliders. A tap anywhere on the row switches."""
    on = "items[props.item].state === 'ON'"
    badge = div([comp("oh-icon", {"icon": "=props.icon || 'material:power_settings_new'", "width": 15, "height": 15})],
                **{"width": "26px", "height": "26px", "flex": "0 0 auto", "border-radius": "50%", "display": "flex",
                   "align-items": "center", "justify-content": "center", "transition": "background 0.2s ease",
                   "background": f"={on} ? 'color-mix(in srgb, var(--switch-color) 22%, transparent)' : "
                                 "'rgba(127, 127, 127, 0.12)'"})
    knob = div([], **{"position": "absolute", "top": "2px", "left": f"={on} ? '20px' : '2px'", "width": "20px",
                      "height": "20px", "border-radius": "50%", "background": "#ffffff",
                      "box-shadow": "0 1px 3px rgba(0, 0, 0, 0.3)", "transition": "left 0.2s ease"})
    track = div([knob], **{"position": "relative", "width": "42px", "height": "24px", "flex": "0 0 auto",
                           "border-radius": "12px", "transition": "background 0.2s ease",
                           "background": f"={on} ? 'var(--switch-color)' : 'rgba(127, 127, 127, 0.35)'"})
    link = comp("oh-link", {"action": "toggle", "actionItem": "=props.item", "actionCommand": "ON",
                            "actionCommandAlt": "OFF",
                            "style": {"position": "absolute", "inset": "0", "display": "block", "border-radius": "8px"}})
    return div([badge,
                label("=props.title", **{"flex": "1", "font-size": "14px", "white-space": "nowrap", "overflow": "hidden",
                                         "text-overflow": "ellipsis"}),
                label(f"={on} ? 'An' : 'Aus'", **{"font-size": "10px", "font-weight": "700", "opacity": "0.6",
                                                  "min-width": "24px", "text-align": "right"}),
                track, link],
               **{"--switch-color": "=props.color || '#78909c'", "position": "relative", "display": "flex",
                  "align-items": "center", "gap": "8px", "padding": "5px 2px",
                  "border-bottom": "1px solid rgba(127, 127, 127, 0.15)"})


def switch_row(title, icon, item, color):
    """One compact row with a switch in the card's colour, an instance of the switch row widget."""
    return comp("widget:switch-row", {"item": item, "title": title, "icon": icon, "color": color})


def watts(item):
    return f"=Math.round({num(item)}) + ' W'"


SWITCHES = [
    # title, icon, item, colour, live value; in this order under the energy flow
    ("Kaffee", "material:coffee", "coffee_machine_switch", "#8d6e63", watts("coffee_machine_power")),
    ("E-Bikes", "material:electric_bike", "bicycle_batteries_switch", "#7cb342", watts("bicycle_batteries_power")),
    ("Büro 1", "material:computer", "office_1_switch", "#ab47bc", watts("office_1_power")),
    ("Büro 2", "material:computer", "office_2_switch", "#ab47bc", watts("office_2_power")),
    ("Terrasse", "material:light", "terrace_light_switch", "#fbc02d", watts("terrace_light_power")),
]
def is_on(item):
    return f"items.{item}.state === 'ON'"


def toggle_link(item, radius):
    """Transparent link over a whole tile or pill: a tap switches the item."""
    return comp("oh-link", {"action": "toggle", "actionItem": item, "actionCommand": "ON", "actionCommandAlt": "OFF",
                            "style": {"position": "absolute", "inset": "0", "display": "block",
                                      "border-radius": radius}})


AC_BLUE = "#29b6f6"
HP_RUNNING = f"{num(HPX['power'])} > {HP_ON}"
AC_MODES = [("A", "Auto"), ("H", "Heizen"), ("C", "Kühlen"), ("D", "Entfeuchten"), ("F", "Lüften")]
AC_FAN = [("Q", "Leise"), ("A", "Auto"), ("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"), ("5", "5")]
# the Smart Grid states in their short texts at every width; the long ones (Einschaltempfehlung …) crowd the bar
SMART_GRID = [("0", "Normal"), ("1", "Sperre"), ("2", "Empfehlung"), ("3", "Befehl")]


# Framework7 slides a highlight under the active segment of a strong bar, sized for equal segments; bars sized
# by their labels colour the active segment themselves and hide it, or it would stick out beside a narrow one
BY_TEXT_BAR = ".segmented-highlight { display: none; }"


def state_bar_widget():
    """The widget every segmented bar of the controls is an instance of: the states of one item as the segments of a
    strong bar, the current one filled in the colour; a tap sends a segment's state. options holds value=label pairs
    separated by semicolons. byText sizes the segments by their labels instead of equal widths and hides Framework7's
    sliding highlight, which is sized for equal segments and would stick out beside a narrow one."""
    def bar(by_text):
        opt = "loop.option.split('=')"
        active = f"items[props.item].state === {opt}[0]"
        width = {"flex": "1 1 auto", "width": "auto", "padding": "0 6px"} if by_text else {"padding": "0 4px"}
        button = comp("oh-button", {"text": f"={opt}[1]", "action": "command", "actionItem": "=props.item",
                                    "actionCommand": f"={opt}[0]", "small": True, "active": f"={active}",
                                    "style": {"font-size": "12px", **width,
                                              "background-color": f"=({active}) ? props.color : ''",
                                              "color": f"=({active}) ? '#ffffff' : ''"}})
        config = {"strong": True, "visible": "=!!props.byText" if by_text else "=!props.byText",
                  "style": {"flex": "=props.flex || ''", "width": "=props.width || '100%'"}}
        if by_text:
            config["stylesheet"] = BY_TEXT_BAR
        return comp("f7-segmented", config, default=[
            comp("oh-repeater", {"for": "option", "sourceType": "array", "in": "=(props.options || '').split(';')",
                                 "fragment": True}, default=[button])])
    return div([bar(True), bar(False)], **{"display": "contents"})


def state_bar(item, options, color, by_text=False, flex=None, width=None):
    """An instance of the segmented bar widget; options are (value, label) pairs, color may be an expression."""
    cfg = {"item": item, "options": ";".join(f"{v}={t}" for v, t in options), "color": color}
    if by_text:
        cfg["byText"] = True
    if flex:
        cfg["flex"] = flex
    if width:
        cfg["width"] = width
    return comp("widget:state-bar", cfg)


def smart_grid_bar():
    """The Smart Grid states sized by their texts, so Empfehlung fits on a phone; equal segments cut it off."""
    return state_bar("espaltherma_smart_grid", SMART_GRID, HP_ORANGE, by_text=True)


def smart_grid_section(row=False):
    """Smart Grid: its title, the bar below."""
    return section("material:power", "Smart Grid", HP_ORANGE, [smart_grid_bar()], row=row)


def power_pill_widget():
    """The widget every An/Aus pill is an instance of: on and off as a wide pill, a knob with the power symbol slides
    to the right and the pill fills with the device colour while on; a tap anywhere switches."""
    on = "items[props.item].state === 'ON'"
    knob = div([comp("oh-icon", {"icon": "material:power_settings_new", "width": 20, "height": 20})],
               **{"position": "absolute", "top": "4px", "left": f"={on} ? 'calc(100% - 36px)' : '4px'",
                  "width": "32px", "height": "32px", "border-radius": "50%", "display": "flex",
                  "align-items": "center", "justify-content": "center", "background": "#ffffff",
                  "color": f"={on} ? 'var(--power-color)' : '#9e9e9e'", "box-shadow": "0 1px 3px rgba(0, 0, 0, 0.3)",
                  "transition": "left 0.25s ease, color 0.25s ease"})
    text = label(f"={on} ? (props.onText || 'An') : 'Aus'",
                 **{"width": "100%", "text-align": "center", "padding": "0 44px", "font-size": "14px",
                    "font-weight": "600", "white-space": "nowrap", "overflow": "hidden", "text-overflow": "ellipsis",
                    "color": f"={on} ? '#ffffff' : ''"})
    return div([text, knob, toggle_link("=props.item", "20px")],
               **{"--power-color": "=props.color || '#78909c'", "position": "relative", "display": "flex",
                  "align-items": "center", "height": "40px", "border-radius": "20px", "flex": "0 0 auto",
                  "background": f"={on} ? 'var(--power-color)' : 'rgba(127, 127, 127, 0.18)'",
                  "transition": "background 0.25s ease"})


def power_pill(item, color, on_text):
    """An instance of the An/Aus pill widget; on_text is an expression, evaluated where the pill stands."""
    return comp("widget:power-pill", {"item": item, "color": color, "onText": f"={on_text}"})


def pill_switch_widget():
    """The widget every switch pill is an instance of: the air conditioner's An/Aus pill made small, for switches that
    stand side by side. A white knob with the icon of what it switches (the power symbol without one) slides to the
    right and the pill fills with the card's colour while on; the name stands in the part the knob leaves free. Every
    pill has the same sizes. A tap anywhere switches."""
    on = "items[props.item].state === 'ON'"
    knob = div([comp("oh-icon", {"icon": "=props.icon || 'material:power_settings_new'", "width": 16, "height": 16})],
               **{"position": "absolute", "top": "4px", "left": f"={on} ? 'calc(100% - 30px)' : '4px'",
                  "width": "26px", "height": "26px", "border-radius": "50%", "display": "flex",
                  "align-items": "center", "justify-content": "center", "background": "#ffffff",
                  "color": f"={on} ? 'var(--pill-color)' : '#9e9e9e'", "box-shadow": "0 1px 3px rgba(0, 0, 0, 0.3)",
                  "transition": "left 0.25s ease, color 0.25s ease"})
    text = label("=props.title", **{
        "width": "100%", "text-align": "center", "box-sizing": "border-box",
        "padding": f"={on} ? '0 34px 0 5px' : '0 5px 0 34px'", "font-size": "12px", "font-weight": "600",
        "white-space": "nowrap", "overflow": "hidden", "text-overflow": "ellipsis",
        "color": f"={on} ? '#ffffff' : ''", "transition": "padding 0.25s ease"})
    link = comp("oh-link", {"action": "toggle", "actionItem": "=props.item", "actionCommand": "ON",
                            "actionCommandAlt": "OFF",
                            "style": {"position": "absolute", "inset": "0", "display": "block", "border-radius": "17px"}})
    return div([text, knob, link],
               **{"--pill-color": "=props.color || '#78909c'", "position": "relative", "display": "flex",
                  "align-items": "center", "height": "34px", "min-width": "0", "border-radius": "17px",
                  "background": f"={on} ? 'var(--pill-color)' : 'rgba(127, 127, 127, 0.18)'",
                  "transition": "background 0.25s ease"})


def pill_switch(title, item, color, icon=None):
    """An instance of the switch pill widget."""
    cfg = {"item": item, "title": title, "color": color}
    if icon:
        cfg["icon"] = icon
    return comp("widget:pill-switch", cfg)


def pill_switches(*pills, columns=None, min_width="150px"):
    """Switch pills side by side: a fixed number of columns, or as many as fit at min_width."""
    cols = f"repeat({columns}, minmax(0, 1fr))" if columns else f"repeat(auto-fit, minmax({min_width}, 1fr))"
    return div(list(pills), **{"display": "grid", "grid-template-columns": cols, "gap": "6px"})


def section(icon, title, color, children, row=False, divider=True, dim=None):
    """A group of controls under its title: the icon in a circle tinted in the device colour and the title, as on a
    slider (pill-slider), the controls below. In the controls of a page (row) it has the slider rows' padding and
    divider, without row neither."""
    badge = div([comp("oh-icon", {"icon": icon, "width": 15, "height": 15})],
                **{"width": "26px", "height": "26px", "flex": "0 0 auto", "border-radius": "50%",
                   "background": f"color-mix(in srgb, {color} 20%, transparent)", "display": "flex",
                   "align-items": "center", "justify-content": "center"})
    head = div([badge, label(title, **{"font-size": "13px", "line-height": "16px"})],
               **{"display": "flex", "align-items": "center", "gap": "8px"})
    style = {"display": "flex", "flex-direction": "column", "gap": "6px",
             "padding": "8px 2px 10px" if row else "4px 0 0"}
    if row and divider:
        style["border-bottom"] = "1px solid rgba(127, 127, 127, 0.15)"
    return div([head, *children], **style, **(dim or {}))

def boost_pill_widget():
    """The widget every boost pill is an instance of: a boost as an action, icon, title and state, and Starten or
    Stoppen; while it runs the pill fills with the device colour and rings pulse from the icon. A tap anywhere
    switches."""
    on = "items[props.item].state === 'ON'"
    pulse = svg("svg", [svg("circle", [
        svg("animate", attributeName="r", values="11;19", dur="1.6s", begin=b, repeatCount="indefinite"),
        svg("animate", attributeName="opacity", values="0.7;0", dur="1.6s", begin=b, repeatCount="indefinite")],
        cx=20, cy=20, r=11, fill="none", stroke="#ffffff", **{"stroke-width": 2}) for b in ("0s", "0.8s")],
        visible=f"={on}", viewBox="0 0 40 40", width=40, height=40, style={"position": "absolute", "inset": "0"})
    badge_ = div([pulse, comp("oh-icon", {"icon": "=props.icon || 'material:bolt'", "state": "=items[props.item].state",
                                          "width": 22, "height": 22})],
                 **{"position": "relative", "width": "40px", "height": "40px", "flex": "0 0 auto", "border-radius": "50%",
                    "display": "flex", "align-items": "center", "justify-content": "center",
                    "background": f"={on} ? 'rgba(255, 255, 255, 0.22)' : "
                                  "'color-mix(in srgb, var(--boost-color) 15%, transparent)'"})
    texts = div([label("=props.title || 'Boost'", **{"font-size": "14px", "font-weight": "600", "line-height": "18px"}),
                 label(f"={on} ? (props.running || 'läuft') : 'Aus'",
                       **{"font-size": "11px", "opacity": "0.8", "line-height": "15px", "white-space": "nowrap",
                          "overflow": "hidden", "text-overflow": "ellipsis"})],
                **{"flex": "1", "min-width": "0", "display": "flex", "flex-direction": "column"})
    action = label(f"={on} ? 'Stoppen' : 'Starten'",
                   **{"flex": "0 0 auto", "padding": "3px 12px", "border-radius": "999px", "font-size": "12px",
                      "font-weight": "700",
                      "border": f"=({on} ? '1.5px solid #ffffff' : '1.5px solid var(--boost-color)')",
                      "color": f"={on} ? '#ffffff' : 'var(--boost-color)'"})
    return div([badge_, texts, action, toggle_link("=props.item", "26px")],
               **{"--boost-color": "=props.color || '#fb8c00'", "position": "relative", "display": "flex",
                  "align-items": "center", "gap": "10px", "padding": "6px 10px 6px 6px", "border-radius": "26px",
                  "background": f"={on} ? 'linear-gradient(135deg, var(--boost-color), "
                                "color-mix(in srgb, var(--boost-color) 75%, transparent))' : "
                                "'rgba(127, 127, 127, 0.1)'",
                  "color": f"={on} ? '#ffffff' : ''", "transition": "background 0.3s ease"})


def boost_pill(item, icon, color, title, running):
    """An instance of the boost pill widget; running is an expression, evaluated where the pill stands."""
    return comp("widget:boost-pill", {"item": item, "icon": icon, "color": color, "title": title,
                                      "running": f"={running}"})


def ac_mode_bar():
    """The mode can be chosen while the unit is off: the chosen one is marked grey then, blue while it runs."""
    # by text: Entfeuchten fits on phones
    return state_bar("faikout_perfera_mode", AC_MODES, f"={AC_ON_STATE} ? '{AC_BLUE}' : '#90a4ae'", by_text=True,
                     flex="1 1 100%")


def ac_fan_bar():
    return state_bar("faikout_perfera_fan", AC_FAN, f"={AC_ON_STATE} ? '{AC_BLUE}' : '#90a4ae'")


def ac_mode_section(row=False):
    return section("material:thermostat_auto", "Modus", AC_BLUE, [ac_mode_bar()], row=row)


def ac_fan_section(row=False, dim=None):
    return section("material:air", "Lüfter", AC_BLUE, [ac_fan_bar()], row=row, dim=dim)


def ac_airflow_section(row=False):
    """Luftstrom: both swings and the streamer as pills side by side."""
    return section("material:open_with", "Luftstrom", AC_BLUE, [pill_switches(
        pill_switch("Schwenken H", "faikout_perfera_swingh", AC_BLUE, "material:swap_horiz"),
        pill_switch("Schwenken V", "faikout_perfera_swingv", AC_BLUE, "material:swap_vert"),
        pill_switch("Streamer", "faikout_perfera_streamer_mode", AC_BLUE, "material:auto_awesome"),
        min_width="120px")], row=row)


def ac_modes_section(row=False):
    """Modi: Faikin's special modes as switch rows, which draw their own dividers."""
    return section("material:settings_suggest", "Modi", AC_BLUE, [div([
        switch_row("Eco", "material:eco", "faikout_perfera_eco_mode", AC_BLUE),
        switch_row("Komfort", "material:weekend", "faikout_perfera_comfort_mode", AC_BLUE),
        switch_row("Leise", "material:volume_off", "faikout_perfera_quiet_mode", AC_BLUE)])], row=row, divider=False)


def ac_control_rows():
    """The air conditioner's controls on its page, in one order."""
    return [ac_power(), ac_mode_section(row=True), ac_fan_section(row=True), ac_airflow_section(row=True),
            ac_setpoint(row=True), ac_boost(), ac_timer(row=True), ac_modes_section(row=True)]


def ac_power():
    return power_pill("faikout_perfera_switch", AC_BLUE, f"'An · ' + {disp('faikout_perfera_mode')}")


def dhw_boost():
    return boost_pill("pyaltherma_dhw_powerful", "material:rocket_launch", HP_ORANGE, "Warmwasser-Boost",
                      f"'läuft · Speicher ' + {disp(HPX['tank'])}")


def ac_boost():
    return boost_pill("faikout_perfera_powerful", "material:rocket_launch", AC_BLUE, "Boost", "'volle Leistung'")


# air_conditioning_timer_trigger sets this many minutes when the unit is switched on without a running timer
AC_AUTO_TIMER = 360
BATTERY_GREEN = "#7cb342"


def minutes_text(m):
    """Minutes as '1 h 25 min', '2 h' or '45 min'."""
    return (f"({m} >= 60 ? Math.floor({m} / 60) + ' h' + (Math.round({m} % 60) ? ' ' + Math.round({m} % 60) + ' min' : '')"
            f" : Math.round({m}) + ' min')")


def ends_at(m):
    return f"dayjs().add({m}, 'minute').format('HH:mm')"


def pill_slider_widget():
    """The widget every slider is an instance of: a setting as a wide pill slider in the device colour. A gradient
    fills the bar up to the value, the white knob stays inside it at both ends (limitKnobPosition) and its centre marks
    the value; only the knob can be dragged, so scrolling across a slider on a phone leaves it alone; dragging shows
    the value on a label, and it is sent once on release. Above the bar a badge (the icon in
    a tinted circle, or for a timer a ring that empties as the time runs down), the title with a line of context and
    the value large on the right; marks below. The tints are mixed from the colour in CSS, so the stylesheet is fixed."""
    n = "Number(items[props.item].numericState)"
    circ = 62.83  # the ring's circumference, 2π × 10
    ring = div([svg("svg", [
        svg("circle", cx=13, cy=13, r=10, fill="none", stroke="=props.color", **{"stroke-width": 3, "stroke-opacity": 0.25}),
        svg("circle", cx=13, cy=13, r=10, fill="none", stroke="=props.color", transform="rotate(-90 13 13)",
            **{"stroke-width": 3, "stroke-linecap": "round",
               "stroke-dasharray": f"=Math.min(1, Math.max(0, {n}) / (Number(props.ringFull) || Number(props.max))) * "
                                   f"{circ} + ' {circ}'",
               "opacity": f"={n} > 0 ? 1 : 0"})],
        viewBox="0 0 26 26", width=26, height=26, style={"position": "absolute", "inset": "0"}),
        comp("oh-icon", {"icon": "material:timer", "width": 14, "height": 14})],
        visible="=!!props.ring", **{"position": "relative", "width": "26px", "height": "26px", "flex": "0 0 auto",
                                     "display": "flex", "align-items": "center", "justify-content": "center"})
    badge = div([comp("oh-icon", {"icon": "=props.icon || 'material:tune'", "width": 15, "height": 15})],
                visible="=!props.ring", **{"width": "26px", "height": "26px", "flex": "0 0 auto", "border-radius": "50%",
                                           "background": "color-mix(in srgb, var(--pill-color) 20%, transparent)",
                                           "display": "flex", "align-items": "center", "justify-content": "center"})
    texts = div([label("=props.title", **{"font-size": "13px", "line-height": "16px"}),
                 label("=props.context || ''", **{"font-size": "11px", "opacity": "0.7", "line-height": "14px",
                                                  "white-space": "nowrap", "overflow": "hidden", "text-overflow": "ellipsis"})],
                **{"flex": "1", "min-width": "0", "display": "flex", "flex-direction": "column"})
    big = label("=props.value", **{"font-size": "15px", "font-weight": "700", "white-space": "nowrap",
                                   "color": "=props.valueColor !== undefined ? props.valueColor : props.color"})
    header = div([ring, badge, texts, big], **{"display": "flex", "align-items": "center", "gap": "8px"})
    # oh-slider starts at its minimum while the item's state is not known yet, and any touch that ends on it sends
    # its value, so it is only built once the state is a number (a reload, a reconnect after a restart); the box
    # keeps the bar's height meanwhile. MainUI's expressions know Number, Math, JSON and dayjs but not the global
    # isNaN or parseFloat, and an expression that fails counts as visible, hence Number.isNaN(Number.parseFloat(…)).
    # Only the knob can be dragged (draggableBar off): otherwise a finger that lands on the bar while scrolling a phone
    # sets the value there, and oh-slider sends it when the finger lifts
    slider = div([comp("oh-slider", {"item": "=props.item", "min": "=Number(props.min)", "max": "=Number(props.max)",
                                     "step": "=Number(props.step)", "releaseOnly": True, "label": True,
                                     "unit": "=props.unit", "limitKnobPosition": True, "draggableBar": False,
                                     "visible": "=!Number.isNaN(Number.parseFloat(items[props.item].state))"})],
                 **{"min-height": "32px"})
    span = "(Number(props.max) - Number(props.min))"
    mark = label("=loop.mark.split('=')[1]", **{
        "position": "absolute", "left": f"=(Number(loop.mark.split('=')[0]) - Number(props.min)) / {span} * 100 + '%'",
        "transform": "=loop.mark_idx === 0 ? 'translateX(0)' : loop.mark_idx === loop.mark_source.length - 1 ? "
                     "'translateX(-100%)' : 'translateX(-50%)'",
        "font-size": "10px", "opacity": "0.55", "white-space": "nowrap"})
    marks = div([comp("oh-repeater", {"for": "mark", "sourceType": "array", "in": "=(props.marks || '').split(';')",
                                      "fragment": True}, default=[mark])], **{"position": "relative", "height": "13px"})
    css = "\n".join([
        ".range-slider { --f7-range-size: 32px; --f7-range-bar-size: 32px; --f7-range-bar-border-radius: 16px;",
        "  --f7-range-bar-bg-color: color-mix(in srgb, var(--pill-color) 18%, transparent);",
        "  --f7-range-bar-active-bg-color: var(--pill-color); --f7-range-knob-size: 28px; --f7-range-knob-color: #ffffff;",
        "  --f7-range-knob-box-shadow: 0 1px 4px rgba(0, 0, 0, 0.35); --f7-range-label-bg-color: var(--pill-color);",
        "  --f7-range-label-text-color: #ffffff; margin: 0; }",
        ".range-bar-active { background: linear-gradient(90deg, color-mix(in srgb, var(--pill-color) 55%, transparent),",
        "  var(--pill-color)) !important; }",
        # the value while dragging: Framework7's md pin is 26 px with 10 px type and sits right above the knob, under
        # the finger on a phone; instead a label as wide as its text, well above the knob
        ".range-knob-label { width: auto !important; min-width: 0 !important; height: auto !important;",
        "  line-height: 20px !important; margin: 0 0 34px 0 !important; padding: 6px 12px !important; font-size: 16px !important;",
        "  font-weight: 700 !important; border-radius: 12px !important; white-space: nowrap;",
        "  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35); transform: translate(-50%, 100%) scale(0) !important;",
        "  transform-origin: 50% 100%; }",
        ".range-knob-label:before { display: none !important; }",
        ".range-knob-active-state .range-knob-label { transform: translate(-50%, 0) scale(1) !important; }"])
    return comp("div", {"stylesheet": css, "style": {
        "--pill-color": "=props.color || '#78909c'", "display": "flex", "flex-direction": "column", "gap": "6px",
        "padding": "=props.row ? '8px 2px 10px' : '4px 0 0'",
        "border-bottom": "=props.row ? '1px solid rgba(127, 127, 127, 0.15)' : 'none'",
        "opacity": "=props.opacity || '1'"}}, default=[header, slider, marks])


def pill_slider(item, color, low, high, step, title, value, context, marks, unit, icon=None, ring=False,
                value_color=None, dim=None, row=False, ring_full=None):
    """An instance of the slider widget; value, context and ring_full are expressions, evaluated where it stands."""
    cfg = {"item": item, "color": color, "min": low, "max": high, "step": step, "unit": unit, "title": title,
           "value": f"={value}", "context": f"={context}", "marks": ";".join(f"{v}={t}" for v, t in marks)}
    if icon:
        cfg["icon"] = icon
    if ring:
        cfg["ring"] = True
    if ring_full:
        cfg["ringFull"] = f"={ring_full}"
    if value_color is not None:
        cfg["valueColor"] = value_color
    if dim:
        cfg["opacity"] = dim["opacity"]
    if row:
        cfg["row"] = True
    return comp("widget:pill-slider", cfg)


def timer_slider(item, color, high, hours_per_tick, context, dim=None, row=False):
    """A timer on its slider: the minutes left, Aus at 0, its ring full at what it was last set to; the countdown is
    the item's rule's."""
    m = num(item)
    ticks = [(h * 60, f"{h} h" if h else "0") for h in range(0, high // 60 + 1, hours_per_tick)]
    return pill_slider(item, color, 0, high, 15, "Timer", f"{m} > 0 ? {minutes_text(m)} : 'Aus'", context, ticks,
                       "min", ring=True, value_color=f"={m} > 0 ? '{color}' : ''", dim=dim, row=row,
                       ring_full=timer_full(item, high))


def ac_timer(dim=None, row=False):
    on, m = AC_ON_STATE, num("air_conditioning_timer")
    context = (f"{m} > 0 ? ({on} ? 'schaltet um ' + {ends_at(m)} + ' aus' : 'läuft bis ' + {ends_at(m)})"
               f" : ({on} ? 'läuft ohne Timer' : 'beim Einschalten {AC_AUTO_TIMER // 60} h')")
    return timer_slider("air_conditioning_timer", AC_BLUE, 720, 3, context, dim, row)


def vent_timer(row=False):
    auto, m = is_on("ventilation_management"), num("ventilation_timer")
    context = (f"{m} > 0 ? ({auto} ? 'Automatik pausiert bis ' : 'bis ') + {ends_at(m)}"
               f" : ({auto} ? 'Automatik regelt die Stufe' : 'Automatik aus')")
    return timer_slider("ventilation_timer", VENT_TEAL, 360, 2, context, row=row)


def degrees(item):
    n = num(item)
    return f"({n} % 1 ? {fixed(n, 1)} : {n}) + ' °C'"


def ac_setpoint(dim=None, row=False):
    ticks = [(t, f"{t} °C" if t in (18, 30) else str(t)) for t in range(18, 31, 2)]
    return pill_slider("faikout_perfera_temperature_setpoint", AC_BLUE, 18, 30, 0.5, "Soll",  # the unit's range
                       degrees("faikout_perfera_temperature_setpoint"), f"'Raum ' + {disp('faikout_perfera_temperature')}",
                       ticks, "°C", icon="material:device_thermostat", dim=dim, row=row)


def dhw_setpoint(dim=None, row=False):
    auto = is_on("heatpump_dhw_management")
    return pill_slider("pyaltherma_dhw_temp_heating", HP_ORANGE, 30, 60, 5, "Warmwasser Soll",
                       degrees("pyaltherma_dhw_temp_heating"),
                       f"'Speicher ' + {disp(HPX['tank'])} + ({auto} ? ' · Automatik regelt' : '')",
                       [(30, "30 °C"), (40, "40"), (50, "50"), (60, "60 °C")], "°C", icon="material:shower", dim=dim,
                       row=row)


def lw_offset(dim=None, row=False):
    n = f"Math.round({num('pyaltherma_leaving_water_temp_offset_heating')})"
    heating = is_on("pyaltherma_climate_control_power")
    # the item is a Number:Temperature in °C; oh-slider sends its value with the unit, and "−2 K" would be taken as
    # an absolute temperature (−275.15 °C), so the offset is set and shown in °C like the item
    return pill_slider("pyaltherma_leaving_water_temp_offset_heating", HP_ORANGE, -10, 10, 1, "Vorlauf-Offset",
                       f"({n} > 0 ? '+' : '') + {n} + ' °C'",
                       f"'Vorlauf-Soll ' + {disp('espaltherma_leaving_water_setpoint')} + ({heating} ? '' : ' · Heizung aus')",
                       [(-10, "−10 °C"), (-5, "−5"), (0, "0"), (5, "+5"), (10, "+10 °C")], "°C", icon="material:tune",
                       dim=dim, row=row)


def battery_power_slider(item, title, context):
    return pill_slider(item, BATTERY_GREEN, 100, 3500, 100, title, f"Math.round({num(item)}) + ' W'", f"'{context}'",
                       [(100, "100 W"), (1000, "1 kW"), (2000, "2 kW"), (3500, "3,5 kW")], "W", icon="material:bolt",
                       row=True)


def battery_period_slider():
    item = "huawei_inverter_energy_storage_forced_charging_period"
    return pill_slider(item, BATTERY_GREEN, 5, 360, 5, "Zwangsladedauer", minutes_text(num(item)),
                       "'wie lange zwangsweise geladen wird'", [(5, "5 min"), (120, "2 h"), (240, "4 h"), (360, "6 h")],
                       "min", icon="material:hourglass_bottom", row=True)


# hot water, heating and the hot-water automation as three switch pills side by side, named short to fit a phone
# the heat pump's switches; Automatik switches the group heatpump_management, which passes the command on to its
# members (the hot-water automation heatpump_dhw_management)
HP_SWITCH_BAR = [("Heizung", "pyaltherma_climate_control_power", "material:local_fire_department"),
                 ("Warmwasser", "pyaltherma_dhw_power", "material:shower"),
                 ("Automatik", "heatpump_management", "material:auto_mode")]
HP_PILL_WIDTH = "120px"  # Warmwasser fits; three abreast in a wide panel, two and one on a phone


def hp_pill(title):
    return next(pill_switch(t, item, HP_ORANGE, icon) for t, item, icon in HP_SWITCH_BAR if t == title)


def operation_section(*titles, row=False):
    """Betrieb: the heat pump's switch pills under their title, all three or the ones given."""
    pills = [hp_pill(t) for t in (titles or [t for t, _, _ in HP_SWITCH_BAR])]
    return section("material:toggle_on", "Betrieb", HP_ORANGE, [pill_switches(*pills, min_width=HP_PILL_WIDTH)],
                   row=row)


# ---- quick controls: the panels the energy flow's heat pump, air conditioner and ventilation open

# a quick panel opens as a compact popup instead of Framework7's 630 × 630 px: MainUI puts a popup widget's style on
# the popup's page, where the mark tells it from other popups; ":root" keeps the rule unscoped while it is shown
QUICK_POPUP = (':root .popup:has(> .oh-popup[style*="--quick-popup"]) { --f7-popup-tablet-width: 420px; '
               '--f7-popup-tablet-height: min(660px, calc(100vh - 64px)); }')  # the air conditioner's needs 651


def details_button(page, color):
    return div([comp("oh-button", {"text": "Alle Details", "action": "popup", "actionModal": f"page:{page}",
                                   "outline": True, "small": True,
                                   "style": {"color": color, "border-color": color, "width": "auto",
                                             "padding": "0 12px"}})],
               **{"display": "flex", "justify-content": "flex-end", "padding-top": "4px"})


def quick(icon, title, color, state, children, page):
    """A device's main controls under a small head with its state, and the way to its page; opened as a compact
    popup, the bar names the device (config.label)."""
    head = div([div([comp("oh-icon", {"icon": icon, "width": 20, "height": 20})],
                    **{"width": "34px", "height": "34px", "flex": "0 0 auto", "border-radius": "50%",
                       "display": "flex", "align-items": "center", "justify-content": "center",
                       "background": f"color-mix(in srgb, {color} 22%, transparent)"}),
                div([label(title, **{"font-size": "15px", "font-weight": "600"}),
                     label(f"={state}", **{"font-size": "12px", "opacity": "0.7", "white-space": "nowrap",
                                           "overflow": "hidden", "text-overflow": "ellipsis"})],
                    **{"display": "flex", "flex-direction": "column", "min-width": "0"})],
               **{"display": "flex", "align-items": "center", "gap": "10px", "padding-bottom": "4px"})
    root = div([div([head, *children, details_button(page, color)],
                    **{"display": "flex", "flex-direction": "column", "gap": "6px", "padding": "12px 14px"})])
    # a chart's closed period menu would stretch the popup by its full length, as on the pages (PERIOD_MENU)
    root["config"].update({"label": title, "style": {"--quick-popup": "panel"},
                           "stylesheet": "\n".join([QUICK_POPUP, PERIOD_MENU])})
    return root


def hp_quick():
    """The heat pump: Warmwasser-Boost, Smart Grid, Betrieb and the DHW setpoint; the energy flow's heat pump and the
    heating card's tiles open it."""
    state = f"'Speicher ' + {disp(HPX['tank'])} + ' · ' + {kw(HPX['power'])}"
    return quick("material:heat_pump", "Wärmepumpe", HP_ORANGE, state,
                 [dhw_boost(), smart_grid_section(row=True), operation_section(row=True), dhw_setpoint(row=True)],
                 "heatpump")


def ac_quick():
    """The air conditioner: on/off, mode, fan, setpoint, timer and boost, in the order of its page."""
    state = (f"({AC_ON_STATE} ? 'An · ' : 'Aus · ') + {disp('faikout_perfera_mode')} + ' · Raum ' + "
             f"{disp('faikout_perfera_temperature')}")
    return quick("material:ac_unit", "Klimaanlage", AC_BLUE, state,
                 [ac_power(), ac_mode_section(row=True), ac_fan_section(row=True), ac_setpoint(row=True),
                  ac_timer(row=True), ac_boost()],
                 "air_conditioning")


def vent_quick():
    """The ventilation: its level, the timer and the automation."""
    state = f"'Stufe ' + {disp('esplyfterl_level')} + ' · CO₂ ' + {disp('netatmo_weatherstation_co2')}"
    level = section("material:air", "Stufe", VENT_TEAL, [state_bar("esplyfterl_level", VENT_LEVELS, VENT_TEAL)],
                    row=True)
    return quick("material:air", "Lüftung", VENT_TEAL, state,
                 [level, vent_timer(row=True), switch_row("Automatik", "material:tune", "ventilation_management",
                                                          VENT_TEAL)], "ventilation")


# ---- the popups of the heat pump card's tiles

def hp_control_quick():
    """The heat pump's control: heating, hot water and the automation, the hot-water boost and the Smart Grid."""
    on = lambda item: f"(items.{item}.state === 'ON' ? 'an' : 'aus')"
    state = f"'Heizung ' + {on('pyaltherma_climate_control_power')} + ' · Warmwasser ' + {on('pyaltherma_dhw_power')}"
    return quick("material:tune", "Regelung", HP_ORANGE, state,
                 [operation_section(row=True), dhw_boost(), smart_grid_section(row=True)], "heatpump")


def hp_indoor_quick():
    """The indoor unit: all the heat pump's controls, as on its page."""
    state = f"'Vorlauf ' + {disp(HPX['supply'])} + ' · ' + {disp(HPX['flow'])}"
    return quick("material:hvac", "Innengerät", "#64b5f6", state,
                 [smart_grid_section(row=True), operation_section(row=True), dhw_setpoint(row=True), dhw_boost(),
                  lw_offset(row=True)], "heatpump")


def hp_outdoor_quick():
    """The outdoor unit over the day: its circuit's power with the compressor's frequency, the outdoor temperature
    against its heat exchanger's, whose gap tells how hard it pulls heat from the air."""
    state = f"{kw2(HPX['circuit'])} + ' · ' + {disp(HPX['hz'])} + ' · außen ' + {disp(HPX['outdoor'])}"
    work = day_chart([area("Leistung", HPX["circuit"], HP_ORANGE), line("Verdichter", HPX["hz"], "#78909c", y=1)],
                     [value_axis("W", min=0), value_axis("Hz", min=0)], height="280px")
    temps = day_chart([line("Außen", HPX["outdoor"], "#26a69a"), line("Wärmetauscher", HPX["exchanger"], "#4fc3f7"),
                       line("Außenluft", "espaltherma_outdoor_air_temp", "#9e9e9e", dashed=True)],
                      [value_axis("°C", scale=True)], height="250px")
    return quick("material:heat_pump", "Außengerät", HP_ORANGE, state, [work, temps], "heatpump")


def hp_refrigerant_quick():
    """The refrigerant over the day: hot gas with its target, liquid and the outdoor heat exchanger, the pressure."""
    state = f"'Heißgas ' + {disp(HPX['hot_gas'])} + ' · ' + {disp(HPX['pressure'])}"
    temps = day_chart([line("Heißgas", HPX["hot_gas"], REFRIGERANT),
                       line("Heißgas Soll", "espaltherma_target_discharge_temp", REFRIGERANT, dashed=True),
                       line("Flüssig", HPX["refrigerant"], "#4fc3f7"),
                       line("Wärmetauscher", HPX["exchanger"], "#26a69a")], [value_axis("°C", scale=True)],
                      height="270px")
    pressure = day_chart([line("Druck", HPX["pressure"], REFRIGERANT)], [value_axis("bar", scale=True)], height="200px")
    return quick("material:severe_cold", "Kältemittel", REFRIGERANT, state, [temps, pressure], "heatpump")


def hp_circuit_quick():
    """The heating circuit: its leaving water offset, leaving and inlet water over the day with the water's heat."""
    state = f"'Vorlauf ' + {disp(HPX['supply'])} + ' · Rücklauf ' + {disp(HPX['return'])}"
    temps = day_chart([line("Vorlauf", HPX["supply"], SUPPLY), line("Rücklauf", HPX["return"], RETURN),
                       area("Wärme", HPX["water_heat"], HP_ORANGE, y=1)],
                      [value_axis("°C", scale=True), value_axis("W")], height="300px")
    return quick("material:waves", "Heizkreis", SUPPLY, state, [lw_offset(row=True), temps], "heatpump")


def floor_quick(title, icon, temperature, humidity, co2, page):
    """A floor's climate over the day: temperature and humidity, the CO₂ where it is measured."""
    state = f"{disp(temperature)} + ' · ' + {percent(humidity)}" + (f" + ' · ' + {disp(co2)}" if co2 else "")
    charts = [day_chart([line("Temperatur", temperature, "#f48fb1"), line("Luftfeuchtigkeit", humidity, "#4fc3f7", y=1)],
                        [value_axis("°C", scale=True), value_axis("%", scale=True)], height="290px")]
    if co2:
        charts.append(day_chart([area("CO₂", co2, "#78909c")], [value_axis("ppm", scale=True)], height="200px"))
    return quick(f"material:{icon}", title, "#f48fb1", state, charts, page)


# the parts heatpump_metering splits the heat pump's power and energy into, in the colours of the card's day bars
HP_PARTS = [("Heizung", "space", SPACE_C), ("Warmwasser", "dhw", DHW_C), ("Standby", "standby", STANDBY_C)]


def hp_split_quick(title, icon, color, power, today, part_power, part_energy, parts):
    """Electricity or heat by part: the parts' power over the day, their energy per day of the month stacked;
    part_power and part_energy name a part's items by its key."""
    state = f"{kw2(power)} + ' · heute ' + {fixed(num(today), 1)} + ' kWh'"
    day = day_chart([area(name, part_power.format(key), c) for name, key, c in parts], height="260px")
    month = month_chart([daily(name, part_energy.format(key), c, stack="day",
                               **({"itemStyle": {"color": c, "borderRadius": [4, 4, 0, 0]}} if i == len(parts) - 1
                                  else {}))
                         for i, (name, key, c) in enumerate(parts)], "kWh")
    return quick(f"material:{icon}", title, color, state, [day, month], "heatpump")


def hp_cop_quick():
    """The COP over the day against the outdoor temperature it follows, and the day's COPs per day of the month:
    space heating and hot water as columns, the total as a line."""
    cop = num(HPX["cop"])
    day_cop = num("espaltherma_dcop")
    state = f"'jetzt ' + ({cop} > 0 ? {fixed(cop, 2)} : '–') + ' · heute ' + ({day_cop} > 0 ? {fixed(day_cop, 2)} : '–')"
    day = day_chart([area("COP", HPX["cop"], COP_C), line("Außen", HPX["outdoor"], "#26a69a", y=1, dashed=True)],
                    [value_axis("COP", min=0), value_axis("°C", scale=True)], height="280px")
    month = month_chart([daily("Heizung", "espaltherma_dcop_space", SPACE_C,
                               itemStyle={"color": SPACE_C, "borderRadius": [3, 3, 0, 0]}),
                         daily("Warmwasser", "espaltherma_dcop_dhw", DHW_C,
                               itemStyle={"color": DHW_C, "borderRadius": [3, 3, 0, 0]}),
                         daily("Gesamt", "espaltherma_dcop", COP_C, type="line", symbol="circle", symbolSize=5,
                               lineStyle={"width": 2, "color": COP_C})], "COP")
    return quick("material:eco", "COP", COP_C, state, [day, month], "heatpump")


QUICK_PANELS = {"heatpump-quick": hp_quick, "air-conditioner-quick": ac_quick, "ventilation-quick": vent_quick,
                "heatpump-control-quick": hp_control_quick, "heatpump-indoor-quick": hp_indoor_quick,
                "heatpump-outdoor-quick": hp_outdoor_quick,
                "heatpump-refrigerant-quick": hp_refrigerant_quick, "heatpump-circuit-quick": hp_circuit_quick,
                "heatpump-electric-quick": lambda: hp_split_quick(
                    "Elektrisch", "bolt", ELECTRIC_C, HPX["power"], "espaltherma_energy_today",
                    "espaltherma_electrical_power_{}", "espaltherma_energy_{}_today", HP_PARTS),
                "heatpump-heat-quick": lambda: hp_split_quick(
                    "Wärme", "local_fire_department", SUPPLY, HPX["heat"], "espaltherma_heating_energy_today",
                    "espaltherma_heating_power_{}", "espaltherma_heating_energy_{}_today", HP_PARTS[:2]),
                "heatpump-cop-quick": hp_cop_quick,
                "upper-floor-quick": lambda: floor_quick("Obergeschoss", "bed", "faikout_perfera_temperature",
                                                         "tado_humidity", None, "air_conditioning"),
                "ground-floor-quick": lambda: floor_quick("Erdgeschoss", "weekend", HPX["indoor"],
                                                          "netatmo_weatherstation_atmospheric_humidity",
                                                          "netatmo_weatherstation_co2", "netatmo")}
_QUICK = {}


def quick_panel(uid):
    """An instance of a quick panel widget with its items (built once)."""
    if uid not in _QUICK:
        _QUICK[uid] = role_widget(uid, QUICK_PANELS[uid])
    return _QUICK[uid]


# widgets whose props are items named by their role, built with the items and turned into props (see widgets()):
# uid: (builder, title); a card places them with their items, which it takes from its own props in turn
ROLE_WIDGETS = {}
ITEM_PARAMS = {}  # uid: the props of a widget that take an item, for the widgets that place it


def role_widget(uid, builder):
    """An instance of a widget built from builder with its items as role props; its charts start below their period
    buttons, as on the pages."""
    tree = plots_below_controls(builder())
    props = {i: item_prop(i) for i in items_in(tree)}
    ROLE_WIDGETS[uid] = (tree, props)
    ITEM_PARAMS[uid] = set(props.values())
    return comp(f"widget:{uid}", {p: i for i, p in props.items()})


def switch_tile_widget():
    """The widget every switch tile is an instance of: a plug or device as a small card, its icon and An or Aus, name,
    a value and an optional second one (e.g. power and today's energy); a tap anywhere switches it; while on it is
    tinted and outlined in its colour."""
    on = "items[props.item].state === 'ON'"
    line = {"white-space": "nowrap", "overflow": "hidden", "text-overflow": "ellipsis"}
    return div([div([comp("oh-icon", {"icon": "=props.icon", "state": "=items[props.item].state", "width": 22,
                                      "height": 22}),
                     label(f"={on} ? 'An' : 'Aus'", **{"font-size": "11px", "font-weight": "700", "opacity": "0.7"})],
                    **{"display": "flex", "justify-content": "space-between", "align-items": "flex-start"}),
                label("=props.title", **{**line, "font-size": "13px", "font-weight": "600", "margin-top": "5px",
                                         "line-height": "16px"}),
                label("=props.value || ''", **{**line, "font-size": "12px", "opacity": "0.7", "line-height": "15px"}),
                label("=props.energy || ''", visible="=!!props.energy",
                      **{**line, "font-size": "11px", "opacity": "0.55", "line-height": "14px"}),
                toggle_link("=props.item", "12px")],
               **{"--tile-color": "=props.color || '#78909c'", "position": "relative", "padding": "8px 9px",
                  "border-radius": "12px", "min-width": "0", "display": "flex", "flex-direction": "column",
                  "background": f"={on} ? 'color-mix(in srgb, var(--tile-color) 20%, transparent)' : "
                                "'rgba(127, 127, 127, 0.08)'",
                  "box-shadow": f"={on} ? 'inset 0 0 0 1.5px color-mix(in srgb, var(--tile-color) 60%, transparent)' : "
                                "'none'"})


def switch_tile(title, icon, item, color, value, energy=None):
    cfg = {"item": item, "title": title, "icon": icon, "color": color, "value": value}
    if energy:
        cfg["energy"] = energy
    return comp("widget:switch-tile", cfg)


def switch_tiles():
    """The switches under the energy flow, five abreast, three on a phone, with power and today's energy."""
    tiles = [switch_tile(title, icon, item, color, value,
                         f"={fixed(num(item.replace('_switch', '_energy_today')), 2)} + ' kWh'")
             for title, icon, item, color, value in SWITCHES]
    return div(tiles, **{"display": "grid", "gap": "6px",
                         "grid-template-columns": f"={NARROW} ? 'repeat(3, minmax(0, 1fr))' : "
                                                  f"'repeat({len(SWITCHES)}, minmax(0, 1fr))'"})


# ---------------------------------------------------------------- 5. consumption today

parts = [
    # name, items, pastel colour
    ("Wärmepumpe", ["espaltherma_energy_today"], "#ffb74d"),
    ("Klimaanlage", ["air_conditioning_energy_today"], "#4fc3f7"),
    ("Büros", ["office_1_energy_today", "office_2_energy_today"], "#ce93d8"),
    ("Netzwerk", ["network_energy_today"], "#9fa8da"),
    ("Lüftung", ["ventilation_energy_today"], "#80cbc4"),
    ("Kühlschrank", ["refrigerator_energy_today"], "#b0bec5"),
    ("Kaffeemaschine", ["coffee_machine_energy_today"], "#bcaaa4"),
    ("Wohnzimmer Medien", ["living_room_entertainment_energy_today"], "#f48fb1"),
    ("Wäsche & Geschirr", ["dishwasher_energy_today", "washing_machine_1_energy_today",
                          "washing_machine_2_energy_today", "tumble_dryer_energy_today"], "#aed581"),
    ("Terrasse & Fahrräder", ["terrace_light_energy_today", "bicycle_batteries_energy_today"], "#fff176"),
]
HOME_DAY = num("home_ec_day")
metered = " + ".join(num(i) for _, its, _ in parts for i in its)
values = [(name, "(" + " + ".join(num(i) for i in its) + ")", color) for name, its, color in parts]
# the E-Car charges on the air conditioning's circuit: the air conditioner's own energy and the car's make the
# row of the meter, whose value stays in the sum
ECAR_DAY = num("e_car_energy_today")
values[1] = ("Klimaanlage", num("air_conditioning_unit_energy_today"), values[1][2])
values.insert(1, ("E-Auto", ECAR_DAY, "#26a69a"))
values.append(("Nicht gemessen", f"Math.max(0, {HOME_DAY} - ({metered}))", "#e0e0e0"))
FROM_PV, FROM_GRID = num("photovoltaics_own_ec_day"), num("huawei_inverter_power_meter_ec_day")
PV_GREEN, GRID_RED = "#a5d6a7", "#ef9a9a"


def share(value):
    return f"({HOME_DAY} > 0 ? Math.round(100 * {value} / {HOME_DAY}) : 0)"


def dot(color, size="10px"):
    return div([], **{"width": size, "height": size, "border-radius": "50%", "background": color, "flex": "0 0 auto"})


def segment(key, value, color, title):
    return keyed(f"seg k k-{key}", [], title=title, visible=f"={value} > 0.005", style={
        "width": f"=({HOME_DAY} > 0 ? 100 * {value} / {HOME_DAY} : 0).toFixed(2) + '%'", "height": "100%",
        "background": color, "border-radius": "4px"})


def segment_bar(segments, height):
    return div(segments, **{"display": "flex", "gap": "2px", "height": height})


def legend_row(key, name, value, color):
    return keyed(f"item k k-{key}", [
        dot(color),
        label(name, **{"flex": "1", "min-width": "0", "white-space": "nowrap", "overflow": "hidden",
                       "text-overflow": "ellipsis"}),
        label(f"={fixed(value, 2)} + ' kWh'", **{"font-weight": "600", "white-space": "nowrap"}),
        label(f"={share(value)} + ' %'", **{"opacity": "0.6", "min-width": "40px", "text-align": "right"})],
        style={"display": "flex", "align-items": "center", "gap": "8px", "font-size": "13px",
               "break-inside": "avoid", "margin-bottom": "2px"})


def source_head(key, value, title, color, align):
    return keyed(f"item k k-{key}", [
        label(f"={share(value)} + ' %'", **{"font-size": "26px", "font-weight": "700", "color": color,
                                            "line-height": "30px"}),
        label(f"='{title} · ' + {fixed(value, 1)} + ' kWh'", **{"font-size": "12px", "opacity": "0.7"})],
        style={"text-align": align})


consumption = [div([
    hover_group([div([source_head("pv", FROM_PV, "aus PV", "#43a047", "left"),
                      source_head("grid", FROM_GRID, "aus dem Netz", "#e53935", "right")],
                     **{"display": "flex", "justify-content": "space-between", "margin-bottom": "6px"}),
                 segment_bar([segment("pv", FROM_PV, PV_GREEN, "=" + share(FROM_PV) + " + ' % aus PV'"),
                              segment("grid", FROM_GRID, GRID_RED, "=" + share(FROM_GRID) + " + ' % aus dem Netz'")],
                             "10px")],
                [("pv", PV_GREEN), ("grid", GRID_RED)]),
    label("Consumers", **{"font-size": "13px", "opacity": "0.7", "margin": "16px 0 6px"}),
    hover_group([segment_bar([segment(f"c{i}", v, c, f"='{n} · ' + {fixed(v, 2)} + ' kWh · ' + {share(v)} + ' %'")
                              for i, (n, v, c) in enumerate(values)], "18px"),
                 # read down the first column, then the second
                 div([legend_row(f"c{i}", n, v, c) for i, (n, v, c) in enumerate(values)],
                     **{"columns": "2 230px", "column-gap": "24px", "margin-top": "12px"})],
                [(f"c{i}", c) for i, (_, _, c) in enumerate(values)]),
], **{"padding": "4px 16px 16px"})]

# ---------------------------------------------------------------- 6. energy per day

SELF_C, IMPORT_C, PV_C = "#81c784", "#e57373", "#ffa000"


def daily(name, item, color, **extra):
    return comp("oh-aggregate-series", {"name": name, "gridIndex": 0, "xAxisIndex": 0, "yAxisIndex": 0, "type": "bar",
                                        "item": item, "aggregationFunction": "last", "dimension1": "date",
                                        "itemStyle": {"color": color}, **extra})


# one column per day of the month: home consumption split into PV and grid, the PV production as a line
energy_days = chart({"chartType": "month", "periodVisible": True, "height": "100%"},
                    grid=[comp("oh-chart-grid", {"top": "40", "bottom": "70", "left": "45", "right": "45"})],
                    xAxis=[comp("oh-category-axis", {"gridIndex": 0, "categoryType": "month", "name": "Tag", "nameGap": 12,
                                                     "axisTick": {"show": False}})],
                    yAxis=[comp("oh-value-axis", {"gridIndex": 0, "name": "kWh", "nameGap": 14,
                                                  "nameTextStyle": AXIS_NAME,
                                                  "splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.4}}})],
                    series=[daily("From PV", "energy_daily_self_use", SELF_C, stack="home"),
                            daily("From Grid", "energy_daily_grid_import", IMPORT_C, stack="home",
                                  itemStyle={"color": IMPORT_C, "borderRadius": [4, 4, 0, 0]}),
                            daily("PV Production", "energy_daily_pv", PV_C, type="line", symbol="circle",
                                  symbolSize=7, lineStyle={"width": 2.5, "color": PV_C}, z=3)],
                    tooltip=tooltip(trigger="axis", smartFormatter=True), legend=legend())

# ---------------------------------------------------------------- 7. PV calendar

# the card's views of the year, by the value of its variable pvView, and the texts of the bar that switches them:
# on a wider screen the year's calendar, by default, the month calendars and the bars; on a phone the year's 53 weeks
# would leave a day about 5 px wide, so there the bar offers the half-years, by default, instead of the year. pvView
# starts empty, so each width opens on its own default (PV_VIEW)
PV_VIEWS = [("year", "Jahr"), ("halves", "Halbjahre"), ("months", "Monate"), ("bars", "Balken")]
PV_VIEW = f"(vars.pvView || ({NARROW} ? 'halves' : 'year'))"


def pv_shows(view, width=None):
    """The visible expression of a view's chart; width 'narrow' or 'wide' for a chart made for one of them."""
    where = {"narrow": f"({NARROW}) && ", "wide": f"!({NARROW}) && ", None: ""}[width]
    return f"={where}{PV_VIEW} === '{view}'"


PV_SCALE = ["#eeeeee", "#ffe082", "#ffb300", "#e65100"]
calendar = chart({"chartType": "year", "periodVisible": True, "height": "250px", "visible": pv_shows("year", "wide")},
                 calendar=[comp("oh-calendar-axis", {"orient": "horizontal", "cellSize": ["auto", "auto"],
                                                     "top": "75", "bottom": "10", "left": "40", "right": "20",
                                                     "dayLabel": {"firstDay": 1}, "yearLabel": {"show": False},
                                                     "monthLabel": {"fontSize": "=screen.width < 600 ? 8 : 12"}})],
                 series=[comp("oh-calendar-series", {"name": "PV Production", "type": "heatmap", "calendarIndex": 0,
                                                     "item": "energy_daily_pv", "aggregationFunction": "last"})],
                 visualMap=[comp("oh-chart-visualmap", {"show": "=!(screen.width < 600)", "min": 0, "max": 60, "type": "continuous", "calculable": True,
                                                        "orient": "horizontal", "left": "center", "top": "8", "itemWidth": 12, "itemHeight": 200,
                                                        "inRange": {"color": PV_SCALE}})],
                 tooltip=tooltip())


# Halbjahre on a phone: the year in two halves, January to June above July to December, cells twice as wide as in the
# year's calendar. MainUI gives every calendar the whole selected year (oh-calendar-axis sets range to the chart's period), so
# both show the whole year, 53 week columns of a fixed width, the second shifted left by 26 columns, to the week of
# 1 July; masks in the chart's colour hide what either shows beyond its half, and the second half's weekday names are
# drawn beside it, its own standing far off to the left. The size is given as width and height: MainUI always sets
# right and bottom, and with both sides set ECharts sizes the cells itself. The canvas is 28 px narrower than the
# screen: 27 columns fill it, the lower half's
PV_CW = "(screen.width - 64) / 27"  # a week column
PV_X0, PV_CH, PV_T1, PV_T2 = 28, 14, 78, 210  # the cells' left edge, a day's height, the halves' tops
PV_BG = "=themeOptions.dark === 'dark' ? '#121212' : '#ffffff'"  # MainUI's dark chart background, the white card
PV_DAYS = ["M", "D", "M", "D", "F", "S", "S"]


def pv_half(top, left):
    return comp("oh-calendar-axis", {"orient": "horizontal", "cellSize": ["auto", "auto"], "width": f"=53 * {PV_CW}",
                                     "height": 7 * PV_CH, "top": str(top), "bottom": "10", "left": left, "right": "20",
                                     "dayLabel": {"firstDay": 1}, "yearLabel": {"show": False},
                                     "monthLabel": {"fontSize": 10}})


def pv_mask(x, y, width, height):
    return {"type": "rect", "z": 100, "shape": {"x": x, "y": y, "width": width, "height": height},
            "style": {"fill": PV_BG}}


pv_halves_graphic = [pv_mask(f"={PV_X0} + 26 * {PV_CW}", PV_T1 - 20, "=screen.width", 7 * PV_CH + 22),  # July, above
                     pv_mask(f"={PV_X0} + 27 * {PV_CW}", PV_T2 - 20, "=screen.width", 7 * PV_CH + 22),  # beyond December
                     pv_mask(0, PV_T2 - 20, PV_X0 - 1, 7 * PV_CH + 22),  # the first half, below
                     *[{"type": "text", "z": 101, "silent": True,
                        "style": {"text": d, "x": PV_X0 - 5, "y": PV_T2 + (i + 0.5) * PV_CH, "textAlign": "right",
                                  "textVerticalAlign": "middle", "fontSize": 12,
                                  "fill": "=themeOptions.dark === 'dark' ? '#aaa' : '#000'"}}
                       for i, d in enumerate(PV_DAYS)]]
pv_halves = chart({"chartType": "year", "periodVisible": True, "height": "318px", "visible": pv_shows("halves", "narrow"),
                   "options": {"graphic": pv_halves_graphic}},
                  calendar=[pv_half(PV_T1, PV_X0), pv_half(PV_T2, f"={PV_X0} - 26 * {PV_CW}")],
                  series=[comp("oh-calendar-series", {"name": "PV Production", "type": "heatmap", "calendarIndex": i,
                                                      "item": "energy_daily_pv", "aggregationFunction": "last"})
                          for i in (0, 1)],
                  visualMap=[comp("oh-chart-visualmap", {"show": True, "min": 0, "max": 60, "type": "continuous",
                                                         "calculable": True, "orient": "horizontal", "left": PV_X0,
                                                         "top": "8", "itemWidth": 10, "itemHeight": 110,
                                                         "inRange": {"color": PV_SCALE}})],
                  tooltip=tooltip())


def pv_hidden_calendar():
    """The calendar a custom series draws on: MainUI sets its range to the selected year, the series takes the year
    from it; the calendar itself stays unseen."""
    return comp("oh-calendar-axis", {"orient": "horizontal", "cellSize": ["auto", "auto"], "top": "75", "bottom": "10",
                                     "left": "40", "right": "20", "dayLabel": {"firstDay": 1, "show": False},
                                     "yearLabel": {"show": False}, "monthLabel": {"show": False},
                                     "splitLine": {"show": False}, "itemStyle": {"opacity": 0}})


def pv_custom_days(render):
    """The days' yields as a custom series on the hidden calendar, drawn by render."""
    return comp("oh-calendar-series", {"name": "PV Production", "calendarIndex": 0, "type": "custom",
                                       "renderItem": render, "item": "energy_daily_pv", "aggregationFunction": "last"})


def pv_short_scale():
    """A short scale at the top left, without handles, clear of the year's buttons down to 360 px; its ends name the
    scale's values."""
    return comp("oh-chart-visualmap", {"show": True, "min": 0, "max": 60, "type": "continuous", "calculable": False,
                                       "orient": "horizontal", "left": 4, "top": "22", "itemWidth": 10,
                                       "itemHeight": 60, "text": ["60 kWh", "0"], "inRange": {"color": PV_SCALE}})


# Monate: twelve wall calendars in square cells, three a row on a phone; where the chart is 600 px wide or more six or
# four a row, whichever gives the larger cells in its width and height. MainUI forces the selected year onto every
# oh-calendar-axis, so the calendar series is a custom series here that lays the months out itself, the year taken
# from the calendar's range, so the year navigation keeps working; the calendar itself stays, unseen, for its
# coordinate system. The first day also draws the frame: every month's name and empty cells, and the weekdays'
# initials over the first row
PV_MONTH_NAMES = "['Jänner', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', " \
                 "'November', 'Dezember']"


def pv_wall_calendar():
    """renderItem of the custom series: (params, api) => the day's cell, with the frame on the first day."""
    fg = "(themeOptions.dark === 'dark' ? '#bdbdbd' : '#616161')"
    empty = "(themeOptions.dark === 'dark' ? '#2b2b2b' : '#eeeeee')"
    # (the day and month lists are written without spaces: the generator's guard against hard-coded ventilation levels
    # looks for "1, 2, 3")
    # c6, c4: the cell's pitch with six or four months a row, n months of seven cells and gaps of 10 across and the
    # rows of months in the chart's height; n: three on a phone (where the height follows from the pitch), else the
    # one with the larger cells; x0 centres the months; rows of months 16 (the name) + six weeks + 12 apart, from 80
    # down: the colour scale and the year's buttons above, then the weekdays
    at = ("((W, H, y) => ((c6, c4) => ((n) => ((c) => ((x0) => ((bx, by, off) => {body})"
          "((m) => x0 + (m % n) * (7 * c + 10), (m) => 80 + Math.floor(m / n) * (16 + 6 * c + 12),"
          " (m) => (dayjs().date(1).year(y).month(m).day() + 6) % 7))"
          "((W - n * 7 * c - (n - 1) * 10) / 2))"
          "(Math.floor(n === 3 ? Math.min((W - 32) / 21, (H - 196) / 24) : n === 6 ? c6 : c4)))"
          "(W < 600 ? 3 : c6 >= c4 ? 6 : 4))"
          "(Math.min((W - 82) / 42, (H - 136) / 12), Math.min((W - 62) / 28, (H - 164) / 18)))"
          "(api.getWidth(), api.getHeight(), params.coordSys.rangeInfo.start.y)")
    cell = ("({{type: 'rect', silent: {silent}, shape: {{x: bx({m}) + ({i}) % 7 * c + 1, "
            "y: by({m}) + 16 + Math.floor(({i}) / 7) * c + 1, width: c - 2, height: c - 2, r: 2}}, "
            "style: {{fill: {fill}}}}})")
    day = cell.format(silent="false", m="dayjs(api.value(0)).month()",
                      i="off(dayjs(api.value(0)).month()) + dayjs(api.value(0)).date() - 1", fill="api.visual('color')")
    month = ("({{type: 'group', silent: true, children: [{{type: 'text', silent: true, style: {{x: bx(m), y: by(m), "
             "text: {names}[m], fontSize: 11, fontWeight: 600, fill: {fg}}}}}].concat("
             "[{days}].slice(0, dayjs().date(1).year(y).month(m).daysInMonth()).map((i) => {cell}))}})").format(
        names=PV_MONTH_NAMES, fg=fg, days=",".join(str(i) for i in range(31)),
        cell=cell.format(silent="true", m="m", i="off(m) + i", fill=empty))
    weekdays = ("[0,1,2,3,4,5].slice(0, n).map((m) => ['M', 'D', 'M', 'D', 'F', 'S', 'S'].map((w, k) => ({{type: 'text', silent: true, "
                "style: {{x: bx(m) + k * c + c / 2, y: 64, text: w, fontSize: 9, fill: {fg}, align: 'center'}}}})))"
                ".reduce((a, b) => a.concat(b), [])").format(fg=fg)
    frame = ("({{type: 'group', silent: true, children: [{months}].map((m) => {month}).concat({weekdays})}})").format(
        months=",".join(str(m) for m in range(12)), month=month, weekdays=weekdays)
    body = f"params.dataIndex === 0 ? ({{type: 'group', children: [{frame}, {day}]}}) : {day}"
    return "=(params, api) => " + at.format(body=body)


# on a phone the chart is the screen less 28 px wide, so its cells and height follow from the screen's width; on a
# wider screen the months fit 420 px, two rows of six or three of four
PV_WALL_HEIGHT = f"={NARROW} ? (84 + 4 * (28 + 6 * Math.floor((screen.width - 60) / 21))) + 'px' : '420px'"
pv_wall = chart({"chartType": "year", "periodVisible": True, "height": PV_WALL_HEIGHT, "visible": pv_shows("months")},
                calendar=[pv_hidden_calendar()], series=[pv_custom_days(pv_wall_calendar())],
                visualMap=[pv_short_scale()], tooltip=tooltip())

# Balken: the months as bars, the sum of their days' yields; the average per day, of the days with a value so far,
# only in the tooltip, as a second line would just redraw the bars' shape
PV_MONTHS_SHORT = "['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']"
PV_MONTHS = ["Jänner", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November",
             "Dezember"]
# the month's sum whole, the average per day to a tenth
PV_MONTH_VALUE = ("=(v) => v == null ? '–' : Number(v).toLocaleString('de-AT', {minimumFractionDigits: Number(v) >= 100 ? 0 "
                  ": 1, maximumFractionDigits: Number(v) >= 100 ? 0 : 1}) + ' kWh'")
pv_months = chart({"chartType": "year", "periodVisible": True, "height": "250px", "visible": pv_shows("bars")},
                  grid=[comp("oh-chart-grid", {"top": "62", "bottom": "28", "left": "45", "right": "12"})],
                  # the months as the axis' own values: the tooltip names the month in full, the axis shortly
                  xAxis=[comp("oh-category-axis", {"gridIndex": 0, "categoryType": "values", "data": PV_MONTHS,
                                                   "name": " ", "axisTick": {"show": False},
                                                   "axisLabel": {"interval": 0, "fontSize": f"={NARROW} ? 10 : 12",
                                                                 "formatter": f"=(v, i) => {PV_MONTHS_SHORT}[i]"}})],
                  yAxis=[comp("oh-value-axis", {"gridIndex": 0, "name": "kWh", "nameGap": 14, "nameTextStyle": AXIS_NAME,
                                                "axisLabel": {"formatter": "=(v) => v.toLocaleString('de-AT')"},
                                                "splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.4}}}),
                         comp("oh-value-axis", {"gridIndex": 0, "show": False})],
                  series=[comp("oh-aggregate-series", {"name": "PV Production", "gridIndex": 0, "xAxisIndex": 0,
                                                       "yAxisIndex": 0, "type": "bar", "item": "energy_daily_pv",
                                                       "aggregationFunction": "sum", "dimension1": "month",
                                                       "itemStyle": {"color": "#ffb300", "borderRadius": [4, 4, 0, 0]}}),
                          comp("oh-aggregate-series", {"name": "Average per Day", "gridIndex": 0, "xAxisIndex": 0,
                                                       "yAxisIndex": 1, "type": "line", "item": "energy_daily_pv",
                                                       "aggregationFunction": "average", "dimension1": "month",
                                                       "symbol": "none", "lineStyle": {"opacity": 0},
                                                       "itemStyle": {"color": "#e65100"}})],
                  # MainUI's smart formatter, on unless switched off, would override valueFormatter
                  tooltip=tooltip(trigger="axis", smartFormatter=False, valueFormatter=PV_MONTH_VALUE))


def pv_view_bar():
    """The bar that switches the views, in the look of the Smart Grid states (widget state-bar, sized by its texts) in
    the PV colour; state-bar sends an item command, this one sets the card's variable pvView. Jahr only on a wider
    screen, where the bar stays at most 440 px wide, Halbjahre only on a phone."""
    active = f"{PV_VIEW} === '{{}}'"
    buttons = [comp("oh-button", {"text": text, "action": "variable", "actionVariable": "pvView",
                                  "actionVariableValue": view, "small": True, "active": f"={active.format(view)}",
                                  **({"visible": f"=!({NARROW})"} if view == "year" else
                                     {"visible": f"={NARROW}"} if view == "halves" else {}),
                                  "style": {"font-size": "12px", "flex": "1 1 auto", "width": "auto", "padding": "0 6px",
                                            "background-color": f"=({active.format(view)}) ? '{PV_C}' : ''",
                                            "color": f"=({active.format(view)}) ? '#ffffff' : ''"}})
               for view, text in PV_VIEWS]
    bar = comp("f7-segmented", {"strong": True, "stylesheet": BY_TEXT_BAR,
                                "style": {"width": "100%", "max-width": f"={NARROW} ? 'none' : '440px'"}},
               default=buttons)
    return div([bar], **{"padding": "4px 12px 0"})


def pv_days():
    """The card's content: the bar and the chosen view; the variable lives in an oh-context, so it passes into the
    widget's parts, and starts empty, so each width shows its own default (PV_VIEW)."""
    return comp("oh-context", {"variables": {"pvView": ""}},
                default=[pv_view_bar(), calendar, pv_halves, pv_wall, pv_months])

# ---------------------------------------------------------------- 8. temperatures, storage, appliances


def gradient(rgb):
    return {"type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
            "colorStops": [{"offset": 0, "color": f"rgba({rgb}, 0.45)"}, {"offset": 1, "color": f"rgba({rgb}, 0.02)"}]}


def temp_stat(title, item, color, sub):
    return div([label(title, **{"font-size": "13px", "opacity": "0.7"}),
                label(f"={disp(item)}", **{"font-size": "30px", "font-weight": "700", "line-height": "36px"}),
                label(sub, **{"font-size": "12px", "opacity": "0.6"})],
               **{"border-left": f"4px solid {color}", "padding": "4px 12px"})


INDOOR, OUTDOOR = "espaltherma_indoor_ambient_temp", "espaltherma_ext_ambient_temp"
def marks(color):
    """Outlined dots at the day's minimum and maximum, the value as a badge above (max) or below (min) the line."""
    return {"data": [{"type": "max", "name": "max"}, {"type": "min", "name": "min", "label": {"position": "bottom"}}],
            "symbol": "circle", "symbolSize": 12, "itemStyle": {"color": color, "borderColor": "#ffffff",
                                                                 "borderWidth": 2.5},
            "label": {"show": True, "position": "top", "distance": 10, "formatter": "{c} °C",
                      "fontSize": 14, "fontWeight": 700, "color": "#ffffff", "backgroundColor": color,
                      "padding": [3, 7], "borderRadius": 6}}
temps = [
    div([temp_stat("Indoor", INDOOR, "#fb8c00", "Heatpump sensor"),
         temp_stat("Outdoor", OUTDOOR, "#29b6f6", "Heatpump sensor")],
        **{"display": "grid", "grid-template-columns": "1fr 1fr", "gap": "12px", "padding": "4px 16px 0"}),
    chart({"period": "D", "height": "320px"},
          grid=[comp("oh-chart-grid", {"top": "40", "bottom": "40", "left": "40", "right": "15"})],
          xAxis=[comp("oh-time-axis", {"gridIndex": 0})],
          yAxis=[comp("oh-value-axis", {"gridIndex": 0, "name": "°C", "scale": True, "nameGap": 14, "nameTextStyle": AXIS_NAME,
                                        "splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.4}}})],
          series=[time_series("Indoor", "temperature_indoor_15min", smooth=0.5,
                              lineStyle={"width": 2.5, "color": "#fb8c00"}, itemStyle={"color": "#fb8c00"},
                              markPoint=marks("#fb8c00")),
                  time_series("Outdoor", "temperature_outdoor_15min", smooth=0.5,
                              lineStyle={"width": 2.5, "color": "#29b6f6"}, itemStyle={"color": "#29b6f6"},
                              areaStyle={"color": gradient("41, 182, 246")}, markPoint=marks("#29b6f6"))],
          tooltip=tooltip(trigger="axis", smartFormatter=True), legend=legend()),
]

def ok(item):
    return f"(items.{item}.state !== 'UNDEF' && items.{item}.state !== 'NULL')"


def machine_body(front):
    """Common appliance housing inside the ring: body, control panel line, knob, plus the front drawing."""
    return [svg("rect", x=20, y=15, width=24, height=34, rx=3, **stroke(1.6)),
            svg("line", x1=20, y1=21, x2=44, y2=21, **stroke(1.2)),
            svg("circle", cx=39, cy=18, r=1.3, fill="currentColor"),
            *front]


def washer_front(running, water="#42a5f5"):
    """Door with a drum whose laundry turns while the machine runs."""
    drum = [svg("path", d="M26.5,35 a5.5,5.5 0 0 1 11,0", fill=water, **{"fill-opacity": "0.55"}),
            svg("circle", cx=29, cy=37.5, r=1.6, fill=water),
            svg("circle", cx=35, cy=38.5, r=1.2, fill=water),
            spin(32, 35, "1.1s", running)]
    return [svg("circle", cx=32, cy=35, r=9, **stroke(1.6)),
            svg("circle", cx=32, cy=35, r=6.5, **stroke(0.8, "#90a4ae")),
            svg("g", drum)]


def dryer_front(running):
    """Door with a drum whose paddles turn while the dryer runs, plus a lint filter slot."""
    paddles = [svg("line", x1=32, y1=29.5, x2=32, y2=33, transform=f"rotate({a} 32 35)", **stroke(1.6, "#ffb74d"))
               for a in (0, 120, 240)]
    paddles.append(spin(32, 35, "1.8s", running))
    return [svg("circle", cx=32, cy=35, r=9, **stroke(1.6)),
            svg("circle", cx=32, cy=35, r=6.5, **{"fill-opacity": "0.15"}, **stroke(0.8, "#90a4ae", fill="#ffb74d")),
            svg("g", paddles),
            svg("line", x1=27, y1=46, x2=37, y2=46, **stroke(1.2, opacity="0.7"))]


def dishwasher_front(running):
    """Translucent front through which the spray arm turns and droplets rise while it runs."""
    arm = [svg("line", x1=24.5, y1=38, x2=39.5, y2=38, **stroke(2, "#4fc3f7")),
           svg("circle", cx=32, cy=38, r=1.4, fill="#4fc3f7"),
           spin(32, 38, "1.4s", running)]
    drops = [svg("circle", [svg("animate", attributeName="cy", values="37;29;37", dur=f"{1 + i * 0.3:.1f}s",
                                 repeatCount="indefinite", visible=f"={running}")],
                 cx=x, cy=35, r=0.9, fill="#4fc3f7", visible=f"={running}") for i, x in enumerate((27, 32, 37))]
    return [svg("line", x1=27, y1=24.5, x2=37, y2=24.5, **stroke(1.6)),
            svg("rect", x=22.5, y=27, width=19, height=19, rx=2, **{"fill-opacity": "0.12"},
                **stroke(1, "#90a4ae", fill="#4fc3f7")),
            svg("g", arm), *drops]


def appliance_icon_widget():
    """The widget every appliance icon is an instance of: a washer, dryer or dishwasher (kind: washer, dryer,
    dish-washer) drawn inside a ring, its drum, paddles or spray arm turning while running holds; the ring fills with
    progress (0 to 100) while it runs and pulses in the rest of it, as the energy flow's rings beside an arc do (the
    arc, as wide and in the same colour, covers the pulsing ring under it), or pulses as a whole when there is no
    progress."""
    running = "!!props.running"
    has_progress = "(props.progress !== undefined && props.progress !== null && props.progress !== '')"
    ring_ = round(2 * math.pi * 28, 2)
    track = svg("circle", cx=32, cy=32, r=28, **stroke(4, "#9e9e9e", **{"stroke-opacity": "0.25"}))
    arc = svg("circle", cx=32, cy=32, r=28, transform="rotate(-90 32 32)", visible=f"={running} && {has_progress}",
              **stroke(4, "=props.color || '#1e88e5'",
                       **{"stroke-dasharray": f"=({ring_} * Number(props.progress) / 100).toFixed(1) + ' {ring_}'"}))
    # beside the progress arc as weak as the energy flow's pulse, alone as strong as before
    pulse = svg("circle", [svg("animate", attributeName="opacity", dur="2s", repeatCount="indefinite",
                               values=f"={has_progress} ? '{PULSE['values']}' : '{PULSE_FULL['values']}'",
                               visible=f"={running}")],
                cx=32, cy=32, r=28, visible=f"={running}", **stroke(4, "=props.color || '#1e88e5'"))
    fronts = [svg("g", front(running), visible=f"=props.kind === '{kind}'") for kind, front in APPLIANCE_FRONTS]
    return svg("svg", [track, pulse, arc, *machine_body(fronts)], viewBox="0 0 64 64", width="=props.size || 72",
               height="=props.size || 72")


def appliance_icon(front_kind, running, progress=None, size=72):
    cfg = {"kind": front_kind, "running": f"={running}", "size": size}
    if progress:
        cfg["progress"] = f"={num(progress)}"
    return comp("widget:appliance-icon", cfg)


def chip(text, color):
    return comp("Label", {"text": text, "style": {"background": color, "color": "#ffffff", "border-radius": "10px",
                                                  "padding": "2px 10px", "font-size": "12px", "font-weight": "600",
                                                  "white-space": "nowrap"}})


def duration(item, secs=None):
    """Seconds, an item's or an expression's, as '1:05 h', or '35 min' below an hour."""
    secs = secs or num(item)
    return (f"({secs} >= 3600 ? Math.floor({secs} / 3600) + ':' + ('0' + Math.floor({secs} % 3600 / 60)).slice(-2) + ' h'"
            f" : Math.ceil({secs} / 60) + ' min')")


def timer_chip(text, visible):
    """Small tinted pill with a timer icon and a remaining time."""
    color = "=themeOptions.dark === 'dark' ? '#64b5f6' : '#1565c0'"
    return div([comp("f7-icon", {"f7": "timer", "size": 13}), label(text)], visible=visible,
               **{"display": "inline-flex", "align-items": "center", "gap": "4px", "color": color,
                  "background": "rgba(30, 136, 229, 0.16)", "border-radius": "10px", "padding": "2px 8px",
                  "font-size": "12px", "font-weight": "600", "white-space": "nowrap"})


def remaining_chip(p, running):
    """The program's remaining time as a timer chip."""
    return timer_chip(f"={duration(p + '_program_remaining_time')}",
                      f"={running} && {ok(p + '_program_remaining_time')}")


def chips(*children):
    return div(list(children), **{"display": "flex", "flex-wrap": "wrap", "justify-content": "center", "gap": "6px"})


TILE_LINK = {"position": "absolute", "inset": "0", "display": "block", "border-radius": "12px"}


def tile(children, popup, link=None):
    """Appliance tile; a transparent link over it opens the appliance's page as a popup (popup may be an
    expression), or link is laid over it instead."""
    modal = f"='page:' + {popup[1:]}" if popup and popup.startswith("=") else f"page:{popup}"
    link = link or comp("oh-link", {"action": "popup", "actionModal": modal, "style": TILE_LINK})
    return div([*children, link], **{"position": "relative", "display": "flex", "flex-direction": "column",
                                     "align-items": "center", "justify-content": "center", "gap": "6px",
                                     "padding": "12px 8px",
                                     "border-radius": "12px", "text-align": "center",
                                     "background": "rgba(127, 127, 127, 0.08)"})


APPLIANCE_FRONTS = [("washer", washer_front), ("dryer", dryer_front), ("dish-washer", dishwasher_front)]
APPLIANCES = [
    # the device page a tap opens as a popup, title, front drawing, Miele item prefix (None: plug only), plug prefix
    ("washing_machine_1", "Washing Machine 1", washer_front, "miele_washing_machine_wwg360", "washing_machine_1"),
    ("washing_machine_2", "Washing Machine 2", washer_front, None, "washing_machine_2"),
    ("tumble_dryer", "Tumble Dryer", dryer_front, "miele_tumble_dryer_twc560wp", "tumble_dryer"),
    ("dishwasher", "Dishwasher", dishwasher_front, "miele_dishwasher_g7465", "dishwasher"),
]


def miele_state(p):
    """Running flag, chip colour, chip text and the program · phase · ready line of a Miele machine."""
    running = ok(f"{p}_program_progress")
    state = f"items.{p}_operation_state.state"
    finished = f"(('' + {state}).toLowerCase().indexOf('beendet') >= 0)"
    color = f"={running} ? '#1e88e5' : {finished} ? '#43a047' : '#9e9e9e'"
    status = f"={running} ? {disp(p + '_program_progress')} : {disp(p + '_operation_state')}"
    prog, phase = f"items.{p}_active_program.state", f"items.{p}_program_phase.state"
    details = (f"=({ok(p + '_active_program')} ? {prog} : '') + "
               f"({ok(p + '_active_program')} && {ok(p + '_program_phase')} ? ' · ' : '') + "
               f"({ok(p + '_program_phase')} ? {phase} : '') + "
               f"({ok(p + '_program_finished_time')} ? ' · fertig ' + dayjs(items.{p}_program_finished_time.state).format('HH:mm') : '')")
    return running, color, status, details


WM2_POWER = num("washing_machine_2_power")
WM2_RUNNING = f"{WM2_POWER} > 10"
WM2_FINISHED = "items.washing_machine_2_finished.state === 'ON'"
WM2_STATUS = (f"={WM2_RUNNING} ? 'läuft · ' + {disp('washing_machine_2_power')} : {WM2_FINISHED} ? 'fertig' : "
              f"{WM2_POWER} >= 1 ? 'An' : 'Aus'")
WM2_COLOR = f"={WM2_RUNNING} ? '#1e88e5' : {WM2_FINISHED} ? '#43a047' : '#9e9e9e'"


def appliance_tile_widget():
    """The widget every appliance tile is an instance of: the appliance's icon, its name and state, a tap opening its
    page as a popup. A Miele machine (progress given) shows program progress in the ring, its state as a chip in blue while
    it runs, green when it is finished, grey otherwise, the remaining time, and program, phase and end time while it
    runs; a machine behind a metered plug (power given) runs above 10 W, is finished when done is on, and pulses."""
    it = lambda key: f"items[props.{key}]"
    ok_ = lambda key: f"(!!props.{key} && {it(key)}.state !== 'UNDEF' && {it(key)}.state !== 'NULL')"
    shown = lambda key: (f"(['NULL', 'UNDEF'].includes({it(key)}.state) ? '–' : "
                         f"({it(key)}.displayState || {it(key)}.state))")
    miele = "!!props.progress"
    watts = f"(Number({it('power')}.numericState) || 0)"
    running = f"({miele} ? {ok_('progress')} : {watts} > 10)"
    finished = (f"({miele} ? (('' + {it('state')}.state).toLowerCase().indexOf('beendet') >= 0) : "
                f"(!!props.done && {it('done')}.state === 'ON'))")
    color = f"={running} ? '#1e88e5' : {finished} ? '#43a047' : '#9e9e9e'"
    status = (f"={miele} ? ({running} ? {shown('progress')} : {shown('state')}) : "
              f"({running} ? 'läuft · ' + {shown('power')} : {finished} ? 'fertig' : "
              f"{watts} >= 1 ? 'An' : 'Aus')")
    remaining = duration(None, f"(Number({it('remaining')}.numericState) || 0)")
    remaining_chip_ = timer_chip(f"={remaining}", f"={miele} && {running} && {ok_('remaining')}")
    details = (f"=({ok_('program')} ? {it('program')}.state : '') + "
               f"({ok_('program')} && {ok_('phase')} ? ' · ' : '') + ({ok_('phase')} ? {it('phase')}.state : '') + "
               f"({ok_('finished')} ? ' · fertig ' + dayjs({it('finished')}.state).format('HH:mm') : '')")
    icon = comp("widget:appliance-icon", {"kind": "=props.kind", "running": f"={running}",
                                          "progress": f"={miele} ? Number({it('progress')}.numericState) || 0 : ''"})
    state_chips = chips(chip(status, color), remaining_chip_)
    state_chips["config"]["visible"] = f"={miele}"
    plug_chip = chip(status, color)
    plug_chip["config"]["visible"] = f"=!{miele}"
    return tile([icon, label("=props.title", **{"font-weight": "600"}), state_chips, plug_chip,
                 comp("Label", {"text": details, "visible": f"={miele} && {running}",
                                "style": {"font-size": "12px", "opacity": "0.75"}})], "=props.popup")


APPLIANCE_TILE_ITEMS = {  # prop: the Miele item suffix, or the plug's
    "progress": "_program_progress", "state": "_operation_state", "program": "_active_program",
    "phase": "_program_phase", "finished": "_program_finished_time", "remaining": "_program_remaining_time"}
ITEM_PARAMS["appliance-tile"] = {*APPLIANCE_TILE_ITEMS, "power", "done"}


def appliance_tile(uid, title, front, p, plug):
    """An instance of the appliance tile widget: a Miele machine through its items, else the plug's power."""
    cfg = {"kind": front_kind(front), "title": title, "popup": uid}
    if p:
        cfg.update({key: p + suffix for key, suffix in APPLIANCE_TILE_ITEMS.items()})
    else:
        cfg.update({"power": plug + "_power", "done": plug + "_finished"})
    return comp("widget:appliance-tile", cfg)


def front_kind(front):
    return next(k for k, f in APPLIANCE_FRONTS if f is front)


def machine_icon(front, p, size=72):
    """An appliance icon: a Miele machine's with its program progress, else the plug machine's, pulsing."""
    if p:
        return appliance_icon(front_kind(front), miele_state(p)[0], f"{p}_program_progress", size)
    return appliance_icon(front_kind(front), WM2_RUNNING, size=size)


appliances = [div([appliance_tile(*a) for a in APPLIANCES],
                  **{"display": "grid", "grid-template-columns": "1fr 1fr", "grid-auto-rows": "1fr", "gap": "10px",
                     "padding": "12px 16px 16px", "flex": "1 1 auto"})]


# ---------------------------------------------------------------- 8a. hot water and heating, below the appliances

HEAT_ICON = 2 * HP_ORBIT + 8  # a drawing with its grey ring, one unit a pixel as in the heat pump card


def heat_icon(drawing, orbit, defs=None):
    """A device of the heat pump card as an icon: its drawing in its ring and the grey ring round it, filled and
    running as in the card."""
    h = HEAT_ICON / 2
    return svg("svg", [*([svg("defs", defs)] if defs else []), *orbit, *drawing], viewBox=f"{-h} {-h} {HEAT_ICON} {HEAT_ICON}",
               width=HEAT_ICON, height=HEAT_ICON, style={"display": "block", "overflow": "visible"})


def heat_tile(icon, title, on, color, value):
    """A tile like the appliances': the icon, the title and the temperature as a pill (user's variant E, 2026-10-03),
    filled in the tile's colour while switched on, only outlined in it while off. A tap opens the heat pump's quick
    panel, as in the energy flow."""
    temperature = label(value, **{"background": f"={on} ? '{color}' : 'transparent'",
                                  "color": f"={on} ? '#ffffff' : '{color}'", "border": f"1.5px solid {color}",
                                  "border-radius": "12px", "padding": "1px 11px", "font-size": "15px",
                                  "font-weight": "700", "white-space": "nowrap"})
    return tile([icon, label(title, **{"font-weight": "600"}), chips(temperature)], None,
                hp_popup_link(TILE_LINK, "heatpump-quick"))


def heat_specs():
    """What the heating card's two tiles show, as keyword arguments of a tile builder: the tank as in the heat pump
    card with the source of its heat as a badge, its grey ring filled by its temperature, and the tank's temperature;
    the heat pump as its node in the energy flow with the same badge, its grey ring filled by the compressor's
    frequency, and the leaving water; on is the switch for hot water and for heating."""
    tank = heat_icon([*tank_node(0, 0, "heatTank"), *tank_source_badge(0, 0)],
                     hp_orbit((0, 0), "#e57373", f"({TANK_FLOW} || {BSH_ON})",
                              f"{num(HPX['tank'])} / {TANK_FULL}"),
                     [tank_layers("heatTank")])
    pump = heat_icon([flow_node("heat-pump", (0, 0), num(HPX["power"]), frequency=num(HPX["hz"])),
                      *hp_mode_badges(0, 0)],
                     hp_orbit((0, 0), HP_ORANGE, COMPRESSOR, f"{num(HPX['hz'])} / {HZ_FULL}"))
    return [dict(icon=tank, title="Warmwasserspeicher", on="items.pyaltherma_dhw_power.state === 'ON'", color=DHW_C,
                 value=f"={disp(HPX['tank'])}"),
            dict(icon=pump, title="Heizung", on="items.pyaltherma_climate_control_power.state === 'ON'",
                 color=SPACE_C, value=f"={disp(HPX['supply'])}")]


def heating(tile=heat_tile):
    """The heating card's content: the tank and the heat pump as tiles (built by tile), today's split of electricity
    and heat, and the day's three COPs, two abreast over the total."""
    tiles = div([tile(**spec) for spec in heat_specs()],
                **{"display": "grid", "grid-template-columns": "1fr 1fr", "gap": "10px", "margin-bottom": "16px"})
    # space heating and DHW side by side, the total across the row below them (user, 2026-10-03); every ring as large
    # as Eigenverbrauch's and Autarkie's under the energy flow, which stand three abreast on a desktop and two on a
    # phone, so each drawing is as wide as in such a tile: from a tile of half the row (gap 8, paddings 2 x 10) on a
    # desktop 2/3 of its width less 9.3 px, from the row-wide total 1/3 less 18.7 px; on a phone the halves' own
    # width, from the total half less 14 px
    half = f"={NARROW} ? '100%' : 'calc(66.7% - 9.3px)'"
    # a tap on any of them opens the COP popup, as the heat pump card's COP tile does
    pop = "heatpump-cop-quick"
    total = cop_tile("COP gesamt", "espaltherma_dcop", COP_C, "eco",
                     f"={NARROW} ? 'calc(50% - 14px)' : 'calc(33.3% - 18.7px)'", pop)
    total["config"]["style"]["grid-column"] = "1 / -1"
    cops = div([cop_tile("COP Heizung", "espaltherma_dcop_space", SPACE_C, "local_fire_department", half, pop),
                cop_tile("COP Warmwasser", "espaltherma_dcop_dhw", DHW_C, "shower", half, pop), total],
               **{"display": "grid", "gap": "8px", "grid-template-columns": "repeat(2, minmax(0, 1fr))"})
    content = div([tiles, *hp_day_split(), cops], **{"padding": "12px 16px 16px", "font-size": "14px"})
    return [content]

# ---------------------------------------------------------------- 8b. appliance pages


# ---- watermark icons of the value tiles

# The item types of the items the value tiles show, read from Item.json, the plug widgets' placeholder items
# (zzpfx_*) typed like a real plug's. A tile whose item is missing here gets its icon from the keywords alone.
TILE_ITEM_TYPES = {
    "DateTime": ("epex_spot_awattar_cheapest_hour epex_spot_awattar_priciest_hour huawei_inverter_shutdown_time "
                 "huawei_inverter_startup_time miele_dishwasher_g7465_delayed_start_time_absolute "
                 "miele_dishwasher_g7465_program_finished_time "
                 "miele_tumble_dryer_twc560wp_delayed_start_time_absolute "
                 "miele_tumble_dryer_twc560wp_program_finished_time "
                 "miele_washing_machine_wwg360_delayed_start_time_absolute "
                 "miele_washing_machine_wwg360_program_finished_time netatmo_outdoor_last_seen "
                 "netatmo_outdoor_measures_timestamp netatmo_weatherstation_last_seen "
                 "netatmo_weatherstation_measures_timestamp water_meter_timestamp"),
    "Dimensionless": ("espaltherma_water_pump_signal huawei_inverter_efficiency huawei_inverter_energy_storage_soc "
                      "huawei_inverter_energy_storage_unit_1_soc miele_dishwasher_g7465_program_progress "
                      "miele_tumble_dryer_twc560wp_program_progress miele_washing_machine_wwg360_program_progress "
                      "netatmo_outdoor_atmospheric_humidity netatmo_outdoor_battery_level "
                      "netatmo_weatherstation_atmospheric_humidity netatmo_weatherstation_co2"),
    "ElectricCurrent": ("e_car_current espaltherma_inv_primary_current huawei_inverter_energy_storage_bus_current "
                        "huawei_inverter_energy_storage_unit_1_bus_current smartpi_i4 zzpfx_current"),
    "ElectricPotential": ("e_car_voltage huawei_inverter_energy_storage_bus_voltage "
                          "huawei_inverter_energy_storage_unit_1_bus_voltage zzpfx_voltage"),
    "Energy": ("dishwasher_energy_today dishwasher_energy_total e_car_energy_today e_car_energy_total "
               "espaltherma_energy_dhw_today espaltherma_energy_space_today espaltherma_energy_standby_today "
               "espaltherma_energy_today espaltherma_heating_energy_dhw_today espaltherma_heating_energy_space_today "
               "espaltherma_heating_energy_today home_ec_day huawei_inverter_e_day huawei_inverter_e_total "
               "huawei_inverter_energy_storage_day_charge huawei_inverter_energy_storage_day_discharge "
               "huawei_inverter_energy_storage_total_charge huawei_inverter_energy_storage_total_discharge "
               "huawei_inverter_energy_storage_unit_1_day_charge huawei_inverter_energy_storage_unit_1_day_discharge "
               "huawei_inverter_energy_storage_unit_1_total_charge "
               "huawei_inverter_energy_storage_unit_1_total_discharge huawei_inverter_power_meter_ec_day "
               "huawei_inverter_power_meter_ep_day miele_dishwasher_g7465_current_energy_consumption "
               "miele_tumble_dryer_twc560wp_current_energy_consumption "
               "miele_washing_machine_wwg360_current_energy_consumption photovoltaics_own_ec_day smartpi_ecday "
               "smartpi_epday tumble_dryer_energy_today tumble_dryer_energy_total washing_machine_1_energy_today "
               "washing_machine_1_energy_total washing_machine_2_energy_today washing_machine_2_energy_total "
               "zzpfx_energy_today zzpfx_energy_total"),
    "EnergyPrice": ("epex_spot_awattar epex_spot_awattar_cheapest epex_spot_awattar_market_gross "
                    "epex_spot_awattar_priciest epex_spot_awattar_total_gross epex_spot_awattar_total_net"),
    "Frequency": ("espaltherma_inv_frequency faikout_perfera_compressor_frequency faikout_perfera_fan_speed "
                  "huawei_inverter_power_meter_frequency miele_washing_machine_wwg360_spinning_speed"),
    "Number": ("espaltherma_cop espaltherma_cop_dhw espaltherma_cop_space espaltherma_dcop espaltherma_dcop_dhw "
               "espaltherma_dcop_space huawei_inverter_device_status huawei_inverter_energy_storage_forcible_status "
               "huawei_inverter_energy_storage_running_status huawei_inverter_energy_storage_unit_1_running_status "
               "huawei_inverter_error_code huawei_inverter_optimizers_online huawei_inverter_optimizers_total "
               "huawei_inverter_power_meter_power_factor miele_dishwasher_g7465_program_elapsed_time "
               "miele_dishwasher_g7465_program_remaining_time miele_tumble_dryer_twc560wp_program_elapsed_time "
               "miele_tumble_dryer_twc560wp_program_remaining_time miele_washing_machine_wwg360_program_elapsed_time "
               "miele_washing_machine_wwg360_program_remaining_time netatmo_outdoor_signal_strength "
               "netatmo_weatherstation_noise netatmo_weatherstation_signal_strength zzpfx_power_factor"),
    "Power": ("air_conditioning_unit_power dishwasher_power e_car_power espaltherma_electrical_power heatpump_power "
              "espaltherma_electrical_power_dhw espaltherma_electrical_power_space "
              "espaltherma_electrical_power_standby espaltherma_heating_power espaltherma_heating_power_after_buh "
              "espaltherma_heating_power_before_buh espaltherma_heating_power_dhw espaltherma_heating_power_space "
              "faikout_perfera_power home_active_power huawei_inverter_active_peak_of_current_day "
              "huawei_inverter_active_power huawei_inverter_energy_storage_power "
              "huawei_inverter_energy_storage_unit_1_power huawei_inverter_input_power "
              "huawei_inverter_power_meter_active_power huawei_inverter_power_meter_phase_a_active_power "
              "huawei_inverter_power_meter_phase_b_active_power huawei_inverter_power_meter_phase_c_active_power "
              "huawei_inverter_power_meter_reactive_power huawei_inverter_pv1_power huawei_inverter_pv2_power "
              "huawei_inverter_reactive_power netatmo_outdoor_signal netatmo_weatherstation_signal tumble_dryer_power "
              "washing_machine_1_power washing_machine_2_power zzpfx_apparent_power zzpfx_reactive_power"),
    "Pressure": ("espaltherma_refrigerant_pressure_sensor espaltherma_water_pressure "
                 "netatmo_weatherstation_absolute_pressure netatmo_weatherstation_barometric_pressure"),
    "String": ("espaltherma_3way_valve_mode espaltherma_error_code espaltherma_i_u_operation_mode "
               "espaltherma_operation_mode miele_dishwasher_g7465_active_program "
               "miele_dishwasher_g7465_operation_state miele_dishwasher_g7465_power_state "
               "miele_dishwasher_g7465_program_phase miele_tumble_dryer_twc560wp_active_program "
               "miele_tumble_dryer_twc560wp_drying_target miele_tumble_dryer_twc560wp_operation_state "
               "miele_tumble_dryer_twc560wp_power_state miele_tumble_dryer_twc560wp_program_phase "
               "miele_washing_machine_wwg360_active_program miele_washing_machine_wwg360_operation_state "
               "miele_washing_machine_wwg360_power_state miele_washing_machine_wwg360_program_phase vuuno4k_channel "
               "vuuno4k_description vuuno4k_title water_meter_error water_meter_status"),
    "Switch": ("espaltherma_bsh_mode espaltherma_buh_step1_mode espaltherma_defrost_operaton "
               "espaltherma_powerful_dhw_operation espaltherma_reheat espaltherma_space_heating_operation "
               "espaltherma_storage_eco_mode espaltherma_water_pump_operation"),
    "Temperature": ("espaltherma_dhw_setpoint espaltherma_dhw_tank_temp espaltherma_discharge_pipe_temp "
                    "espaltherma_ext_ambient_temp espaltherma_heat_exchanger_mid_temp espaltherma_indoor_ambient_temp "
                    "espaltherma_inlet_water_temp espaltherma_leaving_water_setpoint "
                    "espaltherma_leaving_water_setpoint_add espaltherma_leaving_water_temp_after_buh "
                    "espaltherma_leaving_water_temp_before_buh espaltherma_outdoor_air_temp "
                    "espaltherma_pressure_sensor_temp espaltherma_refrig_temp_liquid_side "
                    "espaltherma_room_temp_setpoint espaltherma_target_delta_t_heating "
                    "espaltherma_target_discharge_temp faikout_perfera_liquid_temperature "
                    "faikout_perfera_outdoor_temperature faikout_perfera_temperature "
                    "faikout_perfera_temperature_setpoint huawei_inverter_energy_storage_unit_1_temperature "
                    "huawei_inverter_internal_temperature miele_washing_machine_wwg360_target_temperature "
                    "netatmo_outdoor_dewpoint netatmo_outdoor_heat_index netatmo_outdoor_max_temp "
                    "netatmo_outdoor_min_temp netatmo_weatherstation_dewpoint netatmo_weatherstation_heat_index "
                    "netatmo_weatherstation_max_temp netatmo_weatherstation_min_temp"),
    "Volume": ("miele_dishwasher_g7465_current_water_consumption "
               "miele_washing_machine_wwg360_current_water_consumption water_meter_value"),
    "VolumetricFlowRate": ("espaltherma_flow_sensor water_meter_rate"),
}
ITEM_DIMENSION = {item: dim for dim, names in TILE_ITEM_TYPES.items() for item in names.split()}
TEMP_C, POWER_C, ENERGY_C, PV_C, BATTERY_C = "#ff7043", "#fb8c00", "#ffa726", "#ffb300", "#7cb342"
STATE_C, TIME_C, WATER_C, PRESSURE_C, GREEN, RED = "#78909c", "#7e57c2", "#42a5f5", "#5c6bc0", "#43a047", "#e53935"
# Every value tile carries a large pale icon; the first rule whose dimension (None: any) and keyword pattern (None:
# any) fit its item wins. The pattern is searched in the item name and the tile title, lower case; the colour
# serves tiles without one of their own.
TILE_ICONS = [
    (None, r"self-consumption|self-sufficiency", "pie_chart", GREEN),
    (None, r"d?cop(_|\b)", "eco", GREEN),
    (None, r"error", "report_problem", RED),
    (None, r"cheapest", "trending_down", GREEN),
    (None, r"priciest", "trending_up", RED),
    ("Temperature", r"leaving_water", "thermostat", SUPPLY),
    ("Temperature", r"inlet_water", "thermostat", RETURN),
    ("Temperature", r"dhw", "water_drop", "#ef5350"),
    ("Temperature", r"dewpoint", "grain", "#4fc3f7"),
    ("Temperature", r"outdoor|ext_ambient", "device_thermostat", "#26a69a"),
    ("Temperature", r"indoor_ambient|room_temp|perfera_temperature", "home", "#ff8a65"),
    ("Temperature", r"discharge|refrig|liquid|heat_exchanger|pressure_sensor", "thermostat", REFRIGERANT),
    ("Temperature", None, "thermostat", TEMP_C),
    ("Power", r"heating_power", "local_fire_department", RED),
    ("Power", r"reactive|apparent", "bolt", "#90a4ae"),
    ("Power", r"signal", "signal_cellular_alt", STATE_C),
    ("Power", r"pv\d|input_power|huawei_inverter_active", "solar_power", PV_C),
    ("Power", r"power_meter|smartpi", "electric_meter", POWER_C),
    ("Power", r"energy_storage", "battery_charging_full", BATTERY_C),
    ("Power", None, "bolt", POWER_C),
    ("Energy", r"heating_energy", "local_fire_department", RED),
    ("Energy", r"power_meter_ec|smartpi_ec", "download", RED),
    ("Energy", r"power_meter_ep|smartpi_ep", "upload", GREEN),
    ("Energy", r"own_ec", "solar_power", GREEN),
    ("Energy", r"inverter_e_", "solar_power", PV_C),
    ("Energy", r"discharge", "battery_full", BATTERY_C),
    ("Energy", r"charge", "battery_charging_full", BATTERY_C),
    ("Energy", r"home_ec", "home", "#1e88e5"),
    ("Energy", None, "offline_bolt", ENERGY_C),
    ("EnergyPrice", None, "euro", "#ffa000"),
    ("Pressure", r"refrigerant", "compress", REFRIGERANT),
    ("Pressure", None, "compress", PRESSURE_C),
    ("VolumetricFlowRate", None, "waves", WATER_C),
    ("Volume", None, "water", WATER_C),
    ("Frequency", r"fan_speed", "air", "#4dd0e1"),
    ("Frequency", r"spinning", "autorenew", TIME_C),
    ("Frequency", r"power_meter", "graphic_eq", TIME_C),
    ("Frequency", None, "speed", "#8d6e63"),
    ("ElectricCurrent", None, "cable", "#ffa000"),
    ("ElectricPotential", None, "power_input", "#ffa000"),
    (None, r"soc\b", "battery_5_bar", BATTERY_C),
    (None, r"battery_level", "battery_std", STATE_C),
    (None, r"humidity", "opacity", "#4fc3f7"),
    (None, r"co2", "co2", STATE_C),
    (None, r"noise", "volume_up", TIME_C),
    (None, r"progress", "donut_large", TIME_C),
    (None, r"efficiency", "insights", GREEN),
    (None, r"power_factor", "functions", "#90a4ae"),
    (None, r"water_pump|pump_operation", "sync", WATER_C),
    (None, r"signal", "signal_cellular_alt", STATE_C),
    (None, r"optimizers", "developer_board", STATE_C),
    (None, r"remaining_time", "hourglass_bottom", TIME_C),
    (None, r"elapsed_time", "timer", TIME_C),
    (None, r"finished_time", "event_available", GREEN),
    (None, r"delayed_start", "alarm", TIME_C),
    (None, r"startup_time", "wb_sunny", PV_C),
    (None, r"shutdown_time", "nights_stay", PRESSURE_C),
    (None, r"timestamp|last_seen", "schedule", STATE_C),
    (None, r"valve", "call_split", SPACE_C),
    (None, r"program_phase", "timelapse", TIME_C),
    (None, r"active_program", "list_alt", TIME_C),
    (None, r"drying_target", "dry", TIME_C),
    (None, r"power_state", "power_settings_new", STATE_C),
    (None, r"channel", "tv", STATE_C),
    (None, r"vuuno4k", "subtitles", STATE_C),
    (None, r"defrost", "ac_unit", "#4fc3f7"),
    (None, r"buh|bsh", "whatshot", "#ff8a65"),
    (None, r"powerful", "rocket_launch", "#ef5350"),
    (None, r"reheat", "replay", "#ef5350"),
    (None, r"space_heating", "heat_pump", SPACE_C),
    (None, r"storage_eco", "eco", GREEN),
    (None, r"status|state|operation", "info", STATE_C),
    ("Dimensionless", None, "percent", STATE_C),
    ("DateTime", None, "schedule", STATE_C),
    ("Switch", None, "toggle_on", STATE_C),
    ("Number", None, "numbers", STATE_C),
    (None, None, "info", STATE_C),
]
TILE_ICON_DEFAULTS = set()  # tiles left with the last rule, listed by the dry run


def tile_icon(title, value):
    """Icon and colour of a value tile's watermark: its item comes from the value expression, the rules pick them."""
    item = (re.findall(r"items\.(\w+)", value) or [""])[0]
    text, dim = f"{item} {title}".lower(), ITEM_DIMENSION.get(item)
    rule = next(r for r in TILE_ICONS if r[0] in (None, dim) and (r[1] is None or re.search(r[1], text)))
    if rule is TILE_ICONS[-1]:
        TILE_ICON_DEFAULTS.add(f"{title} [{item}]")
    return rule[2:]


def value_tile_widget():
    """The widget every value tile is an instance of: title and value over a large pale icon, a tap opening the item's
    popup where an item is given. Its lengths are em of its font size, 14 px unless fontSize sets another, so a tile
    in a card that grows grows with it; wrap lets a long text wrap across the whole row of the grid."""
    return div([
        # Framework7 sets the icon's font size, width and height from one value; in em of the tile that is right for
        # the font size (58 px at 14 px), but width and height are em of the icon's own font size, so the style
        # sets them to 1em, and the offsets, 6 and 10 of its 58 px, are em of that size too
        comp("oh-icon", {"icon": "=props.icon || 'material:info'", "width": "4.143em", "height": "4.143em", "style": {
            "width": "1em", "height": "1em", "position": "absolute", "right": "-0.1034em", "bottom": "-0.1724em",
            "opacity": "0.16", "color": "=props.iconColor || props.color || '#78909c'"}}),
        # the texts stand above the icon in their own positioned box, the link above both
        div([label("=props.title", **{"font-size": "0.8571em", "opacity": "0.65"}),
             label("=props.value", **{"font-size": "=props.wrap ? '1em' : '1.429em'",
                                      "font-weight": "=props.wrap ? 600 : 700",
                                      "line-height": "=props.wrap ? '1.357' : '1.3'",
                                      "white-space": "=props.wrap ? 'normal' : 'nowrap'",
                                      "overflow": "hidden", "text-overflow": "=props.wrap ? 'clip' : 'ellipsis'",
                                      "overflow-wrap": "anywhere", "color": "=props.color || ''"})],
            **{"position": "relative"}),
        comp("oh-link", {"visible": "=!!props.item", "action": "=props.action || 'popup'", "actionItem": "=props.item",
                         "actionModal": "widget:item-popup",
                         "actionModalConfig": {"item": "=props.item", "title": "=props.title",
                                               "color": f"=props.color || '{POPUP_COLOR}'",
                                               "kind": "=props.kind || 'number'", "states": "=props.states || ''"},
                         "style": {"position": "absolute", "inset": "0", "display": "block",
                                   "border-radius": "0.8571em"}})],
        **{"position": "relative", "overflow": "hidden", "box-sizing": "border-box", "height": "100%",
           "min-width": "0", "font-size": "=props.fontSize || '14px'", "padding": "0.7143em 0.8571em",
           "border-radius": "0.8571em", "grid-column": "=props.wrap ? '1 / -1' : 'auto'",
           "background": "rgba(127, 127, 127, 0.08)"})


def value_tile(title, value, visible=None, color=None):
    """An instance of the value tile widget; the rules pick its icon, and its colour where it has none of its own."""
    icon, fallback = tile_icon(title, value)
    cfg = {"title": title, "value": value, "icon": f"material:{icon}"}
    cfg.update({"color": color} if color else {"iconColor": fallback})
    if visible:
        cfg["visible"] = visible
    return comp("widget:value-tile", cfg)


def tile_grid(tiles, minw="140px"):
    return div(tiles, **{"display": "grid", "grid-template-columns": f"repeat(auto-fit, minmax({minw}, 1fr))",
                         "gap": "10px", "padding": "4px 16px 16px"})


def progress_bar(p):
    pct = num(f"{p}_program_progress")
    return div([
        div([div([], **{"width": f"=Math.min(100, {pct}) + '%'", "height": "100%", "background": "#42a5f5",
                        "border-radius": "4px"})],
            **{"height": "8px", "border-radius": "4px", "background": "rgba(127, 127, 127, 0.18)", "overflow": "hidden"}),
        div([label(f"={duration(p + '_program_elapsed_time')} + ' vergangen'"),
             label(f"={duration(p + '_program_remaining_time')} + ' übrig'")],
            **{"display": "flex", "justify-content": "space-between", "font-size": "12px", "opacity": "0.7",
               "margin-top": "4px"}),
    ], visible=f"={miele_state(p)[0]}", **{"padding": "0 16px 16px"})


def appliance_header(front, p):
    """The machine drawn large beside its state; while a Miele program runs also program, phase and ready time."""
    if p:
        running, color, status, details = miele_state(p)
        lines = [chips(chip(status, color), remaining_chip(p, running)),
                 comp("Label", {"text": details, "visible": f"={running}", "style": {"font-size": "14px"}}),
                 comp("Label", {"text": f"='fertig um ' + dayjs(items.{p}_program_finished_time.state).format('HH:mm')",
                                "visible": f"={running} && {ok(p + '_program_finished_time')}",
                                "style": {"font-size": "22px", "font-weight": "700"}})]
    else:
        lines = [chip(WM2_STATUS, WM2_COLOR)]
    return div([machine_icon(front, p, size=104),
                div(lines, **{"display": "flex", "flex-direction": "column", "align-items": "flex-start", "gap": "6px",
                              "min-width": "0"})],
               **{"display": "flex", "align-items": "center", "gap": "18px", "padding": "12px 16px 16px"})


# ---------------------------------------------------------------- 8c. energy flow popups


def rgb_of(hex_):
    return ", ".join(str(int(hex_[i:i + 2], 16)) for i in (1, 3, 5))


def area(name, item, color, y=0, **extra):
    return time_series(name, item, yAxisIndex=y, symbol="none", sampling="lttb",
                       lineStyle={"width": 1.5, "color": color}, itemStyle={"color": color},
                       areaStyle={"color": gradient(rgb_of(color))}, **extra)


def line(name, item, color, y=0, dashed=False, **extra):
    style = {"width": 1.5, "type": "dashed", "color": color} if dashed else {"width": 2, "color": color}
    return time_series(name, item, yAxisIndex=y, symbol="none", lineStyle=style, itemStyle={"color": color}, **extra)


def value_axis(name, **extra):
    return comp("oh-value-axis", {"gridIndex": 0, "name": name, "nameGap": 14, "nameTextStyle": AXIS_NAME,
                                  "splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.4}}, **extra})


def day_chart(series, axes=None, height="260px", **slots):
    """The last day with arrows for earlier days; a legend once there is more than one series. A second axis stands
    on the right, its name over its labels."""
    axes = axes or [value_axis("W")]
    axes = axes[:1] + [{**a, "config": {**a["config"], "nameTextStyle": RIGHT_AXIS_NAME}} for a in axes[1:]]
    extra = {"legend": legend()} if len(series) > 1 else {}
    return chart({"period": "D", "periodVisible": True, "height": height},
                 grid=[comp("oh-chart-grid", {"top": "35", "bottom": "60" if extra else "35", "left": "50",
                                              "right": "50" if len(axes) > 1 else "20"})],
                 xAxis=[comp("oh-time-axis", {"gridIndex": 0})], yAxis=axes, series=series,
                 tooltip=tooltip(trigger="axis", smartFormatter=True), **extra, **slots)


def scaled(factor, unit):
    """Axis labels and tooltip values of a series persisted in a larger unit, multiplied into the unit shown."""
    fmt = f"=(v) => Math.round(v * {factor}).toLocaleString('de-AT')"
    return {"axisLabel": {"formatter": fmt}}, tooltip(trigger="axis", valueFormatter=fmt + f" + ' {unit}'")


def month_bars(name, item, color, unit="kWh", factor=None):
    """The daily totals of a day counter over the current month; the arrows page through months."""
    axis, tip = scaled(factor, unit) if factor else ({}, tooltip(trigger="axis", smartFormatter=True))
    return chart({"chartType": "month", "periodVisible": True, "height": "260px"},
                 grid=[comp("oh-chart-grid", {"top": "40", "bottom": "35", "left": "45", "right": "45"})],
                 xAxis=[comp("oh-category-axis", {"gridIndex": 0, "categoryType": "month", "name": "Tag", "nameGap": 12,
                                                  "axisTick": {"show": False}})],
                 yAxis=[value_axis(unit, **axis)],
                 series=[comp("oh-aggregate-series", {"name": name, "gridIndex": 0, "xAxisIndex": 0, "yAxisIndex": 0,
                                                      "type": "bar", "item": item, "aggregationFunction": "last",
                                                      "dimension1": "date",
                                                      "itemStyle": {"color": color, "borderRadius": [4, 4, 0, 0]}})],
                 tooltip=tip)


def month_chart(series, unit, height="270px"):
    """Several day series over the current month with a legend; the arrows page through months."""
    return chart({"chartType": "month", "periodVisible": True, "height": height},
                 grid=[comp("oh-chart-grid", {"top": "40", "bottom": "60", "left": "45", "right": "45"})],
                 xAxis=[comp("oh-category-axis", {"gridIndex": 0, "categoryType": "month", "name": "Tag", "nameGap": 12,
                                                  "axisTick": {"show": False}})],
                 yAxis=[value_axis(unit)], series=series, legend=legend(),
                 tooltip=tooltip(trigger="axis", smartFormatter=True))


def plots_below_controls(tree):
    """The period buttons sit in the top right corner of a chart, 6 to 42 px from its top (PERIOD_MENU); with the
    plot starting below them they hide no data. A second axis names its unit at the plot's top right corner, 14 px
    above it, so with one the plot starts lower still. Returns a copy, as parts of a tree may be shared with the
    overview."""
    def lower(v):
        if isinstance(v, dict):
            if v.get("component") == "oh-chart" and v.get("config", {}).get("periodVisible"):
                named = [a for a in v.get("slots", {}).get("yAxis", []) if a["config"].get("name")]
                for g in v.get("slots", {}).get("grid", []):
                    g["config"]["top"] = "80" if len(named) > 1 else "62"
            for x in v.values():
                lower(x)
        elif isinstance(v, list):
            for x in v:
                lower(x)
        return v
    return lower(copy.deepcopy(tree))


def water_rate_chart():
    """The water meter's flow over the day, stored in m³/min and shown in l/min."""
    axis, tip = scaled(1000, "l/min")
    rate = day_chart([area("Durchfluss", "water_meter_rate", "#1e88e5")], [value_axis("l/min", **axis)])
    rate["slots"]["tooltip"] = tip
    return rate


def pct(part, whole):
    return f"=({num(whole)} > 0 ? Math.round(100 * {num(part)} / {num(whole)}) : 0) + ' %'"


def sign_colors():
    """Colours the first series by its sign: green below zero, red above. The pieces must be finite: with only
    open-ended ones ECharts has no colour stops for the line gradient and throws instead of drawing."""
    return [comp("oh-chart-visualmap", {"show": False, "type": "piecewise", "dimension": 1, "seriesIndex": 0,
                                        "pieces": [{"min": -100000, "max": 0, "color": "#43a047"},
                                                   {"min": 0, "max": 100000, "color": "#e53935"}]})]


def controls_box(*rows):
    return div(list(rows), **{"padding": "4px 16px 12px"})


HOME_BLUE = "#1e88e5"


def split_now(title, parts):
    """Power split by where it comes from or goes to now, each part with its share, as a split bar over tiles; parts:
    (title, watts, colour, icon)."""
    whole = "Math.max(1, " + " + ".join(v for _, v, _, _ in parts) + ")"
    share_ = lambda v: f"Math.round(100 * {v} / {whole})"
    bar = div([div([], visible=f"={v} > 5", **{"width": f"=(100 * {v} / {whole}).toFixed(2) + '%'", "height": "100%",
                                               "background": c, "border-radius": "4px"})
               for _, v, c, _ in parts], **{"display": "flex", "gap": "2px", "height": "10px", "margin": "0 16px 10px"})
    tiles = []
    for t, v, c, icon in parts:
        tile = value_tile(f"='{t} · ' + {share_(v)} + ' %'", f"={fixed(f'{v} / 1000', 3)} + ' kW'", color=c)
        tile["config"]["icon"] = f"material:{icon}"  # the title's share names other items, which would mislead the rules
        tiles.append(tile)
    return [label(title, **{"font-size": "13px", "opacity": "0.7", "padding": "4px 16px 6px"}), bar, wide_grid(tiles)]


GRID_IN, GRID_OUT = f"Math.max(0, {num(GRID)})", f"Math.max(0, -{num(GRID)})"
BATT_OUT, BATT_IN = f"Math.max(0, {num(BATT)})", f"Math.max(0, -{num(BATT)})"
# PV's part of the house's power: what the grid's import and the battery's discharge leave, at most PV's power
PV_HOUSE = f"Math.max(0, Math.min({num(PV)}, {num(HOME)} - {GRID_IN} - {BATT_OUT}))"


def home_sources():
    """Where the house's power comes from now: from PV directly, from the battery and from the grid. The grid counts
    only while it imports, the battery only while it discharges; PV covers the rest, at most its own power."""
    return split_now("Woher der Strom jetzt kommt", [
        ("aus PV", PV_HOUSE, "#ffb300", "solar_power"), ("aus der Batterie", BATT_OUT, BATTERY_GREEN, "battery_full"),
        ("aus dem Netz", GRID_IN, "#e53935", "electric_meter")])


# where PV's power goes, in this order and never more than it is: into the house, into the battery while it charges,
# into the grid while it exports (an export beyond it comes from the battery)
PV_BATT = f"Math.max(0, Math.min({BATT_IN}, {num(PV)} - {PV_HOUSE}))"
PV_GRID = f"Math.max(0, Math.min({GRID_OUT}, {num(PV)} - {PV_HOUSE} - {PV_BATT}))"


def pv_destinations():
    """Where PV's power goes now: into the house, into the battery, into the grid."""
    return split_now("Wohin der PV-Strom jetzt geht", [
        ("ins Haus", PV_HOUSE, "#1e88e5", "home"), ("in den Akku", PV_BATT, BATTERY_GREEN, "battery_charging_full"),
        ("ins Netz", PV_GRID, "#78909c", "upload")])


def day_sums(series, stack):
    """The daily totals of the current month as stacked bars, the arrows paging through months; series: (name,
    item, colour)."""
    return chart({"chartType": "month", "periodVisible": True, "height": "260px"},
                 grid=[comp("oh-chart-grid", {"top": "40", "bottom": "60", "left": "45", "right": "20"})],
                 xAxis=[comp("oh-category-axis", {"gridIndex": 0, "categoryType": "month", "name": "Tag", "nameGap": 12,
                                                  "axisTick": {"show": False}})],
                 yAxis=[value_axis("kWh")],
                 series=[daily(name, item, color, stack=stack,
                               **({"itemStyle": {"color": color, "borderRadius": [4, 4, 0, 0]}} if i == len(series) - 1
                                  else {}))
                         for i, (name, item, color) in enumerate(series)],
                 tooltip=tooltip(trigger="axis", smartFormatter=True), legend=legend())


def month_sums(series):
    """Sums per month of the daily total items over a year, the arrows paging through years; series: (name, item,
    colour, extra), bars unless extra says otherwise."""
    return chart({"chartType": "year", "periodVisible": True, "height": "260px"},
                 grid=[comp("oh-chart-grid", {"top": "40", "bottom": "60", "left": "45", "right": "12"})],
                 xAxis=[comp("oh-category-axis", {"gridIndex": 0, "categoryType": "values", "data": PV_MONTHS,
                                                  "name": " ", "axisTick": {"show": False},
                                                  "axisLabel": {"interval": 0, "fontSize": f"={NARROW} ? 10 : 12",
                                                                "formatter": f"=(v, i) => {PV_MONTHS_SHORT}[i]"}})],
                 yAxis=[comp("oh-value-axis", {"gridIndex": 0, "name": "kWh", "nameGap": 14, "nameTextStyle": AXIS_NAME,
                                               "axisLabel": {"formatter": "=(v) => v.toLocaleString('de-AT')"},
                                               "splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.4}}})],
                 series=[comp("oh-aggregate-series", {"name": name, "gridIndex": 0, "xAxisIndex": 0, "yAxisIndex": 0,
                                                      "type": "bar", "item": item, "aggregationFunction": "sum",
                                                      "dimension1": "month", "itemStyle": {"color": color}, **extra})
                         for name, item, color, extra in series],
                 # MainUI's smart formatter, on unless switched off, would override valueFormatter
                 tooltip=tooltip(trigger="axis", smartFormatter=False, valueFormatter=PV_MONTH_VALUE), legend=legend())


def home_blocks():
    """The house, which has no device page: where its power comes from now, its power over the day beside PV and the
    grid, the day's balance, the consumers of the day (the overview's card), and its energy per day and per month."""
    pv_share = f"Math.round(100 * Math.max(0, Math.min({num(PV)}, {num(HOME)} - Math.max(0, {num(GRID)}) - " \
               f"Math.max(0, {num(BATT)}))) / Math.max(1, {num(HOME)}))"
    now = [hero("material:home", HOME_BLUE, "Hausverbrauch", f"={kw(HOME)}",
                [chip(f"='jetzt ' + {pv_share} + ' % aus PV'", "#ffb300")]),
           *home_sources()]
    power = day_chart([area("Haus", HOME, HOME_BLUE), line("PV", PV, "#ffb300", sampling="lttb"),
                       # sampled, a day of 5-second readings is too much to draw
                       line("Netz", GRID, "#e53935", sampling="lttb")], height="100%")
    today = wide_grid([vtile("Verbrauch heute", "home_ec_day", color=HOME_BLUE),
                       vtile("aus PV", "photovoltaics_own_ec_day", color="#43a047"),
                       vtile("aus dem Netz", "huawei_inverter_power_meter_ec_day", color="#e53935"),
                       value_tile("Self-sufficiency", pct("photovoltaics_own_ec_day", "home_ec_day"), color="#43a047"),
                       value_tile("Self-consumption", pct("photovoltaics_own_ec_day", "huawei_inverter_e_day"),
                                  color="#43a047"),
                       vtile("PV-Ertrag", "huawei_inverter_e_day"),
                       vtile("Einspeisung", "huawei_inverter_power_meter_ep_day", color="#43a047"),
                       vtile("Batterie geladen", "huawei_inverter_energy_storage_day_charge"),
                       vtile("Batterie entladen", "huawei_inverter_energy_storage_day_discharge")])
    props = overview_widget_props()
    months = month_sums([("From PV", "energy_daily_self_use", SELF_C, {"stack": "home"}),
                         ("From Grid", "energy_daily_grid_import", IMPORT_C,
                          {"stack": "home", "itemStyle": {"color": IMPORT_C, "borderRadius": [4, 4, 0, 0]}}),
                         ("PV Production", "energy_daily_pv", PV_C,
                          {"type": "line", "symbol": "circle", "symbolSize": 7, "lineStyle": {"width": 2.5, "color": PV_C},
                           "z": 3})])
    return [two(card("Jetzt", now), card("Leistung heute", [fill_chart(power, "260px")], fill=True)),
            block(row(col([card("Heute", [today])]), col([widget_ref("consumption-card", **props["consumption-card"])]))),
            block(row(col([widget_ref("energy-days-card", **props["energy-days-card"])]),
                      col([card("Energie pro Monat", [months])])))]


def appliances_blocks():
    """The household appliances together, which have no device page: their tiles, each opening its machine's page,
    the power now and over the day, the day's energy and its share of the house's, energy per day and the meters."""
    powers = [num(p + "_power") for p, _, _ in FLOW_APPLIANCES]
    running = "[" + ", ".join(powers) + f"].filter((w) => w > {APPL_ON}).length"
    state = f"=((n) => n === 0 ? 'alle aus' : n === 1 ? '1 läuft' : n + ' laufen')({running})"
    total = f"({APPL_POWER} >= 100 ? Math.round({APPL_POWER}) : {fixed(APPL_POWER, 1)}) + ' W'"
    now = [hero("material:local_laundry_service", APPL_COLOR, "Leistung", f"={total}",
                [chip(state, f"=({running}) > 0 ? '#1e88e5' : '#9e9e9e'")]),
           wide_grid([vtile(title, p + "_power") for p, title, _ in FLOW_APPLIANCES])]
    # lines, not stacked areas: ECharts stacks a time axis by the points' index, not their time, and the four plugs
    # are persisted at different moments
    floor = comp("oh-data-series", {"name": "", "type": "line", "xAxisIndex": 0, "yAxisIndex": 0,
                                     "data": [["=dayjs().valueOf()", 100]], "symbol": "none", "silent": True,
                                     "tooltip": {"show": False}})  # keeps their standby noise from filling the axis
    power = day_chart([*[line(title, p + "_power", color) for p, title, color in FLOW_APPLIANCES], floor],
                      height="100%")
    home_share = f"({num('home_ec_day')} > 0 ? 100 * {APPL_DAY} / {num('home_ec_day')} : 0)"
    today = wide_grid([value_tile("Total", f"={fixed(APPL_DAY, 2)} + ' kWh'", color=APPL_COLOR),
                       *[vtile(title, p + "_energy_today") for p, title, _ in FLOW_APPLIANCES],
                       # a decimal below 10 %, so a small day shows more than 0 %
                       value_tile("Anteil am Hausverbrauch", f"=({home_share} < 10 ? {fixed(home_share, 1)} : "
                                  f"Math.round({home_share})) + ' %'", color=HOME_BLUE)])
    days = chart({"chartType": "month", "periodVisible": True, "height": "260px"},
                 grid=[comp("oh-chart-grid", {"top": "40", "bottom": "60", "left": "45", "right": "20"})],
                 xAxis=[comp("oh-category-axis", {"gridIndex": 0, "categoryType": "month", "name": "Tag", "nameGap": 12,
                                                  "axisTick": {"show": False}})],
                 yAxis=[value_axis("kWh")],
                 series=[daily(title, p + "_energy_today", color, stack="appliances")
                         for p, title, color in FLOW_APPLIANCES],
                 tooltip=tooltip(trigger="axis", smartFormatter=True), legend=legend())
    meters = wide_grid([vtile(title, p + "_energy_total") for p, title, _ in FLOW_APPLIANCES])
    return [two(card("Geräte", copy.deepcopy(appliances)), card("Jetzt", now)),
            two(card("Leistung heute", [fill_chart(power, "260px")], fill=True), card("Heute", [today])),
            two(card("Energie pro Tag", [days]), card("Zählerstände", [meters]))]


# the energy flow's own popups, for the two nodes without a device page, laid out like the device pages and opened as
# wide as they are: uid: (label, builder of the blocks)
def self_consumption_blocks():
    """Self-consumption, the share of PV's yield the house uses itself, in the battery included: where PV's power goes
    now, today's yield and its parts, and per day and per month what was used and what was fed in."""
    now = [hero("material:solar_power", "#ffb300", "PV-Leistung", f"={kw(PV)}",
                [chip(f"={num(PV)} > 10 ? 'jetzt ' + Math.round(100 * ({PV_HOUSE} + {PV_BATT}) / {num(PV)}) + "
                      f"' % selbst genutzt' : 'PV ruht'", f"={num(PV)} > 10 ? '#43a047' : '#9e9e9e'")]),
           *pv_destinations()]
    today = wide_grid([value_tile("Self-consumption", pct("photovoltaics_own_ec_day", "huawei_inverter_e_day"),
                                  color="#43a047"),
                       vtile("PV-Ertrag", "huawei_inverter_e_day", color="#ffb300"),
                       vtile("Selbst genutzt", "photovoltaics_own_ec_day", color="#43a047"),
                       vtile("Eingespeist", "huawei_inverter_power_meter_ep_day"),
                       vtile("Akku geladen", "huawei_inverter_energy_storage_day_charge")])
    split = [("Selbst genutzt", "energy_daily_self_use", SELF_C), ("Eingespeist", "energy_daily_grid_export", "#90a4ae")]
    months = month_sums([(n, i, c, {"stack": "pv"}) for n, i, c in split])
    return [two(card("Jetzt", now), card("Heute", [today])),
            two(card("Pro Tag", [day_sums(split, "pv")]), card("Pro Monat", [months]))]


def self_sufficiency_blocks():
    """Self-sufficiency, the share of the house's consumption that PV covers, by way of the battery too: where the
    house's power comes from now, today's consumption and its sources, and per day and per month from PV and from the
    grid."""
    own = f"({PV_HOUSE} + {BATT_OUT})"
    now = [hero("material:home", HOME_BLUE, "Hausverbrauch", f"={kw(HOME)}",
                [chip(f"='jetzt ' + Math.round(100 * Math.min(1, {own} / Math.max(1, {num(HOME)}))) + "
                      f"' % aus eigenen Quellen'", "#43a047")]),
           *home_sources()]
    today = wide_grid([value_tile("Self-sufficiency", pct("photovoltaics_own_ec_day", "home_ec_day"), color="#43a047"),
                       vtile("Verbrauch heute", "home_ec_day", color=HOME_BLUE),
                       vtile("aus PV", "photovoltaics_own_ec_day", color="#43a047"),
                       vtile("aus dem Netz", "huawei_inverter_power_meter_ec_day", color="#e53935"),
                       vtile("Akku entladen", "huawei_inverter_energy_storage_day_discharge")])
    split = [("From PV", "energy_daily_self_use", SELF_C), ("From Grid", "energy_daily_grid_import", IMPORT_C)]
    months = month_sums([(n, i, c, {"stack": "home"}) for n, i, c in split])
    return [two(card("Jetzt", now), card("Heute", [today])),
            two(card("Pro Tag", [day_sums(split, "home")]), card("Pro Monat", [months]))]


FLOW_POPUPS = {"flow_home": ("Home", home_blocks), "flow_appliances": ("Appliances", appliances_blocks),
               "flow_self_consumption": ("Self-consumption", self_consumption_blocks),
               "flow_self_sufficiency": ("Self-sufficiency", self_sufficiency_blocks)}


# ---------------------------------------------------------------- 10. device pages

def wide_grid(tiles):
    """Tiles on the device pages are a little wider than in the popups, so long values fit."""
    return tile_grid(tiles, "160px")


def dash(expr):
    """An empty string, as a String item holds while its device sleeps, shown as a dash like NULL."""
    return f"({expr} || '–')"


def kwc(item):
    return "=" + kw(item)


def kw_signed(item):
    return f"={fixed(f'{num(item)} / 1000', 3)} + ' kW'"


POPUP_COLOR = "#5c6bc0"  # the course in an item popup, where the tile has no colour of its own


def item_modal(item, title, color=None):
    """The props of the item popup for one item: what it shows depends on the item's type and state options."""
    kind, states = item_kind(item)
    props = {"item": item, "title": title, "color": color or POPUP_COLOR, "kind": kind}
    if states:
        props["states"] = states
    return {"action": "popup", "actionModal": "widget:item-popup", "actionModalConfig": props}


def link_over(item, action="popup", radius="12px", title="", color=None):
    """Transparent link over a tile: a tap opens the item's popup (or the item's options)."""
    cfg = {"action": action, "style": {"position": "absolute", "inset": "0", "display": "block", "border-radius": radius}}
    if action == "popup":
        cfg.update(item_modal(item, title, color))
    else:
        cfg["actionItem"] = item
    return comp("oh-link", cfg)


def item_tap(item, action="popup"):
    """The props of a value tile for a tap on it: the item, and what its popup shows or the other action."""
    if action != "popup":
        return {"item": item, "action": action}
    kind, states = item_kind(item)
    return {"item": item, "kind": kind, **({"states": states} if states else {})}


def vtile(title, item, value=None, color=None, visible=None, action="popup"):
    """A value tile that opens its item's popup when tapped."""
    t = value_tile(title, value or f"={dash(disp(item))}", visible, color)
    t["config"].update(item_tap(item, action))
    return t


def text_tile(title, item):
    """A tile for longer text, which wraps across the whole row instead of being cut."""
    t = value_tile(title, f"={dash(disp(item))}")
    t["config"].update({"wrap": True, **item_tap(item)})
    return t


def status_tile(title, item, color="#fb8c00"):
    """An on/off state as a pill, lit while on; opens the item's popup."""
    on = f"items.{item}.state === 'ON'"
    return div([label(title, **{"font-size": "13px", "flex": "1", "min-width": "0", "white-space": "nowrap",
                                "overflow": "hidden", "text-overflow": "ellipsis"}),
                chip(f"={on} ? 'An' : 'Aus'", f"={on} ? '{color}' : '#9e9e9e'"), link_over(item, title=title, color=color)],
               **{"position": "relative", "display": "flex", "align-items": "center", "gap": "8px",
                  "padding": "8px 12px", "border-radius": "12px", "background": "rgba(127, 127, 127, 0.08)"})


def status_grid(tiles):
    return div(tiles, **{"display": "grid", "grid-template-columns": "repeat(auto-fill, minmax(210px, 1fr))",
                         "gap": "8px", "padding": "4px 16px 16px"})


def badge(icon, color, size=56):
    return div([comp("oh-icon", {"icon": icon, "width": size // 2, "height": size // 2})],
               **{"width": f"{size}px", "height": f"{size}px", "border-radius": "50%", "display": "flex",
                  "align-items": "center", "justify-content": "center", "flex": "0 0 auto", "color": color,
                  "background": rgba(color, 0.14), "box-shadow": f"inset 0 0 0 2px {rgba(color, 0.55)}"})


def hero(icon, color, caption, value, extra=(), value_color=None):
    """Head of a device card: its icon in a tinted ring, the main value large, chips below."""
    big = {"font-size": "30px", "font-weight": "700", "line-height": "34px", "white-space": "nowrap"}
    if value_color:
        big["color"] = value_color
    return div([badge(icon, color),
                div([label(caption, **{"font-size": "12px", "opacity": "0.7"}), label(value, **big), *extra],
                    **{"display": "flex", "flex-direction": "column", "align-items": "flex-start", "gap": "3px",
                       "min-width": "0"})],
               **{"display": "flex", "align-items": "center", "gap": "16px", "padding": "12px 16px 8px"})


def cell(item, value=None, color=None, title=""):
    style = {"font-size": "15px", "font-weight": "700", "text-align": "center", "white-space": "nowrap"}
    if color:
        style["color"] = color
    return div([label(value or f"={disp(item)}", **style), link_over(item, radius="8px", title=title, color=color)],
               **{"position": "relative", "padding": "7px 4px", "border-radius": "8px",
                  "background": "rgba(127, 127, 127, 0.08)", "min-width": "0"})


def phase_table(heads, rows):
    """Measurements per phase side by side: one row per measurement, one column per phase."""
    cells = [label(""), *[label(h, **{"font-size": "12px", "font-weight": "700", "opacity": "0.7",
                                      "text-align": "center"}) for h in heads]]
    for title, items_ in rows:
        cells.append(label(title, **{"font-size": "13px", "opacity": "0.75", "align-self": "center"}))
        cells += [cell(i, title=f"{title} {h}") for i, h in zip(items_, heads)]
    return div(cells, **{"display": "grid", "grid-template-columns": f"minmax(90px, 1.3fr) repeat({len(heads)}, 1fr)",
                         "gap": "6px 8px", "padding": "4px 16px 16px"})


def plug_chart(item, color, floor=100, height="260px"):
    series = [area("Leistung", item, color)]
    if floor:  # keeps standby noise of a few tenths of a watt from filling the axis
        series.append(comp("oh-data-series", {"name": "", "type": "line", "xAxisIndex": 0, "yAxisIndex": 0,
                                              "data": [["=dayjs().valueOf()", floor]], "symbol": "none",
                                              "silent": True, "tooltip": {"show": False}}))
    chart_ = day_chart(series, height=height)
    chart_["slots"].pop("legend", None)  # one visible series needs no legend
    chart_["slots"]["grid"][0]["config"]["bottom"] = "35"
    return chart_


def two(a, b):
    return block(row(col([a]), col([b])))


def one(a):
    return block(row(full(a)))


def plug_now_card(prefix, icon, color, title, note, switch_item=None):
    """A metered plug now: power with the switch state, the switch as an on/off pill in the device colour (hidden
    while props.controllable is false), energy today and total, and a note when there is one."""
    switch_item = switch_item or f"{prefix}_switch"
    on = f"items.{switch_item}.state === 'ON'"
    switch = controls_box(power_pill(switch_item, color, "'An'"))  # the same on/off pill as the air conditioner's
    switch["config"]["visible"] = "=props.controllable !== false && props.controllable !== 'false'"
    return card(title, [
        hero(icon, color, "Leistung", f"={disp(prefix + '_power')}",
             [chip(f"={on} ? 'An' : 'Aus'", f"={on} ? '{color}' : '#9e9e9e'")]),
        switch,
        wide_grid([vtile("Energie heute", f"{prefix}_energy_today"), vtile("Energie gesamt", f"{prefix}_energy_total")]),
        label(note, visible="=!!props.note", **{"font-size": "12px", "opacity": "0.6", "padding": "0 16px 14px"})])


def plug_power_card(prefix, color):
    return card("Leistung heute", [fill_chart(plug_chart(f"{prefix}_power", color, height="100%"), "260px")], fill=True)


def plug_days_card(prefix, color):
    return card("Energie pro Tag", [month_bars("Energie", f"{prefix}_energy_today", color)])


def plug_electric_card(prefix, title="Elektrisch"):
    return card(title, [wide_grid([
        vtile("Spannung", f"{prefix}_voltage"), vtile("Strom", f"{prefix}_current"),
        vtile("Leistungsfaktor", f"{prefix}_power_factor"), vtile("Scheinleistung", f"{prefix}_apparent_power"),
        vtile("Blindleistung", f"{prefix}_reactive_power")])])


def plug_cards(prefix, icon, color, title="Nous Steckdose", controllable=True, note=None, switch=None,
               electric_prefix=None, electric_title=None):
    """The cards every metered plug gets, as widgets: now with switch, power today, energy per day, electrical.
    A device behind a shared meter takes its switch and its electrical values from the meter's items."""
    # the first card is titled after what measures and switches: a Nous A1T socket, a Shelly EM on a circuit
    now = {"prefix": prefix, "icon": icon, "color": color, "title": title}
    if not controllable:
        now["controllable"] = False
    if note:
        now["note"] = note
    if switch:
        now["switch"] = switch
    electric = {"prefix": electric_prefix or prefix}
    if electric_title:
        electric["title"] = electric_title
    return [two(widget_ref("plug-card", **now), widget_ref("plug-power-card", prefix=prefix, color=color)),
            two(widget_ref("plug-energy-days-card", prefix=prefix, color=color),
                widget_ref("plug-electric-card", **electric))]


def plug_page(prefix, icon, color, **kw):
    return lambda: plug_cards(prefix, icon, color, **kw)


# ---- appliances with a Miele connection


def miele_page(uid, title, front, p, plug, extra, icon, color):
    def blocks():
        running = miele_state(p)[0]
        program = wide_grid([
            vtile("Status", f"{p}_operation_state"), vtile("Programm", f"{p}_active_program"),
            vtile("Programmphase", f"{p}_program_phase"),
            *[vtile(t, f"{p}_{s}") for t, s in extra],
            vtile("Fortschritt", f"{p}_program_progress"), vtile("Laufzeit", f"{p}_program_elapsed_time"),
            vtile("Restzeit", f"{p}_program_remaining_time"), vtile("Fertig um", f"{p}_program_finished_time"),
            vtile("Startvorwahl", f"{p}_delayed_start_time_absolute"),
            vtile("Energie Programm", f"{p}_current_energy_consumption"),
            *([vtile("Wasser Programm", f"{p}_current_water_consumption")] if uid != "tumble_dryer" else []),
            vtile("Betriebszustand", f"{p}_power_state", action="options")])
        states = status_grid([status_tile("Fertig (Miele)", f"{p}_finished", "#43a047"),
                              status_tile("Tür offen", f"{p}_door_signal", "#fb8c00"),
                              status_tile("Fertig (Steckdose)", f"{plug}_finished", "#43a047")])
        now = [appliance_header(front, p), progress_bar(p), states]
        return [two(card("Jetzt", now), card("Programm", [program])),
                *plug_cards(plug, icon, color)]
    return blocks


# ---- the individual devices


def heatpump_blocks():
    P = HPX
    controls = controls_box(
        smart_grid_section(row=True),
        operation_section(row=True),
        dhw_setpoint(row=True),
        dhw_boost(),
        lw_offset(row=True))
    now = [hero("material:heat_pump", "#fb8c00", "Elektrische Leistung", f"={disp(P['power'])}",
                [chip(f"={disp(P['valve'])}", "#ffa726")]),
           wide_grid([vtile("Heizleistung", P["heat"], color="#e53935"),
                      vtile("COP", P["cop"], f"={num(P['cop'])} > 0 ? {fixed(num(P['cop']), 2)} : '–'"),
                      vtile("Vorlauf nach Heizstab", P["supply"]), vtile("Rücklauf", P["return"]),
                      vtile("Warmwasser", P["tank"]), vtile("Außentemperatur", P["outdoor"]),
                      vtile("Verdichterfrequenz", P["hz"]), vtile("Inverter Strom", "espaltherma_inv_primary_current"),
                      vtile("Durchfluss", P["flow"]), vtile("Umwälzpumpe Signal", "espaltherma_water_pump_signal"),
                      vtile("Wasserdruck", "espaltherma_water_pressure")])]
    power_chart_ = day_chart([area("Elektrisch", P["power"], "#fb8c00"), line("Heizleistung", P["heat"], "#e53935")],
                             height="100%")
    temps_chart = day_chart([line("Vorlauf", P["supply"], "#e53935"), line("Rücklauf", P["return"], "#1e88e5"),
                             line("Warmwasser", P["tank"], "#ab47bc"), line("Außen", P["outdoor"], "#26a69a")],
                            [value_axis("°C", scale=True)])
    today = wide_grid([vtile("Elektrisch heute", "espaltherma_energy_today"),
                       vtile("Heizung", "espaltherma_energy_space_today"),
                       vtile("Warmwasser", "espaltherma_energy_dhw_today"),
                       vtile("Standby", "espaltherma_energy_standby_today"),
                       vtile("Wärme heute", "espaltherma_heating_energy_today", color="#e53935"),
                       vtile("Wärme Heizung", "espaltherma_heating_energy_space_today"),
                       vtile("Wärme Warmwasser", "espaltherma_heating_energy_dhw_today"),
                       vtile("Tages-COP", "espaltherma_dcop"), vtile("Tages-COP Heizung", "espaltherma_dcop_space"),
                       vtile("Tages-COP Warmwasser", "espaltherma_dcop_dhw")])
    split = wide_grid([vtile("Elektrisch Heizung", "espaltherma_electrical_power_space"),
                       vtile("Elektrisch Warmwasser", "espaltherma_electrical_power_dhw"),
                       vtile("Elektrisch Standby", "espaltherma_electrical_power_standby"),
                       vtile("Heizleistung Heizung", "espaltherma_heating_power_space"),
                       vtile("Heizleistung Warmwasser", "espaltherma_heating_power_dhw"),
                       vtile("Heizleistung vor Heizstab", "espaltherma_heating_power_before_buh"),
                       vtile("Heizleistung nach Heizstab", "espaltherma_heating_power_after_buh"),
                       vtile("COP Heizung", "espaltherma_cop_space"), vtile("COP Warmwasser", "espaltherma_cop_dhw")])
    temps = wide_grid([vtile("Raumtemperatur", P["indoor"]), vtile("Außenluft", "espaltherma_outdoor_air_temp"),
                       vtile("Außentemperatur", P["outdoor"]), vtile("Warmwasser", P["tank"]),
                       vtile("Vorlauf vor Heizstab", "espaltherma_leaving_water_temp_before_buh"),
                       vtile("Vorlauf nach Heizstab", P["supply"]), vtile("Rücklauf", P["return"])])
    setpoints = wide_grid([vtile("Vorlauf Sollwert", "espaltherma_leaving_water_setpoint"),
                           vtile("Vorlauf Sollwert (Zusatz)", "espaltherma_leaving_water_setpoint_add"),
                           vtile("Raum Sollwert", "espaltherma_room_temp_setpoint"),
                           vtile("Warmwasser Sollwert", P["tank_set"]),
                           vtile("Soll-Spreizung Heizen", "espaltherma_target_delta_t_heating")])
    modes = status_grid([status_tile(t, i) for t, i in [
        ("Umwälzpumpe", P["pump"]), ("Heizstab Stufe 1", P["buh1"]), ("Heizstab Stufe 2", P["buh2"]),
        ("Warmwasser-Boost", "espaltherma_powerful_dhw_operation"), ("Zusatzheizung Speicher", P["bsh"]),
        ("Heizbetrieb", "espaltherma_space_heating_operation"), ("Flüstermodus", "espaltherma_silent_mode"),
        ("Speicher Komfortmodus", "espaltherma_storage_comfort_mode"), ("Speicher Eco-Modus", "espaltherma_storage_eco_mode"),
        ("Nachheizen", "espaltherma_reheat"), ("System aus", "espaltherma_system_off"),
        ("Thermostatschalter", "espaltherma_thermostat_switch"), ("Frostschutz", "espaltherma_freeze_protection"),
        ("Thermoschutz Heizstab", "espaltherma_thermal_protector_buh"),
        ("Thermoschutz Zusatzheizung", "espaltherma_thermal_protector_bsh"), ("Notbetrieb", "espaltherma_emergency_active"),
        ("Abtauen", P["defrost"]), ("Geräuscharmer Betrieb", "espaltherma_low_noise_control"),
        ("Anforderungssignal", "espaltherma_demand_signal"), ("Neustart-Standby", "espaltherma_restart_standby"),
        ("Anlaufsteuerung", "espaltherma_startup_control"), ("Ölrückführung", "espaltherma_oil_return_operation"),
        ("Druckausgleich", "espaltherma_pressure_equalizing_operation")]])
    refrigerant = wide_grid([vtile("Wärmetauscher Mitte", "espaltherma_heat_exchanger_mid_temp"),
                             vtile("Kältemittel flüssig", "espaltherma_refrig_temp_liquid_side"),
                             vtile("Soll-Heißgas", "espaltherma_target_discharge_temp"),
                             vtile("Heißgas", "espaltherma_discharge_pipe_temp"),
                             vtile("Kältemitteldruck", "espaltherma_refrigerant_pressure_sensor"),
                             vtile("Drucksensor Temperatur", "espaltherma_pressure_sensor_temp")])
    operation = wide_grid([vtile("Außengerät Betrieb", "espaltherma_operation_mode"),
                           vtile("Innengerät Betrieb", "espaltherma_i_u_operation_mode"),
                           vtile("3-Wege-Ventil", P["valve"]), vtile("Fehlercode", "espaltherma_error_code")])
    return [two(card("Steuerung", [controls]), card("Jetzt", now)),
            two(card("Leistung heute", [fill_chart(power_chart_, "260px")], fill=True), card("Temperaturen heute", [temps_chart])),
            two(card("Energie heute", [today]), card("Leistung aufgeteilt", [split])),
            two(card("Temperaturen", [temps]), card("Sollwerte", [setpoints])),
            one(card("Modi", [modes])),
            two(card("Kältemittel", [refrigerant]), card("Betrieb", [operation])),
            *plug_cards("heatpump", "material:heat_pump", "#fb8c00", title="Shelly EM")]


def air_conditioning_blocks():
    controls = controls_box(
        *ac_control_rows(),
        div([comp("oh-icon", {"icon": "material:restart_alt", "width": 22, "height": 22}),
             label("Faikout neu starten", **{"flex": "1", "font-size": "14px"}),
             comp("oh-button", {"text": "Neu starten", "action": "command", "actionItem": "faikout_perfera_restart",
                                "actionCommand": "ON", "actionConfirmation": "Faikout Perfera neu starten?",
                                "actionFeedback": "Neustart gesendet", "outline": True, "small": True})],
            **{"display": "flex", "align-items": "center", "gap": "10px", "padding": "5px 2px"}))
    on = AC_ON_STATE
    now = [hero("material:ac_unit", AC_BLUE, "Raumtemperatur", f"={disp('faikout_perfera_temperature')}",
                [chip(f"={on} ? 'An · ' + {disp('faikout_perfera_mode')} : 'Aus'", f"={on} ? '{AC_BLUE}' : '#9e9e9e'")]),
           wide_grid([vtile("Geräteleistung", "air_conditioning_unit_power", color=AC_BLUE),
                      vtile("Außengerät", "faikout_perfera_power"), vtile("Außentemperatur", "faikout_perfera_outdoor_temperature"),
                      vtile("Flüssigkeitstemperatur", "faikout_perfera_liquid_temperature"),
                      vtile("Solltemperatur", "faikout_perfera_temperature_setpoint"),
                      vtile("Lüfterdrehzahl", "faikout_perfera_fan_speed"),
                      vtile("Verdichterfrequenz", "faikout_perfera_compressor_frequency")])]
    temps_chart = day_chart([line("Raum", "faikout_perfera_temperature", "#fb8c00"),
                             line("Außen", "faikout_perfera_outdoor_temperature", "#26a69a"),
                             line("Flüssigkeit", "faikout_perfera_liquid_temperature", "#29b6f6")],
                            [value_axis("°C", scale=True)])
    return [two(card("Steuerung", [controls]), stack(card("Jetzt", now), card("Temperaturen heute", [temps_chart]))),
            *plug_cards("air_conditioning_unit", "material:ac_unit", AC_BLUE, title="Shelly EM",
                        switch="air_conditioning_switch", electric_prefix="air_conditioning",
                        electric_title="Elektrisch · Shelly EM")]


VENT_LEVELS = [("1", "Niedrig"), ("2", "Mittel"), ("3", "Hoch")]


def ventilation_blocks():
    controls = controls_box(
        section("material:air", "Stufe", VENT_TEAL, [state_bar("esplyfterl_level", VENT_LEVELS, VENT_TEAL)], row=True),
        vent_timer(row=True),
        switch_row("Automatik", "material:tune", "ventilation_management", VENT_TEAL),
        switch_row("CO2-Automatik", "material:co2", "ventilation_co2_management", VENT_TEAL),
        switch_row("Feuchte-Automatik", "material:water_drop", "ventilation_humidity_management", VENT_TEAL),
        switch_row("Temperatur-Automatik", "material:thermostat", "ventilation_temperature_management", VENT_TEAL))
    air = day_chart([line("CO2", "netatmo_weatherstation_co2", "#78909c"),
                     line("Luftfeuchtigkeit", "netatmo_weatherstation_atmospheric_humidity", "#29b6f6", y=1)],
                    [value_axis("ppm", scale=True), value_axis("", splitLine={"show": False}, axisLabel={"formatter": "{value} %"})])
    return [two(card("Steuerung", [controls]), card("Raumluft heute", [air])),
            *plug_cards("ventilation", "material:air", VENT_TEAL)]


def energy_storage_blocks():
    batt_state = f"{num(BATT)} < -10 ? 'lädt' : {num(BATT)} > 10 ? 'entlädt' : 'ruht'"
    now = [hero("material:battery_charging_full", "#7cb342", "Ladestand", f"={disp(SOC)}",
                [chip(f"={fixed(f'{num(BATT)} / 1000', 3)} + ' kW · ' + ({batt_state})", "#7cb342")]),
           wide_grid([vtile("Leistung", BATT, kw_signed(BATT)),
                      vtile("Status", "huawei_inverter_energy_storage_running_status"),
                      vtile("Geladen heute", "huawei_inverter_energy_storage_day_charge"),
                      vtile("Entladen heute", "huawei_inverter_energy_storage_day_discharge")])]
    control_items = [
        comp("oh-label-item", {"action": "options", "actionItem": "huawei_inverter_energy_storage_forcible_charge_discharge",
                               "icon": "material:battery_charging_full", "item": "huawei_inverter_energy_storage_forcible_charge_discharge",
                               "title": "Zwangsladen/-entladen"}),
        comp("oh-label-item", {**item_modal("huawei_inverter_energy_storage_remaining_charge_discharge_time",
                                            "Restzeit Laden/Entladen"),
                               "icon": "material:hourglass_bottom", "item": "huawei_inverter_energy_storage_remaining_charge_discharge_time",
                               "title": "Restzeit Laden/Entladen"})]
    controls = [comp("f7-list", {"style": {"margin": "0 0 8px"}}, default=control_items),
                controls_box(battery_power_slider("huawei_inverter_energy_storage_forcible_charge_power",
                                                  "Zwangsladeleistung", "beim Zwangsladen"),
                             battery_power_slider("huawei_inverter_energy_storage_forcible_discharge_power",
                                                  "Zwangsentladeleistung", "beim Zwangsentladen"),
                             battery_period_slider()),
                wide_grid([vtile("Zwangsladestatus", "huawei_inverter_energy_storage_forcible_status")])]
    totals = wide_grid([vtile("Ladestand", SOC), vtile("Geladen gesamt", "huawei_inverter_energy_storage_total_charge"),
                        vtile("Entladen gesamt", "huawei_inverter_energy_storage_total_discharge"),
                        vtile("Busspannung", "huawei_inverter_energy_storage_bus_voltage"),
                        vtile("Busstrom", "huawei_inverter_energy_storage_bus_current")])
    u = "huawei_inverter_energy_storage_unit_1_"
    unit = wide_grid([vtile("Status", u + "running_status"), vtile("Ladestand", u + "soc"), vtile("Leistung", u + "power"),
                      vtile("Geladen heute", u + "day_charge"), vtile("Entladen heute", u + "day_discharge"),
                      vtile("Geladen gesamt", u + "total_charge"), vtile("Entladen gesamt", u + "total_discharge"),
                      vtile("Busspannung", u + "bus_voltage"), vtile("Busstrom", u + "bus_current"),
                      vtile("Temperatur", u + "temperature")])
    chart_ = day_chart([area("Leistung", BATT, "#7cb342"), line("Ladestand", SOC, "#43a047", y=1)],
                       [value_axis("W"), value_axis("", min=0, max=100, splitLine={"show": False}, axisLabel={"formatter": "{value} %"})],
                       height="100%")
    return [two(card("Jetzt", now), card("Leistung heute", [fill_chart(chart_, "260px")], fill=True)),
            two(card("Steuerung", controls), card("Speicher", [totals])),
            one(card("Einheit 1", [unit]))]


def photovoltaics_blocks():
    now = [hero("material:solar_power", "#ffb300", "Eingangsleistung", kwc(PV)),
           wide_grid([vtile("Wirkleistung", "huawei_inverter_active_power", kwc("huawei_inverter_active_power")),
                      vtile("Spitze heute", "huawei_inverter_active_peak_of_current_day",
                            kwc("huawei_inverter_active_peak_of_current_day")),
                      vtile("Blindleistung", "huawei_inverter_reactive_power"),
                      vtile("Wirkungsgrad", "huawei_inverter_efficiency"),
                      vtile("Energie heute", "huawei_inverter_e_day", color="#ffb300"),
                      vtile("Eigenverbrauch heute", "photovoltaics_own_ec_day", color="#43a047"),
                      vtile("Energie gesamt", "huawei_inverter_e_total")])]
    chart_ = day_chart([area("Eingang", PV, "#ffb300"), line("Wirkleistung", "huawei_inverter_active_power", "#5c6bc0")],
                       height="100%")
    strings = phase_table(["PV1", "PV2"], [("Leistung", ["huawei_inverter_pv1_power", "huawei_inverter_pv2_power"]),
                                           ("Spannung", ["huawei_inverter_pv1_voltage", "huawei_inverter_pv2_voltage"]),
                                           ("Strom", ["huawei_inverter_pv1_current", "huawei_inverter_pv2_current"])])
    grid_ = phase_table(["A", "B", "C"], [("Spannung", [f"huawei_inverter_phase_{x}_voltage" for x in "abc"]),
                                           ("Strom", [f"huawei_inverter_phase_{x}_current" for x in "abc"])])
    inverter = wide_grid([vtile("Gerätestatus", "huawei_inverter_device_status"),
                          vtile("Startzeit", "huawei_inverter_startup_time"),
                          vtile("Abschaltzeit", "huawei_inverter_shutdown_time"),
                          vtile("Innentemperatur", "huawei_inverter_internal_temperature"),
                          vtile("Fehlercode", "huawei_inverter_error_code"),
                          vtile("Optimierer online", "huawei_inverter_optimizers_online"),
                          vtile("Optimierer gesamt", "huawei_inverter_optimizers_total")])
    return [two(card("Jetzt", now), card("Leistung heute", [fill_chart(chart_, "260px")], fill=True)),
            two(card("Strings (DC)", [strings]), card("Netz (AC)", [grid_])),
            two(card("Wechselrichter", [inverter]), card("Ertrag pro Tag", [month_bars("PV-Ertrag", "energy_daily_pv", "#ffb300")]))]


def meter_blocks(title_item, color_expr, today, phases, heads, extra, chart_item):
    """SmartPi and the Huawei power meter: signed power, today's energies, the phases side by side."""
    def blocks():
        now = [hero("material:electric_meter", "#5c6bc0", f"={num(title_item)} < 0 ? 'Einspeisung' : 'Bezug'",
                    kw_signed(title_item), value_color=color_expr),
               wide_grid([vtile(t, i, color=c) for t, i, c in today] + [vtile(t, i) for t, i in extra])]
        # sampled, a day of 5-second readings is too much to draw
        chart_ = day_chart([time_series("Leistung", chart_item, symbol="none", sampling="lttb", lineStyle={"width": 1.5},
                                        areaStyle={"opacity": 0.25})], height="100%", visualMap=sign_colors())
        return [two(card("Jetzt", now), card("Leistung heute", [fill_chart(chart_, "260px")], fill=True)),
                one(card("Phasen", [phase_table(heads, phases)]))]
    return blocks


def netatmo_blocks():
    w, o = "netatmo_weatherstation_", "netatmo_outdoor_"
    inside = [hero("material:thermostat", "#fb8c00", "Innen", f"={disp(w + 'temperature')}"),
              wide_grid([vtile("Luftfeuchtigkeit", w + "atmospheric_humidity"), vtile("CO2", w + "co2"),
                         vtile("Lärm", w + "noise"), vtile("Luftdruck", w + "barometric_pressure")])]
    outside = [hero("material:wb_sunny", "#29b6f6", "Außen", f"={disp(o + 'temperature')}"),
               wide_grid([vtile("Luftfeuchtigkeit", o + "atmospheric_humidity"), vtile("Batteriestand", o + "battery_level")])]
    temps = day_chart([line("Innen", w + "temperature", "#fb8c00"), line("Außen", o + "temperature", "#29b6f6")],
                      [value_axis("°C", scale=True)])
    air = day_chart([line("CO2", w + "co2", "#78909c"),
                     line("Luftfeuchtigkeit innen", w + "atmospheric_humidity", "#29b6f6", y=1),
                     line("Luftfeuchtigkeit außen", o + "atmospheric_humidity", "#80deea", y=1)],
                    [value_axis("ppm", scale=True), value_axis("", splitLine={"show": False}, axisLabel={"formatter": "{value} %"})])

    def details(p, extra):
        return wide_grid([vtile("Zuletzt gesehen", p + "last_seen"), vtile("Messzeitpunkt", p + "measures_timestamp"),
                          vtile("Signal", p + "signal"), vtile("Signalstärke", p + "signal_strength"), *extra,
                          vtile("Taupunkt", p + "dewpoint"), vtile("Hitzeindex", p + "heat_index"),
                          vtile("Min. Temperatur", p + "min_temp"), vtile("Max. Temperatur", p + "max_temp")])
    return [two(card("Wetterstation", inside), card("Außenmodul", outside)),
            two(card("Temperaturen heute", [temps]), card("Raumluft heute", [air])),
            two(card("Wetterstation Details", [details(w, [vtile("Absoluter Luftdruck", w + "absolute_pressure")])]),
                card("Außenmodul Details", [details(o, [])]))]


def water_meter_blocks():
    now = [hero("material:water", "#1e88e5", "Verbrauch heute", f"={disp('water_meter_value_day')}"),
           wide_grid([vtile("Zählerstand", "water_meter_value"), vtile("Durchfluss", "water_meter_rate"),
                      vtile("Status", "water_meter_status"), vtile("Zeitstempel", "water_meter_timestamp"),
                      text_tile("Fehler", "water_meter_error")])]
    image = comp("oh-image-card", {"action": "url", "actionUrl": "http://water-meter.domotics.lan", "lazy": True,
                                   "lazyFadeIn": True, "refreshInterval": 10000.0, "url": "/water-meter/img_tmp/alg_roi.jpg",
                                   "noShadow": True, "noBorder": True})
    rate = water_rate_chart()
    return [two(card("Jetzt", now), card("Zählerbild", [image])),
            two(card("Durchfluss heute", [rate]), card("Verbrauch pro Tag", [month_bars("Verbrauch", "water_meter_value_day", "#1e88e5", "l", 1000)]))]


def living_room_blocks():
    vu = [hero("material:tv", "#ec407a", "Vu+ Uno 4k", f"={disp('vuuno4k_channel')}",
               [chip(f"=items.vuuno4k_power.state === 'ON' ? 'An' : 'Aus'",
                     f"=items.vuuno4k_power.state === 'ON' ? '#ec407a' : '#9e9e9e'")]),
          controls_box(power_pill("vuuno4k_power", "#ec407a", "'An'")),  # the same on/off pill as the plugs'
          wide_grid([vtile("Sender", "vuuno4k_channel"), text_tile("Titel", "vuuno4k_title"),
                     text_tile("Beschreibung", "vuuno4k_description")])]
    blocks = plug_cards("living_room_entertainment", "material:tv", "#ec407a")
    return [one(card("Receiver", vu)), *blocks]


def epex_spot_blocks():
    now = [hero("material:euro", "#fb8c00", "Gesamtpreis brutto", f"={disp(PRICE)}", value_color=price_color),
           wide_grid([vtile("Gesamt netto", "epex_spot_awattar_total_net"),
                      vtile("Markt brutto", "epex_spot_awattar_market_gross"),
                      vtile("Markt netto", "epex_spot_awattar"),
                      vtile("Günstigste Stunde", "epex_spot_awattar_cheapest_hour"),
                      vtile("Günstigster Preis", "epex_spot_awattar_cheapest"),
                      vtile("Teuerste Stunde", "epex_spot_awattar_priciest_hour"),
                      vtile("Teuerster Preis", "epex_spot_awattar_priciest")])]
    prices = chart({"period": "2D", "future": "0.75", "periodVisible": True, "height": "100%"},
                   grid=[comp("oh-chart-grid", {"top": "40", "bottom": "60", "left": "50", "right": "20"})],
                   xAxis=[comp("oh-time-axis", {"gridIndex": 0})],
                   yAxis=[value_axis("EUR/kWh")],
                   series=[time_series(n, i, step="end", symbol="none", lineStyle={"width": w, "color": c},
                                       itemStyle={"color": c}, **extra)
                           for n, i, c, w, extra in (
                               ("Gesamt brutto", PRICE, "#e53935", 2.5, {"areaStyle": {"opacity": 0.12},
                                "markLine": {"symbol": ["none", "none"], "silent": True, "label": {"show": False},
                                             "lineStyle": {"color": "#888", "type": "dashed"},
                                             "data": [{"xAxis": "=dayjs().valueOf()"}]}}),
                               ("Gesamt netto", "epex_spot_awattar_total_net", "#fb8c00", 1.5, {}),
                               ("Markt brutto", "epex_spot_awattar_market_gross", "#ffb74d", 1.5, {}),
                               ("Markt netto", "epex_spot_awattar", "#ffcc80", 1.5, {}))],
                   tooltip=tooltip(trigger="axis", smartFormatter=True), legend=legend())
    return [two(card("Jetzt", now), card("Preise 12 h zurück, 36 h voraus", [fill_chart(prices, "360px")], fill=True))]


GRID_SIGN = f"={num(GRID)} < 0 ? '#43a047' : '#e53935'"
SMARTPI_SIGN = f"={num('smartpi_ptot')} < 0 ? '#43a047' : '#e53935'"
def below_controls(builder):
    return lambda: plots_below_controls(builder())


# the label, icon and sidebar order of a page the generator adds, until the UI changes them
NEW_PAGES = {"weather": {"label": "Wetter", "icon": "material:wb_sunny", "order": "1"}}
DEVICE_PAGES = {
    # uid: builder of the blocks; label, icon and sidebar order stay those of the existing page
    "weather": weather_blocks,
    "netatmo": netatmo_blocks,
    "smartpi": meter_blocks("smartpi_ptot", SMARTPI_SIGN,
                            [("Bezug heute", "smartpi_ecday", "#e53935"), ("Einspeisung heute", "smartpi_epday", "#43a047")],
                            [("Leistung", ["smartpi_p1", "smartpi_p2", "smartpi_p3"]),
                             ("Spannung", ["smartpi_v1", "smartpi_v2", "smartpi_v3"]),
                             ("Strom", ["smartpi_i1", "smartpi_i2", "smartpi_i3"]),
                             ("Frequenz", ["smartpi_f1", "smartpi_f2", "smartpi_f3"]),
                             ("cos φ", ["smartpi_cos1", "smartpi_cos2", "smartpi_cos3"])],
                            ["L1", "L2", "L3"], [("Strom N", "smartpi_i4")], "smartpi_ptot"),
    "power_meter": meter_blocks(GRID, GRID_SIGN,
                                [("Bezug heute", "huawei_inverter_power_meter_ec_day", "#e53935"),
                                 ("Einspeisung heute", "huawei_inverter_power_meter_ep_day", "#43a047")],
                                [("Wirkleistung", [f"huawei_inverter_power_meter_phase_{x}_active_power" for x in "abc"]),
                                 ("Spannung", [f"huawei_inverter_power_meter_phase_{x}_voltage" for x in "abc"]),
                                 ("Strom", [f"huawei_inverter_power_meter_phase_{x}_current" for x in "abc"])],
                                ["A", "B", "C"],
                                [("Blindleistung", "huawei_inverter_power_meter_reactive_power"),
                                 ("Leistungsfaktor", "huawei_inverter_power_meter_power_factor"),
                                 ("Frequenz", "huawei_inverter_power_meter_frequency")], GRID),
    "photovoltaics": photovoltaics_blocks,
    "energy_storage": energy_storage_blocks,
    "e_car": plug_page("e_car", "material:electric_car", ECAR_COLOR, title="E-Auto", controllable=False,
                       note=ECAR_CALC + " Der Schalter spiegelt nur das Relais des Shelly EM, das mit nichts "
                                        "verbunden ist."),
    "air_conditioning": air_conditioning_blocks,
    "heatpump": heatpump_blocks,
    "ventilation": ventilation_blocks,
    "water_meter": water_meter_blocks,
    "coffee_machine": plug_page("coffee_machine", "material:coffee", "#8d6e63"),
    "washing_machine_1": miele_page("washing_machine_1", "Waschmaschine 1", washer_front, "miele_washing_machine_wwg360",
                                    "washing_machine_1", [("Zieltemperatur", "target_temperature"),
                                                          ("Schleuderdrehzahl", "spinning_speed")],
                                    "material:local_laundry_service", "#42a5f5"),
    "washing_machine_2": plug_page("washing_machine_2", "material:local_laundry_service", "#42a5f5"),
    "tumble_dryer": miele_page("tumble_dryer", "Wäschetrockner", dryer_front, "miele_tumble_dryer_twc560wp",
                               "tumble_dryer", [("Trocknungsziel", "drying_target")], "material:dry_cleaning", "#ffa726"),
    "refrigerator": plug_page("refrigerator", "material:kitchen", "#78909c"),
    "dishwasher": miele_page("dishwasher", "Geschirrspüler", dishwasher_front, "miele_dishwasher_g7465",
                             "dishwasher", [], "material:flatware", "#26c6da"),
    "living_room_entertainment": living_room_blocks,
    "network": plug_page("network", "material:router", "#5c6bc0"),
    "office_1": plug_page("office_1", "material:computer", "#ab47bc"),
    "office_2": plug_page("office_2", "material:computer", "#ab47bc"),
    "terrace_light": plug_page("terrace_light", "material:light", "#fbc02d"),
    "bicycle_batteries": plug_page("bicycle_batteries", "material:electric_bike", "#7cb342"),
    "epex_spot": epex_spot_blocks,
}
DEVICE_PAGES = {uid: below_controls(builder) for uid, builder in DEVICE_PAGES.items()}



# ---------------------------------------------------------------- German texts of the generated pages

GEN_DE = {
    # page and card titles
    "Overview": "Übersicht", "Controls": "Steuerung", "Energy Flow": "Energiefluss", "Appliances": "Haushaltsgeräte",
    "Switches": "Schalter",
    "Heating & Hot Water": "Heizung & Warmwasser", "Electricity Price": "Strompreis", "Heatpump": "Wärmepumpe", "Energy per Day": "Energie pro Tag",
    "PV Production per Day": "PV-Ertrag pro Tag", "Temperatures": "Temperaturen", "Now": "Jetzt", "Today": "Heute",
    "Power": "Leistung", "Home": "Haus", "Washing Machine 1": "Waschmaschine 1", "Washing Machine 2": "Waschmaschine 2",
    "Tumble Dryer": "Wäschetrockner", "Dishwasher": "Geschirrspüler",
    # energy flow and heat pump drawing
    "Self-consumption": "Eigenverbrauch", "Self-sufficiency": "Autarkie", "today": "heute", "Defrosting": "Abtauen",
    "Upper Floor": "Obergeschoss", "Ground Floor": "Erdgeschoss", "Radiators": "Heizkörper", "Basement": "Keller",
    # heat pump panel and controls
    "Electrical": "Elektrisch", "Heat": "Wärme", "COP": "COP", "COP Space": "COP Heizung", "COP DHW": "COP Warmwasser",
    "COP Total": "COP gesamt", "Electricity": "Strom", "Electricity Today": "Strom heute", "Heat Today": "Wärme heute", "Heizung": "Heizung", "Warmwasser": "Warmwasser",
    "Standby": "Standby", "Smart Grid": "Smart Grid", "Ventilation": "Lüftung", "Fan": "Lüfter", "Mode": "Modus",
    "Timer": "Timer", "Auto": "Auto",
    # price
    "per kWh all-in": "pro kWh gesamt", "EUR/kWh": "EUR/kWh", "All-in price": "Gesamtpreis",
    "Total Net": "Gesamt netto", "Market Gross": "Markt brutto", "Market Net": "Markt netto",
    # consumption, daily energy, calendar, temperatures
    "Consumers": "Verbraucher", "From PV": "Aus PV", "From Grid": "Aus dem Netz", "PV Production": "PV-Ertrag",
    "Average per Day": "Ø pro Tag", "kWh": "kWh", "Tag": "Tag", "Indoor": "Innen", "Outdoor": "Außen",
    "Heatpump sensor": "Fühler der Wärmepumpe", "°C": "°C", "W": "W",
    # energy flow popups and the controls
    "Total": "Gesamt", "Consumption": "Verbrauch", "Climate Control": "Heizung",
    "DHW Management": "Warmwasser-Automatik", "DHW Setpoint": "Warmwasser Soll",
    "Leaving Water Offset": "Vorlauf-Offset", "Eco": "Eco", "Quiet": "Leise", "Comfort": "Komfort",
    "Streamer": "Streamer", "Swing Horizontal": "Schwenken horizontal", "Swing Vertical": "Schwenken vertikal",
    "Swing H": "Schwenken H", "Swing V": "Schwenken V", "Status": "Status",
}

# classic icons in the generated pages become material ones
ICONS = {
    "oh:heating": "material:heat_pump", "oh:snow": "material:ac_unit", "oh:fan": "material:air",
    "oh:water": "material:shower", "oh:settings": "material:tune", "oh:temperature_hot": "material:device_thermostat",
    "oh:temperature": "material:device_thermostat", "oh:climate": "material:tune", "oh:time": "material:timer",
    "oh:fire": "material:whatshot", "oh:energy": "material:eco", "oh:soundvolume_mute": "material:volume_off",
    "oh:sofa": "material:weekend", "oh:flow": "material:air", "oh:movecontrol": "material:swap_vert",
    "oh:oil": "material:coffee", "oh:lowbattery": "material:electric_bike", "oh:office": "material:computer",
    "oh:light": "material:light", "oh:switch": "material:toggle_on",
}


def germanize(node, missing):
    """Translate plain texts and classic icons in a component tree in place; collect texts without translation."""
    if isinstance(node, list):
        for x in node:
            germanize(x, missing)
        return
    if not isinstance(node, dict):
        return
    cfg = node.get("config", {})
    for key in ("text", "title", "label", "name", "content"):
        val = cfg.get(key)
        if isinstance(val, str) and val and not val.startswith("=") and any(c.isalpha() for c in val):
            if val in GEN_DE:
                cfg[key] = GEN_DE[val]
            elif val not in GEN_DE.values() and val.isascii():
                missing.add(val)
    if isinstance(cfg.get("icon"), str) and cfg["icon"] in ICONS:
        cfg["icon"] = ICONS[cfg["icon"]]
    for key in ("xAxis", "yAxis"):
        pass
    for slot in node.get("slots", {}).values():
        germanize(slot, missing)


MISSING_DE = set()


# ---------------------------------------------------------------- page


def timestamp(now):
    hour = now.hour % 12 or 12
    return f"{now:%b} {now.day}, {now.year}, {hour}:{now:%M:%S} {'AM' if now.hour < 12 else 'PM'}"


# A chart's period menu is hidden by opacity alone and stays in the layout: under a chart low on a page it
# stretches the page, or a popup, by its full length. Out of the layout while closed, it opens as before. Its buttons
# stand 6 to 42 px from the chart's top instead of Framework7's 16 to 52 px, clear of the axis names below them;
# Framework7 sets the padding class's padding as important.
PERIOD_MENU = "\n".join([".menu-item-dropdown:not(.menu-item-dropdown-opened) .menu-dropdown { display: none; }",
                         ".oh-chart-container > .menu.padding { padding-top: 6px !important; }"])


def one_block(blocks):
    """The rows of all blocks in one block: the cards keep a card's gap of 20 px between them, not a block's 36."""
    assert all(b["component"] == "oh-block" and not b["config"] for b in blocks), "a block with a config of its own"
    return [block(*[c for b in blocks for c in b["slots"]["default"]])]


# A device page opened as a popup (from the overview's controls, energy flow, appliances, heat pump drawing or
# weather bar), and the energy flow's own popups, take nearly the whole window instead of Framework7's 630 × 630 px,
# so their two columns keep their width. MainUI puts a popup page's config.style on the popup's page element; the mark
# there tells such a popup from the item popups opened over it. ":root" keeps the rule unscoped, it holds while the page is shown; a
# phone shows every popup full screen anyway.
WIDE_POPUP_MARK = {"--page-popup": "wide"}
WIDE_POPUP = (':root .popup:has(> .oh-popup[style*="--page-popup"]) { --f7-popup-tablet-width: min(1240px, '
              'calc(100vw - 64px)); --f7-popup-tablet-height: calc(100vh - 64px); }')


def layout_page(uid, config, blocks, now):
    blocks = one_block(blocks)
    germanize(blocks, MISSING_DE)
    if config.get("label") in GEN_DE:
        config = {**config, "label": GEN_DE[config["label"]]}
    config = {**config, "stylesheet": "\n".join(filter(None, [config.get("stylesheet"), PHONE_EDGES, PERIOD_MENU]))}
    return {
        "class": "org.openhab.core.ui.components.RootUIComponent",
        "value": {"uid": uid, "tags": [], "props": {"parameters": [], "parameterGroups": []},
                  "timestamp": timestamp(now), "component": "oh-layout-page", "config": config,
                  "slots": {"canvas": [], "default": blocks}},
    }


def full(card_):
    return col([card_], medium="100", large="100", xlarge="100")


# MainUI hides the scrollbar on its home page (.page-home .page-content::-webkit-scrollbar { width: 0 }); the
# standard properties override that in Chrome and Firefox, the thumb rule in Safari. ":root" keeps the rules
# unscoped, they apply while the overview is shown.
SCROLLBAR = """:root .page-home .page-content { scrollbar-width: thin; scrollbar-color: rgba(127, 127, 127, 0.5) transparent; }
:root .page-home .page-content::-webkit-scrollbar { width: 8px; }
:root .page-home .page-content::-webkit-scrollbar-thumb { background: rgba(127, 127, 127, 0.5); border-radius: 4px; }"""
# On phones the cards of every generated page come closer to the screen edges, 10 px instead of 26 (block
# padding plus card margin), and hold less padding themselves: Framework7's 16 px comes on top of the 16 px of
# the tiles and grids inside, so it shrinks to 4 px at the sides and the title lines up with the content.
# Scoped to the page, so the rules win over Framework7's; the card content also carries Framework7's
# utility class "padding", whose 16 px are !important.
PHONE_EDGES = """@media (max-width: 599px) { .block { padding-left: 4px; padding-right: 4px; }
  .card { margin-left: 6px; margin-right: 6px; }
  .card-content-padding { padding: 12px 4px !important; }
  .card-header { padding-left: 20px; padding-right: 20px; } }"""


def overview_cards():
    """The overview's cards; each is a widget of its own."""
    return {
        "weather-card": weather_card(),
        "energy-flow-card": card("Energy Flow", energy_flow(), fill=True),
        "switches-card": card("Switches", [div([switch_tiles()], **{"padding": "12px 16px 16px"})]),
        "appliances-card": card("Appliances", appliances, fill=True),
        "heating-card": card("Heating & Hot Water", heating()),
        "electricity-price-card": card("Electricity Price", price, fill=True),
        "heatpump-card": card("Heatpump", heatpump_content(), fill=True),
        "consumption-card": card("='Verbrauch heute · ' + " + disp("home_ec_day"), consumption),
        "energy-days-card": card("Energy per Day", [fill_chart(energy_days, "340px")], fill=True),
        "pv-days-card": card("PV Production per Day", [pv_days()]),
        "temperatures-card": card("Temperatures", temps),
    }


def widget_stack(*cards, grow=None):
    """Card widgets one above the other in a column, as stack() does with cards: MainUI renders a widget without a
    wrapper, so the column's stylesheet sets the heights: all at their own, one taking what the row leaves, the
    last or the grow-th (from 1)."""
    column = div(list(cards), **{"display": "flex", "flex-direction": "column", "height": "100%"})
    which = f":nth-child({grow})" if grow else ":last-child"
    column["config"]["stylesheet"] = (":host > .card { height: auto !important; flex: 0 0 auto; }\n"
                                      f":host > .card{which} {{ flex: 1 1 auto; }}")
    return column


def page(now):
    props = overview_widget_props()
    w = lambda uid: widget_ref(uid, **props[uid])  # every item a widget reads comes in as a prop
    return layout_page(PAGE_UID, {"label": "Overview", "stylesheet": SCROLLBAR}, [
        # the weather bar over the energy flow over the switches beside the appliances over heating and hot water (on
        # a phone the weather stays on top), the flow taking the height the row leaves; the heat pump beside today's
        # consumption over the energy per day, which fills the column down to the heat pump's height; the price beside
        # the temperatures; the PV calendar across the bottom
        block(row(col([widget_stack(w("weather-card"), w("energy-flow-card"), w("switches-card"), grow=2)]),
                  col([widget_stack(w("appliances-card"), w("heating-card"))])),
              row(col([w("heatpump-card")]), col([widget_stack(w("consumption-card"), w("energy-days-card"))])),
              row(col([w("electricity-price-card")]), col([w("temperatures-card")])),
              row(full(w("pv-days-card")))),
    ], now)


# ---------------------------------------------------------------- 11. widgets

# The plug widgets are built by the same card builders from placeholders, then every placeholder becomes an
# expression on the widget's props; the colour's rgba shades are worked out from props.color in the widget.
PLUG_PLACEHOLDERS = {"prefix": "zzpfx", "icon": "zzicon", "color": "#010203", "title": "zztitle", "note": "zznote",
                     "switch": "zzswitch", "item": "zzitem"}
SWITCH_JS = "(props.switch || props.prefix + '_switch')"  # the switch item: its own prop, else the prefix's
PROPS_RGB = ("Number.parseInt(props.color.slice(1, 3), 16) + ', ' + Number.parseInt(props.color.slice(3, 5), 16)"
             " + ', ' + Number.parseInt(props.color.slice(5, 7), 16)")
PLACEHOLDER_JS = [("rgba(1, 2, 3, ", "rgba(' + " + PROPS_RGB + " + ', "), ("#010203", "' + props.color + '"),
                  ("zzicon", "' + props.icon + '"), ("zztitle", "' + props.title + '"), ("zznote", "' + props.note + '"),
                  ("zzswitch", "' + " + SWITCH_JS + " + '"), ("zzitem", "' + props.item + '"),
                  ("zzpfx", "' + props.prefix + '")]


def has_placeholder(v):
    return isinstance(v, str) and any(t in v for t, _ in PLACEHOLDER_JS)


def tidy(expr):
    """Drop the empty string pieces the substitution leaves around a prop."""
    expr = expr.replace("'' + " + SWITCH_JS + " + ''", SWITCH_JS)
    return re.sub(r"(props\.\w+) \+ ''", r"\1", re.sub(r"'' \+ (props\.\w+)", r"\1", expr))


def js_literal(text):
    """A plain text as a JavaScript string expression, its placeholders turned into props."""
    lit = "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"
    for token, js in PLACEHOLDER_JS:
        lit = lit.replace(token, js)
    return tidy(lit)


def templated(v):
    """A component tree built from placeholders, with every placeholder read from the widget's props."""
    if isinstance(v, dict):
        return {k: templated(x) for k, x in v.items()}
    if isinstance(v, list):
        if any(has_placeholder(x) for x in v):  # a list with placeholders, e.g. the state band's category
            return "=[" + ", ".join(js_literal(x) for x in v) + "]"
        return [templated(x) for x in v]
    if has_placeholder(v):
        if v.startswith("="):
            expr = re.sub(r"items\.zzpfx_(\w+)", r"items[props.prefix + '_\1']", v[1:])
            expr = expr.replace("items.zzswitch", "items[" + SWITCH_JS + "]").replace("items.zzitem", "items[props.item]")
            for token, js in PLACEHOLDER_JS:  # what is left sits inside string literals
                expr = expr.replace(token, js)
            return "=" + tidy(expr)
        return "=" + js_literal(v)
    return v


# the band of an item's states reads its labels from props.states, value=label pairs; switches read An and Aus
STATE_LABEL = ("=(s) => ((props.states || 'ON=An,OFF=Aus').split(',').map((o) => o.trim().split('='))"
               ".find((o) => o[0] === s) || [s, s])[1]")


def item_popup():
    """The popup a tile of a device page opens: the item's value large, its course over the day as a line, or as a
    band of its states for switches, texts and numbers with state options."""
    item, title, color = PLUG_PLACEHOLDERS["item"], PLUG_PLACEHOLDERS["title"], PLUG_PLACEHOLDERS["color"]
    now = card(title, [label(f"={dash(disp(item))}", **{"font-size": "30px", "font-weight": "700", "line-height": "36px",
                                                        "overflow-wrap": "anywhere", "padding": "4px 16px 18px"})])
    line = card("Verlauf", [day_chart([area(title, item, color)], [value_axis("")])])
    line["config"]["visible"] = "=!props.kind || props.kind === 'number'"
    band = card("Verlauf", [chart({"period": "D", "periodVisible": True, "height": "150px"},
                                  grid=[comp("oh-chart-grid", {"top": "35", "bottom": "35", "left": "20", "right": "20"})],
                                  xAxis=[comp("oh-time-axis", {"gridIndex": 0})],
                                  yAxis=[comp("oh-category-axis", {"gridIndex": 0, "categoryType": "values", "data": [title],
                                                                   "show": False})],
                                  series=[comp("oh-state-series", {"name": title, "item": item, "xAxisIndex": 0,
                                                                   "yAxisIndex": 0, "yValue": 0, "mapState": STATE_LABEL})],
                                  tooltip=[comp("oh-chart-tooltip", {"show": True, "confine": True})])])
    band["config"]["visible"] = "=props.kind === 'state'"
    root = div([now, line, band], **{"padding": "8px 6px"})
    root["config"]["stylesheet"] = PERIOD_MENU  # the chart's period menu, out of the layout while closed
    return root


def param(name, label_, description, type_="TEXT", default=None, required=False):
    p = {"name": name, "label": label_, "description": description, "type": type_, "required": required}
    if default is not None:
        p["default"] = default
    return p


PREFIX = param("prefix", "Item prefix", "Name prefix of the plug's items: <prefix>_power, _switch, _energy_today, "
               "_energy_total, _voltage, _current, _power_factor, _apparent_power, _reactive_power", required=True)
COLOR = param("color", "Colour", "Device colour as #rrggbb", default="#8d6e63")
PLUG_PARAMS = [PREFIX, param("title", "Title", "Card title, the device's name where the card is not a plug",
                             default="Steckdose"),
               param("icon", "Icon", "Device icon, e.g. material:coffee", default="material:power"), COLOR,
               param("controllable", "Switchable", "Show the plug's switch", "BOOLEAN", default="true"),
               param("note", "Note", "Small print under the energies, hidden when empty"),
               dict(param("switch", "Switch item", "The switch's item where it is not <prefix>_switch, e.g. a "
                          "shared meter's"), context="item")]


_ITEMS = None


def known_items():
    """name: (label, type, state options as value=label pairs) of openHAB's items, from the JSONDB on homepi, else a
    REST export beside the script."""
    global _ITEMS
    if _ITEMS is None:
        _ITEMS = {}
        db, export = m.DB + "org.openhab.core.items.Item.json", os.path.join(HERE, "items_all.json")
        if os.access(db, os.R_OK):
            meta = m.json.load(open(m.DB + "org.openhab.core.items.Metadata.json"))
            options = {k.split(":", 1)[1]: v["value"].get("configuration", {}).get("options", "")
                       for k, v in meta.items() if k.startswith("stateDescription:")}
            _ITEMS = {k: (v["value"].get("label", k), v["value"]["itemType"], options.get(k, ""))
                      for k, v in m.json.load(open(db)).items()}
        elif os.path.exists(export):
            import json as _json
            _ITEMS = {i["name"]: (i.get("label", i["name"]), i["type"],
                                  ",".join(f"{o['value']}={o['label']}" for o in i.get("stateDescription", {}).get("options", [])))
                      for i in _json.load(open(export))}
    return _ITEMS


def item_kind(item):
    """How an item's popup shows its course: a line (number), a band of its states (state), or not at all (none)."""
    if item.startswith("zzpfx"):  # the plug cards' items are all measurements
        return "number", ""
    _, type_, options = known_items().get(item, (item, "", ""))
    if type_.startswith("Number") or type_ == "Dimmer":
        return ("state" if options else "number"), options
    if type_ in ("Switch", "Contact", "String"):
        return "state", options
    return "none", options


def overview_widget_props():
    """uid: {prop: item} the overview passes to each of its card widgets."""
    return {uid: {item_prop(i): i for i in items_in(card_)} for uid, card_ in overview_cards().items()}


ITEM_POPUP_PARAMS = [
    dict(param("item", "Item", "The item to show", required=True), context="item"),
    param("title", "Title", "Title of the popup, the tile's"),
    param("color", "Colour", "Colour of the course as #rrggbb", default=POPUP_COLOR),
    param("kind", "Kind", "number: its course as a line; state: a band of its states; none: only the value",
          default="number"),
    param("states", "State labels", "value=label pairs, comma-separated, for the band of states")]

VALUE_TILE_PARAMS = [
    param("title", "Title", "Title above the value", required=True),
    param("value", "Value", "The text to show, usually an expression on an item", required=True),
    param("icon", "Icon", "The pale icon, e.g. material:thermostat", default="material:info"),
    param("color", "Colour", "Colour of the value and the icon as #rrggbb; empty: the text colour"),
    param("iconColor", "Icon colour", "Colour of the icon where the value keeps the text colour, as #rrggbb"),
    dict(param("item", "Item", "The item whose popup a tap opens; empty: no tap"), context="item"),
    param("action", "Action", "popup: the item popup (widget item-popup); options: the item's command options",
          default="popup"),
    param("kind", "Kind", "What the item popup shows: number, state or none", default="number"),
    param("states", "State labels", "value=label pairs, comma-separated, for the item popup's band of states"),
    param("wrap", "Wrap", "A long text wraps across the whole row of the grid instead of being cut", "BOOLEAN"),
    param("fontSize", "Font size", "The tile's base size, e.g. 1.1em to grow with its card; default 14px")]

PILL_SLIDER_PARAMS = [
    dict(param("item", "Item", "The number item the slider sets", required=True), context="item"),
    param("color", "Colour", "Device colour as #rrggbb", default="#78909c"),
    param("min", "Minimum", "The slider's lowest value", "DECIMAL", default="0"),
    param("max", "Maximum", "The slider's highest value", "DECIMAL", default="100"),
    param("step", "Step", "The slider's step", "DECIMAL", default="1"),
    param("unit", "Unit", "Unit on the label while dragging and of the command sent; must be the item's own (a "
          "difference in K sent to a °C item is taken as an absolute temperature)"),
    param("title", "Title", "Title above the slider", required=True),
    param("icon", "Icon", "The badge's icon, e.g. material:thermostat", default="material:tune"),
    param("ring", "Timer ring", "A ring around a timer icon instead of the icon, emptying as the item runs down to 0",
          "BOOLEAN"),
    param("ringFull", "Full ring", "What a full timer ring stands for, e.g. an expression on the minutes the timer was "
          "last set to; empty: the maximum"),
    param("value", "Value", "The value to show, usually an expression on the item", required=True),
    param("valueColor", "Value colour", "Colour of the value where it is not the device colour; empty: the text colour"),
    param("context", "Context", "A line under the title saying what the setting does, usually an expression"),
    param("marks", "Marks", "value=label pairs below the bar, separated by semicolons, e.g. 0=0;60=1 h;120=2 h"),
    param("opacity", "Opacity", "e.g. 0.6 while the device is off"),
    param("row", "Row", "A row of a page's or popup's controls, with their divider", "BOOLEAN")]

SWITCH_ITEM = dict(param("item", "Item", "The switch item", required=True), context="item")
POWER_PILL_PARAMS = [SWITCH_ITEM,
                     param("color", "Colour", "Device colour as #rrggbb, of the pill while on", default="#78909c"),
                     param("onText", "Text while on", "What the pill says while on, e.g. An · Lüften; usually an "
                           "expression", default="An")]
BOOST_PILL_PARAMS = [SWITCH_ITEM, param("title", "Title", "Name of the boost", default="Boost"),
                     param("icon", "Icon", "Icon, e.g. material:rocket_launch; a classic openHAB icon follows the "
                           "item's state", default="material:bolt"),
                     param("color", "Colour", "Device colour as #rrggbb", default="#fb8c00"),
                     param("running", "Text while on", "The line under the title while the boost runs; usually an "
                           "expression", default="läuft")]
STATE_BAR_PARAMS = [
    dict(param("item", "Item", "The item whose states the segments send", required=True), context="item"),
    param("options", "Options", "value=label pairs separated by semicolons, e.g. 1=Niedrig;2=Mittel;3=Hoch",
          required=True),
    param("color", "Colour", "Colour of the current segment as #rrggbb; may be an expression", default="#78909c"),
    param("byText", "Sized by text", "Segments as wide as their labels instead of equal widths", "BOOLEAN"),
    param("flex", "Flex", "CSS flex of the bar in a row, e.g. 1 1 240px"),
    param("width", "Width", "CSS width of the bar", default="100%")]
SWITCH_TILE_PARAMS = [SWITCH_ITEM, param("title", "Title", "Name of the plug or device", required=True),
                      param("icon", "Icon", "Icon, e.g. material:coffee (its state follows the item)"),
                      param("color", "Colour", "Colour of the tile while on as #rrggbb", default="#78909c"),
                      param("value", "Value", "A line under the name, e.g. the power; usually an expression"),
                      param("energy", "Second value", "A line under the value, e.g. today's energy; usually an "
                            "expression; empty: none")]
SWITCH_ROW_PARAMS = [
    dict(param("item", "Item", "The switch item", required=True), context="item"),
    param("title", "Title", "Name of the switch", required=True),
    param("icon", "Icon", "The icon, e.g. material:eco", default="material:power_settings_new"),
    param("color", "Colour", "The card's colour as #rrggbb, of the switch while on", default="#78909c")]

PILL_SWITCH_PARAMS = [
    dict(param("item", "Item", "The switch item", required=True), context="item"),
    param("title", "Title", "Name of the switch, in the pill", required=True),
    param("icon", "Icon", "Icon on the knob, of what it switches, e.g. material:shower",
          default="material:power_settings_new"),
    param("color", "Colour", "The card's colour as #rrggbb, of the pill while on", default="#78909c")]

FLOW_POWER = param("power", "Power", "The power in W; usually an expression on an item", required=True)
FLOW_LINK_PARAMS = [
    *[param(k, k, f"{'Start' if k[1] == '1' else 'End'} point's {k[0]} in the flow's viewBox", "DECIMAL", required=True)
      for k in ("x1", "y1", "x2", "y2")],
    param("color", "Colour", "The link's colour as #rrggbb; may be an expression", default="#78909c"), FLOW_POWER,
    param("forward", "Forward", "The dots run from (x1, y1) to (x2, y2) while it holds, else back; usually an "
          "expression", "BOOLEAN"),
    param("threshold", "Threshold", "The power in W above which the dots run", "DECIMAL", default="10")]
FLOW_NODE_PARAMS = [
    dict(param("kind", "Kind", "The device drawn", required=True), limitToOptions=True,
         options=[{"value": k, "label": k} for k in FLOW_KINDS]),
    param("x", "x", "Centre's x in the flow's viewBox", "DECIMAL", required=True),
    param("y", "y", "Centre's y in the flow's viewBox", "DECIMAL", required=True),
    dict(FLOW_POWER, required=False),
    param("soc", "State of charge", "The battery's state of charge in %; usually an expression", "DECIMAL"),
    param("frequency", "Compressor frequency", "The heat pump's compressor frequency in Hz, which turns its fan; "
          "usually an expression", "DECIMAL")]
FLOW_SHARE_RING_PARAMS = [
    param("x", "x", "Centre's x in the flow's viewBox", "DECIMAL", required=True),
    param("y", "y", "Centre's y in the flow's viewBox", "DECIMAL", required=True),
    param("title", "Title", "Text beside the ring, e.g. Eigenverbrauch", required=True),
    param("part", "Part", "The part, e.g. today's PV energy used at home; usually an expression", required=True),
    param("whole", "Whole", "The whole, e.g. today's PV energy; usually an expression", required=True)]
WEATHER_ICON_PARAMS = [
    param("symbol", "Symbol", "The weather drawn: " + ", ".join(k for k, _ in WX_SYMBOLS) + "; usually an "
          "expression", required=True),
    param("day", "Day", "Whether the sun is up; false draws the moon; usually an expression", "BOOLEAN",
          default="true"),
    param("size", "Size", "Width and height in px", "INTEGER", default="36")]
APPLIANCE_KIND = dict(param("kind", "Kind", "The appliance drawn", required=True), limitToOptions=True,
                      options=[{"value": k, "label": k} for k, _ in APPLIANCE_FRONTS])
APPLIANCE_ICON_PARAMS = [
    APPLIANCE_KIND,
    param("running", "Running", "Whether it runs; usually an expression", "BOOLEAN"),
    param("progress", "Progress", "Program progress in %, filling the ring while it runs; empty: the ring pulses",
          "DECIMAL"),
    param("color", "Colour", "Colour of the ring as #rrggbb", default="#1e88e5"),
    param("size", "Size", "Width and height in px", "INTEGER", default="72")]
APPLIANCE_TILE_PARAMS = [
    APPLIANCE_KIND, param("title", "Title", "The appliance's name", required=True),
    param("popup", "Popup", "The uid of the page a tap opens as a popup", required=True),
    *[dict(param(key, key[:1].upper() + key[1:], f"Miele item {suffix}, e.g. "
                 f"miele_washing_machine{suffix}; set for a Miele machine"), context="item")
      for key, suffix in APPLIANCE_TILE_ITEMS.items()],
    dict(param("power", "Power item", "The plug's power item, for a machine without program data"), context="item"),
    dict(param("done", "Finished item", "Switch item that is on while the plug machine is finished"), context="item")]


def widgets():
    """uid: (card, props parameters, tags) of every generated widget."""
    ph = PLUG_PLACEHOLDERS
    plug = {"plug-card": (plug_now_card(ph["prefix"], ph["icon"], ph["color"], ph["title"], ph["note"], ph["switch"]),
                          PLUG_PARAMS),
            "plug-power-card": (plug_power_card(ph["prefix"], ph["color"]), [PREFIX, COLOR]),
            "plug-energy-days-card": (plug_days_card(ph["prefix"], ph["color"]), [PREFIX, COLOR]),
            "plug-electric-card": (plug_electric_card(ph["prefix"], ph["title"]),
                                   [PREFIX, param("title", "Title", "Card title", default="Elektrisch")])}
    out = {}
    names = known_items()
    for uid, card_ in overview_cards().items():
        # the overview's charts start below their period buttons too, as the pages' do
        card_ = plots_below_controls(card_)
        props = {i: item_prop(i) for i in items_in(card_)}
        assert len(set(props.values())) == len(props), f"{uid}: two items share a prop name"
        params = [dict(param(p, names.get(i, (p, ""))[0], f"{names.get(i, ('', 'Item'))[1]} item", required=True),
                       context="item") for i, p in props.items()]
        out[uid] = (itemized(card_, props), params, ["overview"])
    for uid, (card_, params) in plug.items():
        # the plug cards stand on the device pages, whose charts start below their period buttons
        out[uid] = (templated(plots_below_controls(card_)), params, ["plug"])
    out["item-popup"] = (templated(plots_below_controls(item_popup())), ITEM_POPUP_PARAMS, ["popup"])
    out["value-tile"] = (value_tile_widget(), VALUE_TILE_PARAMS, ["tile"])
    out["pill-slider"] = (pill_slider_widget(), PILL_SLIDER_PARAMS, ["slider"])
    out["switch-row"] = (switch_row_widget(), SWITCH_ROW_PARAMS, ["switch"])
    out["power-pill"] = (power_pill_widget(), POWER_PILL_PARAMS, ["switch"])
    out["boost-pill"] = (boost_pill_widget(), BOOST_PILL_PARAMS, ["switch"])
    out["state-bar"] = (state_bar_widget(), STATE_BAR_PARAMS, ["controls"])
    out["switch-tile"] = (switch_tile_widget(), SWITCH_TILE_PARAMS, ["switch"])
    out["flow-link"] = (flow_link_widget(), FLOW_LINK_PARAMS, ["flow"])
    out["flow-node"] = (flow_node_widget(), FLOW_NODE_PARAMS, ["flow"])
    out["flow-share-ring"] = (share_ring_widget(), FLOW_SHARE_RING_PARAMS, ["flow"])
    out["appliance-icon"] = (appliance_icon_widget(), APPLIANCE_ICON_PARAMS, ["appliance"])
    out["appliance-tile"] = (appliance_tile_widget(), APPLIANCE_TILE_PARAMS, ["appliance"])
    out["weather-icon"] = (weather_icon_widget(), WEATHER_ICON_PARAMS, ["weather"])
    for uid, (tree, props) in ROLE_WIDGETS.items():
        params = [dict(param(p, names.get(i, (p, ""))[0], f"{names.get(i, ('', 'Item'))[1]} item", required=True),
                       context="item") for i, p in props.items()]
        out[uid] = (itemized(tree, props), params, ["controls"])
    out["pill-switch"] = (pill_switch_widget(), PILL_SWITCH_PARAMS, ["switch"])
    for uid, (card_, _, _) in out.items():
        assert not has_placeholder(str(card_)) and "1, 2, 3" not in str(card_), uid
        # references to other widgets carry names such as heatpump-quick, which a group item may share, and the pages
        # a tap opens and the energy flow's node kinds are named after their device, as its group item is (weather,
        # heatpump, ventilation)
        text = re.sub(r'"(widget:[a-z0-9-]+|page:[a-z0-9_]+)"', '""', m.json.dumps(card_))
        text = re.sub(r'"(popup|kind)": "[a-z0-9_-]+"', '""', text)  # a node's kind is an option, not an item
        text = re.sub(r"props\.kind === '[a-z-]+'|\{\"value\": \"[a-z-]+\", \"label\": \"[a-z-]+\"\}", "", text)
        left = [n for n in names if re.search(r"(?<![A-Za-z0-9_])" + re.escape(n) + r"(?![A-Za-z0-9_])", text)]
        assert not left, f"{uid} still names items: {left[:5]}"
    return out


def widget_entries(now):
    entries = {}
    for uid, (card_, params, tags) in widgets().items():
        tree = copy.deepcopy(card_)
        germanize(tree, MISSING_DE)
        entries[uid] = {"class": "org.openhab.core.ui.components.RootUIComponent",
                        "value": {"uid": uid, "tags": ["generated", *tags],
                                  "props": {"parameters": params, "parameterGroups": []},
                                  "timestamp": timestamp(now), "component": tree["component"], "config": tree["config"],
                                  "slots": tree.get("slots", {})}}
    return entries


def migrate_widgets(d):
    """The generated widgets replace the ones generated before; widgets made in the UI stay."""
    d = {uid: w for uid, w in d.items() if "generated" not in w["value"].get("tags", [])}
    for uid, entry in widget_entries(datetime.datetime.now()).items():
        d = m.insert(d, uid, entry)
    return d


# ---------------------------------------------------------------- JSONDB edits

# pages that no longer exist, removed on every update
OBSOLETE_PAGES = ["dashboard",  # became the overview page
                  "flow_water_meter",  # the water meter left the energy flow
                  "proposals",  # control variants, decided
                  "widget_gallery",  # the widget repository's screenshots, put up by widget_gallery.py while they are taken
                  "dashboard_smart_meter", "dashboard_battery", "dashboard_hot_water", "dashboard_pv", "dashboard_home",
                  "dashboard_power_meter", "dashboard_energy_storage", "dashboard_pv_days", "dashboard_energy_days",
                  "dashboard_outdoor", "dashboard_indoor", "dashboard_heatpump_dhw",
                  # popups of their own, replaced by the device pages they now open
                  "flow_photovoltaics", "flow_power_meter", "flow_heatpump", "flow_air_conditioning",
                  "flow_energy_storage", "flow_e_car", "hp_outdoor_unit", "hp_indoor_unit", "hp_valve", "hp_dhw_tank",
                  "hp_space_heating", "appliance_washing_machine_1", "appliance_washing_machine_2",
                  "appliance_tumble_dryer", "appliance_dishwasher", "forecast"]
def migrate_pages(d):
    now = datetime.datetime.now()
    if not sys.argv[1].startswith("update"):
        assert PAGE_UID not in d
    d = m.insert(d, PAGE_UID, page(now))
    for uid in OBSOLETE_PAGES:
        d.pop(uid, None)
    for uid, (title, blocks) in FLOW_POPUPS.items():
        config = {"label": title, "sidebar": False, "style": WIDE_POPUP_MARK, "stylesheet": WIDE_POPUP}
        d = m.insert(d, uid, layout_page(uid, config, plots_below_controls(blocks()), now))
    for uid, blocks in DEVICE_PAGES.items():  # the device pages, label, icon and sidebar order kept
        old = d[uid]["value"]["config"] if uid in d else NEW_PAGES[uid]
        config = {"label": old["label"], "icon": old.get("icon"), "order": old.get("order"), "sidebar": True,
                  "style": WIDE_POPUP_MARK, "stylesheet": WIDE_POPUP}
        d = m.insert(d, uid, layout_page(uid, config, blocks(), now))
    # the home page shows the overview alone: with all three model tabs hidden MainUI drops the tab bar
    d["home"]["value"]["config"]["hiddenModelTabs"] = ["locations", "equipment", "properties"]
    return d


def migrate_items(d):
    for item, lbl, _ in DAILY:
        assert item not in d, item
        d = m.insert(d, item, {"class": "org.openhab.core.items.ManagedItemProvider$PersistedItem",
                               "value": {"groupNames": [], "itemType": "Number:Energy", "tags": [],
                                         "label": lbl, "category": "energy"}})
    return d


def migrate_metadata(d):
    for item, *_ in DAILY:
        for ns, value, cfg in (("unit", "kWh", {}), ("stateDescription", " ", {"pattern": "%.2f %unit%"})):
            key = f"{ns}:{item}"
            assert key not in d, key
            d = m.insert(d, key, {"class": "org.openhab.core.items.Metadata",
                                  "value": {"key": {"segments": [ns, item], "uid": key}, "value": value,
                                            "configuration": dict(cfg)}})
    return d


def migrate_rules(d):
    assert RULE_UID not in d
    return m.insert(d, RULE_UID, {
        "class": "org.openhab.core.automation.dto.RuleDTO",
        "value": {
            "triggers": [
                {"id": "1", "configuration": {"cronExpression": "0 0/5 * * * ? *"}, "type": "timer.GenericCronTrigger"},
                {"id": "2", "configuration": {"cronExpression": "50 59 23 * * ? *"}, "type": "timer.GenericCronTrigger"},
            ],
            "conditions": [],
            "actions": [{"inputs": {}, "id": "3",
                         "configuration": {"script": RULE_SCRIPT, "type": "application/javascript"},
                         "type": "script.ScriptAction"}],
            "configuration": {},
            "configDescriptions": [],
            "templateState": "no-template",
            "uid": RULE_UID,
            "name": "Energy Daily Totals",
            "tags": [],
            "visibility": "VISIBLE",
            "description": "Keeps one point per day for PV yield, home consumption, grid import and grid export, for charts over weeks and years.",
        },
    })


FILES = {
    "uicomponents_ui_page.json": migrate_pages,
    "org.openhab.core.items.Item.json": migrate_items,
    "org.openhab.core.items.Metadata.json": migrate_metadata,
    "automation_rules.json": migrate_rules,
}


def main():
    results = {}
    files = ({"uicomponents_ui_widget.json": migrate_widgets, "uicomponents_ui_page.json": migrate_pages}
             if sys.argv[1].startswith("update") else FILES)
    for name, fn in files.items():
        data, enc = m.detect(m.DB + name)
        results[name] = m.encode(fn(data), *enc)
        print(f"{name}: encoder html={enc[0]} newline={enc[1]} ok")
    if TILE_ICON_DEFAULTS:
        print("value tiles with the default icon:", ", ".join(sorted(TILE_ICON_DEFAULTS)))
    if sys.argv[1] not in ("apply", "update-apply"):
        return
    for name, text in results.items():
        with open(m.DB + name, "w", encoding="utf-8") as f:
            f.write(text)
    print("written")


main()
