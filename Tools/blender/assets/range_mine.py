"""range_mine: the archery range and the mine of the voxel village.

  SM_ArcheryRange   open-fronted timber shed, 9 x 6 m, front (open side) faces -Y
  SM_Target         straw target on its easel
  SM_ArrowBarrel    barrel full of arrows
  SM_MineCliff      rock outcrop 16 x 11 m with the mine portal, tunnel, rails and ramp; portal faces -Y
  SM_MineCart       mine cart heaped with gold ore (long axis X)

Run:  Blender -b --factory-startup --python Tools/blender/assets/range_mine.py -- [--no-render] [--only=range,cliff,...]
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import voxlib as V
import voxkit as K
from voxlib import Vox

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
NO_RENDER = "--no-render" in ARGS
ONLY = [n for a in ARGS if a.startswith("--only=") for n in a.split("=", 1)[1].split(",")]
TASK = "range_mine"

DARK = "#1a1410"            # tunnel walls
SHAFT = "#c9a468"           # arrow shafts
LEATHER = "#7a4a24"


def preview(tag, **kw):
    if NO_RENDER:
        return
    import time
    path = os.path.join(V.PREVIEWS, "%s_%s.png" % (TASK, tag))
    for attempt in range(5):                                # other jobs share the GPU: it can run out of memory
        try:
            V.render(path, **kw)
            return
        except RuntimeError as e:
            print("render failed (%s), retrying" % str(e)[:80])
            time.sleep(25)


def drop_bottom(ob, z=0.0):
    """Delete the faces lying flat on the ground plane and facing down (never seen: saves faces on big rock masses)."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    doomed = [f for f in bm.faces if f.normal.z < -0.5 and all(abs(vt.co.z - z) < 1e-4 for vt in f.verts)]
    n = len(doomed)
    bmesh.ops.delete(bm, geom=doomed, context="FACES")
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()
    ob["voxel_faces"] = int(ob.get("voxel_faces", 0)) - n // 2
    return ob


def brace(v, x, y0, y1, z, dx, n=5, mat="beam"):
    """A stepped diagonal brace starting on a post face at voxel column x, height z, rising towards dx (+1 / -1)."""
    for k in range(n):
        xx = x + k * dx
        v.box(xx if dx > 0 else xx - 1, y0, z + k, xx + 1 if dx > 0 else xx, y1, z + k + 2, mat)


def recess_gable(v, x0, x1, y0, y1, z, run, rise, steps, depth=2):
    """Cut the end face of a kit gable roof back by `depth` voxels inside its barge boards (x0..x1 is the slab of
    voxels to carve), so that the boards stand out as thick stepped blocks. Leaves a tie beam and a king post."""
    for i in range(1, steps):
        lo, hi = y0 + i * run, y1 - i * run
        if hi - lo <= 2 * run:
            break
        v.clear(x0, lo + run, z + i * rise, x1, hi - run, z + (i + 1) * rise)
    mid = (y0 + y1) // 2
    v.box(x0, mid - 1, z + rise, x1, mid + 1, z + (steps - 1) * rise, "post")


# ====================================================================================================== props

def target_voxes(x=0.0, y=0.0, z=0.0):
    """Straw target on a wooden easel: 6.25 cm voxels, the disc 1 m across. Origin centre of base, front -Y."""
    t = Vox(20, 16, 24, 0.0625, origin=(10, 8, 0), name="target", seed=3)
    for s in (-1, 1):                                       # two front legs leaning in
        for zz in range(0, 20):
            off = 8 - zz // 4
            x0 = 10 + s * off - 1
            t.box(x0, 7, zz, x0 + 2, 9, zz + 1, "post")
        t.box(10 + s * 8 - 1, 6, 0, 10 + s * 8 + 1, 10, 1, "beam")       # feet
    for zz in range(0, 18):                                 # back leg
        yy = 9 + int(round((17 - zz) * 5 / 17.0))
        t.box(9, yy, zz, 11, yy + 2, zz + 1, "post")
    t.box(2, 6, 4, 18, 9, 6, "beam")                        # cross rail
    t.box(5, 3, 5, 15, 7, 6, "beam")                        # ledge the disc sits on
    for i in range(20):
        for k in range(6, 22):
            dx, dz = i + 0.5 - 10, k + 0.5 - 14
            if max(abs(dx), abs(dz)) > 8 or abs(dx) + abs(dz) > 11.5:
                continue
            r = (dx * dx + dz * dz) ** 0.5
            col = "target_red" if r < 2.0 else "target_white" if r < 4.0 else "target_red" if r < 6.0 else "target_white"
            t.box(i, 4, k, i + 1, 7, k + 1, "hay")
            t.box(i, 3, k, i + 1, 4, k + 1, "paint", col)
    t.box(9, 4, 22, 11, 9, 24, "beam")                      # top peg
    return [t.at(x, y, z)]


def open_barrel():
    v = Vox(8, 8, 9, 0.125, origin=(4, 4, 0), name="barrel")
    v.cylinder(4, 4, 0, 8, 3.1, "plank")
    v.cylinder(4, 4, 1, 7, 3.6, "plank")
    for z in (1, 6):
        ring = Vox(8, 8, 9, 0.125)
        ring.cylinder(4, 4, z, z + 1, 3.9, "metal")
        v.stamp(ring, 0, 0, 0)
    v.cylinder(4, 4, 7, 8, 2.3, None)                       # open top
    v.cylinder(4, 4, 6, 7, 2.3, "paint", "#2a1d12")
    return v


