import os, re, textwrap
import yaml
EXPORT = os.environ.get("EXPORT", "export")
W = {f[:-4]: yaml.safe_load(open(os.path.join(EXPORT, f))) for f in os.listdir(EXPORT) if f.endswith(".yml")}

OVERVIEW = [
    ("weather-card", "Weather", "A slim bar across the top: the present weather drawn in the style of the energy "
     "flow (`weather-icon`: sun or moon, clear, behind one or two clouds or veil streaks, clouds with rain, snow, a "
     "bolt or fog, the sun peeking out for showers, gently "
     "animated), the outdoor temperature from a local sensor, and today and the next two days, each with its weather "
     "drawn beside its maximum over its minimum. While an official warning of GeoSphere Austria is in effect or begins within 24 hours, it is teased "
     "beside the temperature: a disc in its level's colour (yellow, orange, red) with an exclamation mark and a ring "
     "pulsing out of it, on a wider screen in a pill with the warning's short text (*Gewitter bis 20:00*). On a "
     "phone the gaps narrow, and below 380 px the chevron goes, so the bar keeps its fit. A tap opens the weather page of "
     "my installation as a popup (see [Weather](#weather)). Its items come from two rules, "
     "`scripts/openhab-ui/applied/weather_forecast_rule.js`, which reads Open-Meteo's GeoSphere AROME Austria model, "
     "and `weather_warnings_rule.js`, which reads GeoSphere Austria's warnings and sends a broadcast notification "
     "when their level rises to orange or red."),
    ("energy-flow-card", "Energy flow", "A regular star around the house: PV, heat pump, air conditioner, E-Car, the "
     "household appliances together, ventilation, battery and grid, each with its power and today's energy. Every node "
     "is one grey ring around its drawing, the ring carrying what the node shows beyond it. Dots run "
     "along the lines in the direction of the flow at four speeds and slide under the node rims; while power flows "
     "through a node, its ring pulses in its colour. The icons move with the power (sun rays, air streams, pylon dashes, a pulsing bolt over the "
     "charging car, sparkles twinkling while the appliances run, the battery filled to its state of charge, the "
     "ventilation unit's fan turning and its air arrows flowing, fresh air in and used air out), the heat pump's fan "
     "with its compressor: while only its electric heaters run it stands and the energy only flows. Badges just "
     "outside the rings tell what the heat pump does (space heating, hot water, defrost, a red bolt while only its "
     "electric heaters run), whether the air conditioner is on and the ventilation's level; a badge is filled in its "
     "colour while its device works and grey otherwise. A running timer covers its device's ring with an arc, "
     "full at what it was last set to, and the battery's ring is filled with its state of charge; beside such an arc "
     "the rest of the ring pulses softly, never as strong as the arc. A tap on "
     "the heat pump, the air conditioner or the ventilation opens its quick popup (see [Quick popups](#quick-popups)). "
     "Under the star three tiles with large pale icons, the house's power and today's self-consumption and "
     "self-sufficiency as rings. The card places its lines, nodes and rings as `flow-link`, `flow-node` and "
     "`flow-share-ring`. The recording and the dark screenshot show it with demo values."),
    ("switches-card", "Switches", "The switchable plugs under the energy flow as `switch-tile`s, five abreast, three "
     "on a phone: icon, *An* or *Aus*, name, power and today's energy; a tap anywhere switches, and while on a tile is "
     "tinted and outlined in its colour."),
    ("appliances-card", "Appliances", "Washing machines, dryer and dishwasher as `appliance-tile`s, each drawn inside a "
     "ring filled with the program progress, the rest of it pulsing; drums and paddles turn and the spray arm sprays "
     "while they run, with a pill for the remaining time; a machine without progress pulses its whole ring."),
    ("heating-card", "Heating and hot water", "Two tiles in the appliances' style, the DHW tank and the heat pump: "
     "the tank drawn as in the heat pump card, its water in three layers (the top in its temperature's colour) with "
     "the Effect Heater beside it, lit while it heats, its ring filled by its temperature and a badge for where its "
     "heat comes from (the booster heater's red bolt, else the heat pump while the compressor charges the tank); the "
     "heat pump as the energy flow's node with the same mode badge, its ring filled by the compressor's frequency. "
     "Each tile's pill holds the temperature, the tank's and the leaving water's, filled in the tile's colour while "
     "hot water or heating is switched on, outlined while off; a tap opens the heat pump's quick popup. Below them "
     "today's electricity and heat of the heat pump split into space heating, DHW and standby as bars (hovering a "
     "part lifts it everywhere), and today's COPs of space heating, DHW and in total as rings like the energy flow's "
     "self-consumption. The screenshots show it with the heat pump card's demo values."),
    ("electricity-price-card", "Electricity price", "The all-in price, the cheapest and priciest hour, and the prices "
     "12 hours back and 36 hours ahead, coloured green, orange and red by price."),
    ("heatpump-card", "Heat pump", "A section through the house: the outdoor unit on the roof (the energy flow's "
     "`flow-node`), wall unit, three-way valve, DHW tank (in layers, the Effect Heater beside it) and radiators in "
     "the basement, floor heating on the two levels above. Every device is one grey ring like the energy flow's "
     "nodes, pulsing while it works, softly beside the arc that shows its value; the outdoor unit's fan turns while the compressor runs and its ring is filled by the compressor's "
     "frequency, the wall unit's by its own draw, the measured circuit (full and red while the backup heater runs; "
     "the tank's booster heater does not count), the tank's by its temperature, radiators and floor loops by the "
     "leaving water while they carry it. Dots run along the pipes, as many as a pipe is long, faster with the water's flow or the compressor's "
     "frequency, and all of them backwards during a defrost. The valve shows its position in its icon. Badges just "
     "outside three rings say what the outdoor unit's ring shows (*Hz*) and the wall unit's (a bolt, red while the "
     "backup heater runs) and where the tank's heat comes from; grey while their device rests. Tiles in the "
     "style of the switch tiles hold the figures: the outdoor unit, the control (heating, hot water, Smart Grid, "
     "automation), the refrigerant, the heating circuit, the climate of the two floors, the tank with its booster "
     "heater and the indoor unit with its own power (the measured circuit plus the backup heater), each tinted in its "
     "colour while what it shows is at work. A tap on a tile, the wall unit or the outdoor unit "
     "opens its quick popup with charts or controls. Above the drawing the electrical power, the heat and the COP as "
     "a row of value tiles that open popups with their charts of the day and the month (today's split and COPs are "
     "in the heating card). On a phone the drawing takes the card's width; on a wider screen it stands at most at "
     "its own size, as the energy flow does, so their texts keep the UI's sizes and their rings come out the same, "
     "and in the middle of the height its row gives the card. The recording and the dark screenshot show it with demo values (a space "
     "heating run)."),
    ("consumption-card", "Consumption today", "Today's consumption as one bar split by source (PV, grid) and by "
     "consumer, with a legend in two columns; hovering a part lifts it everywhere. The screenshot shows it with demo "
     "values."),
    ("energy-days-card", "Energy per day", "The month's daily home consumption as stacked bars: from PV and from the "
     "grid, with PV production beside it."),
    ("pv-days-card", "PV production per day", "The daily PV yield of a year in four views a bar switches: a "
     "calendar heatmap of the year, two half-years, twelve month calendars and the months' sums as bars; a wider "
     "screen gets the year, the month calendars and the bars, a phone the half-years instead of the year."),
    ("temperatures-card", "Temperatures", "Indoor and outdoor temperature now, the day's minimum and maximum, and the "
     "last day as a chart from 15-minute means."),
]
PLUG = [("plug-card", "Now: power, on/off pill, energy today and total"), ("plug-power-card", "Power over the day"),
        ("plug-energy-days-card", "Energy per day of the month"), ("plug-electric-card", "Voltage, current, power factor, "
                                                                                      "apparent and reactive power")]
