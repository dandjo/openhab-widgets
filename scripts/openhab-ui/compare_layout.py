import json, os, sys
A, B = sys.argv[1], sys.argv[2]
diffs = {}
for f in sorted(os.listdir(A)):
    a = json.load(open(os.path.join(A, f))); b = json.load(open(os.path.join(B, f)))
    msgs = []
    if abs(a.get("sh", 0) - b.get("sh", 0)) > 2: msgs.append(f"scrollHeight {a.get('sh')} -> {b.get('sh')}")
    ca, cb = a.get("cards", []), b.get("cards", [])
    if len(ca) != len(cb): msgs.append(f"cards {len(ca)} -> {len(cb)}")
    for i, (x, y) in enumerate(zip(ca, cb)):
        if x["h"] != y["h"]: msgs.append(f"card {i} title {x['h']!r} -> {y['h']!r}")
        if any(abs(p - q) > 2 for p, q in zip(x["r"], y["r"])): msgs.append(f"card {i} {x['h']!r} rect {x['r']} -> {y['r']}")
        kd = sum(1 for p, q in zip(x["kids"], y["kids"]) if any(abs(u - v) > 2 for u, v in zip(p, q)))
        if kd or len(x["kids"]) != len(y["kids"]): msgs.append(f"card {i} {x['h']!r}: {kd} inner boxes moved, kids {len(x['kids'])}->{len(y['kids'])}")
    if [s[0] for s in a.get("svgs", [])] != [s[0] for s in b.get("svgs", [])]: msgs.append("svg set differs")
    for s1, s2 in zip(a.get("svgs", []), b.get("svgs", [])):
        if any(abs(p - q) > 2 for p, q in zip(s1[1:], s2[1:])): msgs.append(f"svg {s1[0]} {s1[1:]} -> {s2[1:]}")
    if len(a.get("canv", [])) != len(b.get("canv", [])): msgs.append(f"charts {len(a.get('canv', []))} -> {len(b.get('canv', []))}")
    for c1, c2 in zip(a.get("canv", []), b.get("canv", [])):
        if any(abs(p - q) > 2 for p, q in zip(c1, c2)): msgs.append(f"chart {c1} -> {c2}")
    if msgs: diffs[f] = msgs
print(len(os.listdir(A)), "page/width combinations,", len(diffs), "with differences")
for f, msgs in diffs.items():
    print("==", f); [print("   ", m) for m in msgs[:10]]
