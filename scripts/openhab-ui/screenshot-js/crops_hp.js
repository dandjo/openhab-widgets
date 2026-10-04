(() => {
  const card = document.querySelector(".page-current .card");
  const leaf = t => [...card.querySelectorAll("*")].find(e => e.childElementCount === 0 && e.textContent.trim() === t);
  const up = (e, ok) => { while (e && !ok(getComputedStyle(e), e)) e = e.parentElement; return e.getBoundingClientRect(); };
  const r = { "pill-switches": up(leaf("Heating"), cs => cs.display === "grid"),
              "boost-dhw": up(leaf("Hot water boost"), cs => cs.borderRadius === "26px") };
  return JSON.stringify(Object.entries(r).map(([k, b]) => [k, b.left, b.top, b.width, b.height]));
})()
