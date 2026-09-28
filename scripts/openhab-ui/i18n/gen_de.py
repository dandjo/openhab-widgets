"""German for the plain texts of the generated pages (overview and popups); applied after the pages are built."""
GEN_DE = {
    # page and card titles
    "Overview": "Übersicht", "Controls": "Steuerung", "Energy Flow": "Energiefluss", "Appliances": "Haushaltsgeräte",
    "Electricity Price": "Strompreis", "Heatpump": "Wärmepumpe", "Energy per Day": "Energie pro Tag",
    "PV Production per Day": "PV-Ertrag pro Tag", "Temperatures": "Temperaturen", "Temperature": "Temperatur",
    "Now": "Jetzt", "Today": "Heute", "Power": "Leistung", "Program": "Programm",
    "Photovoltaics": "Photovoltaik", "Power Meter": "Stromzähler", "Home": "Haus", "Air Conditioning": "Klimaanlage",
    "Energy Storage": "Batteriespeicher", "E-Car": "E-Auto", "Outdoor Unit": "Außengerät", "Altherma 3": "Altherma 3",
    "Three-Way Valve": "3-Wege-Ventil", "DHW Tank": "Warmwasserspeicher", "Space Heating": "Heizkreis",
    "Washing Machine 1": "Waschmaschine 1", "Washing Machine 2": "Waschmaschine 2", "Tumble Dryer": "Wäschetrockner",
    "Dishwasher": "Geschirrspüler",
    # energy flow and heat pump drawing
    "Self-consumption": "Eigenverbrauch", "Self-sufficiency": "Autarkie", "today": "heute", "Defrosting": "Abtauen",
    "Upper Floor": "Obergeschoss", "Ground Floor": "Erdgeschoss", "Radiators": "Heizkörper", "Basement": "Keller",
    # heat pump panel and controls
    "Electrical": "Elektrisch", "Heat": "Wärme", "COP": "COP", "COP Space": "COP Heizung", "COP DHW": "COP Warmwasser",
    "COP Total": "COP gesamt", "Electricity": "Strom", "Heizung": "Heizung", "Warmwasser": "Warmwasser", "Standby": "Standby",
    "Smart Grid": "Smart Grid", "Powerful DHW": "Warmwasser-Boost", "Ventilation": "Lüftung", "Fan": "Lüfter",
    "Setpoint": "Soll", "Mode": "Modus", "Timer": "Timer", "Auto": "Auto", "Aus": "Aus",
    "Coffee Machine": "Kaffeemaschine", "Bicycle Batteries": "Fahrradakkus", "Office 1": "Büro 1", "Office 2": "Büro 2",
    "Terrace Light": "Terrassenlicht",
    # price
    "per kWh all-in": "pro kWh gesamt", "EUR/kWh": "EUR/kWh", "All-in price": "Gesamtpreis", "Total Net": "Gesamt netto",
    "Market Gross": "Markt brutto", "Market Net": "Markt netto",
    # consumption, daily energy, calendar, temperatures
    "Consumers": "Verbraucher", "From PV": "Aus PV", "From Grid": "Aus dem Netz", "PV Production": "PV-Ertrag",
    "kWh": "kWh", "Tag": "Tag", "Indoor": "Innen", "Outdoor": "Außen", "Heatpump sensor": "Fühler der Wärmepumpe",
    "°C": "°C", "W": "W", "Hz": "Hz", "%": "%",
    # appliance popups
    "Energy Today": "Energie heute", "Energy Total": "Energie gesamt", "Phase": "Phase", "Program Energy": "Energie Programm",
    "Delayed Start": "Startvorwahl", "Spin Speed": "Schleuderdrehzahl", "Program Water": "Wasser Programm",
    "Drying Target": "Trocknungsziel",
    # energy flow popups
    "Input Power": "Eingangsleistung", "Output Power": "Ausgangsleistung", "Peak Today": "Spitze heute",
    "String 1": "String 1", "String 2": "String 2", "Inverter": "Wechselrichter", "Production": "Ertrag",
    "Self-used": "Selbst verbraucht", "Fed In": "Eingespeist", "Total": "Gesamt", "PV": "PV", "Phase A": "Phase A",
    "Phase B": "Phase B", "Phase C": "Phase C", "Frequency": "Frequenz", "Price All-in": "Strompreis gesamt",
    "Imported": "Bezogen", "Exported": "Eingespeist", "Grid": "Netz", "Consumption": "Verbrauch",
    "Heating": "Heizleistung", "Operation": "Betrieb", "Valve": "Ventil", "Leaving Water": "Vorlauf",
    "Inlet Water": "Rücklauf", "DHW": "Warmwasser", "Climate Control": "Heizung", "DHW Management": "Warmwasser-Automatik",
    "DHW Setpoint": "Warmwasser Soll", "Leaving Water Offset": "Vorlauf-Offset", "Room": "Raum", "Compressor": "Verdichter",
    "Fan Speed": "Lüfterdrehzahl", "Powerful": "Boost", "Eco": "Eco", "Quiet": "Leise", "Comfort": "Komfort",
    "Streamer": "Streamer", "Swing Horizontal": "Schwenken horizontal", "Swing Vertical": "Schwenken vertikal",
    "State of Charge": "Ladestand", "Status": "Status", "Charged": "Geladen", "Discharged": "Entladen",
    "Voltage": "Spannung", "Current": "Strom",
    "Calculated: the air conditioning's plug minus the air conditioner's own power from Faikin, including a few watts "
    "of standby and an LED light.": "Berechnet: die Steckdose der Klimaanlage minus deren eigene Leistung laut Faikin, "
    "samt einigen Watt Standby und einem LED-Licht.",
    # heat pump popups
    "Inverter Current": "Inverter-Strom", "Defrost": "Abtauen", "Discharge Pipe": "Heißgas", "Heat Exchanger": "Wärmetauscher",
    "Refrigerant": "Kältemitteldruck", "Flow": "Durchfluss", "Pump": "Pumpe", "Water Pressure": "Wasserdruck",
    "Before Backup Heater": "Vor Heizstab", "LW Setpoint": "Vorlauf Soll", "Backup Heater": "Heizstab",
    "Error Code": "Fehlercode", "Position": "Stellung", "Indoor Operation": "Innengerät", "Electrical Space": "Elektrisch Heizung",
    "Electrical DHW": "Elektrisch Warmwasser", "Space": "Heizung", "Tank": "Speicher", "Effect Heater": "Zusatzheizung",
    "Reheat": "Nachheizen", "Storage Eco": "Speicher Eco", "Room Setpoint": "Raum Soll",
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
            elif val not in GEN_DE.values():
                missing.add(val)
    if isinstance(cfg.get("icon"), str) and cfg["icon"] in ICONS:
        cfg["icon"] = ICONS[cfg["icon"]]
    for key in ("xAxis", "yAxis"):
        pass
    for slot in node.get("slots", {}).values():
        germanize(slot, missing)
