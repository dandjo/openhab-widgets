#!/bin/bash
# capture_all.sh OUTDIR: layout of every page (capture_layout.sh's JS) plus the geometry of every drawn SVG element,
# at desktop and phone width. Moving flow dots, texts' widths and hidden elements are left out of the geometry.
OUT=$1; mkdir -p "$OUT" "$(dirname $OUT)/$(basename $OUT)_geo"
LJS=$(sed -n "s/^JS='\(.*\)'$/\1/p" capture_layout.sh)
GJS='(() => { const pc = document.querySelector(".page-current .page-content"); if (!pc) return "[]"; const top0 = pc.getBoundingClientRect().top - pc.scrollTop; const out = []; [...pc.querySelectorAll("svg[viewBox]")].filter(s => s.getBoundingClientRect().width > 100).forEach((s, si) => { s.querySelectorAll("*").forEach(e => { const t = e.tagName.toLowerCase(); if (t.startsWith("animate") || t === "g" || t === "svg") return; if (e.querySelector("animateMotion")) return; for (let p = e.parentElement; p && p.tagName.toLowerCase() !== "svg"; p = p.parentElement) { if (p.querySelector(":scope > animateTransform")) return; } const r = e.getBoundingClientRect(); if (!r.width && !r.height) return; out.push(t === "text" ? [si, t, Math.round(r.top - top0 + r.height / 2)] : [si, t, Math.round(r.left * 2) / 2, Math.round((r.top - top0) * 2) / 2, Math.round(r.width * 2) / 2, Math.round(r.height * 2) / 2]); }); }); return JSON.stringify(out); })()'
PAGES="$2"
JS="(() => { const L = JSON.parse(${LJS}); const G = JSON.parse(${GJS}); L.geo = G; return JSON.stringify(L); })()"
for w in 1400 390; do
  for p in $PAGES; do
    python3 cdp_evalw.py "http://127.0.0.1:18080/page/$p" 14 "$JS" $w > "$OUT/raw_${p}_$w.txt" 2>/dev/null
    python3 -c "import json,sys; d=json.loads(json.loads(open('$OUT/raw_${p}_$w.txt').read())); geo=d.pop('geo'); open('$OUT/${p}_$w.json','w').write(json.dumps(d)); open('$OUT/../$(basename $OUT)_geo/${p}_$w.json','w').write(json.dumps(geo))" && rm "$OUT/raw_${p}_$w.txt" || echo "fail $p $w"
  done
done
ls "$OUT" | wc -l