def arrow_bundle(spots, seed=4, lean=0.2, size=18, height=14):
    """Arrows standing nock-up (6.25 cm voxels): shaft, a fat coloured fletching, a dark nock. Origin: centre, z=0."""
    a = Vox(size, size, height, 0.0625, origin=(size / 2.0, size / 2.0, 0), name="arrows")
    rng = np.random.default_rng(seed)
    cols = ["target_red", "white", "flower_orange", "cream", "target_red", "white", "flower_yellow"]
    for j, (bx, by) in enumerate(spots):
        lx, ly = bx / 3.0 * lean, by / 3.0 * lean
        shaft = int(rng.integers(5, 9))
        col = cols[j % len(cols)]
        for k in range(shaft + 4):
            px, py = size // 2 + bx + int(round(lx * k)), size // 2 + by + int(round(ly * k))
            if k < shaft:
                a.set(px, py, k, "paint", SHAFT)
            elif k < shaft + 3:
                a.set(px, py, k, "paint", col)
                if j % 2:
                    a.set(px - 1, py, k, "paint", col)
                    a.set(px + 1, py, k, "paint", col)
                else:
                    a.set(px, py - 1, k, "paint", col)
                    a.set(px, py + 1, k, "paint", col)
            else:
                a.set(px, py, k, "paint", "#3a2a1c")
    return a


def arrow_barrel_voxes(x=0.0, y=0.0, z=0.0):
    spots = [(-3, -3), (0, -3), (3, -3), (-3, 0), (0, 0), (3, 0), (-3, 3), (0, 3), (3, 3)]
    return [open_barrel().at(x, y, z), arrow_bundle(spots).at(x, y, z + 0.875)]


def quiver_rack_voxes(x=0.0, y=0.0, z=0.0):
    """A rack with three quivers and a bow (6.25 cm voxels). Origin centre of base, front -Y."""
    r = Vox(24, 10, 26, 0.0625, origin=(12, 5, 0), name="rack")
    for x0 in (1, 21):
        r.box(x0, 4, 0, x0 + 2, 6, 23, "post")
        r.box(x0, 1, 0, x0 + 2, 9, 2, "beam")
    r.box(0, 4, 20, 24, 6, 22, "beam")
    r.box(1, 4, 7, 23, 6, 9, "beam")
    for i, x0 in enumerate((4, 10, 16)):
        r.box(x0, 1, 6, x0 + 4, 4, 17, "paint", LEATHER)
        r.box(x0, 1, 14, x0 + 4, 4, 15, "paint", "gold")
        r.box(x0, 1, 6, x0 + 4, 4, 7, "paint", "#5a3418")
        r.box(x0 + 1, 3, 17, x0 + 3, 5, 20, "paint", "#5a3418")          # strap up to the rail
        for k, col in enumerate(("target_red", "white", "flower_orange")):
            px = x0 + k + (1 if k else 0)
            r.box(px, 2, 17, px + 1, 3, 19 + (k + i) % 2, "paint", col)
    return [r.at(x, y, z)]


# ====================================================================================================== archery range

