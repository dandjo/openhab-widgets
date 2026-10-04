"""German → English for the texts of the generated widgets and of the pages in the repository's screenshots (en.py).
Keys are the cores of texts: spaces and separators at their ends are kept around the English. Item labels come from
the English originals in labels_export.json where an item is older than the German labels (en.py); the items made
since are below."""

EN = {
    # cards, pages, sections
    "Übersicht": "Overview", "Steuerung": "Controls", "Energiefluss": "Energy Flow", "Haushaltsgeräte": "Appliances",
    "Schalter": "Switches", "Heizung & Warmwasser": "Heating & Hot Water", "Strompreis": "Electricity Price",
    "Wärmepumpe": "Heat Pump", "Energie pro Tag": "Energy per Day", "PV-Ertrag pro Tag": "PV Yield per Day",
    "PV-Ertrag": "PV yield", "Temperaturen": "Temperatures", "Temperaturen heute": "Temperatures today",
    "Verbrauch heute": "Consumption Today", "Widget-Galerie": "Widget Gallery", "Regelung": "Control",
    "Wäsche & Geschirr": "Laundry & Dishes", "Terrasse & Fahrräder": "Terrace & Bicycles", "Terrasse": "Terrace",
    "Büros": "Offices", "Kaffee": "Coffee", "Verbraucher": "Consumers", "Sollwerte": "Setpoints", "Modi": "Modes",
    "Verlauf": "History", "Vorhersage": "Forecast", "Warnungen": "Warnings", "Weitere Quellen": "More sources",
    "Alle Details": "All details", "Öffnen": "Open",
    # energy flow
    "Eigenverbrauch": "Self-consumption", "Autarkie": "Self-sufficiency", "heute": "today", "kWh heute": "kWh today",
    "Bezug": "Import", "Einsp.": "Export", "Entl.": "Disch.", "Gel.": "Chg.", "Akku": "Battery", "ruht": "idle",
    "Voll in": "Full in", "Voll um": "Full at", "Leer in": "Empty in", "Leer um": "Empty at", "Ø 5 min": "Ø 5 min",
    "Fertig in": "Done in", "Fertig um": "Done at", "Aus PV heute": "From PV today", "Aus PV": "From PV",
    "Aus dem Netz": "From the grid", "aus PV": "from PV", "aus dem Netz": "from the grid", "Haus": "Home",
    "Strompreis gesamt": "Electricity price", "Läuft": "Running", "nichts": "nothing", "lädt": "charging",
    "lädt nicht": "not charging", "Raum · Soll": "Room · Target", "CO₂": "CO₂", "Luftfeuchtigkeit": "Humidity",
    "Stufe": "Level", "Timer": "Timer", "WM 1": "WM 1", "WM 2": "WM 2", "Trockner": "Dryer",
    "Geschirrspüler": "Dishwasher", "Waschmaschine 1": "Washing Machine 1", "Waschmaschine 2": "Washing Machine 2",
    "Wäschetrockner": "Tumble Dryer", "Kühlschrank": "Refrigerator", "Kaffeemaschine": "Coffee Machine",
    "Netzwerk": "Network", "Büro 1": "Office 1", "Büro 2": "Office 2", "Wohnzimmer Medien": "Living Room Media",
    "Fahrradakkus": "Bicycle Batteries", "E-Bikes": "E-Bikes", "Terrassenlicht": "Terrace Light", "E-Auto": "E-Car",
    "Batteriespeicher": "Battery", "Stromzähler": "Power Meter", "Photovoltaik": "Photovoltaics", "Lüftung": "Ventilation",
    "Klimaanlage": "Air Conditioner", "Steckdose": "Plug", "Nous Steckdose": "Nous Plug",
    # heat pump
    "Außengerät": "Outdoor Unit", "Innengerät": "Indoor Unit", "3-Wege-Ventil": "3-Way Valve", "Ventil": "Valve",
    "Kältemittel": "Refrigerant", "Heizkreis": "Heating Circuit", "Warmwasserspeicher": "Hot Water Tank",
    "Obergeschoss": "Upper Floor", "Erdgeschoss": "Ground Floor", "Heizkörper": "Radiators", "Keller": "Basement",
    "Fußbodenheizung": "Floor Heating", "Elektrisch": "Electrical", "Wärme": "Heat", "Strom": "Electricity",
    "Strom heute": "Electricity today", "Wärme heute": "Heat today", "Heizung": "Heating", "Warmwasser": "Hot water",
    "Standby": "Standby", "Gesamt": "Total", "COP Heizung": "COP heating", "COP WW": "COP DHW",
    "COP Warmwasser": "COP hot water", "COP gesamt": "COP total", "COP pro Tag": "COP per day", "Tages-COP": "Daily COP",
    "Tages-COP Heizung": "Daily COP heating", "Tages-COP Warmwasser": "Daily COP hot water", "Abtauen": "Defrost",
    "Bereit": "Ready", "Betrieb": "Operation", "Heizen": "Heating", "Laden": "Charging", "Zusatzheizung": "Booster heater",
    "Zusatzheizung Speicher": "Booster heater", "Heizstab": "Backup heater", "Heizstab Stufe 1": "Backup heater step 1",
    "Heizstab Stufe 2": "Backup heater step 2", "Warmwasserladung · fertig": "Hot water charge · done at",
    "WW fertig um": "DHW done at", "seit": "since", "Läuft seit": "Running since", "noch": "left",
    "Heizen seit": "Heating since", "Laden seit": "Charging since", "Außen": "Outdoor", "Innen": "Indoor",
    "außen": "outdoor", "Außenluft": "Outdoor air", "Außentemperatur": "Outdoor temperature", "Raum": "Room",
    "Raumtemperatur": "Room temperature", "Raum Sollwert": "Room setpoint", "Vorlauf": "Flow", "Rücklauf": "Return",
    "Vorlauf-Soll": "Flow target", "Vorlauf Sollwert": "Flow setpoint", "Vorlauf Sollwert (Zusatz": "Flow setpoint (add",
    "Vorlauf nach Heizstab": "Flow after backup heater", "Vorlauf vor Heizstab": "Flow before backup heater",
    "Vorlauf-Offset": "Flow offset", "Soll": "Target", "Warmwasser Soll": "Hot water target",
    "Warmwasser Sollwert": "Hot water setpoint", "Warmwasser-Boost": "Hot water boost", "Durchfluss": "Flow rate",
    "Druck": "Pressure", "Wasserdruck": "Water pressure", "Kältemitteldruck": "Refrigerant pressure",
    "Kältemittel flüssig": "Refrigerant liquid", "Flüssig": "Liquid", "Flüssigkeit": "Liquid",
    "Flüssigkeitstemperatur": "Liquid temperature", "Heißgas": "Hot gas", "Heißgas Soll": "Hot gas target",
    "Soll-Heißgas": "Hot gas target", "Verdichter": "Compressor", "Verdichterfrequenz": "Compressor frequency",
    "Wärmetauscher": "Heat exchanger", "Wärmetauscher Mitte": "Heat exchanger middle", "Umwälzpumpe": "Circulation pump",
    "Umwälzpumpe Signal": "Circulation pump signal", "Elektrische Leistung": "Electrical power",
    "Heizleistung": "Heat output", "Heizleistung Heizung": "Heat output heating",
    "Heizleistung Warmwasser": "Heat output hot water", "Heizleistung nach Heizstab": "Heat output after backup heater",
    "Heizleistung vor Heizstab": "Heat output before backup heater", "Leistung": "Power", "Leistung heute": "Power today",
    "Leistung ohne Heizstab": "Power without backup heater", "Leistung aufgeteilt": "Power split",
    "Strom nach Zweck": "Electricity by use", "Wärme nach Zweck": "Heat by use", "Wärme Heizung": "Heat heating",
    "Wärme Warmwasser": "Heat hot water", "Elektrisch Heizung": "Electrical heating",
    "Elektrisch Warmwasser": "Electrical hot water", "Elektrisch Standby": "Electrical standby",
    "Elektrisch heute": "Electrical today", "Elektrisch · Shelly EM": "Electrical · Shelly EM",
    "Heizbetrieb": "Space heating", "Heizbetrieb heute": "Space heating today", "Heizkreis heute": "Heating circuit today",
    "Außengerät heute": "Outdoor unit today", "Außengerät Betrieb": "Outdoor unit operation",
    "Innengerät heute": "Indoor unit today", "Innengerät Betrieb": "Indoor unit operation",
    "Kältemittel heute": "Refrigerant today", "3-Wege-Ventil heute": "3-way valve today",
    "Warmwasserspeicher heute": "Hot water tank today", "Betrieb heute": "Operation today", "Speicher": "Tank",
    "Speicher Eco-Modus": "Tank eco mode", "Speicher Komfortmodus": "Tank comfort mode", "Smart Grid": "Smart Grid",
    "Empfehlung": "Recommended", "Sperre": "Blocked", "Frei": "Free", "Zwang": "Forced", "Automatik": "Automatic",
    "Automatik aus": "Automatic off", "Automatik pausiert bis": "Automatic paused until",
    "Automatik regelt": "Automatic controls", "Automatik regelt die Stufe": "Automatic controls the level",
    "Heizung aus": "Heating off", "System aus": "System off", "Nachheizen": "Reheat", "Notbetrieb": "Emergency mode",
    "Frostschutz": "Frost protection", "Flüstermodus": "Whisper mode", "Geräuscharmer Betrieb": "Low-noise operation",
    "Druckausgleich": "Pressure equalisation", "Drucksensor Temperatur": "Pressure sensor temperature",
    "Ölrückführung": "Oil return", "Anlaufsteuerung": "Start-up control", "Anforderungssignal": "Demand signal",
    "Thermostatschalter": "Thermostat switch", "Thermoschutz Heizstab": "Backup heater thermal protection",
    "Thermoschutz Zusatzheizung": "Booster heater thermal protection", "Soll-Spreizung Heizen": "Target delta heating",
    "Fehlercode": "Error code", "Inverter Strom": "Inverter current", "Stellung": "Position", "Befehl": "Command",
    "Nicht gemessen": "Not measured", "Neustart-Standby": "Restart standby", "Fühler der Wärmepumpe": "Heat pump sensor",
    "volle Leistung": "full power", "schaltet um": "switching", "von 3": "of 3", "über 2 Tage": "over 2 days",
    "Solltemperatur": "Target temperature", "Temperatur": "Temperature", "Starten": "Start", "Stoppen": "Stop",
    "{s0|Außen} · {s1|Wärmetauscher}": "{s0|Outdoor} · {s1|Heat exchanger}",
    "{s0|Heißgas} · {s1|Soll gestrichelt}": "{s0|Hot gas} · {s1|Target dashed}",
    "{s0|Temperatur} · {s1|Soll gestrichelt}": "{s0|Temperature} · {s1|Target dashed}",
    "{s0|Vorlauf} · {s1|Rücklauf}": "{s0|Flow} · {s1|Return}",
    "{s0|Heizstab} · {s1|Zusatzheizung}": "{s0|Backup heater} · {s1|Booster heater}",
    "Space=Heizung,DHW=Warmwasser": "Space=Heating,DHW=Hot water",
    "Heating=Heizen,Heating + DHW=Heizen + Warmwasser,DHW=Warmwasser,Stop=Stopp":
        "Heating=Heating,Heating + DHW=Heating + Hot water,DHW=Hot water,Stop=Stop",
    "Heating=Heizen,Fan Only=Nur Lüfter,Cooling=Kühlen,Defrost=Abtauen,Stop=Stopp":
        "Heating=Heating,Fan Only=Fan only,Cooling=Cooling,Defrost=Defrost,Stop=Stop",
    "ON=An,OFF=Aus": "ON=On,OFF=Off", "an": "on", "aus": "off", "bis": "until",
    "0=Normal;1=Sperre;2=Empfehlung;3=Befehl": "0=Normal;1=Blocked;2=Recommended;3=Forced",
    "1=Niedrig;2=Mittel;3=Hoch": "1=Low;2=Medium;3=High",
    "A=Auto;H=Heizen;C=Kühlen;D=Entfeuchten;F=Lüften": "A=Auto;H=Heating;C=Cooling;D=Drying;F=Fan",
    "Q=Leise;A=Auto;1=1;2=2;3=3;4=4;5=5": "Q=Quiet;A=Auto;1=1;2=2;3=3;4=4;5=5",
    # air conditioner, ventilation, switches
    "An": "On", "Aus": "Off", "Modus": "Mode", "Lüfter": "Fan", "Lüfterdrehzahl": "Fan speed", "Luftstrom": "Airflow",
    "Leise": "Quiet", "Komfort": "Comfort", "Eco": "Eco", "Boost": "Boost", "Auto": "Auto",
    "Kühlen": "Cooling", "Entfeuchten": "Drying", "Lüften": "Fan", "Schwenken H": "Swing H", "Schwenken V": "Swing V",
    "Schwenken horizontal": "Swing horizontal", "Schwenken vertikal": "Swing vertical", "läuft bis": "running until",
    "läuft ohne Timer": "running without timer", "beim Einschalten 6 h": "6 h when switched on",
    "Faikout neu starten": "Restart Faikout", "Faikout Perfera neu starten?": "Restart Faikout Perfera?",
    "Neu starten": "Restart", "Neustart gesendet": "Restart sent", "Niedrig": "Low", "Mittel": "Medium", "Hoch": "High",
    "Popup": "Popup", "Status": "Status", "Geräteleistung": "Unit power",
    # appliances
    "läuft": "running", "fertig": "done", "Phase": "Phase", "Programm": "Program", "läuft · Speicher": "running · tank",
    "läuft · 45": "running · 45", "läuft · 70": "running · 70", "läuft, ohne Fortschritt": "running, no progress",
    # plugs
    "Energie": "Energy", "Energie heute": "Energy today", "Energie gesamt": "Energy total", "Spannung": "Voltage",
    "Scheinleistung": "Apparent power", "Blindleistung": "Reactive power", "Leistungsfaktor": "Power factor",
    # price
    "Günstigste": "Cheapest", "Günstigste Stunde": "Cheapest hour", "pro kWh gesamt": "per kWh all-in",
    "Gesamtpreis": "All-in price", "Gesamt netto": "Total net", "Markt brutto": "Market gross", "Markt netto": "Market net",
    # consumption, daily energy, calendar, temperatures
    "Ø pro Tag": "Ø per day", "Tag": "Day", "Jahr": "Year", "Monate": "Months", "Halbjahre": "Half-years",
    "Balken": "Bars", "Jetzt": "Now", "Heute": "Today",
    "Jänner": "January", "Februar": "February", "März": "March", "April": "April", "Mai": "May", "Juni": "June",
    "Juli": "July", "August": "August", "September": "September", "Oktober": "October", "November": "November",
    "Dezember": "December", "Jän": "Jan", "Mär": "Mar", "Okt": "Oct", "Dez": "Dec",
    # weather
    "Niederschlag": "Precipitation", "Wind": "Wind", "Warnstufe": "Warning level",
    "Meteoblue · 5 Tage": "Meteoblue · 5 days", "Prognose für Wien bei wetter.orf.at": "Forecast for Vienna at wetter.orf.at",
    "Die Außentemperatur der Leiste misst der Sensor der Wärmepumpe. Vorhersage von Open-Meteo.com (CC BY 4.0), "
    "Modell GeoSphere AROME Austria, spätere Stunden und Tage sowie die Regenwahrscheinlichkeit aus dem Best Match; "
    "Warnungen von GeoSphere Austria (warnungen.zamg.at).":
        "The bar's outdoor temperature comes from the heat pump's sensor. Forecast by Open-Meteo.com (CC BY 4.0), model "
        "GeoSphere AROME Austria, later hours and days and the probability of rain from Best Match; warnings by "
        "GeoSphere Austria (warnungen.zamg.at).",
    # prop descriptions with German examples
    "Text beside the ring, e.g. Eigenverbrauch": "Text beside the ring, e.g. Self-consumption",
    "What the pill says while on, e.g. An · Lüften; usually an expression":
        "What the pill says while on, e.g. On · Fan; usually an expression",
    "value=label pairs separated by semicolons, e.g. 1=Niedrig;2=Mittel;3=Hoch":
        "value=label pairs separated by semicolons, e.g. 1=Low;2=Medium;3=High",
    # item labels of the items made after the German labels (older ones come from labels_export.json)
    "Batteriespeicher Leistung 5 min": "Energy Storage Power 5 min",
    "ESPAltherma Elektrische Leistung Heizstab": "ESPAltherma Electrical Power Backup Heater",
    "ESPAltherma Elektrische Leistung Zusatzheizung": "ESPAltherma Electrical Power Booster Heater",
    "Klimaanlage Geräteenergie heute": "Air Conditioning Unit Energy Today",
    "Klimaanlage Geräteenergie gesamt": "Air Conditioning Unit Energy Total",
    "Klimaanlage Timer eingestellt": "Air Conditioning Timer Set", "Lüftung Timer eingestellt": "Ventilation Timer Set",
    "Waschmaschine 2 läuft seit": "Washing Machine 2 Running Since", "Wetter": "Weather",
    "Wetter Stundenprognose": "Weather Hourly Forecast", "Wetter Tag": "Weather Day",
    "Wetter Tagesprognose": "Weather Daily Forecast", "Wetter aktuell": "Weather Current",
    "Wetter heute Max.": "Weather Today Max.", "Wetter heute Min.": "Weather Today Min.",
    "Wetter morgen Max.": "Weather Tomorrow Max.", "Wetter morgen Min.": "Weather Tomorrow Min.",
    "Wetter übermorgen Max.": "Weather Day After Tomorrow Max.", "Wetter übermorgen Min.": "Weather Day After Tomorrow Min.",
    "Wetterwarnung": "Weather Warning", "Wetterwarnung Stufe": "Weather Warning Level", "Wetterwarnungen": "Weather Warnings",
    "Wärmepumpe 3-Wege-Ventil als Zahl (1 = Warmwasser)": "Heatpump Three-Way Valve as Number (1 = DHW)",
    "Wärmepumpe Abtauen als Zahl (1 = Abtauen)": "Heatpump Defrost as Number (1 = Defrost)",
    "Wärmepumpe Heizung läuft seit": "Heatpump Heating Running Since",
    "Wärmepumpe Warmwasser fertig um": "Heatpump DHW Done At", "Wärmepumpe Warmwasser lädt seit": "Heatpump DHW Charging Since",
}

    # installation texts the screenshots show (Miele programs and phases), for ui_proxy.py
