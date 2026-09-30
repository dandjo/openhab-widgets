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
     "phone the gaps narrow, and below 380 px the chevron goes, so the bar keeps its fit. A tap opens the forecast popup of "
     "my installation (see [Weather](#weather)). Its items come from two rules, "
     "`scripts/openhab-ui/applied/weather_forecast_rule.js`, which reads Open-Meteo's GeoSphere AROME Austria model, "
     "and `weather_warnings_rule.js`, which reads GeoSphere Austria's warnings and sends a broadcast notification "
     "when their level rises to orange or red."),
    ("controls-card", "Controls", "Heat pump, air conditioner and ventilation, each folded to a head of three lines "
     "with its main action on the right: a Boost button for the heat pump's hot water, the air conditioner's on/off "
     "pill, the ventilation levels 1 to 3; the heat pump's second line names which of its switches are on and "
     "which off. A tap on a head folds out its details, each group under its icon and title: Smart Grid, Betrieb "
     "(the switch pills Heizung, Warmwasser and Automatik, each with the icon of what it switches, three abreast "
     "where there is room and two and one on a phone) and sliders for the DHW setpoint and the leaving water offset; "
     "mode, fan, setpoint, boost and timer (usable while the unit is off); the ventilation timer. Below them tiles "
     "that toggle plugs and show their power. The three devices are the widgets `heatpump-controls`, "
     "`air-conditioner-controls` and `ventilation-controls`, the tiles `switch-tile`."),
    ("energy-flow-card", "Energy flow", "A regular star around the house: PV, heat pump, air conditioner, E-Car, the "
     "household appliances together, battery and grid, each with its power and today's energy. Dots run along the "
     "lines in the direction of the flow at four speeds and slide under the node rims; the icons move with the power "
     "(sun rays, fan, air streams, pylon dashes, a pulsing bolt over the charging car, sparkles twinkling while the "
     "appliances run, the battery filled to its state of charge). Rings for today's self-consumption and "
     "self-sufficiency sit in the free corner. The card places its lines, nodes and rings as `flow-link`, `flow-node` "
     "and `flow-share-ring`. The recording and the dark screenshot show it with demo values."),
    ("appliances-card", "Appliances", "Washing machines, dryer and dishwasher as `appliance-tile`s, each drawn inside a "
     "ring filled with the program progress; drums and paddles turn and the spray arm sprays while they run, with a "
     "pill for the remaining time."),
    ("electricity-price-card", "Electricity price", "The all-in price, the cheapest and priciest hour, and the prices "
     "12 hours back and 36 hours ahead, coloured green, orange and red by price."),
    ("heatpump-card", "Heat pump", "A section through the house: outdoor unit on the roof (the energy flow's "
     "`flow-node`), wall unit, three-way valve and DHW tank in the basement, floor heating and radiators on their "
     "levels, with the flow animated along the pipes as the valve decides. Two framed badges, each joined to its pipe "
     "by a dotted line, hold the refrigerant's temperature and pressure (violet while the compressor runs) and the "
     "water's heat with its leaving and inlet temperatures (coloured by that heat); the tank's temperature stands "
     "below it in a colour from blue to red, the sum of all electrical consumers below the wall unit, powers in kW. "
     "Beside it the power, today's energies split "
     "into space heating, DHW and standby, and daily COPs. On a phone the drawing takes the card's width; on a wider "
     "screen it stands at most at its own size, as the energy flow does, so their texts keep the UI's sizes and "
     "their circles come out the same."),
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
DEVICES = [("heatpump-controls", "Heat pump", "storage temperature and power in its head, and which of its three "
            "switches are on (Warmwasser, Automatik an · Heizung aus), Boost as its main action; folded out Smart Grid "
            "(`state-bar`), Betrieb (`pill-switch`: Heizung, Warmwasser, and Automatik, which switches a group of the "
            "heat pump's automations) and the sliders for DHW setpoint and leaving water offset (`pill-slider`)"),
           ("air-conditioner-controls", "Air conditioner", "state, mode, setpoint, room temperature and timer in its "
            "head, on/off as its main action; folded out mode and fan (`state-bar`), setpoint, boost (`boost-pill`) "
            "and timer, in the order of its popup, faded while the unit is off but usable"),
           ("ventilation-controls", "Ventilation", "level, power, CO₂ and what the automation does in its head, the "
            "levels 1 to 3 as its main action; folded out the timer slider. It always runs, so its panel is always "
            "tinted")]


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


