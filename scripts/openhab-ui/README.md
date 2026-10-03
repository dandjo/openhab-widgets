# openHAB UI generator

`dashboard.py` generates homepi's MainUI: the `overview` page with the energy flow's two popups (`flow_home`,
`flow_appliances`), the 24 device pages in the sidebar, which the overview opens as popups everywhere else, and the
widgets these pages are built from. It writes them into
`uicomponents_ui_page.json` and `uicomponents_ui_widget.json` in `/var/lib/openhab/jsondb`. Every page it
generates is replaced on each run, and so is every widget tagged `generated`; widgets made in the UI stay.
Changes made in the UI to a generated page or widget are overwritten by the next run, so this script is the
source of the UI.

The widgets are the overview's nine cards (`weather-card`, `energy-flow-card`, `appliances-card`, `heatpump-card`,
`electricity-price-card`, `consumption-card`, `energy-days-card`, `pv-days-card`, `temperatures-card`) and the parts they are built from, wherever a part stands in more than one place or makes sense
on its own:

- the quick popups: `heatpump-quick`, `air-conditioner-quick` and `ventilation-quick`, which the energy flow opens,
  and the heat pump card's `heatpump-control-quick`, `heatpump-indoor-quick`, `heatpump-outdoor-quick`,
  `heatpump-refrigerant-quick`, `heatpump-circuit-quick`, `upper-floor-quick`, `ground-floor-quick`,
  `heatpump-electric-quick`, `heatpump-heat-quick` and `heatpump-cop-quick`, which its tiles open;
- the controls: `state-bar`, every segmented bar; `pill-switch`, `power-pill` and `boost-pill`, the switches as pills; `pill-slider`, the slider of every setpoint, offset, power and timer;
  `switch-row`, every row with a switch outside the overview's tiles; and `switch-tile`, the switch cards under the
  energy flow;
- the energy flow: `flow-link`, `flow-node` and `flow-share-ring`, its lines, nodes and rings; the heat pump card's
  outdoor unit is a `flow-node` too;
- the appliances: `appliance-tile` and `appliance-icon`, which the Miele machines' pages show too;
- the weather: `weather-icon`, the weather drawn from a WMO code, in the weather bar and in the weather page's days;
- four parametrised plug cards used by every metered device page (`plug-card`, `plug-power-card`,
  `plug-energy-days-card`, `plug-electric-card`), `item-popup`, the popup every tile of the device pages opens, and
  `value-tile`, the tile itself: title and value over a large pale icon.

A widget that places another takes the other's items from its own props: `role_widget()` builds a quick panel with
its items and turns them into role props (`item_prop()`), `ITEM_PARAMS` names the props of a widget that take an
item, and `items_in()` and `itemized()` follow them into the widgets a card places and into the `actionModalConfig`
of a link that opens a widget as a popup. The plug cards are built by the
same card builders from placeholders; `templated()` turns each placeholder into an expression on the widget's props,
so a widget renders exactly like the card built for one device. All widgets are also published, as YAML, in the
GitHub repository `dandjo/openhab-widgets`.

## Running it

A dry run encodes both files and checks them, without writing:

    sudo python3 dashboard.py update

It also names the value tiles for which no rule of `TILE_ICONS` found an icon; they carry the neutral default.

To apply, with openHAB stopped:

    sudo systemctl stop openhab
    sudo python3 dashboard.py update-apply
    sudo chown openhab:openhab /var/lib/openhab/jsondb/uicomponents_ui_page.json /var/lib/openhab/jsondb/uicomponents_ui_widget.json
    sudo systemctl start openhab

`awattar_migrate.py` holds the JSONDB helpers the script uses: byte-exact re-encoding of openHAB's files and
insertion in their sorted order.

## The rest of this directory

- `i18n/`: German labels and Material icons for items, things, channels, rules, transformations and the
  `default` sitemap. `german_apply.py check|apply` applies them (openHAB stopped); `de_labels.py` and `icons_de.py`
  hold the data, `coverage.py` checks the exports in the same directory for untranslated labels.
- `applied/`: one-off JSONDB and InfluxDB changes that have been applied, kept as a record of what was done.
  They read `awattar_migrate.py` from `/tmp`, where they were run.
- Tools for a workstation with headless Chrome and an SSH tunnel to port 8080; they do not run on homepi:
  - `preview.py` renders an SVG component tree offline with item states from the REST API.
  - `cdp_shot.py`, `cdp_click.py`, `cdp_popup.py`, `cdp_eval.py`, `cdp_evalw.py`, `cdp_console.py` and
    `cdp_hover.py` take screenshots, click, and evaluate JavaScript in MainUI through the Chrome DevTools
    protocol.
  - `check_dev.py` and `diff_strings.py` build every page from two versions of the generator and list what
    differs.
  - `capture_layout.sh` records the position and size of every card, drawing and chart of every page at desktop
    and phone width; `compare_layout.py` compares two such recordings. `capture_all.sh` records the same and the
    box of every drawn SVG element besides, `compare_geo.py` compares those boxes.
  - `flow_layout.py`, `flow_layout5.py` and `flow_layout17.py` search the energy flow's star layout from the
    bounding boxes of its nodes and texts.
  - `export_widgets.py` writes the generated widgets from a copy of `uicomponents_ui_widget.json` as YAML, and
    `make_readme.py` builds the README of the GitHub repository from them, with its props tables;
    `cdp_cards.py` takes the screenshots of every card of a page, light or dark, at any width (`cdp_cards_js.py`
    after running a script in the page first), `cdp_elems.py` of any elements a script finds, and `cdp_tap.py`
    taps the tile whose text contains a text and saves the popup it opens. `cdp_gif.py` records a card as an animated GIF,
    stepping its SVG animations frame by frame; `demo_flow.js` gives the energy flow demo values in that browser
    only, by stopping MainUI's state tracking, `demo_heatpump.js` the heat pump card (a space heating run). `widget_gallery.py OUTDIR` writes the page `widget_gallery` with
    the energy flow's and the appliances' widgets on demo values and the controls' small widgets, for the
    screenshots, as the body to POST to `/rest/ui/components/ui:page`; delete it afterwards, the generator's next run
    removes it too. `shoot_all.sh` takes every screenshot of the GitHub repository with
    these tools and the element scripts in `screenshot-js/`, the energy flow, the heat pump card, the consumption
    card and the weather page's warnings on demo values (`demo_flow.js`, `demo_heatpump.js`, `demo_consumption.js`,
    `demo_weather.js`), and the quick popups
    each as tall as its content (`screenshot-js/quick.js`), while the gallery is up.
