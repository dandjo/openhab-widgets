"""Find node positions for the energy flow star from the bounding boxes of icon and texts.

Boxes are relative to each node centre, in viewBox units, from the text widths at the page font
(13 px ≈ 7.2, 18 px bold ≈ 10.5, 12 px ≈ 6.6 units per character)."""
import math, random
W, H = 440, 440
HOME = (220, 205)
BOXES = {  # left, top, right, bottom relative to the node centre
    "pv": (-30, -30, 42 + 15 * 6.6 + 4, 34),          # label right: Photovoltaics / 0.00 kW / 19.30 kWh today
    "hp": (-37, -30, 37, 78),                          # label below: Heatpump / 0.02 kW
    "ac": (-58, -30, 58, 78),                          # Air Conditioning
    "ecar": (-58, -30, 58, 78),                        # E-Car · charging
    "batt": (-69, -30, 69, 78),                        # Energy Storage 78 %
    "grid": (-42, -30, 42, 78),                        # Power Meter / -0.36 kW
}
ORDER = ["pv", "hp", "ac", "ecar", "batt", "grid"]
FIXED = [(HOME[0] - 30, HOME[1] - 30, HOME[0] + 30, HOME[1] + 30),        # house
         (HOME[0] - 112, HOME[1] - 60, HOME[0] - 38, HOME[1] - 17),       # its label
         (18, 18, 178, 140)]                                              # the two rings


def rect(node, pos):
    l, t, r, b = BOXES[node]
    return (pos[0] + l, pos[1] + t, pos[0] + r, pos[1] + b)


def gap(a, b):
    dx = max(b[0] - a[2], a[0] - b[2], 0)
    dy = max(b[1] - a[3], a[1] - b[3], 0)
    if dx == 0 and dy == 0:  # overlap: negative depth
        return -min(a[2] - b[0], b[2] - a[0], a[3] - b[1], b[3] - a[1])
    return math.hypot(dx, dy)


def seg_hits(p, q, r, pad=4):
    """Does the segment p-q pass through rectangle r (shrunk by pad)?"""
    x0, y0, x1, y1 = r[0] + pad, r[1] + pad, r[2] - pad, r[3] - pad
    for i in range(41):
        t = i / 40
        x, y = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
        if x0 < x < x1 and y0 < y < y1:
            return True
    return False


def score(params):
    pos = {}
    for n, (ang, rad) in zip(ORDER, params):
        a = math.radians(ang)
        pos[n] = (HOME[0] + rad * math.cos(a), HOME[1] + rad * math.sin(a))
    rects = {n: rect(n, pos[n]) for n in ORDER}
    worst = 1e9
    allr = list(rects.values()) + FIXED
    for i in range(len(allr)):
        for j in range(i + 1, len(allr)):
            if i >= len(ORDER) and j >= len(ORDER):
                continue
            worst = min(worst, gap(allr[i], allr[j]))
    pen = 0
    for n, r in rects.items():
        pen += max(0, 4 - r[0]) + max(0, 4 - r[1]) + max(0, r[2] - (W - 4)) + max(0, r[3] - (H - 4))
        # a spoke must not cross another node's box or the labels
        for m, s in rects.items():
            if m != n and seg_hits(HOME, pos[n], s):
                pen += 50
        for f in FIXED[1:]:
            if seg_hits(HOME, pos[n], f):
                pen += 50
    radii = [p[1] for p in params]
    return worst - 10 * pen - 0.05 * (max(radii) - min(radii)), pos, worst


random.seed(7)
best = [(-90 + 54 * k, 160) for k in range(6)]
bs, bp, bw = score(best)
for it in range(60000):
    cand = [(a + random.gauss(0, 3), min(190, max(130, r + random.gauss(0, 3)))) for a, r in best]
    if not all(cand[i][0] < cand[i + 1][0] for i in range(5)):
        continue
    s, p, w = score(cand)
    if s > bs:
        best, bs, bp, bw = cand, s, p, w
print("min gap between boxes", round(bw, 1), "score", round(bs, 1))
for n, (a, r) in zip(ORDER, best):
    print(f"{n:5} angle {a:7.1f} radius {r:6.1f} pos ({bp[n][0]:.0f}, {bp[n][1]:.0f})")