def range_voxes():
    v = Vox(72, 40, 46, 0.125, origin=(36, 20, 0), name="range", seed=21)
    # ---- floor
    v.box(4, 5, 0, 68, 36, 1, "plank")
    v.box(4, 5, 0, 68, 6, 1, "beam")
    v.box(4, 35, 0, 68, 36, 1, "beam")
    v.box(4, 5, 0, 5, 36, 1, "beam")
    v.box(67, 5, 0, 68, 36, 1, "beam")

    # ---- roofs: the high centre gable, then the two lower ones tucked under its barge boards
    K.gable_roof(v, 17, 1, 55, 39, 26, ridge="x", run=4, rise=2, thick=3, trim_w=4, trim_up=2)
    v.box(21, 2, 26, 51, 38, 27, "plank")                                  # boarded underside
    recess_gable(v, 17, 19, 1, 39, 26, 4, 2, 5)
    recess_gable(v, 53, 55, 1, 39, 26, 4, 2, 5)
    for (a0, a1) in ((1, 20), (52, 71)):
        K.gable_roof(v, a0, 3, a1, 37, 17, ridge="x", run=4, rise=2, thick=3, trim_w=4, trim_up=2)
        v.box(a0 + 4, 4, 17, a1 - 4, 36, 18, "plank")
    recess_gable(v, 1, 3, 3, 37, 17, 4, 2, 5)
    recess_gable(v, 69, 71, 3, 37, 17, 4, 2, 5)
    v.scatter("roof", "moss", p=0.07, seed=4, direction="+z")
    v.tint("roof", "#dff0b8", p=0.18, seed=6, cell=2)
    v.tint("roof", "#b8d0a0", p=0.15, seed=8, cell=2)

    # ---- posts on stone footings
    posts = [(4, 8, 14), (20, 24, 22), (48, 52, 22), (64, 68, 14)]
    for (x0, x1, top) in posts:
        for (y0, y1) in ((6, 10), (31, 35)):
            v.box(x0 - 1, y0 - 1, 0, x1 + 1, y1 + 1, 5, "stone")
            v.box(x0, y0, 5, x1, y1, top, "post")
    v.box(33, 30, 0, 39, 36, 5, "stone")                                    # middle post of the back wall
    v.box(34, 31, 5, 38, 35, 22, "post")

    # ---- plates and lintels
    v.box(19, 6, 22, 53, 10, 26, "beam")
    v.box(19, 31, 22, 53, 35, 26, "beam")
    v.box(20, 5, 22, 24, 36, 26, "beam")
    v.box(48, 5, 22, 52, 36, 26, "beam")
    for (a0, a1, px) in ((3, 20, 4), (52, 69, 64)):
        v.box(a0, 6, 14, a1, 10, 17, "beam")
        v.box(a0, 31, 14, a1, 35, 17, "beam")
        v.box(px, 5, 14, px + 4, 36, 17, "beam")
    v.box(24, 19, 23, 48, 21, 26, "beam")                                   # tie beam across the centre bay
    # braces
    brace(v, 24, 7, 9, 16, +1, 6)
    brace(v, 48, 7, 9, 16, -1, 6)
    brace(v, 20, 7, 9, 10, -1, 4)
    brace(v, 8, 7, 9, 10, +1, 4)
    brace(v, 52, 7, 9, 10, +1, 4)
    brace(v, 64, 7, 9, 10, -1, 4)

    # ---- back wall of planks, with rails standing proud on both faces
    v.box(8, 33, 1, 20, 35, 14, "plank")
    v.box(24, 33, 1, 48, 35, 22, "plank")
    v.box(52, 33, 1, 64, 35, 14, "plank")
    v.box(8, 32, 8, 20, 36, 10, "beam")
    v.box(24, 32, 11, 48, 36, 13, "beam")
    v.box(52, 32, 8, 64, 36, 10, "beam")
    v.box(4, 32, 1, 68, 36, 2, "beam")
    # ---- side walls: boarded to waist height, open above
    for (x0, x1) in ((5, 7), (65, 67)):
        v.box(x0, 10, 1, x1, 31, 9, "plank")
        v.box(x0 - 1, 10, 9, x1 + 1, 31, 10, "beam")
        v.box(x0, 19, 1, x1, 22, 14, "post")
    v.tint("plank", "#e8d2b0", p=0.25, seed=3, cell=2)

    # ---- lanterns on the posts
    K.wall_lantern(v, 22, 6, 17)
    K.wall_lantern(v, 50, 6, 12)
    K.wall_lantern(v, 66, 6, 13)
    K.wall_lantern(v, 5, 6, 13)

    # ---- furnishings
    v.box(26, 27, 1, 34, 32, 6, "hay")                                      # straw bales behind the targets
    v.box(35, 28, 1, 46, 32, 5, "hay")
    v.box(29, 28, 6, 37, 32, 10, "hay")
    v.box(10, 24, 1, 19, 31, 5, "hay")                                      # left bay: bales and a crate
    v.box(11, 26, 5, 17, 30, 9, "hay")
    v.stamp(K.crate(6), 12, 17, 1)
    v.stamp(K.barrel(), 59, 27, 1)                                          # right bay: barrel and crates
    v.stamp(K.crate(6), 56, 20, 1)
    v.stamp(K.crate(5), 56, 20, 7)
    # bows hung on the back wall of the centre bay
    v.box(25, 32, 15, 47, 33, 16, "beam")
    for bx in (40, 44):
        v.box(bx, 32, 14, bx + 1, 33, 21, "paint", "wood_dark")
        v.box(bx + 1, 31, 14, bx + 2, 32, 15, "paint", "wood_dark")
        v.box(bx + 1, 31, 20, bx + 2, 32, 21, "paint", "wood_dark")

    # ---- a little green: vines off the eaves and up a post, moss on the footings
    for (vx, ln) in ((24, 3), (25, 2), (27, 4), (31, 2), (44, 2), (45, 3)):
        v.box(vx, 0, 26 - ln, vx + 1, 1, 26, "leaves", "#d8f0a0")
    for (vx, ln) in ((2, 3), (3, 2), (9, 2), (63, 2), (70, 3)):
        v.box(vx, 2, 17 - ln, vx + 1, 3, 17, "leaves", "#d8f0a0")
    for zz in range(5, 13):
        if zz % 3:
            v.set(19, 6 + zz % 2, zz, "leaves", "#d8f0a0")
    v.chunky("stone", p=0.35, seed=2)
    v.scatter("stone", "mossy_stone", p=0.12, seed=5)

    parts = [v]
    parts += target_voxes(-0.75, -0.75, 0.125)
    parts += target_voxes(0.75, -0.75, 0.125)
    parts += arrow_barrel_voxes(-2.875, -1.875, 0.0)
    parts += quiver_rack_voxes(2.75, -0.75, 0.125)
    parts.append(K.banner("arrows", w=18, h=30).at(2.0, -2.175, 3.25))
    return parts


def build_range():
    return V.join(range_voxes(), "SM_ArcheryRange")


def build_target():
    return V.join(target_voxes(), "SM_Target")


def build_arrow_barrel():
    return V.join(arrow_barrel_voxes(), "SM_ArrowBarrel")


