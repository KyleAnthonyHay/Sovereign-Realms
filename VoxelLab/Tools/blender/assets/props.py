"""props: the village's bridge, lantern posts, plaza banner and clutter (barrel, crates, sacks, planter, signpost,
stone steps).

    Blender -b --factory-startup --python Tools/blender/assets/props.py -- [--no-render] [--no-export] [--only=a,b]

Most of these are small things seen close up, so they are built on the 6.25 cm grid (one texel per voxel): stones get
real joints, lanterns get thin cages, barrels get hoops. Big walkable timber (the bridge deck) is on the 12.5 cm grid.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import voxlib as V
import voxkit as K
from voxlib import Vox

T = V.TEXEL                    # 6.25 cm: the fine grid
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
NO_RENDER = "--no-render" in ARGS
NO_EXPORT = "--no-export" in ARGS
ONLY = None
for _a in ARGS:
    if _a.startswith("--only="):
        ONLY = set(_a.split("=", 1)[1].split(","))

STONE = ["#ffffff", "#f3eee4", "#e6e1d8", "#dad5cc", "#f1e8d8", "#d0cbc3", "#f8f2e6"]      # stone to stone
CORE = "#aaa398"                                                                           # what shows in the joints
WOOD = ["#ffffff", "#f0dcc0", "#e2c8a6", "#f6e8d2", "#d8bc98"]                             # board to board


# ---------------------------------------------------------------------------------------------------- helpers

def _cuts(a0, a1, r, lo, hi, avoid=()):
    """Split a0..a1 into pieces lo..hi long with a one-voxel joint between them, away from the joints in `avoid`."""
    out = [(a0, a1)]
    for _ in range(16):
        out, a = [], a0
        while True:
            rem = a1 - a
            if rem <= hi:
                out.append((a, a1))
                break
            w = int(r.integers(lo, hi + 1))
            if rem - w - 1 < lo:
                w = max(2, rem - 1 - lo)
            out.append((a, a + w))
            a += w + 1
        if not ({b for (_, b) in out[:-1]} & set(avoid)):
            break
    return out


def masonry(v, x0, y0, z0, x1, y1, z1, course=8, seed=0, proud=0.2, lo=3, hi=7, top_groove=True, tints=STONE,
            mat="stone", core=CORE, flush_top=False):
    """A block of dry stone on the fine grid: courses of separate stones with recessed joints one voxel wide, each
    stone its own shade, a share of them standing one voxel proud. Leave a voxel of room around it in the grid."""
    r = np.random.default_rng(seed)
    v.box(x0 + 1, y0 + 1, z0, x1 - 1, y1 - 1, z1 - (1 if top_groove else 0), mat, core)
    px, py = (), ()
    z = z0
    while z < z1:
        zt = min(z + course, z1)
        if z1 - zt < 3:
            zt = z1
        top = zt >= z1
        xs = _cuts(x0, x1, r, lo, hi, px)
        ys = _cuts(y0, y1, r, lo, hi, py)
        px = [s + d for (_, s) in xs[:-1] for d in (-1, 0, 1)]
        py = [s + d for (_, s) in ys[:-1] for d in (-1, 0, 1)]
        for (xa, xb) in xs:
            for (ya, yb) in ys:
                edge = xa == x0 or xb == x1 or ya == y0 or yb == y1
                if not edge and not top:
                    continue
                c = tints[int(r.integers(len(tints)))]
                p = edge and r.random() < proud
                v.box(xa - (1 if p and xa == x0 else 0), ya - (1 if p and ya == y0 else 0), z,
                      xb + (1 if p and xb == x1 else 0), yb + (1 if p and yb == y1 else 0),
                      zt if top else zt - 1, mat, c)
        z = zt
    return v


def moss(v, thresh=0.6, scale=5.0, seed=0, region=None, mats=("stone",), dirs=("+z",), mat="moss", color=None):
    """Patches of moss (not speckle) on the open faces of these materials."""
    m = v.mask(*mats)
    surf = np.zeros_like(m)
    for d in dirs:
        surf |= v.exposed(d)
    m &= surf & (V.noise3(v.n, scale, seed + 3) > thresh)
    if region:
        x0, y0, z0, x1, y1, z1 = v._clip(*region)
        keep = np.zeros_like(m)
        keep[x0:x1, y0:y1, z0:z1] = True
        m &= keep
    return v.where(m, mat, color)


def lantern(v, cx, cy, z, body=6, h=6, frame="beam", roof="beam", hang=False):
    """The village lantern on the fine grid: a wooden base plate, a glowing box in a cage of corner posts, an
    overhanging lid, a little stepped roof and a knob. (cx, cy) is the centre (a voxel corner), z its underside.
    Returns the z of its top (h + 5 above z). hang=True adds a drop under the base instead of nothing."""
    b = body // 2
    v.box(cx - b - 1, cy - b - 1, z, cx + b + 1, cy + b + 1, z + 1, frame)
    v.box(cx - b, cy - b, z + 1, cx + b, cy + b, z + 1 + h, "glow", "lantern")
    for dx in (cx - b, cx + b - 1):
        for dy in (cy - b, cy + b - 1):
            v.box(dx, dy, z + 1, dx + 1, dy + 1, z + 1 + h, frame)
    zl = z + 1 + h
    v.box(cx - b - 1, cy - b - 1, zl, cx + b + 1, cy + b + 1, zl + 1, frame)
    v.box(cx - b, cy - b, zl + 1, cx + b, cy + b, zl + 2, roof, "#e8d0b0")
    v.box(cx - b + 1, cy - b + 1, zl + 2, cx + b - 1, cy + b - 1, zl + 3, roof)
    v.box(cx - 1, cy - 1, zl + 3, cx + 1, cy + 1, zl + 4, frame)
    if hang:
        v.box(cx - 1, cy - 1, z - 1, cx + 1, cy + 1, z, frame)
    return zl + 4


def flower(v, x, y, z, color, h=3, big=False):
    """A little flower on the fine grid: a green stem and a coloured head."""
    v.box(x, y, z, x + 1, y + 1, z + h, "leaves", "leaf_dark")
    if big:
        v.box(x - 1, y, z + h, x + 2, y + 1, z + h + 1, "paint", color)
        v.box(x, y - 1, z + h, x + 1, y + 2, z + h + 1, "paint", color)
        v.box(x, y, z + h, x + 1, y + 1, z + h + 2, "paint", "flower_yellow" if color != "flower_yellow" else "flower_orange")
    else:
        v.box(x, y, z + h, x + 1, y + 1, z + h + 1, "paint", color)


def tuft(v, x, y, z, r, color="leaf"):
    """A tuft of grass: a few blades of different heights."""
    for (dx, dy) in ((0, 0), (1, 0), (0, 1), (-1, 1), (1, -1)):
        if r.random() < 0.7:
            hh = int(r.integers(1, 5))
            v.box(x + dx, y + dy, z, x + dx + 1, y + dy + 1, z + hh, "leaves", color if r.random() < 0.6 else "leaf_dark")


# ---------------------------------------------------------------------------------------------------- lantern posts

def pier_grid(height_t, name="pier", seed=1, below=0, proud=0.22):
    """A lantern pier on the fine grid: a 62.5 cm shaft of stone blocks `height_t` tall above z = 0 (and `below` voxels
    under it), a 75 cm cap slab and a lantern. Origin: centre of the shaft at z = 0."""
    v = Vox(16, 16, below + height_t + 16, T, origin=(8, 8, below), name=name, seed=seed)
    masonry(v, 4, 4, 0, 12, 12, below + height_t - 2, course=7, seed=seed, proud=proud * 0.6, top_groove=False)
    zc = below + height_t - 2
    v.box(3, 3, zc, 13, 13, zc + 2, "stone", "#f3eee4")                 # cap slab
    lantern(v, 8, 8, zc + 2, body=6, h=7)
    return v


def build_lantern_post():
    v = pier_grid(18, "lantern_post", seed=4)
    moss(v, 0.60, 4.0, seed=2, dirs=("+z",), region=(0, 0, 14, 16, 16, 16))
    moss(v, 0.55, 4.0, seed=5, dirs=("-x", "+x", "-y", "+y"), region=(0, 0, 0, 16, 16, 4))
    return V.join([v], "SM_LanternPost")



def build_lantern_post_tall():
    """A timber post with the lantern hanging from an arm that points to -Y (the front)."""
    v = Vox(16, 30, 46, T, origin=(8, 22, 0), name="lantern_tall", seed=3)
    masonry(v, 3, 17, 0, 13, 27, 5, course=5, seed=8, proud=0.3, lo=4, hi=5)        # stone footing
    v.box(6, 20, 0, 10, 24, 42, "post")
    v.box(5, 19, 5, 11, 25, 7, "beam")                                               # collar on the footing
    v.box(7, 9, 38, 9, 26, 40, "beam")                                               # the arm, tenoned through the post
    v.box(6, 9, 38, 10, 10, 40, "beam", "#e8d0b0")                                   # its end block
    for k in range(6):                                                               # brace under the arm
        v.box(7, 19 - k, 31 + k, 9, 20 - k, 33 + k, "beam")
    v.box(5, 19, 36, 11, 25, 37, "metal")                                            # iron strap under the arm
    v.box(5, 19, 42, 11, 25, 43, "beam")                                             # cap
    v.box(6, 20, 43, 10, 24, 44, "beam", "#e8d0b0")
    v.box(7, 12, 37, 9, 14, 38, "metal")                                             # hook
    lantern(v, 8, 13, 26, hang=True)                                                 # top of its knob at 37
    moss(v, 0.58, 4.0, seed=2, dirs=("+z", "-y", "+x"), region=(0, 14, 0, 16, 30, 5))
    return V.join([v], "SM_LanternPost_Tall")


# ---------------------------------------------------------------------------------------------------- bridge

def deck_top(yi):
    """Height (voxels) of the deck at voxel row yi (0 .. 55) along the bridge: a GENTLE arch, as in the reference: it
    rises three voxels (37.5 cm) from the banks to a long level middle, one voxel at a time."""
    d = min(yi, 55 - yi)                      # distance from the nearer end
    for lim, h in ((6, 0), (12, 1), (19, 2)):
        if d < lim:
            return h
    return 3


def build_bridge():
    """Footbridge along Y, 7 m long: the deck meets the banks at y = +/-3.5 m, z = 0 and arches gently to 0.375 m."""
    OX, OY, OZ = 16, 28, 20
    v = Vox(32, 56, 40, 0.125, origin=(OX, OY, OZ), name="bridge", seed=7)

    def b(x0, y0, z0, x1, y1, z1, mat, col=None):
        v.box(x0 + OX, y0 + OY, z0 + OZ, x1 + OX, y1 + OY, z1 + OZ, mat, col)

    r = np.random.default_rng(11)
    tops = [deck_top(i) for i in range(56)]
    half = [10 if (i < 5 or i > 50) else 11 for i in range(56)]         # the deck is narrower between the piers

    # stone: abutments under the two ends, the feet of the piers and of the trestle legs (all under water or in shade)
    for yi in list(range(0, 4)) + list(range(52, 56)):
        b(-10, yi - 28, -20, 10, yi - 27, tops[yi] - 2, "stone")
    for sx in (-1, 1):
        for sy in (-1, 1):
            b(min(sx * 10, sx * 15), min(sy * 23, sy * 28), -20, max(sx * 10, sx * 15), max(sy * 23, sy * 28), -10, "stone")
            b(min(sx * 5, sx * 10), min(sy * 7, sy * 12), -20, max(sx * 5, sx * 10), max(sy * 7, sy * 12), -15, "stone")
    v.chunky("stone", p=0.3, seed=3)
    v.scatter("stone", "mossy_stone", p=0.25, seed=5, region=(0, 0, 8, 32, 56, 20))

    # timber under the deck: three stringers following the arch
    for yi in range(56):
        Y, h = yi - 28, tops[yi]
        if 4 <= yi < 52:
            for (xa, xb) in ((-10, -8), (-1, 1), (8, 10)):
                b(xa, Y, h - 5, xb, Y + 1, h - 2, "beam")
    # two trestles standing in the river
    for sy in (-1, 1):
        y0, y1 = (8, 11) if sy > 0 else (-11, -8)
        for (xa, xb) in ((-9, -6), (6, 9)):
            b(xa, y0, -20, xb, y1, -2, "post")
        b(-11, y0, -2, 11, y1, 0, "beam")                                # cap beam under the stringers
        b(-12, y0, -2, -11, y1, 0, "beam", "#e8d0b0")
        b(11, y0, -2, 12, y1, 0, "beam", "#e8d0b0")
        b(-9, y0 + 1, -7, 9, y0 + 2, -5, "beam")                         # tie just above the water
        for k in range(4):                                               # knee braces across
            b(-6 + k, y0 + 1, -6 + k, -5 + k, y0 + 2, -4 + k, "beam")
            b(5 - k, y0 + 1, -6 + k, 6 - k, y0 + 2, -4 + k, "beam")
        for (xa, xb) in ((-9, -7), (7, 9)):                              # knee braces along the bridge, both ways
            for k in range(5):
                yy = (y0 - 1 - k) if sy > 0 else (y1 + k)
                b(xa, yy, -5 + k, xb, yy + 1, -3 + k, "beam")
            for k in range(4):
                yy = (y1 + k) if sy > 0 else (y0 - 1 - k)
                b(xa, yy, -5 + k, xb, yy + 1, -3 + k, "beam")

    # the deck: boards across, two voxels thick, no gaps
    yi = 0
    while yi < 56:
        n = 1
        while yi + n < 56 and tops[yi + n] == tops[yi] and n < 3:
            n += 1
        cut = sorted(int(c) for c in r.choice(np.arange(-7, 8), size=2, replace=False))
        if cut[1] - cut[0] < 4:
            cut = cut[:1]
        edges = [-11] + cut + [11]
        cols = [WOOD[int(r.integers(len(WOOD)))] for _ in edges[1:]]
        for j in range(yi, yi + n):
            for (xa, xb, c) in zip(edges[:-1], edges[1:], cols):
                b(max(xa, -half[j]), j - 28, tops[j] - 2, min(xb, half[j]), j - 27, tops[j], "plank", c)
        yi += n

    # railings: posts, a handrail on top and a rail half way up, following the arch
    for sx in (-1, 1):
        xo0, xo1 = (9, 11) if sx > 0 else (-11, -9)
        xi0, xi1 = (9, 10) if sx > 0 else (-10, -9)
        for yi in range(5, 51):
            h = tops[yi]
            hn = tops[yi + 1] if yi < 28 else tops[yi - 1]
            lo, hi = min(h, hn), max(h, hn)
            b(xo0, yi - 28, lo + 6, xo1, yi - 27, hi + 7, "beam")
            b(xi0, yi - 28, lo + 3, xi1, yi - 27, hi + 4, "plank", "#e2c8a6")
        for yc in (-22, -15, -8, 0, 8, 15, 22):
            ya = yc - 1
            hs = (tops[ya + 28], tops[ya + 29])
            b(xo0, ya, min(hs), xo1, ya + 2, max(hs) + 8, "post")
            b(xo0, ya, max(hs) + 8, xo1, ya + 2, max(hs) + 9, "beam", "#e8d0b0")

    parts = [v]
    seed = 20
    for sx in (-1, 1):
        for sy in (-1, 1):
            seed += 1
            p = pier_grid(16, "pier", seed=seed, below=20, proud=0.18)
            moss(p, 0.60, 4.0, seed=seed, dirs=("+z",), region=(0, 0, 32, 16, 16, 38))
            moss(p, 0.57, 4.0, seed=seed + 9, dirs=("-x", "+x", "-y", "+y"), region=(0, 0, 0, 16, 16, 10))
            parts.append(p.at(sx * 12.5 * 0.125, sy * 25.5 * 0.125, 0.0))
    return V.join(parts, "SM_Bridge")


def bridge_context():
    """Not exported: river banks, a path and water, so the preview shows the bridge where it belongs."""
    c = Vox(44, 60, 11, 0.25, origin=(22, 30, 10), name="ctx", seed=2)
    for (ya, yb) in ((0, 16), (44, 60)):
        c.box(0, ya, 0, 44, yb, 9, "dirt")
        c.box(0, ya, 9, 44, yb, 10, "grass")
        c.box(17, ya, 9, 27, yb, 10, "cobble")
    c.box(0, 16, 0, 44, 44, 2, "gravel")
    c.box(0, 16, 2, 44, 44, 6, "water")
    return V.join([c], "ctx")


# ---------------------------------------------------------------------------------------------------- plaza banner

TREE = [
    "....GGGGG....",
    "..GGGGGGGGG..",
    ".GGGGGGGGGGG.",
    ".GGGGGGGGGGG.",
    "GGGGGGGGGGGGG",
    "GGGGGGGGGGGGG",
    "GGG.GGGGG.GGG",
    ".GG.GGGGG.GG.",
    "..G..GGG..G..",
    ".....GGG.....",
    ".....GGG.....",
    ".....GGG.....",
    "....GGGGG....",
    "..GGGGGGGGG..",
]


def cloth(v, x0, y, ztop, w=17, h=28, notch=6, pattern=TREE, row0=4):
    """The banner cloth drawn into v: one voxel thick at layer y, hanging down from ztop, x0 its left edge."""
    inside = np.zeros((h, w), bool)
    for j in range(h):
        for i in range(w):
            k = j - (h - notch)
            cut = k >= 0 and abs(i - (w - 1) / 2.0) < (k + 1) * (w / 2.0 - 2) / notch
            inside[j, i] = not cut
    pw = max(len(p) for p in pattern)
    px0 = (w - pw) // 2
    for j in range(h):
        for i in range(w):
            if not inside[j, i]:
                continue
            border = i == 0 or i == w - 1 or j == 0 or j == h - 1 or not inside[min(j + 1, h - 1), i] \
                or not inside[j, max(i - 1, 0)] or not inside[j, min(i + 1, w - 1)]
            col = "gold" if border else "banner"
            pj, pi = j - row0, i - px0
            if not border and 0 <= pj < len(pattern) and 0 <= pi < len(pattern[pj]) and pattern[pj][pi] == "G":
                col = "gold_light" if (pj < 3 and pi < 6) else "gold"
            elif not border and (i * 7 + j * 3) % 13 == 0:
                col = "banner_dark"
            v.box(x0 + i, y, ztop - 1 - j, x0 + i + 1, y + 1, ztop - j, "paint", col)
    v.hang(region=(x0, y, ztop - h, x0 + w, y + 1, ztop))


def build_plaza_banner():
    """Stepped stone pedestal, pole with a crossbar, the big green banner with the gold tree. Faces -Y."""
    v = Vox(41, 41, 58, T, origin=(20.5, 20.5, 0), name="plaza_banner", seed=6)
    r = np.random.default_rng(5)
    masonry(v, 8, 8, 0, 33, 33, 7, course=7, seed=3, proud=0.3, lo=5, hi=9)          # 1.56 m square
    masonry(v, 14, 14, 7, 27, 27, 15, course=8, seed=9, proud=0.2, lo=5, hi=7)       # 0.81 m square
    for (x0, y0, x1, y1, z1, c) in ((5, 11, 8, 16, 3, 1), (33, 24, 36, 29, 4, 3), (20, 33, 26, 36, 3, 2),
                                    (27, 5, 31, 8, 2, 4), (11, 5, 15, 8, 3, 5)):       # loose stones at the foot
        v.box(x0, y0, 0, x1, y1, z1, "stone", STONE[c])
    for (x0, y0, x1, y1) in ((8, 8, 13, 12), (28, 28, 33, 33), (8, 27, 12, 33)):        # corner stones standing tall
        v.box(x0, y0, 7, x1, y1, 9, "stone", STONE[2])
    moss(v, 0.63, 5.0, seed=4, dirs=("+z",), region=(0, 0, 0, 41, 41, 10))
    moss(v, 0.68, 5.0, seed=7, dirs=("+z",), region=(0, 0, 10, 41, 41, 16))
    moss(v, 0.62, 5.0, seed=8, dirs=("-x", "+x", "-y", "+y"), region=(0, 0, 0, 41, 41, 4))
    # grass and flowers at its foot
    colors = ["flower_white", "flower_yellow", "flower_pink", "flower_orange", "#b58be0"]
    for k in range(34):
        a = r.uniform(0, 2 * np.pi)
        d = r.uniform(13.5, 18.5)
        x, y = int(20.5 + np.cos(a) * d * 1.05), int(20.5 + np.sin(a) * d * 1.05)
        if 8 <= x < 33 and 8 <= y < 33:
            continue
        if not (1 <= x < 39 and 1 <= y < 39) or v.get(x, y, 0):
            continue
        if k % 3 == 0:
            flower(v, x, y, 0, colors[k % len(colors)], h=int(r.integers(2, 5)), big=(k % 6 == 0))
        else:
            tuft(v, x, y, 0, r)
    # pole, crossbar, banner
    v.box(18, 18, 15, 23, 23, 17, "beam")
    v.box(19, 19, 15, 22, 22, 55, "post")
    v.box(18, 18, 55, 23, 23, 56, "beam", "#e8d0b0")
    v.box(18, 18, 48, 23, 23, 49, "metal")                                             # iron band under the crossbar
    v.box(9, 17, 50, 32, 19, 52, "beam")                                               # crossbar, in front of the pole
    v.box(8, 17, 50, 10, 19, 52, "gold")
    v.box(31, 17, 50, 33, 19, 52, "gold")
    cloth(v, 12, 17, 50)
    for x in (12, 20, 27):                                                             # gold loops over the bar
        v.box(x, 16, 49, x + 2, 20, 53, "gold")
    return V.join([v], "SM_PlazaBanner")


# ---------------------------------------------------------------------------------------------------- clutter

BARREL_R = [5.0, 5.4, 5.7, 5.9, 6.0, 6.0, 6.0, 6.0, 6.0, 6.0, 5.9, 5.7, 5.4, 5.4]


def barrel(v, cx, cy, z0, seed=0, pal=WOOD):
    """A barrel drawn into a fine grid: 75 cm across, 87.5 cm tall, staves of different shades, two iron hoops, a
    sunk lid. (cx, cy) is its centre (a voxel corner)."""
    X, Y, Z = v.grid()
    d2 = (X + 0.5 - cx) ** 2 + (Y + 0.5 - cy) ** 2
    ang = np.arctan2(Y + 0.5 - cy, X + 0.5 - cx)
    stave = np.floor((ang + np.pi) / (2 * np.pi) * 14 + 0.5).astype(int) % 14
    r = np.random.default_rng(seed + 40)
    cols = np.array([V.rgb(c) for c in pal])[r.integers(0, len(pal), 14)][stave]
    for k, rad in enumerate(BARREL_R):
        layer = (Z == z0 + k) & (d2 <= rad * rad)
        v.m[layer] = V.IDS["plank"]
        v.c[layer] = cols[layer]
        if k in (2, 11):
            v.where((Z == z0 + k) & (d2 <= (rad + 0.75) ** 2) & (d2 > (rad - 1.3) ** 2), "metal", "#c8c8d0")
    top = z0 + len(BARREL_R) - 1
    v.where((Z == top) & (d2 <= 12.5), None)
    v.where((Z == top - 1) & (d2 <= 12.5), "plank", "#e2c8a6")
    return v


def crate(v, x0, y0, z0, s=10, seed=0, pal=WOOD, frame=None, flip=False):
    """A crate drawn into a fine grid: a frame of dark battens two voxels wide, sunk board panels, a diagonal brace
    on each side, iron corners."""
    x1, y1, z1 = x0 + s, y0 + s, z0 + s
    v.box(x0, y0, z0, x1, y1, z1, None)
    v.box(x0 + 1, y0 + 1, z0, x1 - 1, y1 - 1, z1 - 1, "plank")
    gx, gy = np.meshgrid(np.arange(x0 + 1, x1 - 1), np.arange(y0 + 1, y1 - 1), indexing="ij")
    k = ((gx - x0) // 2 * 3 + (gy - y0) // 2 * 5 + seed) % len(pal)
    v.c[x0 + 1:x1 - 1, y0 + 1:y1 - 1, z0:z1 - 1] = np.array([V.rgb(c) for c in pal])[k][:, :, None, :]
    v.frame(x0, y0, z0, x1, y1, z1, "beam", frame, t=2)
    for i in range(2, s - 2):
        for dz in (0, 1):
            zi = z0 + ((s - 1 - i) if flip else i) + dz
            if not (z0 + 2 <= zi < z1 - 2):
                continue
            v.set(x0 + i, y0, zi, "beam", frame)
            v.set(x1 - 1 - i, y1 - 1, zi, "beam", frame)
            v.set(x0, y1 - 1 - i, zi, "beam", frame)
            v.set(x1 - 1, y0 + i, zi, "beam", frame)
    for xx in (x0, x1 - 1):
        for yy in (y0, y1 - 1):
            for zz in (z0, z1 - 1):
                v.set(xx, yy, zz, "metal")
    return v


SACK = ["#c8a467", "#b99257", "#d6b67c", "#ad854c"]
ROPE = "#6a4220"


def blob(v, cx, cy, cz, rx, ry, rz, mat, color, n=2.6, zmin=None):
    """A plump rounded box (a pillow): between an ellipsoid (n = 2) and a box (large n)."""
    X, Y, Z = v.grid()
    m = (np.abs((X + 0.5 - cx) / rx) ** n + np.abs((Y + 0.5 - cy) / ry) ** n + np.abs((Z + 0.5 - cz) / rz) ** n) <= 1.0
    if zmin is not None:
        m &= Z >= zmin
    return v.where(m, mat, color)


def sack(v, cx, cy, z0, rx=4.5, ry=4.0, color=SACK[0], open_top=False):
    """A standing grain sack 70 cm tall: a plump body, a rope round the neck and the gathered top (or an open mouth
    full of grain). (cx, cy) is a voxel corner."""
    blob(v, cx, cy, z0 + 4.0, rx, ry, 5.2, "wool", color, zmin=z0)
    zt = z0 + 9
    ix, iy = int(cx), int(cy)
    if open_top:
        v.box(ix - 3, iy - 3, zt - 1, ix + 3, iy + 3, zt + 1, "wool", color)                # rolled-down mouth
        v.box(ix - 2, iy - 2, zt - 1, ix + 2, iy + 2, zt + 1, "wheat", "#ffe9a0")
        v.box(ix - 1, iy - 1, zt + 1, ix + 1, iy + 1, zt + 2, "wheat", "#ffe9a0")
    else:
        v.box(ix - 2, iy - 2, zt - 1, ix + 2, iy + 2, zt, "wool", color)
        v.box(ix - 2, iy - 2, zt, ix + 2, iy + 2, zt + 1, "paint", ROPE)
        v.box(ix - 3, iy - 2, zt + 1, ix + 3, iy + 2, zt + 2, "wool", color)
        v.box(ix - 2, iy - 1, zt + 2, ix + 2, iy + 1, zt + 3, "wool", color)
    return v


def sack_lying(v, cx, cy, z0, axis="x", color=SACK[1], length=6.5, fat=4.2, end=1):
    """A sack on its side, 37 cm high: its tied neck sticks out of one end (end = +1 / -1 along the axis)."""
    rx, ry = (length, fat) if axis == "x" else (fat, length)
    cz = z0 + 2.6
    blob(v, cx, cy, cz, rx, ry, 3.4, "wool", color, zmin=z0)
    ix, iy, iz = int(cx), int(cy), int(round(cz))
    a = (ix if axis == "x" else iy) + (int(length) if end > 0 else -int(length) - 1)
    for k, (w, hh, mat, c) in enumerate(((1, 1, "paint", ROPE), (2, 1, "wool", color))):
        p = a + end * k
        if axis == "x":
            v.box(p, iy - w, iz - hh, p + 1, iy + w, iz + hh, mat, c)
        else:
            v.box(ix - w, p, iz - hh, ix + w, p + 1, iz + hh, mat, c)
    return v


def build_barrel():
    v = Vox(14, 14, 15, T, origin=(7, 7, 0), name="barrel", seed=1)
    barrel(v, 7, 7, 0, seed=1)
    return V.join([v], "SM_Barrel")


def build_crate():
    v = Vox(10, 10, 10, T, origin=(5, 5, 0), name="crate", seed=2)
    crate(v, 0, 0, 0, 10, seed=1)
    return V.join([v], "SM_Crate")


def build_crate_stack():
    """Four crates and a barrel, 1.7 m wide: two big crates side by side, one across the top of them, a small one
    and the barrel in front."""
    v = Vox(32, 28, 24, T, origin=(15, 14, 0), name="crate_stack", seed=4)
    dark = ["#e6cfae", "#d6ba94", "#c8aa84", "#eedcbc"]
    crate(v, 2, 14, 0, 12, seed=1)
    crate(v, 15, 14, 0, 12, seed=2, pal=dark, flip=True)
    crate(v, 9, 15, 12, 10, seed=3, flip=True)
    crate(v, 3, 4, 0, 8, seed=4, pal=dark)
    barrel(v, 22, 7, 0, seed=3)
    return V.join([v], "SM_CrateStack")


def build_sacks():
    """A pile of grain sacks, about 1.5 m x 1.3 m and 0.7 m high: three lying, two standing in front (one open)."""
    v = Vox(28, 24, 16, T, origin=(14, 12, 0), name="sacks", seed=5)
    sack_lying(v, 9, 16, 0, "x", SACK[1], end=-1)
    sack_lying(v, 20, 15, 0, "y", SACK[3], end=1)
    sack_lying(v, 14, 16, 5, "x", SACK[2], length=6.0, fat=4.0, end=1)
    sack(v, 7, 6, 0, 4.5, 4.0, SACK[0])
    sack(v, 17, 5, 0, 4.6, 4.2, SACK[2], open_top=True)
    v.box(5, 2, 3, 8, 3, 6, "paint", "#a07a48")                                      # a patch on the front
    return V.join([v], "SM_Sacks")


def build_flower_planter():
    """A wooden trough of earth with flowers, 1.5 m long. Front faces -Y."""
    v = Vox(24, 12, 16, T, origin=(12, 6, 0), name="planter", seed=6)
    r = np.random.default_rng(8)
    v.box(1, 2, 1, 23, 10, 6, "plank")
    for i in range(1, 23):                                                            # boards along it, three high
        pass
    for (z0, z1, c) in ((1, 3, WOOD[1]), (3, 5, WOOD[0]), (5, 6, WOOD[2])):
        v.box(1, 2, z0, 23, 10, z1, "plank", c)
    v.box(2, 3, 2, 22, 9, 6, None)
    v.box(2, 3, 2, 22, 9, 5, "dirt")
    v.frame(1, 2, 5, 23, 10, 6, "beam", t=1)                                          # rim
    for (x0, x1) in ((0, 2), (22, 24), (11, 13)):                                     # posts at the ends, a strap mid way
        for (y0, y1) in ((1, 3), (9, 11)):
            if x0 == 11:
                v.box(x0, y0 + (1 if y0 == 1 else 0), 1, x1, y1 - (1 if y0 == 9 else 0), 6, "beam")
            else:
                v.box(x0, y0, 0, x1, y1, 7, "beam")
    v.box(1, 2, 0, 3, 10, 1, "beam")
    v.box(21, 2, 0, 23, 10, 1, "beam")
    colors = ["flower_pink", "flower_white", "flower_yellow", "#b58be0", "flower_orange", "flower_pink", "#b58be0",
              "flower_white", "flower_yellow"]
    for x in range(2, 22):                                                            # a bed of leaves
        for y in range(3, 9):
            if r.random() < 0.75:
                hh = int(r.integers(1, 4))
                v.box(x, y, 5, x + 1, y + 1, 5 + hh, "leaves", "leaf" if r.random() < 0.6 else "leaf_dark")
    for k, x in enumerate((3, 5, 8, 10, 12, 14, 16, 18, 20)):
        y = 4 + int(r.integers(0, 4))
        hh = 3 + int(r.integers(0, 4))
        v.box(x, y, 5, x + 1, y + 1, 5 + hh, "leaves", "leaf_dark")
        v.box(x - 1, y, 5 + hh, x + 2, y + 1, 6 + hh, "paint", colors[k])
        v.box(x, y - 1, 5 + hh, x + 1, y + 2, 6 + hh, "paint", colors[k])
        v.box(x, y, 5 + hh, x + 1, y + 1, 7 + hh, "paint", "flower_yellow" if colors[k] != "flower_yellow" else "flower_orange")
    for x in (4, 5, 9, 15, 16, 19):                                                   # leaves trailing over the front
        v.box(x, 1, 6 - int(r.integers(1, 4)), x + 1, 2, 6, "leaves", "leaf")
        v.box(x, 2, 6, x + 1, 3, 7, "leaves", "leaf")
    for x in (7, 13, 18):
        v.box(x, 10, 6 - int(r.integers(1, 3)), x + 1, 11, 6, "leaves", "leaf_dark")
        v.box(x, 9, 6, x + 1, 10, 7, "leaves", "leaf_dark")
    return V.join([v], "SM_FlowerPlanter")


def build_signpost():
    """A post with two pointing boards on its front (-Y): the upper one points to +X, the lower one to -X."""
    v = Vox(32, 14, 36, T, origin=(16, 8, 0), name="signpost", seed=7)
    masonry(v, 12, 4, 0, 20, 12, 3, course=3, seed=6, proud=0.5, lo=3, hi=4)           # stones round its foot
    v.box(10, 9, 0, 13, 13, 2, "stone", STONE[3])
    v.box(19, 3, 0, 22, 6, 2, "stone", STONE[1])
    v.box(14, 6, 0, 18, 10, 32, "post")
    v.box(13, 5, 32, 19, 11, 33, "beam")
    v.box(14, 6, 33, 18, 10, 34, "beam", "#e8d0b0")

    def board(x0, x1, z0, tip, c):
        """A board 5 voxels high on the post's front; tip = +1 points to +X, -1 to -X."""
        v.box(x0, 4, z0, x1, 6, z0 + 5, "plank", c)
        a = x1 if tip > 0 else x0 - 1                                                  # the point
        v.box(a, 4, z0 + 1, a + 1, 6, z0 + 4, "plank", c)
        v.box(a + tip, 4, z0 + 2, a + tip + 1, 6, z0 + 3, "plank", c)
        t = x0 if tip > 0 else x1 - 1                                                  # the notched tail
        v.box(t, 4, z0 + 2, t + 1, 6, z0 + 3, None)
        v.box(x0, 4, z0 + 4, x1, 5, z0 + 5, "beam")                                    # a darker top edge
        v.box(x0, 4, z0, x1, 5, z0 + 1, "beam")
        x = (x0 + 2) if tip > 0 else (x0 + 1)                                          # painted "writing"
        for w in (3, 2, 4, 2, 3):
            if x + w > ((x1 - 1) if tip > 0 else (x1 - 2)):
                break
            v.box(x, 4, z0 + 2, x + w, 5, z0 + 3, "paint", "wood_dark")
            x += w + 1

    board(9, 27, 24, +1, WOOD[0])
    board(5, 22, 16, -1, WOOD[1])
    moss(v, 0.6, 3.0, seed=2, dirs=("+z",), region=(0, 0, 0, 32, 14, 4))
    return V.join([v], "SM_Signpost")


