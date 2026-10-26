#!/usr/bin/env python3
"""The trip map (user, 2026-10-26): static/trip-map.html next to the scripts goes into openHAB's html folder, which
openHAB serves under /static/, with Leaflet 1.9.4 beside it in leaflet-1.9.4/, fetched from unpkg and checked
against its SHA-256 (the same from unpkg and jsDelivr on 2026-10-26). openHAB serves /static/ with a year's cache:
the folder carries Leaflet's version, and the widget addresses the page with its checksum, so a change reaches every
browser. The page takes a trip's places in its address and stores
nothing; the widget trip-popup shows it in a frame. Only the map tiles come from openstreetmap.org.
Usage: trip_map.py check|apply   (on homepi, as pi with sudo)"""
import hashlib
import os
import subprocess
import sys
import tempfile
import urllib.request

HTML = "/etc/openhab/html"
HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "..", "static", "trip-map.html")
LEAFLET = "https://unpkg.com/leaflet@1.9.4/dist/"
LEAFLET_DIR = "leaflet-1.9.4"
FILES = {"leaflet.js": "db49d009c841f5ca34a888c96511ae936fd9f5533e90d8b2c4d57596f4e5641a",
         "leaflet.css": "a7837102824184820dfa198d1ebcd109ff6d0ff9a2672a074b9a1b4d147d04c6"}


def sha(path):
    try:
        return hashlib.sha256(open(path, "rb").read()).hexdigest()
    except OSError:
        return None


def install(source, target):
    subprocess.run(["sudo", "install", "-o", "openhab", "-g", "openhab", "-m", "644", source, target], check=True)


def main():
    apply = sys.argv[1] == "apply"
    page = os.path.join(HTML, "trip-map.html")
    same = sha(page) == sha(PAGE)
    print("trip-map.html:", "up to date" if same else "differs" if os.path.exists(page) else "missing")
    if apply and not same:
        install(PAGE, page)
        print("  installed")
    if apply:
        subprocess.run(["sudo", "install", "-d", "-o", "openhab", "-g", "openhab", "-m", "755",
                        os.path.join(HTML, LEAFLET_DIR)], check=True)
    for name, digest in FILES.items():
        target = os.path.join(HTML, LEAFLET_DIR, name)
        ok = sha(target) == digest
        print(f"{LEAFLET_DIR}/{name}:", "ok" if ok else "missing or changed")
        if apply and not ok:
            data = urllib.request.urlopen(LEAFLET + name, timeout=60).read()
            if hashlib.sha256(data).hexdigest() != digest:
                sys.exit(f"{LEAFLET_DIR}/{name}: the download does not match its SHA-256, not installed")
            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(data)
            try:
                install(f.name, target)
            finally:
                os.unlink(f.name)
            print("  installed")


main()