# ====================================================================================================== mine cart

def cart_voxes(x=0.0, y=0.0, z=0.0, rot=0):
    """Wooden / iron mine cart heaped with gold ore, 6.25 cm voxels, long axis X, wheels 0.875 m apart (the rail
    gauge of SM_MineCliff). Origin centre of base (the bottom of the wheels)."""
    c = Vox(22, 18, 18, 0.0625, origin=(11, 9, 0), name="cart", seed=2)
    iron, steel = "#6c6c74", "#c4c8ce"
    for wx in (6.5, 15.5):
        for (y0, y1) in ((1, 3), (15, 17)):
            c.cylinder(wx, 2.5, y0, y1, 2.5, "metal", iron, axis="y")
        c.box(wx - 0.5, 3, 2, wx + 0.5, 15, 3, "metal", iron)                # axle
        c.box(wx - 0.5, 0, 2, wx + 0.5, 1, 3, "metal", steel)                # hubs
        c.box(wx - 0.5, 17, 2, wx + 0.5, 18, 3, "metal", steel)
    c.box(2, 4, 4, 20, 14, 5, "beam")                                        # chassis
    c.box(2, 3, 5, 20, 15, 12, "paint", "#aeb2b8")                           # iron tub ...
    c.box(3, 4, 5, 19, 14, 12, "plank")                                      # ... lined with planks
    for (a0, a1) in ((4, 10), (12, 18)):                                     # framed panels on the long sides
        c.clear(a0, 3, 7, a1, 4, 10)
        c.clear(a0, 14, 7, a1, 15, 10)
    c.clear(2, 6, 7, 3, 12, 10)
    c.clear(19, 6, 7, 20, 12, 10)
    for (bx, by) in ((2, 3), (19, 3), (2, 14), (19, 14)):                    # rivets of gold on the corners
        c.set(bx, by, 10, "gold")
        c.set(bx, by, 6, "gold")
    c.box(1, 2, 11, 21, 16, 12, "paint", "#5e6068")                          # rim
    c.box(2, 3, 5, 20, 15, 6, "paint", "#5e6068")                            # bottom band
    c.box(3, 4, 11, 19, 14, 12, "ore")
    c.box(0, 8, 6, 2, 10, 8, "metal", iron)                                  # couplings
    c.box(20, 8, 6, 22, 10, 8, "metal", iron)
    heap = Vox(22, 18, 18, 0.0625, seed=5)
    heap.ellipsoid(11, 9, 11.0, 8.8, 5.6, 5.4, "gold", noise=0.5, noise_scale=3, seed=3)
    heap.clear(0, 0, 0, 22, 18, 12)
    heap.erode("gold", p=0.22, seed=1)
    heap.tint("gold", "#ffe08a", p=0.3, seed=2)
    heap.tint("gold", "#d8a040", p=0.22, seed=7)
    heap.scatter("gold", "ore", p=0.10, seed=3)
    c.stamp(heap, 0, 0, 0)
    return [c.at(x, y, z, rot)]


def build_cart():
    return V.join(cart_voxes(), "SM_MineCart")


# ====================================================================================================== mine cliff

# Rock heights in metres on a 1 m grid; first row is the back (y = +5), last the front edge (y = -5.5).
# Columns run from x = -8 (left) to x = +8. The zeros at the front right are the rail ramp and the steps.
HM = [
    [3.0, 4.5, 4.5, 6.0, 6.0, 6.5, 6.5, 6.5, 6.5, 6.0, 6.0, 5.0, 5.0, 4.0, 3.0, 3.0],
    [3.0, 4.5, 6.0, 6.0, 6.5, 8.0, 8.0, 8.0, 7.5, 6.5, 6.0, 6.0, 5.0, 4.0, 4.0, 3.0],
    [3.0, 4.5, 6.0, 6.5, 6.5, 8.0, 8.0, 8.0, 7.5, 6.5, 6.5, 6.0, 5.0, 5.0, 4.0, 3.0],
    [3.0, 4.5, 4.5, 6.5, 6.5, 7.5, 8.0, 7.5, 7.5, 6.5, 6.5, 6.0, 6.0, 5.0, 4.0, 2.5],
    [3.0, 4.5, 4.5, 4.5, 6.5, 6.5, 6.5, 6.5, 6.5, 6.5, 6.0, 6.0, 6.0, 4.5, 3.0, 2.5],
    [2.0, 3.0, 4.5, 4.5, 4.5, 6.5, 6.5, 6.5, 6.5, 6.0, 6.0, 6.0, 5.5, 4.5, 3.0, 2.5],
    [2.0, 3.0, 3.0, 4.5, 4.5, 4.5, 4.5, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 3.0, 2.5],
    [2.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.5],
    [1.0, 1.0, 3.0, 3.0, 3.0, 1.5, 1.5, 1.0, 1.0, 0, 0, 0, 0, 0.5, 0.5, 1.0],
    [1.0, 1.0, 1.0, 1.5, 1.5, 1.5, 0.5, 0.5, 0.5, 0, 0, 0, 0, 0.5, 0.5, 0.5],
    [0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.25, 0.25, 0, 0, 0, 0, 0, 0.25, 0],
]

