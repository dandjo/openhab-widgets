(async (unplugged) => {
  // demo values for the e-car page's screenshots, in this browser only: the state tracking stops, so no update from
  // openHAB overwrites them; nothing is sent to openHAB. Charging at home (unplugged = false) or back from a drive
  // with the cable out (true); every time relative to now, the trips made up, so no screenshot shows a real one
  const st = document.querySelector("#app").__vue_app__.config.globalProperties.$pinia._s.get("states");
  st.stopTrackingStates();
  const q = (v, unit, digits) => ({ state: `${v} ${unit}`, numericState: v, unit, type: "Quantity",
    displayState: `${v.toFixed(digits)} ${unit}` });  // English, as the repository's screenshots
  const on = (b, yes, no) => ({ state: b ? "ON" : "OFF", type: "OnOff", displayState: b ? yes : no });
  const text = (state, shown) => ({ state, type: "String", displayState: shown });
  const shut = { state: "CLOSED", type: "OpenClosed", displayState: "Closed" };
  const none = { state: "UNDEF", type: "UnDef" };
  const pad = (n) => String(n).padStart(2, "0");
  const local = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const iso = (d) => {
    const o = -d.getTimezoneOffset();
    return `${local(d)}T${pad(d.getHours())}:${pad(d.getMinutes())}:00.000${o < 0 ? "-" : "+"}`
      + `${pad(Math.floor(Math.abs(o) / 60))}${pad(Math.abs(o) % 60)}`;
  };
  const when = (minutes) => {
    const d = new Date(Date.now() + minutes * 60000);
    return { state: iso(d), type: "DateTime", displayState: `${pad(d.getHours())}:${pad(d.getMinutes())}` };
  };
  // 30 days of made-up trips, newest first: a day's km, its trips with start and end, km and kWh
  const km = [23, 0, 41, 12, 0, 0, 87, 18, 23, 0, 31, 9, 0, 154, 0, 23, 12, 0, 46, 0, 0, 23, 64, 8, 0, 19, 0, 23, 35, 0];
  const days = km.map((total, i) => {
    const d = new Date(Date.now() - i * 86400000);
    const parts = total > 30 ? [Math.round(total * 0.45), total - Math.round(total * 0.45)] : total ? [total] : [];
    const trips = parts.map((k, j) => {
      const start = i === 0 ? new Date(Date.now() - 300 * 60000) : new Date(d.setHours(17 - 8 * j, 5 + 7 * i % 40));
      const end = new Date(start.getTime() + (12 + k * 1.1) * 60000);
      const hm = (t) => `${pad(t.getHours())}:${pad(t.getMinutes())}`;
      return { id: 1000 - i * 3 - j, s: hm(start), e: hm(end), km: k, kwh: Math.round(k * 0.17 * 10) / 10, x: 0 };
    }).reverse();
    return { d: local(d), km: total, t: trips };
  }).filter((day) => day.km > 0);
  const charging = !unplugged;
  const demo = {
    skoda_enyaq_plug: on(charging, "Plugged in", "Unplugged"),
    skoda_enyaq_charging: on(charging, "On", "Off"),
    skoda_enyaq_charging_state: charging ? text("CHARGING", "Charging") : text("CONNECT_CABLE", "Not plugged in"),
    skoda_enyaq_charge_type: charging ? text("AC", "AC") : text("OFF", "Off"),
    skoda_enyaq_charge_power: q(charging ? 2.2 : 0, "kW", 1),
    skoda_enyaq_charge_rate: none,
    skoda_enyaq_soc: q(charging ? 72 : 64, "%", 0),
    skoda_enyaq_soc_estimate: charging ? q(73, "%", 0) : none,
    skoda_enyaq_range: q(charging ? 261 : 232, "km", 0),
    skoda_enyaq_charge_target: q(80, "%", 0),
    skoda_enyaq_battery_care: on(true, "On", "Off"),
    skoda_enyaq_target_reached_at: charging ? when(125) : none,
    skoda_enyaq_updated: when(charging ? -9 : -26),
    skoda_enyaq_last_read: when(-3),
    skoda_enyaq_next_read: when(charging ? 2 : 11),
    skoda_enyaq_api_requests_left: { state: "14", numericState: 14, type: "Decimal", displayState: "14" },
    skoda_enyaq_api_status: text("OK", "OK"),
    skoda_enyaq_command_result: none,
    skoda_enyaq_at_home: on(true, "At home", "Away"),
    skoda_enyaq_parking_state: text("PARKED", "Parked"),
    skoda_enyaq_locked: on(true, "Locked", "Unlocked"),
    skoda_enyaq_doors: shut, skoda_enyaq_windows: shut, skoda_enyaq_trunk: shut, skoda_enyaq_bonnet: shut,
    skoda_enyaq_lights: on(false, "On", "Off"),
    skoda_enyaq_climate: on(false, "On", "Off"),
    skoda_enyaq_climate_state: text("OFF", "Off"),
    skoda_enyaq_climate_target: q(21, "°C", 1),
    skoda_enyaq_window_heating_front: on(false, "On", "Off"),
    skoda_enyaq_window_heating_rear: on(false, "On", "Off"),
    skoda_enyaq_odometer: q(24318, "km", 0),
    skoda_enyaq_km_today: q(23, "km", 0),
    skoda_enyaq_trips: text(JSON.stringify(days), ""),
    e_car_power: q(charging ? 2310 : 0, "W", 0),
    e_car_energy_today: q(charging ? 6.4 : 0, "kWh", 1),
  };
  await new Promise(r => setTimeout(r, 500));
  for (const [name, state] of Object.entries(demo)) st.setItemState(name, state);
  await new Promise(r => setTimeout(r, 1500));
  return Object.keys(demo).length;
})
