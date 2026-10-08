(async (index) => {
  // opens the weather page's day popup of the index-th forecast day and lets it grow to its content, the page below it
  // as tall, so cdp_elems.py's viewport (the page's length) holds the whole popup
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const links = [...document.querySelectorAll(".page-current a.link")]
    .filter(a => a.parentElement && getComputedStyle(a.parentElement).display === "grid");
  links[index].click();
  await sleep(9000);
  const pop = document.querySelector(".popup.modal-in");
  if (!pop) return "no popup";
  const nav = pop.querySelector(".navbar"), content = pop.querySelector(".page-content");
  const height = Math.ceil(nav.offsetHeight + content.scrollHeight);
  pop.style.setProperty("--f7-popup-tablet-height", height + "px");
  // every page content taller than the popup, whichever of them cdp_elems.py measures for its viewport
  document.querySelectorAll(".page-content").forEach(e => { e.style.minHeight = (height + 200) + "px"; });
  await sleep(2500);
  return height;
})
