"""granary: the food storehouse (EVLBuilding::Granary) of the voxel village, after References/Remake/granary.png.

  SM_Granary   a thatched timber-and-stone storehouse: a steep golden thatch gable roof (ridge front to back) with a
               small louvred, thatched vent cupola; grey block walls on a chunky stone base, heavy timber framing with
               iron brackets, stone piers at the corners. The front gable: a stone-arched open doorway with sacks,
               barrels and a shovel inside (lit by a lantern), stone steps up to it; a big green banner with a gold
               wheat emblem in the gable, two smaller ones on the piers either side of the door and two iron lanterns.
               On the left a thatched lean-to with a green striped awning, sheltering sacks, crates and barrels; round
               the foot a hand cart full of wheat, wheat sheaves, a big grain sack with a wheat emblem, crates, a
               barrel and loose straw. All the clutter stays inside the footprint.

Pivot: the middle of the footprint at ground level (z = 0); the door faces -Y. One mesh; the banners and the awning
are cloth (they sway in game and take the enemy's colour). About 13 x 10.5 m, 9.75 m to the top of the cupola.

Run:  Blender -b --factory-startup --python Tools/blender/assets/granary.py -- [--no-render] [--views=a,b] [--samples N] [--cpu]
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
TASK = "granary"
NAME = "SM_Granary"

VX = 0.125
TX = V.TEXEL
NX, NY, NZ = 120, 96, 84             # 15 x 12 x 10.5 m
OX, OY = 60, 48                      # the voxel that becomes (0, 0) before the model is centred on its footprint

# colours
WALL_T = "#bdb6ab"                   # the grey block walls
STONE_T = "#cfc8bc"                  # piers, base, arch, steps
STONE_L = "#e2dbcf"
STONE_D = "#aaa298"
WOOD_T = "#f0c090"                   # the timber (orange-brown)
WOOD_D = "#d49c68"
WOOD_L = "#ffd4a4"
IRON = "#5e5c64"                     # iron brackets and lantern cages (painted: the metal texture reads black)
STUD = "#a4a8b0"                     # bolt heads
THATCH = ["#ffffff", "#f8f0e0", "#f0e4cc", "#fff8ec", "#ece0c4"]
ROWS = ["#b89868", "#d8bc8c", "#f0dcb4", "#ffffff"]       # a thatch course from its underside to its top
SACKS = ["#d8b47a", "#c9a46a", "#e2c088", "#bf975c"]
ROPE = "#7a5028"

# plan (voxels of 12.5 cm, relative to the pivot before centring)
HX0, HX1 = -16, 44                   # the hall's walls (7.5 m)
WY0, WY1 = -22, 34                   # its front face .. back face (7 m)
BASE = 12                            # top of the stone base course
PLATE = 32                           # bottom of the timber top plate
EAVE = 36                            # top of the walls
SILL = 4                             # the floor of the doorway
DX = (HX0 + HX1) // 2                # the doorway's middle (14)
DZ = 18                              # where its round head springs
R_OPEN, R_ARCH = 9.0, 13.0
RX0, RX1 = HX0 - 6, HX1 + 6          # the main roof (ridge along Y)
RY0, RY1 = WY0 - 5, WY1 + 4
RUN, RISE, THICK = 4, 3, 4
LX0 = -48                            # the lean-to's outer posts
LY0 = WY0 - 3                        # its front beam
DEPTH = 16                           # how deep the doorway goes into the hall


def B(v, x0, y0, z0, x1, y1, z1, mat, color=None):
    v.box(OX + x0, OY + y0, z0, OX + x1, OY + y1, z1, mat, color)


def S(v, x, y, z, mat, color=None):
    v.set(OX + x, OY + y, z, mat, color)


def G(v, x, y, z):
    return v.get(OX + x, OY + y, z)


def ring_xz(v, cx, cz, r0, r1, y0, y1, mat, color=None, cond=None, colfn=None):
    """Voxels whose centre lies r0 <= d < r1 from (cx, cz) in the front (XZ) plane, from y0 to y1."""
    for x in range(int(math.floor(cx - r1)) - 1, int(math.ceil(cx + r1)) + 1):
        for z in range(max(0, int(math.floor(cz - r1)) - 1), int(math.ceil(cz + r1)) + 1):
            dx, dz = x + 0.5 - cx, z + 0.5 - cz
            d = math.hypot(dx, dz)
            if r0 <= d < r1 and (cond is None or cond(dx, dz, d)):
                B(v, x, y0, z, x + 1, y1, z + 1, mat, colfn(dx, dz, d) if colfn else color)


def bracket(v, x, y, z, face="-y", n=2):
    """An iron plate n x n voxels one voxel proud of a face with a bright bolt in it; (x, y, z) its low corner on the
    face layer."""
    if face == "-y":
        B(v, x, y - 1, z, x + n, y, z + n, "paint", IRON)
        if n >= 2:
            S(v, x + (n - 1) // 2, y - 2, z + (n - 1) // 2, "paint", STUD)
    elif face == "+y":
        B(v, x, y + 1, z, x + n, y + 2, z + n, "paint", IRON)
        if n >= 2:
            S(v, x + (n - 1) // 2, y + 2, z + (n - 1) // 2, "paint", STUD)
    elif face == "-x":
        B(v, x - 1, y, z, x, y + n, z + n, "paint", IRON)
        if n >= 2:
            S(v, x - 2, y + (n - 1) // 2, z + (n - 1) // 2, "paint", STUD)
    elif face == "+x":
        B(v, x + 1, y, z, x + 2, y + n, z + n, "paint", IRON)
        if n >= 2:
            S(v, x + 2, y + (n - 1) // 2, z + (n - 1) // 2, "paint", STUD)


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


def centre(ob, step=0.0625):
    """Move the mesh (and its lamp positions) so that the middle of its footprint is the pivot."""
    import json
    me = ob.data
    co = np.zeros(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    mid = (co.min(axis=0) + co.max(axis=0)) * 0.5
    sx, sy = -round(float(mid[0]) / step) * step, -round(float(mid[1]) / step) * step
    co[:, 0] += sx
    co[:, 1] += sy
    me.vertices.foreach_set("co", co.reshape(-1))
    me.update()
    lights = json.loads(ob.get("lights", "[]"))
    ob["lights"] = json.dumps([[round(l[0] + sx, 4), round(l[1] + sy, 4), l[2], l[3]] for l in lights])
    print("centred by (%.4f, %.4f)" % (sx, sy))
    return sx, sy


# ====================================================================================================== pixel-art pieces

def wheat_emblem(w=11, h=15, spread=26.0, ear=6):
    """A sheaf of three wheat ears fanning from a bound stem (a char grid, top row first): 'T' grain, 'L' its lit side,
    'S' stalk, 'B' the band round them."""
    g = [["." for _ in range(w)] for _ in range(h)]

    def put(x, row, ch, over=True):
        if 0 <= x < w and 0 <= row < h and (over or g[row][x] == "."):
            g[row][x] = ch

    cx = (w - 1) / 2.0
    base = h - 1
    band = int(round(h * 0.62))
    for a in (-spread, 0.0, spread):
        t = math.radians(a)
        dx, dy = math.sin(t), math.cos(t)
        n = h - 1 if a == 0 else h - 2
        for k in range(n):
            # stalks straight up from the foot to the band, then fanning out
            if base - k > band:
                put(int(round(cx + (a / spread if spread else 0) * 0.0)), base - k, "S")
                continue
            kk = k - (base - band)
            x = cx + dx * kk * 1.05
            row = band - dy * kk
            xi, ri = int(round(x)), int(round(row))
            if kk < 2:
                put(xi, ri, "S")
            else:
                put(xi, ri, "T")
                if kk % 2 == 0 and kk < n - (base - band) - 1:
                    put(xi - 1, ri, "L" if a <= 0 else "T", over=False)
                    put(xi + 1, ri, "T" if a <= 0 else "L", over=False)
    for x in range(int(cx) - 1, int(cx) + 2):
        put(x, band + 1, "B")
    return ["".join(r) for r in g]


def banner(w=12, h=22, tip=4, shape="point", name="banner", field="banner", edge="gold", emblem=None, ey0=3):
    """A hanging banner with a wheat emblem, a gold border and fringe, on a wooden rod with iron ends (6.25 cm voxels).
    shape 'point': its foot runs to a point; 'flat': a straight foot. Origin: the middle of the top of the rod; it faces
    -Y and the cloth sways."""
    pattern = emblem or wheat_emblem()
    ew = max(len(r) for r in pattern)
    ex0 = (w - ew) // 2
    inside = np.zeros((h, w), bool)
    for j in range(h):
        for i in range(w):
            k = j - (h - tip)
            cut = shape == "point" and k >= 0 and abs(i + 0.5 - w / 2.0) > (w / 2.0) * (1.0 - (k + 1) / float(tip + 1))
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
                col = {"T": "gold", "L": "gold_light", "S": "gold_dark", "B": "gold_light"}[pattern[pj][pi]]
            elif not border and (i * 7 + j * 3) % 11 == 0:
                col = "banner_dark"
            z = h - 1 - j
            v.box(i + 2, 0, z, i + 3, 1, z + 1, "paint", col)
            if border and j == h - 1 and shape == "flat" and i % 2 == 0:
                v.box(i + 2, 0, z - 1, i + 3, 1, z, "paint", "gold_dark")          # a fringe
    v.box(0, 0, h, w + 4, 2, h + 2, "beam", WOOD_T)
    v.box(0, 0, h, 2, 2, h + 2, "paint", IRON)
    v.box(w + 2, 0, h, w + 4, 2, h + 2, "paint", IRON)
    v.hang(region=(0, 0, 0, w + 4, 2, h))
    return v


def awning(w=64, out=16, drop=6, name="awning"):
    """The lean-to's striped green awning (6.25 cm voxels): a cloth sloping down and out from a beam, green and dark
    green stripes, a scalloped gold-edged valance along its foot. It runs along X; its top edge is at y = 0, it reaches
    `out` voxels towards -Y and falls `drop` on the way, then the valance hangs 3 more. Origin: the middle of its top
    edge; it sways (most at the foot)."""
    v = Vox(w, out + 1, drop + 6, TX, origin=(w / 2.0, out + 1, drop + 6), name=name)
    top = drop + 5
    for j in range(out + 1):
        z = top - int(round(j * drop / float(out)))
        y = out - j
        for i in range(w):
            stripe = (i // 6) % 2
            col = "banner" if stripe == 0 else "banner_dark"
            if i in (0, w - 1):
                col = "gold_dark"
            v.box(i, y, z, i + 1, y + 1, z + 1, "paint", col)
    # the valance: a hanging strip with a scalloped foot and a gold edge
    zt = top - drop
    for i in range(w):
        k = i % 6
        depth = 3 if k in (1, 2, 3, 4) else 2
        for d in range(depth):
            col = ("banner" if (i // 6) % 2 == 0 else "banner_dark") if d < depth - 1 else "gold"
            v.box(i, 0, zt - 1 - d, i + 1, 1, zt - d, "paint", col)
    v.hang()
    return v


def lantern(v, x, y, z, out="-y"):
    """An iron lantern on a bracket off a wall; (x, y, z) is the wall voxel the bracket leaves from (outward -Y or -X)."""
    sx, sy = (0, -1) if out == "-y" else (-1, 0)
    for k in range(1, 5):
        S(v, x + sx * k, y + sy * k, z, "paint", IRON)
    S(v, x + sx * 1, y + sy * 1, z - 1, "paint", IRON)
    S(v, x + sx * 1, y + sy * 1, z - 2, "paint", IRON)
    cx, cy = x + sx * 4, y + sy * 4
    B(v, cx - 2, cy - 2, z - 8, cx + 3, cy + 3, z - 7, "paint", IRON)
    B(v, cx - 2, cy - 2, z - 7, cx + 3, cy + 3, z - 2, "glow", "lantern")
    for dx in (cx - 2, cx + 2):
        for dy in (cy - 2, cy + 2):
            B(v, dx, dy, z - 7, dx + 1, dy + 1, z - 2, "paint", IRON)
    B(v, cx - 2, cy - 2, z - 2, cx + 3, cy + 3, z - 1, "paint", IRON)
    B(v, cx - 1, cy - 1, z - 1, cx + 2, cy + 2, z, "paint", IRON)
    S(v, cx, cy, z - 9, "paint", IRON)


# ---------------------------------------------------------------------------------------------------- fine clutter
# (copied from props.py and changed: barrels, crates and sacks on the 6.25 cm grid)

BARREL_R = [5.0, 5.4, 5.7, 5.9, 6.0, 6.0, 6.0, 6.0, 6.0, 6.0, 5.9, 5.7, 5.4, 5.4]
PWOOD = ["#ffffff", "#f0dcc0", "#e2c8a6", "#f6e8d2", "#d8bc98"]


def fine(nx, ny, nz, name, seed=0):
    """A grid of 6.25 cm voxels whose origin is the middle of its floor."""
    return Vox(nx, ny, nz, TX, origin=(nx / 2.0, ny / 2.0, 0), name=name, seed=seed)


def barrel(v, cx, cy, z0, seed=0, full=None):
    """A barrel 75 cm across, 87.5 cm tall: staves, two iron hoops, a sunk lid (or a heap of grain: full='wheat')."""
    X, Y, Z = v.grid()
    d2 = (X + 0.5 - cx) ** 2 + (Y + 0.5 - cy) ** 2
    ang = np.arctan2(Y + 0.5 - cy, X + 0.5 - cx)
    stave = np.floor((ang + np.pi) / (2 * np.pi) * 14 + 0.5).astype(int) % 14
    r = np.random.default_rng(seed + 40)
    cols = np.array([V.rgb(c) for c in PWOOD])[r.integers(0, len(PWOOD), 14)][stave]
    for k, rad in enumerate(BARREL_R):
        layer = (Z == z0 + k) & (d2 <= rad * rad)
        v.m[layer] = V.IDS["plank"]
        v.c[layer] = cols[layer]
        if k in (2, 11):
            v.where((Z == z0 + k) & (d2 <= (rad + 0.75) ** 2) & (d2 > (rad - 1.3) ** 2), "metal", "#8a8890")
    top = z0 + len(BARREL_R) - 1
    v.where((Z == top) & (d2 <= 12.5), None)
    if full:
        v.where((Z == top) & (d2 <= 12.5), "wheat", "#fff0c0")
        v.where((Z == top + 1) & (d2 <= 6.5), "wheat", "#fff6d8")
    else:
        v.where((Z == top - 1) & (d2 <= 12.5), "plank", "#e2c8a6")
    return v


def crate(v, x0, y0, z0, s=10, seed=0, flip=False, h=None):
    """A crate: a frame of dark battens, sunk board panels, a diagonal brace on each side, iron corners."""
    h = h or s
    x1, y1, z1 = x0 + s, y0 + s, z0 + h
    v.box(x0 + 1, y0 + 1, z0, x1 - 1, y1 - 1, z1 - 1, "plank")
    gx, gy = np.meshgrid(np.arange(x0 + 1, x1 - 1), np.arange(y0 + 1, y1 - 1), indexing="ij")
    k = ((gx - x0) // 2 * 3 + (gy - y0) // 2 * 5 + seed) % len(PWOOD)
    v.c[x0 + 1:x1 - 1, y0 + 1:y1 - 1, z0:z1 - 1] = np.array([V.rgb(c) for c in PWOOD])[k][:, :, None, :]
    v.frame(x0, y0, z0, x1, y1, z1, "beam", "#c89060", t=2)
    for i in range(2, min(s, h) - 2):
        zi = z0 + ((h - 1 - i) if flip else i)
        if not (z0 + 2 <= zi < z1 - 2):
            continue
        xi = x0 + int(round(i * (s - 1) / float(h - 1)))
        v.set(xi, y0, zi, "beam", "#c89060")
        v.set(x1 - 1 - (xi - x0), y1 - 1, zi, "beam", "#c89060")
    for xx in (x0, x1 - 1):
        for yy in (y0, y1 - 1):
            for zz in (z0, z1 - 1):
                v.set(xx, yy, zz, "paint", IRON)
    return v


def blob(v, cx, cy, cz, rx, ry, rz, mat, color, n=2.6, zmin=None):
    """A plump rounded box (a pillow): between an ellipsoid (n = 2) and a box (large n)."""
    X, Y, Z = v.grid()
    m = (np.abs((X + 0.5 - cx) / rx) ** n + np.abs((Y + 0.5 - cy) / ry) ** n + np.abs((Z + 0.5 - cz) / rz) ** n) <= 1.0
    if zmin is not None:
        m &= Z >= zmin
    return v.where(m, mat, color)


def sack(v, cx, cy, z0, rx=4.5, ry=4.0, color=SACKS[0], open_top=False, tall=5.2):
    """A standing grain sack: a plump body, a rope round the neck and the gathered top (or an open mouth of grain)."""
    blob(v, cx, cy, z0 + tall * 0.77, rx, ry, tall, "wool", color, zmin=z0)
    zt = z0 + int(round(tall * 1.73))
    ix, iy = int(cx), int(cy)
    if open_top:
        v.box(ix - 3, iy - 3, zt - 1, ix + 3, iy + 3, zt + 1, "wool", color)
        v.box(ix - 2, iy - 2, zt - 1, ix + 2, iy + 2, zt + 1, "wheat", "#ffe9a0")
        v.box(ix - 1, iy - 1, zt + 1, ix + 1, iy + 1, zt + 2, "wheat", "#ffe9a0")
    else:
        v.box(ix - 2, iy - 2, zt - 1, ix + 2, iy + 2, zt, "wool", color)
        v.box(ix - 2, iy - 2, zt, ix + 2, iy + 2, zt + 1, "paint", ROPE)
        v.box(ix - 3, iy - 2, zt + 1, ix + 3, iy + 2, zt + 2, "wool", color)
        v.box(ix - 2, iy - 1, zt + 2, ix + 2, iy + 1, zt + 3, "wool", color)
    return v


def sack_lying(v, cx, cy, z0, axis="x", color=SACKS[1], length=6.5, fat=4.2, end=1):
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


def emblem_on(v, rows, x0, z0, ymax, color="#7a4a22"):
    """Paint a char grid (top row first) onto the front (-Y) surface of whatever is in the grid, from column x0 and
    row z0 (the bottom of the pattern)."""
    h = len(rows)
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch == ".":
                continue
            x, z = x0 + i, z0 + (h - 1 - j)
            for y in range(0, ymax):
                if v.m[x, y, z]:
                    v.c[x, y, z] = V.rgb(color if ch != "L" else "#9a6a32")
                    break


def sheaf(v, cx, cy, z0, h=14, r=2.6, seed=0):
    """A standing sheaf of wheat: stalks bound with a band, heads flaring out on top, the stalk ends splayed at the
    foot (6.25 cm voxels)."""
    rng = np.random.default_rng(seed)
    band = z0 + int(h * 0.45)
    for z in range(z0, z0 + h):
        if z < band:
            rr = r + 0.8 * (band - z) / float(band - z0)                     # splayed foot
        elif z < z0 + h - 5:
            rr = r + 0.6 * (z - band) / float(max(1, h - 5 - (band - z0)))
        else:
            rr = r + 1.6 - 0.45 * (z - (z0 + h - 5))                           # the heads
        for x in range(int(cx - rr - 1), int(cx + rr + 2)):
            for y in range(int(cy - rr - 1), int(cy + rr + 2)):
                d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
                if d <= rr and (z < z0 + h - 5 or rng.random() < 0.85):
                    head = z >= z0 + h - 5
                    v.set(x, y, z, "wheat", "#fff8e8" if head and rng.random() < 0.5 else ("#f4e8cc" if head else "#e8d4a8"))
    for x in range(int(cx - r - 1), int(cx + r + 2)):
        for y in range(int(cy - r - 1), int(cy + r + 2)):
            if math.hypot(x + 0.5 - cx, y + 0.5 - cy) <= r + 0.5:
                v.box(x, y, band, x + 1, y + 1, band + 2, "paint", ROPE)
    # a few heads leaning out
    for k in range(6):
        a = k * math.pi / 3 + rng.random() * 0.5
        x, y = int(cx + math.cos(a) * (r + 1.8)), int(cy + math.sin(a) * (r + 1.8))
        v.set(x, y, z0 + h - 2 - int(rng.integers(0, 2)), "wheat", "#fff8e8")
    return v


def straw(v, x0, y0, x1, y1, p=0.22, seed=0):
    """Loose straw lying on the ground: single flat voxels and short stalks."""
    rng = np.random.default_rng(seed)
    for x in range(x0, x1):
        for y in range(y0, y1):
            if v.m[x, y, 0] == 0 and rng.random() < p:
                if rng.random() < 0.5:
                    v.box(x, y, 0, x + 2, y + 1, 1, "wheat", "#fff8e8")
                else:
                    v.box(x, y, 0, x + 1, y + 2, 1, "wheat", "#f0e4c8")


def tuft(v, x, y, seed=0):
    """A small tuft of grass."""
    rng = np.random.default_rng(seed)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if rng.random() < 0.7:
                v.box(x + dx, y + dy, 0, x + dx + 1, y + dy + 1, 1 + int(rng.integers(1, 4)), "leaves", "#b8e070")


# ====================================================================================================== the building

def hall(v):
    """The hall: the block walls on a chunky stone base course, the timber top plate."""
    B(v, HX0, WY0, 0, HX1, WY1, EAVE, "brick", WALL_T)
    v.tint("brick", "#ccc6bc", p=0.25, seed=41, cell=4)
    v.tint("brick", "#aca59b", p=0.2, seed=42, cell=4)
    B(v, HX0 - 1, WY0 - 1, 0, HX1 + 1, WY1 + 1, BASE, "stone", STONE_T)
    for k, z in enumerate(range(0, BASE, 4)):
        if k % 2:
            B(v, HX0 - 1, WY0 - 1, z, HX1 + 1, WY1 + 1, z + 4, "stone", STONE_L)
    B(v, HX0 - 2, WY0 - 2, BASE, HX1 + 2, WY1 + 2, BASE + 1, "stone", STONE_D)       # a weathered capping course
    B(v, HX0 - 1, WY0 - 1, PLATE, HX1 + 1, WY1 + 1, EAVE, "beam", WOOD_T)             # the top plate


def pier(v, x0, y0, x1, y1, top=26, cap=2, seed=0):
    """A stone pier: courses of blocks, alternately lighter, a wider plinth and a cap."""
    B(v, x0 - 1, y0 - 1, 0, x1 + 1, y1 + 1, 3, "stone", STONE_D)
    for k, z in enumerate(range(3, top, 4)):
        B(v, x0, y0, z, x1, y1, min(z + 4, top), "stone", (STONE_T, STONE_L)[(k + seed) % 2])
        # staggered joints: a darker block now and then
    B(v, x0 - 1, y0 - 1, top, x1 + 1, y1 + 1, top + cap, "stone", STONE_L)


def frame_wall(v, axis, plane, out, a0, a1, posts, braces=True, rail=BASE + 1, z1=PLATE):
    """Timber framing one voxel proud of a wall face: a sill rail on the base course, posts at `posts` (2 wide), an
    X of braces in alternate bays; iron brackets where they meet. axis 'x' or 'y' is the wall's normal; plane the wall's
    outer layer; out +1 / -1."""
    p = plane + out

    def put(al, ah, zl, zh, col=WOOD_T, layer=0):
        q = p + out * layer
        if axis == "y":
            B(v, al, q, zl, ah, q + 1, zh, "beam", col)
        else:
            B(v, q, al, zl, q + 1, ah, zh, "beam", col)

    def plate(a, z):
        if axis == "y":
            bracket(v, a, p, z, "-y" if out < 0 else "+y", 2)
        else:
            bracket(v, p, a, z, "-x" if out < 0 else "+x", 2)

    put(a0, a1, rail, rail + 2)
    put(a0, a1, (rail + z1) // 2 + 2, (rail + z1) // 2 + 4)
    for a in posts:
        put(a, a + 2, rail, z1)
    for n in range(len(posts) - 1):
        l, r = posts[n] + 2, posts[n + 1]
        wdt = r - l
        if not braces or wdt < 4:
            continue
        zl, zh = (rail + z1) // 2 + 4, z1
        hgt = zh - zl
        for t in range(wdt):
            zz = zl + int(t * hgt / float(wdt))
            if n % 2 == 0:
                put(l + t, l + t + 1, zz, min(zz + 2, zh), WOOD_D)
            else:
                put(r - 1 - t, r - t, zz, min(zz + 2, zh), WOOD_D)
    for a in posts:
        for z in (rail, (rail + z1) // 2 + 2):
            plate(a, z)
    return p


def front(v):
    y = WY0
    # the corner piers (stone, wrapping the corners) and the door piers
    pier(v, HX0 - 2, y - 3, HX0 + 12, y + 4, top=26, seed=0)                 # the left one, wide
    pier(v, 27, y - 3, 34, y, top=26, seed=1)                                # right of the door
    pier(v, HX1 - 4, y - 2, HX1 + 2, y + 4, top=14, seed=1)                  # the right corner: a low footing
    # timber over the piers: posts up to the plate
    for (a0, a1) in ((HX0 - 1, HX0 + 3), (HX0 + 8, HX0 + 11), (29, 32), (HX1 - 3, HX1 + 1)):
        B(v, a0, y - 2, 26 if a1 < 40 else 14, a1, y, PLATE, "beam", WOOD_T)
    B(v, HX1 - 3, y - 2, 14, HX1 + 1, y + 3, PLATE, "beam", WOOD_T)          # the right corner post wraps the corner
    # the plate is a heavy beam on the front, two proud, with iron brackets at the posts
    B(v, HX0 - 2, y - 3, PLATE, HX1 + 2, y, EAVE, "beam", WOOD_T)
    for x in (HX0 - 1, HX0 + 8, 29, HX1 - 3):
        bracket(v, x, y - 3, PLATE + 1, "-y", 2)
    # between the right pier and the corner: a rail, a brace
    B(v, 34, y - 1, BASE + 1, HX1 - 3, y, BASE + 3, "beam", WOOD_T)
    for t in range(HX1 - 3 - 34):
        zz = PLATE - 1 - int(t * 8 / 6.0)
        if zz > 20:
            B(v, 34 + t, y - 1, zz - 1, 35 + t, y, zz + 1, "beam", WOOD_D)
    # the doorway: a round-headed opening, deep, through the wall and the piers
    for x in range(int(DX - R_OPEN) - 1, int(DX + R_OPEN) + 1):
        for z in range(SILL, int(DZ + R_OPEN) + 1):
            dx = x + 0.5 - DX
            if abs(dx) < R_OPEN and (z < DZ or math.hypot(dx, z + 0.5 - DZ) < R_OPEN):
                B(v, x, y - 4, z, x + 1, y + DEPTH, z + 1, None)
    B(v, DX - 10, y - 4, SILL - 1, DX + 10, y + DEPTH, SILL, "plank", "#b08458")    # the floor
    B(v, DX - 10, y + DEPTH - 1, SILL, DX + 10, y + DEPTH, DZ + 10, "plank", "#8a6440")   # the back wall
    for x in range(DX - 9, DX + 9, 3):
        B(v, x, y + DEPTH - 2, SILL, x + 1, y + DEPTH - 1, DZ + 10, "beam", "#7a5638")
    # inside: posts and a beam, dark
    for x in (DX - 9, DX + 8):
        B(v, x, y + 11, SILL, x + 1, y + 13, DZ + 4, "beam", WOOD_D)
    B(v, DX - 9, y + 11, DZ + 4, DX + 9, y + 13, DZ + 6, "beam", WOOD_D)
    # the arch: voussoirs round the head, stone jambs, a keystone
    ARCH_A, ARCH_B, JOINT = "#f2ece2", "#ddd6ca", "#8a847a"
    def seg(dx, dz, d):
        a = (math.atan2(dz, dx) + 1e-3) / (math.pi / 9)
        if abs(a - round(a)) < 0.09 * 13.0 / max(d, 1.0):
            return JOINT
        return (ARCH_A, ARCH_B)[int(a) % 2]
    ring_xz(v, DX, DZ, R_OPEN, R_ARCH, y - 4, y + 1, "stone", cond=lambda dx, dz, d: dz >= 0, colfn=seg)
    ring_xz(v, DX, DZ, R_ARCH, R_ARCH + 1.0, y - 3, y + 1, "stone", STONE_D, cond=lambda dx, dz, d: dz >= 0)
    for side in (-1, 1):
        a0 = int(DX + R_OPEN) if side > 0 else int(DX - R_ARCH)
        a1 = int(DX + R_ARCH) if side > 0 else int(DX - R_OPEN)
        for k, z in enumerate(range(SILL, DZ, 4)):
            B(v, a0, y - 4 + (k % 2), z, a1, y + 1, min(z + 4, DZ), "stone", (ARCH_A, ARCH_B)[k % 2])
            B(v, a0, y - 4, min(z + 4, DZ) - 1, a1, y + 1, min(z + 4, DZ), "stone", JOINT) if z + 4 < DZ else None
    B(v, DX - 2, y - 5, int(DZ + R_ARCH) - 4, DX + 2, y, int(DZ + R_ARCH) + 1, "stone", ARCH_A)     # keystone
    # the gable: tie beam = plate; a collar, struts and short posts in the block infill
    collar = EAVE + 15
    span = lambda z: (RX0 + RUN * ((z - EAVE) // RISE + 1) + 2, RX1 - RUN * ((z - EAVE) // RISE + 1) - 2)
    l, r = span(collar)
    B(v, l, y - 2, collar, r, y, collar + 2, "beam", WOOD_T)
    for (xa, xb) in ((DX - 12, DX - 10), (DX + 10, DX + 12)):
        B(v, xa, y - 2, EAVE, xb, y, collar, "beam", WOOD_T)
    for side in (-1, 1):
        # a strut from the plate near each end up to the collar
        xs = (HX0 + 2) if side < 0 else (HX1 - 4)
        xe = DX - 12 if side < 0 else DX + 10
        n = abs(xe - xs)
        for t in range(n):
            x = xs + t * (1 if side < 0 else -1)
            zz = EAVE + int(t * (collar - EAVE) / float(n))
            B(v, x, y - 1, zz, x + 2, y, zz + 2, "beam", WOOD_D)
    B(v, DX - 2, y - 2, collar + 2, DX + 2, y, EAVE + 24, "beam", WOOD_T)          # king post
    for x in (l, DX - 12, DX + 10, r - 2, DX - 2):
        bracket(v, x, y - 2, collar, "-y", 2)


def gable_walls(v):
    """The block infill of the two gable triangles, set in under the thatch's overhang."""
    for i in range(12):
        l, r = RX0 + RUN * (i + 1), RX1 - RUN * (i + 1)
        if r <= l:
            break
        z0 = EAVE + RISE * i
        B(v, l, WY0, z0, r, WY1, z0 + RISE + 1, "brick", WALL_T)


