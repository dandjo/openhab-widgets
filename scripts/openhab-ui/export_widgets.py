#!/usr/bin/env python3
"""Export the generated widgets from a copy of uicomponents_ui_widget.json as YAML, one <uid>.yml per widget, in the
format of MainUI's widget editor; the internal tag "generated" is left out. With the item JSONDB given, in English
(i18n/en.py; the repository is published in English while homepi's widgets stay German).
Usage: export_widgets.py WIDGETS_JSON OUTDIR [ITEMS_JSON]"""
import json, os, sys
import yaml


class Dumper(yaml.SafeDumper):
    pass


Dumper.add_representer(str, lambda d, s: d.represent_scalar("tag:yaml.org,2002:str", s))
src, out = sys.argv[1], sys.argv[2]
english = len(sys.argv) > 3
if english:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "i18n"))
    import en
    en.load_item_labels(sys.argv[3])
os.makedirs(out, exist_ok=True)
for uid, entry in sorted(json.load(open(src)).items()):
    v = entry["value"]
    if english:
        v = en.translate(v)
    if "generated" not in v.get("tags", []):
        continue
    doc = {"uid": v["uid"], "tags": [t for t in v["tags"] if t != "generated"], "props": v["props"],
           "timestamp": v["timestamp"], "component": v["component"], "config": v["config"], "slots": v["slots"]}
    text = yaml.dump(doc, Dumper=Dumper, sort_keys=False, allow_unicode=True, width=120, default_flow_style=False)
    assert yaml.safe_load(text) == doc, uid
    open(os.path.join(out, uid + ".yml"), "w").write(text)
    print(uid)
