"""English → German labels for homepi's openHAB: device names, measurements and fixed texts."""

# device and source names, longest first when matching a label prefix
DEVICES = {
    "Air Conditioning": "Klimaanlage", "Air-conditioning": "Klimaanlage",
    "Bicycle Batteries": "Fahrradakkus", "Coffee Machine": "Kaffeemaschine", "Dishwasher": "Geschirrspüler",
    "E-Car": "E-Auto", "Heatpump": "Wärmepumpe", "Living Room Entertainment": "Wohnzimmer Medien",
    "Network": "Netzwerk", "Office 1": "Büro 1", "Office 2": "Büro 2", "Refrigerator": "Kühlschrank",
    "Terrace Light": "Terrassenlicht", "Tumble Dryer": "Wäschetrockner", "Ventilation": "Lüftung",
    "Washing Machine 1": "Waschmaschine 1", "Washing Machine 2": "Waschmaschine 2", "Washing Machine": "Waschmaschine",
    "Water Meter": "Wasserzähler", "Photovoltaics": "Photovoltaik", "Home": "Haus", "SmartPi": "SmartPi",
    "Huawei Inverter Power Meter": "Stromzähler", "Huawei Inverter Energy Storage Unit 1": "Batteriespeicher Einheit 1",
    "Huawei Inverter Energy Storage": "Batteriespeicher", "Huawei Inverter": "Wechselrichter",
    "ESPAltherma": "ESPAltherma", "Pyaltherma": "Pyaltherma", "Faikout Perfera": "Faikout Perfera",
    "ESPLyfterl": "ESPLyfterl", "EPEX Spot aWATTar": "Strompreis", "EPEX Spot": "Strompreis",
    "Miele Washing Machine WWG360": "Miele Waschmaschine WWG360", "Miele Tumble Dryer TWC560WP": "Miele Wäschetrockner TWC560WP",
    "Miele Dishwasher G7465": "Miele Geschirrspüler G7465", "Miele Dishwasher ": "Miele Geschirrspüler",
    "Miele Washing Machine": "Miele Waschmaschine", "Miele Tumble Dryer": "Miele Wäschetrockner",
    "Miele Dishwasher": "Miele Geschirrspüler", "Netatmo Weatherstation": "Netatmo Wetterstation",
    "Netatmo Weather Station": "Netatmo Wetterstation", "Netatmo Outdoor Module": "Netatmo Außenmodul",
    "Netatmo Outdoor": "Netatmo Außenmodul", "Netatmo": "Netatmo", "Tado Air Conditioning": "Tado Klimaanlage",
    "Tado Home": "Tado Zuhause", "Tado": "Tado", "Vu+ Uno 4k": "Vu+ Uno 4k", "Energy Daily": "Energie täglich",
    "Energy Storage": "Batteriespeicher", "Power Meter": "Stromzähler", "Smart Meter": "Stromzähler",
}

