"""archery_hall: the archer hall of the voxel village, remade after References/Remake/archery.png.

  SM_ArcheryHall   a long open-fronted timber shooting hall (raised middle roof between two lower wings) at the back,
                   three targets, a bow rack, arrow barrels, crates and lanterns inside, and in front a dirt yard
                   inside a timber rail fence with stone lantern pillars, banner posts and a gap with a cobble path.

Pivot: the centre of the whole footprint (hall + yard), ground z = 0. The hall is at the back (+Y), its open side and
the yard opening face -Y (the front). Everything static is one mesh; banners are cloth (they sway in game).

Run:  Blender -b --factory-startup --python Tools/blender/assets/archery_hall.py -- [--no-render] [--views=a,b] [--samples N] [--cpu]
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import voxlib as V
import voxkit as K
from voxlib import Vox

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
NO_RENDER = "--no-render" in ARGS
VIEWS = [n for a in ARGS if a.startswith("--views=") for n in a.split("=", 1)[1].split(",")]
SAMPLES = int(ARGS[ARGS.index("--samples") + 1]) if "--samples" in ARGS else 32
CPU = "--cpu" in ARGS
TASK = "archery_hall"

VX = 0.125
NX, NY, NZ = 152, 120, 66            # 19 x 15 x 7.5 m
OX, OY = 76, 64                      # voxel that becomes (0, 0)

SHAFT = "#c9a468"
LEATHER = "#7a4a24"
STEEL = "#aeb2ba"
BACKWALL = "#a89484"
YARD = "#e6ab6c"


def vx(m):
    """metres east -> voxel x"""
    return int(round(m / VX + OX))


def vy(m):
    return int(round(m / VX + OY))


# ====================================================================================================== small helpers

def drop_bottom(ob, zs=(0.0,)):
    """Delete the faces lying flat at one of the heights zs and facing down (never seen)."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    doomed = [f for f in bm.faces if f.normal.z < -0.5 and any(all(abs(vt.co.z - z) < 1e-4 for vt in f.verts) for z in zs)]
    n = len(doomed)
    bmesh.ops.delete(bm, geom=doomed, context="FACES")
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()
    ob["voxel_faces"] = int(ob.get("voxel_faces", 0)) - n // 2
    return ob


def stud(v, x, y, z, face):
    """An iron stud one voxel proud of a face. (x, y, z) is the voxel of the face; face '-y', '+x', '+z' ..."""
    d = {"-y": (0, -1, 0), "+y": (0, 1, 0), "-x": (-1, 0, 0), "+x": (1, 0, 0), "+z": (0, 0, 1)}[face]
    v.set(x + d[0], y + d[1], z + d[2], "paint", STEEL)


def brace(v, x, y0, y1, z, dx, n=5, mat="beam"):
    """Stepped diagonal knee brace from a post face at voxel column x, height z, rising towards dx (+1 / -1)."""
    for k in range(n):
        xx = x + k * dx
        v.box(xx if dx > 0 else xx - 1, y0, z + k, xx + 1 if dx > 0 else xx, y1, z + k + 2, mat)


def brace_y(v, x0, x1, y, z, dy, n=5, mat="beam"):
    """The same in the YZ plane (braces on the end walls)."""
    for k in range(n):
        yy = y + k * dy
        v.box(x0, yy if dy > 0 else yy - 1, z + k, x1, yy + 1 if dy > 0 else yy, z + k + 2, mat)


# ====================================================================================================== the roof

