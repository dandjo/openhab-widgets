#!/usr/bin/env python3
"""Derive the gross aWATTar prices from the net channels via a multiplying JS profile.

The bridge only sends time series on market-net and total-net; market-gross and total-gross stay empty.
Usage: awattar_gross.py check|apply   (run as root with openHAB stopped for apply)
"""
import sys

src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)

BRIDGE = "awattar:bridge:epex_spot_awattar"
TRANSFORM = "config:js:multiply"
PROFILE = {"profile": "transform:JS", "toItemScript": f"{TRANSFORM}?factor=1.2"}
RELINK = {
    # item: (dead channel, net channel)
    "epex_spot_awattar_market_gross": ("market-gross", "market-net"),
    "epex_spot_awattar_total_gross": ("total-gross", "total-net"),
}
FUNCTION = """(function(data) {
  // factor arrives as URL parameter: config:js:multiply?factor=1.2; a unit after the number is kept
  if (typeof factor === 'undefined') {
    console.warn('multiply called without factor, passing ' + data + ' through');
    return data;
  }
  const v = parseFloat(data);
  if (!isFinite(v)) {
    return null;
  }
  const unit = String(data).trim().split(' ').slice(1).join(' ');
  return String(v * parseFloat(factor)) + (unit ? ' ' + unit : '');
})(input)"""


def migrate_links(d):
    for item, (dead, net) in RELINK.items():
        old = f"{item} -> {BRIDGE}:{dead}"
        assert old in d, old
        d.pop(old)
        uid = f"{BRIDGE}:{net}"
        d = m.insert(d, f"{item} -> {uid}", {
            "class": "org.openhab.core.thing.link.ItemChannelLink",
            "value": {"channelUID": {"segments": uid.split(":"), "uid": uid},
                      "configuration": {"properties": dict(PROFILE)}, "itemName": item},
        })
    return d


def migrate_transforms(d):
    assert TRANSFORM not in d
    return m.insert(d, TRANSFORM, {
        "class": "org.openhab.core.transform.ManagedTransformationProvider$PersistedTransformation",
        "value": {"uid": TRANSFORM, "label": "Multiply", "type": "js", "configuration": {"function": FUNCTION}},
    })


FILES = {
    "org.openhab.core.thing.link.ItemChannelLink.json": migrate_links,
    "org.openhab.core.transform.Transformation.json": migrate_transforms,
}


def main():
    results = {}
    for name, fn in FILES.items():
        data, enc = m.detect(m.DB + name)
        results[name] = m.encode(fn(data), *enc)
        print(f"{name}: encoder html={enc[0]} newline={enc[1]} ok")
    if sys.argv[1] != "apply":
        return
    for name, text in results.items():
        with open(m.DB + name, "w", encoding="utf-8") as f:
            f.write(text)
    print("written")


main()
