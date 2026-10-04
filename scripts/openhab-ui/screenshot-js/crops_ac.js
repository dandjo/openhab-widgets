(() => {
  const card = document.querySelector(".page-current .card");
  const leaf = t => [...card.querySelectorAll("*")].find(e => e.childElementCount === 0 && e.textContent.trim() === t);
  const up = (e, ok) => { while (e && !ok(getComputedStyle(e), e)) e = e.parentElement; return e.getBoundingClientRect(); };
  const power = [...card.querySelectorAll("div")].find(e => getComputedStyle(e).borderRadius === "20px" && getComputedStyle(e).height === "40px");
  const r = { "power-pill": power.getBoundingClientRect(),
              "boost-ac": up(leaf("Boost"), cs => cs.borderRadius === "26px"),
              "switch-rows": up(leaf("Modes"), cs => cs.paddingTop === "8px" && cs.flexDirection === "column") };
  return JSON.stringify(Object.entries(r).map(([k, b]) => [k, b.left, b.top, b.width, b.height]));
})()