QUICK = [  # uid, title, what it holds; the first three open from the energy flow, the rest from the heat pump card
    ("heatpump-quick", "Heat pump", "the hot-water boost, the Smart Grid, heating, hot water and automation, the "
     "DHW setpoint"),
    ("air-conditioner-quick", "Air conditioner", "on/off, mode, fan, setpoint, timer and boost"),
    ("ventilation-quick", "Ventilation", "the level, the timer and the automation"),
    ("heatpump-control-quick", "Control", "heating, hot water and automation, the hot-water boost and the Smart Grid"),
    ("heatpump-indoor-quick", "Indoor unit", "all the heat pump's controls"),
    ("heatpump-outdoor-quick", "Outdoor unit", "its power with the compressor frequency and the outdoor temperature "
     "against its heat exchanger's over the day"),
    ("heatpump-refrigerant-quick", "Refrigerant", "hot gas with its target, liquid, heat exchanger and pressure over "
     "the day"),
    ("heatpump-circuit-quick", "Heating circuit", "the leaving water offset, leaving and inlet water with the heat over "
     "the day"),
    ("upper-floor-quick", "Upper floor", "temperature and humidity over the day"),
    ("ground-floor-quick", "Ground floor", "temperature, humidity and CO₂ over the day"),
    ("heatpump-electric-quick", "Electricity", "the power of space heating, DHW and standby over the day, their energy "
     "per day of the month"),
    ("heatpump-heat-quick", "Heat", "the heat of space heating and DHW over the day, per day of the month"),
    ("heatpump-cop-quick", "COP", "the COP against the outdoor temperature over the day, the daily COPs of the month")]

