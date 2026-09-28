"""Shared by the heat pump checks: InfluxDB access and heatpump_metering's split (with variants A and B) in Python."""
import json
import os
import urllib.parse
import urllib.request

INFLUX = os.environ.get("INFLUX", "http://127.0.0.1:18086")  # default: an ssh tunnel to homepi's InfluxDB
DAY = int(86400e9)

# the rule's inputs; switches are stored as 1/0
INPUTS = {
    "plug": "heatpump_power",
    "inv_frequency": "espaltherma_inv_frequency",
    "inv_current": "espaltherma_inv_primary_current",
    "pump": "espaltherma_water_pump_operation",
    "valve": "espaltherma_3way_valve_mode",
    "bsh": "espaltherma_bsh_mode",
    "buh1": "espaltherma_buh_step1_mode",
    "buh2": "espaltherma_buh_step2_mode",
    "op_mode": "espaltherma_operation_mode",
    "flow": "espaltherma_flow_sensor",
    "inlet": "espaltherma_inlet_water_temp",
    "lwt_before": "espaltherma_leaving_water_temp_before_buh",
    "lwt_after": "espaltherma_leaving_water_temp_after_buh",
    "climate": "pyaltherma_climate_control_power",
    "sh_operation": "espaltherma_space_heating_operation",
}
SWITCHES = {"pump", "bsh", "buh1", "buh2", "climate", "sh_operation"}


def query(q):
    url = f"{INFLUX}/query?" + urllib.parse.urlencode({"db": "openhab", "epoch": "ns", "q": q})
    series = json.load(urllib.request.urlopen(url, timeout=900))["results"][0].get("series", [])
    return [(t, v) for t, v in series[0]["values"]] if series else []


def points(m, a, b, step=7 * DAY):
    out = []
    for s in range(a, b, step):
        out += query(f'SELECT value FROM "{m}" WHERE time >= {s} AND time < {min(b, s + step)}')
    return out


def before(m, t):
    p = query(f'SELECT value FROM "{m}" WHERE time < {t} ORDER BY time DESC LIMIT 1')
    return p[0] if p else None


def write(lines):
    for i in range(0, len(lines), 5000):
        req = urllib.request.Request(f"{INFLUX}/write?" + urllib.parse.urlencode({"db": "openhab", "precision": "ns"}),
                                     data="\n".join(lines[i:i + 5000]).encode(), method="POST")
        with urllib.request.urlopen(req, timeout=300) as resp:
            assert resp.status == 204, resp.status


def value(key, v):
    if key in SWITCHES:
        return "ON" if v in (1, 1.0, True, "ON") else "OFF"
    return v


def events(a, b):
    """Every change of an input between a and b as (t, key, value), with the state before a first (t = a)."""
    ev = []
    for key, m in INPUTS.items():
        p = before(m, a)
        if p is not None:
            ev.append((a, key, value(key, p[1])))
        ev += [(t, key, value(key, v)) for t, v in points(m, a, b)]
    ev.sort(key=lambda e: (e[0], e[1]))
    return ev


class Metering:
    """heatpump_metering's split up to the energy integration, with variants A and B. Times in ns."""

    def __init__(self):
        self.pump_mode = None

    def step(self, x, now, valve_changed):
        plug = x.get("plug")
        is_inverter = (plug is not None and plug > 70) or (x.get("inv_frequency") or 0) > 0 \
            or (x.get("inv_current") or 0) > 0
        is_pump = x.get("pump") == "ON"
        valve = x.get("valve")
        dhw_travel = valve == "Space" and valve_changed is not None and now - valve_changed < 30e9
        is_dhw = valve == "DHW" or dhw_travel
        is_space = valve == "Space" and not dhw_travel
        if is_pump and (is_dhw or is_space):
            self.pump_mode = "DHW" if is_dhw else "Space"
        elif not is_pump and is_inverter and valve != "DHW":
            if self.pump_mode in ("DHW", "Space"):
                is_dhw = self.pump_mode == "DHW"
                is_space = self.pump_mode == "Space"
        is_bsh = x.get("bsh") == "ON"
        is_buh = x.get("buh1") == "ON" or x.get("buh2") == "ON"
        heating_off = x.get("climate") == "OFF" and x.get("sh_operation") == "OFF"
        pump_only = False
        if heating_off and is_space:
            is_space, is_dhw = False, True
            pump_only = not is_inverter and not is_buh
        p = plug or 0.0  # JavaScript adds a null as 0
        space = dhw = standby = 0.0
        if is_space and (is_inverter or is_pump):
            space += p
        if is_dhw and (is_inverter or is_pump) and not pump_only:
            dhw += p
        if (not is_inverter and not is_pump) or pump_only:
            standby += p
        if x.get("buh1") == "ON":
            space += 2000 if is_space else 0
            dhw += 2000 if is_dhw else 0
        if x.get("buh2") == "ON":
            space += 4000 if is_space else 0
            dhw += 4000 if is_dhw else 0
        if is_bsh:
            dhw += 2000
        before_buh = after_buh = h_space = h_dhw = 0.0
        if x.get("op_mode") == "Heating":
            flow_kg_h = (x.get("flow") or 0) * 60
            inlet = x.get("inlet") or 0
            before_buh += flow_kg_h * 1.1639 * ((x.get("lwt_before") or 0) - inlet)
            after_buh += flow_kg_h * 1.1639 * ((x.get("lwt_after") or 0) - inlet)
            h_space += after_buh if is_space else 0
            h_dhw += after_buh if is_dhw else 0
        if is_bsh:
            h_dhw += 2000
        return {"space": space, "dhw": dhw, "standby": standby, "total": space + dhw + standby,
                "h_before": before_buh, "h_after": after_buh, "h_space": h_space, "h_dhw": h_dhw,
                "h_total": h_space + h_dhw}