# measurements, states and other label parts; also used for whole short texts
TERMS = {
    # electrical
    "Power": "Leistung", "Active Power": "Wirkleistung", "Apparent Power": "Scheinleistung",
    "Reactive Power": "Blindleistung", "Power Factor": "Leistungsfaktor", "Current": "Strom", "Voltage": "Spannung",
    "Frequency": "Frequenz", "Energy": "Energie", "Energy Today": "Energie heute", "Energy Total": "Energie gesamt",
    "Energy Day": "Energie heute", "Switch": "Schalter", "Unit Power": "Geräteleistung", "Power Switch": "Ein/Aus",
    "Power State": "Betriebszustand", "Electrical Power": "Elektrische Leistung", "Electrical Energy": "Elektrische Energie",
    "Input Power": "Eingangsleistung", "Storage Power": "Speicherleistung", "Unit 1 Power": "Einheit 1 Leistung",
    "AC Current": "Wechselstrom", "AC Voltage": "Wechselspannung", "DC Current": "Gleichstrom", "DC Power": "DC-Leistung",
    "DC Voltage": "Gleichspannung", "Cosine Φ": "Cosinus φ", "Efficiency": "Wirkungsgrad",
    # generic
    "Finished": "Fertig", "Timer": "Timer", "Management": "Automatik", "Level": "Stufe", "Mode": "Modus",
    "Modes": "Modi", "Status": "Status", "Error": "Fehler", "Error Code": "Fehlercode", "Info": "Info",
    "Temperature": "Temperatur", "Temperatures": "Temperaturen", "Humidity": "Luftfeuchtigkeit", "Timestamp": "Zeitstempel",
    "Controls": "Steuerung", "Parameter": "Parameter", "Operations": "Betrieb", "Setpoints": "Sollwerte",
    "Storage": "Speicher", "Unit 1": "Einheit 1", "Consumption Today": "Verbrauch heute", "Consumption Total": "Verbrauch gesamt",
    "Energy Consumption": "Energieverbrauch", "Energy Consumption Today": "Verbrauch heute",
    "Energy Production Today": "Einspeisung heute", "Title": "Titel", "Description": "Beschreibung", "Channel": "Sender",
    "Home Page": "Startseite", "Home Consumption": "Hausverbrauch", "Electricity": "Strom", "Equipment": "Geräte",
    "Quick Controls": "Schnellzugriff", "Sitemap": "Sitemap", "Forecast": "Prognose", "Grid": "Netz", "Indoor": "Innen",
    "Outdoor": "Außen", "Strings": "Strings", "EUR/kWh": "EUR/kWh",
    # plug extras
    "Humidty Management": "Feuchte-Automatik", "Humidity Management": "Feuchte-Automatik",
    "CO2 Management": "CO2-Automatik", "Temperature Management": "Temperatur-Automatik",
    "DHW Management": "Warmwasser-Automatik", "Watchdog": "Überwachung",
    # heat pump (ESPAltherma, Pyaltherma, pages)
    "3-Way Valve Mode": "3-Wege-Ventil", "3-Way Valve": "3-Wege-Ventil",
    "Backup Heater (BUH) Step 1 Mode": "Heizstab Stufe 1", "Backup Heater (BUH) Step 2 Mode": "Heizstab Stufe 2",
    "Backup Heater (BUH) 1": "Heizstab Stufe 1", "Backup Heater (BUH) 2": "Heizstab Stufe 2", "BUH 1": "Heizstab 1",
    "BUH 2": "Heizstab 2", "Booster Heater (BSH) Mode": "Zusatzheizung Speicher", "Booster Heater (BSH)": "Zusatzheizung Speicher",
    "BSH": "Zusatzheizung Speicher", "COP": "COP", "COP DHW": "COP Warmwasser", "COP Space": "COP Heizung",
    "DCOP": "Tages-COP", "DCOP DHW": "Tages-COP Warmwasser", "DCOP Space": "Tages-COP Heizung",
    "Coefficient Of Performance": "Leistungszahl", "Daily Coefficient Of Performance": "Tages-Leistungszahl",
    "DHW": "Warmwasser", "DHW Setpoint": "Warmwasser Sollwert", "DHW Tank Temperature": "Warmwasserspeicher Temperatur",
    "Domestic Hot Water": "Warmwasser", "Defrost Operation": "Abtauen", "Defrost": "Abtauen",
    "Demand Signal": "Anforderungssignal", "Discharge Pipe Temperature": "Heißgastemperatur", "Discharge Pipe": "Heißgas",
    "Electrical Power DHW": "Elektrische Leistung Warmwasser", "Electrical Power Space": "Elektrische Leistung Heizung",
    "Electrical Power Standby": "Elektrische Leistung Standby", "Emergency Active": "Notbetrieb", "Emergency": "Notbetrieb",
    "Energy DHW Today": "Energie Warmwasser heute", "Energy Space Today": "Energie Heizung heute",
    "Energy Standby Today": "Energie Standby heute", "Error Detailed Code": "Fehler Detailcode", "Error Type": "Fehlertyp",
    "External Ambient Temperature": "Außentemperatur", "External Ambient": "Außentemperatur",
    "Flow Sensor (l/min)": "Durchfluss", "Flow Sensor": "Durchfluss", "Flow Rate": "Durchfluss",
    "Freeze Protection": "Frostschutz", "Heat Exchanger Mid Temperature": "Wärmetauscher Mitte", "Heat Exchanger Mid": "Wärmetauscher Mitte",
    "Heating Energy DHW Today": "Heizenergie Warmwasser heute", "Heating Energy Space Today": "Heizenergie Heizung heute",
    "Heating Energy Today": "Heizenergie heute", "Heating Energy": "Heizenergie", "Heating Power": "Heizleistung",
    "Heating Power After BUH": "Heizleistung nach Heizstab", "Heating Power Before BUH": "Heizleistung vor Heizstab",
    "Heating Power (after BUH)": "Heizleistung nach Heizstab", "Heating Power (before BUH)": "Heizleistung vor Heizstab",
    "Heating (after BUH)": "Heizleistung nach Heizstab", "Heating (before BUH)": "Heizleistung vor Heizstab",
    "Heating Power DHW": "Heizleistung Warmwasser", "Heating Power Space": "Heizleistung Heizung",
    "Heating DHW Today": "Heizenergie Warmwasser heute", "Heating Space Today": "Heizenergie Heizung heute",
    "Heating Today": "Heizenergie heute", "Heating Circuit Temperatures": "Heizkreis-Temperaturen",
    "IU Operation Mode": "Innengerät Betriebsart", "IU Operation": "Innengerät Betrieb", "OU Operation": "Außengerät Betrieb",
    "Indoor Ambient Temperature": "Raumtemperatur", "Indoor Ambient": "Raumtemperatur",
    "Inlet Water Temperature": "Rücklauftemperatur", "Inlet Water": "Rücklauf", "Inverter Frequency": "Verdichterfrequenz",
    "Inverter Primary Current": "Inverter Primärstrom", "Inverter Secondary Current": "Inverter Sekundärstrom",
    "Inverter Voltage N-Phase": "Inverter Spannung N-Phase", "Inverter Current": "Inverter Strom", "Inverter": "Wechselrichter",
    "Leaving Water Setpoint": "Vorlauf Sollwert", "Leaving Water Setpoint (add)": "Vorlauf Sollwert (Zusatz)",
    "Leaving Water Temperature After BUH": "Vorlauftemperatur nach Heizstab",
    "Leaving Water Temperature Before BUH": "Vorlauftemperatur vor Heizstab",
    "Leaving Water (after BUH)": "Vorlauf nach Heizstab", "Leaving Water (before BUH)": "Vorlauf vor Heizstab",
    "LW (after BUH)": "Vorlauf nach Heizstab", "LW (before BUH)": "Vorlauf vor Heizstab", "LW Offset": "Vorlauf-Offset",
    "LW Setpoint": "Vorlauf Sollwert", "LW Setpoint (add)": "Vorlauf Sollwert (Zusatz)",
    "Low Noise Control": "Geräuscharmer Betrieb", "Oil Return Operation": "Ölrückführung", "Oil Return": "Ölrückführung",
    "Operation Mode": "Betriebsart", "Outdoor Air Temperature": "Außenluft Temperatur", "Outdoor Air": "Außenluft",
    "Powerful DHW Operation": "Warmwasser-Boost aktiv", "Powerful DHW": "Warmwasser-Boost",
    "Pressure Equalizing Operation": "Druckausgleich", "Pressure Equalizing": "Druckausgleich",
    "Pressure Sensor Temperature": "Drucksensor Temperatur", "Refrigerant Pressure Sensor": "Kältemitteldruck",
    "Refrigerant Pressure": "Kältemitteldruck", "Refrigerant Temperature Liquid Side": "Kältemittel flüssig",
    "Refrigerant Liquid Side": "Kältemittel flüssig", "Refrigerants": "Kältemittel", "Reheat": "Nachheizen",
    "Restart Standby": "Neustart-Standby", "Room Temperature Setpoint": "Raumtemperatur Sollwert", "Room Setpoint": "Raum Sollwert",
    "Silent Mode": "Flüstermodus", "Smart Grid": "Smart Grid", "Space Heating Operation": "Heizbetrieb",
    "Space Heating": "Heizbetrieb", "Startup Control": "Anlaufsteuerung", "Storage Comfort Mode": "Speicher Komfortmodus",
    "Storage Eco Mode": "Speicher Eco-Modus", "System OFF": "System aus", "Target Delta T Heating": "Soll-Spreizung Heizen",
    "Target Discharge Temperature": "Soll-Heißgastemperatur", "Target Discharge": "Soll-Heißgas",
    "Thermal Protector BSH": "Thermoschutz Zusatzheizung", "Thermal Protector BUH": "Thermoschutz Heizstab",
    "Thermostat Switch": "Thermostatschalter", "Water Pressure": "Wasserdruck", "Water Pump Operation": "Umwälzpumpe",
    "Water Pump Signal": "Umwälzpumpe Signal", "Water Pump": "Umwälzpumpe", "Waterpump": "Umwälzpumpe",
    "ATTR": "ATTR", "Climate Control Power": "Heizung Ein/Aus", "Climate Control": "Heizung Ein/Aus",
    "DHW Power": "Warmwasser Ein/Aus", "DHW Powerful": "Warmwasser-Boost", "DHW Target Temp": "Warmwasser Zieltemperatur",
    "DHW Temp": "Warmwasser Temperatur", "DHW Temp Heating": "Warmwasser Solltemperatur", "Indoor Temp": "Innentemperatur",
    "Leaving Water Temp Current": "Vorlauf aktuell", "Leaving Water Temp Offset Heating": "Vorlauf-Offset Heizen",
    "Outdoor Temp": "Außentemperatur", "Heatpump SG": "Wärmepumpe SG", "Heatpump DHW": "Wärmepumpe Warmwasser",
    "Heatpump Indoor": "Wärmepumpe innen", "Heatpump Outdoor": "Wärmepumpe außen",
    # air conditioner
    "Comfort Mode": "Komfortmodus", "Compressor Frequency": "Verdichterfrequenz", "Eco Mode": "Eco-Modus",
    "Fan": "Lüfter", "Fan Speed": "Lüfterdrehzahl", "Liquid Temperature": "Flüssigkeitstemperatur",
    "Outdoor Temperature": "Außentemperatur", "Powerful": "Powerful", "Powerful Mode": "Powerful-Modus",
    "Quiet Mode": "Leisemodus", "Restart": "Neustart", "Restart Faikout": "Faikout neu starten",
    "Restart Faikout []": "Faikout neu starten []", "Streamer Mode": "Streamer", "Swing Horizontal": "Schwenken horizontal",
    "Swing Vertical": "Schwenken vertikal", "Temperature Setpoint": "Solltemperatur", "Tempearture Setpoint": "Solltemperatur",
    "Indoor Temperature": "Innentemperatur", "Air Conditioning Indoor": "Klimaanlage innen",
    "Air Conditioning Outdoor": "Klimaanlage außen", "Plug (Air Conditioning)": "Steckdose (Klimaanlage)",
    "Calculated from the Air Conditioning Plug": "Berechnet aus der Steckdose der Klimaanlage",
    # inverter, storage, meter
    "Active Peak Of Current Day": "Spitzenleistung heute", "Active Peak Today": "Spitzenleistung heute", "Peak Today": "Spitze heute",
    "Device Status": "Gerätestatus", "E-Day": "Ertrag heute", "E-Total": "Ertrag gesamt", "Internal Temperature": "Innentemperatur",
    "Optimizers Online": "Optimierer online", "Optimizers Total": "Optimierer gesamt",
    "PV1 Current": "PV1 Strom", "PV1 Power": "PV1 Leistung", "PV1 Voltage": "PV1 Spannung",
    "PV2 Current": "PV2 Strom", "PV2 Power": "PV2 Leistung", "PV2 Voltage": "PV2 Spannung",
    "Phase A Current": "Phase A Strom", "Phase A Voltage": "Phase A Spannung", "Phase A Active Power": "Phase A Wirkleistung",
    "Phase B Current": "Phase B Strom", "Phase B Voltage": "Phase B Spannung", "Phase B Active Power": "Phase B Wirkleistung",
    "Phase C Current": "Phase C Strom", "Phase C Voltage": "Phase C Spannung", "Phase C Active Power": "Phase C Wirkleistung",
    "Shutdown": "Abschaltung", "Shutdown Time": "Abschaltzeit", "Startup": "Start", "Startup Time": "Startzeit",
    "Modbus TCP": "Modbus TCP", **{f"Poller {n}": f"Poller {n}" for n in range(101, 109)}, "Bus Current": "Busstrom", "Bus Voltage": "Busspannung",
    "Day Charge": "Ladung heute", "Day Discharge": "Entladung heute", "Total Charge": "Ladung gesamt",
    "Total Discharge": "Entladung gesamt", "Charged Today": "Geladen heute", "Charged Total": "Geladen gesamt",
    "Discharged Today": "Entladen heute", "Discharged Total": "Entladen gesamt", "Forced Charging Period": "Zwangsladedauer",
    "Forcible Charge Power": "Zwangsladeleistung", "Forcible Charge/Discharge": "Zwangsladen/-entladen",
    "Forcible Discharge Power": "Zwangsentladeleistung", "Forcible Status": "Zwangsladestatus",
    "Remaining Charge/Discharge Time": "Restzeit Laden/Entladen", "Remaining Charge/Discharge": "Restzeit Laden/Entladen",
    "Running Status": "Betriebsstatus", "SOC": "Ladestand", "Energy Storage Charged": "Batteriespeicher geladen",
    "Energy Storage Discharged": "Batteriespeicher entladen", "Ec-Day": "Bezug heute", "Ep-Day": "Einspeisung heute",
    "Grid Consumption": "Netzbezug", "Grid Production": "Netzeinspeisung", "Own Ec-Day": "Eigenverbrauch heute",
    "Own Consumption Today": "Eigenverbrauch heute", "Own Ec Today": "Eigenverbrauch heute",
    "PV Own Consumption": "PV-Eigenverbrauch", "PV Production": "PV-Ertrag", "Active Power ": "Wirkleistung",
    "Grid Import": "Netzbezug", "Grid Export": "Netzeinspeisung", "PV": "PV", "Self Use": "Eigenverbrauch",
    # SmartPi
    "COS1": "cos φ L1", "COS2": "cos φ L2", "COS3": "cos φ L3", "Ebal": "Energiebilanz", "Ec1": "Bezug L1",
    "Ec2": "Bezug L2", "Ec3": "Bezug L3", "EcDay": "Bezug heute", "EcTot": "Bezug gesamt", "Ep1": "Einspeisung L1",
    "Ep2": "Einspeisung L2", "Ep3": "Einspeisung L3", "EpDay": "Einspeisung heute", "EpTot": "Einspeisung gesamt",
    "F1": "Frequenz L1", "F2": "Frequenz L2", "F3": "Frequenz L3", "I1": "Strom L1", "I2": "Strom L2", "I3": "Strom L3",
    "I4": "Strom N", "P1": "Leistung L1", "P2": "Leistung L2", "P3": "Leistung L3", "Ptot": "Leistung gesamt",
    "V1": "Spannung L1", "V2": "Spannung L2", "V3": "Spannung L3",
    # Miele
    "Active Program": "Programm", "Current Energy Consumption": "Energieverbrauch Programm",
    "Current Water Consumption": "Wasserverbrauch Programm", "Delayed Start Time": "Startvorwahl",
    "Delayed Start Time Absolute": "Startzeitpunkt", "Door Signal": "Tür offen", "Drying Target": "Trocknungsziel",
    "Operation State": "Status", "Program Elapsed Time": "Laufzeit", "Program Finished Time": "Fertig um",
    "Program Phase": "Programmphase", "Program Progress": "Fortschritt", "Program Remaining Time": "Restzeit",
    "Program Elapsed": "Laufzeit", "Program Finished": "Fertig um", "Program Remaining": "Restzeit",
    "Spinning Speed": "Schleuderdrehzahl", "Target Temperature": "Zieltemperatur", "Water Consumption": "Wasserverbrauch",
    "Can Be Started": "Startbar", "Can Be Stopped": "Stoppbar", "Can Be Switched Off": "Ausschaltbar",
    "Can Be Switched On": "Einschaltbar", "Can Control Light": "Licht steuerbar", "Light Enabled": "Licht an",
    "Raw Active Program": "Programm (Rohwert)", "Raw Drying Target": "Trocknungsziel (Rohwert)",
    "Raw Operation State": "Status (Rohwert)", "Raw Program Phase": "Programmphase (Rohwert)",
    "Raw Spinning Speed": "Schleuderdrehzahl (Rohwert)", "Start Stop": "Start/Stopp", "Stop": "Stopp",
    # weather, Tado, Vu+, water meter
    "Absolute Pressure": "Absoluter Luftdruck", "Atmospheric Humidity": "Luftfeuchtigkeit", "Barometric Pressure": "Luftdruck",
    "Barometer": "Luftdruck", "Battery Level": "Batteriestand", "CO2": "CO2", "CO2 Alert": "CO2-Warnung",
    "Carbondioxide": "CO2", "Carbondioxide Alert": "CO2-Warnung", "Dewpoint": "Taupunkt",
    "Dewpoint Depression": "Taupunktdifferenz", "Heat Index": "Hitzeindex", "Humidex": "Humidex",
    "Humidex Appreciation": "Humidex-Bewertung", "Last Seen": "Zuletzt gesehen", "Max Temp": "Max. Temperatur",
    "Min Temp": "Min. Temperatur", "Measures Timestamp": "Messzeitpunkt", "Noise": "Lärm", "Pressure Trend": "Luftdrucktrend",
    "Signal": "Signal", "Signal Strength": "Signalstärke", "Temperature Trend": "Temperaturtrend",
    "Today Max Timestamp": "Zeitpunkt Max. heute", "Today Min Timestamp": "Zeitpunkt Min. heute", "Weatherstation": "Wetterstation",
    "Indoor Humidity": "Luftfeuchtigkeit innen", "Outdoor Humidity": "Luftfeuchtigkeit außen", "Low Battery": "Batterie schwach",
    "At Home": "Zuhause", "Geofencing Enabled": "Geofencing aktiv", "HVAC Mode": "HVAC-Modus",
    "Open Window Detected": "Offenes Fenster erkannt", "Overlay End Time": "Überschreibung endet",
    "Override Remaining Time": "Überschreibung Restzeit", "Timer Duration": "Timer-Dauer", "Zone Operation Mode": "Zonenbetriebsart",
    "Location": "Ort", "Answer": "Antwort", "Media Control": "Mediensteuerung", "Mute": "Stumm", "Volume": "Lautstärke",
    "Change": "Änderung", "Rate": "Durchfluss", "Value": "Zählerstand", "Value Day": "Verbrauch heute",
    "Vu+ Uno 4k Power": "Vu+ Uno 4k Ein/Aus",
    # modbus data channels
    "Last Erroring Read": "Letzter fehlerhafter Lesezugriff", "Last Erroring Write": "Letzter fehlerhafter Schreibzugriff",
    "Last Successful Read": "Letzter erfolgreicher Lesezugriff", "Last Successful Write": "Letzter erfolgreicher Schreibzugriff",
    "Value as Contact": "Wert als Kontakt", "Value as DateTime": "Wert als Datum/Zeit", "Value as Dimmer": "Wert als Dimmer",
    "Value as Number": "Wert als Zahl", "Value as Rollershutter": "Wert als Rollladen", "Value as String": "Wert als Text",
    "Value as Switch": "Wert als Schalter",
    # prices
    "Cheapest": "günstigster", "Cheapest Hour": "Günstigste Stunde", "Priciest": "teuerster", "Priciest Hour": "Teuerste Stunde",
    "Prices": "Strompreise", "Market Gross": "Markt brutto", "Total Gross": "Gesamt brutto", "Total Net": "Gesamt netto",
    "Gross Market Price": "Marktpreis brutto", "Gross Total Price": "Gesamtpreis brutto", "Net Market Price": "Marktpreis netto",
    "Net Total Price": "Gesamtpreis netto", "aWATTar Market Gross": "Markt brutto", "aWATTar Market Net": "Markt netto",
    "aWATTar Total Gross": "Gesamt brutto", "aWATTar Total Net": "Gesamt netto", "aWATTar": "Markt netto",
    "aWATTar Cheapest": "Günstigster Preis", "aWATTar Priciest": "Teuerster Preis", "EPEX aWATTar": "Strompreis",
    # rules
    "Mode Power": "Modus schaltet ein", "Timer Reset": "Timer zurücksetzen", "Timer Trigger": "Timer starten",
    "Forcible Sync": "Zwangsladen abgleichen", "Extrema": "Extremwerte", "Daily COP": "Tages-COP",
    "Metering": "Messung", "Energy Production": "Einspeisung", "Own Energy": "Eigenverbrauch",
    "Program Finished Time ": "Fertigzeit", "Daily Totals": "Tagessummen", "Consumption": "Verbrauch", "Test": "Test",
}

