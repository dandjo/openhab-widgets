#!/bin/bash
# every screenshot of the widget repository, into shots/v4/repo under the repository's names, in English as the
# repository publishes the widgets: through ui_proxy.py on 18081 (in front of the SSH tunnel on 18080), which hands the
# browser the English widgets and pages; needs the page widget_gallery (widget_gallery.py writes it, to be POSTed to
# ui:page). The energy flow, the
# heat pump card, the heating card, the consumption card and the weather page's warnings are shot with demo values (demo_flow.js,
# demo_heatpump.js, demo_consumption.js, demo_weather.js), set in the browser only
set -u
B=${BASE:-http://127.0.0.1:18081}/page
O=shots/v4; R=$O/repo; mkdir -p $O $R
step() { echo "$(date +%T) $*"; }
shot() { ls $O/$1-*-$2.png | head -1; }  # a card's screenshot by its title, whatever its place on the page
# the overview in its whole length, nothing cut off at the bottom (user, 2026-10-04)
# 1600 px wide, where Consumption Today lists its consumers in two columns (user, 2026-10-04)
step overview; python3 cdp_shot.py $B/overview $R/overview-light.png 16 1600 full >/dev/null
python3 cdp_shot.py $B/overview $R/overview-dark.png 16 1600 full dark >/dev/null
python3 cdp_shot.py $B/overview $R/overview-phone.png 16 390 full >/dev/null
step cards; python3 cdp_cards.py $B/overview $O/ov 1400 >/dev/null
python3 cdp_cards.py $B/overview $O/ovd 1400 dark >/dev/null
cp $(shot ov appliances) $R/appliances-card.png; cp $(shot ov electricity-price) $R/electricity-price-card.png
cp $(shot ov switches) $R/switches-card.png
cp $(shot ov consumption-today*) $R/consumption-card.png; cp $(shot ov energy-per-day) $R/energy-days-card.png
cp $(shot ov pv-yield*) $R/pv-days-card.png; cp $(shot ov temperatures) $R/temperatures-card.png
cp $O/ov-0-card.png $R/weather-card.png; cp $O/ovd-0-card.png $R/weather-card-dark.png
# 1600 px, where the consumers list shows each consumer's share beside its energy
python3 cdp_cards_js.py $B/overview $O/ovcons 1600 light "$(cat demo_consumption.js)" >/dev/null
cp $(shot ovcons consumption-today*) $R/consumption-card.png
# every animated GIF also in dark mode, animated as well (user, 2026-10-04)
step flow; PRE_JS=demo_flow.js FPS=20 python3 cdp_gif.py $B/overview 1 1400 $R/energy-flow-card.gif 6 light 1.5
PRE_JS=demo_flow.js FPS=20 python3 cdp_gif.py $B/overview 1 1400 $R/energy-flow-card-dark.gif 6 dark 1.5
step heatpump; PRE_JS=demo_heatpump.js FPS=20 python3 cdp_gif.py $B/overview 5 1400 $R/heatpump-card.gif 4 light 1
PRE_JS=demo_heatpump.js FPS=20 python3 cdp_gif.py $B/overview 5 1400 $R/heatpump-card-dark.gif 4 dark 1
python3 cdp_cards_js.py $B/overview $O/ovhp-dark 1400 dark "$(cat demo_heatpump.js)" >/dev/null
# the heating card on the heat pump card's demo values: a space heating run, the tank not charging
python3 cdp_cards_js.py $B/overview $O/ovhp 1400 light "$(cat demo_heatpump.js)" >/dev/null
cp $(shot ovhp heating-hot-water) $R/heating-card.png; cp $(shot ovhp-dark heating-hot-water) $R/heating-card-dark.png
step crops; python3 cdp_elems.py $B/heatpump 1400 $O/crops "$(cat screenshot-js/crops_hp.js)" >/dev/null
python3 cdp_elems.py $B/air_conditioning 1400 $O/crops "$(cat screenshot-js/crops_ac.js)" >/dev/null
python3 cdp_elems.py $B/heatpump 1400 $O/crops "$(cat screenshot-js/sliders.js)" >/dev/null
python3 cdp_elems.py $B/coffee_machine 1400 $O/crops "$(cat screenshot-js/plugcards.js)" >/dev/null
python3 cdp_elems.py $B/air_conditioning 1400 $O/crops "$(cat screenshot-js/tiles.js)" >/dev/null
for c in pill-switches power-pill switch-rows plug-cards value-tiles; do cp $O/crops/$c.png $R/; done
# the switch rows' crop ends above the restart button below them
python3 -c "from PIL import Image; s = Image.open('$R/switch-rows.png'); s.crop((0, 0, s.size[0], s.size[1] - 10)).save('$R/switch-rows.png')"
python3 -c "
from PIL import Image
for parts, out in ((('boost-dhw', 'boost-ac'), 'boost-pills'), (('slider-dhw', 'slider-offset'), 'pill-sliders')):
    a, b = (Image.open('$O/crops/' + p + '.png') for p in parts)
    s = Image.new('RGB', (max(a.size[0], b.size[0]), a.size[1] + b.size[1]), 'white'); s.paste(a, (0, 0)); s.paste(b, (0, a.size[1]))
    s.save('$R/' + out + '.png')"
step popup; python3 cdp_tap.py $B/coffee_machine $R/item-popup.png "Energy today"
# the weather page's warnings and forecast at phone width, one card under the other, the warnings on demo values
step weather; python3 cdp_elems.py $B/weather 390 $O/weather "$(cat screenshot-js/forecast.js)" "$(cat demo_weather.js)" >/dev/null
python3 cdp_elems.py $B/weather 390 $O/weather-dark "$(cat screenshot-js/forecast.js)" "$(cat demo_weather.js)" dark >/dev/null
cp $O/weather/weather-forecast.png $R/; cp $O/weather-dark/weather-forecast.png $R/weather-forecast-dark.png
if [ "${GALLERY:-1}" = 1 ]; then  # GALLERY=0 leaves the gallery's shots as they are
step gallery; python3 cdp_cards.py $B/widget_gallery $O/g900 900 >/dev/null
cp $O/g900-2-flow-share-ring.png $R/flow-share-rings.png; cp $O/g900-5-state-bar.png $R/state-bars.png
cp $O/g900-6-switch-tile.png $R/switch-tiles.png
FPS=20 python3 cdp_gif.py $B/widget_gallery 0 900 $R/flow-node.gif 6 light 1.5
FPS=20 python3 cdp_gif.py $B/widget_gallery 1 900 $R/flow-link.gif 6 light 1.5
FPS=20 python3 cdp_gif.py $B/widget_gallery 3 900 $R/appliance-icon.gif 4 light 1.5
FPS=20 python3 cdp_gif.py $B/widget_gallery 0 900 $R/flow-node-dark.gif 6 dark 1.5
FPS=20 python3 cdp_gif.py $B/widget_gallery 1 900 $R/flow-link-dark.gif 6 dark 1.5
FPS=20 python3 cdp_gif.py $B/widget_gallery 3 900 $R/appliance-icon-dark.gif 4 dark 1.5
fi
step done; ls $R | wc -l