NX, NY, NZ = 128, 88, 72          # 16 x 11 x 9 m at 12.5 cm
FLOOR = 8                         # the portal floor / landing: 1 m above the village ground
TX = 84                           # voxel x of the middle of the track and of the portal  (x = +2.5 m)


def track_h(vy):
    """Height (voxels) of the rail bed at voxel row vy: a ramp from the front edge up to the landing."""
    return min(FLOOR, 1 + vy // 3)


def flower_patch(seed):
    f = Vox(8, 8, 8, 0.0625, origin=(4, 4, 0), name="flowers", seed=seed)
    rng = np.random.default_rng(seed)
    heads = ["flower_white", "flower_yellow", "flower_pink", "#b07ae0", "flower_white", "flower_orange"]
    for _ in range(int(rng.integers(3, 6))):
        fx, fy = int(rng.integers(1, 7)), int(rng.integers(1, 7))
        h = int(rng.integers(2, 5))
        f.box(fx, fy, 0, fx + 1, fy + 1, h, "leaves", "#b8e070")
        col = heads[int(rng.integers(0, len(heads)))]
        f.set(fx, fy, h, "paint", col)
        if rng.random() < 0.5:
            for (ax, ay) in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                f.set(fx + ax, fy + ay, h, "paint", col)
            f.set(fx, fy, h, "paint", "flower_yellow" if col != "flower_yellow" else "flower_orange")
    for _ in range(4):
        fx, fy = int(rng.integers(0, 8)), int(rng.integers(0, 8))
        f.box(fx, fy, 0, fx + 1, fy + 1, int(rng.integers(1, 3)), "leaves", "#d0f080")
    return f


def crate_lantern():
    """Two stacked crates with a lantern on top (the lamp beside the portal). Origin bottom centre."""
    v = Vox(8, 8, 20, 0.125, origin=(4, 4, 0), name="crate_lantern")
    v.stamp(K.crate(6), 4, 4, 0)
    v.stamp(K.crate(4), 4, 4, 6)
    K.lantern(v, 4, 4, 10, 4)
    return v


def cliff_voxes():
    v = Vox(NX, NY, NZ, 0.125, origin=(64, 44, 0), name="cliff", seed=7)
    H = np.array(HM[::-1], np.float32)                     # H[row from the front, column]
    rng = np.random.default_rng(5)
    # ---- the rock: 1 m columns, then half-metre blocks added to or cut from their tops
    for r in range(11):
        for c in range(16):
            h = int(round(H[r, c] * 8))
            if h > 0:
                v.box(8 * c, 8 * r, 0, 8 * c + 8, 8 * r + 8, h, "stone")
    for r in range(11):
        for c in range(16):
            h = int(round(H[r, c] * 8))
            if h < 12 or (3 <= r <= 4 and 7 <= c <= 13) or rng.random() > 0.32:
                continue
            qx, qy = int(rng.integers(0, 2)), int(rng.integers(0, 2))
            sx, sy = (4, 4) if rng.random() < 0.55 else ((8, 4) if rng.random() < 0.5 else (4, 8))
            x0 = 8 * c + (qx * 4 if sx == 4 else 0)
            y0 = 8 * r + (qy * 4 if sy == 4 else 0)
            if h + 4 <= 64:
                v.box(x0, y0, h, x0 + sx, y0 + sy, h + 4, "stone")
    v.chunky("stone", cell=8, depth=1, p=0.40, seed=3)
    v.chunky("stone", cell=4, depth=1, p=0.10, seed=9)
    # the left, back and right faces are the edge of the footprint: push some blocks IN so they are not flat
    for a in range(16):
        for zc in range(9):
            if rng.random() < 0.4 and a < 11:
                v.clear(0, 8 * a, 8 * zc, 1, 8 * a + 8, 8 * zc + 8)
            if rng.random() < 0.4 and a < 11:
                v.clear(NX - 1, 8 * a, 8 * zc, NX, 8 * a + 8, 8 * zc + 8)
            if rng.random() < 0.4:
                v.clear(8 * a, NY - 1, 8 * zc, 8 * a + 8, NY, 8 * zc + 8)
    # ---- the landing in front of the portal, and room for the ramp and the steps
    v.clear(56, 24, FLOOR, 112, 39, NZ)
    v.box(56, 24, 0, 112, 40, FLOOR, "stone")
    v.clear(72, 0, 0, 108, 24, NZ)

    # ---- colour of the rock, grass and moss on the ledges
    v.tint("stone", "#f0dcc0", p=0.30, seed=2, cell=8)
    v.tint("stone", "#cfc6c0", p=0.25, seed=4, cell=8)
    v.tint("stone", "#e0c8a4", p=0.12, seed=6, cell=4)
    X, Y, Z = v.grid()
    stone = v.mask("stone")
    top = v.exposed("+z") & stone
    cellr = rng.random((11, 16))
    kind = np.where(cellr < 0.36, 1, np.where(cellr < 0.68, 2, 0))          # 1 grass, 2 moss, 0 bare rock
    kind[H <= 1.0] = 1
    kind[H >= 7.5] = 1
    K8 = np.repeat(np.repeat(kind.T, 8, axis=0), 8, axis=1)[:, :, None]     # (x, y, 1)
    for (code, mat) in ((1, "grass"), (2, "mossy_stone")):
        g = top & (K8 == code)
        for k in range(4):
            lim = g if (k < 2 or code == 2) else (g & (Z >= 56))            # the summit gets whole grass blocks
            sh = np.zeros_like(g)
            sh[:, :, :NZ - k] = lim[:, :, k:]
            v.where(sh & stone, mat)
    # moss creeping down some side blocks
    side_pick = (V._hash3(X // 4, Y // 4, Z // 4, 77) < 0.10) & (Z >= 8)
    v.where(v.mask("stone") & side_pick, "mossy_stone")

    # ---- gold ore in the rock
    ore_pick = (V._hash3(X // 4, Y // 4, Z // 4, 131) < 0.04) & (Z >= 10)
    v.where(v.mask("stone", "mossy_stone") & ore_pick, "ore")
    for (x0, y0, z0, x1, y1, z1) in ((76, 38, 40, 88, 44, 48), (88, 38, 44, 92, 44, 48), (56, 38, 28, 64, 44, 36),
                                     (52, 31, 12, 56, 40, 20), (40, 30, 24, 44, 44, 32), (100, 38, 24, 104, 44, 32),
                                     (24, 16, 12, 32, 22, 20), (64, 38, 40, 68, 44, 44)):
        m = np.zeros(v.n, bool)
        m[x0:x1, y0:y1, z0:z1] = True
        v.where(m & (v.m > 0), "ore")
    for i, d in enumerate(("-y", "+x", "-x")):
        v.scatter("ore", "gold", p=0.28, seed=11 + i, direction=d)
        g = v.exposed(d) & v.mask("gold") & (rng.random(v.n) < 0.45)       # some nuggets stand proud of the face
        axis, sign = "xyz".index(d[1]), (1 if d[0] == "+" else -1)
        out = np.roll(g, sign, axis=axis)
        v.where(out & (v.m == 0), "gold", "#ffe9a0")

    # ---- rail ramp and steps up from the front edge
    for vy in range(0, 24):
        h = track_h(vy)
        v.box(72, vy, 0, 96, vy + 1, h, "stone")
        v.box(72, vy, h, 74, vy + 1, h + 1, "beam")                         # timber kerbs
        v.box(94, vy, h, 96, vy + 1, h + 1, "beam")
    for k in range(4):
        v.box(96, 6 * k, 0, 108, 24, 2 * k + 2, "cobble")
    v.box(108, 0, 0, 110, 24, 2, "stone")
    v.box(108, 10, 0, 110, 24, 6, "stone")
    v.box(108, 18, 0, 110, 24, 10, "stone")

    # ---- the landing surface
    v.box(56, 24, FLOOR - 2, 112, 39, FLOOR, "grass")
    v.box(68, 27, FLOOR - 1, 100, 40, FLOOR, "dirt")
    v.box(96, 24, FLOOR - 1, 108, 28, FLOOR, "cobble")

    # ---- the tunnel: 2.5 m wide and high, 3 m in
    T0, T1, TH = 74, 94, FLOOR + 20
    v.clear(T0, 39, FLOOR, T1, 64, TH)
    v.box(T0 - 1, 40, FLOOR, T0, 65, TH + 1, "paint", DARK)
    v.box(T1, 40, FLOOR, T1 + 1, 65, TH + 1, "paint", DARK)
    v.box(T0 - 1, 40, TH, T1 + 1, 65, TH + 1, "paint", DARK)
    v.box(T0 - 1, 64, FLOOR, T1 + 1, 65, TH + 1, "paint", DARK)
    v.box(T0, 40, FLOOR - 1, T1, 64, FLOOR, "gravel", "#8a7868")
    for vy in (47, 56):                                                     # pit props inside
        v.box(T0, vy, FLOOR, T0 + 2, vy + 2, TH, "post", "#b89878")
        v.box(T1 - 2, vy, FLOOR, T1, vy + 2, TH, "post", "#b89878")
        v.box(T0, vy, TH - 2, T1, vy + 2, TH, "beam", "#b89878")
    v.box(T0, 51, 19, T0 + 2, 53, 21, "glow", "lantern")                    # lamps deep inside
    v.box(T0, 51, 21, T0 + 2, 53, 22, "metal")
    v.box(T1 - 2, 60, 19, T1, 62, 21, "glow", "lantern")
    v.box(T1 - 2, 60, 21, T1, 62, 22, "metal")

    # ---- the track: gravel bed, flush sleepers, two rails; from the tunnel down the ramp to the front edge
    for vy in range(0, 62):
        h = track_h(vy)
        dark = "#8a7868" if vy >= 40 else None
        v.box(76, vy, h - 1, 92, vy + 1, h, "gravel", dark)
        if vy % 6 < 2:
            v.box(77, vy, h - 1, 91, vy + 1, h, "beam", "#c8a888" if vy < 40 else "#a08060")
        v.box(80, vy, h, 81, vy + 1, h + 1, "metal")
        v.box(87, vy, h, 88, vy + 1, h + 1, "metal")
    v.box(79, 62, FLOOR, 89, 63, FLOOR + 3, "beam", "#a08060")              # buffer stop

    # ---- the portal: stone footings, thick posts, double lintel, plank roof with stepped ends
    for (x0, x1) in ((T0 - 6, T0 + 1), (T1 - 1, T1 + 6)):
        v.box(x0, 32, FLOOR, x1, 40, FLOOR + 4, "stone")
        v.box(x0 + 1, 33, FLOOR + 4, x1 - 1, 40, TH, "post")
    v.box(T0 - 7, 32, TH, T1 + 7, 40, TH + 4, "beam")
    v.box(T0 - 10, 31, TH + 4, T1 + 10, 40, TH + 7, "beam", "#e8d0b0")
    for jx in (70, 77, 83, 89, 96):                                         # joist ends
        v.box(jx, 29, TH + 5, jx + 2, 31, TH + 7, "beam")
    RZ = TH + 7                                                             # the plank roof: thick, stepped at its ends
    v.box(68, 27, RZ, 100, 42, RZ + 3, "plank")
    v.box(64, 27, RZ - 1, 68, 42, RZ + 2, "plank")
    v.box(100, 27, RZ - 1, 104, 42, RZ + 2, "plank")
    v.box(61, 27, RZ - 2, 64, 42, RZ, "plank")
    v.box(104, 27, RZ - 2, 107, 42, RZ, "plank")
    v.box(61, 27, RZ - 2, 107, 28, RZ - 1, "beam")
    for bx in (61, 64, 68, 98, 102, 105):                                   # barge blocks standing proud on the steps
        zb = RZ if bx in (61, 105) else RZ + 2 if bx in (64, 102) else RZ + 3
        v.box(bx, 27, zb, bx + 2, 42, zb + 1, "beam")
    for k in range(6):                                                      # braces in the mouth
        v.box(T0 + k, 34, TH - 7 + k, T0 + 2 + k, 38, TH - 5 + k, "beam")
        v.box(T1 - 2 - k, 34, TH - 7 + k, T1 - k, 38, TH - 5 + k, "beam")
    v.scatter("plank", "moss", p=0.30, seed=8, direction="+z", region=(58, 26, RZ - 3, 110, 43, RZ + 5))
    v.scatter("plank", "grass", p=0.10, seed=9, direction="+z", region=(58, 26, RZ - 3, 110, 43, RZ + 5))
    K.wall_lantern(v, T0 - 3, 33, FLOOR + 16)
    K.wall_lantern(v, T1 + 2, 33, FLOOR + 16)

    # ---- things standing by the portal
    v.stamp(K.crate(6), 60, 35, FLOOR)
    v.stamp(K.crate(5), 60, 35, FLOOR + 6)
    v.stamp(K.crate(6), 64, 28, FLOOR, rot=1)
    v.box(62, 26, FLOOR + 6, 66, 30, FLOOR + 7, "ore")                      # a crate of ore
    v.set(63, 27, FLOOR + 7, "gold")
    v.set(64, 29, FLOOR + 7, "gold")
    v.stamp(K.barrel(), 58, 28, FLOOR)
    v.stamp(K.crate(6), 104, 36, FLOOR)                                     # planter crate on the right
    v.box(102, 34, FLOOR + 6, 106, 38, FLOOR + 8, "leaves", "#d8f0a0")
    v.set(103, 35, FLOOR + 8, "paint", "flower_yellow")
    v.set(105, 36, FLOOR + 8, "paint", "flower_white")
    v.stamp(K.barrel(), 109, 34, FLOOR)
    v.stamp(crate_lantern(), 111, 27, FLOOR)
    v.stamp(K.lantern_post(10), 114, 5, 0)                                  # and a lamp at the foot of the steps
    for k in range(10):                                                     # a pickaxe leaning on the left footing
        v.set(70, 31 - k // 4, FLOOR + k, "paint", "wood")
    v.box(68, 29, FLOOR + 9, 73, 30, FLOOR + 10, "metal")

    # ---- flowers and tufts on the grass
    solid = v.m > 0
    tz = (NZ - 1) - np.argmax(solid[:, :, ::-1], axis=2)                    # top solid voxel of every column
    is_grass = np.take_along_axis(v.m, tz[:, :, None], axis=2)[:, :, 0] == V.IDS["grass"]

    def walk_zone(x, y):
        return (68 <= x < 112 and y < 40)

    parts = [v]
    cand = []
    for cx in range(0, NX, 4):
        for cy in range(0, NY, 4):
            if walk_zone(cx, cy):
                continue
            blk_t, blk_g = tz[cx:cx + 4, cy:cy + 4], is_grass[cx:cx + 4, cy:cy + 4]
            if blk_g.all() and (blk_t == blk_t[0, 0]).all():
                cand.append((cx, cy, int(blk_t[0, 0])))
    rng2 = np.random.default_rng(12)
    for i in rng2.permutation(len(cand))[:26]:
        cx, cy, t = cand[i]
        parts.append(flower_patch(int(100 + i)).at((cx + 2 - 64) * 0.125, (cy + 2 - 44) * 0.125, (t + 1) * 0.125))
    tuft = np.argwhere((v.exposed("+z") & v.mask("grass")) & (rng2.random(v.n) < 0.03))
    for (x, y, z) in tuft.tolist():
        if walk_zone(x, y) or z + 3 >= NZ:
            continue
        v.box(x, y, z + 1, x + 1, y + 1, z + 2 + int(rng2.integers(0, 2)), "leaves", "#c8f070")

    # ---- bushes and vines: 25 cm leaf cubes
    L = Vox(64, 44, 40, 0.25, origin=(32, 22, 0), name="cliff_leaves", seed=4)

    def top_cell(xm, ym):
        return (int(tz[int((xm + 8) * 8), int((ym + 5.5) * 8)]) + 1) / 2.0

    for i, (xm, ym, rad) in enumerate(((-6.5, -1.6, 2.2), (-4.4, -3.6, 1.8), (6.6, -0.9, 2.0), (7.0, -4.3, 1.7),
                                        (-2.6, -4.4, 1.6), (-7.2, 2.4, 2.4), (5.6, 1.6, 2.0), (-1.4, 0.4, 1.6),
                                        (-5.5, 0.6, 1.8), (0.5, 3.6, 2.2), (-3.4, 3.4, 1.7))):
        cx, cy, cz = (xm + 8) * 4, (ym + 5.5) * 4, top_cell(xm, ym)
        L.ellipsoid(cx, cy, cz + rad * 0.45, rad * 1.15, rad * 1.15, rad, "leaves", noise=0.5, noise_scale=3, seed=i)
        L.ellipsoid(cx + 0.8, cy - 0.6, cz + rad * 0.9, rad * 0.7, rad * 0.7, rad * 0.7, "leaves", noise=0.4, noise_scale=3, seed=i + 20)
    L.erode("leaves", p=0.18, seed=1)
    L.tint("leaves", "#d8e8a0", p=0.3, seed=2)
    L.tint("leaves", "#b0c890", p=0.2, seed=5)
    # vines over the right-hand end of the portal: from the rock above, across the plank roof, down its corner
    vine = "#dcf5a0"
    L2 = Vox(64, 44, 40, 0.25, origin=(32, 22, 0), name="cliff_vines", seed=6)
    for (cx, z0, z1) in ((45, 21, 24), (46, 20, 24), (47, 19, 24), (48, 19, 22), (49, 19, 23), (50, 19, 22), (51, 20, 22)):
        L2.box(cx, 19, z0, cx + 1, 20, z1, "leaves", vine)                   # on the rock face above the roof
    L2.box(50, 15, 19, 54, 19, 20, "leaves", vine)                           # a mat on the roof's right end
    L2.box(51, 14, 19, 53, 15, 20, "leaves", vine)
    L2.box(52, 17, 20, 53, 19, 21, "leaves", vine)
    for (cx, ln) in ((50, 2), (51, 1), (52, 4), (53, 3)):
        L2.box(cx, 13, 19 - ln, cx + 1, 14, 20, "leaves", vine)              # strands over the front edge
    for (cy, ln) in ((14, 3), (15, 2), (16, 5), (17, 4), (18, 7), (19, 8)):
        L2.box(54, cy, 19 - ln, 55, cy + 1, 20, "leaves", vine)              # ... and down the end
    for (cx, cy, z0, z1) in ((28, 19, 16, 24), (29, 19, 19, 24), (27, 19, 20, 24), (36, 19, 22, 26), (37, 19, 24, 26)):
        L2.box(cx, cy, z0, cx + 1, cy + 1, z1, "leaves", vine)               # strands on the face left of the portal
    L2.erode("leaves", p=0.14, seed=3)
    L2.tint("leaves", "#c0e080", p=0.3, seed=9)
    parts += [L, L2]
    parts += cart_voxes(2.5, -2.2, (FLOOR + 1) * 0.125, rot=1)
    return parts


def build_cliff():
    ob = V.join(cliff_voxes(), "SM_MineCliff")
    return drop_bottom(ob)


# ====================================================================================================== main

def want(name):
    return not ONLY or name in ONLY


def main():
    if want("range"):
        V.reset_scene()
        ob = build_range()
        V.export_gltf(ob)
        preview("range", target=(0, 0, 2.0), az=28, el=32, dist=34, lens=85)
        preview("range_front", target=(0, 0, 1.8), az=8, el=14, dist=24, lens=70)
        preview("range_back", target=(0, 0, 2.0), az=205, el=30, dist=34, lens=85)
    if want("target"):
        V.reset_scene()
        ob = build_target()
        V.export_gltf(ob)
        V.reset_scene()
        a = build_target()
        a.location = (-0.9, 0, 0)
        b = build_arrow_barrel()
        b.location = (0.7, 0, 0)
        c = build_cart()
        c.location = (2.4, 0, 0)
        preview("props", target=(0.8, 0, 0.7), az=28, el=28, dist=11, lens=85)
        preview("props_back", target=(0.8, 0, 0.7), az=200, el=28, dist=11, lens=85)
    if want("barrel"):
        V.reset_scene()
        V.export_gltf(build_arrow_barrel())
    if want("cart"):
        V.reset_scene()
        V.export_gltf(build_cart())
    if want("cliff"):
        V.reset_scene()
        ob = build_cliff()
        V.export_gltf(ob)
        preview("cliff", target=(0, 0, 3.0), az=28, el=32, dist=54, lens=85)
        preview("cliff_portal", target=(2.0, -1.5, 2.4), az=20, el=22, dist=22, lens=85)
        preview("cliff_back", target=(0, 0, 3.2), az=215, el=35, dist=48, lens=85)
        preview("cliff_left", target=(0, 0, 3.2), az=-60, el=30, dist=48, lens=85)


main()
