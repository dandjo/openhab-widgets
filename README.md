# openHAB Widgets

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
| `air-conditioner-quick` | `boost-pill`, `pill-slider`, `power-pill`, `state-bar` |
| `appliance-icon` | – |
| `appliance-tile` | `appliance-icon` |
| `appliances-card` | `appliance-icon`, `appliance-tile` |
| `boost-pill` | – |
| `consumption-card` | – |
| `electricity-price-card` | – |
| `energy-days-card` | – |
| `energy-flow-card` | `air-conditioner-quick`, `boost-pill`, `flow-link`, `flow-node`, `flow-share-ring`, `heatpump-quick`, `pill-slider`, `pill-switch`, `power-pill`, `state-bar`, `switch-row`, `switch-tile`, `ventilation-quick` |
| `flow-link` | – |
| `flow-node` | – |
| `flow-share-ring` | – |
| `ground-floor-quick` | – |
| `heatpump-card` | `boost-pill`, `flow-node`, `ground-floor-quick`, `heatpump-circuit-quick`, `heatpump-control-quick`, `heatpump-cop-quick`, `heatpump-electric-quick`, `heatpump-heat-quick`, `heatpump-indoor-quick`, `heatpump-outdoor-quick`, `heatpump-refrigerant-quick`, `item-popup`, `pill-slider`, `pill-switch`, `state-bar`, `upper-floor-quick`, `value-tile` |
| `heatpump-circuit-quick` | `pill-slider` |
| `heatpump-control-quick` | `boost-pill`, `pill-switch`, `state-bar` |
| `heatpump-cop-quick` | – |
| `heatpump-electric-quick` | – |
| `heatpump-heat-quick` | – |
| `heatpump-indoor-quick` | `boost-pill`, `pill-slider`, `pill-switch`, `state-bar` |
| `heatpump-outdoor-quick` | – |
| `heatpump-quick` | `boost-pill`, `pill-slider`, `pill-switch` |
| `heatpump-refrigerant-quick` | – |
| `item-popup` | – |
| `pill-slider` | – |
| `pill-switch` | – |
| `plug-card` | `item-popup`, `power-pill`, `value-tile` |
| `plug-electric-card` | `item-popup`, `value-tile` |
| `plug-energy-days-card` | – |
| `plug-power-card` | – |
| `power-pill` | – |
| `pv-days-card` | – |
| `state-bar` | – |
| `switch-row` | – |
| `switch-tile` | – |
| `temperatures-card` | – |
| `upper-floor-quick` | – |
| `value-tile` | `item-popup` |
| `ventilation-quick` | `pill-slider`, `state-bar`, `switch-row` |
| `weather-card` | `weather-icon` |
| `weather-icon` | – |

## Dashboard cards

The cards of my overview page. Each takes the items it shows as props; the prop names say what an item is. Most
elements open a page of my installation as a popup when tapped: the page of their device (`page:heatpump`,
`page:weather` …), or for the energy flow's house and appliances a popup of its own (`page:flow_home`,
`page:flow_appliances`). The pages are not part of this repository; the quick popups the energy flow's heat pump, air
conditioner and ventilation and the heat pump card's tiles open are (see [Quick popups](#quick-popups)).

### Weather: `weather-card`