# whole labels that do not follow the device + term pattern
EXACT = {
    "000 MapDB Change Restore": "000 MapDB bei Änderung, beim Start wiederherstellen",
    "001 InfluxDB Change": "001 InfluxDB bei Änderung", "001 InfluxDB Change At Most": "001 InfluxDB bei Änderung, höchstens alle 5 s",
    "002 InfluxDB Update": "002 InfluxDB bei Aktualisierung", "003 InfluxDB Periodic": "003 InfluxDB periodisch",
    "004 InfluxDB Forecast": "004 InfluxDB Prognose",
    "EPEX Spot aWATTar": "Strompreis Markt netto", "EPEX Spot aWATTar Cheapest": "Strompreis günstigster",
    "EPEX Spot aWATTar Priciest": "Strompreis teuerster", "EPEX Spot aWATTar Market Gross": "Strompreis Markt brutto",
    "EPEX Spot aWATTar Total Gross": "Strompreis gesamt brutto", "EPEX Spot aWATTar Total Net": "Strompreis gesamt netto",
    "EPEX Spot aWATTar Prices": "Strompreise", "EPEX Spot": "Strompreis",
    "Energy Daily Grid Export": "Energie täglich Netzeinspeisung", "Energy Daily Grid Import": "Energie täglich Netzbezug",
    "Energy Daily Home": "Energie täglich Haus", "Energy Daily PV": "Energie täglich PV",
    "Energy Daily Self Use": "Energie täglich Eigenverbrauch", "Home Active Power": "Haus Leistung",
    "Home Energy Day": "Haus Energie heute", "Temperature Indoor 15 min": "Temperatur innen 15 min",
    "Temperature Outdoor 15 min": "Temperatur außen 15 min", "Huawei Inverter Modbus TCP": "Huawei Wechselrichter Modbus TCP",
    "Huawei Inverter": "Wechselrichter", "MQTT Broker": "MQTT-Broker", "Miele@home Account": "Miele@home-Konto",
    "Netatmo Account": "Netatmo-Konto", "Heatpump Management": "Wärmepumpe Automatik",
    "Ventilation Management": "Lüftung Automatik", "Air Conditioning Unit Power": "Klimaanlage Geräteleistung",
    "Photovoltaics Own Ec-Day": "Photovoltaik Eigenverbrauch heute", "Miele Dishwasher  G7465 Power State": "Miele Geschirrspüler G7465 Betriebszustand",
    "Power Meter": "Stromzähler", "Energy Storage": "Batteriespeicher", "E-Car": "E-Auto", "Home": "Haus",
    "Netatmo Indoor": "Netatmo innen", "Netatmo Outdoor": "Netatmo außen", "Meteoblue": "Meteoblue", "ORF": "ORF",
    "Temperature 15 min": "Temperatur 15 min", "Water Meter Consumption": "Wasserzähler Verbrauch",
    "Water Meter Watchdog": "Wasserzähler Überwachung", "Refrigerator Watchdog": "Kühlschrank Überwachung",
    "Home Energy": "Haus Energie", "Home Power": "Haus Leistung",
    "Huawei Inverter Power Meter Energy Consumption": "Stromzähler Bezug",
    "Huawei Inverter Power Meter Energy Production": "Stromzähler Einspeisung",
    "SmartPi Energy Consumption": "SmartPi Bezug", "SmartPi Energy Production": "SmartPi Einspeisung",
    "Photovoltaics Own Energy": "Photovoltaik Eigenverbrauch", "Energy Daily Totals": "Energie Tagessummen",
    "Energy Storage Forcible Sync": "Batteriespeicher Zwangsladen abgleichen", "EPEX Spot aWATTar Extrema": "Strompreis Extremwerte",
    "Heatpump Daily COP": "Wärmepumpe Tages-COP", "Heatpump Metering": "Wärmepumpe Messung",
    "Air Conditioning Mode Power": "Klimaanlage Modus schaltet ein",
    # page labels of the device pages
    "Smart Grid": "Smart Grid",
}


