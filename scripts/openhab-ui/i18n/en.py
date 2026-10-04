"""English texts for the widget repository: the generator builds German for homepi; this pass turns its widgets (and,
for the screenshots, its pages) into English. Plain texts are looked up whole, the quoted texts in expressions by
their core (spaces and separators at their ends kept), item labels through the English originals the installation had
before its German labels (labels_export.json beside this file, the current labels from the item JSONDB), and the
German number and time formats become English ones.
Usage as a module: translate(tree) returns the English copy and the texts it left German.
python3 en.py ITEMS.json FILE.json ...   lists what is left German in JSONDB files of widgets or pages."""
import copy
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from en_texts import DAY_LETTERS, EN, LISTS  # noqa: E402

# what a text may carry around its core, kept as it is
EDGE = " ·:,;()/+–-|%•"
# keys whose strings are no texts: CSS, SVG geometry, icons, ids, item and component names
TECHNICAL = {"stylesheet", "d", "transform", "viewBox", "icon", "f7", "material", "item", "component", "uid",
             "class", "fill", "stroke", "color", "background", "href", "action", "actionModal", "actionPage",
             "actionItem", "actionCommand", "actionCommandAlt", "actionPageTransition", "points", "type", "seriesId",
             "id", "key", "variable", "value", "iconColor", "font-family", "period", "service", "aggregationFunction",
             "chartType", "gradient", "attributeName", "begin", "dur", "repeatCount", "keyTimes", "calcMode",
             "keySplines", "from", "to", "by", "context", "src", "url", "image", "groupName"}
# a widget's props: their names and types are ids, their labels and descriptions texts
PARAM_IDS = {"name", "type", "context", "groupName", "limitToOptions", "required", "multiple"}
LITERAL = re.compile(r"'((?:[^'\\]|\\.)*)'")
ITEM_LABELS = {}


def load_item_labels(items_json):
    """German label → English original, for every item whose label changed since labels_export.json."""
    try:
        exp = json.load(open(os.path.join(HERE, "labels_export.json")))["items"]
        items = json.load(open(items_json))
    except (OSError, ValueError, KeyError):
        return
    for name, e in items.items():
        de = e.get("value", {}).get("label")
        if de and name in exp and exp[name].get("label") and exp[name]["label"] != de:
            ITEM_LABELS[de] = exp[name]["label"]


def split(text):
    i, j = 0, len(text)
    while i < j and text[i] in EDGE:
        i += 1
    while j > i and text[j - 1] in EDGE:
        j -= 1
    return text[:i], text[i:j], text[j:]


RICH = re.compile(r"\{(s\d+)\|([^{}]*)\}")  # a chart title's coloured names, {s0|Name} · {s1|Name}


def tr_core(core):
    if core in EN or core in ITEM_LABELS:
        return EN.get(core) or ITEM_LABELS[core]
    if RICH.search(core):  # each coloured name of a title on its own
        return RICH.sub(lambda m: "{" + m.group(1) + "|" + tr_plain(m.group(2)) + "}", core)
    return core


def tr_plain(text):
    lead, core, trail = split(text)
    return lead + tr_core(core) + trail if core else text


def tr_expr(expr):
    """An expression: whole lists, then its quoted texts by their cores; German number and time formats English."""
    for de, en in LISTS.items():
        expr = expr.replace(de, en)
    expr = expr.replace(".replace('.', ',')", "").replace("toLocaleString('de-AT'", "toLocaleString('en-GB'")
    expr = expr.replace(" + ' Uhr'", "").replace("' Uhr'", "''")
    return LITERAL.sub(lambda m: m.group(0) if "\\" in m.group(1) else "'" + tr_plain(m.group(1)) + "'", expr)


def tr(v, key=None):
    if isinstance(v, dict) and key == "parameters":
        return v
    if isinstance(v, list) and key == "parameters":
        return [{k: (x if k in PARAM_IDS else tr(x, k)) for k, x in p.items()} if isinstance(p, dict) else p for p in v]
    if isinstance(v, dict):
        if key == "style":  # CSS, but an ECharts graphic's style holds its text
            return {k: (tr(x, "text") if k == "text" else x) for k, x in v.items()}
        return {k: (x if k in TECHNICAL and isinstance(x, str) and not x.startswith("=") else tr(x, k))
                for k, x in v.items()}
    if isinstance(v, list):
        out = [tr(x, key) for x in v]
        texts = [x.get("style", {}).get("text") if isinstance(x, dict) and isinstance(x.get("style"), dict) else None
                 for x in out]
        if texts == DAY_LETTERS[0]:
            for x, letter in zip(out, DAY_LETTERS[1]):
                x["style"]["text"] = letter
        return out
    if isinstance(v, str):
        if v.startswith("="):
            return tr_expr(v)
        if v.startswith(("image://", "http://", "https://", "material:", "f7:", "oh:", "iconify:", "widget:")):
            return v
        return tr_plain(v)
    return v


def translate(tree):
    """The English copy of a component tree (a widget's or a page's value)."""
    return tr(copy.deepcopy(tree))


def leftovers(tree, words):
    """The texts in an (English) tree that hold words neither English nor known names."""
    found = set()
    allow = set("""espaltherma esplyfterl faikout perfera pyaltherma miele wwg twc wp netatmo tado huawei pv dhw cop buh
    bsh sg co kwh kw hz rrggbb uid viewbox css svg ac oh mainui echarts dayjs eur ct utc openhab url rgba nous shelly em
    altherma daikin api iso hh mm dd yyyy ui rx llll meteoblue geosphere arome zamg orf wien warnungen wetter mo tu we th
    fr sa su eco wm cq cqw srgb mix minmax fr px auto nowrap pre""".split())

    def walk(v, key=None):
        if isinstance(v, list) and key == "parameters":
            for p in v:
                if isinstance(p, dict):
                    walk({k: x for k, x in p.items() if k not in PARAM_IDS})
            return
        if isinstance(v, dict):
            for k, x in v.items():
                if k in TECHNICAL or k in ("style",):
                    if k == "style" and isinstance(x, dict) and isinstance(x.get("text"), str):
                        check(x["text"])
                    continue
                walk(x, k)
        elif isinstance(v, list):
            for x in v:
                walk(x, key)
        elif isinstance(v, str):
            if v.startswith("="):
                for m in LITERAL.finditer(v):
                    check(m.group(1))
            elif not v.startswith(("image://", "http", "material:", "f7:", "oh:", "widget:")):
                check(v)

    def check(text):
        _, core, _ = split(text)
        toks = re.findall(r"[A-Za-zÄÖÜäöüß]+", core)
        if re.search(r"[äöüÄÖÜß]", core) or any(len(t) >= 3 and t.lower() not in words and t.lower() not in allow
                                                and not re.match(r"^[a-z]+[A-Z]", t) for t in toks):
            if not re.search(r"(rgba?\(|var\(|calc\(|repeat\(|color-mix|px\b|#[0-9a-fA-F]{3,6}|</?\w+>)", core):
                found.add(core)
    walk(tree)
    return found


if __name__ == "__main__":
    load_item_labels(sys.argv[1])
    words = set()
    for f in ("/usr/share/dict/american-english", "/usr/share/dict/british-english"):
        if os.path.exists(f):
            words |= {w.strip().lower() for w in open(f)}
    left = set()
    for path in sys.argv[2:]:
        for e in json.load(open(path)).values():
            left |= leftovers(translate(e["value"]), words)
    print("\n".join(sorted(left)))
    print(len(left), "texts left German or unknown", file=sys.stderr)