A slim bar across the top: the present weather drawn in the style of the energy flow (`weather-icon`: sun or moon,
clear, behind one or two clouds or veil streaks, clouds with rain, snow, a bolt or fog, the sun peeking out for showers,
gently animated), the outdoor temperature from a local sensor, and today and the next two days, each with its weather
drawn beside its maximum over its minimum. While an official warning of GeoSphere Austria is in effect or begins within
24 hours, it is teased beside the temperature: a disc in its level's colour (yellow, orange, red) with an exclamation
mark and a ring pulsing out of it, on a wider screen in a pill with the warning's short text (*Gewitter bis 20:00*). On
a phone the gaps narrow, and below 380 px the chevron goes, so the bar keeps its fit. A tap opens the weather page of my
installation as a popup (see [Weather](#weather)). Its items come from two rules,
`scripts/openhab-ui/applied/weather_forecast_rule.js`, which reads Open-Meteo's GeoSphere AROME Austria model, and
`weather_warnings_rule.js`, which reads GeoSphere Austria's warnings and sends a broadcast notification when their level
rises to orange or red.

Needs `weather-icon`.

![Weather](screenshots/weather-card.png)

![Weather in dark mode](screenshots/weather-card-dark.png)

<details>
<summary>12 props</summary>

| Prop | Item | Item type |
|---|---|---|
| `weatherSymbol` | Wetter aktuell | String |
| `weatherIsDay` | Wetter Tag | Switch |
| `heatpumpExtAmbientTemp` | ESPAltherma Außentemperatur | Number:Temperature |
| `weatherWarningLevel` | Wetterwarnung Stufe | Number |
| `weatherWarningText` | Wetterwarnung | String |
| `weatherDaily` | Wetter Tagesprognose | String |
| `weatherDay0Max` | Wetter heute Max. | Number:Temperature |
| `weatherDay0Min` | Wetter heute Min. | Number:Temperature |
| `weatherDay1Max` | Wetter morgen Max. | Number:Temperature |
| `weatherDay1Min` | Wetter morgen Min. | Number:Temperature |
| `weatherDay2Max` | Wetter übermorgen Max. | Number:Temperature |
| `weatherDay2Min` | Wetter übermorgen Min. | Number:Temperature |

</details>

### Energy flow: `energy-flow-card`

A regular star around the house: PV, heat pump, air conditioner, E-Car, the household appliances together, ventilation,
battery and grid, each with its power and today's energy. Dots run along the lines in the direction of the flow at four
speeds and slide under the node rims; while power flows through a node, dots in its colour run round its grey ring,
clockwise towards the house and the other way out of it. The icons move with the power (sun rays, air streams, pylon
dashes, a pulsing bolt over the charging car, sparkles twinkling while the appliances run, the battery filled to its
state of charge, the ventilation's duct fan turning), the heat pump's fan with its compressor: while only its electric
heaters run it stands and the energy only flows. Badges on the rings tell what the heat pump does (space heating, hot
water, defrost, a red bolt while only its electric heaters run), whether the air conditioner is on and the ventilation's
level. A running timer covers its device's ring with an arc, full at what it was last set to, and the battery's ring is
filled with its state of charge; the dots run on in the rest of the ring. A tap on the heat pump, the air conditioner or
the ventilation opens its quick popup (see [Quick popups](#quick-popups)). Under the star three tiles with large pale
icons, the house's power and today's self-consumption and self-sufficiency as rings, and below them switch tiles for
plugs. The card places its lines, nodes and rings as `flow-link`, `flow-node` and `flow-share-ring`, the plugs as
`switch-tile`. The recording and the dark screenshot show it with demo values.

Needs `air-conditioner-quick`, `boost-pill`, `flow-link`, `flow-node`, `flow-share-ring`, `heatpump-quick`,
`pill-slider`, `pill-switch`, `power-pill`, `state-bar`, `switch-row`, `switch-tile`, `ventilation-quick`.

![Energy flow](screenshots/energy-flow-card.gif)

![Energy flow in dark mode](screenshots/energy-flow-card-dark.png)

<details>
<summary>67 props</summary>

| Prop | Item | Item type |
|---|---|---|
| `pvPower` | Wechselrichter Eingangsleistung | Number:Power |
| `gridPower` | Stromzähler Wirkleistung | Number:Power |
| `heatpumpPower` | ESPAltherma Elektrische Leistung | Number:Power |
| `acSwitch` | Faikout Perfera Schalter | Switch |
| `acUnitPower` | Klimaanlage Geräteleistung | Number:Power |
| `ecarPower` | E-Auto Leistung | Number:Power |
| `washingMachine1Power` | Waschmaschine 1 Leistung | Number:Power |
| `washingMachine2Power` | Waschmaschine 2 Leistung | Number:Power |
| `tumbleDryerPower` | Wäschetrockner Leistung | Number:Power |
| `dishwasherPower` | Geschirrspüler Leistung | Number:Power |
| `batteryPower` | Batteriespeicher Leistung | Number:Power |
| `ventilationPower` | Lüftung Leistung | Number:Power |
| `homePower` | Haus Leistung | Number:Power |
| `acTimer` | Klimaanlage Timer | Number:Time |
| `acTimerSet` | Klimaanlage Timer eingestellt | Number:Time |
| `ventilationTimer` | Lüftung Timer | Number:Time |
| `ventilationTimerSet` | Lüftung Timer eingestellt | Number:Time |
| `batterySoc` | Batteriespeicher Ladestand | Number:Dimensionless |
| `heatpumpInvFrequency` | ESPAltherma Verdichterfrequenz | Number:Frequency |
| `heatpumpBuhStep1Mode` | ESPAltherma Heizstab Stufe 1 | Switch |
| `heatpumpBuhStep2Mode` | ESPAltherma Heizstab Stufe 2 | Switch |
| `heatpumpBshMode` | ESPAltherma Zusatzheizung Speicher | Switch |
| `heatpumpDefrostOperaton` | ESPAltherma Abtauen | Switch |
| `heatpumpValve` | ESPAltherma 3-Wege-Ventil | String |
| `ventilationLevel` | ESPLyfterl Stufe | String |
| `pvEnergyToday` | Wechselrichter Ertrag heute | Number:Energy |
| `gridImportToday` | Stromzähler Bezug heute | Number:Energy |
| `gridExportToday` | Stromzähler Einspeisung heute | Number:Energy |
| `heatpumpEnergyToday` | ESPAltherma Energie heute | Number:Energy |
| `acUnitEnergyToday` | Klimaanlage Geräteenergie heute | Number:Energy |
| `ecarEnergyToday` | E-Auto Energie heute | Number:Energy |
| `washingMachine1EnergyToday` | Waschmaschine 1 Energie heute | Number:Energy |
| `washingMachine2EnergyToday` | Waschmaschine 2 Energie heute | Number:Energy |
| `tumbleDryerEnergyToday` | Wäschetrockner Energie heute | Number:Energy |
| `dishwasherEnergyToday` | Geschirrspüler Energie heute | Number:Energy |
| `batteryDischargeToday` | Batteriespeicher Entladung heute | Number:Energy |
| `batteryChargeToday` | Batteriespeicher Ladung heute | Number:Energy |
| `heatpumpDhwTankTemp` | ESPAltherma Warmwasserspeicher Temperatur | Number:Temperature |
| `heatpumpDhwBoost` | Pyaltherma Warmwasser-Boost | Switch |
| `heatpumpClimateControlPower` | Pyaltherma Heizung Ein/Aus | Switch |
| `heatpumpDhwPower` | Pyaltherma Warmwasser Ein/Aus | Switch |
| `heatpumpManagement` | Wärmepumpe Automatik | Group |
| `heatpumpDhwTempHeating` | Pyaltherma Warmwasser Solltemperatur | Number:Temperature |
| `heatpumpDhwManagement` | Wärmepumpe Warmwasser-Automatik | Switch |
| `acMode` | Faikout Perfera Modus | String |
| `acTemperature` | Faikout Perfera Temperatur | Number:Temperature |
| `acTemperatureSetpoint` | Faikout Perfera Solltemperatur | Number:Temperature |
| `acPowerful` | Faikout Perfera Powerful | Switch |
| `netatmoWeatherstationCo2` | Netatmo Wetterstation CO2 | Number:Dimensionless |
| `ventilationManagement` | Lüftung Automatik | Group |
| `homeEnergyToday` | Haus Energie heute | Number:Energy |
| `pvSelfUseToday` | Photovoltaik Eigenverbrauch heute | Number:Energy |
| `coffeeMachineSwitch` | Kaffeemaschine Schalter | Switch |
| `coffeeMachinePower` | Kaffeemaschine Leistung | Number:Power |
| `coffeeMachineEnergyToday` | Kaffeemaschine Energie heute | Number:Energy |
| `bicycleBatteriesSwitch` | Fahrradakkus Schalter | Switch |
| `bicycleBatteriesPower` | Fahrradakkus Leistung | Number:Power |
| `bicycleBatteriesEnergyToday` | Fahrradakkus Energie heute | Number:Energy |
| `office1Switch` | Büro 1 Schalter | Switch |
| `office1Power` | Büro 1 Leistung | Number:Power |
| `office1EnergyToday` | Büro 1 Energie heute | Number:Energy |
| `office2Switch` | Büro 2 Schalter | Switch |
| `office2Power` | Büro 2 Leistung | Number:Power |
| `office2EnergyToday` | Büro 2 Energie heute | Number:Energy |
| `terraceLightSwitch` | Terrassenlicht Schalter | Switch |
| `terraceLightPower` | Terrassenlicht Leistung | Number:Power |
| `terraceLightEnergyToday` | Terrassenlicht Energie heute | Number:Energy |

</details>

### Appliances: `appliances-card`

Washing machines, dryer and dishwasher as `appliance-tile`s, each drawn inside a ring filled with the program progress;
drums and paddles turn and the spray arm sprays while they run, with a pill for the remaining time.

Needs `appliance-icon`, `appliance-tile`.

![Appliances](screenshots/appliances-card.png)

<details>
<summary>20 props</summary>

| Prop | Item | Item type |
|---|---|---|
| `washer1ProgramProgress` | Miele Waschmaschine WWG360 Fortschritt | Number:Dimensionless |
| `washer1OperationState` | Miele Waschmaschine WWG360 Status | String |
| `washer1ActiveProgram` | Miele Waschmaschine WWG360 Programm | String |
| `washer1ProgramPhase` | Miele Waschmaschine WWG360 Programmphase | String |
| `washer1ProgramFinishedTime` | Miele Waschmaschine WWG360 Fertig um | DateTime |
| `washer1ProgramRemainingTime` | Miele Waschmaschine WWG360 Restzeit | Number |
| `washingMachine2Power` | Waschmaschine 2 Leistung | Number:Power |
| `washingMachine2Finished` | Waschmaschine 2 Fertig | Switch |
| `dryerProgramProgress` | Miele Wäschetrockner TWC560WP Fortschritt | Number:Dimensionless |
| `dryerOperationState` | Miele Wäschetrockner TWC560WP Status | String |
| `dryerActiveProgram` | Miele Wäschetrockner TWC560WP Programm | String |
| `dryerProgramPhase` | Miele Wäschetrockner TWC560WP Programmphase | String |
| `dryerProgramFinishedTime` | Miele Wäschetrockner TWC560WP Fertig um | DateTime |
| `dryerProgramRemainingTime` | Miele Wäschetrockner TWC560WP Restzeit | Number |
| `dishwasherProgramProgress` | Miele Geschirrspüler G7465 Fortschritt | Number:Dimensionless |
| `dishwasherOperationState` | Miele Geschirrspüler G7465 Status | String |
| `dishwasherActiveProgram` | Miele Geschirrspüler G7465 Programm | String |
| `dishwasherProgramPhase` | Miele Geschirrspüler G7465 Programmphase | String |
| `dishwasherProgramFinishedTime` | Miele Geschirrspüler G7465 Fertig um | DateTime |
| `dishwasherProgramRemainingTime` | Miele Geschirrspüler G7465 Restzeit | Number |

</details>

### Electricity price: `electricity-price-card`

The all-in price, the cheapest and priciest hour, and the prices 12 hours back and 36 hours ahead, coloured green,
orange and red by price.

![Electricity price](screenshots/electricity-price-card.png)

<details>
<summary>6 props</summary>

| Prop | Item | Item type |
|---|---|---|
| `priceTotalGross` | Strompreis gesamt brutto | Number:EnergyPrice |
| `priceCheapestHour` | Günstigste Stunde | DateTime |
| `pricePriciestHour` | Teuerste Stunde | DateTime |
| `priceTotalNet` | Strompreis gesamt netto | Number:EnergyPrice |
| `priceMarketGross` | Strompreis Markt brutto | Number:EnergyPrice |
| `priceMarketNet` | Strompreis Markt netto | Number:EnergyPrice |

</details>

### Heat pump: `heatpump-card`

A section through the house: the outdoor unit on the roof (the energy flow's `flow-node`), wall unit, three-way valve,
DHW tank and radiators in the basement, floor heating on the two levels above. Every device sits in a grey ring like the
energy flow's nodes, dots running round it while it works; the outdoor unit's fan turns while the compressor runs and
its ring is filled by the compressor's frequency, the wall unit's by its own draw, the measured circuit (full and red
while the backup heater runs; the tank's booster heater does not count), the tank's by its temperature, radiators and
floor loops by the leaving water while they carry it. Dots run along the pipes, as many as a pipe is long, faster with
the water's flow or the compressor's frequency, and all of them backwards during a defrost. The valve shows its position
in its icon. Tiles in the style of the switch tiles hold the figures: the outdoor unit, the control (heating, hot water,
Smart Grid, automation), the refrigerant, the heating circuit, the climate of the two floors, the tank with its booster
heater and the indoor unit with its own power (the measured circuit plus the backup heater), each tinted in its colour
while what it shows is at work. A tap on a tile, the wall unit or the outdoor unit opens its quick popup with charts or
controls. Beside the drawing the electrical power, the heat and the COP as value tiles that open popups with their
charts of the day and the month, today's energies split into space heating, DHW and standby as bars, and today's COPs as
rings. On a phone the drawing takes the card's width; on a wider screen it stands at most at its own size, as the energy
flow does, so their texts keep the UI's sizes and their circles come out the same. The recording and the dark screenshot
show it with demo values (a space heating run).

Needs `boost-pill`, `flow-node`, `ground-floor-quick`, `heatpump-circuit-quick`, `heatpump-control-quick`,
`heatpump-cop-quick`, `heatpump-electric-quick`, `heatpump-heat-quick`, `heatpump-indoor-quick`,
`heatpump-outdoor-quick`, `heatpump-refrigerant-quick`, `item-popup`, `pill-slider`, `pill-switch`, `state-bar`,
`upper-floor-quick`, `value-tile`.

![Heat pump](screenshots/heatpump-card.gif)

![Heat pump in dark mode](screenshots/heatpump-card-dark.png)

<details>
<summary>56 props</summary>

| Prop | Item | Item type |
|---|---|---|
| `heatpumpDhwTankTemp` | ESPAltherma Warmwasserspeicher Temperatur | Number:Temperature |
| `heatpumpInvFrequency` | ESPAltherma Verdichterfrequenz | Number:Frequency |
| `heatpumpDefrostOperaton` | ESPAltherma Abtauen | Switch |
| `heatpumpWaterPumpOperation` | ESPAltherma Umwälzpumpe | Switch |
| `heatpumpFlowSensor` | ESPAltherma Durchfluss | Number:VolumetricFlowRate |
| `heatpumpValve` | ESPAltherma 3-Wege-Ventil | String |
| `heatpumpBuhStep1Mode` | ESPAltherma Heizstab Stufe 1 | Switch |
| `heatpumpBuhStep2Mode` | ESPAltherma Heizstab Stufe 2 | Switch |
| `heatpumpCircuitPower` | Wärmepumpe Leistung | Number:Power |
| `heatpumpBshMode` | ESPAltherma Zusatzheizung Speicher | Switch |
| `heatpumpLeavingWaterTempAfterBuh` | ESPAltherma Vorlauftemperatur nach Heizstab | Number:Temperature |
| `heatpumpExtAmbientTemp` | ESPAltherma Außentemperatur | Number:Temperature |
| `heatpumpHeatExchangerMidTemp` | ESPAltherma Wärmetauscher Mitte | Number:Temperature |
| `heatpumpSmartGrid` | ESPAltherma Smart Grid | String |
| `heatpumpClimateControlPower` | Pyaltherma Heizung Ein/Aus | Switch |
| `heatpumpDhwBoost` | Pyaltherma Warmwasser-Boost | Switch |
| `heatpumpDhwPower` | Pyaltherma Warmwasser Ein/Aus | Switch |
| `heatpumpManagement` | Wärmepumpe Automatik | Group |
| `heatpumpDischargePipeTemp` | ESPAltherma Heißgastemperatur | Number:Temperature |
| `heatpumpRefrigerantTemp` | ESPAltherma Kältemittel flüssig | Number:Temperature |
| `heatpumpRefrigerantPressure` | ESPAltherma Kältemitteldruck | Number:Pressure |
| `heatpumpHeatingPowerAfterBuh` | ESPAltherma Heizleistung nach Heizstab | Number:Power |
| `heatpumpInletWaterTemp` | ESPAltherma Rücklauftemperatur | Number:Temperature |
| `acTemperature` | Faikout Perfera Temperatur | Number:Temperature |
| `tadoHumidity` | Tado Luftfeuchtigkeit | Number:Dimensionless |
| `heatpumpIndoorAmbientTemp` | ESPAltherma Raumtemperatur | Number:Temperature |
| `netatmoWeatherstationAtmosphericHumidity` | Netatmo Wetterstation Luftfeuchtigkeit | Number:Dimensionless |
| `netatmoWeatherstationCo2` | Netatmo Wetterstation CO2 | Number:Dimensionless |
| `heatpumpDhwSetpoint` | ESPAltherma Warmwasser Sollwert | Number:Temperature |
| `heatpumpBshPower` | ESPAltherma Elektrische Leistung Zusatzheizung | Number:Power |
| `heatpumpBuhPower` | ESPAltherma Elektrische Leistung Heizstab | Number:Power |
| `heatpumpWaterPressure` | ESPAltherma Wasserdruck | Number:Pressure |
| `heatpumpOutdoorAirTemp` | ESPAltherma Außenluft Temperatur | Number:Temperature |
| `heatpumpTargetDischargeTemp` | ESPAltherma Soll-Heißgastemperatur | Number:Temperature |
| `heatpumpLeavingWaterTempOffsetHeating` | Pyaltherma Vorlauf-Offset Heizen | Number:Temperature |
| `heatpumpLeavingWaterSetpoint` | ESPAltherma Vorlauf Sollwert | Number:Temperature |
| `heatpumpDhwTempHeating` | Pyaltherma Warmwasser Solltemperatur | Number:Temperature |
| `heatpumpDhwManagement` | Wärmepumpe Warmwasser-Automatik | Switch |
| `heatpumpPower` | ESPAltherma Elektrische Leistung | Number:Power |
| `heatpumpEnergyToday` | ESPAltherma Energie heute | Number:Energy |
| `heatpumpElectricalPowerSpace` | ESPAltherma Elektrische Leistung Heizung | Number:Power |
| `heatpumpElectricalPowerDhw` | ESPAltherma Elektrische Leistung Warmwasser | Number:Power |
| `heatpumpElectricalPowerStandby` | ESPAltherma Elektrische Leistung Standby | Number:Power |
| `heatpumpEnergySpaceToday` | ESPAltherma Energie Heizung heute | Number:Energy |
| `heatpumpEnergyDhwToday` | ESPAltherma Energie Warmwasser heute | Number:Energy |
| `heatpumpEnergyStandbyToday` | ESPAltherma Energie Standby heute | Number:Energy |
| `heatpumpHeatPower` | ESPAltherma Heizleistung | Number:Power |
| `heatpumpHeatingEnergyToday` | ESPAltherma Heizenergie heute | Number:Energy |
| `heatpumpHeatingPowerSpace` | ESPAltherma Heizleistung Heizung | Number:Power |
| `heatpumpHeatingPowerDhw` | ESPAltherma Heizleistung Warmwasser | Number:Power |
| `heatpumpHeatingEnergySpaceToday` | ESPAltherma Heizenergie Heizung heute | Number:Energy |
| `heatpumpHeatingEnergyDhwToday` | ESPAltherma Heizenergie Warmwasser heute | Number:Energy |
| `heatpumpCop` | ESPAltherma COP | Number |
| `heatpumpDcop` | ESPAltherma Tages-COP | Number |
| `heatpumpDcopSpace` | ESPAltherma Tages-COP Heizung | Number |
| `heatpumpDcopDhw` | ESPAltherma Tages-COP Warmwasser | Number |

</details>

### Consumption today: `consumption-card`

Today's consumption as one bar split by source (PV, grid) and by consumer, with a legend in two columns; hovering a part
lifts it everywhere. The screenshot shows it with demo values.

![Consumption today](screenshots/consumption-card.png)

<details>
<summary>20 props</summary>

| Prop | Item | Item type |
|---|---|---|
| `homeEnergyToday` | Haus Energie heute | Number:Energy |
| `pvSelfUseToday` | Photovoltaik Eigenverbrauch heute | Number:Energy |
| `gridImportToday` | Stromzähler Bezug heute | Number:Energy |
| `heatpumpEnergyToday` | ESPAltherma Energie heute | Number:Energy |
| `ecarEnergyToday` | E-Auto Energie heute | Number:Energy |
| `acUnitEnergyToday` | Klimaanlage Geräteenergie heute | Number:Energy |
| `office1EnergyToday` | Büro 1 Energie heute | Number:Energy |
| `office2EnergyToday` | Büro 2 Energie heute | Number:Energy |
| `networkEnergyToday` | Netzwerk Energie heute | Number:Energy |
| `ventilationEnergyToday` | Lüftung Energie heute | Number:Energy |
| `refrigeratorEnergyToday` | Kühlschrank Energie heute | Number:Energy |
| `coffeeMachineEnergyToday` | Kaffeemaschine Energie heute | Number:Energy |
| `livingRoomEntertainmentEnergyToday` | Wohnzimmer Medien Energie heute | Number:Energy |
| `dishwasherEnergyToday` | Geschirrspüler Energie heute | Number:Energy |
| `washingMachine1EnergyToday` | Waschmaschine 1 Energie heute | Number:Energy |
| `washingMachine2EnergyToday` | Waschmaschine 2 Energie heute | Number:Energy |
| `tumbleDryerEnergyToday` | Wäschetrockner Energie heute | Number:Energy |
| `terraceLightEnergyToday` | Terrassenlicht Energie heute | Number:Energy |
| `bicycleBatteriesEnergyToday` | Fahrradakkus Energie heute | Number:Energy |
| `acMeterEnergyToday` | Klimaanlage Energie heute | Number:Energy |

</details>

### Energy per day: `energy-days-card`

The month's daily home consumption as stacked bars: from PV and from the grid, with PV production beside it.

![Energy per day](screenshots/energy-days-card.png)

<details>
<summary>3 props</summary>

| Prop | Item | Item type |
|---|---|---|
| `dailySelfUse` | Energie täglich Eigenverbrauch | Number:Energy |
| `dailyGridImport` | Energie täglich Netzbezug | Number:Energy |
| `dailyPv` | Energie täglich PV | Number:Energy |

</details>

### PV production per day: `pv-days-card`

The daily PV yield of a year in four views a bar switches: a calendar heatmap of the year, two half-years, twelve month
calendars and the months' sums as bars; a wider screen gets the year, the month calendars and the bars, a phone the
half-years instead of the year.

![PV production per day](screenshots/pv-days-card.png)

<details>
<summary>1 props</summary>

| Prop | Item | Item type |
|---|---|---|
| `dailyPv` | Energie täglich PV | Number:Energy |

</details>

### Temperatures: `temperatures-card`

Indoor and outdoor temperature now, the day's minimum and maximum, and the last day as a chart from 15-minute means.

![Temperatures](screenshots/temperatures-card.png)

<details>
<summary>4 props</summary>

| Prop | Item | Item type |
|---|---|---|
| `heatpumpIndoorAmbientTemp` | ESPAltherma Raumtemperatur | Number:Temperature |
| `heatpumpExtAmbientTemp` | ESPAltherma Außentemperatur | Number:Temperature |
| `temperatureIndoor15min` | Temperatur innen 15 min | Number:Temperature |
| `temperatureOutdoor15min` | Temperatur außen 15 min | Number:Temperature |

</details>

## Quick popups

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

It opens 420 px wide and up to 640 px high, on a phone full screen; its charts start below their period buttons, a
closed period menu takes no room. The energy flow's heat pump, air conditioner and ventilation open the first three,
the heat pump card's tiles, wall unit and outdoor unit the others:

- `heatpump-quick`, heat pump: the hot-water boost, heating, hot water and automation, the DHW setpoint.
- `air-conditioner-quick`, air conditioner: on/off, mode, setpoint, timer and boost.
- `ventilation-quick`, ventilation: the level, the timer and the automation.
- `heatpump-control-quick`, control: heating, hot water and automation, the hot-water boost and the Smart Grid.
- `heatpump-indoor-quick`, indoor unit: all the heat pump's controls.
- `heatpump-outdoor-quick`, outdoor unit: its power with the compressor frequency and the outdoor temperature against
  its heat exchanger's over the day.
- `heatpump-refrigerant-quick`, refrigerant: hot gas with its target, liquid, heat exchanger and pressure over the day.
- `heatpump-circuit-quick`, heating circuit: the leaving water offset, leaving and inlet water with the heat over the
  day.
- `upper-floor-quick`, upper floor: temperature and humidity over the day.
- `ground-floor-quick`, ground floor: temperature, humidity and CO₂ over the day.
- `heatpump-electric-quick`, electricity: the power of space heating, DHW and standby over the day, their energy per day
  of the month.
- `heatpump-heat-quick`, heat: the heat of space heating and DHW over the day, per day of the month.
- `heatpump-cop-quick`, COP: the COP against the outdoor temperature over the day, the daily COPs of the month.

| | | |
|---|---|---|
| ![Heat pump](screenshots/heatpump-quick.png) | ![Air conditioner](screenshots/air-conditioner-quick.png) | ![Ventilation](screenshots/ventilation-quick.png) |
| ![Control](screenshots/heatpump-control-quick.png) | ![Indoor unit](screenshots/heatpump-indoor-quick.png) | ![Outdoor unit](screenshots/heatpump-outdoor-quick.png) |
| ![Refrigerant](screenshots/heatpump-refrigerant-quick.png) | ![Heating circuit](screenshots/heatpump-circuit-quick.png) | ![Upper floor](screenshots/upper-floor-quick.png) |
| ![Ground floor](screenshots/ground-floor-quick.png) | ![Electricity](screenshots/heatpump-electric-quick.png) | ![Heat](screenshots/heatpump-heat-quick.png) |
| ![COP](screenshots/heatpump-cop-quick.png) |  |  |

`heatpump-quick` needs `boost-pill`, `pill-slider`, `pill-switch`.

<details>
<summary><code>heatpump-quick</code>: 8 props</summary>

| Prop | Item | Item type |
|---|---|---|
| `heatpumpDhwTankTemp` | ESPAltherma Warmwasserspeicher Temperatur | Number:Temperature |
| `heatpumpPower` | ESPAltherma Elektrische Leistung | Number:Power |
| `heatpumpDhwBoost` | Pyaltherma Warmwasser-Boost | Switch |
| `heatpumpClimateControlPower` | Pyaltherma Heizung Ein/Aus | Switch |
| `heatpumpDhwPower` | Pyaltherma Warmwasser Ein/Aus | Switch |
| `heatpumpManagement` | Wärmepumpe Automatik | Group |
| `heatpumpDhwTempHeating` | Pyaltherma Warmwasser Solltemperatur | Number:Temperature |
| `heatpumpDhwManagement` | Wärmepumpe Warmwasser-Automatik | Switch |

</details>

`air-conditioner-quick` needs `boost-pill`, `pill-slider`, `power-pill`, `state-bar`.

<details>
<summary><code>air-conditioner-quick</code>: 7 props</summary>

| Prop | Item | Item type |
|---|---|---|
| `acSwitch` | Faikout Perfera Schalter | Switch |
| `acMode` | Faikout Perfera Modus | String |
| `acTemperature` | Faikout Perfera Temperatur | Number:Temperature |
| `acTemperatureSetpoint` | Faikout Perfera Solltemperatur | Number:Temperature |
| `acTimer` | Klimaanlage Timer | Number:Time |
| `acTimerSet` | Klimaanlage Timer eingestellt | Number:Time |
| `acPowerful` | Faikout Perfera Powerful | Switch |

</details>

`ventilation-quick` needs `pill-slider`, `state-bar`, `switch-row`.

<details>
<summary><code>ventilation-quick</code>: 5 props</summary>

| Prop | Item | Item type |
|---|---|---|
| `ventilationLevel` | ESPLyfterl Stufe | String |
| `netatmoWeatherstationCo2` | Netatmo Wetterstation CO2 | Number:Dimensionless |
| `ventilationTimer` | Lüftung Timer | Number:Time |
| `ventilationManagement` | Lüftung Automatik | Group |
| `ventilationTimerSet` | Lüftung Timer eingestellt | Number:Time |

</details>

`heatpump-control-quick` needs `boost-pill`, `pill-switch`, `state-bar`.

<details>
<summary><code>heatpump-control-quick</code>: 6 props</summary>

| Prop | Item | Item type |
|---|---|---|
| `heatpumpClimateControlPower` | Pyaltherma Heizung Ein/Aus | Switch |
| `heatpumpDhwPower` | Pyaltherma Warmwasser Ein/Aus | Switch |
| `heatpumpManagement` | Wärmepumpe Automatik | Group |
| `heatpumpDhwBoost` | Pyaltherma Warmwasser-Boost | Switch |
| `heatpumpDhwTankTemp` | ESPAltherma Warmwasserspeicher Temperatur | Number:Temperature |
| `heatpumpSmartGrid` | ESPAltherma Smart Grid | String |

</details>

`heatpump-indoor-quick` needs `boost-pill`, `pill-slider`, `pill-switch`, `state-bar`.

<details>
<summary><code>heatpump-indoor-quick</code>: 12 props</summary>

| Prop | Item | Item type |
|---|---|---|
| `heatpumpLeavingWaterTempAfterBuh` | ESPAltherma Vorlauftemperatur nach Heizstab | Number:Temperature |
| `heatpumpFlowSensor` | ESPAltherma Durchfluss | Number:VolumetricFlowRate |
| `heatpumpSmartGrid` | ESPAltherma Smart Grid | String |
| `heatpumpClimateControlPower` | Pyaltherma Heizung Ein/Aus | Switch |
| `heatpumpDhwPower` | Pyaltherma Warmwasser Ein/Aus | Switch |
| `heatpumpManagement` | Wärmepumpe Automatik | Group |
| `heatpumpDhwTempHeating` | Pyaltherma Warmwasser Solltemperatur | Number:Temperature |
| `heatpumpDhwTankTemp` | ESPAltherma Warmwasserspeicher Temperatur | Number:Temperature |
| `heatpumpDhwManagement` | Wärmepumpe Warmwasser-Automatik | Switch |
| `heatpumpDhwBoost` | Pyaltherma Warmwasser-Boost | Switch |
| `heatpumpLeavingWaterTempOffsetHeating` | Pyaltherma Vorlauf-Offset Heizen | Number:Temperature |
| `heatpumpLeavingWaterSetpoint` | ESPAltherma Vorlauf Sollwert | Number:Temperature |

</details>

<details>
<summary><code>heatpump-outdoor-quick</code>: 5 props</summary>

| Prop | Item | Item type |
|---|---|---|
| `heatpumpCircuitPower` | Wärmepumpe Leistung | Number:Power |
| `heatpumpInvFrequency` | ESPAltherma Verdichterfrequenz | Number:Frequency |
| `heatpumpExtAmbientTemp` | ESPAltherma Außentemperatur | Number:Temperature |
| `heatpumpHeatExchangerMidTemp` | ESPAltherma Wärmetauscher Mitte | Number:Temperature |
| `heatpumpOutdoorAirTemp` | ESPAltherma Außenluft Temperatur | Number:Temperature |

</details>

<details>
<summary><code>heatpump-refrigerant-quick</code>: 5 props</summary>

| Prop | Item | Item type |
|---|---|---|
| `heatpumpDischargePipeTemp` | ESPAltherma Heißgastemperatur | Number:Temperature |
| `heatpumpRefrigerantPressure` | ESPAltherma Kältemitteldruck | Number:Pressure |
| `heatpumpTargetDischargeTemp` | ESPAltherma Soll-Heißgastemperatur | Number:Temperature |
| `heatpumpRefrigerantTemp` | ESPAltherma Kältemittel flüssig | Number:Temperature |
| `heatpumpHeatExchangerMidTemp` | ESPAltherma Wärmetauscher Mitte | Number:Temperature |

</details>

`heatpump-circuit-quick` needs `pill-slider`.

<details>
<summary><code>heatpump-circuit-quick</code>: 6 props</summary>

| Prop | Item | Item type |
|---|---|---|
| `heatpumpLeavingWaterTempAfterBuh` | ESPAltherma Vorlauftemperatur nach Heizstab | Number:Temperature |
| `heatpumpInletWaterTemp` | ESPAltherma Rücklauftemperatur | Number:Temperature |
| `heatpumpLeavingWaterTempOffsetHeating` | Pyaltherma Vorlauf-Offset Heizen | Number:Temperature |
| `heatpumpLeavingWaterSetpoint` | ESPAltherma Vorlauf Sollwert | Number:Temperature |
| `heatpumpClimateControlPower` | Pyaltherma Heizung Ein/Aus | Switch |
| `heatpumpHeatingPowerAfterBuh` | ESPAltherma Heizleistung nach Heizstab | Number:Power |

</details>

<details>
<summary><code>upper-floor-quick</code>: 2 props</summary>

| Prop | Item | Item type |
|---|---|---|
| `acTemperature` | Faikout Perfera Temperatur | Number:Temperature |
| `tadoHumidity` | Tado Luftfeuchtigkeit | Number:Dimensionless |

</details>

<details>
<summary><code>ground-floor-quick</code>: 3 props</summary>

| Prop | Item | Item type |
|---|---|---|
| `heatpumpIndoorAmbientTemp` | ESPAltherma Raumtemperatur | Number:Temperature |
| `netatmoWeatherstationAtmosphericHumidity` | Netatmo Wetterstation Luftfeuchtigkeit | Number:Dimensionless |
| `netatmoWeatherstationCo2` | Netatmo Wetterstation CO2 | Number:Dimensionless |

</details>

<details>
<summary><code>heatpump-electric-quick</code>: 8 props</summary>

| Prop | Item | Item type |
|---|---|---|
| `heatpumpPower` | ESPAltherma Elektrische Leistung | Number:Power |
| `heatpumpEnergyToday` | ESPAltherma Energie heute | Number:Energy |
| `heatpumpElectricalPowerSpace` | ESPAltherma Elektrische Leistung Heizung | Number:Power |
| `heatpumpElectricalPowerDhw` | ESPAltherma Elektrische Leistung Warmwasser | Number:Power |
| `heatpumpElectricalPowerStandby` | ESPAltherma Elektrische Leistung Standby | Number:Power |
| `heatpumpEnergySpaceToday` | ESPAltherma Energie Heizung heute | Number:Energy |
| `heatpumpEnergyDhwToday` | ESPAltherma Energie Warmwasser heute | Number:Energy |
| `heatpumpEnergyStandbyToday` | ESPAltherma Energie Standby heute | Number:Energy |

</details>

<details>
<summary><code>heatpump-heat-quick</code>: 6 props</summary>

| Prop | Item | Item type |
|---|---|---|
| `heatpumpHeatPower` | ESPAltherma Heizleistung | Number:Power |
| `heatpumpHeatingEnergyToday` | ESPAltherma Heizenergie heute | Number:Energy |
| `heatpumpHeatingPowerSpace` | ESPAltherma Heizleistung Heizung | Number:Power |
| `heatpumpHeatingPowerDhw` | ESPAltherma Heizleistung Warmwasser | Number:Power |
| `heatpumpHeatingEnergySpaceToday` | ESPAltherma Heizenergie Heizung heute | Number:Energy |
| `heatpumpHeatingEnergyDhwToday` | ESPAltherma Heizenergie Warmwasser heute | Number:Energy |

</details>

<details>
<summary><code>heatpump-cop-quick</code>: 5 props</summary>

| Prop | Item | Item type |
|---|---|---|
| `heatpumpCop` | ESPAltherma COP | Number |
| `heatpumpDcop` | ESPAltherma Tages-COP | Number |
| `heatpumpExtAmbientTemp` | ESPAltherma Außentemperatur | Number:Temperature |
| `heatpumpDcopSpace` | ESPAltherma Tages-COP Heizung | Number |
| `heatpumpDcopDhw` | ESPAltherma Tages-COP Warmwasser | Number |

</details>


## Controls

The parts of the quick popups and of my device pages' controls.


### Segmented bar: `state-bar`

The states of one item as the segments of a bar, the current one filled in the colour; a tap sends a segment's state.
`options` holds `value=label` pairs separated by semicolons. With `byText` the segments are as wide as their labels, so
a long one such as *Entfeuchten* fits on a phone; Framework7's sliding highlight is sized for equal segments and is
hidden then. `color` may be an expression, e.g. grey while the device is off.

![Segmented bars](screenshots/state-bars.png)

```yaml
component: widget:state-bar
config:
  item: esplyfterl_level
  options: 1=1;2=2;3=3
  color: "#26a69a"
```

| Prop | Description | Type | Default |
|---|---|---|---|
| `item` | The item whose states the segments send | Item |  |
| `options` | value=label pairs separated by semicolons, e.g. 1=Niedrig;2=Mittel;3=Hoch | TEXT |  |
| `color` | Colour of the current segment as #rrggbb; may be an expression | TEXT | `#78909c` |
| `byText` | Segments as wide as their labels instead of equal widths | BOOLEAN |  |
| `flex` | CSS flex of the bar in a row, e.g. 1 1 240px | TEXT |  |
| `width` | CSS width of the bar | TEXT | `100%` |

### Switch tile: `switch-tile`

A plug or device as a small tile: its icon, *An* or *Aus*, the name and a value such as its power; a tap anywhere
switches it. While on it is tinted and outlined in its colour. Put several in a grid, e.g. `grid-template-columns:
repeat(auto-fill, minmax(120px, 1fr))`.

![Switch tiles](screenshots/switch-tiles.png)

```yaml
component: widget:switch-tile
config:
  item: coffee_machine_switch
  title: Kaffeemaschine
  icon: material:coffee
  color: "#8d6e63"
  value: =Math.round(Number(items.coffee_machine_power.numericState) || 0) + ' W'
```

| Prop | Description | Type | Default |
|---|---|---|---|
| `item` | The switch item | Item |  |
| `title` | Name of the plug or device | TEXT |  |
| `icon` | Icon, e.g. material:coffee (its state follows the item) | TEXT |  |
| `color` | Colour of the tile while on as #rrggbb | TEXT | `#78909c` |
| `value` | A line under the name, e.g. the power; usually an expression | TEXT |  |
| `energy` | A line under the value, e.g. today's energy; usually an expression; empty: none | TEXT |  |

### On/off pill: `power-pill`

A device's on and off as a wide pill: a white knob with the power symbol slides to the right and the pill fills with the
device colour while on, with `onText` in it (an expression, e.g. the mode it runs in); a tap anywhere switches. The plug
cards and the device pages switch with it.

![On/off pill](screenshots/power-pill.png)

```yaml
component: widget:power-pill
config:
  item: faikout_perfera_switch
  color: "#29b6f6"
  onText: ="An · " + items.faikout_perfera_mode.displayState
```

| Prop | Description | Type | Default |
|---|---|---|---|
| `item` | The switch item | Item |  |
| `color` | Device colour as #rrggbb, of the pill while on | TEXT | `#78909c` |
| `onText` | What the pill says while on, e.g. An · Lüften; usually an expression | TEXT | `An` |

### Boost pill: `boost-pill`

A boost that runs for a while, as a pill: its icon in a tinted circle, the name, what it does while it runs (`running`,
an expression) or *Aus*, and *Starten* or *Stoppen*; while it runs the pill fills with a gradient of the device colour
and rings pulse from the icon. A tap anywhere switches the item. My heat pump's hot-water boost and my air conditioner's
boost both carry a rocket.

![Boost pills](screenshots/boost-pills.png)

```yaml
component: widget:boost-pill
config:
  item: pyaltherma_dhw_powerful
  title: Warmwasser-Boost
  icon: material:rocket_launch
  color: "#fb8c00"
  running: ="läuft · Speicher " + items.espaltherma_dhw_tank_temp.displayState
```

| Prop | Description | Type | Default |
|---|---|---|---|
| `item` | The switch item | Item |  |
| `title` | Name of the boost | TEXT | `Boost` |
| `icon` | Icon, e.g. material:rocket_launch; a classic openHAB icon follows the item's state | TEXT | `material:bolt` |
| `color` | Device colour as #rrggbb | TEXT | `#fb8c00` |
| `running` | The line under the title while the boost runs; usually an expression | TEXT | `läuft` |

### Slider: `pill-slider`

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

| Prop | Description | Type | Default |
|---|---|---|---|
| `item` | The number item the slider sets | Item |  |
| `color` | Device colour as #rrggbb | TEXT | `#78909c` |
| `min` | The slider's lowest value | DECIMAL | `0` |
| `max` | The slider's highest value | DECIMAL | `100` |
| `step` | The slider's step | DECIMAL | `1` |
| `unit` | Unit on the label while dragging and of the command sent; must be the item's own (a difference in K sent to a °C item is taken as an absolute temperature) | TEXT |  |
| `title` | Title above the slider | TEXT |  |
| `icon` | The badge's icon, e.g. material:thermostat | TEXT | `material:tune` |
| `ring` | A ring around a timer icon instead of the icon, emptying as the item runs down to 0 | BOOLEAN |  |
| `ringFull` | What a full timer ring stands for, e.g. an expression on the minutes the timer was last set to; empty: the maximum | TEXT |  |
| `value` | The value to show, usually an expression on the item | TEXT |  |
| `valueColor` | Colour of the value where it is not the device colour; empty: the text colour | TEXT |  |
| `context` | A line under the title saying what the setting does, usually an expression | TEXT |  |
| `marks` | value=label pairs below the bar, separated by semicolons, e.g. 0=0;60=1 h;120=2 h | TEXT |  |
| `opacity` | e.g. 0.6 while the device is off | TEXT |  |
| `row` | A row of a page's or popup's controls, with their divider | BOOLEAN |  |

### Switch pill: `pill-switch`

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

| Prop | Description | Type | Default |
|---|---|---|---|
| `item` | The switch item | Item |  |
| `title` | Name of the switch, in the pill | TEXT |  |
| `icon` | Icon on the knob, of what it switches, e.g. material:shower | TEXT | `material:power_settings_new` |
| `color` | The card's colour as #rrggbb, of the pill while on | TEXT | `#78909c` |

### Switch row: `switch-row`

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

| Prop | Description | Type | Default |
|---|---|---|---|
| `item` | The switch item | Item |  |
| `title` | Name of the switch | TEXT |  |
| `icon` | The icon, e.g. material:eco | TEXT | `material:power_settings_new` |
| `color` | The card's colour as #rrggbb, of the switch while on | TEXT | `#78909c` |

## Energy flow

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


### Node: `flow-node`

A device in a ring, its animation driven by `power`: `pv` (a tilted module under a sun, both brighter with the power,
rays turning faster), `grid` (a pylon, red on import and green on export, dashes running along its wires), `home` (a
house whose windows glow and pulse with the consumption), `heat-pump` (an outdoor unit whose fan turns while
`frequency`, the compressor's, is above 0 Hz, faster from 30 and 55 Hz), `air-conditioner` (an indoor unit whose air
streams flow), `e-car` (a car with a bolt fading in and out while it charges), `battery` (filled to `soc`, red, orange
or green), `appliances` (an appliance's housing with sparkles for a front, the big one breathing and the small ones
twinkling while they run) and `ventilation` (a duct fan whose five blades turn above 5 W, faster with the power). The
ring has an opaque disc in the card colour under its tint, so dots running under it disappear.

![Flow nodes](screenshots/flow-node.gif)

| Prop | Description | Type | Default |
|---|---|---|---|
| `kind` | The device drawn | TEXT |  |
| `x` | Centre's x in the flow's viewBox | DECIMAL |  |
| `y` | Centre's y in the flow's viewBox | DECIMAL |  |
| `power` | The power in W; usually an expression on an item | TEXT |  |
| `soc` | The battery's state of charge in %; usually an expression | DECIMAL |  |
| `frequency` | The heat pump's compressor frequency in Hz, which turns its fan; usually an expression | DECIMAL |  |

### Line: `flow-link`

A line from (`x1`, `y1`) to (`x2`, `y2`) in `color`. While |`power`| exceeds `threshold` three dots run along it,
towards (`x2`, `y2`) while `forward` holds and back otherwise, at four speeds by the power; below the threshold the line
fades. The dots run a dot radius past both ends, so they slide out from under one node's rim and back under the other's.
`color` and `forward` may be expressions, e.g. the grid's line green and outward while it exports.

![Flow lines between three nodes](screenshots/flow-link.gif)

| Prop | Description | Type | Default |
|---|---|---|---|
| `x1` | Start point's x in the flow's viewBox | DECIMAL |  |
| `y1` | Start point's y in the flow's viewBox | DECIMAL |  |
| `x2` | End point's x in the flow's viewBox | DECIMAL |  |
| `y2` | End point's y in the flow's viewBox | DECIMAL |  |
| `color` | The link's colour as #rrggbb; may be an expression | TEXT | `#78909c` |
| `power` | The power in W; usually an expression on an item | TEXT |  |
| `forward` | The dots run from (x1, y1) to (x2, y2) while it holds, else back; usually an expression | BOOLEAN |  |
| `threshold` | The power in W above which the dots run | DECIMAL | `10` |

### Share ring: `flow-share-ring`

A ring around (`x`, `y`) filled to `part` / `whole`, the percentage inside and `title` with *heute* beside it; the
energy flow shows today's self-consumption and self-sufficiency with it.

![Share rings](screenshots/flow-share-rings.png)

```yaml
component: widget:flow-share-ring
config:
  x: 40
  y: 40
  title: Eigenverbrauch
  part: =Number(items.photovoltaics_own_ec_day.numericState) || 0
  whole: =Number(items.huawei_inverter_e_day.numericState) || 0
```

| Prop | Description | Type | Default |
|---|---|---|---|
| `x` | Centre's x in the flow's viewBox | DECIMAL |  |
| `y` | Centre's y in the flow's viewBox | DECIMAL |  |
| `title` | Text beside the ring, e.g. Eigenverbrauch | TEXT |  |
| `part` | The part, e.g. today's PV energy used at home; usually an expression | TEXT |  |
| `whole` | The whole, e.g. today's PV energy; usually an expression | TEXT |  |

## Appliances

The appliances card's parts.

### Appliance icon: `appliance-icon`

A washer, dryer or dishwasher (`kind`: `washer`, `dryer`, `dish-washer`) drawn inside a ring: the drum's laundry, the
dryer's paddles or the dishwasher's spray arm turn while `running` holds, droplets rise in the dishwasher. While it runs
the ring fills with `progress`, or pulses where there is none.

![Appliance icons](screenshots/appliance-icon.gif)

```yaml
component: widget:appliance-icon
config:
  kind: dryer
  running: =items.miele_tumble_dryer_twc560wp_program_progress.state !== 'UNDEF'
  progress: =Number(items.miele_tumble_dryer_twc560wp_program_progress.numericState) || 0
  size: 72
```

| Prop | Description | Type | Default |
|---|---|---|---|
| `kind` | The appliance drawn | TEXT |  |
| `running` | Whether it runs; usually an expression | BOOLEAN |  |
| `progress` | Program progress in %, filling the ring while it runs; empty: the ring pulses | DECIMAL |  |
| `color` | Colour of the ring as #rrggbb | TEXT | `#1e88e5` |
| `size` | Width and height in px | INTEGER | `72` |

### Appliance tile: `appliance-tile`

An appliance as a tile of the appliances card: its icon, name and state; a tap opens the page `popup` as a popup. A
Miele machine comes with the items of its program (`progress`, `state`, `program`, `phase`, `finished`, `remaining`, as
the Miele binding provides them): the ring shows the progress, the state chip is blue while it runs, green when it is
finished and grey otherwise, beside it the remaining time, and program, phase and end time below. A machine behind a
metered plug comes with its `power` and an optional `done` switch: it runs above 10 W, is finished while `done` is on,
and its ring pulses. Put the tiles in a grid, e.g. two columns.

![Appliance tiles](screenshots/appliances-card.png)

```yaml
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
```

Needs `appliance-icon`.

| Prop | Description | Type | Default |
|---|---|---|---|
| `kind` | The appliance drawn | TEXT |  |
| `title` | The appliance's name | TEXT |  |
| `popup` | The uid of the page a tap opens as a popup | TEXT |  |
| `progress` | Miele item _program_progress, e.g. miele_washing_machine_program_progress; set for a Miele machine | Item |  |
| `state` | Miele item _operation_state, e.g. miele_washing_machine_operation_state; set for a Miele machine | Item |  |
| `program` | Miele item _active_program, e.g. miele_washing_machine_active_program; set for a Miele machine | Item |  |
| `phase` | Miele item _program_phase, e.g. miele_washing_machine_program_phase; set for a Miele machine | Item |  |
| `finished` | Miele item _program_finished_time, e.g. miele_washing_machine_program_finished_time; set for a Miele machine | Item |  |
| `remaining` | Miele item _program_remaining_time, e.g. miele_washing_machine_program_remaining_time; set for a Miele machine | Item |  |
| `power` | The plug's power item, for a machine without program data | Item |  |
| `done` | Switch item that is on while the plug machine is finished | Item |  |

## Weather

### Weather icon: `weather-icon`

The weather drawn from a symbol in the style of the energy flow's nodes: the sun, its rays turning slowly, or the moon
while `day` is false. The sky in five levels: `clear` alone, `fair` with a small cloud, `partly` behind a cloud of its
size, `mostly` peeking out behind a large cloud with a darker one behind it, `overcast` as two clouds; `veil` behind
three thin streaks; a raised cloud over `fog`, falling `rain`, drifting white `snow` or a flickering bolt (`thunder`),
with the sun peeking out at its top left for showers (`rain_sun`, `snow_sun`, `thunder_sun`). Nothing for any other
value, as an item is `NULL` after a restart. My rule works the symbol out from Open-Meteo: a day's sky from the share of
its daylight the sun shines, an hour's from the cloud layers, the high ones counted half. My weather bar shows the
present weather with it, and my weather page each day's, beside its hours of sunshine with their share of the daylight
and the strongest wind with an arrow of its dominant direction and its compass point, above a chart of the next 60
hours: temperature with the weather drawn above it and over the precipitation of each hour, the wind below with arrows
of its direction, both every three hours; ECharts takes no widget, so the drawings there are this widget's layers as
still SVG images. That page is part of my installation, not a widget of this repository; its rule writes the forecast as
JSON into String items, and the chart reads them through an `oh-data-series` whose `data` is an expression such as
`=JSON.parse(items.weather_hourly.state).map((r) => [r[0] * 1000, r[1]])`, with no persistence involved. The warnings in
the screenshots are demo values.

| Light | Dark |
|---|---|
| ![Weather page: warnings, days and chart](screenshots/weather-forecast.png) | ![Weather page in dark mode](screenshots/weather-forecast-dark.png) |

```yaml
component: widget:weather-icon
config:
  symbol: =items.weather_symbol.state
  day: =items.weather_is_day.state !== 'OFF'
  size: 36
```

| Prop | Description | Type | Default |
|---|---|---|---|
| `symbol` | The weather drawn: clear, fair, partly, mostly, overcast, veil, fog, rain, snow, thunder, rain_sun, snow_sun, thunder_sun; usually an expression | TEXT |  |
| `day` | Whether the sun is up; false draws the moon; usually an expression | BOOLEAN | `true` |
| `size` | Width and height in px | INTEGER | `36` |

## Plug cards

Four cards for a metered plug, built from one item prefix: `<prefix>_power`, `_switch`, `_energy_today`,
`_energy_total`, `_voltage`, `_current`, `_power_factor`, `_apparent_power` and `_reactive_power`, as a Tasmota plug
provides them. On a device page they stand two by two. `plug-card` also covers devices that are not plugs: give it
the device's `title`, hide the switch with `controllable: false`, or take the switch from another item with `switch`.
Every value tile carries a large pale icon of what it shows.

![Plug cards](screenshots/plug-cards.png)

### `plug-card`

Now: power, on/off pill, energy today and total. Needs `item-popup`, `power-pill`, `value-tile`.

| Prop | Description | Type | Default |
|---|---|---|---|
| `prefix` | Name prefix of the plug's items: `<prefix>_power`, _switch, _energy_today, _energy_total, _voltage, _current, _power_factor, _apparent_power, _reactive_power | TEXT |  |
| `title` | Card title, the device's name where the card is not a plug | TEXT | `Steckdose` |
| `icon` | Device icon, e.g. material:coffee | TEXT | `material:power` |
| `color` | Device colour as #rrggbb | TEXT | `#8d6e63` |
| `controllable` | Show the plug's switch | BOOLEAN | `true` |
| `note` | Small print under the energies, hidden when empty | TEXT |  |
| `switch` | The switch's item where it is not `<prefix>_switch`, e.g. a shared meter's | Item |  |

### `plug-power-card`

Power over the day.

| Prop | Description | Type | Default |
|---|---|---|---|
| `prefix` | Name prefix of the plug's items: `<prefix>_power`, _switch, _energy_today, _energy_total, _voltage, _current, _power_factor, _apparent_power, _reactive_power | TEXT |  |
| `color` | Device colour as #rrggbb | TEXT | `#8d6e63` |

### `plug-energy-days-card`

Energy per day of the month.

| Prop | Description | Type | Default |
|---|---|---|---|
| `prefix` | Name prefix of the plug's items: `<prefix>_power`, _switch, _energy_today, _energy_total, _voltage, _current, _power_factor, _apparent_power, _reactive_power | TEXT |  |
| `color` | Device colour as #rrggbb | TEXT | `#8d6e63` |

### `plug-electric-card`

Voltage, current, power factor, apparent and reactive power. Needs `item-popup`, `value-tile`.

| Prop | Description | Type | Default |
|---|---|---|---|
| `prefix` | Name prefix of the plug's items: `<prefix>_power`, _switch, _energy_today, _energy_total, _voltage, _current, _power_factor, _apparent_power, _reactive_power | TEXT |  |
| `title` | Card title | TEXT | `Elektrisch` |

## Item popup: `item-popup`

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

| Prop | Description | Type | Default |
|---|---|---|---|
| `item` | The item to show | Item |  |
| `title` | Title of the popup, the tile's | TEXT |  |
| `color` | Colour of the course as #rrggbb | TEXT | `#5c6bc0` |
| `kind` | number: its course as a line; state: a band of its states; none: only the value | TEXT | `number` |
| `states` | value=label pairs, comma-separated, for the band of states | TEXT |  |

## Value tile: `value-tile`

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

| Prop | Description | Type | Default |
|---|---|---|---|
| `title` | Title above the value | TEXT |  |
| `value` | The text to show, usually an expression on an item | TEXT |  |
| `icon` | The pale icon, e.g. material:thermostat | TEXT | `material:info` |
| `color` | Colour of the value and the icon as #rrggbb; empty: the text colour | TEXT |  |
| `iconColor` | Colour of the icon where the value keeps the text colour, as #rrggbb | TEXT |  |
| `item` | The item whose popup a tap opens; empty: no tap | Item |  |
| `action` | popup: the item popup (widget item-popup); options: the item's command options | TEXT | `popup` |
| `kind` | What the item popup shows: number, state or none | TEXT | `number` |
| `states` | value=label pairs, comma-separated, for the item popup's band of states | TEXT |  |
| `wrap` | A long text wraps across the whole row of the grid instead of being cut | BOOLEAN |  |
| `fontSize` | The tile's base size, e.g. 1.1em to grow with its card; default 14px | TEXT |  |

## About these widgets

The widgets are generated from Python by the script that builds my whole MainUI, which keeps the cards of the
dashboard and the device pages consistent; that is why their YAML is dense and machine-formatted. The script and its
tools are in [`scripts/openhab-ui/`](scripts/openhab-ui/): `dashboard.py`, the headless-Chrome tools behind the
screenshots, and the one-off JSONDB changes in `applied/`. The cards are
built from the smaller widgets wherever a part stands in more than one place or makes sense on its own, so a fix in
one widget reaches every place it stands. The widgets in this repository are exported from that script unchanged.