def _term(rest):
    return TERMS.get(rest)


def translate(s):
    """German for an English label, or None when nothing matches."""
    if s is None or s == "":
        return s
    if s in EXACT:
        return EXACT[s]
    if s in TERMS:
        return TERMS[s]
    for en in sorted(DEVICES, key=len, reverse=True):
        de = DEVICES[en]
        if s == en.strip():
            return de
        if s.startswith(en.rstrip() + " "):
            rest = s[len(en.rstrip()) + 1:]
            t = _term(rest)
            if t is not None:
                return f"{de} {t}"
            # rule names like "<device> <term> <suffix>": try the longest known term at the start
            for i in range(len(rest.split()), 0, -1):
                head, tail = " ".join(rest.split()[:i]), " ".join(rest.split()[i:])
                if head in TERMS and tail in TERMS:
                    return f"{de} {TERMS[head]} {TERMS[tail]}"
            return None
    return None

EXACT.update({
    "EPEX Spot aWATTar Cheapest": "Günstigster Strompreis", "EPEX Spot aWATTar Priciest": "Teuerster Strompreis",
    "EPEX Spot aWATTar Cheapest Hour": "Günstigste Stunde", "EPEX Spot aWATTar Priciest Hour": "Teuerste Stunde",
    "Smart Meter": "Zähler",
})

