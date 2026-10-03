(async (card, title, round) => {
  // opens the popup titled `title` from the card titled `card` and lets it grow to its content, so the screenshot shows
  // all of it: taps the card's links in turn until that popup opens; with `round` only round ones, the energy flow's
  // nodes, so no switch tile is switched
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const c = [...document.querySelectorAll(".page-current .card")].find(c => (c.querySelector(".card-header") || {}).innerText?.trim() === card);
  const links = [...c.querySelectorAll("a.link")].filter(a => !round || getComputedStyle(a).borderRadius === "50%");
  for (const a of links) {
    a.click();
    await sleep(2500);
    const pop = document.querySelector(".popup.modal-in");
    if (!pop) continue;
    if ((pop.querySelector(".navbar .title") || {}).innerText?.trim() === title) {
      // its content ends with the button Alle Details and the panel's padding of 12 px
      const nav = pop.querySelector(".navbar"), content = pop.querySelector(".page-content");
      const end = [...pop.querySelectorAll(".button")].find(b => b.textContent.includes("Alle Details"));
      const height = end.getBoundingClientRect().bottom - content.getBoundingClientRect().top + content.scrollTop + 12;
      pop.style.setProperty("--f7-popup-tablet-height", Math.ceil(nav.offsetHeight + height) + "px");
      await sleep(1500);
      return title;
    }
    pop.querySelector(".navbar .left a").click();
    await sleep(1500);
  }
  return "not found: " + title;
})
