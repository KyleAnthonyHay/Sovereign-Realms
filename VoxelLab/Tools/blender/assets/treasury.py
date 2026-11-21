"""treasury: the gold vault (EVLBuilding::Treasury) of the voxel village, after References/Remake/gold_vault.png.

  SM_Treasury   a squat stone strongroom: grey block walls on a plinth, stone corner pillars with timber capitals and
                gold plates, a dark timber top plate and braces, a green hip roof with a cross gable over the door and a
                small lit lantern cupola on the ridge. The front: a big round wooden vault door with a ship's-wheel
                handle, iron hinge and gold rivets in a stone arch; a gold coin-stack crest framed by laurels in the
                gable; green coin banners and hanging lanterns either side of the door; stone steps with a green
                runner and two stone lantern posts; an arched leaded window with a flower box; crates of gold bars
                and a barrel round the foot.

Pivot: the middle of the footprint at ground level (z = 0); the door faces -Y. One mesh; the banners are cloth (they
sway in game and take the enemy's colour). About 12.5 x 9 m, 9 m to the top of the cupola.

Run:  Blender -b --factory-startup --python Tools/blender/assets/treasury.py -- [--no-render] [--views=a,b] [--samples N] [--cpu]
"""
import math
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
TASK = "treasury"
NAME = "SM_Treasury"

VX = 0.125
TX = V.TEXEL
NX, NY, NZ = 104, 80, 80             # 13 x 10 x 10 m
OX, OY = 52, 40                      # the voxel that becomes (0, 0); all plan coordinates below are relative to it
SHIFT_Y = 0.25                       # moves the whole model so that its footprint is centred on the pivot

# colours
WALL_T = "#b9b3aa"                   # the grey block walls
STONE_T = "#cfc8bc"                  # pillars, arch, steps
STONE_L = "#e2dbcf"
STONE_D = "#aaa298"
WOOD_T = "#c8a07a"                   # the timber
WOOD_D = "#9a7656"
PLANK_T = "#c49a6c"                  # the door's planks
IRON = None                          # (the metal texture as it is: a dark grey)
RUNNER = "#2f6b25"

# plan (voxels of 12.5 cm, relative to the pivot before SHIFT_Y)
WX0, WX1 = -44, 44                   # walls (11 m)
WY0, WY1 = -24, 32                   # front face .. back face (7 m)
EAVE = 36                            # top of the walls (4.5 m)
PLATE = 30                           # bottom of the timber top plate
SILL = 6                             # the landing in front of the door
DX, DZ = 14, 16.0                    # centre of the vault door (x, z)
R_DOOR, R_RECESS, R_ARCH = 9.25, 9.75, 13.0
GX0, GX1 = -12, 40                   # the front cross gable over the door bay (its middle is the door's)
GY0 = WY0 - 4                        # the front of its roof (half a metre in front of the wall)
WIN_X = -31                          # the arched window


def B(v, x0, y0, z0, x1, y1, z1, mat, color=None):
    v.box(OX + x0, OY + y0, z0, OX + x1, OY + y1, z1, mat, color)


def S(v, x, y, z, mat, color=None):
    v.set(OX + x, OY + y, z, mat, color)