def panels():
    """The three device panels: what each shows, folded out side by side, and what each needs."""
    rows = ["### Device panels: " + ", ".join(f"`{u}`" for u, _, _ in DEVICES), "",
            "The three devices of the controls card, each a widget of its own that takes its items as props:", ""]
    rows += [fill(f"- `{u}`, the {t.lower()}: {w}.", "  ") for u, t, w in DEVICES]
    rows += ["", "Each panel is tinted in its device's colour while the device runs; place them one under the other.",
             "", "| " + " | ".join(t for _, t, _ in DEVICES) + " |", "|---|---|---|",
             "| " + " | ".join(img(f"{u}.png", f"{t}, folded out") for u, t, _ in DEVICES) + " |", ""]
    for u, t, _ in DEVICES:
        rows += [f"`{u}` needs " + ", ".join(f"`{d}`" for d in sorted(needs(u))) + ".", ""]
    for u, _, _ in DEVICES:
        rows += [details(u).replace("<summary>", f"<summary><code>{u}</code>: "), ""]
    return "\n".join(rows)


md = ["""# openHAB Widgets

MainUI widgets from my openHAB 5 installation: the cards of an energy and home dashboard and the parts they are built
from, which work on their own too: device panels with their heads, pills, bars and sliders, the nodes and lines of the
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

The cards of my overview page. Each takes the items it shows as props; the prop names say what an item is. Some
elements open popup pages of my installation when tapped (`page:flow_*`, `page:hp_*`, `page:appliance_*`,
`page:forecast`); they are not part of this repository.
""")
for uid, title, what in OVERVIEW:
    shots = []
    for name, alt in ((f"{uid}.gif", title), (f"{uid}.png", title), (f"{uid}-open.png", f"{title}, folded out"),
                      (f"{uid}-dark.png", f"{title} in dark mode")):
        if os.path.exists(os.path.join(EXPORT, "screenshots", name)):
            shots.append(img(name, alt))
    deps = needs(uid)
    need = ("\n\n" + fill("Needs " + ", ".join(f"`{d}`" for d in sorted(deps)) + ".")) if deps else ""
    md.append(f"### {title}: `{uid}`\n\n{fill(what)}{need}\n\n" + "\n\n".join(shots) + f"\n\n{details(uid)}\n")