def fill(text, indent=""):
    """A paragraph wrapped at 120 characters."""
    return textwrap.fill(" ".join(text.split()), 120, subsequent_indent=indent, break_long_words=False,
                         break_on_hyphens=False)


def code(text):
    """Backticks around the placeholders GitHub would read as HTML tags."""
    return text.replace("<prefix>_switch", "`<prefix>_switch`").replace("<prefix>_power", "`<prefix>_power`")


def table(uid):
    params = W[uid]["props"]["parameters"]
    if all(p.get("context") == "item" and p["description"].endswith(" item") for p in params):
        rows = ["| Prop | Item | Item type |", "|---|---|---|"]
        rows += [f"| `{p['name']}` | {p['label']} | {p['description'][:-5]} |" for p in params]
    else:
        rows = ["| Prop | Description | Type | Default |", "|---|---|---|---|"]
        for p in params:
            default = f"`{p['default']}`" if "default" in p else ""
            kind = "Item" if p.get("context") == "item" else p["type"]
            rows.append(f"| `{p['name']}` | {code(p['description'])} | {kind} | {default} |")
    return "\n".join(rows)


def placed(tree):
    """The widgets a widget places itself."""
    return set(re.findall(r"widget:([a-z0-9-]+)", yaml.safe_dump(tree)))


def needs(uid, seen=None):
    """Every widget of this repository a widget needs, through the widgets it places too."""
    seen = set() if seen is None else seen
    for other in sorted(placed(W[uid]) - seen):
        if other in W:
            seen.add(other)
            needs(other, seen)
    return seen


def section(title, uid, text, example=None, shot=None, props=True):
    """A widget's section: text, an example, its screenshot and its props."""
    parts = [f"### {title}: `{uid}`\n\n{fill(text)}"]
    if shot:
        parts.append(shot)
    if example:
        parts.append(f"```yaml\n{example.strip()}\n```")
    deps = needs(uid)
    if deps:
        parts.append("Needs " + ", ".join(f"`{d}`" for d in sorted(deps)) + ".")
    if props:
        parts.append(table(uid))
    return "\n\n".join(parts) + "\n"


def details(uid):
    n = len(W[uid]["props"]["parameters"])
    return f"<details>\n<summary>{n} props</summary>\n\n{table(uid)}\n\n</details>"


def img(name, alt):
    return f"![{alt}](screenshots/{name})"


