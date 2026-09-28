import json, sys
js = json.loads(open(sys.argv[1]).read())
py = json.load(open(sys.argv[2]))
assert len(js) == len(py), (len(js), len(py))
names = ["space", "dhw", "standby", "total", "h_before", "h_after", "h_space", "h_dhw", "h_total"]
diffs = [0] * len(names); worst = [0.0] * len(names)
for a, b in zip(js, py):
    for k in range(len(names)):
        d = abs(a[k] - round(b[k], 2))
        if d > 0.0051:
            diffs[k] += 1
        worst[k] = max(worst[k], d)
print("evaluations", len(js), {n: (diffs[k], round(worst[k], 3)) for k, n in enumerate(names)})
