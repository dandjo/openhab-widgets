"""Compare the SVG geometry captured by capture_all.sh: every drawn element's box, texts by their vertical centre."""
import json, os, sys
A, B = sys.argv[1], sys.argv[2]
pattern = sys.argv[3] if len(sys.argv) > 3 else ""
bad = 0
for f in sorted(os.listdir(B)):
    if pattern not in f or not os.path.exists(os.path.join(A, f)):
        continue
    a, b = json.load(open(os.path.join(A, f))), json.load(open(os.path.join(B, f)))
    msgs = []
    if len(a) != len(b):
        msgs.append(f"{len(a)} -> {len(b)} elements")
    for i, (x, y) in enumerate(zip(a, b)):
        if x[:2] != y[:2] or any(abs(p - q) > 1 for p, q in zip(x[2:], y[2:])):
            msgs.append(f"#{i} {x} -> {y}")
    if msgs:
        bad += 1
        print("==", f, len(a), "elements"); [print("   ", m) for m in msgs[:8]]
print(len([f for f in os.listdir(B) if pattern in f]), "files,", bad, "with differences")