RULE_DESCRIPTIONS = {
    "air_conditioning_timer": "Zählt air_conditioning_timer jede Minute um eine Minute herunter und schaltet das Split-Gerät bei null aus.",
    "air_conditioning_timer_reset": "Setzt air_conditioning_timer auf null, wenn das Split-Gerät von Hand ausgeschaltet wird.",
    "air_conditioning_timer_trigger": "Startet den 360-Minuten-Timer air_conditioning_timer, wenn das Split-Gerät eingeschaltet wird und kein Timer läuft.",
    "bicycle_batteries_management": "Standby-Killer: schaltet die Steckdose der Fahrradakkus nach 10 Minuten unter 6 W im Mittel ohne manuelle Änderung aus. Das Laden mit Überschuss ist auskommentiert.",
    "coffee_machine_management": "Schaltet die Steckdose der Kaffeemaschine eine Stunde nach dem letzten Schalten aus, unabhängig von der Leistung.",
    "dishwasher_finished": "Alte leistungsbasierte Fertig-Erkennung für die Steckdose des Geschirrspülers, ersetzt durch das Miele-Cloud-Binding.",
    "air_conditioning_circuit_energy": "Energie des E-Autos heute, seine Leistung seit Mitternacht integriert, und gesamt auf Basis von gestern; die Energie der Klimaanlage selbst als Messung des Shelly EM minus E-Auto.",
    "air_conditioning_circuit_power": "Teilt die Messung des Shelly EM der Klimaanlage in E-Auto (e_car_*) und Klimaanlage selbst (air_conditioning_unit_power) auf, nach Leistung und Schalter von Faikin, und spiegelt den Schalter des Shelly-Relais. Unter 300 W lädt das Auto nicht; die gelernte Grundlast der Klimaanlage (Standby, Innengerät) wird beim Laden abgezogen.",
    "energy_daily_totals": "Hält einen Punkt pro Tag für PV-Ertrag, Hausverbrauch, Netzbezug, Netzeinspeisung und PV-Eigenverbrauch, für Diagramme über Wochen, Monate und Jahre.",
    "energy_storage_forcible_sync": "Spiegelt den Zwangslade-Status des Wechselrichters in das beschreibbare Steuer-Item, ohne etwas an den Wechselrichter zu senden.",
    "epex_spot_awattar_extrema": "Sucht den günstigsten und teuersten gespeicherten aWATTar-Preis vom laufenden Zeitfenster bis zum Ende der veröffentlichten Day-Ahead-Preise.",
    "heatpump_dcop": "Berechnet jede Minute die Tages-COPs aus den Energie-Integralen von heatpump_metering; das 5-Sekunden-Fenster um Mitternacht in persistCop ist Absicht.",
    "heatpump_error": "Schickt eine Benachrichtigung mit Code und deutscher Beschreibung, wenn die Wärmepumpe einen anderen Fehlertyp als Normal meldet.",
    "heatpump_dhw_management": "Warmwasser-Steuerung: wählt den Warmwasser-Sollwert nach Tageszeit und PV-Überschuss und zwingt die Wärmepumpe über Smart Grid an, wenn der Speicher voll und der Überschuss hoch ist.",
    "weather_forecast": "Holt alle 30 Minuten und beim Start das aktuelle Wetter, Min./Max. für heute und die zwei Folgetage sowie die Vorhersage der nächsten 61 Stunden und 5 Tage als JSON von Open-Meteo, Modell GeoSphere AROME Austria (Stunden und Tage außerhalb seiner Reichweite und die Regenwahrscheinlichkeit aus dem Best Match), für Wien, für die Wetterleiste der Übersicht und ihr Popup.",
    "weather_warnings": "Holt alle 15 Minuten und beim Start die amtlichen Wetterwarnungen der GeoSphere Austria für Wien: die höchste Stufe der Warnungen, die jetzt oder in den nächsten 24 Stunden gelten, diese als Kurztext und alle noch nicht abgelaufenen Warnungen als JSON, für die Wetterleiste der Übersicht und ihr Popup.",
    "heatpump_metering": "Teilt die elektrische Leistung der Wärmepumpe in Heizung, Warmwasser und Standby, leitet die Heizleistung aus Durchfluss und Spreizung ab, berechnet momentane COPs und integriert alles mit einem gemeinsamen Zeitschritt zu den Energien von heute.",
    "home_energy": "Berechnet den Energieverbrauch des Hauses heute aus PV-Ertrag und Netzbezug/-einspeisung seit Mitternacht.",
    "home_power": "Berechnet alle 10 Sekunden die Wirkleistung des Hauses aus Wechselrichter-Ausgang und Leistung am Netzzähler.",
    "huawei_inverter_power_meter_ec": "Berechnet den Netzbezug heute aus dem Gesamtzählerstand des Stromzählers.",
    "huawei_inverter_power_meter_ep": "Berechnet die Netzeinspeisung heute aus dem Gesamtzählerstand des Stromzählers.",
    "huawei_inverter_pv1_power": "Berechnet die Leistung von PV-String 1 aus Spannung und Strom.",
    "huawei_inverter_pv2_power": "Berechnet die Leistung von PV-String 2 aus Spannung und Strom.",
    "miele_dishwasher_finished": "Schickt eine Benachrichtigung mit dem Programm, wenn der Miele-Geschirrspüler sein Programm beendet.",
    "miele_dishwasher_program_finished_time": "Setzt die Fertigzeit des Geschirrspülers auf jetzt + Startvorwahl + Restzeit, auf die Minute gerundet; UNDEF im Leerlauf.",
    "miele_tumble_dryer_finished": "Schickt eine Benachrichtigung mit Programm und Trocknungsziel, wenn der Miele-Wäschetrockner sein Programm beendet.",
    "miele_tumble_dryer_program_finished_time": "Setzt die Fertigzeit des Wäschetrockners auf jetzt + Startvorwahl + Restzeit, auf die Minute gerundet; UNDEF im Leerlauf.",
    "miele_washing_machine_finished": "Schickt eine Benachrichtigung mit Programm, Temperatur und Schleuderdrehzahl, wenn die Miele-Waschmaschine ihr Programm beendet.",
    "miele_washing_machine_program_finished_time": "Setzt die Fertigzeit der Waschmaschine auf jetzt + Startvorwahl + Restzeit, auf die Minute gerundet; UNDEF im Leerlauf.",
    "office_1_management": "Standby-Killer: schaltet die Steckdose Büro 1 nach 10 Minuten unter 10 W im Mittel ohne manuelle Änderung aus.",
    "office_2_management": "Standby-Killer: schaltet die Steckdose Büro 2 nach 10 Minuten unter 15 W im Mittel ohne manuelle Änderung aus.",
    "photovoltaics_own_energy": "Berechnet den selbst verbrauchten PV-Strom heute als PV-Ertrag minus Netzeinspeisung seit Mitternacht.",
    "refrigerator_watchdog": "Warnt einmal, wenn der Kühlschrank zwei Stunden lang gleichmäßig 110 W oder mehr ohne Kompressor-Spitzen zieht, was auf eine offene Tür deutet.",
    "smartpi_ec": "Berechnet den Energiebezug heute aus dem Gesamtzählerstand des SmartPi.",
    "smartpi_ep": "Berechnet die Energieeinspeisung heute aus dem Gesamtzählerstand des SmartPi.",
    "temperature_15min": "Schreibt 15-Minuten-Mittelwerte der Innen- und Außenfühler der Wärmepumpe auf gemeinsame Zeitpunkte, für das Diagramm der Übersicht.",
    "test": "Werkbank ohne Auslöser: vergleicht vier numerische Integrationsverfahren samt Laufzeit; belegt, warum die Energie-Integration der Wärmepumpe das Trapezverfahren nutzt.",
    "tumble_dryer_finished": "Alte leistungsbasierte Fertig-Erkennung für die Steckdose des Wäschetrockners, ersetzt durch das Miele-Cloud-Binding.",
    "ventilation_management": "Setzt die Lüftungsstufe nach CO2, Feuchte und Außentemperatur, solange keine manuelle Übersteuerung läuft, und warnt bei hohem CO2 mit 30 Minuten Entprellung.",
    "ventilation_timer": "Zählt die Übersteuerung der Lüftung (ventilation_timer) jede Minute um eine Minute herunter.",
    "ventilation_timer_trigger": "Startet eine 30-minütige Übersteuerung, wenn sich die Lüftungsstufe ändert, von Hand oder durch ventilation_management; das entprellt auch die Automatik.",
    "washing_machine_1_finished": "Alte leistungsbasierte Fertig-Erkennung für Waschmaschine 1, ersetzt durch das Miele-Cloud-Binding.",
    "washing_machine_2_finished": "Setzt washing_machine_2_finished nach einem Programm (Spitze von 50 W innerhalb von 15 Minuten, 5-Minuten-Mittel höchstens 5 W, noch eingeschaltet) und löscht es, wenn die Maschine zum Ausräumen ausgeschaltet wird oder neu startet.",
    "water_meter_consumption": "Berechnet den Wasserverbrauch heute aus dem Zählerstand und schreibt eine explizite Null um Mitternacht in InfluxDB.",
    "water_meter_error": "Schickt eine Benachrichtigung, wenn der Wasserzähler den Zustand ohne Fehler verlässt.",
    "water_meter_watchdog": "Warnt einmal, wenn der Wasserzähler 15 Minuten lang nichts gesendet hat oder der Durchfluss 30 Minuten lang über null bleibt (Leck).",
}