def build_stone_steps():
    """Four stone steps, 2 m wide, climbing 1 m towards +Y over 2 m (each 50 cm deep, 25 cm high). Origin: the centre
    of the bottom front edge. The treads are flush (joints show as darker lines); risers and sides have real joints."""
    v = Vox(32, 32, 16, T, origin=(16, 0, 0), name="steps", seed=8)
    r = np.random.default_rng(21)
    prev = ()
    for i in range(4):
        z0 = 4 * i
        v.box(0, 8 * i, z0, 32, 32, z0 + 4, "stone", CORE)
        for j in range(i, 4):
            xs = _cuts(0, 32, r, 6, 11, prev)
            prev = [s + d for (_, s) in xs[:-1] for d in (-1, 0, 1)]
            for (xa, xb) in xs:
                v.box(xa, 8 * j, z0, xb, 8 * j + 8, z0 + 4, "stone", STONE[int(r.integers(len(STONE)))])
            if j == i:                                                                 # joints in the riser
                for (_, xb) in xs[:-1]:
                    v.box(xb, 8 * j, z0, xb + 1, 8 * j + 1, z0 + 4, None)
            jy = 8 * j + (7 if i % 2 == 0 else 3)                                      # joints in the two sides
            for x in (0, 31):
                v.box(x, jy, z0, x + 1, jy + 1, z0 + 4, None)
        if i < 3:
            for x in (0, 31):
                v.box(x, 8 * (i + 1), z0 + 3, x + 1, 32, z0 + 4, None)
    moss(v, 0.70, 4.0, seed=3, dirs=("+z",))
    return V.join([v], "SM_StoneSteps")


