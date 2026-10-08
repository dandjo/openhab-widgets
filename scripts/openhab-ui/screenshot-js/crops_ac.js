(() => {
  const card = document.querySelector(".page-current .card");
  const leaf = t => [...card.querySelectorAll("*")].find(e => e.childElementCount === 0 && e.textContent.trim() === t);
  const up = (e, ok) => { while (e && !ok(getComputedStyle(e), e)) e = e.parentElement; return e.getBoundingClientRect(); };
  // found by their build, not their corners, which the look may change
  const power = [...card.querySelectorAll("div")].find(e => getComputedStyle(e).height === "40px" && getComputedStyle(e).position === "relative" && getComputedStyle(e).display === "flex");
  const r = { "power-pill": power.getBoundingClientRect(),
              "boost-ac": up(leaf("Boost"), cs => cs.padding === "6px 10px 6px 6px"),
              "switch-rows": up(leaf("Modes"), cs => cs.paddingTop === "8px" && cs.flexDirection === "column") };
  return JSON.stringify(Object.entries(r).map(([k, b]) => [k, b.left, b.top, b.width, b.height]));
})()
