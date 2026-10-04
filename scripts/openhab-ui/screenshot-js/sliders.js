(() => {
  // the heat pump page's controls: the DHW setpoint and the leaving water offset, each cropped on its own (the
  // Warmwasser-Boost stands between them)
  const card = [...document.querySelectorAll(".page-current .card")].find(c => (c.querySelector(".card-header") || {}).innerText === "Controls");
  const leaf = t => [...card.querySelectorAll("*")].find(e => e.childElementCount === 0 && e.textContent.trim() === t);
  const root = t => { let e = leaf(t); while (e && !(e.querySelector(".range-slider") && getComputedStyle(e).flexDirection === "column")) e = e.parentElement; return e.getBoundingClientRect(); };
  const a = root("Hot water target"), b = root("Flow offset");
  // cdp_elems.py adds 6 px all round, which would catch the boost pill between them; cut each crop to its slider
  const flush = (k, r) => [k, r.left, r.top + 6, r.width, r.height - 12];
  return JSON.stringify([flush("slider-dhw", a), flush("slider-offset", b)]);
})()