def C(c, x0, y0, z0, x1, y1, z1, mat, color=None):
    """A box of the coarse (25 cm) roof grid, given in fine-grid plan coordinates (all even)."""
    for q in (x0, y0, z0, x1, y1, z1):
        assert q % 2 == 0, (x0, y0, z0, x1, y1, z1)
    c.box((OX + x0) // 2, (OY + y0) // 2, z0 // 2, (OX + x1) // 2, (OY + y1) // 2, z1 // 2, mat, color)


def ring_xz(v, cx, cz, r0, r1, y0, y1, mat, color=None, cond=None, colfn=None):
    """Voxels whose centre lies r0 <= d < r1 from (cx, cz) in the front (XZ) plane, from y0 to y1."""
    for x in range(int(math.floor(cx - r1)) - 1, int(math.ceil(cx + r1)) + 1):
        for z in range(max(0, int(math.floor(cz - r1)) - 1), int(math.ceil(cz + r1)) + 1):
            dx, dz = x + 0.5 - cx, z + 0.5 - cz
            d = math.hypot(dx, dz)
            if r0 <= d < r1 and (cond is None or cond(dx, dz, d)):
                B(v, x, y0, z, x + 1, y1, z + 1, mat, colfn(dx, dz, d) if colfn else color)


def plate(v, x, y, z, face="-y", n=2, stud=True):
    """A gold plate n x n voxels one voxel proud of a face; (x, y, z) is its low corner on the face layer."""
    if face == "-y":
        B(v, x, y - 1, z, x + n, y, z + n, "gold", "#e8d8b0")
        if stud and n >= 3:
            S(v, x + n // 2, y - 2, z + n // 2, "gold")
    elif face == "+y":
        B(v, x, y + 1, z, x + n, y + 2, z + n, "gold", "#e8d8b0")
        if stud and n >= 3:
            S(v, x + n // 2, y + 2, z + n // 2, "gold")
    elif face == "-x":
        B(v, x - 1, y, z, x, y + n, z + n, "gold", "#e8d8b0")
        if stud and n >= 3:
            S(v, x - 2, y + n // 2, z + n // 2, "gold")
    elif face == "+x":
        B(v, x + 1, y, z, x + 2, y + n, z + n, "gold", "#e8d8b0")
        if stud and n >= 3:
            S(v, x + 2, y + n // 2, z + n // 2, "gold")


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


# ====================================================================================================== pixel-art pieces

def coin_rows(w, h, stacks, laurel=None):
    """A char grid (top row first): stacks = [(x0, width, bottom_row, coins)], drawn in order (later ones in front,
    with a gap of the background round them). 'T' coin side, 'D' the dark line between coins and the stack's edges,
    'L' the light top of a stack; laurel = (cx, cy, r, a0, a1): two mirrored branches on that arc (cy measured up
    from the bottom; degrees, a0 the foot, a1 the tip), 'S' stem, 'G' leaves."""
    g = [["." for _ in range(w)] for _ in range(h)]

    def put(x, row, ch):
        if 0 <= x < w and 0 <= row < h:
            g[row][x] = ch

    if laurel:
        cx, cy, r, a0, a1 = laurel
        for side in (0, 1):
            def P(px, py, ch):
                xx, yy = int(round(px)), int(round(py))
                put(w - 1 - xx if side else xx, h - 1 - yy, ch)
            a, k = a0, 0
            while a >= a1:
                t = math.radians(a)
                px, py = cx + r * math.cos(t), cy + r * math.sin(t)
                P(px, py, "S")
                if k % 3 == 1:
                    tx, ty = math.sin(t), -math.cos(t)          # up the branch
                    nx, ny = math.cos(t), math.sin(t)           # outwards
                    for sgn in (1, -1):
                        dx, dy = tx * 0.75 + nx * 0.65 * sgn, ty * 0.75 + ny * 0.65 * sgn
                        L = math.hypot(dx, dy)
                        dx, dy = dx / L, dy / L
                        for st in (1.0, 2.0, 3.0):
                            P(px + dx * st, py + dy * st, "G")
                            if st < 3.0:
                                P(px + dx * st + tx * 0.8, py + dy * st + ty * 0.8, "G")
                a -= 4
                k += 1
            # a berry-like tip
            t = math.radians(a1)
            P(cx + r * math.cos(t) + math.sin(t) * 1.5, cy + r * math.sin(t) - math.cos(t) * 1.5, "G")
    for n_, (x0, cw, bottom, n) in enumerate(stacks):
        top = bottom - 2 * n
        if n_:
            for row in range(top - 1, bottom + 1):
                put(x0 - 1, row, ".")
                put(x0 + cw, row, ".")
        for k in range(n):
            for x in range(x0, x0 + cw):
                edge = x in (x0, x0 + cw - 1)
                put(x, bottom - 2 * k, "D")
                put(x, bottom - 2 * k - 1, "D" if edge else "T")
        for x in range(x0, x0 + cw):
            put(x, top, "L" if x not in (x0, x0 + cw - 1) else "T")
        for x in range(x0 + 2, x0 + cw - 2):
            put(x, top - 1, "L")
    return ["".join(r) for r in g]


def crest():
    """The coin-stack crest with its laurels (6.25 cm voxels): three stacks of coins, two laurel branches round them.
    Origin: the middle of its bottom edge, at its back face (it faces -Y)."""
    w, h = 34, 26
    rows = coin_rows(w, h, [(11, 12, 23, 7), (4, 10, 23, 4), (20, 10, 23, 3)], laurel=(16.5, 12.0, 14.0, 245, 140))
    pal = {"T": ("gold", "#f2e2bc"), "D": ("gold", "#c49a58"), "L": ("gold", "#ffffff"), "G": ("gold", "#e8cc90"),
           "S": ("gold", "#b89050")}
    v = Vox(w, 2, h, TX, origin=(w / 2.0, 2, 0), name="crest")
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch == ".":
                continue
            m, col = pal[ch]
            z = h - 1 - j
            d0 = 0 if ch not in "GS" else 1                # coins two texels deep, the laurels one
            v.box(i, d0, z, i + 1, 2, z + 1, m, col)
    return v


def coin_emblem():
    return coin_rows(11, 11, [(0, 7, 10, 4), (5, 6, 10, 2)])


def banner(w=12, h=22, notch=4, name="banner", field="banner", edge="gold", rod="beam"):
    """voxkit.banner with a coin-stack emblem. Origin: the middle of the top of the rod; faces -Y; the cloth sways."""
    pattern = coin_emblem()
    ew = max(len(r) for r in pattern)
    ex0 = (w - ew) // 2
    ey0 = 3
    inside = np.zeros((h, w), bool)
    for j in range(h):
        for i in range(w):
            k = j - (h - notch)
            cut = k >= 0 and abs(i - (w - 1) / 2.0) < (k + 1) * (w / 2.0 - 2) / notch
            inside[j, i] = not cut
    v = Vox(w + 4, 2, h + 2, TX, origin=((w + 4) / 2.0, 1, h + 2), name=name)
    for j in range(h):
        for i in range(w):
            if not inside[j, i]:
                continue
            border = i == 0 or i == w - 1 or j == h - 1 or (j + 1 < h and not inside[j + 1, i]) \
                or (i > 0 and not inside[j, i - 1]) or (i + 1 < w and not inside[j, i + 1])
            col = edge if border else field
            pj, pi = j - ey0, i - ex0
            if not border and 0 <= pj < len(pattern) and 0 <= pi < len(pattern[pj]) and pattern[pj][pi] != ".":
                col = {"T": "gold", "D": "gold_dark", "L": "gold_light", "G": "gold", "S": "gold_dark"}[pattern[pj][pi]]
            elif not border and (i * 7 + j * 3) % 11 == 0:
                col = "banner_dark"
            z = h - 1 - j
            v.box(i + 2, 0, z, i + 3, 1, z + 1, "paint", col)
    v.box(0, 0, h, w + 4, 2, h + 2, rod, WOOD_T)
    v.box(0, 0, h, 2, 2, h + 2, "gold")
    v.box(w + 2, 0, h, w + 4, 2, h + 2, "gold")
    v.hang(region=(0, 0, 0, w + 4, 2, h))
    return v


def wheel():
    """The ship's-wheel handle of the vault door (6.25 cm voxels): a rim, eight spokes running out past it into
    turned handles, a gold hub. Origin: its centre on its back face (it faces -Y)."""
    n = 34
    c = n / 2.0
    v = Vox(n, 3, n, TX, origin=(c, 3, c), name="wheel")
    for i in range(n):
        for k in range(n):
            dx, dz = i + 0.5 - c, k + 0.5 - c
            d = math.hypot(dx, dz)
            ang = math.degrees(math.atan2(dz, dx)) % 45.0
            on_spoke = min(ang, 45.0 - ang) * math.pi / 180.0 * d < 0.95
            if d < 2.6:
                v.box(i, 0, k, i + 1, 3, k + 1, "gold")
            elif d < 3.6:
                v.box(i, 1, k, i + 1, 3, k + 1, "gold", "#c8a060")
            elif 9.0 <= d < 11.0:
                v.box(i, 1, k, i + 1, 3, k + 1, "beam", "#c89468")
            elif on_spoke and d < 13.0:
                v.box(i, 1, k, i + 1, 3, k + 1, "beam", "#c89468" if d < 11 else "#d8a878")
            elif on_spoke and 13.0 <= d < 15.5:
                v.box(i, 0, k, i + 1, 3, k + 1, "gold", "#f0dcb0")
            if 9.4 <= d < 10.6 and on_spoke:
                v.box(i, 0, k, i + 1, 1, k + 1, "gold")     # gold studs where the spokes cross the rim
    return v


def leaded_window(w=16, rect=24):
    """An arched window of glowing panes in a diamond lattice of lead (6.25 cm voxels), w wide, `rect` tall to the
    springing of its round head. Origin: the middle of its bottom edge (it stands in the XZ plane)."""
    r = w / 2.0
    h = rect + int(r)
    v = Vox(w, 1, h, TX, origin=(w / 2.0, 0.5, 0), name="window")
    for i in range(w):
        for k in range(h):
            dx = i + 0.5 - r
            if k >= rect and math.hypot(dx, k + 0.5 - rect) > r:
                continue
            lead = (i + k) % 5 == 0 or (i - k) % 5 == 0 or i in (0, w - 1) or k == 0
            v.box(i, 0, k, i + 1, 1, k + 1, "metal" if lead else "window", "#3a3430" if lead else None)
    return v


def gold_bars(nx=2, ny=3):
    """Gold bars stacked two layers deep (6.25 cm voxels: a bar is 4 x 2 x 2). Origin: bottom centre."""
    w, d = nx * 5, ny * 3
    v = Vox(w + 1, d + 1, 5, TX, origin=((w + 1) / 2.0, (d + 1) / 2.0, 0), name="bars")
    for i in range(nx):
        for j in range(ny):
            v.box(i * 5 + 1, j * 3 + 1, 0, i * 5 + 5, j * 3 + 3, 2, "gold", "#f0dcb0" if (i + j) % 2 else None)
    for i in range(nx - 1 if nx > 1 else 1):
        for j in range(ny - 1 if ny > 1 else 1):
            ox = 3 if nx > 1 else 1
            v.box(i * 5 + ox, j * 3 + 2, 2, i * 5 + ox + 4, j * 3 + 4, 4, "gold", None if (i + j) % 2 else "#f0dcb0")
    return v


def flowers(seed=1, w=24, d=6):
    """Leaves and flowers spilling out of a flower box (6.25 cm voxels). Origin: bottom centre."""
    rng = np.random.default_rng(seed)
    v = Vox(w, d, 7, TX, origin=(w / 2.0, d / 2.0, 0), name="flowers", seed=seed)
    for i in range(w):
        for j in range(d):
            hgt = int(rng.integers(1, 4))
            v.box(i, j, 0, i + 1, j + 1, hgt, "leaves", "#c8e890" if rng.random() < 0.5 else "#a8d070")
    for _ in range(w // 2):
        i, j = int(rng.integers(0, w)), int(rng.integers(0, d))
        top = 3 + int(rng.integers(0, 2))
        v.box(i, j, 0, i + 1, j + 1, top, "leaves", "#b8e078")
        v.set(i, j, top, "paint", ["flower_white", "flower_yellow", "flower_orange", "flower_pink"][int(rng.integers(0, 4))])
    # a few trailing over the front edge
    for i in range(1, w, 3):
        v.box(i, 0, 0, i + 1, 1, 1, "leaves", "#a8d070")
    return v


# ====================================================================================================== the building

def body(v):
    # walls and a plinth course one voxel proud
    B(v, WX0, WY0, 0, WX1, WY1, EAVE, "brick", WALL_T)
    B(v, WX0 - 1, WY0 - 1, 0, WX1 + 1, WY1 + 1, 4, "stone", STONE_D)
    B(v, WX0 - 1, WY0 - 1, 4, WX1 + 1, WY1 + 1, 5, "stone", STONE_T)
    v.tint("brick", "#c8c2b8", p=0.25, seed=41, cell=4)
    v.tint("brick", "#a8a198", p=0.2, seed=42, cell=4)
    # the timber top plate, one voxel proud all round
    B(v, WX0 - 1, WY0 - 1, PLATE, WX1 + 1, WY1 + 1, EAVE, "beam", WOOD_T)
    B(v, WX0 - 2, WY0 - 2, PLATE + 2, WX1 + 2, WY1 + 2, PLATE + 3, "beam", WOOD_D)     # a moulding along it


def pillar(v, x0, y0, s=8, top=EAVE, cap=6, faces=("-y",), seed=0):
    """A stone pillar s x s (low corner x0, y0), a wider plinth, a gold band and a timber capital with gold plates."""
    B(v, x0 - 1, y0 - 1, 0, x0 + s + 1, y0 + s + 1, 6, "stone", STONE_D)
    B(v, x0 - 1, y0 - 1, 6, x0 + s + 1, y0 + s + 1, 7, "stone", STONE_L)
    B(v, x0, y0, 7, x0 + s, y0 + s, top - cap, "stone", STONE_T)
    for k, z in enumerate(range(7, top - cap, 4)):                       # courses, alternately a shade lighter
        if (k + seed) % 2:
            B(v, x0, y0, z, x0 + s, y0 + s, min(z + 4, top - cap), "stone", STONE_L)
    B(v, x0, y0, top - cap - 8, x0 + s, y0 + s, top - cap - 7, "gold", "#d8c090")     # a brass band
    B(v, x0 - 1, y0 - 1, top - cap, x0 + s + 1, y0 + s + 1, top, "beam", WOOD_T)       # capital
    for f in faces:
        if f == "-y":
            plate(v, x0 + s // 2 - 1, y0 - 1, top - cap + 2, "-y", 3)
        elif f == "+y":
            plate(v, x0 + s // 2 - 1, y0 + s, top - cap + 2, "+y", 3)
        elif f == "-x":
            plate(v, x0 - 1, y0 + s // 2 - 1, top - cap + 2, "-x", 3)
        else:
            plate(v, x0 + s, y0 + s // 2 - 1, top - cap + 2, "+x", 3)


def pillars(v):
    pillar(v, -48, -26, faces=("-y", "-x"), seed=0)
    pillar(v, 40, -26, faces=("-y", "+x"), seed=1)
    pillar(v, -48, 26, faces=("+y", "-x"), seed=1)
    pillar(v, 40, 26, faces=("+y", "+x"), seed=0)
    pillar(v, -18, -27, faces=("-y",), seed=1)                  # between the window bay and the door bay
    pillar(v, -46, 0, s=6, faces=("-x",), seed=0)               # the middle of each side
    pillar(v, 40, 0, s=6, faces=("+x",), seed=1)
    pillar(v, -4, 28, s=6, faces=("+y",), seed=0)               # the middle of the back


def frieze(v, axis, plane, out, a0, a1, z0=21, z1=PLATE, spacing=12):
    """Timber framing one voxel proud of a wall face: a rail at z0, posts every `spacing` voxels and X braces between
    them, up to the top plate. axis 'x' or 'y' (the wall's normal), plane = the wall's outer layer, out = +1 / -1."""
    p = plane + out

    def put(al, ah, zl, zh, mat=("beam", WOOD_T)):
        if axis == "y":
            B(v, al, p, zl, ah, p + 1, zh, *mat)
        else:
            B(v, p, al, zl, p + 1, ah, zh, *mat)

    put(a0, a1, z0, z0 + 2)
    n = max(1, int(round((a1 - a0) / float(spacing))))
    xs = [int(round(a0 + i * (a1 - a0 - 2) / float(n))) for i in range(n + 1)]
    for a in xs:
        put(a, a + 2, z0, z1)
    for i in range(n):
        l, r = xs[i] + 2, xs[i + 1]
        wdt = r - l
        hgt = z1 - (z0 + 2)
        for t in range(wdt):
            zz = z0 + 2 + int(t * hgt / float(wdt))
            put(l + t, l + t + 1, zz, zz + 2, ("beam", WOOD_D))
            put(r - 1 - t, r - t, zz, zz + 2, ("beam", WOOD_D))


def front(v):
    y = WY0                                     # the front face layer is y = WY0 (outward -Y)
    # dark timber posts framing the door bay
    for (a0, a1) in ((-10, -8), (38, 40)):
        B(v, a0, y - 1, 5, a1, y, PLATE, "beam", WOOD_T)
    # gold plates along the top plate
    for x in (-44, -34, -24, 30, 36):
        plate(v, x, y - 1, PLATE + 3, "-y", 2)

    # ---- the window bay: an arched leaded window with a stone surround and a flower box, braces above
    wx = WIN_X
    B(v, wx - 7, y - 1, 6, wx + 7, y, 28, None)                              # (no swollen blocks in front of it)
    B(v, -26, y - 1, 8, -19, y, 25, None)
    for z in range(8, 26):
        for x in range(wx - 4, wx + 4):
            dx = x + 0.5 - wx
            if z < 20 or math.hypot(dx, z + 0.5 - 20) <= 4.0:
                B(v, x, y, z, x + 1, y + 2, z + 1, None)                      # the recess (the pane goes in it)
    ring_xz(v, wx, 20, 4.0, 6.5, y - 2, y, "stone", cond=lambda dx, dz, d: dz >= 0,
            colfn=lambda dx, dz, d: (STONE_T, STONE_L)[int((math.atan2(dz, dx) + 0.01) / (math.pi / 5)) % 2])
    for (a0, a1) in ((wx - 6, wx - 4), (wx + 4, wx + 6)):
        for k, z in enumerate(range(8, 20, 3)):
            B(v, a0, y - 1 - (k % 2), z, a1, y, z + 3, "stone", (STONE_T, STONE_L)[k % 2])
    B(v, wx - 7, y - 2, 6, wx + 7, y, 8, "stone", STONE_L)                   # sill
    B(v, wx - 7, y - 5, 2, wx + 7, y - 1, 6, "plank", WOOD_T)                # flower box under it
    B(v, wx - 7, y - 5, 5, wx + 7, y - 4, 6, "beam", WOOD_D)
    B(v, wx - 7, y - 5, 2, wx + 7, y - 4, 3, "beam", WOOD_D)
    # a narrow window beside it
    nx = -23
    B(v, nx - 2, y, 10, nx + 2, y + 1, 22, "window")
    B(v, nx - 2, y, 16, nx + 2, y + 1, 17, "metal", "#3a3430")
    B(v, nx - 3, y - 1, 10, nx - 2, y, 22, "beam", WOOD_T)
    B(v, nx + 2, y - 1, 10, nx + 3, y, 22, "beam", WOOD_T)
    B(v, nx - 3, y - 1, 22, nx + 3, y, 24, "beam", WOOD_T)
    B(v, nx - 4, y - 2, 8, nx + 4, y, 10, "stone", STONE_L)
    # braces in the upper wall of the bay
    frieze(v, "y", y, -1, -40, -18, z0=26, z1=PLATE, spacing=11)

    # ---- the door bay: the round vault door in a stone arch
    # the recess
    ring_xz(v, DX, DZ, 0, R_RECESS, y, y + 3, None, cond=lambda dx, dz, d: dz > -DZ + SILL)
    # the door: vertical planks, an iron rim, cross bars with gold plates at their ends, gold rivets
    ring_xz(v, DX, DZ, 0, R_DOOR, y + 1, y + 3, "plank",
            colfn=lambda dx, dz, d: (PLANK_T, "#b08458", "#d0a878")[int(math.floor(dx / 2.0)) % 3])
    ring_xz(v, DX, DZ, 8.25, R_DOOR, y, y + 1, "beam", "#a87e58")
    ring_xz(v, DX, DZ, 0, 8.25, y, y + 1, "beam", WOOD_D, cond=lambda dx, dz, d: abs(dx) < 1.0 or abs(dz) < 1.0)
    ring_xz(v, DX, DZ, 0, 8.25, y, y + 1, "beam", WOOD_D,
            cond=lambda dx, dz, d: abs(abs(dx) - abs(dz)) < 0.8 and d > 3.0)
    for (px, pz) in ((DX - 1, DZ + 5.5), (DX - 1, DZ - 7.5), (DX + 5.5, DZ - 1), (DX - 7.5, DZ - 1)):
        B(v, int(px), y - 1, int(pz), int(px) + 2, y, int(pz) + 2, "gold", "#e8d8b0")
    for k in range(12):
        a = math.radians(k * 30 + 15)
        S(v, int(math.floor(DX + 7.0 * math.cos(a))), y, int(math.floor(DZ + 7.0 * math.sin(a))), "gold")
    for k in range(16):
        a = math.radians(k * 22.5)
        S(v, int(math.floor(DX + 8.7 * math.cos(a))), y - 1, int(math.floor(DZ + 8.7 * math.sin(a))), "gold", "#f0dcb0")
    # the stone arch: voussoirs round the top, jambs down to the landing, a gold keystone
    seg = lambda dx, dz, d: (STONE_T, STONE_L, "#c0b8ac")[int((math.atan2(dz, dx) + math.pi) / (math.pi / 9)) % 3]
    ring_xz(v, DX, DZ, R_RECESS, R_ARCH, y - 2, y, "stone", cond=lambda dx, dz, d: dz >= 0, colfn=seg)
    for side in (-1, 1):
        a0 = DX + side * R_RECESS if side > 0 else DX - R_ARCH
        a0 = int(math.ceil(DX + R_RECESS - 0.5)) if side > 0 else int(math.floor(DX - R_ARCH + 0.5))
        a1 = int(math.ceil(DX + R_ARCH - 0.5)) if side > 0 else int(math.floor(DX - R_RECESS + 0.5))
        for k, z in enumerate(range(SILL, int(DZ), 3)):
            B(v, a0, y - 2, z, a1, y, min(z + 3, int(DZ)), "stone", (STONE_T, STONE_L)[k % 2])
        B(v, a0 - (1 if side < 0 else 0), y - 3, SILL, a1 + (1 if side > 0 else 0), y, SILL + 2, "stone", STONE_D)
    B(v, DX - 2, y - 3, int(DZ + R_ARCH) - 4, DX + 2, y, int(DZ + R_ARCH), "gold", "#e8d0a0")      # keystone
    B(v, DX - 1, y - 4, int(DZ + R_ARCH) - 3, DX + 1, y - 3, int(DZ + R_ARCH) - 1, "gold")
    # the hinge: an iron barrel on the left with two straps across the door
    hx = int(math.floor(DX - R_DOOR)) - 2
    B(v, hx, y - 4, int(DZ) - 8, hx + 3, y, int(DZ) + 8, "metal", IRON)
    B(v, hx, y - 4, int(DZ) - 9, hx + 3, y, int(DZ) - 8, "gold")
    B(v, hx, y - 4, int(DZ) + 8, hx + 3, y, int(DZ) + 9, "gold")
    for zz in (int(DZ) - 6, int(DZ) + 4):
        B(v, hx + 3, y - 2, zz, DX - 2, y, zz + 2, "metal", IRON)
        S(v, hx + 1, y - 5, zz + 1, "gold")
        S(v, DX - 4, y - 3, zz, "gold")

    # ---- the crest panel above the arch, in the gable (flush with the front of the gable's roof)
    B(v, 3, GY0 - 2, 27, 25, y, 44, "beam", WOOD_T)                          # frame
    B(v, 5, GY0 - 2, 29, 23, GY0 - 1, 42, None)
    B(v, 5, GY0 - 1, 29, 23, GY0, 42, "plank", "#6a4a32")                    # dark panel
    for (cx, cz) in ((2, 26), (22, 26), (2, 40), (22, 40)):
        B(v, cx, GY0 - 3, cz, cx + 4, GY0 - 1, cz + 4, "gold", "#e8d8b0")    # gold corner blocks
        S(v, cx + 1, GY0 - 4, cz + 1, "gold")
        S(v, cx + 2, GY0 - 4, cz + 2, "gold")


def gable_wall(v):
    """The triangle of timber boards under the cross gable (set back behind the roof's overhang)."""
    run, rise = 6, 4
    for i in range(6):
        l, r = GX0 + (i + 1) * run, GX1 - (i + 1) * run
        if r <= l:
            break
        B(v, l, GY0, EAVE + i * rise, r, WY0 + 4, EAVE + (i + 1) * rise, "plank", "#c49a70")
        # vertical battens
        for x in range(l + 2, r - 1, 6):
            B(v, x, GY0 - 1, EAVE + i * rise, x + 2, GY0, EAVE + (i + 1) * rise, "beam", WOOD_D)


def side_and_back(v):
    # sides: two framed windows each, the frieze; a hanging lantern by the east one
    for (plane, out, sgn) in ((OX + WX0, -1, -1), (OX + WX1 - 1, 1, 1)):
        for ya in (-16, 14):
            B(v, WX0 - 1 if sgn < 0 else WX1, ya - 2, 9, WX0 if sgn < 0 else WX1 + 1, ya + 8, 22, None)
            K.window(v, "x", plane, OY + ya, 11, w=6, h=9, out=out, frame="beam")
        frieze(v, "x", WX0 if sgn < 0 else WX1 - 1, out, -18, 26, z0=24, z1=PLATE, spacing=11)
        for yy in (-24, -4, 12, 24):
            plate(v, (WX0 - 1) if sgn < 0 else (WX1), yy, PLATE + 3, "-x" if sgn < 0 else "+x", 2)
    # back: three windows, the frieze
    for xa in (-34, -18, 10, 26):
        B(v, xa - 2, WY1, 9, xa + 8, WY1 + 1, 22, None)
        K.window(v, "y", OY + WY1 - 1, OX + xa, 11, w=6, h=9, out=1, frame="beam")
    frieze(v, "y", WY1 - 1, 1, -40, -4, z0=24, z1=PLATE, spacing=12)
    frieze(v, "y", WY1 - 1, 1, 2, 40, z0=24, z1=PLATE, spacing=12)
    for x in (-40, -20, 14, 34):
        plate(v, x, WY1, PLATE + 3, "+y", 2)


def roofs(v, c):
    run, rise = 6, 4
    # the hip roof over the whole block
    x0, x1, y0, y1 = WX0 - 6, WX1 + 6, WY0 - 2, WY1 + 2
    i = 0
    while x1 - x0 - 2 * i * run > 0 and y1 - y0 - 2 * i * run > 0:
        C(c, x0 + i * run, y0 + i * run, EAVE + i * rise, x1 - i * run, y1 - i * run, EAVE + (i + 1) * rise, "roof")
        i += 1
    top = EAVE + i * rise
    ymid = (y0 + y1) // 2
    # the cross gable over the door bay, its ridge running back to the main ridge
    gy0 = GY0
    for k in range(6):
        l, r = GX0 + k * run, GX1 - k * run
        if r <= l:
            break
        C(c, l, gy0, EAVE + k * rise, r, ymid, EAVE + (k + 1) * rise, "roof")
        il, ir = GX0 + (k + 1) * run, GX1 - (k + 1) * run
        if ir > il:
            C(c, il, gy0, EAVE + k * rise, ir, gy0 + 2, EAVE + (k + 1) * rise, None)   # open under the overhang
    c.tint("roof", "#9cb088", p=1.0, seed=5)
    c.tint("roof", "#b8cc98", p=0.18, seed=6)
    c.tint("roof", "#7e966a", p=0.2, seed=8)
    c.scatter("roof", "moss", p=0.03, seed=4, direction="+z")

    # ridge beams
    B(v, -26 - 1, ymid - 2, top, 26 + 1, ymid + 2, top + 2, "beam", WOOD_T)
    B(v, (GX0 + GX1) // 2 - 2, gy0 - 1, top, (GX0 + GX1) // 2 + 2, ymid, top + 2, "beam", WOOD_T)
    # stepped timber along the four hips, a gold cap on each step's corner
    for k in range(i):
        for (sx, sy) in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            cx = (x0 + k * run) if sx < 0 else (x1 - k * run)
            cy = (y0 + k * run) if sy < 0 else (y1 - k * run)
            if sy < 0 and GX0 - 2 <= cx <= GX1 + 2:
                continue                                             # (under the cross gable)
            xa, xb = (cx - 1, cx + 2) if sx < 0 else (cx - 2, cx + 1)
            ya, yb = (cy - 1, cy + 2) if sy < 0 else (cy - 2, cy + 1)
            ca, cb = (cx, cx + 2) if sx < 0 else (cx - 2, cx)
            da, db = (cy, cy + 2) if sy < 0 else (cy - 2, cy)
            C(c, ca, da, EAVE + k * rise, cb, db, EAVE + (k + 1) * rise, None)        # (no tile inside the timber)
            B(v, xa, ya, EAVE + k * rise, xb, yb, EAVE + (k + 1) * rise, "beam", (WOOD_T, "#d4b088")[k % 2])
            if k == 0:
                B(v, xa, ya, EAVE - 2, xb, yb, EAVE + rise + 2, "beam", WOOD_T)
                plate(v, xa + 1 if sx < 0 else xa, ya if sy < 0 else yb - 1, EAVE, "-y" if sy < 0 else "+y", 2)
    # the barge boards of the cross gable: one chunky block per step, gold plates on the eave and ridge blocks
    for k in range(6):
        l, r = GX0 + k * run, GX1 - k * run
        if r <= l:
            break
        zl = EAVE + k * rise
        col = (WOOD_T, "#c09a74")[k % 2]
        B(v, l - 2, gy0 - 2, zl, l + run, gy0 + 3, zl + rise + 2, "beam", col)
        B(v, r - run, gy0 - 2, zl, r + 2, gy0 + 3, zl + rise + 2, "beam", col)
    gm = (GX0 + GX1) // 2
    B(v, gm - 4, gy0 - 3, top - 2, gm + 4, gy0 + 3, top + 4, "beam", WOOD_T)                   # the apex block
    plate(v, gm - 1, gy0 - 3, top, "-y", 3)
    for (a0, a1) in ((GX0 - 4, GX0 + 4), (GX1 - 4, GX1 + 4)):
        B(v, a0, gy0 - 3, EAVE - 6, a1, gy0 + 4, EAVE + 4, "beam", WOOD_T)                     # the eave blocks
        plate(v, a0 + 2, gy0 - 3, EAVE - 3, "-y", 4)
    return top


def cupola(v, top):
    """A small lit lantern cupola on the main ridge."""
    cx, cy, h = -8, 4, 6
    z0 = top
    B(v, cx - h - 1, cy - h - 1, z0, cx + h + 1, cy + h + 1, z0 + 2, "beam", WOOD_T)
    B(v, cx - h, cy - h, z0 + 2, cx + h, cy + h, z0 + 8, "plank", "#9a7454")
    zw = z0 + 3
    for k in range(2):
        a = cx - h + 2 + k * 5
        B(v, a, cy - h - 1, zw, a + 3, cy - h, zw + 4, "window")
        B(v, a, cy + h, zw, a + 3, cy + h + 1, zw + 4, "window")
        b = cy - h + 2 + k * 5
        B(v, cx - h - 1, b, zw, cx - h, b + 3, zw + 4, "window")
        B(v, cx + h, b, zw, cx + h + 1, b + 3, zw + 4, "window")
    for (px, py) in ((cx - h - 1, cy - h - 1), (cx + h - 1, cy - h - 1), (cx - h - 1, cy + h - 1), (cx + h - 1, cy + h - 1)):
        B(v, px, py, z0 + 2, px + 2, py + 2, z0 + 8, "beam", WOOD_T)
    B(v, cx - h - 1, cy - h - 1, z0 + 8, cx + h + 1, cy + h + 1, z0 + 9, "beam", WOOD_T)
    for (px, py) in ((cx - h - 2, cy - h - 2), (cx + h, cy - h - 2), (cx - h - 2, cy + h), (cx + h, cy + h)):
        B(v, px, py, z0 + 8, px + 2, py + 2, z0 + 10, "gold", "#e8d8b0")
    # its roof: four tile steps, a gold finial
    z = z0 + 9
    for k, rz in enumerate((2, 2, 1, 1)):
        e = h + 2 - 2 * k
        B(v, cx - e, cy - e, z, cx + e, cy + e, z + rz, "roof", "#8ea67a" if k % 2 else "#a4b88c")
        z += rz
    B(v, cx - 1, cy - 1, z, cx + 1, cy + 1, z + 2, "gold")
    S(v, cx, cy, z + 2, "gold")


def steps(v):
    """Stone steps up to the door with a green runner edged in gold, cheek walls, a landing."""
    sx0, sx1 = DX - 10, DX + 10
    B(v, sx0 - 2, WY0 - 5, 0, sx1 + 2, WY0, SILL, "stone", STONE_T)                  # landing
    for k in range(3):
        B(v, sx0, WY0 - 14 + 3 * k, 0, sx1, WY0 - 5, (k + 1) * 2, "stone", (STONE_L, STONE_T, STONE_L)[k])
    for (a0, a1) in ((sx0 - 2, sx0), (sx1, sx1 + 2)):                                # cheek walls
        for k in range(3):
            B(v, a0, WY0 - 14 + 3 * k, 0, a1, WY0 - 5, (k + 1) * 2 + 2, "stone", (STONE_L, STONE_T)[k % 2])
    # the runner: paint the top and the risers of the middle of each step and of the landing
    def height(y):
        for z in range(NZ - 1, -1, -1):
            if v.get(OX + DX, OY + y, z) == "stone":
                return z + 1
        return 0
    hs = {y: height(y) for y in range(WY0 - 15, WY0)}
    for y in range(WY0 - 14, WY0):
        h = hs[y]
        lo = hs[y - 1]
        for x in range(DX - 6, DX + 6):
            edge = x in (DX - 6, DX + 5)
            col = ("gold", "#e8c880") if edge else ("paint", RUNNER)
            for z in range(min(lo, h - 1), h):
                S(v, x, y, z, *col)


def lantern_post(v, x, y):
    """A stone post at the foot of the steps with a glowing lantern under a little roof. (x, y): its middle."""
    B(v, x - 4, y - 4, 0, x + 4, y + 4, 2, "stone", STONE_D)
    B(v, x - 3, y - 3, 2, x + 3, y + 3, 6, "stone", STONE_T)
    B(v, x - 4, y - 4, 6, x + 4, y + 4, 7, "stone", STONE_L)
    B(v, x - 3, y - 3, 7, x + 3, y + 3, 8, "beam", WOOD_D)
    B(v, x - 2, y - 2, 8, x + 2, y + 2, 12, "glow", "lantern")
    for dx in (x - 3, x + 2):
        for dy in (y - 3, y + 2):
            B(v, dx, dy, 8, dx + 1, dy + 1, 12, "beam", WOOD_D)
    B(v, x - 4, y - 4, 12, x + 4, y + 4, 13, "beam", WOOD_T)
    B(v, x - 3, y - 3, 13, x + 3, y + 3, 14, "beam", WOOD_T)
    B(v, x - 2, y - 2, 14, x + 2, y + 2, 15, "beam", WOOD_T)
    B(v, x - 1, y - 1, 15, x + 1, y + 1, 17, "gold")


def hang_lantern(v, x, y, z):
    """A lantern on an iron bracket off the front wall; (x, y, z): the wall voxel the bracket leaves from."""
    for k in range(1, 5):
        S(v, x, y - k, z, "metal", IRON)
    S(v, x, y - 1, z - 1, "metal", IRON)
    S(v, x, y - 4, z - 1, "metal", IRON)
    cx, cy = x, y - 4
    B(v, cx - 2, cy - 2, z - 8, cx + 3, cy + 3, z - 7, "beam", WOOD_D)
    B(v, cx - 2, cy - 2, z - 7, cx + 3, cy + 3, z - 2, "glow", "lantern")
    for dx in (cx - 2, cx + 2):
        for dy in (cy - 2, cy + 2):
            B(v, dx, dy, z - 7, dx + 1, dy + 1, z - 2, "beam", WOOD_D)
    B(v, cx - 2, cy - 2, z - 2, cx + 3, cy + 3, z - 1, "beam", WOOD_T)
    S(v, cx, cy, z - 9, "gold")


def crate(size=6, h=5, name="crate"):
    v = Vox(size + 1, size, h, VX, origin=((size + 1) / 2.0, size / 2.0, 0), name=name)
    v.box(0, 0, 0, size + 1, size, h, "plank", PLANK_T)
    v.frame(0, 0, 0, size + 1, size, h, "beam", WOOD_D)
    v.box(1, 1, h - 1, size, size - 1, h, "plank", "#4a3424")                      # open: dark inside
    return v


def build():
    v = Vox(NX, NY, NZ, VX, origin=(OX, OY, 0), name="vault", seed=31)
    c = Vox(NX // 2, NY // 2, NZ // 2, 2 * VX, origin=(OX // 2, OY // 2, 0), name="roof", seed=32)
    body(v)
    # swollen blocks on the walls (the front only in the window bay), then on the pillars, before the details
    for reg in ((0, 0, 0, OX + WX0 + 1, NY, PLATE), (OX + WX1 - 1, 0, 0, NX, NY, PLATE), (0, OY + WY1 - 1, 0, NX, NY, PLATE),
                (OX - 40, 0, 0, OX - 18, OY + WY0 + 1, PLATE)):
        v.chunky("brick", cell=4, depth=1, p=0.07, seed=5, region=reg)
    pillars(v)
    v.chunky("stone", cell=4, depth=1, p=0.1, seed=6, region=(0, 0, 7, NX, NY, 28))
    side_and_back(v)
    front(v)
    top = roofs(v, c)
    gable_wall(v)
    cupola(v, top)
    steps(v)
    lantern_post(v, DX - 15, WY0 - 10)
    lantern_post(v, DX + 15, WY0 - 10)
    hang_lantern(v, DX - 14, WY0, 28)
    hang_lantern(v, DX + 14, WY0, 28)
    v.scatter("stone", "mossy_stone", p=0.05, seed=7, direction="+z")
    v.scatter("brick", "mossy_stone", p=0.004, seed=8)

    parts = [v, c]
    m = lambda q: q * VX
    # pixel-art pieces
    parts.append(leaded_window().at(m(WIN_X), m(WY0 + 2) - TX * 0.5, m(8)))
    parts.append(wheel().at(m(DX), m(WY0), m(DZ)))
    parts.append(crest().at(m(DX), m(GY0 - 1), m(29)))
    parts.append(flowers(seed=2, w=26, d=5).at(m(WIN_X), m(WY0 - 3.5), m(6)))
    parts.append(banner(name="bannerL").at(m(-6), m(WY0 - 2) - TX, m(PLATE - 1)))
    parts.append(banner(name="bannerR").at(m(35), m(WY0 - 2) - TX, m(PLATE - 1)))
    for bx in (-6, 35):                                                          # brackets for the rods
        for dx in (-4, 3):
            B(v, bx + dx, WY0 - 3, PLATE - 2, bx + dx + 1, WY0, PLATE - 1, "metal", IRON)
    # props round the foot: crates of gold bars, a barrel
    props = [(-40, -31, 7), (-32, -32, 6), (41, -32, 6)]
    for k, (px, py, s) in enumerate(props):
        parts.append(crate(s, 5).at(m(px), m(py), 0.0))
        parts.append(gold_bars(2, 2 if s < 7 else 3).at(m(px), m(py), m(5)))
    parts.append(K.barrel().at(m(-24), m(-30), 0.0))
    for p in parts:
        p.offset = (p.offset[0], p.offset[1] + SHIFT_Y, p.offset[2])
    ob = V.join(parts, NAME)
    drop_bottom(ob, zs=(0.0,))
    return ob


# ====================================================================================================== main

def render(path, target=(0, 0, 1.5), az=28.0, el=32.0, dist=22.0, lens=85.0, res=(1280, 800), samples=32,
           sun_az=-60.0, sun_el=32.0):
    """voxlib.render, with a choice of CPU (Cycles on Metal can crash while other jobs render)."""
    import bpy
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
    preview("front", target=(0.6, 0, 3.4), az=-6, el=8, dist=34, lens=50, res=(1280, 860), sun_az=-150, sun_el=30)
    preview("three", target=(0.3, 0, 3.0), az=32, el=30, dist=38, lens=50, res=(1280, 860), sun_az=-125, sun_el=30)
    preview("door", target=(1.6, -3.5, 2.6), az=-4, el=6, dist=14, lens=50, res=(1280, 860), sun_az=-150, sun_el=30)
    preview("back", target=(0, 0, 3.0), az=200, el=28, dist=38, lens=50, res=(1280, 860))
    preview("ref", target=(0.6, 0, 3.0), az=-14, el=14, dist=30, lens=50, res=(1536, 1024), sun_az=-120, sun_el=24)


if __name__ == "__main__":
    main()
