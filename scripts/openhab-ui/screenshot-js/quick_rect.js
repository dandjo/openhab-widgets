((name) => {
  // the open popup's box, less the 6 px margin cdp_elems.py adds, so the backdrop stays out
  const r = document.querySelector(".popup.modal-in").getBoundingClientRect();
  return JSON.stringify([[name, r.left + 6, r.top + 6, r.width - 12, r.height - 12]]);
})