md.append("""## Device controls

The parts of the controls card. A device panel is a `device-head` over its details, which fold out on a tap on the
head. Folding sends no command: the head sets a variable, which the panel declares in an `oh-context` around head and
details. It has to be a context variable: MainUI gives every widget instance its own copy of the page's variables, so
a page variable the head widget set would never reach the details, while a context's variables reach through the
widgets placed inside it.

""" + panels() + "\n")
md.append(section("Device head", "device-head", """A device in three lines: its icon in a circle, tinted in the
device's colour while `active` holds; beside it the name with a chevron and the main action, and under them two lines
of state that run the whole width, under the action too, so they stay readable on a phone. A tap anywhere but on the
action folds the details in or out through the variable `var`. The main action is a switch pill (`action: switch`,
`pill-switch`), a boost button (`button`, `boost-button`) or a segmented bar (`bar`, `state-bar` with
`actionOptions`) on `actionItem`. Declare `var` in an `oh-context` around the head and the details, and show the
details while `vars.<var>` holds:""", """
component: oh-context
config:
  variables:
    acOpen: false
slots:
  default:
    - component: div
      slots:
        default:
          - component: widget:device-head
            config:
              icon: material:ac_unit
              title: Klimaanlage
              line1: "=(items.faikout_perfera_switch.state === 'ON' ? 'An · ' : 'Aus · ') + items.faikout_perfera_mode.displayState"
              line2: ="Raum " + items.faikout_perfera_temperature.displayState
              color: "#29b6f6"
              active: =items.faikout_perfera_switch.state === 'ON'
              var: acOpen
              action: switch
              actionItem: faikout_perfera_switch
              actionTitle: An/Aus
          - component: div
            config:
              visible: =!!vars.acOpen
            slots:
              default:
                - component: widget:state-bar
                  config:
                    item: faikout_perfera_mode
                    options: A=Auto;H=Heizen;C=Kühlen;D=Entfeuchten;F=Lüften
                    color: "#29b6f6"
                    byText: true
""", img("device-heads.png", "Device heads, folded")))
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
md.append(section("Boost button", "boost-button", """A boost as one small pill, for a place without room for the boost
pill such as a device head: its name in the device colour, outlined, filled with the colour while it runs. A tap
switches the item.""", """
component: widget:boost-button
config:
  item: pyaltherma_dhw_powerful
  title: Boost
  color: "#fb8c00"
"""))
md.append("""### Slider: `pill-slider`

A setting as a wide pill slider in the device colour, for setpoints, offsets, powers and timers: a gradient fills the
bar up to the value, the white knob stays inside the bar at both ends, and the value is sent once on release. Only the
knob can be dragged, so scrolling across a slider on a phone leaves it alone. Above the
bar an icon in a tinted circle (for a timer, `ring: true`, a ring around a timer icon that empties as the item runs
down to 0), the title with a line of context and the value large on the right; `marks` puts labels below the bar.
`value` and `context` are expressions, evaluated where the slider is placed. The slider is only built once the item
has a numeric state, because MainUI's slider starts at its minimum and a touch ending on it sends its value.

```yaml
component: widget:pill-slider
config:
  item: faikout_perfera_temperature_setpoint
  color: "#29b6f6"
  min: 18
  max: 32
  step: 0.5
  unit: °C
  title: Soll
  icon: material:device_thermostat
  value: =items.faikout_perfera_temperature_setpoint.displayState
  context: ="Raum " + items.faikout_perfera_temperature.displayState
  marks: 18=18 °C;22=22;26=26;32=32 °C
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
outdoor unit whose fan turns above 100 W), `air-conditioner` (an indoor unit whose air streams flow), `e-car` (a car
with a bolt fading in and out while it charges), `battery` (filled to `soc`, red, orange or green) and `appliances`
(an appliance's housing with sparkles for a front, the big one breathing and the small ones twinkling while
they run). The ring has an opaque disc in the card colour under its tint, so dots running under it disappear.""", shot=img("flow-node.gif", "Flow nodes")))
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
    popup: appliance_washing_machine_1
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
    popup: appliance_washing_machine_2
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
cloud layers, the high ones counted half. My weather bar shows the present weather with it, and my forecast
popup each day's, beside its hours of sunshine with their share of the daylight and the strongest wind with an arrow
of its dominant direction and its compass point, above a
chart of the next 60 hours: temperature with the weather drawn above it and over the precipitation of each hour, the
wind below with arrows of its direction, both every three hours; ECharts takes no widget, so the drawings there are
this widget's layers as still SVG images. That popup is a page of my installation, not a widget of this repository; its rule writes the forecast as JSON
into String items, and the chart reads them through an `oh-data-series` whose `data` is an expression such as
`=JSON.parse(items.weather_hourly.state).map((r) => [r[0] * 1000, r[1]])`, with no persistence involved. The
warnings in the screenshots are demo values.""", """
component: widget:weather-icon
config:
  symbol: =items.weather_symbol.state
  day: =items.weather_is_day.state !== 'OFF'
  size: 36
""", "| Light | Dark |\n|---|---|\n| " + img("forecast-popup.png", "Forecast popup: warnings, days and chart") + " | "
      + img("forecast-popup-dark.png", "Forecast popup in dark mode") + " |"))
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
