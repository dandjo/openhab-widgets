(async () => {
  // demo values for the consumption card's screenshot, in this browser only: the state tracking stops, so no update
  // from openHAB overwrites them; nothing is sent to openHAB
  const st = document.querySelector("#app").__vue_app__.config.globalProperties.$pinia._s.get("states");
  st.stopTrackingStates();
  const q = v => ({ state: `${v} kWh`, numericState: v, unit: "kWh", type: "Quantity",
    displayState: `${v.toFixed(2).replace(".", ",")} kWh` });
  const demo = {
    home_ec_day: 16.3, photovoltaics_own_ec_day: 13.9, huawei_inverter_power_meter_ec_day: 2.4,
    espaltherma_energy_today: 3.9, e_car_energy_today: 5.1, air_conditioning_unit_energy_today: 1.3,
    air_conditioning_energy_today: 6.4, office_1_energy_today: 0.62, office_2_energy_today: 0.35,
    network_energy_today: 0.41, ventilation_energy_today: 0.98, refrigerator_energy_today: 0.52,
    coffee_machine_energy_today: 0.18, living_room_entertainment_energy_today: 0.44, dishwasher_energy_today: 0.95,
    washing_machine_1_energy_today: 0.61, washing_machine_2_energy_today: 0, tumble_dryer_energy_today: 0,
    terrace_light_energy_today: 0.05, bicycle_batteries_energy_today: 0.12,
  };
  await new Promise(r => setTimeout(r, 500));
  for (const [name, v] of Object.entries(demo)) st.setItemState(name, q(v));
  await new Promise(r => setTimeout(r, 1500));
  return Object.keys(demo).length;
})()