OPTIONS = {
    "0=Free running,1=Forced OFF,2=Recommended ON,3=Forced ON": "0=Normalbetrieb,1=Sperre,2=Einschaltempfehlung,3=Einschaltbefehl",
    "1=Low,2=Medium,3=High": "1=Niedrig,2=Mittel,3=Hoch",
    "Q=Quiet,A=Auto,1=1,2=2,3=3,4=4,5=5": "Q=Leise,A=Auto,1=1,2=2,3=3,4=4,5=5",
    "A=Auto,H=Heat,C=Cool,D=Dry,F=Fan": "A=Auto,H=Heizen,C=Kühlen,D=Entfeuchten,F=Lüften",
    "0=Stop,1=Charge,2=Discharge": "0=Stopp,1=Laden,2=Entladen",
    "0=Offline,1=Standby,2=Running,3=Fault,4=Sleep": "0=Offline,1=Standby,2=In Betrieb,3=Störung,4=Ruhezustand",
    ("0=Standby: Initializing,1=Standby: Detecting insulation resistance,2=Standby: Detecting irradiation,3=Standby: Detecting grid,"
     "256=Starting,512=On-grid,513=On-grid: Power limiting,514=On-grid: Self derating,768=Shutdown: Fault,769=Shutdown: Command,"
     "770=Shutdown: OVGR,771=Shutdown: Communication disconnected,772=Shutdown: Power limited,773=Shutdown: Manual startup required,"
     "774=Shutdown: DC switches disconnected,775=Shutdown: Rapid cutoff,776=Shutdown: Input underpowered,1025=Grid scheduling: cos(Phi)-P curve,"
     "1026=Grid scheduling: Q-U curve,1027=Grid scheduling: PF-U curve,1028=Grid scheduling: Dry contact,1029=Grid scheduling: Q-P curve,"
     "1280=Spot-check ready,1281=Spot-checking,1536=Inspecting,1792=AFCI self-check,2048=I-V scanning,2304=DC input detection,"
     "2560=Running: Off-grid charging,40960=Standby: No irradiation"):
    ("0=Standby: Initialisierung,1=Standby: Isolationsprüfung,2=Standby: Einstrahlungsprüfung,3=Standby: Netzprüfung,"
     "256=Startet,512=Am Netz,513=Am Netz: Leistungsbegrenzung,514=Am Netz: Selbst-Derating,768=Abgeschaltet: Störung,769=Abgeschaltet: Befehl,"
     "770=Abgeschaltet: OVGR,771=Abgeschaltet: Kommunikation getrennt,772=Abgeschaltet: Leistungsbegrenzt,773=Abgeschaltet: Manueller Start nötig,"
     "774=Abgeschaltet: DC-Schalter getrennt,775=Abgeschaltet: Schnellabschaltung,776=Abgeschaltet: Eingangsleistung zu gering,"
     "1025=Netzsteuerung: cos(Phi)-P-Kennlinie,1026=Netzsteuerung: Q-U-Kennlinie,1027=Netzsteuerung: PF-U-Kennlinie,"
     "1028=Netzsteuerung: Trockenkontakt,1029=Netzsteuerung: Q-P-Kennlinie,1280=Stichprobe bereit,1281=Stichprobe läuft,"
     "1536=Prüfung,1792=AFCI-Selbsttest,2048=I-U-Scan,2304=DC-Eingangserkennung,2560=In Betrieb: Laden im Inselbetrieb,"
     "40960=Standby: Keine Einstrahlung"),
}

# raw device states shown in German through display options; the states themselves stay as they are
STATE_OPTIONS = {
    "espaltherma_3way_valve_mode": "Space=Heizung,DHW=Warmwasser",
    "espaltherma_i_u_operation_mode": "Heating=Heizen,Heating + DHW=Heizen + Warmwasser,DHW=Warmwasser,Stop=Stopp",
    "espaltherma_operation_mode": "Heating=Heizen,Fan Only=Nur Lüfter,Cooling=Kühlen,Defrost=Abtauen,Stop=Stopp",
    "espaltherma_error_type": "Normal=Normal,Warning=Warnung,Error=Fehler",
}

TRANSFORMATIONS = {"Multiply": "Multiplizieren", "Offset to absolute time": "Versatz in absolute Zeit",
                   "Passthrough": "Durchreichen", "Range Filter": "Bereichsfilter", "Seconds to HMS": "Sekunden in h:mm:ss"}