def sides_and_back(v):
    # the east side: framing, two louvred vents, a lantern
    frame_wall(v, "x", HX1 - 1, 1, WY0 + 4, WY1 - 1, [WY0 + 4, WY0 + 18, WY0 + 32, WY0 + 46, WY1 - 3])
    for ya in (WY0 + 9, WY0 + 37):
        B(v, HX1 - 1, ya, 16, HX1, ya + 6, 23, "window")
        for z in range(16, 23, 2):
            B(v, HX1, ya, z, HX1 + 1, ya + 6, z + 1, "beam", WOOD_D)
        B(v, HX1, ya - 1, 15, HX1 + 2, ya + 7, 16, "beam", WOOD_T)
        B(v, HX1, ya - 1, 23, HX1 + 2, ya + 7, 24, "beam", WOOD_T)
    pier(v, HX1 - 4, WY1 - 4, HX1 + 2, WY1 + 2, top=14, seed=0)
    B(v, HX1 - 3, WY1 - 3, 14, HX1 + 1, WY1 + 1, PLATE, "beam", WOOD_T)
    # the west side (inside the lean-to): framing, a door into the store
    frame_wall(v, "x", HX0, -1, WY0 + 12, WY1 - 1, [WY0 + 12, WY0 + 26, WY0 + 40, WY1 - 3], braces=False)
    pier(v, HX0 - 2, WY1 - 4, HX0 + 4, WY1 + 2, top=14, seed=1)
    B(v, HX0 - 1, WY1 - 3, 14, HX0 + 3, WY1 + 1, PLATE, "beam", WOOD_T)
    # the back: framing, a hoist door high in the gable
    frame_wall(v, "y", WY1 - 1, 1, HX0 + 3, HX1 - 3, [HX0 + 3, HX0 + 17, DX - 1, HX1 - 19, HX1 - 5])
    B(v, DX - 4, WY1 - 1, EAVE + 2, DX + 4, WY1, EAVE + 12, "plank", "#a87e58")
    B(v, DX - 5, WY1, EAVE + 1, DX + 5, WY1 + 1, EAVE + 2, "beam", WOOD_T)
    B(v, DX - 5, WY1, EAVE + 12, DX + 5, WY1 + 1, EAVE + 13, "beam", WOOD_T)
    B(v, DX - 1, WY1, EAVE + 17, DX + 1, WY1 + 6, EAVE + 19, "beam", WOOD_T)     # the hoist beam
    for z in (EAVE + 4, EAVE + 9):
        B(v, DX - 4, WY1, z, DX + 4, WY1 + 1, z + 1, "paint", IRON)


