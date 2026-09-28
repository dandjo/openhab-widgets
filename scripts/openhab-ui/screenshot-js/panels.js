(() => {
  const card = [...document.querySelectorAll(".page-current .card")].find(c => (c.querySelector(".card-header") || {}).innerText === "Steuerung");
  const panel = t => { let e = [...card.querySelectorAll("*")].find(x => x.childElementCount === 0 && x.textContent.trim() === t);
    while (e && !(getComputedStyle(e).borderRadius === "14px" && getComputedStyle(e).paddingTop === "10px")) e = e.parentElement;
    return e.getBoundingClientRect(); };
  const r = { "heatpump-controls": panel("Wärmepumpe"), "air-conditioner-controls": panel("Klimaanlage"),
              "ventilation-controls": panel("Lüftung") };
  const out = Object.entries(r).map(([k, b]) => [k, b.left, b.top, b.width, b.height]);
  const a = r["heatpump-controls"], z = r["ventilation-controls"];
  out.push(["device-heads", a.left, a.top, a.width, z.bottom - a.top]);
  return JSON.stringify(out);
})()