def quick_popups():
    """The quick popups: what each holds, their screenshots three abreast and their props."""
    rows = ["""## Quick popups

Compact popups the cards open: a device's main controls or the charts of one of its parts, under a small head with
its state and above *Alle Details*, which opens the device's page of my installation. Each is a widget that takes its
items as props; open it from a link with `action: popup`, `actionModal: widget:<uid>` and its items in
`actionModalConfig`, as the cards do:

```yaml
action: popup
actionModal: widget:ventilation-quick
actionModalConfig:
  ventilationLevel: esplyfterl_level
  netatmoWeatherstationCo2: netatmo_weatherstation_co2
  ventilationTimer: ventilation_timer
  ventilationManagement: ventilation_management
```

It opens 420 px wide and up to 660 px high, on a phone full screen; its charts start below their period buttons, a
closed period menu takes no room. The energy flow's heat pump, air conditioner and ventilation open the first three
(the heating card's tiles open the heat pump's too), the heat pump card's tiles, wall unit and outdoor unit the others:
"""]
    rows += [fill(f"- `{u}`, {t.lower() if t != 'COP' else t}: {w}.", "  ") for u, t, w in QUICK]
    rows += ["", "| | | |", "|---|---|---|"]
    for i in range(0, len(QUICK), 3):
        group = QUICK[i:i + 3] + [None] * (3 - len(QUICK[i:i + 3]))
        rows.append("| " + " | ".join(img(f"{q[0]}.png", q[1]) if q else "" for q in group) + " |")
    rows.append("")
    for u, _, _ in QUICK:
        deps = needs(u)
        if deps:
            rows += [f"`{u}` needs " + ", ".join(f"`{d}`" for d in sorted(deps)) + ".", ""]
        rows += [details(u).replace("<summary>", f"<summary><code>{u}</code>: "), ""]
    return "\n".join(rows)


md = ["""# openHAB Widgets

MainUI widgets from my openHAB 5 installation: the cards of an energy and home dashboard and the parts they are built
from, which work on their own too: the quick popups they open, pills, bars and sliders, the nodes and lines of the
energy flow, appliance icons and tiles, a weather drawing; besides them a set of cards for every metered plug, a popup
for any item and the tile their values stand in. The UI texts are German, numbers use a decimal comma. No widget names
an item: every item comes in as a prop, so the widgets work with any item names.

![Overview](screenshots/overview-light.png)

| Dark mode | Phone |
|---|---|
| ![Overview in dark mode](screenshots/overview-dark.png) | ![Overview on a phone](screenshots/overview-phone.png) |

## Installing a widget

In MainUI open *Developer Tools → Widgets*, create a widget and replace its code with the content of a `.yml` file from
this repository. Use it on a layout page as a component `widget:<uid>` with its props, for example:

```yaml
- component: widget:plug-card
  config:
    prefix: coffee_machine
    title: Kaffeemaschine
    icon: material:coffee
    color: "#8d6e63"
```

Many widgets place other widgets of this repository; install those too, under the same uids. Every section below
names the widgets one needs, directly or through the widgets it places.

The widgets rely on MainUI of openHAB 5 (SVG and CSS in card content, `:has()` for hover highlights, `color-mix()`,
aggregate chart series, `oh-context` variables). Values are shown through the items' state descriptions, so units and
number formats come from the items.

| Widget | Needs |
|---|---|
"""]
for uid in sorted(W):
    deps = needs(uid)
    md[-1] += f"| `{uid}` | {', '.join(f'`{d}`' for d in sorted(deps)) if deps else '–'} |\n"

md.append("""## Dashboard cards

The cards of my overview page. Each takes the items it shows as props; the prop names say what an item is. Most
elements open a page of my installation as a popup when tapped: the page of their device (`page:heatpump`,
`page:weather` …), or for the energy flow's house and appliances a popup of its own (`page:flow_home`,
`page:flow_appliances`). The pages are not part of this repository; the quick popups the energy flow's heat pump, air
conditioner and ventilation and the heat pump card's tiles open are (see [Quick popups](#quick-popups)).
""")
for uid, title, what in OVERVIEW:
    shots = []
    for name, alt in ((f"{uid}.gif", title), (f"{uid}.png", title), (f"{uid}-dark.png", f"{title} in dark mode")):
        if os.path.exists(os.path.join(EXPORT, "screenshots", name)):
            shots.append(img(name, alt))
    deps = needs(uid)
    need = ("\n\n" + fill("Needs " + ", ".join(f"`{d}`" for d in sorted(deps)) + ".")) if deps else ""
    md.append(f"### {title}: `{uid}`\n\n{fill(what)}{need}\n\n" + "\n\n".join(shots) + f"\n\n{details(uid)}\n")

