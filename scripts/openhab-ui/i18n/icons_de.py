"""Icons for homepi's items: groups and switches by device, measurements by what they measure.
Material icons, all checked to exist in the fonts of both MainUI and Basic UI; the battery state of charge
keeps the classic level icon, which fills with the state."""
import re

M = "material:"

# device by item-name prefix, longest first
DEVICE_ICONS = {
    "air_conditioning": "ac_unit", "faikout_perfera": "ac_unit", "tado": "thermostat", "bicycle_batteries": "electric_bike",
    "coffee_machine": "coffee", "dishwasher": "flatware", "miele_dishwasher": "flatware", "e_car": "electric_car",
    "epex_spot": "euro", "espaltherma": "heat_pump", "pyaltherma": "heat_pump", "heatpump": "heat_pump",
    "esplyfterl": "air", "ventilation": "air", "huawei_inverter_energy_storage": "battery_charging_full",
    "huawei_inverter_power_meter": "electric_meter", "huawei_inverter": "solar_power", "photovoltaics": "solar_power",
    "living_room_entertainment": "tv", "vuuno4k": "tv", "miele_tumble_dryer": "dry_cleaning", "tumble_dryer": "dry_cleaning",
    "miele_washing_machine": "local_laundry_service", "washing_machine": "local_laundry_service", "netatmo": "cloud",
    "network": "router", "office": "computer", "refrigerator": "kitchen", "smart_meter": "electric_meter",
    "smartpi": "electric_meter", "terrace_light": "light", "water_meter": "water", "home": "home",
    "energy_daily": "bar_chart", "temperature_": "thermostat",
}

# (regex on the English label, icon), first match wins
MEASURE_ICONS = [
    (r"Electrical Power", "bolt"),
    (r"Door Signal$", "door_front"),
    (r"Demand Signal", "notifications"),
    (r"Water Pump", "cyclone"),
    (r"Streamer", "air"),
    (r"Climate Control", "fireplace"),
    (r"DHW Power$", "shower"),
    (r"Thermostat Switch", "toggle_on"),
    (r"Energy Storage (Unit 1 )?SOC$", "oh:batterylevel"),
    (r"Battery Level$", "battery_std"),
    (r"Apparent Power$|Reactive Power$", "waves"),
    (r"Power Factor$|COS\d$", "functions"),
    (r"Voltage|Voltage N-Phase$| V\d$", "electric_bolt"),
    (r"Water Consumption", "water_drop"),
    (r"Energy Consumption$", "bolt"),
    (r"(Bus |Primary |Secondary |Phase . |PV\d )?Current$| I\d$", "electrical_services"),
    (r"Inverter Frequency|Compressor Frequency", "speed"),
    (r"Frequency$| F\d$", "graphic_eq"),
    (r"Energy Daily", "bar_chart"),
    (r"Energy (DHW |Space |Standby )?Today$|Energy Total$|Energy Day$|E-Day$|E-Total$|Ec-Day$|Ep-Day$|Ec\d$|Ep\d$|"
     r"EcDay$|EpDay$|EcTot$|EpTot$|Ebal$|Grid Consumption$|Grid Production$|Day Charge$|Day Discharge$|Total Charge$|"
     r"Total Discharge$|Own Ec-Day$", "electric_meter"),
    (r"Heating Energy", "local_fire_department"),
    (r"Heating Power", "local_fire_department"),
    (r"Forcible Charge/Discharge$", "battery_charging_full"),
    (r"Forcible Status$|Running Status$|Device Status$|Operation State$|Water Meter Status$", "info"),
    (r"Forced Charging Period$|Remaining Charge/Discharge Time$|Remaining Time$|Elapsed Time$|Delayed Start Time$", "hourglass_bottom"),
    (r"Price|Cheapest$|Priciest$|aWATTar$|Prices$|Market Gross$|Total Gross$|Total Net$", "euro"),
    (r"Hour$|Last Seen$|Timestamp$|Startup Time$|Shutdown Time$|Finished Time$|Start Time Absolute$", "schedule"),
    (r"Finished$", "task_alt"),
    (r"Timer$", "timer"),
    (r"Management$", "tune"),
    (r"CO2 Alert$", "notification_important"),
    (r"CO2$", "co2"),
    (r"Noise$", "volume_up"),
    (r"Humidity$", "water_drop"),
    (r"Water Pressure$|Refrigerant Pressure|Absolute Pressure$|Barometric Pressure$|Pressure Equalizing", "compress"),
    (r"3-Way Valve", "alt_route"),
    (r"Backup Heater|Booster Heater|Reheat", "local_fire_department"),
    (r"D?COP", "insights"),
    (r"Defrost|Freeze Protection", "severe_cold"),
    (r"Demand Signal", "notifications"),
    (r"Flow Sensor", "water"),
    (r"Error|Emergency", "error"),
    (r"Oil Return", "oil_barrel"),
    (r"Restart|Startup Control", "restart_alt"),
    (r"Smart Grid", "power"),
    (r"Space Heating Operation|Climate Control", "fireplace"),
    (r"Storage Comfort Mode|Comfort Mode", "weekend"),
    (r"Eco Mode|Storage Eco", "eco"),
    (r"System OFF", "power_off"),
    (r"Target Delta T", "swap_vert"),
    (r"Thermal Protector", "shield"),
    (r"Thermostat Switch", "toggle_on"),
    (r"Water Pump", "cyclone"),
    (r"Powerful", "whatshot"),
    (r"DHW Power$", "shower"),
    (r"Low Noise|Silent Mode|Quiet Mode", "volume_off"),
    (r"Fan Speed|Fan$|Streamer|ESPLyfterl Level", "air"),
    (r"Swing Horizontal", "swap_horiz"),
    (r"Swing Vertical", "swap_vert"),
    (r"Offset", "tune"),
    (r"Efficiency", "percent"),
    (r"Optimizers", "device_hub"),
    (r"Active Program$", "list"),
    (r"Program Phase$", "linear_scale"),
    (r"Program Progress$", "donut_large"),
    (r"Power State$", "power_settings_new"),
    (r"Door Signal$", "door_front"),
    (r"Spinning Speed$", "rotate_right"),
    (r"Drying Target$", "tune"),
    (r"Shutdown$|Startup$", "power_settings_new"),
    (r"Channel$", "live_tv"),
    (r"Title$", "title"),
    (r"Description$", "description"),
    (r"Water Meter Value Day$", "water_drop"),
    (r"Water Meter Value$", "water"),
    (r"Water Meter Rate$", "speed"),
    (r"Water Meter Change$", "trending_up"),
    (r"DHW Tank Temperature|DHW Temp", "shower"),
    (r"Setpoint|Target Temp|Temp Heating|Target Temperature", "device_thermostat"),
    (r"Temperature|Temp$|Temp Current$|Dewpoint|Heat Index", "thermostat"),
    (r"Operation Mode|IU Operation|Mode$", "tune"),
    (r"Signal Strength$", "network_wifi"),
    (r"Signal$", "signal_cellular_alt"),
    (r"Power$| P\d$|Ptot$|Active Peak", "bolt"),
]


