import math
exec(open("flow_layout5.py").read().split("W_, H_ = 520, 540")[0])
BOXES.update({"hp": (-48, -30, 48, 72), "ac": (-48, -30, 48, 72), "ecar": (-48, -30, 48, 72),
              "batt": (-56, -30, 56, 87), "grid": (-66, -30, 66, 87), "pv": (-30, -30, 42 + 97, 30)})
ANG = {"pv": -90, "hp": -36, "ac": 18, "ecar": 72, "batt": 126, "grid": 180}
LABELS = {  # the house's power and today's energy, relative to the house centre
    "upper-left": (-128, -52, -38, -13), "upper-left-high": (-128, -72, -38, -33),
    "left-of-pv-spoke": (-98, -92, -8, -53), "right": (38, -26, 128, 13)}
MIN_GAP = 12
found = []
for W_ in range(430, 501, 5):
    for H_ in range(420, 501, 5):
        rings = (15, 15, 161, 141)
        best = None
        for lname, (l0, t0, r0, b0) in LABELS.items():
            for hx in range(W_ // 2 - 30, W_ // 2 + 31, 3):
                for hy in range(H_ // 2 - 60, H_ // 2 + 21, 3):
                    home = (hx, hy)
                    fixed = [(hx - 30, hy - 30, hx + 30, hy + 30), (hx + l0, hy + t0, hx + r0, hy + b0), rings]
                    for R in range(150, 206, 2):
                        pos = {n: (hx + R * math.cos(math.radians(ANG[n])), hy + R * math.sin(math.radians(ANG[n]))) for n in ORDER}
                        rects = {n: rect(n, pos[n]) for n in ORDER}
                        if any(r[0] < 4 or r[1] < 4 or r[2] > W_ - 4 or r[3] > H_ - 4 for r in rects.values()):
                            continue
                        allr = list(rects.values()) + fixed
                        worst = min(gap(allr[i], allr[j]) for i in range(len(allr)) for j in range(i + 1, len(allr))
                                    if not (i >= 6 and j >= 6))
                        if worst < MIN_GAP:
                            continue
                        if any(seg_hits(home, pos[n], q) for n in ORDER for m, q in rects.items() if m != n) or \
                           any(seg_hits(home, pos[n], f) for n in ORDER for f in fixed[1:]):
                            continue
                        if best is None or worst > best[0]:
                            best = (round(worst, 1), lname, home, R)
                        break
        if best:
            found.append((W_ * H_, W_, H_, best))
found.sort()
for f in found[:8]:
    print(f[1], f[2], f[3])