md.append(quick_popups() + "\n")
md.append("""## Controls

The parts of the quick popups and of my device pages' controls.

""")
md.append(section("Segmented bar", "state-bar", """The states of one item as the segments of a bar, the current one
filled in the colour; a tap sends a segment's state. `options` holds `value=label` pairs separated by semicolons.
With `byText` the segments are as wide as their labels, so a long one such as *Entfeuchten* fits on a phone;
Framework7's sliding highlight is sized for equal segments and is hidden then. `color` may be an expression, e.g. grey
while the device is off.""", """
component: widget:state-bar
config:
  item: esplyfterl_level
  options: 1=1;2=2;3=3
  color: "#26a69a"
""", img("state-bars.png", "Segmented bars")))
md.append(section("Switch tile", "switch-tile", """A plug or device as a small tile: its icon, *An* or *Aus*, the name
and a value such as its power; a tap anywhere switches it. While on it is tinted and outlined in its colour. Put
several in a grid, e.g. `grid-template-columns: repeat(auto-fill, minmax(120px, 1fr))`.""", """
component: widget:switch-tile
config:
  item: coffee_machine_switch
  title: Kaffeemaschine
  icon: material:coffee
  color: "#8d6e63"
  value: =Math.round(Number(items.coffee_machine_power.numericState) || 0) + ' W'
""", img("switch-tiles.png", "Switch tiles")))
md.append(section("On/off pill", "power-pill", """A device's on and off as a wide pill: a white knob with the power
symbol slides to the right and the pill fills with the device colour while on, with `onText` in it (an expression,
e.g. the mode it runs in); a tap anywhere switches. The plug cards and the device pages switch with it.""", """
component: widget:power-pill
config:
  item: faikout_perfera_switch
  color: "#29b6f6"
  onText: ="An · " + items.faikout_perfera_mode.displayState
""", img("power-pill.png", "On/off pill")))
md.append(section("Boost pill", "boost-pill", """A boost that runs for a while, as a pill: its icon in a tinted circle,
the name, what it does while it runs (`running`, an expression) or *Aus*, and *Starten* or *Stoppen*; while it runs
the pill fills with a gradient of the device colour and rings pulse from the icon. A tap anywhere switches the item.
My heat pump's hot-water boost and my air conditioner's boost both carry a rocket.""", """
component: widget:boost-pill
config:
  item: pyaltherma_dhw_powerful
  title: Warmwasser-Boost
  icon: material:rocket_launch
  color: "#fb8c00"
  running: ="läuft · Speicher " + items.espaltherma_dhw_tank_temp.displayState
""", img("boost-pills.png", "Boost pills")))
md.append("""### Slider: `pill-slider`

A setting as a wide pill slider in the device colour, for setpoints, offsets, powers and timers: a gradient fills the
bar up to the value, the white knob stays inside the bar at both ends, and the value is sent once on release. Only the
knob can be dragged, so scrolling across a slider on a phone leaves it alone. Above the
bar an icon in a tinted circle (for a timer, `ring: true`, a ring around a timer icon that empties as the item runs
down to 0, full at `ringFull`, e.g. the minutes it was last set to, or at `max`), the title with a line of context and the value large on the right; `marks` puts labels below the bar.
`value` and `context` are expressions, evaluated where the slider is placed. The slider is only built once the item
has a numeric state, because MainUI's slider starts at its minimum and a touch ending on it sends its value.

```yaml
component: widget:pill-slider
config:
  item: faikout_perfera_temperature_setpoint
  color: "#29b6f6"
  min: 18
  max: 30
  step: 0.5
  unit: °C
  title: Soll
  icon: material:device_thermostat
  value: =items.faikout_perfera_temperature_setpoint.displayState
  context: ="Raum " + items.faikout_perfera_temperature.displayState
  marks: 18=18 °C;22=22;26=26;30=30 °C
```

![Sliders](screenshots/pill-sliders.png)

""" + table("pill-slider") + "\n")
md.append("""### Switch pill: `pill-switch`

A switch for switches that stand side by side: a pill 34 px high in which a white knob with the icon of what it
switches (`icon`; the power symbol without one) slides to the right while the pill fills with the card's colour, the
name in the part the knob leaves free. Every pill has the same sizes and 12 px text. Put several in a grid that places
as many as fit, e.g. `grid-template-columns: repeat(auto-fit, minmax(120px, 1fr))`, which holds a name such as
*Warmwasser* and lets three pills stand abreast where there is room and two and one on a phone. A tap anywhere on the
pill switches the item.

```yaml
component: widget:pill-switch
config:
  item: pyaltherma_climate_control_power
  title: Heizung
  icon: material:local_fire_department
  color: "#fb8c00"
```

![Switch pills](screenshots/pill-switches.png)

""" + table("pill-switch") + "\n")
md.append("""### Switch row: `switch-row`

A switch in a list of switches: its icon in a circle tinted in the card's colour while on, the name, *An* or *Aus*, and
a switch drawn in the card's colour, a track that fills while on and a white knob that slides over. A tap anywhere
on the row switches the item.

```yaml
component: widget:switch-row
config:
  item: faikout_perfera_eco_mode
  title: Eco
  icon: material:eco
  color: "#29b6f6"
```

![Switch rows](screenshots/switch-rows.png)

""" + table("switch-row") + "\n")
md.append("""## Energy flow

The energy flow card's lines, nodes and rings, for a flow of your own. They draw SVG, so place them in an `svg`
component, in its `viewBox` coordinates: every node is a circle of radius 30 around `x`, `y`, a line runs best from
rim to rim. Place the lines first, so the nodes cover their ends and the dots slide in under the rims. Powers are
expressions in W, evaluated where the widget stands:

```yaml
component: svg
config:
  viewBox: 0 0 440 110
  width: 100%
slots:
  default:
    - component: widget:flow-link
      config: { x1: 80, y1: 45, x2: 190, y2: 45, color: "#ffb300", forward: true,
                power: "=Number(items.huawei_inverter_input_power.numericState) || 0" }
    - component: widget:flow-link
      config: { x1: 250, y1: 45, x2: 360, y2: 45, color: "#26a69a", forward: true, threshold: 100,
                power: "=Number(items.e_car_power.numericState) || 0" }
    - component: widget:flow-node
      config: { kind: pv, x: 50, y: 45, power: "=Number(items.huawei_inverter_input_power.numericState) || 0" }
    - component: widget:flow-node
      config: { kind: home, x: 220, y: 45, power: "=Number(items.home_active_power.numericState) || 0" }
    - component: widget:flow-node
      config: { kind: e-car, x: 390, y: 45, power: "=Number(items.e_car_power.numericState) || 0" }
```

The recordings show the widgets with fixed demo values.

""")
md.append(section("Node", "flow-node", """A device in a ring, its animation driven by `power`: `pv` (a tilted module
under a sun, both brighter with the power, rays turning faster), `grid` (a pylon, red on import and green on export,
dashes running along its wires), `home` (a house whose windows glow and pulse with the consumption), `heat-pump` (an
outdoor unit whose fan turns while `frequency`, the compressor's, is above 0 Hz, faster from 30 and 55 Hz),
`air-conditioner` (an indoor unit whose air streams flow), `e-car` (a car
with a bolt fading in and out while it charges), `battery` (filled to `soc`, red, orange or green), `appliances`
(an appliance's housing with sparkles for a front, the big one breathing and the small ones twinkling while
they run) and `ventilation` (a ventilation unit whose fan turns above 5 W, faster with the power, and whose two
arrows, fresh air in and used air out, flow while it runs). A node is its drawing on a disc tinted in its colour over
an opaque one in the card colour, so dots running under it disappear; the card that places it draws the grey ring
around it, as the energy flow does (`track()` in the generator), and its badges.""", shot=img("flow-node.gif", "Flow nodes")))
md.append(section("Line", "flow-link", """A line from (`x1`, `y1`) to (`x2`, `y2`) in `color`. While
|`power`| exceeds `threshold` three dots run along it, towards (`x2`, `y2`) while `forward` holds and back otherwise, at
four speeds by the power; below the threshold the line fades. The dots run a dot radius past both ends, so they slide
out from under one node's rim and back under the other's. `color` and `forward` may be expressions, e.g. the grid's
line green and outward while it exports.""", shot=img("flow-link.gif", "Flow lines between three nodes")))
md.append(section("Share ring", "flow-share-ring", """A ring around (`x`, `y`) filled to `part` / `whole`, the
percentage inside and `title` with *heute* beside it; the energy flow shows today's self-consumption and
self-sufficiency with it.""", """
component: widget:flow-share-ring
config:
  x: 40
  y: 40
  title: Eigenverbrauch
  part: =Number(items.photovoltaics_own_ec_day.numericState) || 0
  whole: =Number(items.huawei_inverter_e_day.numericState) || 0
""", img("flow-share-rings.png", "Share rings")))
md.append("""## Appliances

The appliances card's parts.

""" + section("Appliance icon", "appliance-icon", """A washer, dryer or dishwasher (`kind`: `washer`, `dryer`,
`dish-washer`) drawn inside a ring: the drum's laundry, the dryer's paddles or the dishwasher's spray arm turn while
`running` holds, droplets rise in the dishwasher. While it runs the ring fills with `progress`, or pulses where there
is none.""", """
component: widget:appliance-icon
config:
  kind: dryer
  running: =items.miele_tumble_dryer_twc560wp_program_progress.state !== 'UNDEF'
  progress: =Number(items.miele_tumble_dryer_twc560wp_program_progress.numericState) || 0
  size: 72
""", img("appliance-icon.gif", "Appliance icons")))
md.append(section("Appliance tile", "appliance-tile", """An appliance as a tile of the appliances card: its icon, name
and state; a tap opens the page `popup` as a popup. A Miele machine comes with the items of its program (`progress`,
`state`, `program`, `phase`, `finished`, `remaining`, as the Miele binding provides them): the ring shows the
progress, the state chip is blue while it runs, green when it is finished and grey otherwise, beside it the remaining
time, and program, phase and end time below. A machine behind a metered plug comes with its `power` and an optional
`done` switch: it runs above 10 W, is finished while `done` is on, and its ring pulses. Put the tiles in a grid,
e.g. two columns.""", """
- component: widget:appliance-tile
  config:
    kind: washer
    title: Waschmaschine 1
    popup: washing_machine_1
    progress: miele_washing_machine_wwg360_program_progress
    state: miele_washing_machine_wwg360_operation_state
    program: miele_washing_machine_wwg360_active_program
    phase: miele_washing_machine_wwg360_program_phase
    finished: miele_washing_machine_wwg360_program_finished_time
    remaining: miele_washing_machine_wwg360_program_remaining_time
- component: widget:appliance-tile
  config:
    kind: washer
    title: Waschmaschine 2
    popup: washing_machine_2
    power: washing_machine_2_power
    done: washing_machine_2_finished
""", img("appliances-card.png", "Appliance tiles")))
md.append("""## Weather

""" + section("Weather icon", "weather-icon", """The weather drawn from a symbol in the style of the energy flow's
nodes: the sun, its rays turning slowly, or the moon while `day` is false. The sky in five levels: `clear` alone,
`fair` with a small cloud, `partly` behind a cloud of its size, `mostly` peeking out behind a large cloud with a darker
one behind it, `overcast` as two clouds; `veil` behind three thin streaks; a raised cloud over `fog`, falling `rain`,
drifting white `snow` or a flickering bolt (`thunder`), with the sun peeking out at its top left for showers
(`rain_sun`, `snow_sun`, `thunder_sun`). Nothing for any other value, as an item is `NULL` after a restart. My rule
works the symbol out from Open-Meteo: a day's sky from the share of its daylight the sun shines, an hour's from the
cloud layers, the high ones counted half. My weather bar shows the present weather with it, and my weather
page each day's, beside its hours of sunshine with their share of the daylight and the strongest wind with an arrow
of its dominant direction and its compass point, above a
chart of the next 60 hours: temperature with the weather drawn above it and over the precipitation of each hour, the
wind below with arrows of its direction, both every three hours; ECharts takes no widget, so the drawings there are
this widget's layers as still SVG images. That page is part of my installation, not a widget of this repository; its rule writes the forecast as JSON
into String items, and the chart reads them through an `oh-data-series` whose `data` is an expression such as
`=JSON.parse(items.weather_hourly.state).map((r) => [r[0] * 1000, r[1]])`, with no persistence involved. The
warnings in the screenshots are demo values.""", """
component: widget:weather-icon
config:
  symbol: =items.weather_symbol.state
  day: =items.weather_is_day.state !== 'OFF'
  size: 36
""", "| Light | Dark |\n|---|---|\n| " + img("weather-forecast.png", "Weather page: warnings, days and chart") + " | "
      + img("weather-forecast-dark.png", "Weather page in dark mode") + " |"))
