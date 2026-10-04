(async () => {
  // demo values for the heat pump card's recording and dark screenshot, in this browser only: a space heating run on a
  // mild winter day, compressor, pump and both heating branches at work, no heater; the state tracking stops, so no
  // update from openHAB overwrites them; nothing is sent to openHAB
  const st = document.querySelector("#app").__vue_app__.config.globalProperties.$pinia._s.get("states");
  st.stopTrackingStates();
  const q = (v, unit, digits) => ({ state: `${v} ${unit}`, numericState: v, unit, type: "Quantity",
    displayState: `${v.toFixed(digits)} ${unit}` });  // English, as the repository's screenshots
  const on = (v) => ({ state: v ? "ON" : "OFF", type: "OnOff" });
  const text = (v) => ({ state: v, type: "String" });
  const demo = {
    espaltherma_inv_frequency: q(48, "Hz", 0), espaltherma_water_pump_operation: on(true),
    espaltherma_flow_sensor: q(14.2, "l/min", 1), espaltherma_3way_valve_mode: text("Space"),
    espaltherma_defrost_operaton: on(false), espaltherma_bsh_mode: on(false),
    espaltherma_buh_step1_mode: on(false), espaltherma_buh_step2_mode: on(false),
    heatpump_power: q(1180, "W", 0), espaltherma_electrical_power: q(1180, "W", 0),
    espaltherma_electrical_power_buh: q(0, "W", 0), espaltherma_electrical_power_bsh: q(0, "W", 0),
    espaltherma_heating_power: q(4350, "W", 0), espaltherma_heating_power_after_buh: q(4350, "W", 0),
    espaltherma_cop: { state: "3.69", numericState: 3.69, displayState: "3,69", type: "Decimal" },
    espaltherma_leaving_water_temp_after_buh: q(33.5, "°C", 1), espaltherma_inlet_water_temp: q(29.1, "°C", 1),
    espaltherma_ext_ambient_temp: q(4.5, "°C", 1), espaltherma_heat_exchanger_mid_temp: q(-1.8, "°C", 1),
    espaltherma_discharge_pipe_temp: q(68.4, "°C", 1), espaltherma_refrig_temp_liquid_side: q(31.2, "°C", 1),
    espaltherma_refrigerant_pressure_sensor: q(19.8, "bar", 1), espaltherma_water_pressure: q(1.6, "bar", 1),
    espaltherma_dhw_tank_temp: q(47.5, "°C", 1), espaltherma_dhw_setpoint: q(50, "°C", 0),
    espaltherma_indoor_ambient_temp: q(21.4, "°C", 1), faikout_perfera_temperature: q(22.1, "°C", 1),
    tado_humidity: q(46, "%", 0), netatmo_weatherstation_atmospheric_humidity: q(48, "%", 0),
    netatmo_weatherstation_co2: q(640, "ppm", 0),
    pyaltherma_climate_control_power: on(true), pyaltherma_dhw_power: on(true), pyaltherma_dhw_powerful: on(false),
    espaltherma_smart_grid: { state: "0", type: "Decimal" }, heatpump_management: on(true),
  };
  await new Promise(r => setTimeout(r, 500));
  for (const [name, state] of Object.entries(demo)) st.setItemState(name, state);
  await new Promise(r => setTimeout(r, 1500));
  return Object.keys(demo).length;
})()
