(async () => {
  // demo values for the energy flow's screenshots, in this browser only: the state tracking stops, so no update
  // from openHAB overwrites them; nothing is sent to openHAB
  const st = document.querySelector("#app").__vue_app__.config.globalProperties.$pinia._s.get("states");
  st.stopTrackingStates();
  const q = (v, unit, digits) => ({ state: `${v} ${unit}`, numericState: v, unit, type: "Quantity",
    displayState: `${v.toFixed(digits).replace(".", ",")} ${unit}` });
  const demo = {
    huawei_inverter_input_power: q(6240, "W", 0), huawei_inverter_power_meter_active_power: q(-870, "W", 0),
    huawei_inverter_energy_storage_power: q(-1480, "W", 0), huawei_inverter_energy_storage_soc: q(64, "%", 0),
    home_active_power: q(3890, "W", 0), espaltherma_electrical_power: q(1210, "W", 0),
    air_conditioning_unit_power: q(460, "W", 0), e_car_power: q(1920, "W", 0),
    huawei_inverter_e_day: q(24.6, "kWh", 2), photovoltaics_own_ec_day: q(13.9, "kWh", 2), home_ec_day: q(16.3, "kWh", 2),
    huawei_inverter_power_meter_ec_day: q(2.4, "kWh", 2), huawei_inverter_power_meter_ep_day: q(10.7, "kWh", 2),
    espaltherma_energy_today: q(4.8, "kWh", 2), air_conditioning_unit_energy_today: q(1.3, "kWh", 2),
    e_car_energy_today: q(6.9, "kWh", 2), huawei_inverter_energy_storage_day_charge: q(5.2, "kWh", 2),
    huawei_inverter_energy_storage_day_discharge: q(1.9, "kWh", 2),
    washing_machine_1_power: q(1950, "W", 0), washing_machine_2_power: q(4.1, "W", 1), tumble_dryer_power: q(0.4, "W", 1),
    dishwasher_power: q(0.3, "W", 1), washing_machine_1_energy_today: q(3.029, "kWh", 3),
    washing_machine_2_energy_today: q(1.511, "kWh", 3), tumble_dryer_energy_today: q(1.057, "kWh", 3),
    dishwasher_energy_today: q(0.007, "kWh", 3),
    faikout_perfera_switch: { state: "ON", type: "OnOff" },
  };
  await new Promise(r => setTimeout(r, 500));
  for (const [name, state] of Object.entries(demo)) st.setItemState(name, state);
  await new Promise(r => setTimeout(r, 1500));
  return Object.keys(demo).length;
})()
