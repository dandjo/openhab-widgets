(async () => {
  // demo warnings for the weather page's and the weather bar's screenshots, in this browser only: the state
  // tracking stops, so no update from openHAB overwrites them; nothing is sent to openHAB. Run it once the page has
  // its states
  const st = document.querySelector("#app").__vue_app__.config.globalProperties.$pinia._s.get("states");
  st.stopTrackingStates();
  const now = Math.floor(Date.now() / 3600000) * 3600;
  const list = JSON.stringify([
    { type: "Thunderstorm", level: 2, start: now - 3600, end: now + 6 * 3600,
      text: "Thunderstorms with heavy rain, hail and gale-force gusts. Local flooding possible." },
    { type: "Wind", level: 1, start: now + 20 * 3600, end: now + 32 * 3600, text: "Gale-force gusts up to 70 km/h." },
  ]);
  const text = (s) => ({ state: s, displayState: s, type: "String" });
  await new Promise(r => setTimeout(r, 500));
  st.setItemState("weather_warning_list", text(list));
  st.setItemState("weather_warning_level", { state: "2", displayState: "Orange", numericState: 2, type: "Decimal" });
  await new Promise(r => setTimeout(r, 1500));
  return "demo warnings";
})()
