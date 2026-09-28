#!/usr/bin/env python3
"""Export the generated widgets from a copy of uicomponents_ui_widget.json as YAML, one <uid>.yml per widget, in the
format of MainUI's widget editor; the internal tag "generated" is left out.
Usage: export_widgets.py WIDGETS_JSON OUTDIR"""
import json, os, sys
import yaml


class Dumper(yaml.SafeDumper):
    pass


Dumper.add_representer(str, lambda d, s: d.represent_scalar("tag:yaml.org,2002:str", s))
src, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
for uid, entry in sorted(json.load(open(src)).items()):
    v = entry["value"]
    if "generated" not in v.get("tags", []):
        continue
    doc = {"uid": v["uid"], "tags": [t for t in v["tags"] if t != "generated"], "props": v["props"],
           "timestamp": v["timestamp"], "component": v["component"], "config": v["config"], "slots": v["slots"]}
    text = yaml.dump(doc, Dumper=Dumper, sort_keys=False, allow_unicode=True, width=120, default_flow_style=False)
    assert yaml.safe_load(text) == doc, uid
    open(os.path.join(out, uid + ".yml"), "w").write(text)
    print(uid)
