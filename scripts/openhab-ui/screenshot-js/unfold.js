(() => { let n = 0; for (const h of ["Wärmepumpe", "Klimaanlage", "Lüftung"]) {
  const el = [...document.querySelectorAll(".page-current .card:first-child *")].find(e => e.childElementCount === 0 && e.textContent.trim() === h);
  let p = el, link = null; while (p && !link) { link = p.querySelector(":scope > a"); p = p.parentElement; }
  if (link) { link.click(); n++; } } return n; })()
