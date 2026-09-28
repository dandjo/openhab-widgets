(() => {
  const cards = [...document.querySelectorAll(".page-current .card")].slice(0, 4).map(c => c.getBoundingClientRect());
  const l = Math.min(...cards.map(r => r.left)), t = Math.min(...cards.map(r => r.top));
  const r = Math.max(...cards.map(r => r.right)), b = Math.max(...cards.map(r => r.bottom));
  return JSON.stringify([["plug-cards", l, t, r - l, b - t]]);
})()