# ---------------------------------------------------------------------------------------------------- run

ASSETS = [
    # name, builder, collision, (preview target, distance)
    ("SM_Bridge", build_bridge, "complex", ((0, 0, 0.2), 30.0)),
    ("SM_LanternPost", build_lantern_post, "complex", ((0, 0, 0.9), 9.0)),
    ("SM_LanternPost_Tall", build_lantern_post_tall, "complex", ((0, -0.3, 1.4), 12.0)),
    ("SM_PlazaBanner", build_plaza_banner, "complex", ((0, 0, 1.75), 14.0)),
    ("SM_Barrel", build_barrel, "complex", ((0, 0, 0.45), 6.0)),
    ("SM_Crate", build_crate, "complex", ((0, 0, 0.3), 5.0)),
    ("SM_CrateStack", build_crate_stack, "complex", ((0, 0, 0.6), 9.0)),
    ("SM_Sacks", build_sacks, "complex", ((0, 0, 0.4), 8.0)),
    ("SM_FlowerPlanter", build_flower_planter, "complex", ((0, 0, 0.3), 7.0)),
    ("SM_Signpost", build_signpost, "complex", ((0, 0, 1.1), 10.0)),
    ("SM_StoneSteps", build_stone_steps, "complex", ((0, 1.0, 0.5), 11.0)),
]


