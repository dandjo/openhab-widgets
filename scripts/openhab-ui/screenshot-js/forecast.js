(() => {
  // the weather page's warnings and forecast cards, together
  const cards = [...document.querySelectorAll(".page-current .card")];
  const card = t => cards.find(c => (c.querySelector(".card-header") || {}).innerText === t).getBoundingClientRect();
  const a = card("Warnungen"), z = card("Vorhersage");
  return JSON.stringify([["weather-forecast", a.left, a.top, a.width, z.bottom - a.top]]);
})()
