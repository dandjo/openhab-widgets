#!/bin/bash
# every screenshot of the widget repository, into shots/v4/repo under the repository's names; needs the page
# widget_gallery (widget_gallery.py writes it, to be POSTed to ui:page) and the SSH tunnel on 18080. The energy flow, the consumption card and the
# weather page's warnings are shot with demo values (demo_flow.js, demo_consumption.js, demo_weather.js), set in the
# browser only
set -u
B=http://127.0.0.1:18080/page
O=shots/v4; R=$O/repo; mkdir -p $O $R
step() { echo "$(date +%T) $*"; }
shot() { ls $O/$1-*-$2.png | head -1; }  # a card's screenshot by its title, whatever its place on the page
step overview; python3 cdp_shot.py $B/overview $R/overview-light.png 16 1400 1621 >/dev/null
python3 cdp_shot.py $B/overview $R/overview-dark.png 16 1400 1621 dark >/dev/null
python3 cdp_shot.py $B/overview $R/overview-phone.png 16 390 1400 >/dev/null
step cards; python3 cdp_cards.py $B/overview $O/ov 1400 >/dev/null
python3 cdp_cards.py $B/overview $O/ovd 1400 dark >/dev/null
cp $(shot ov haushaltsgeraete) $R/appliances-card.png; cp $(shot ov strompreis) $R/electricity-price-card.png
cp $(shot ov waermepumpe) $R/heatpump-card.png; cp $(shot ovd waermepumpe) $R/heatpump-card-dark.png
cp $(shot ov verbrauch-heute*) $R/consumption-card.png; cp $(shot ov energie-pro-tag) $R/energy-days-card.png
cp $(shot ov pv-ertrag*) $R/pv-days-card.png; cp $(shot ov temperaturen) $R/temperatures-card.png
cp $O/ov-0-card.png $R/weather-card.png; cp $O/ovd-0-card.png $R/weather-card-dark.png
python3 cdp_cards_js.py $B/overview $O/ovcons 1400 light "$(cat demo_consumption.js)" >/dev/null
cp $(shot ovcons verbrauch-heute*) $R/consumption-card.png
step flow; PRE_JS=demo_flow.js FPS=20 python3 cdp_gif.py $B/overview 1 1400 $R/energy-flow-card.gif 6 light 1.5
python3 cdp_cards_js.py $B/overview $O/ovdemo-dark 1400 dark "$(cat demo_flow.js)" >/dev/null
cp $(shot ovdemo-dark energiefluss) $R/energy-flow-card-dark.png
# the quick popups as the energy flow's nodes and the heat pump card's tiles open them, each as tall as its content
step popups
for spec in "Energiefluss|Wärmepumpe|true|heatpump-quick" "Energiefluss|Klimaanlage|true|air-conditioner-quick" \
            "Energiefluss|Lüftung|true|ventilation-quick" "Wärmepumpe|Regelung|false|heatpump-control-quick" \
            "Wärmepumpe|Innengerät|false|heatpump-indoor-quick" "Wärmepumpe|Außengerät|false|heatpump-outdoor-quick" \
            "Wärmepumpe|Kältemittel|false|heatpump-refrigerant-quick" "Wärmepumpe|Heizkreis|false|heatpump-circuit-quick" \
            "Wärmepumpe|Obergeschoss|false|upper-floor-quick" "Wärmepumpe|Erdgeschoss|false|ground-floor-quick" \
            "Wärmepumpe|Elektrisch|false|heatpump-electric-quick" "Wärmepumpe|Wärme|false|heatpump-heat-quick" \
            "Wärmepumpe|COP|false|heatpump-cop-quick"; do
  IFS='|' read -r card title round name <<< "$spec"
  python3 cdp_elems.py $B/overview 1400 $O/quick "$(cat screenshot-js/quick_rect.js)('$name')" \
    "$(cat screenshot-js/quick.js)('$card', '$title', $round)" >/dev/null
  cp $O/quick/$name.png $R/
done
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
step popup; python3 cdp_tap.py $B/coffee_machine $R/item-popup.png "Energie heute"
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
fi
step done; ls $R | wc -l