EN.update({"Pflegeleicht": "Easy care", "Baumwolle": "Cottons", "Waschen": "Washing", "Trocknen": "Drying",
           "Spülen": "Rinsing", "Schleudern": "Spinning", "Hauptwäsche": "Main wash", "Vorwäsche": "Pre-wash",
           "Abkühlen": "Cooling down", "Knitterschutz": "Anti-crease", "Feinwäsche": "Delicates", "Wolle": "Woollens",
           "Oberhemden": "Shirts", "Schnell": "Quick", "Kurz": "Short", "Programmende": "Finished", "Beendet": "Finished",
           "In Betrieb": "Running", "Bereit": "Ready", "Pause": "Pause", "Trocknen Plus": "Drying plus",
           "Hauptspülen": "Main rinse", "Klarspülen": "Final rinse", "Reinigen": "Cleaning", "Vorspülen": "Pre-rinse",
           "Orange": "Orange", "Gelb": "Yellow", "Rot": "Red", "Grün": "Green"})

# whole lists in expressions, translated as a whole: a letter may stand for two days
LISTS = {
    "['N', 'NNO', 'NO', 'ONO', 'O', 'OSO', 'SO', 'SSO', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']":
        "['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']",
    "['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa']": "['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']",
    "['M', 'D', 'M', 'D', 'F', 'S', 'S']": "['M', 'T', 'W', 'T', 'F', 'S', 'S']",
    "['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']":
        "['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']",
}
# the weekday letters of the PV calendar, as separate texts in this order
DAY_LETTERS = (["M", "D", "M", "D", "F", "S", "S"], ["M", "T", "W", "T", "F", "S", "S"])
