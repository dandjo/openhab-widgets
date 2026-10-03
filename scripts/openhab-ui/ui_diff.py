#!/usr/bin/env python3
"""Compare the UI components of two JSONDB directories uid by uid and write what changed as a REST body for ui_put.py.

Usage: ui_diff.py LIVE_DIR NEW_DIR [BODY]

LIVE_DIR holds the live uicomponents_ui_page.json and uicomponents_ui_widget.json (or a copy), NEW_DIR the same files
after a generator run against a copy of them. Differences openHAB's REST writes cause by themselves are ignored: the
timestamp, the `editable` flag, the order of the tags and ints stored as floats (26.0). BODY gets
{"ui:page": {uid: component}, "ui:widget": {...}}, with null for a uid that is gone.
"""
import json
import sys


def load(d, kind):
    with open(f"{d}/uicomponents_ui_{kind}.json", encoding="utf-8") as f:
        return {k: v["value"] for k, v in json.load(f).items()}


def canon(x):
    if isinstance(x, dict):
        return {k: canon(v) for k, v in x.items() if k not in ("timestamp", "editable")}
    if isinstance(x, list):
        return [canon(v) for v in x]
    if isinstance(x, float) and x.is_integer():
        return int(x)
    return x


def same(a, b):
    a, b = canon(a), canon(b)
    for c in (a, b):
        if isinstance(c.get("tags"), list):
            c["tags"] = sorted(c["tags"])
    return a == b


def main():
    live_dir, new_dir = sys.argv[1], sys.argv[2]
    body = {}
    for kind in ("page", "widget"):
        live, new = load(live_dir, kind), load(new_dir, kind)
        changes = {}
        for uid in sorted(set(live) | set(new)):
            if uid not in new:
                changes[uid] = None
                print(f"ui:{kind} {uid}: removed")
            elif uid not in live or not same(live[uid], new[uid]):
                changes[uid] = new[uid]
                print(f"ui:{kind} {uid}: {'added' if uid not in live else 'changed'}")
        if changes:
            body[f"ui:{kind}"] = changes
    if not body:
        print("no changes")
    if len(sys.argv) > 3:
        with open(sys.argv[3], "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
