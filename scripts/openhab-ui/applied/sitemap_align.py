#!/usr/bin/env python3
"""Align the default sitemap's controls with MainUI: the air conditioner in its popup's order (Ein/Aus, Modus, Lüfter;
Luftstrom; Soll, Boost, Timer; Modi; the restart), the heat pump's switches as Betrieb with Automatik on the group
heatpump_management, the ventilation's automations after the timer; MainUI's names and icons, both boosts with the
rocket. Only the control frames and a few icons change; the values below them stay.
Usage: sitemap_align.py check|apply   (with openHAB stopped for apply)"""
import copy
import json
import sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
NAME = "uicomponents_system_sitemap.json"
data, enc = m.detect(m.DB + NAME)
root = data["default"]["value"]
changes = []


def find(c, label, comp):
    if c.get("component") == comp and c.get("config", {}).get("label", "") == label:
        return c
    for slot in (c.get("slots") or {}).values():
        for x in slot:
            r = find(x, label, comp)
            if r:
                return r


def set_cfg(w, label=None, icon=None, item=None):
    cfg = w["config"]
    for key, value in (("label", label), ("item", item), ("icon", icon)):
        if value is not None and cfg.get(key) != value:
            changes.append(f"  {cfg.get('item')}: {key} {cfg.get(key)!r} -> {value!r}")
            cfg[key] = value
    return w


def controls(page_label):
    """The device subpage and its first frame's widgets by (component, item), each used once."""
    page = find(find(root, "Geräte", "Frame"), page_label, "Text")
    frame = page["slots"]["widgets"][0]
    assert frame["component"] == "Frame" and not frame["config"].get("label"), page_label
    pool = {}
    for w in frame["slots"]["widgets"]:
        key = (w["component"], w["config"]["item"])
        assert key not in pool or key[0] in ("Selection", "Setpoint"), key
        pool.setdefault(key, []).append(w)
    return page, frame, pool


def take(pool, comp, name, **cfg):
    return set_cfg(pool[(comp, name)].pop(0), **cfg)


def frame_like(template, label, widgets):
    f = copy.deepcopy(template)
    f["config"]["label"] = label
    f["slots"]["widgets"] = widgets
    return f


def replace_first_frame(page, frame, pool, groups):
    used = sum(len(ws) for _, ws in groups)
    left = [w for ws in pool.values() for w in ws]  # every control placed once
    assert not left, [w["config"]["item"] for w in left]
    page["slots"]["widgets"][0:1] = [frame_like(frame, label, ws) for label, ws in groups]
    changes.append(f"  {page['config']['label']}: {used} controls in {len(groups)} frames")


# the air conditioner
page, frame, p = controls("Klimaanlage")
replace_first_frame(page, frame, p, [
    ("", [take(p, "Switch", "faikout_perfera_switch"),
          take(p, "Selection", "faikout_perfera_mode", icon="material:thermostat_auto"),
          take(p, "Selection", "faikout_perfera_fan", icon="material:air")]),
    ("Luftstrom", [take(p, "Switch", "faikout_perfera_swingh", label="Schwenken H", icon="material:swap_horiz"),
                   take(p, "Switch", "faikout_perfera_swingv", label="Schwenken V", icon="material:swap_vert"),
                   take(p, "Switch", "faikout_perfera_streamer_mode", icon="material:auto_awesome")]),
    ("", [take(p, "Selection", "faikout_perfera_temperature_setpoint", label="Soll", icon="material:device_thermostat"),
          take(p, "Switch", "faikout_perfera_powerful", label="Boost", icon="material:rocket_launch"),
          take(p, "Selection", "air_conditioning_timer"), take(p, "Setpoint", "air_conditioning_timer")]),
    ("Modi", [take(p, "Switch", "faikout_perfera_eco_mode", label="Eco", icon="material:eco"),
              take(p, "Switch", "faikout_perfera_comfort_mode", label="Komfort", icon="material:weekend"),
              take(p, "Switch", "faikout_perfera_quiet_mode", label="Leise", icon="material:volume_off")]),
    ("", [take(p, "Switch", "faikout_perfera_restart")])])

# the heat pump; Automatik switches the group, which passes the command on to the hot-water automation
page, frame, p = controls("Wärmepumpe")
replace_first_frame(page, frame, p, [
    ("", [take(p, "Selection", "espaltherma_smart_grid", icon="material:power")]),
    ("Betrieb", [take(p, "Switch", "pyaltherma_climate_control_power", label="Heizung",
                      icon="material:local_fire_department"),
                 take(p, "Switch", "pyaltherma_dhw_power", icon="material:shower"),
                 take(p, "Switch", "heatpump_dhw_management", label="Automatik", item="heatpump_management",
                      icon="material:auto_mode")]),
    ("", [take(p, "Selection", "pyaltherma_dhw_temp_heating", label="Warmwasser Soll", icon="material:shower"),
          take(p, "Switch", "pyaltherma_dhw_powerful", icon="material:rocket_launch"),
          take(p, "Selection", "pyaltherma_leaving_water_temp_offset_heating", icon="material:tune")])])
status = [w for f in page["slots"]["widgets"] for w in f.get("slots", {}).get("widgets", [])
          if w["config"].get("item") == "espaltherma_powerful_dhw_operation"]
assert len(status) == 1
set_cfg(status[0], icon="material:rocket_launch")

# the ventilation: the level, its timer, then the automations, with MainUI's icons
page, frame, p = controls("Lüftung")
replace_first_frame(page, frame, p, [
    ("", [take(p, "Selection", "esplyfterl_level"),
          take(p, "Selection", "ventilation_timer"), take(p, "Setpoint", "ventilation_timer"),
          take(p, "Switch", "ventilation_management", icon="material:tune"),
          take(p, "Switch", "ventilation_co2_management", icon="material:co2"),
          take(p, "Switch", "ventilation_humidity_management", icon="material:water_drop"),
          take(p, "Switch", "ventilation_temperature_management", icon="material:thermostat")])])

# the quick access
quick = find(root, "Schnellzugriff", "Frame")["slots"]["widgets"]
for w in quick:
    item = w["config"].get("item")
    if item == "espaltherma_smart_grid":
        set_cfg(w, label="Smart Grid")
    elif item == "pyaltherma_dhw_powerful":
        set_cfg(w, icon="material:rocket_launch")

print("\n".join(changes))
text = m.encode(data, *enc)
print(f"{NAME}: encoder html={enc[0]} newline={enc[1]} ok, {len(changes)} changes")
if sys.argv[1] == "apply":
    open(m.DB + NAME, "w", encoding="utf-8").write(text)
    print("written")
