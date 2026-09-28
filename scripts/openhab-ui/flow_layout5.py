"""The energy flow star with the water meter: six nodes on a 45° grid, the top-left slot for the two rings and the
bottom-right slot for the water meter, both off the star. Boxes from the German texts (13 px ≈ 7.2, 18 px bold ≈ 10.5,
12 px ≈ 6.6 units per character); angle offsets from the grid only where boxes crowd."""
import itertools, math
exec(open("flow_layout.py").read().split("def score")[0].split("W, H = ")[0])
exec("def gap" + open("flow_layout.py").read().split("def gap")[1].split("def score")[0])
BOXES = {
    "pv": (-30, -30, 42 + 15 * 6.6 + 4, 34),   # right: Photovoltaik / 0,000 kW / 23,66 kWh heute
    "hp": (-47, -30, 47, 94),                   # below: Wärmepumpe / 0,016 kW / 4,85 kWh heute
    "ac": (-47, -30, 47, 94),                   # Klimaanlage
    "ecar": (-48, -30, 48, 94),                 # E-Auto · lädt
    "batt": (-77, -30, 77, 111),                # Batteriespeicher 15 % / … / Entladen 7,37 kWh
    "grid": (-67, -30, 67, 111),                # Stromzähler / … / Einspeisung 4,28 kWh
}
ORDER = ["pv", "hp", "ac", "ecar", "batt", "grid"]
BASE = {"pv": -90, "hp": -45, "ac": 0, "ecar": 90, "batt": 135, "grid": 180}


def rect(node, pos):
    l, t, r, b = BOXES[node]
    return (pos[0] + l, pos[1] + t, pos[0] + r, pos[1] + b)


W_, H_ = 520, 540
water = (W_ - 18 - 44 - 32 - 100, H_ - 18 - 44 - 8, W_ - 18, H_ - 18)   # ring at the corner, texts left of it
rings = (18, 18, 178, 140)
results = []
for hx in range(245, 276, 5):
    for hy in range(230, 271, 5):
        home = (hx, hy)
        fixed = [(hx - 30, hy - 30, hx + 30, hy + 30), (hx - 112, hy - 68, hx - 38, hy - 13), rings, water]
        for R in range(176, 232, 4):
            for dhp, dac, decar, dbatt, dgrid in itertools.product((0, 3, 6, 9, 12), (-6, -3, 0, 3, 6), (-6, -3, 0, 3, 6),
                                                                   (-6, -3, 0, 3, 6), (-3, 0, 3)):
                ang = dict(BASE, hp=-45 + dhp, ac=dac, ecar=90 + decar, batt=135 + dbatt, grid=180 + dgrid)
                pos = {n: (hx + R * math.cos(math.radians(ang[n])), hy + R * math.sin(math.radians(ang[n]))) for n in ORDER}
                rects = {n: rect(n, pos[n]) for n in ORDER}
                if any(r[0] < 4 or r[1] < 4 or r[2] > W_ - 4 or r[3] > H_ - 4 for r in rects.values()):
                    continue
                allr = list(rects.values()) + fixed
                worst = min(gap(allr[i], allr[j]) for i in range(len(allr)) for j in range(i + 1, len(allr))
                            if not (i >= 6 and j >= 6))
                if worst < 18:
                    continue
                if any(seg_hits(home, pos[n], s) for n in ORDER for m, s in rects.items() if m != n) or \
                   any(seg_hits(home, pos[n], f) for n in ORDER for f in fixed[1:]):
                    continue
                dev = abs(dhp) + abs(dac) + abs(decar) + abs(dbatt) + abs(dgrid)
                results.append((dev, -round(worst, 1), hx, hy, R, (dhp, dac, decar, dbatt, dgrid)))
results.sort()
print(len(results), "layouts with every box 18 apart")
for r in results[:8]:
    print("deviation", r[0], "worst gap", -r[1], "home", (r[2], r[3]), "R", r[4], "offsets hp/ac/ecar/batt/grid", r[5])