def cbox(c, x0, y0, z0, x1, y1, z1, mat, color=None):
    """Fill a box of the coarse (25 cm) grid given in main-grid (12.5 cm) voxel coordinates (all even)."""
    for q in (x0, y0, z0, x1, y1, z1):
        assert q % 2 == 0, (x0, y0, z0, x1, y1, z1)
    c.box(x0 // 2, y0 // 2, z0 // 2, x1 // 2, y1 // 2, z1 // 2, mat, color)


def hall_roof(v, c, x0, x1, y0, y1, z, run=6, rise=4, thick=4, bw=6, left=True, right=True, seed=0, drop=None):
    """A stepped gable roof over x0..x1 / y0..y1 (ridge along X, eaves at height z): the tiles go into the coarse
    grid c (25 cm voxels: the same texture, a quarter of the faces), the chunky barge boards of stacked timber blocks
    at the two ends (each step its own block, iron studs on the big end blocks) and the ridge beam into v.
    left/right: whether that end gets barge boards. Returns the z of the top of the ridge beam."""
    half = (y1 - y0) / 2.0
    steps = int(np.ceil(half / run))
    top = z
    shades = ["#ffffff", "#e8d8c4"]
    for i in range(steps):
        lo, hi = y0 + i * run, y1 - i * run
        if hi - lo <= 0:
            break
        zl = z + i * rise
        zh = zl + max(thick, rise)
        cbox(c, x0, lo, zl, x1, hi, zh, "roof")
        top = zh
    mid = (y0 + y1) // 2
    # ridge beam
    v.box(x0, mid - 2, top, x1, mid + 2, top + 3, "beam")
    # barge boards: one block per step, three voxels proud of the tiles and one in front of their risers
    for (b0, b1, out, on) in ((x0 - 1, x0 + bw - 1, -1, left), (x1 - bw + 1, x1 + 1, 1, right)):
        if not on:
            continue
        for i in range(steps):
            lo, hi = y0 + i * run, y1 - i * run
            if hi - lo <= 0:
                break
            zl = z + i * rise
            col = shades[(i + seed) % 2]
            v.box(b0, lo - 1, zl, b1, hi + 1, zl + rise + 3, "beam", col)
        # the big end blocks at the eaves (front and back), with studs
        for (ya, yb, face) in ((y0 - 2, y0 + 4, "-y"), (y1 - 4, y1 + 2, "+y")):
            v.box(b0 - (1 if out < 0 else 0), ya, z - 3 if drop is None else drop, b1 + (1 if out > 0 else 0), yb,
                  z + rise + 3, "beam")
            sx = (b0 + b1) // 2 - (1 if out < 0 else 0)
            fy = ya if face == "-y" else yb - 1
            stud(v, sx, fy, z + 1, face)
            stud(v, b0 - 1 if out < 0 else b1, (ya + yb) // 2, z + 1, "-x" if out < 0 else "+x")
            stud(v, sx, (ya + yb) // 2, z + rise + 2, "+z")
        # block at the ridge end
        v.box(b0 - (1 if out < 0 else 0), mid - 3, top - 1, b1 + (1 if out > 0 else 0), mid + 3, top + 4, "beam")
        stud(v, b0 - 1 if out < 0 else b1, mid, top + 1, "-x" if out < 0 else "+x")
        stud(v, (b0 + b1) // 2, mid - 3, top + 1, "-y")
        stud(v, (b0 + b1) // 2, mid + 2, top + 1, "+y")
    return top + 3


# ====================================================================================================== pieces (own grids)

def emblem_arrows(n):
    """Crossed arrows, heads up, as an n x n pattern ('T' gold, 'L' light gold)."""
    g = [["." for _ in range(n)] for _ in range(n)]
    for (sx, sy, ex, ey) in ((1.0, n - 1.0, n - 2.0, 2.0), (n - 1.0, n - 1.0, 2.0, 2.0)):
        dx, dy = ex - sx, ey - sy
        L = (dx * dx + dy * dy) ** 0.5
        ux, uy = dx / L, dy / L
        for j in range(n):
            for i in range(n):
                px, py = i + 0.5 - sx, j + 0.5 - sy
                along = px * ux + py * uy
                perp = abs(-px * uy + py * ux)
                if 0 <= along <= L and perp < 0.62:
                    g[j][i] = "T"
                # head: a diamond at the far end
                a2 = along - (L - 0.6)
                if -2.2 <= a2 <= 1.4 and perp <= (1.4 - a2) * 0.55 and perp <= (a2 + 2.2) * 0.9:
                    g[j][i] = "T"
                # fletching: two short wings at the near end
                if 0.0 <= along <= 2.6 and 0.6 <= perp <= 1.7:
                    g[j][i] = "L"
    return ["".join(r) for r in g]


def banner(w=16, h=26, notch=5, emblem=12, name="banner", field="banner", edge="gold", rod="beam"):
    """Copy of voxkit.banner with our own crossed-arrows emblem (emblem = its size in texels). Origin: middle of the
    top of the rod; the cloth hangs below it facing -Y and sways in game."""
    pattern = emblem_arrows(emblem)
    ew = emblem
    ex0 = (w - ew) // 2
    ey0 = 3
    inside = np.zeros((h, w), bool)
    for j in range(h):
        for i in range(w):
            k = j - (h - notch)
            cut = k >= 0 and abs(i - (w - 1) / 2.0) < (k + 1) * (w / 2.0 - 2) / notch
            inside[j, i] = not cut
    v = Vox(w + 4, 2, h + 2, V.TEXEL, origin=((w + 4) / 2.0, 1, h + 2), name=name)
    for j in range(h):
        for i in range(w):
            if not inside[j, i]:
                continue
            border = i == 0 or i == w - 1 or j == h - 1 or (j + 1 < h and not inside[j + 1, i]) \
                or (i > 0 and not inside[j, i - 1]) or (i + 1 < w and not inside[j, i + 1])
            col = edge if border else field
            pj, pi = j - ey0, i - ex0
            if not border and 0 <= pj < len(pattern) and 0 <= pi < len(pattern[pj]) and pattern[pj][pi] != ".":
                col = "gold_light" if pattern[pj][pi] == "L" else "gold"
            elif not border and (i * 7 + j * 3) % 11 == 0:
                col = "banner_dark"
            z = h - 1 - j
            v.box(i + 2, 0, z, i + 3, 1, z + 1, "paint", col)
    v.box(0, 0, h, w + 4, 2, h + 2, rod)
    v.box(0, 0, h, 2, 2, h + 2, "gold")
    v.box(w + 2, 0, h, w + 4, 2, h + 2, "gold")
    v.box(3, 0, h, 5, 2, h + 2, "paint", "banner")                       # green straps round the rod
    v.box(w - 1, 0, h, w + 1, 2, h + 2, "paint", "banner")
    v.hang(region=(0, 0, 0, w + 4, 2, h))
    return v


def target_arrows(seed=3):
    """Three arrows stuck in a target, pointing out towards the viewer and to the right (6.25 cm voxels).
    Origin: the centre of the disc's front face."""
    a = Vox(26, 15, 14, 0.0625, origin=(5, 14, 7), name="arrows", seed=seed)
    rng = np.random.default_rng(seed)
    for k in range(3):
        hx, hz = 5 + int(rng.integers(-2, 3)), 7 + int(rng.integers(-2, 3)) - (k - 1)
        sx = 0.75 + 0.35 * rng.random()
        sz = (rng.random() - 0.4) * 0.35
        n = 13
        for st in range(n):
            px, py, pz = hx + int(round(st * sx)), 13 - st, hz + int(round(st * sz))
            if st < n - 4:
                a.set(px, py, pz, "paint", SHAFT)
            else:
                col = "target_red" if st == n - 3 else "white"
                a.set(px, py, pz, "paint", col)
                a.set(px, py, pz + 1, "paint", col)
                a.set(px, py, pz - 1, "paint", col)
    return a


def target(name="target", seed=3):
    """Round straw target on an A-frame stand with arrows in it (6.25 cm voxels). Disc ~1 m, centre 1.3 m up.
    Origin: centre of the base; faces -Y."""
    t = Vox(22, 22, 32, 0.0625, origin=(11, 11, 0), name=name, seed=seed)
    cz = 21                                                 # disc centre (voxels)
    # legs: two front legs splaying out, a back leg leaning back
    for s in (-1, 1):
        for zz in range(0, 18):
            off = 7 - zz // 5
            x0 = 11 + s * off - 1
            t.box(x0, 11, zz, x0 + 2, 13, zz + 1, "post")
        t.box(11 + s * 7 - 2, 9, 0, 11 + s * 7 + 2, 14, 1, "beam")
    for zz in range(0, 18):
        yy = 13 + int(round((17 - zz) * 6 / 17.0))
        t.box(10, yy, zz, 12, yy + 2, zz + 1, "post")
    t.box(4, 11, 6, 18, 13, 8, "beam")                      # cross rail
    t.box(6, 9, 11, 16, 12, 12, "beam")                     # ledge the disc sits on
    # disc
    for i in range(22):
        for k in range(cz - 10, cz + 11):
            dx, dz = i + 0.5 - 11, k + 0.5 - cz
            if max(abs(dx), abs(dz)) > 9.6 or abs(dx) + abs(dz) > 13.6:
                continue
            r = (dx * dx + dz * dz) ** 0.5
            ring = max(abs(dx), abs(dz)) > 8.4 or abs(dx) + abs(dz) > 12.2
            col = "#b98244" if ring else "target_red" if r < 2.2 else "target_white" if r < 4.2 else \
                "target_red" if r < 6.2 else "target_white"
            t.box(i, 9, k, i + 1, 12, k + 1, "hay", "#d8b070")
            t.box(i, 8, k, i + 1, 9, k + 1, "paint" if not ring else "plank", col if not ring else "#f0c890")
    t.box(10, 10, cz + 10, 12, 13, cz + 11, "beam")
    return t


def open_barrel():
    v = Vox(8, 8, 9, 0.125, origin=(4, 4, 0), name="barrel")
    v.cylinder(4, 4, 0, 8, 3.1, "plank")
    v.cylinder(4, 4, 1, 7, 3.6, "plank")
    for z in (1, 6):
        ring = Vox(8, 8, 9, 0.125)
        ring.cylinder(4, 4, z, z + 1, 3.9, "metal")
        v.stamp(ring, 0, 0, 0)
    v.cylinder(4, 4, 7, 8, 2.3, None)
    v.cylinder(4, 4, 6, 7, 2.3, "paint", "#2a1d12")
    return v


def arrow_bundle(seed=4, size=18, height=16, n=13):
    """Arrows standing nock-up in a barrel (6.25 cm voxels): shaft, white/red fletching. Origin centre, z=0."""
    a = Vox(size, size, height, 0.0625, origin=(size / 2.0, size / 2.0, 0), name="arrows")
    rng = np.random.default_rng(seed)
    cols = ["white", "target_red", "white", "cream", "white", "target_red"]
    spots = [(int(rng.integers(-3, 4)), int(rng.integers(-3, 4))) for _ in range(n)]
    for j, (bx, by) in enumerate(spots):
        lx, ly = bx / 3.0 * 0.25, by / 3.0 * 0.25
        shaft = int(rng.integers(6, 10))
        col = cols[j % len(cols)]
        for k in range(shaft + 4):
            px, py = size // 2 + bx + int(round(lx * k)), size // 2 + by + int(round(ly * k))
            if k < shaft:
                a.set(px, py, k, "paint", SHAFT)
            elif k < shaft + 3:
                a.set(px, py, k, "paint", col if k != shaft + 1 else "target_red")
                if j % 2:
                    a.set(px - 1, py, k, "paint", col)
                    a.set(px + 1, py, k, "paint", col)
                else:
                    a.set(px, py - 1, k, "paint", col)
                    a.set(px, py + 1, k, "paint", col)
            else:
                a.set(px, py, k, "paint", "#3a2a1c")
    return a


def arrow_barrel(x, y, seed=4):
    return [open_barrel().at(x, y, 0.0), arrow_bundle(seed).at(x, y, 0.875)]


def bow_rack(n=8, name="bowrack"):
    """A long low rack with bows standing in it (6.25 cm voxels). Origin centre of the base; front -Y."""
    w = n * 5 + 6
    r = Vox(w, 10, 30, 0.0625, origin=(w / 2.0, 5, 0), name=name)
    for x0 in (0, w // 2 - 1, w - 3):                        # uprights
        r.box(x0, 3, 0, x0 + 3, 7, 13, "post")
        r.box(x0 - 1, 1, 0, x0 + 4, 9, 1, "beam")
    r.box(0, 2, 2, w, 8, 4, "beam")                         # bottom trough
    r.box(0, 3, 10, w, 7, 13, "beam")                       # top rail with notches
    r.box(0, 2, 6, w, 3, 8, "beam")                         # front rail
    for i in range(0, w, 6):
        r.set(i + 2, 1, 7, "metal", STEEL)
        r.set(i + 2, 2, 11, "metal", STEEL)
    for b in range(n):
        bx = 4 + b * 5
        # limb: an arc bulging to the left, string straight on the right
        for zz in range(3, 29):
            t = (zz - 3) / 25.0
            bulge = int(round(2.2 * (1 - (2 * t - 1) ** 2)))
            r.box(bx - bulge, 4, zz, bx - bulge + 1, 6, zz + 1, "paint", "wood" if zz % 7 else "wood_dark")
            r.set(bx + 1, 5, zz, "paint", "cream")
        r.box(bx - 2, 4, 14, bx, 6, 17, "paint", LEATHER)  # grip
        r.box(bx, 4, 28, bx + 1, 6, 30, "paint", "wood_dark")  # tips
        r.box(bx, 4, 2, bx + 1, 6, 4, "paint", "wood_dark")
    return r


def crate(size=6, name="crate"):
    v = Vox(size, size, size, VX, origin=(size / 2.0, size / 2.0, 0), name=name)
    v.box(0, 0, 0, size, size, size, "plank")
    v.frame(0, 0, 0, size, size, size, "beam")
    h = size // 2
    v.set(h, 0, h, "metal", STEEL)
    v.set(0, h, h, "metal", STEEL)
    v.set(h, h, size - 1, "metal", STEEL)
    return v


def lantern(v, x, y, z, cap="beam", lid=True):
    """A 4 x 4 voxel lantern, bottom centre at voxel (x, y, z): base, glowing body in a cage, a wider lid, a knob.
    Returns the z above it."""
    v.box(x - 2, y - 2, z, x + 2, y + 2, z + 1, cap)
    v.box(x - 2, y - 2, z + 1, x + 2, y + 2, z + 5, "glow", "lantern")
    for dx in (x - 2, x + 1):
        for dy in (y - 2, y + 1):
            v.box(dx, dy, z + 1, dx + 1, dy + 1, z + 5, cap)
    if lid:
        v.box(x - 3, y - 3, z + 5, x + 3, y + 3, z + 6, cap)
    else:
        v.box(x - 2, y - 2, z + 5, x + 2, y + 2, z + 6, cap)
    v.box(x - 1, y - 1, z + 6, x + 1, y + 1, z + 7, cap)
    return z + 7


def hang_lantern(v, x, y, z, out=(0, -1)):
    """A lantern hanging from an iron bracket on a post face. (x, y, z): the face voxel the bracket leaves from."""
    ox, oy = out
    for k in range(1, 4):
        v.set(x + ox * k, y + oy * k, z, "metal", "iron")
    v.set(x + ox, y + oy, z - 1, "metal", "iron")
    cx, cy = x + ox * 3, y + oy * 3
    v.set(cx, cy, z - 1, "metal", "iron")
    # the lantern under the hook (4 x 4, its corner bars leave two glowing columns per face)
    ex = 1 if ox > 0 else 0
    ey = 1 if oy > 0 else 0
    cx, cy = cx + ex, cy + ey
    v.box(cx - 2, cy - 2, z - 8, cx + 2, cy + 2, z - 7, "beam")
    v.box(cx - 2, cy - 2, z - 7, cx + 2, cy + 2, z - 3, "glow", "lantern")
    for dx in (cx - 2, cx + 1):
        for dy in (cy - 2, cy + 1):
            v.box(dx, dy, z - 7, dx + 1, dy + 1, z - 3, "beam")
    v.box(cx - 2, cy - 2, z - 3, cx + 2, cy + 2, z - 2, "beam")
    v.box(cx - 1, cy - 1, z - 2, cx + 1, cy + 1, z - 1, "beam")


# ====================================================================================================== the main grid

# hall plan (voxels)
FRONT0, FRONT1 = 72, 76          # front post line   (y 1.5 .. 2.0 m)
BACK0, BACK1 = 110, 114          # back wall          (y 6.25 .. 6.75 m)
ROOF0, ROOF1 = 70, 118           # roof front / back eave (y 0.75 .. 6.75 m)
POSTS = [(10, 14), (46, 50), (102, 106), (138, 142)]   # x of the four front posts (x = -8, -3.5, +3.5, +8 m)
WING_EAVE = 30                   # z where the wing roofs start (3.75 m)
MID_EAVE = 38                    # z where the middle roof starts (4.75 m)
FENCE_Y = 13                     # front fence line (y = -6.375 m), posts y 13..16
FENCE_X = (2, 150)               # side fence lines (posts x 1..4 and 148..151)
GAP = (64, 88)                   # opening in the front fence (x -1.5 .. +1.5 m)


def hall(v, c):
    # ---- floor: packed dirt a voxel above the yard, with a stone curb along the front
    cbox(c, 12, FRONT1, 0, 140, BACK0, 2, "cobble", "#d8a068")
    v.box(14, FRONT0, 0, 138, FRONT1, 2, "stone", "#d8d0c4")
    for x in range(14, 138, 4):                           # curb blocks, alternately a shade lighter
        if (x // 4) % 2:
            v.box(x, FRONT0, 0, x + 4, FRONT1, 2, "stone", "#c4bcb0")

    # ---- back wall: dark stone, up to the roofs
    cbox(c, 10, BACK0, 0, 142, BACK1, WING_EAVE, "brick", BACKWALL)
    cbox(c, 46, BACK0, 0, 106, BACK1, MID_EAVE, "brick", BACKWALL)
    c.tint("brick", "#9c8878", p=0.12, seed=11, cell=2)
    # back wall dressing: posts on the inside face and a rail
    for (x0, x1) in POSTS + [(28, 31), (74, 78), (121, 124)]:
        top = MID_EAVE - 4 if 46 <= x0 <= 102 else WING_EAVE - 4
        v.box(x0, BACK0 - 1, 0, x1, BACK0, top + 4, "post")
    v.box(10, BACK0 - 1, WING_EAVE - 4, 142, BACK0 + 1, WING_EAVE, "beam")
    v.box(46, BACK0 - 1, MID_EAVE - 4, 106, BACK0 + 1, MID_EAVE, "beam")
    # outside face of the back wall: posts and a plate too, so the back is finished
    for (x0, x1) in POSTS + [(28, 31), (74, 78), (121, 124)]:
        top = MID_EAVE if 46 <= x0 <= 102 else WING_EAVE
        v.box(x0, BACK1, 0, x1, BACK1 + 1, top, "post")
    v.box(10, BACK1, WING_EAVE - 4, 142, BACK1 + 1, WING_EAVE, "beam")
    v.box(46, BACK1, MID_EAVE - 4, 106, BACK1 + 1, MID_EAVE, "beam")
    for (x0, x1) in POSTS:
        v.box(x0 - 1, BACK1 - 1, 0, x1 + 1, BACK1 + 2, 6, "stone", "#d0c8bc")

    # ---- end walls: stone to waist height, timber frame above, open
    for (x0, x1, dx) in ((10, 14, -1), (138, 142, 1)):
        v.box(x0 - 1, FRONT1, 0, x1 + 1, BACK0, 8, "stone", "#d8d0c4")
        v.box(x0 - 1, FRONT1, 8, x1 + 1, BACK0, 9, "beam")
        midy = (FRONT1 + BACK0) // 2
        v.box(x0, midy - 2, 9, x1, midy + 2, WING_EAVE, "post")
        v.box(x0, FRONT0, WING_EAVE - 4, x1, BACK0, WING_EAVE, "beam")           # plate along the side
        v.box(x0, FRONT1, 15, x1, BACK0, 17, "beam")                              # mid rail
        brace_y(v, x0 + 1, x1 - 1, midy - 2, 17, -1, 5)
        brace_y(v, x0 + 1, x1 - 1, midy + 2, 17, 1, 5)
        brace_y(v, x0 + 1, x1 - 1, FRONT1, 17, 1, 5)
        brace_y(v, x0 + 1, x1 - 1, BACK0, 17, -1, 5)
    # ---- posts on stone footings
    for i, (x0, x1) in enumerate(POSTS):
        mid = 0 < i < 3
        top = MID_EAVE - 4 if mid else WING_EAVE
        v.box(x0 - 1, FRONT0 - 1, 0, x1 + 1, FRONT1 + 1, 4, "stone", "#d8d0c4")
        v.box(x0 - 1, FRONT0 - 1, 4, x1 + 1, FRONT1 + 1, 8, "stone", "#c8c0b4")
        v.box(x0 - 1, FRONT0 - 1, 8, x1 + 1, FRONT1 + 1, 9, "stone", "#e4dccf")
        v.box(x0, FRONT0, 9, x1, FRONT1, top, "post")
        # back posts (inside the wall line)
    v.chunky("stone", p=0.3, seed=2, region=(0, FRONT0 - 2, 0, NX, FRONT1 + 2, 9))

    # ---- wings: front plate (eave beam) along x, braces
    WB = WING_EAVE - 4
    for (a0, a1) in ((8, 50), (102, 144)):
        v.box(a0, FRONT0 - 1, WB, a1, FRONT1, WING_EAVE, "beam")
    for (x0, x1) in ((14, 46), (106, 138)):
        brace(v, x0, FRONT0, FRONT1 - 1, WB - 6, +1, 6)
        brace(v, x1, FRONT0, FRONT1 - 1, WB - 6, -1, 6)
    # ---- middle bay: lintel, a row of short studs, then the high plate
    L0 = MID_EAVE - 10
    v.box(46, FRONT0, L0, 106, FRONT1, L0 + 3, "beam")
    v.box(50, FRONT0 + 1, L0 + 3, 102, FRONT1, L0 + 6, "plank", "#5a4030")      # dark gap behind the studs
    for x in range(52, 101, 5):
        v.box(x, FRONT0, L0 + 3, x + 2, FRONT1 - 1, L0 + 6, "beam")
    v.box(44, FRONT0 - 1, L0 + 6, 108, FRONT1, MID_EAVE, "beam")
    brace(v, 50, FRONT0, FRONT1 - 1, L0 - 6, +1, 6)
    brace(v, 102, FRONT0, FRONT1 - 1, L0 - 6, -1, 6)
    # beams across the hall (tie beams) above each post pair
    for (x0, x1) in POSTS:
        top = MID_EAVE if 46 <= x0 <= 102 else WING_EAVE
        v.box(x0, FRONT0, top - 4, x1, BACK0, top, "beam")
    # studs on the beam ends and post heads (front)
    for (x0, x1) in POSTS:
        top = MID_EAVE if 46 <= x0 <= 102 else WING_EAVE
        stud(v, (x0 + x1) // 2, FRONT0 - 1, top - 2, "-y")
    for (x0, x1) in ((46, 50), (102, 106)):
        stud(v, (x0 + x1) // 2, FRONT0, L0 + 1, "-y")

    # ---- roofs: the two low wings first, the raised middle over them
    hall_roof(v, c, 6, 50, ROOF0 + 2, ROOF1 - 2, WING_EAVE, right=False, seed=0)
    hall_roof(v, c, 102, 146, ROOF0 + 2, ROOF1 - 2, WING_EAVE, left=False, seed=1)
    hall_roof(v, c, 44, 108, ROOF0, ROOF1, MID_EAVE, seed=0, drop=WING_EAVE)
    c.scatter("roof", "moss", p=0.04, seed=4, direction="+z")
    c.tint("roof", "#a8b88a", p=1.0, seed=5)
    c.tint("roof", "#c8d898", p=0.2, seed=6)
    c.tint("roof", "#88a06c", p=0.18, seed=8)

    # ---- lanterns
    hang_lantern(v, 50, FRONT0 + 1, 24, out=(1, 0))         # on the middle posts, into the middle bay
    hang_lantern(v, 105, FRONT0 - 1, 24, out=(0, -1))
    K.wall_lantern(v, 66, BACK0 - 1, 25)
    K.wall_lantern(v, 86, BACK0 - 1, 25)
    K.wall_lantern(v, 14, 92, 21, out=(1, 0))               # inside the left wing on the end frame
    K.wall_lantern(v, 137, 92, 21, out=(-1, 0))

    # ---- furniture in the left wing: crates
    for (cx, cy, cz, s) in ((22, 104, 2, 6), (29, 104, 2, 6), (25, 104, 8, 6), (20, 92, 2, 5), (37, 98, 2, 5)):
        v.stamp(crate(s), cx, cy, cz)
    v.box(27, 86, 2, 35, 93, 6, "hay")                       # a straw bale
    # right wing: crate behind the bow rack corner
    v.stamp(crate(6), 132, 103, 2)
    v.stamp(crate(5), 132, 103, 8)
    v.tint("plank", "#ead2b0", p=0.25, seed=3, cell=2)

    # ---- a little green: vines down the posts and off the eaves
    for (vx_, ln) in ((47, 4), (49, 2), (104, 3), (12, 3), (139, 2)):
        v.box(vx_, FRONT0 - 2, WING_EAVE - 2 - ln, vx_ + 1, FRONT0 - 1, WING_EAVE - 2, "leaves", "#d8f0a0")
    v.scatter("stone", "mossy_stone", p=0.08, seed=5, region=(0, 0, 0, NX, NY, 9))


def fence(v):
    """Rail fence: chunky posts with iron bands and a stud on top, two rails."""
    def post(x, y):
        v.box(x - 1, y - 1, 0, x + 2, y + 2, 9, "post")
        v.box(x - 1, y - 1, 9, x + 2, y + 2, 10, "beam")
        v.box(x - 1, y - 1, 6, x + 2, y + 2, 7, "metal", "iron")
        v.box(x - 1, y - 1, 3, x + 2, y + 2, 4, "metal", "iron")
        v.set(x, y, 10, "paint", STEEL)

    def rails_x(x0, x1, y):
        v.box(x0, y - 1, 6, x1, y + 1, 8, "beam")
        v.box(x0, y - 1, 3, x1, y + 1, 5, "beam")

    def rails_y(x, y0, y1):
        v.box(x - 1, y0, 6, x + 1, y1, 8, "beam")
        v.box(x - 1, y0, 3, x + 1, y1, 5, "beam")

    fy = FENCE_Y + 1
    lx, rx = FENCE_X[0] + 1, FENCE_X[1] - 1
    # front, left half and right half
    rails_x(lx, GAP[0], fy)
    rails_x(GAP[1], rx, fy)
    xs = sorted(set(list(range(lx + 10, GAP[0] - 4, 11)) + [GAP[0] - 2]))
    xs += sorted(set([GAP[1] + 1] + list(range(GAP[1] + 12, rx - 6, 11))))
    for x in xs:
        post(x, fy)
    # sides, from the corner pillars back to the hall
    for x in (lx, rx):
        rails_y(x, fy, FRONT0 + 2)
        for y in range(fy + 11, FRONT0 - 2, 11):
            post(x, y)
        post(x, FRONT0 + 1)
    # short rails from the side fences to the corner footings
    rails_x(lx, 9, FRONT0 + 1)
    rails_x(143, rx, FRONT0 + 1)


def lantern_pillar(v, x, y):
    """A stone pillar with a lantern on top (the front corners). (x, y): voxel centre."""
    v.box(x - 3, y - 3, 0, x + 3, y + 3, 1, "stone", "#d0c8bc")
    v.box(x - 3, y - 3, 1, x + 3, y + 3, 12, "stone", "#d8d0c4")
    for zz in (4, 8):                                          # courses
        v.box(x - 3, y - 3, zz, x + 3, y + 3, zz + 1, "stone", "#c8c0b4")
    v.box(x - 3, y - 3, 12, x + 3, y + 3, 13, "stone", "#ece4d8")
    lantern(v, x, y, 13)


def banner_post(v, x, y, h=17):
    """A wooden post on a stone block with a crossbar at the top (the banner hangs from it). Returns the z of the bar."""
    v.box(x - 2, y - 2, 0, x + 2, y + 2, 3, "stone", "#d8d0c4")
    v.box(x - 1, y - 1, 3, x + 1, y + 1, h, "post")
    v.box(x - 4, y - 1, h - 2, x + 4, y + 1, h, "beam")
    v.box(x - 1, y - 1, h, x + 1, y + 1, h + 1, "beam")
    v.set(x - 4, y - 1, h - 2, "gold")
    v.set(x + 3, y - 1, h - 2, "gold")
    return h - 2


def path(v):
    """Stone slabs in the gap, out to the front edge, and a threshold row at the fence line."""
    rng = np.random.default_rng(7)
    for x in range(GAP[0], GAP[1], 4):
        for y in range(FENCE_Y - 5, FENCE_Y + 6, 4):
            if y >= FENCE_Y - 1 and y < FENCE_Y + 3:
                continue
            col = ["#d8d0c4", "#c8c0b4", "#e2dacd", "#bcb4a8"][int(rng.integers(0, 4))]
            v.box(x, y, 0, x + 4, y + 4, 1, "stone", col)
            v.clear(x, y, 0, x + 4, y + 4, 0)
    v.box(GAP[0] - 1, FENCE_Y, 0, GAP[1] + 1, FENCE_Y + 3, 2, "stone", "#d0c8bc")
    # the path frays out at the front corners
    for (x, y) in ((GAP[0] - 4, FENCE_Y - 5), (GAP[1], FENCE_Y - 5), (GAP[1], FENCE_Y - 1)):
        v.box(x, y, 0, x + 4, y + 4, 1, "stone", "#c8c0b4")


def yard():
    """The dirt yard: one layer of 25 cm voxels, its top at z = 0.125, grass creeping in along the fence."""
    nx, ny = 72, 30                                          # x -9 .. 9, y -6.25 .. 1.25
    y0 = (FENCE_Y + 1 - OY) * VX
    g = Vox(nx, ny, 1, 0.25, origin=(0, 0, 0), name="yard", seed=5)
    g.box(0, 0, 0, nx, ny, 1, "cobble", YARD)
    rng = np.random.default_rng(3)
    n = V.noise3((nx, ny, 1), 5, seed=9)[:, :, 0]
    for i in range(nx):
        for j in range(ny):
            edge = min(i, nx - 1 - i, j)
            if edge == 0 and rng.random() < 0.75 or edge == 1 and rng.random() < 0.35 or edge == 2 and rng.random() < 0.1:
                g.set(i, j, 0, "grass")
            elif n[i, j] > 0.62:
                g.set(i, j, 0, "cobble", "#d89a5c")
            elif n[i, j] < 0.36:
                g.set(i, j, 0, "cobble", "#eebb80")
    # the gap in the front fence: no yard voxels where the stone path is
    gx0 = int(round((-1.5 + 9.0) / 0.25))
    gx1 = int(round((1.5 + 9.0) / 0.25))
    g.clear(gx0, 0, 0, gx1, 2, 1)
    g.tint("cobble", "#f0b878", p=0.15, seed=4)
    return g.at(-9.0, y0, -0.125)


def tufts(seed=2):
    """Grass tufts and a few flowers along the fence (6.25 cm voxels, walk-through clutter is fine in one mesh)."""
    rng = np.random.default_rng(seed)
    out = []
    spots = [(-8.6, -5.7), (-8.4, -2.5), (-8.7, 0.1), (8.5, -5.3), (8.6, -1.7), (8.3, 0.4), (-6.0, -5.9), (-3.2, -6.0),
             (3.0, -5.9), (6.4, -5.8), (-9.5, -6.8), (9.6, -6.7), (-4.0, -6.9), (5.0, -6.9), (9.7, 1.0), (-9.7, 2.1)]
    for k, (x, y) in enumerate(spots):
        f = Vox(8, 8, 6, 0.0625, origin=(4, 4, 0), seed=k)
        for _ in range(7):
            fx, fy = int(rng.integers(0, 8)), int(rng.integers(0, 8))
            f.box(fx, fy, 0, fx + 1, fy + 1, int(rng.integers(2, 5)), "leaves", "#c8e878")
        if k % 3 == 0:
            fx, fy = int(rng.integers(2, 6)), int(rng.integers(2, 6))
            f.box(fx, fy, 0, fx + 1, fy + 1, 4, "leaves", "#b8e070")
            f.set(fx, fy, 4, "paint", ["flower_white", "flower_yellow", "flower_pink"][k % 3])
        out.append(f.at(x, y, 0.125 if abs(x) < 9.0 and y > -6.2 else 0.0))
    return out


def build():
    v = Vox(NX, NY, NZ, VX, origin=(OX, OY, 0), name="hall", seed=21)
    c = Vox(NX // 2, NY // 2, NZ // 2, 2 * VX, origin=(OX // 2, OY // 2, 0), name="coarse", seed=22)
    hall(v, c)
    fence(v)
    lantern_pillar(v, 3, FENCE_Y + 1)
    lantern_pillar(v, 149, FENCE_Y + 1)
    bl = banner_post(v, 13, FENCE_Y - 1)
    br = banner_post(v, 120, FENCE_Y - 1)
    path(v)
    # crates outside the left corner, on the grass inside the fence
    for (cx, cy, cz, s) in ((6, 64, 0, 5), (6, 58, 0, 5), (6, 64, 5, 4), (17, 66, 0, 6)):
        v.stamp(crate(s), cx, cy, cz)
    v.chunky("stone", p=0.2, seed=8, region=(0, 0, 0, NX, 12, 12))

    parts = [v, c, yard()]
    # targets in the middle bay
    for i, x in enumerate((-2.1, 0.0, 2.1)):
        ty = 3.4 + (0.1 if i == 1 else 0.0)
        parts.append(target(seed=3 + i).at(x, ty, 0.25))
        parts.append(target_arrows(seed=11 + i).at(x, ty - 0.1875, 0.25 + 1.3125))
    # bow rack against the back wall of the right wing
    parts.append(bow_rack(8).at(5.6, 4.0, 0.25))
    # arrow barrels
    parts += arrow_barrel(-3.15, 0.65, seed=4)
    parts += arrow_barrel(6.6, 1.95, seed=6)
    parts += arrow_barrel(8.95, 0.5, seed=8)
    # banners: the big one off the middle eave, small ones on the corner posts and the banner posts
    parts.append(banner(18, 30, emblem=14, name="big").at(2.45, (FRONT0 - 3 - OY) * VX, MID_EAVE * VX - 0.05))
    parts.append(banner(10, 16, notch=4, emblem=8, name="cornerL").at(-8.0, (FRONT0 - 2 - OY) * VX + 0.02, 2.55))
    parts.append(banner(10, 16, notch=4, emblem=8, name="cornerR").at(8.0, (FRONT0 - 2 - OY) * VX + 0.02, 3.0))
    for (bx, bz) in ((13, bl), (120, br)):
        parts.append(banner(9, 15, notch=4, emblem=7, name="post", rod="beam")
                     .at((bx - OX) * VX, (FENCE_Y - 1 - OY) * VX - 0.19, bz * VX + 0.02))
    parts += tufts()
    if os.environ.get("AH_DEBUG"):
        for p_ in parts:
            a_ = p_.mesh_arrays()
            print("part", p_.name, 0 if a_ is None else len(a_["verts"]))
    ob = V.join(parts, "SM_ArcheryHall")
    drop_bottom(ob, zs=(0.0, -0.125))
    return ob


# ====================================================================================================== main

def render(path, target=(0, 0, 1.5), az=28.0, el=32.0, dist=22.0, lens=85.0, res=(1280, 800), samples=32,
           sun_az=-60.0, sun_el=32.0):
    """voxlib.render, with a choice of CPU (Cycles on Metal can crash while other jobs render)."""
    import bpy, math
    scene = bpy.context.scene
    if "Sun" not in bpy.data.objects:
        V.setup_light(scene, sun_az, sun_el)
    if "PreviewGround" not in bpy.data.objects:
        bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, -0.001))
        g = bpy.context.active_object
        g.name = "PreviewGround"
        gm = bpy.data.materials.new("PreviewGround")
        gm.use_nodes = True
        gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.13, 0.25, 0.05, 1)
        gm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 1.0
        g.data.materials.append(gm)
    cam = bpy.data.objects.get("PreviewCam")
    if cam is None:
        cam = bpy.data.objects.new("PreviewCam", bpy.data.cameras.new("PreviewCam"))
        scene.collection.objects.link(cam)
    a, e = math.radians(az), math.radians(el)
    cam.location = (target[0] + math.sin(a) * math.cos(e) * dist, target[1] - math.cos(a) * math.cos(e) * dist,
                    target[2] + math.sin(e) * dist)
    V.look_at(cam, target)
    cam.data.lens = lens
    cam.data.clip_end = 2000
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.filepath = path
    for transform, look in (("Filmic", "Medium High Contrast"), ("AgX", "AgX - Medium High Contrast")):
        try:
            scene.view_settings.view_transform = transform
            scene.view_settings.look = look
            break
        except Exception:
            continue
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 4
    scene.cycles.device = "CPU"
    if not CPU:
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            prefs.compute_device_type = "METAL"
            prefs.get_devices()
            for dev in prefs.devices:
                dev.use = True
            scene.cycles.device = "GPU"
        except Exception:
            pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.render.render(write_still=True)
    print("rendered", path)


def preview(tag, **kw):
    if NO_RENDER or (VIEWS and tag not in VIEWS):
        return
    import time
    path = os.path.join(V.PREVIEWS, "%s_%s.png" % (TASK, tag))
    kw.setdefault("samples", SAMPLES)
    for attempt in range(3):
        try:
            render(path, **kw)
            return
        except RuntimeError as e:
            print("render failed (%s), retrying" % str(e)[:80])
            time.sleep(20)


def main():
    V.reset_scene()
    ob = build()
    print("faces", ob["voxel_faces"])
    V.export_gltf(ob, collision="complex")
    preview("ref", target=(0.3, 0.4, 1.6), az=-18, el=31, dist=33, lens=45, res=(1280, 720), sun_az=-125, sun_el=28)
    preview("front", target=(0, 0, 2.0), az=0, el=12, dist=42, lens=50, res=(1280, 720), sun_az=-150, sun_el=30)
    preview("back", target=(0, 0, 2.0), az=200, el=30, dist=40, lens=50, res=(1280, 720))
    preview("side", target=(0, 0.5, 1.8), az=-75, el=22, dist=36, lens=50, res=(1280, 720), sun_az=-150, sun_el=30)
    preview("junction", target=(-3.5, 1.0, 3.8), az=-20, el=25, dist=9, lens=50, res=(1280, 720), sun_az=-150, sun_el=30)
    preview("close", target=(0, 3.0, 1.6), az=-8, el=20, dist=16, lens=50, res=(1280, 720), sun_az=-150, sun_el=30)


if __name__ == "__main__":
    main()
