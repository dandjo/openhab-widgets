(() => {
  const card = [...document.querySelectorAll(".page-current .card")].find(c => (c.querySelector(".card-header") || {}).innerText === "Steuerung");
  const leaf = t => [...card.querySelectorAll("*")].find(e => e.childElementCount === 0 && e.textContent.trim() === t);
  const root = t => { let e = leaf(t); while (e && !(e.querySelector(".range-slider") && getComputedStyle(e).flexDirection === "column")) e = e.parentElement; return e.getBoundingClientRect(); };
  const a = root("Warmwasser Soll"), b = root("Vorlauf-Offset");
  return JSON.stringify([["pill-sliders", a.left, a.top, a.width, b.bottom - a.top]]);
})()
