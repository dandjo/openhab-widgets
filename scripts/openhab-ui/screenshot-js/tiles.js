(() => {
  const card = [...document.querySelectorAll(".page-current .card")].find(c => (c.querySelector(".card-header") || {}).innerText === "Now");
  const grid = [...card.querySelectorAll("div")].find(e => getComputedStyle(e).display === "grid");
  const r = grid.getBoundingClientRect();
  return JSON.stringify([["value-tiles", r.left, r.top, r.width, r.height]]);
})()
