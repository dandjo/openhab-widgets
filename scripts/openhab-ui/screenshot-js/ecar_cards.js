(() => {
  // the e-car page's Škoda Enyaq card and its controls (beside it on a desktop, under it on a phone) as one picture
  const titled = (title) => [...document.querySelectorAll(".page-current .card")].find((card) =>
    [...card.querySelectorAll(".card-header, .card-header *")].some((e) => e.textContent.trim() === title));
  const cards = ["Škoda Enyaq", "Controls"].map(titled).filter(Boolean).map((c) => c.getBoundingClientRect());
  if (cards.length < 2) return JSON.stringify([]);
  const l = Math.min(...cards.map(r => r.left)), t = Math.min(...cards.map(r => r.top));
  const r = Math.max(...cards.map(r => r.right)), b = Math.max(...cards.map(r => r.bottom));
  return JSON.stringify([["e-car", l, t, r - l, b - t]]);
})()
