#!/bin/bash
# capture_layout.sh OUTDIR: layout of every page at desktop and phone width, as JSON per page and width
OUT=$1; mkdir -p "$OUT"
JS='(() => { const pc = document.querySelector(".page-current .page-content"); if (!pc) return "{}"; const top0 = pc.getBoundingClientRect().top - pc.scrollTop; const R = e => { const r = e.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top - top0), Math.round(r.width), Math.round(r.height)]; }; const cards = [...pc.querySelectorAll(".card")].map(c => ({h: ((c.querySelector(".card-header") || {}).innerText || "").split("·")[0].trim(), r: R(c), kids: [...(c.querySelector(".card-content") || c).querySelectorAll(":scope > *, :scope > * > *, :scope > * > * > *")].slice(0, 40).map(R)})); const svgs = [...pc.querySelectorAll("svg[viewBox]")].filter(s => s.getBoundingClientRect().width > 100).map(s => [s.getAttribute("viewBox"), ...R(s)]); const canv = [...pc.querySelectorAll("canvas")].map(R); return JSON.stringify({sh: pc.scrollHeight, cards, svgs, canv}); })()'
PAGES="overview netatmo smartpi power_meter photovoltaics energy_storage e_car air_conditioning heatpump ventilation water_meter coffee_machine washing_machine_1 washing_machine_2 tumble_dryer refrigerator dishwasher living_room_entertainment network office_1 office_2 terrace_light bicycle_batteries epex_spot flow_home hp_dhw_tank appliance_washing_machine_1"
for w in 1400 390; do
  for p in $PAGES; do
    python3 cdp_evalw.py "http://127.0.0.1:18080/page/$p" 12 "$JS" $w | python3 -c "import json,sys; open('$OUT/${p}_$w.json','w').write(json.loads(sys.stdin.read()))" || echo "fail $p $w"
  done
done
ls "$OUT" | wc -l