md.append("""## Plug cards

Four cards for a metered plug, built from one item prefix: `<prefix>_power`, `_switch`, `_energy_today`,
`_energy_total`, `_voltage`, `_current`, `_power_factor`, `_apparent_power` and `_reactive_power`, as a Tasmota plug
provides them. On a device page they stand two by two. `plug-card` also covers devices that are not plugs: give it
the device's `title`, hide the switch with `controllable: false`, or take the switch from another item with `switch`.
Every value tile carries a large pale icon of what it shows.

![Plug cards](screenshots/plug-cards.png)
""")
for uid, what in PLUG:
    deps = needs(uid)
    need = (" Needs " + ", ".join(f"`{d}`" for d in sorted(deps)) + ".") if deps else ""
    md.append(f"### `{uid}`\n\n{what}.{need}\n\n{table(uid)}\n")
md.append("""## Item popup: `item-popup`

The popup every tile of my device pages opens, in place of the analyzer: the item's value large and its course over
the day with arrows for earlier days, as a line for measurements or as a band of states for switches, texts and
numbers with state options (labelled from the `states` prop), or the value alone for dates. Open it from any link
with `action: popup`, `actionModal: widget:item-popup` and its props in `actionModalConfig`:

```yaml
action: popup
actionModal: widget:item-popup
actionModalConfig:
  item: coffee_machine_energy_today
  title: Energie heute
  kind: number
```

![Item popup](screenshots/item-popup.png)

""" + table("item-popup") + "\n")
md.append("""## Value tile: `value-tile`

The tile every value of my popups, device pages, plug cards and heat pump card stands in: a title, the value, and a
large pale icon in the lower right corner, behind them. Pass the value as an expression; it is evaluated where the
tile is placed. With `item` a tap opens the item popup. The tile's lengths are em of its font size, 14 px unless
`fontSize` sets another, so `fontSize: 1.1em` makes it a tenth larger and lets it grow with a card that scales its
font. `wrap` lets a long text wrap across the whole row of a grid.

```yaml
component: widget:value-tile
config:
  title: Vorlauf
  value: =items.espaltherma_leaving_water_temp_after_buh.displayState
  icon: material:thermostat
  color: "#e57373"
  item: espaltherma_leaving_water_temp_after_buh
```

![Value tiles](screenshots/value-tiles.png)

""" + table("value-tile") + "\n")
md.append("""## About these widgets

The widgets are generated from Python by the script that builds my whole MainUI, which keeps the cards of the
dashboard and the device pages consistent; that is why their YAML is dense and machine-formatted. The script and its
tools are in [`scripts/openhab-ui/`](scripts/openhab-ui/): `dashboard.py`, the headless-Chrome tools behind the
screenshots, and the one-off JSONDB changes in `applied/`. The cards are
built from the smaller widgets wherever a part stands in more than one place or makes sense on its own, so a fix in
one widget reaches every place it stands. The widgets in this repository are exported from that script unchanged.
""")
text = "\n".join(md)
for example in re.findall(r"```yaml\n(.*?)```", text, re.S):  # every example must parse
    yaml.safe_load(example)
open(os.path.join(EXPORT, "README.md"), "w").write(text)
print(len("\n".join(md)), "chars")