def device_icon(name):
    for prefix in sorted(DEVICE_ICONS, key=len, reverse=True):
        if name.startswith(prefix):
            return DEVICE_ICONS[prefix]
    return None


def icon_for(name, label, item_type):
    """The new icon (category) for an item."""
    if name.startswith(("influxdb_", "mapdb_")):
        return M + "storage"
    if item_type == "Group":
        return M + (device_icon(name) or "category")
    if item_type == "Switch" and re.search(r"Switch$|Power$", label or "") and not re.search(r"DHW|Climate|Thermostat", label or ""):
        # a plug's or unit's on/off switch shows the device it switches
        return M + (device_icon(name) or "toggle_on")
    for pattern, icon in MEASURE_ICONS:
        if re.search(pattern, label or ""):
            return icon if icon.startswith("oh:") else M + icon
    return M + (device_icon(name) or "label")


# classic icons of widgets without an item, in pages and the sitemap
CLASSIC_TO_MATERIAL = {
    "sun_clouds": "wb_sunny", "price": "euro", "house": "home", "energy": "bolt", "temperature": "thermostat",
    "solarplant": "solar_power", "battery": "battery_charging_full", "climate": "ac_unit", "heating": "heat_pump",
    "fan": "air", "water": "water", "oil": "coffee", "washingmachine": "local_laundry_service",
    "washingmachine_2": "local_laundry_service", "dryer": "dry_cleaning", "rain": "flatware", "office": "computer",
    "cinema": "tv", "network": "router", "light": "light", "switch": "toggle_on", "time": "schedule", "chart": "show_chart",
    "screen": "tv", "garage": "electric_car", "bath": "shower", "flow": "water", "flowpipe": "arrow_upward",
    "returnpipe": "arrow_downward", "temperature_hot": "shower", "temperature_cold": "thermostat", "fire": "local_fire_department",
    "settings": "settings", "error": "error", "shield": "shield", "pressure": "compress", "humidity": "water_drop",
    "carbondioxide": "co2", "qualityofservice": "insights", "siren": "whatshot", "movecontrol": "swap_vert",
    "smoke": "air", "piggybank": "eco", "sofa": "weekend", "soundvolume_mute": "volume_off", "soundvolume": "volume_up",
    "pump": "cyclone", "batterylevel": "battery_std", "sunrise": "schedule", "sunset": "schedule",
}