def roof(v):
    """The thatch: stepped slabs, a fringe of straw at each step's lip, the eaves ragged, a bound ridge roll; the
    overhang over the gables is open beneath. Returns the z of the top of the ridge."""
    rng = np.random.default_rng(12)
    i = 0
    while RX1 - RX0 - 2 * i * RUN > 0:
        l, r = RX0 + i * RUN, RX1 - i * RUN
        z0 = EAVE + i * RISE
        B(v, l, RY0, z0, r, RY1, z0 + THICK, "wheat")
        i += 1
    n = i
    top = EAVE + (n - 1) * RISE + THICK
    # open under the overhang at both gable ends: only a skin THICK deep under the top of each column stays
    X, Y, Z = v.grid()
    H = np.zeros(NX, np.int32)
    for xi in range(NX):
        x = xi - OX
        ks = [k for k in range(n) if RX0 + k * RUN <= x < RX1 - k * RUN]
        H[xi] = EAVE + max(ks) * RISE + THICK if ks else 0
    band = ((Y >= OY + RY0) & (Y < OY + WY0)) | ((Y >= OY + WY1) & (Y < OY + RY1))
    v.where(band & (Z < H[X] - THICK) & v.mask("wheat"), None)
    # tints in long horizontal courses (the straw laid in rows) and patches
    th = v.mask("wheat")
    course = (Z // 1) % 3
    pal = np.array([V.rgb(c) for c in THATCH])
    pick = (V._hash3(X // 3, Y // 5, Z, 77) * len(THATCH)).astype(int) % len(THATCH)
    v.c[th] = pal[pick][th]
    rel = np.clip(Z - (H[X] - THICK), 0, THICK - 1)
    rows = np.array([V.rgb(c) for c in ROWS])[rel]
    v.c[th] = ((v.c[th].astype(np.float32) * rows[th].astype(np.float32)) / 255.0).clip(0, 255).astype(np.uint8)
    # straw hanging from every step's lip and the eaves (one voxel down and out), and a ragged front edge
    for k in range(n):
        l, r = RX0 + k * RUN, RX1 - k * RUN
        z = EAVE + k * RISE
        for y in range(RY0, RY1):
            for (x, out) in ((l, -1), (r - 1, 1)):
                zz = z + (1 if k else 0)
                q = rng.random()
                if q < 0.7:
                    S(v, x + out, y, zz, "wheat", "#f4e8cc")
                if q < 0.3:
                    S(v, x + out, y, zz + 1, "wheat", "#fff8e8")
                if k == 0 and rng.random() < 0.6:
                    S(v, x, y, z - 1, "wheat", "#d8c49c")
                if k == 0 and rng.random() < 0.25:
                    S(v, x, y, z - 2, "wheat", "#c8b088")
        for x in range(l, r):
            for (y, out) in ((RY0, -1), (RY1 - 1, 1)):
                if G(v, x, y, z + 1) == "wheat" and rng.random() < 0.35:
                    S(v, x, y + out, z + 1 + int(rng.integers(0, 2)), "wheat", "#f4e8cc")
                if rng.random() < 0.15 and G(v, x, y, z) == "wheat":
                    S(v, x, y, z, None)
    # the ridge roll, bound every metre
    mid = (RX0 + RX1) // 2
    B(v, mid - 3, RY0 - 1, top, mid + 3, RY1 + 1, top + 2, "wheat", "#f4e0a8")
    B(v, mid - 2, RY0 - 1, top + 2, mid + 2, RY1 + 1, top + 3, "wheat", "#fff0c4")
    for y in range(RY0 + 2, RY1, 8):
        B(v, mid - 3, y, top, mid + 3, y + 1, top + 2, "hay", "#b89048")
    # moss in a few places
    v.scatter("wheat", "moss", p=0.012, seed=4, direction="+z", region=(0, 0, EAVE, NX, NY, top))
    return top + 3, n


def barge(v, n):
    """Heavy timber along the front and back rakes: one chunky block per step, iron plates, a big apex block."""
    for (y0, y1, face) in ((RY0 + 1, RY0 + 5, "-y"), (RY1 - 5, RY1 - 1, "+y")):
        for k in range(n):
            l, r = RX0 + k * RUN, RX1 - k * RUN
            zl = EAVE + k * RISE
            col = (WOOD_T, WOOD_L)[k % 2]
            if r - l <= 2 * RUN:
                B(v, l - 1, y0, zl, r + 1, y1, zl + RISE + 3, "beam", col)
                continue
            B(v, l - 1, y0, zl - 3, l + RUN + 1, y1, zl + 1, "beam", col)
            B(v, r - RUN - 1, y0, zl - 3, r + 1, y1, zl + 1, "beam", col)
            if k % 3 == 1:
                yb = y0 if face == "-y" else y1 - 1
                bracket(v, l + 1, yb, zl - 2, face, 2)
                bracket(v, r - 3, yb, zl - 2, face, 2)
        mid = (RX0 + RX1) // 2
        ztop = EAVE + (n - 1) * RISE + THICK
        yb = (y0 - 2, y1) if face == "-y" else (y0, y1 + 2)
        B(v, mid - 4, yb[0], ztop - 2, mid + 4, yb[1], ztop + 5, "beam", WOOD_T)      # the apex block
        bracket(v, mid - 1, yb[0] if face == "-y" else yb[1] - 1, ztop, face, 3)
        # the eave ends: big beam ends with iron caps
        for (a0, a1) in ((RX0 - 3, RX0 + 3), (RX1 - 3, RX1 + 3)):
            B(v, a0, yb[0], EAVE - 4, a1, yb[1], EAVE + 3, "beam", WOOD_T)
            bracket(v, a0 + 2, yb[0] if face == "-y" else yb[1] - 1, EAVE - 2, face, 2)
    # purlin ends poking out of the side eaves under the thatch
    for y in range(RY0 + 6, RY1 - 4, 12):
        for (x0, x1) in ((RX0 - 1, RX0 + 3), (RX1 - 3, RX1 + 1)):
            B(v, x0, y, EAVE - 3, x1, y + 3, EAVE, "beam", WOOD_D)


def cupola(v, top):
    """The thatched vent on the ridge: a timber box with louvres (lit from inside), a little thatch hat."""
    cx, cy, h = (RX0 + RX1) // 2, WY0 + 20, 5
    z0 = top - 8
    B(v, cx - h, cy - h, z0, cx + h, cy + h, top + 6, "plank", "#9a7454")
    zw = top - 2
    for (a, b) in ((cy - h - 1, cy - h), (cy + h, cy + h + 1)):
        B(v, cx - h + 2, a, zw, cx + h - 2, b, zw + 6, "window")
        for z in range(zw, zw + 6, 2):
            B(v, cx - h + 2, a - (1 if a < cy else -1), z, cx + h - 2, b - (1 if a < cy else -1), z + 1, "beam", WOOD_D)
    for (a, b) in ((cx - h - 1, cx - h), (cx + h, cx + h + 1)):
        B(v, a, cy - h + 2, zw, b, cy + h - 2, zw + 6, "window")
        for z in range(zw, zw + 6, 2):
            B(v, a - (1 if a < cx else -1), cy - h + 2, z, b - (1 if a < cx else -1), cy + h - 2, z + 1, "beam", WOOD_D)
    for (px, py) in ((cx - h - 1, cy - h - 1), (cx + h - 1, cy - h - 1), (cx - h - 1, cy + h - 1), (cx + h - 1, cy + h - 1)):
        B(v, px, py, top - 3, px + 2, py + 2, top + 6, "beam", WOOD_T)
    B(v, cx - h - 1, cy - h - 1, top - 3, cx + h + 1, cy + h + 1, top - 2, "beam", WOOD_T)
    B(v, cx - h - 1, cy - h - 1, top + 4, cx + h + 1, cy + h + 1, top + 6, "beam", WOOD_T)
    bracket(v, cx - 1, cy - h - 1, top + 4, "-y", 2)
    # the hat: three thatch steps, ragged, a wooden knob
    rng = np.random.default_rng(5)
    z = top + 6
    for k, e in enumerate((h + 3, h + 1, h - 1)):
        B(v, cx - e, cy - e, z, cx + e, cy + e, z + 2, "wheat", THATCH[k % len(THATCH)])
        for x in range(cx - e, cx + e):
            for (y, d) in ((cy - e, -1), (cy + e - 1, 1)):
                if rng.random() < 0.4:
                    S(v, x, y + d, z, "wheat", "#fff2c8")
        for y in range(cy - e, cy + e):
            for (x, d) in ((cx - e, -1), (cx + e - 1, 1)):
                if rng.random() < 0.4:
                    S(v, x + d, y, z, "wheat", "#fff2c8")
        z += 2
    B(v, cx - 1, cy - 1, z, cx + 1, cy + 1, z + 2, "beam", WOOD_T)
    return z + 2


def lean_to(v):
    """The lean-to on the west: posts and a front beam, a low stone wall at the back half, a stone floor, its own
    thatch slope tucked under the main eave."""
    xo = LX0
    B(v, xo - 1, LY0, 0, HX0, WY1 + 2, 2, "cobble", STONE_T)                        # the floor
    for (y0, y1) in ((LY0, LY0 + 3), (6, 9), (WY1 - 1, WY1 + 2)):
        B(v, xo - 1, y0 - 1, 0, xo + 4, y1 + 1, 3, "stone", STONE_D)                  # post bases
        B(v, xo, y0, 3, xo + 3, y1, 20, "post", WOOD_T)
        if y0 == LY0:
            bracket(v, xo, y0, 16, "-y", 2)
    B(v, xo - 1, LY0 - 1, 20, HX0, LY0 + 3, 23, "beam", WOOD_T)                     # the front beam
    B(v, xo - 1, LY0, 20, xo + 3, WY1 + 2, 23, "beam", WOOD_T)                       # the side beam
    for k in range(5):                                                                # knee braces
        B(v, xo + 3 + k, LY0 - 1, 15 + k, xo + 4 + k, LY0 + 2, 17 + k, "beam", WOOD_D)
        B(v, HX0 - 4 - k, LY0 - 1, 15 + k, HX0 - 3 - k, LY0 + 2, 17 + k, "beam", WOOD_D)
    bracket(v, xo, LY0 - 1, 21, "-y", 2)
    bracket(v, HX0 - 3, LY0 - 1, 21, "-y", 2)
    # the triangle between the front beam and the slope: boards
    # a low stone wall along the back half of the open side, a plank wall at the back
    B(v, xo - 1, 9, 2, xo + 3, WY1 - 1, 9, "stone", STONE_T)
    B(v, xo - 1, 9, 9, xo + 3, WY1 - 1, 10, "stone", STONE_L)
    B(v, xo, WY1 - 1, 2, HX0, WY1 + 1, 22, "plank", "#b88a5c")
    # the thatch: four slabs falling to the west, from under the main eave
    rng = np.random.default_rng(8)
    steps = [(HX0 - 8, HX0, 31), (HX0 - 16, HX0 - 8, 28), (HX0 - 24, HX0 - 16, 25), (xo - 3, HX0 - 24, 22)]
    for k, (a0, a1, z0) in enumerate(steps):
        B(v, a0, LY0 - 3, z0, a1 + (2 if k == 0 else 1), WY1 + 4, z0 + 4, "wheat")
    # the back wall closes up to the slope
    for (a0, a1, z0) in steps:
        B(v, max(a0, xo), WY1 - 1, 22, a1, WY1 + 1, z0 + 1, "plank", "#b88a5c")
    # a stepped fascia board along the front and back of the slope
    for k, (a0, a1, z0) in enumerate(steps):
        for (y0, y1) in ((LY0 - 4, LY0 - 2), (WY1 + 3, WY1 + 5)):
            B(v, a0 - 1, y0, z0 - 1, a1 + 1, y1, z0 + 2, "beam", (WOOD_T, WOOD_L)[k % 2])
    th = v.mask("wheat")
    X, Y, Z = v.grid()
    sel = th & (X < OX + HX0 + 2) & (Z < EAVE)
    pal = np.array([V.rgb(c) for c in THATCH])
    pick = (V._hash3(X // 3, Y // 5, Z, 78) * len(THATCH)).astype(int) % len(THATCH)
    v.c[sel] = pal[pick][sel]
    for k, (a0, a1, z0) in enumerate(steps):
        for r_, col in enumerate(ROWS):
            m_ = sel & (X >= OX + a0) & (X < OX + a1) & (Z == z0 + r_)
            v.c[m_] = ((v.c[m_].astype(np.float32) * V.rgb(col).astype(np.float32)) / 255.0).clip(0, 255).astype(np.uint8)
    for k, (a0, a1, z0) in enumerate(steps):
        for y in range(LY0 - 3, WY1 + 4):
            if rng.random() < 0.7:
                S(v, a0 - 1, y, z0 + 1 + int(rng.integers(0, 2)), "wheat", "#f4e8cc")
            if k == len(steps) - 1 and rng.random() < 0.5:
                S(v, a0, y, z0 - 1, "wheat", "#d8c49c")


def steps(v):
    """Stone steps up to the doorway: a landing in the doorway's mouth, two steps, big cheek blocks."""
    sx0, sx1 = DX - 11, DX + 11
    B(v, sx0, WY0 - 5, 0, sx1, WY0, SILL, "stone", STONE_T)
    B(v, sx0, WY0 - 13, 0, sx1, WY0 - 5, 2, "stone", STONE_L)
    B(v, sx0 + 1, WY0 - 9, 2, sx1 - 1, WY0 - 5, 4, "stone", STONE_T)
    # joints across the treads
    for x in range(sx0 + 5, sx1, 6):
        B(v, x, WY0 - 13, 1, x + 1, WY0 - 9, 2, "stone", STONE_D)
        B(v, x - 2, WY0 - 9, 3, x - 1, WY0 - 5, 4, "stone", STONE_D)
    for (a0, a1) in ((sx0 - 3, sx0), (sx1, sx1 + 3)):
        B(v, a0, WY0 - 13, 0, a1, WY0 - 1, 4, "stone", STONE_T)
        B(v, a0, WY0 - 9, 4, a1, WY0 - 1, 7, "stone", STONE_L)
        B(v, a0, WY0 - 13, 4, a1, WY0 - 10, 5, "stone", STONE_D)


def build():
    v = Vox(NX, NY, NZ, VX, origin=(OX, OY, 0), name="granary", seed=31)
    hall(v)
    for reg in ((0, 0, 0, NX, NY, BASE + 1),):
        v.chunky("stone", cell=4, depth=1, p=0.18, seed=5, region=reg)
    v.chunky("brick", cell=4, depth=1, p=0.06, seed=6,
             region=(OX + HX1 - 1, 0, BASE, NX, NY, PLATE))
    v.chunky("brick", cell=4, depth=1, p=0.06, seed=7,
             region=(0, OY + WY1 - 1, BASE, NX, NY, PLATE))
    top, n = roof(v)
    gable_walls(v)
    front(v)
    sides_and_back(v)
    v.chunky("stone", cell=4, depth=1, p=0.12, seed=9, region=(0, 0, 3, NX, OY + WY0 + 1, 27))
    barge(v, n)
    ctop = cupola(v, top)
    lean_to(v)
    steps(v)
    lantern(v, DX - 16, WY0, 27)
    lantern(v, 37, WY0, 27)
    v.scatter("stone", "mossy_stone", p=0.05, seed=7, direction="+z")
    v.scatter("brick", "mossy_stone", p=0.004, seed=8)
    print("ridge top %.2f m, cupola top %.2f m" % (top * VX, ctop * VX))

    parts = [v]
    m = lambda q: q * VX
    # banners: the big one in the gable, two on the piers by the door
    big = banner(w=24, h=36, tip=8, shape="point", name="bannerBig", emblem=wheat_emblem(17, 22, 28.0), ey0=4)
    parts.append(big.at(m(DX), m(WY0 - 4) - TX, m(EAVE + 14)))
    B(v, DX - 7, WY0 - 5, EAVE + 13, DX - 6, WY0 - 2, EAVE + 15, "paint", IRON)
    B(v, DX + 6, WY0 - 5, EAVE + 13, DX + 7, WY0 - 2, EAVE + 15, "paint", IRON)
    for (bx, name) in ((HX0 + 7.5, "bannerL"), (30.5, "bannerR")):
        b = banner(w=10, h=20, tip=0, shape="flat", name=name, emblem=wheat_emblem(7, 11, 30.0), ey0=3)
        parts.append(b.at(m(bx), m(WY0 - 4) - TX, m(25)))
    # the awning along the lean-to's front beam
    parts.append(awning(w=62, out=18, drop=8).at(m((LX0 - 1 + HX0) / 2.0), m(LY0 - 1), m(23)))

    # ---- the fine clutter (6.25 cm voxels), every piece inside the footprint
    # inside the doorway: stacked sacks, a barrel, a shovel
    f = fine(36, 30, 36, "inside", seed=3)
    for (cx, cy, z, ax, end, c) in ((6, 22, 0, "y", 1, SACKS[1]), (6, 22, 6, "y", -1, SACKS[0]), (6, 22, 12, "y", 1, SACKS[2]),
                                    (16, 25, 0, "x", 1, SACKS[3]), (16, 25, 6, "x", -1, SACKS[1]),
                                    (29, 23, 0, "y", -1, SACKS[2]), (29, 23, 6, "y", 1, SACKS[0]), (29, 23, 12, "y", -1, SACKS[3]),
                                    (29, 23, 18, "y", 1, SACKS[1]), (6, 22, 18, "y", -1, SACKS[3])):
        sack_lying(f, cx, cy, z, ax, c, length=5.5 if ax == "y" else 6.5, fat=4.0, end=end)
    sack(f, 7, 9, 0, 4.4, 4.0, SACKS[2])
    barrel(f, 25, 10, 0, seed=4, full="wheat")
    # the shovel, leaning on the barrel
    for k in range(18):
        S_ = (31 - k // 3, 6, 2 + k)
        f.set(S_[0], S_[1], S_[2], "post", "#c08850")
    f.box(30, 5, 0, 34, 7, 4, "metal", "#9a9aa2")
    f.box(25, 6, 20, 27, 7, 21, "post", "#c08850")
    lamp = Vox(6, 6, 9, VX, origin=(3, 3, 9), name="inlamp")
    lamp.box(2, 2, 8, 4, 4, 9, "paint", IRON)
    lamp.box(1, 1, 7, 5, 5, 8, "paint", IRON)
    lamp.box(1, 1, 2, 5, 5, 7, "glow", "lantern")
    lamp.frame(1, 1, 2, 5, 5, 7, "paint", IRON)
    lamp.box(1, 1, 1, 5, 5, 2, "paint", IRON)
    parts.append(lamp.at(m(DX), m(WY0 + 7), m(DZ + 8)))
    parts.append(f.at(m(DX), m(WY0 + 6.5), m(SILL)))

    # under the lean-to: sacks, crates, barrels
    g = fine(60, 100, 30, "shed", seed=4)
    crate(g, 40, 70, 0, s=12, seed=1)
    barrel(g, 14, 84, 0, seed=5)
    barrel(g, 14, 70, 0, seed=6, full="wheat")
    for (cx, cy, z, ax, end, c) in ((44, 46, 0, "y", 1, SACKS[0]), (44, 46, 6, "y", -1, SACKS[2]), (52, 46, 0, "y", -1, SACKS[1]),
                                    (48, 46, 12, "y", 1, SACKS[3])):
        sack_lying(g, cx, cy, z, ax, c, length=6.0, fat=4.0, end=end)
    sack(g, 30, 50, 0, 4.4, 4.0, SACKS[1])
    sack(g, 22, 46, 0, 4.6, 4.2, SACKS[3], open_top=True)
    sack(g, 36, 18, 0, 4.4, 4.0, SACKS[0])
    crate(g, 18, 14, 0, s=11, seed=4)
    straw(g, 2, 2, 58, 60, p=0.03, seed=3)
    parts.append(g.at(m((LX0 + HX0) / 2.0), m(LY0 + 25 + 1.5), m(2)))

    # the hand cart, front left, full of wheat
    c = fine(44, 26, 30, "cart", seed=6)
    BED = 10
    for y in range(3, 23, 2):
        c.box(2, y, BED - 1, 32, y + 2, BED, "plank", PWOOD[(y // 2) % len(PWOOD)])
    for y in (3, 22):
        c.box(2, y, BED - 2, 44, y + 1, BED, "beam", "#c89060")
        c.box(43, y, BED - 1, 44, y + 1, BED + 1, "paint", IRON)
        for x in (2, 11, 20, 31):
            c.box(x, y, BED, x + 1, y + 1, BED + 7, "post", "#d0a070")
        c.box(2, y, BED + 3, 32, y + 1, BED + 4, "plank", "#e2b684")
        c.box(2, y, BED + 6, 32, y + 1, BED + 7, "plank", "#d6a674")
    c.box(2, 3, BED, 3, 23, BED + 7, "plank", "#e2b684")
    c.box(31, 3, BED, 32, 23, BED + 7, "plank", "#d6a674")
    c.box(36, 12, 0, 37, 14, BED - 2, "post", "#c08850")                     # the prop leg
    rng = np.random.default_rng(9)
    X, Y, Z = c.grid()
    load = (X >= 3) & (X < 31) & (Y >= 4) & (Y < 22) & (Z >= BED) & (Z < BED + 9)
    c.where(load, "wheat", "#f0e0c0")
    for x in range(3, 31):
        for y in range(4, 22):
            hgt = BED + 9 + int(rng.integers(0, 4)) - (1 if x in (3, 30) or y in (4, 21) else 0)
            c.box(x, y, BED + 9, x + 1, y + 1, hgt, "wheat", "#fff8e8" if rng.random() < 0.4 else "#f4e8cc")
    for _ in range(20):                                                       # heads leaning over the sides
        x = int(rng.integers(3, 31))
        y = 3 if rng.random() < 0.5 else 22
        c.set(x, y, BED + 7 + int(rng.integers(0, 3)), "wheat", "#fff8e8")
    ax, az, r = 17.0, 8.0, 8.0                                               # wheels on both sides
    c.box(16, 1, 7, 18, 25, 9, "beam", "#a87850")
    for (ya, yb) in ((0, 2), (24, 26)):
        d = np.hypot(X + 0.5 - ax, Z + 0.5 - az)
        c.where((d <= r) & (d > r - 2.2) & (Y >= ya) & (Y < yb), "plank", "#c99a66")
        c.where((d <= r) & (d > r - 1.0) & (Y >= ya) & (Y < yb), "paint", IRON)
        diag = np.abs(np.abs(X + 0.5 - ax) - np.abs(Z + 0.5 - az)) < 0.75
        spoke = (d <= r - 1.5) & (Y >= ya) & (Y < yb) & ((np.abs(X + 0.5 - ax) < 0.6) | (np.abs(Z + 0.5 - az) < 0.6) | diag)
        c.where(spoke, "post", "#c08850")
        c.box(16, ya, 7, 18, yb, 9, "paint", IRON)
    parts.append(c.at(m(LX0 + 8), m(WY0 - 14), 0.0))

    # round the front: sheaves, the emblem sack, a crate, a barrel, straw, grass
    p = fine(208, 40, 30, "front", seed=7)
    # (x in fine voxels from the left of the footprint; y from its front)
    sheaf(p, 94, 30, 0, h=16, r=3.0, seed=1)                                  # left of the steps
    sheaf(p, 84, 28, 0, h=14, r=2.6, seed=2)
    big_sack = fine(18, 16, 24, "bigsack")
    sack(big_sack, 9, 8, 0, 6.5, 5.5, "#d6b27a", tall=7.0)
    emblem_on(big_sack, wheat_emblem(7, 10, 30.0), 6, 3, 16)
    parts.append(big_sack.at(m(-22.5), m(WY0 - 10), 0.0))
    crate(p, 186, 24, 0, s=14, seed=5)
    sheaf(p, 193, 31, 14, h=12, r=2.4, seed=3)                                # a sheaf on the crate
    sheaf(p, 176, 30, 0, h=16, r=3.0, seed=4)
    barrel(p, 178, 13, 0, seed=8)
    sack(p, 200, 12, 0, 4.0, 3.8, SACKS[1])
    straw(p, 70, 16, 112, 34, p=0.04, seed=1)
    straw(p, 8, 4, 56, 16, p=0.04, seed=2)
    straw(p, 164, 6, 204, 22, p=0.035, seed=4)
    for k, (tx, ty) in enumerate(((70, 6), (116, 8), (128, 20), (160, 6), (204, 8), (100, 30), (14, 4), (150, 26))):
        tuft(p, tx, ty, seed=k)
    parts.append(p.at(m(-4), m(WY0 - 12), 0.0))

    for q in parts:
        a = q.mesh_arrays()
        print("  part %-10s %6d faces" % (q.name, 0 if a is None else len(a["verts"])))
    ob = V.join(parts, NAME)
    drop_bottom(ob, zs=(0.0,))
    centre(ob)
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
    preview("front", target=(0, 0, 3.4), az=-6, el=8, dist=34, lens=50, res=(1280, 860), sun_az=-150, sun_el=30)
    preview("three", target=(0, 0, 3.0), az=32, el=30, dist=38, lens=50, res=(1280, 860), sun_az=-125, sun_el=30)
    preview("ref", target=(0, 0, 3.2), az=-22, el=16, dist=32, lens=50, res=(1536, 1024), sun_az=-120, sun_el=24)
    preview("door", target=(0.2, -3.5, 2.4), az=-4, el=6, dist=14, lens=50, res=(1280, 860), sun_az=-150, sun_el=30)
    preview("back", target=(0, 0, 3.0), az=200, el=28, dist=38, lens=50, res=(1280, 860))


if __name__ == "__main__":
    main()
