(() => { const el = [...document.querySelectorAll(".page-current .card:first-child *")].find(e => e.childElementCount === 0 && e.textContent.trim() === "Wärmepumpe");
  let p = el, link = null; while (p && !link) { link = p.querySelector(":scope > a"); p = p.parentElement; } link.click(); return 1; })()
