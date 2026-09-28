#!/bin/bash
# every screenshot of the widget repository, into shots/v4/repo under the repository's names; needs the page
# widget_gallery (widget_gallery.py apply) and the SSH tunnel on 18080. The energy flow and the consumption card are
# shot with demo values (demo_flow.js, demo_consumption.js), set in the browser only
set -u
B=http://127.0.0.1:18080/page
O=shots/v4; R=$O/repo; mkdir -p $O $R
step() { echo "$(date +%T) $*"; }
step overview; python3 cdp_shot.py $B/overview $R/overview-light.png 16 1400 1621 >/dev/null
python3 cdp_shot.py $B/overview $R/overview-dark.png 16 1400 1621 dark >/dev/null
python3 cdp_shot.py $B/overview $R/overview-phone.png 16 390 1400 >/dev/null
step cards; python3 cdp_cards.py $B/overview $O/ov 1400 >/dev/null
python3 cdp_cards.py $B/overview $O/ovd 1400 dark >/dev/null
cp $O/ov-0-steuerung.png $R/controls-card.png; cp $O/ovd-0-steuerung.png $R/controls-card-dark.png
cp $O/ov-2-haushaltsgeraete.png $R/appliances-card.png; cp $O/ov-3-strompreis.png $R/electricity-price-card.png
cp $O/ov-4-waermepumpe.png $R/heatpump-card.png; cp $O/ovd-4-waermepumpe.png $R/heatpump-card-dark.png
cp $O/ov-5-*.png $R/consumption-card.png; cp $O/ov-6-*.png $R/energy-days-card.png
cp $O/ov-7-*.png $R/pv-days-card.png; cp $O/ov-8-*.png $R/temperatures-card.png
python3 cdp_cards_js.py $B/overview $O/ovcons 1400 light "$(cat demo_consumption.js)" >/dev/null
cp $O/ovcons-5-*.png $R/consumption-card.png
step open; python3 cdp_cards_js.py $B/overview $O/ovopen 1400 light "$(cat screenshot-js/unfold.js)" >/dev/null
cp $O/ovopen-0-steuerung.png $R/controls-card-open.png
step flow; PRE_JS=demo_flow.js FPS=20 python3 cdp_gif.py $B/overview 1 1400 $R/energy-flow-card.gif 6 light 1.5
python3 cdp_cards_js.py $B/overview $O/ovdemo-dark 1400 dark "$(cat screenshot-js/demo_flow.js)" >/dev/null
cp $O/ovdemo-dark-1-energiefluss.png $R/energy-flow-card-dark.png
step panels; python3 cdp_elems.py $B/overview 1400 $O/folded "$(cat screenshot-js/panels.js)" >/dev/null
python3 cdp_elems.py $B/overview 1400 $O/unfolded "$(cat screenshot-js/panels.js)" "$(cat screenshot-js/unfold.js)" >/dev/null
cp $O/folded/device-heads.png $R/; for p in heatpump-controls air-conditioner-controls ventilation-controls; do cp $O/unfolded/$p.png $R/; done
step crops; python3 cdp_elems.py $B/heatpump 1400 $O/crops "$(cat screenshot-js/crops_hp.js)" >/dev/null
python3 cdp_elems.py $B/air_conditioning 1400 $O/crops "$(cat screenshot-js/crops_ac.js)" >/dev/null
python3 cdp_elems.py $B/overview 1400 $O/crops "$(cat screenshot-js/sliders.js)" "$(cat screenshot-js/hp_unfold.js)" >/dev/null
python3 cdp_elems.py $B/coffee_machine 1400 $O/crops "$(cat screenshot-js/plugcards.js)" >/dev/null
python3 cdp_elems.py $B/air_conditioning 1400 $O/crops "$(cat screenshot-js/tiles.js)" >/dev/null
for c in pill-switches power-pill switch-rows pill-sliders plug-cards value-tiles; do cp $O/crops/$c.png $R/; done
# the switch rows' crop ends above the restart button below them
python3 -c "from PIL import Image; s = Image.open('$R/switch-rows.png'); s.crop((0, 0, s.size[0], s.size[1] - 10)).save('$R/switch-rows.png')"
python3 -c "
from PIL import Image
a = Image.open('$O/crops/boost-dhw.png'); b = Image.open('$O/crops/boost-ac.png')
s = Image.new('RGB', (max(a.size[0], b.size[0]), a.size[1] + b.size[1]), 'white'); s.paste(a, (0, 0)); s.paste(b, (0, a.size[1]))
s.save('$R/boost-pills.png')"
step popup; python3 cdp_tap2.py $B/coffee_machine $R/item-popup.png "Energie heute"
step gallery; python3 cdp_cards.py $B/widget_gallery $O/g900 900 >/dev/null
cp $O/g900-2-flow-share-ring.png $R/flow-share-rings.png; cp $O/g900-5-state-bar.png $R/state-bars.png
cp $O/g900-6-switch-tile.png $R/switch-tiles.png
FPS=20 python3 cdp_gif.py $B/widget_gallery 0 900 $R/flow-node.gif 6 light 1.5
FPS=20 python3 cdp_gif.py $B/widget_gallery 1 900 $R/flow-link.gif 6 light 1.5
FPS=20 python3 cdp_gif.py $B/widget_gallery 3 900 $R/appliance-icon.gif 4 light 1.5
step done; ls $R | wc -l