def render(path, **kw):
    """V.render, but it survives a busy GPU (other renders running): waits and retries, then falls back to the CPU."""
    import time
    import bpy
    for attempt in range(4):
        try:
            return V.render(path, **kw)
        except RuntimeError as e:
            print("render failed (%s); retrying" % str(e).splitlines()[0][:80])
            time.sleep(20)
            if attempt == 2:
                bpy.app.handlers.render_pre.append(lambda scene, *a: setattr(scene.cycles, "device", "CPU"))
    raise RuntimeError("could not render " + path)


def wanted(name):
    return not ONLY or name in ONLY or name.replace("SM_", "") in ONLY


def main():
    report = []
    for name, fn, collision, (target, dist) in ASSETS:
        if not wanted(name):
            continue
        V.reset_scene()
        ob = fn()
        co = np.array([p.co[:] for p in ob.data.vertices])
        size = co.max(axis=0) - co.min(axis=0)
        report.append("%-22s %6d faces  %.2f x %.2f x %.2f m  z %.2f..%.2f" % (
            name, ob["voxel_faces"], size[0], size[1], size[2], co[:, 2].min(), co[:, 2].max()))
        if not NO_EXPORT:
            V.export_gltf(ob, collision=collision)
        if NO_RENDER:
            continue
        short = name.replace("SM_", "")
        path = os.path.join(V.PREVIEWS, "props_%s%s.png")
        if name == "SM_Bridge":
            bridge_context()
            render(path % (short, ""), target=target, az=-42, el=30, dist=dist, ground=False)
            render(path % (short, "_back"), target=target, az=150, el=24, dist=dist, ground=False)
            render(path % (short, "_side"), target=(0, 0, -0.3), az=90, el=8, dist=dist, ground=False)
            render(path % (short, "_top"), target=target, az=0, el=80, dist=dist, ground=False)
        else:
            render(path % (short, ""), target=target, az=28, el=30, dist=dist)
            render(path % (short, "_back"), target=target, az=205, el=22, dist=dist)
    if wanted("Clutter") and not NO_RENDER:                      # everything small in one picture
        V.reset_scene()
        x = -5.4
        for name, fn, _c, _p in ASSETS:
            if name in ("SM_Bridge", "SM_PlazaBanner"):
                continue
            ob = fn()
            co = np.array([p.co[:] for p in ob.data.vertices])
            x += -co[:, 0].min() + 0.35
            ob.location = (x, 0, 0)
            x += co[:, 0].max()
        render(os.path.join(V.PREVIEWS, "props_Clutter.png"), target=(0, 0.5, 0.8), az=20, el=26, dist=30)
    print("\n".join(report))


main()
