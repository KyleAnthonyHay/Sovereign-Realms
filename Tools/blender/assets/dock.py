"""dock: the pier of the town (References/Remake/town.png, lower left), and where the grain ship ties up.

  SM_Dock   a timber pier. Origin: the middle of its LAND end, at the top of the deck (the deck top is z = 0, flat
            all over). It runs out along -Y: a walkway 3 m wide and 9 m long, then a cross platform 8 x 3.5 m (a T).
            Log piles go down to z = -4 (the sea lies about 1 m under the deck); the piles at the edges stand proud
            of the deck, several with a stone block and a lantern on top; bollards with rope, a ladder, braces.
            Nothing stands in the way: the clear deck is 2.5 m wide on the walkway, more on the head.
            Sidecar: "moor" [x, y, z, yaw] where SM_Boat floats: alongside the seaward face of the head, its starboard
            side 30 cm off the piles, bow toward +X; "props" crates and barrels for the head's corners.
  SM_Boat   the grain ship: built by boat.py (References/Remake/boat_grain.png), exported here too so that running
            this script keeps it. Origin: its middle on the waterline (z = 0 is the water). Long axis X, bow +X.
            (Until 2026-11-22 it was a 4 m rowing boat moored along the walkway: build_rowboat() below.)

Run:  Blender -b --factory-startup --python Tools/blender/assets/dock.py -- [--no-render] [--cpu] [--samples N]
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import math
import numpy as np
import voxlib as V
import voxkit as K
from voxlib import Vox
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from boat import build as build_boat           # the grain ship (SM_Boat)

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
NO_RENDER = "--no-render" in ARGS
CPU = "--cpu" in ARGS
SAMPLES = int(ARGS[ARGS.index("--samples") + 1]) if "--samples" in ARGS else 32

VX = 0.125
NX, NY, NZ = 76, 108, 50
OX, OY, OZ = 38, 104, 32               # the voxel corner that becomes (0, 0, 0): land end, deck top
WOOD = ["#f6d6aa", "#e2b684", "#eec696", "#d6a674", "#fbe0b8", "#c99a66"]
DARK = ["#c8a078", "#b48c64", "#d4ac84"]

WALK_HW, WALK_LEN = 12, 72             # the walkway: 3 m wide, 9 m long
HEAD_HW, HEAD_LEN = 32, 28             # the head: 8 m wide, 3.5 m deep
WATER = -8                             # the waterline, voxels below the deck top

MOOR = [0.0, -14.8, -1.0, 0.0]          # the grain ship (13.5 m by 3.5 m): along the head's seaward face
PROPS = [
    dict(mesh="SM_CrateStack", pos=[-3.05, -11.55, 0.0], yaw=8.0),
    dict(mesh="SM_Barrel", pos=[-3.35, -9.75, 0.0], yaw=0.0),
    dict(mesh="SM_Crate", pos=[3.2, -11.7, 0.0], yaw=-12.0),
    dict(mesh="SM_Barrel", pos=[2.25, -11.95, 0.0], yaw=40.0),
    dict(mesh="SM_Barrel", pos=[3.4, -10.6, 0.0], yaw=0.0),
]


def build_dock():
    v = Vox(NX, NY, NZ, VX, origin=(OX, OY, OZ), name="dock", seed=3)
    rng = np.random.default_rng(12)
    wood = np.array([V.rgb(c) for c in WOOD])

    def deck(x0, x1, y0, y1, seed):
        """Boards across (along X), two voxels wide, each its own shade, a dark joint line here and there; joists under."""
        r = np.random.default_rng(seed)
        for y in range(y0, y1, 2):
            col = wood[r.integers(0, len(wood))]
            v.box(OX + x0, OY + y, OZ - 2, OX + x1, OY + y + 2, OZ, "plank", col)
            if r.random() < 0.45:                                    # a butt joint: the board is two pieces
                xj = int(r.integers(x0 + 4, x1 - 4))
                v.box(OX + xj, OY + y, OZ - 1, OX + xj + 1, OY + y + 2, OZ, "plank", "#a87848")
            for xn in (x0 + 2, x1 - 3):                               # nail heads
                v.box(OX + xn, OY + y, OZ - 1, OX + xn + 1, OY + y + 1, OZ, "plank", "#9a6c40")
        v.box(OX + x0, OY + y0, OZ - 3, OX + x1, OY + y0 + 1, OZ, "beam")      # edge boards, a little proud below
        v.box(OX + x0, OY + y1 - 1, OZ - 3, OX + x1, OY + y1, OZ, "beam")

    deck(-WALK_HW, WALK_HW, -WALK_LEN, 2, 1)
    deck(-HEAD_HW, HEAD_HW, -WALK_LEN - HEAD_LEN, -WALK_LEN, 2)
    # stringers and joists under the deck
    for x in (-WALK_HW, -1, WALK_HW - 2):
        v.box(OX + x, OY - WALK_LEN - HEAD_LEN, OZ - 5, OX + x + 2, OY + 2, OZ - 2, "beam")
    for x in (-HEAD_HW, HEAD_HW - 2):
        v.box(OX + x, OY - WALK_LEN - HEAD_LEN, OZ - 5, OX + x + 2, OY - WALK_LEN, OZ - 2, "beam")
    for y in (-WALK_LEN - HEAD_LEN, -WALK_LEN - 2):
        v.box(OX - HEAD_HW, OY + y, OZ - 5, OX + HEAD_HW, OY + y + 2, OZ - 2, "beam")

    # ---- piles: logs from the sea bed, at the edges (their middles on the edge line: 25 cm onto the deck at most)
    X, Y, Z = v.grid()

    def pile(x, y, top, lantern=False, r=2.3):
        """(x, y): its middle, voxels from the origin. top: voxels above the deck."""
        cx, cy = OX + x, OY + y
        m = ((X + 0.5 - cx) ** 2 + (Y + 0.5 - cy) ** 2 <= r * r) & (Z < OZ + top)
        v.where(m, "log")
        v.c[m] = V.rgb(DARK[int(rng.integers(0, len(DARK)))])
        wet = m & (Z < OZ + WATER + 2)                               # dark and green at the waterline
        v.c[wet] = V.rgb("#8a8a70")
        v.where(m & (Z >= OZ + WATER - 1) & (Z < OZ + WATER + 1) & (rng.random(v.n) < 0.5), "moss")
        v.where(((X + 0.5 - cx) ** 2 + (Y + 0.5 - cy) ** 2 <= (r + 0.8) ** 2) & (Z >= OZ - 6) & (Z < OZ - 5), "metal")   # an iron band
        if lantern:
            z = OZ + top
            v.box(cx - 3, cy - 3, z, cx + 3, cy + 3, z + 5, "stone", "#e6dfd2")
            v.box(cx - 3, cy - 3, z + 5, cx + 3, cy + 3, z + 6, "stone", "#cfc7ba")
            K.lantern(v, cx, cy, z + 6, 4)
        else:
            v.where(((X + 0.5 - cx) ** 2 + (Y + 0.5 - cy) ** 2 <= (r - 0.9) ** 2) & (Z == OZ + top), "log", "#d4ac84")   # a domed top

    walk_piles = [(-WALK_HW, -3, 4, True), (WALK_HW, -3, 4, True), (-WALK_HW, -26, 5, False), (WALK_HW, -26, 5, False),
                  (-WALK_HW, -49, 4, True), (WALK_HW, -49, 5, False)]
    head_piles = [(-HEAD_HW + 1, -WALK_LEN - 1, 4, True), (HEAD_HW - 1, -WALK_LEN - 1, 4, True),
                  (-HEAD_HW + 1, -WALK_LEN - HEAD_LEN + 1, 4, True), (HEAD_HW - 1, -WALK_LEN - HEAD_LEN + 1, 4, True),
                  (-11, -WALK_LEN - HEAD_LEN + 1, 5, False), (11, -WALK_LEN - HEAD_LEN + 1, 5, False),
                  (-WALK_HW - 1, -WALK_LEN + 1, 5, False), (WALK_HW + 1, -WALK_LEN + 1, 4, True)]
    for (x, y, top, lan) in walk_piles + head_piles:
        pile(x, y, top, lan)
    # cross braces between the piles, above the water
    for (y, x0, x1) in ((-3, -WALK_HW, WALK_HW), (-26, -WALK_HW, WALK_HW), (-49, -WALK_HW, WALK_HW),
                        (-WALK_LEN - HEAD_LEN + 1, -HEAD_HW + 1, HEAD_HW - 1), (-WALK_LEN - 1, -HEAD_HW + 1, HEAD_HW - 1)):
        v.box(OX + x0, OY + y - 1, OZ + WATER + 2, OX + x1, OY + y + 1, OZ + WATER + 4, "beam")
        n = x1 - x0
        for i in range(n):                                            # one diagonal under the deck
            zz = OZ - 6 - int(i * (abs(WATER) - 8 + 4) / float(n))
            v.box(OX + x0 + i, OY + y, zz, OX + x0 + i + 1, OY + y + 1, zz + 2, "beam")
    for x in (-HEAD_HW + 1, HEAD_HW - 1):
        v.box(OX + x - 1, OY - WALK_LEN - HEAD_LEN + 1, OZ + WATER + 2, OX + x + 1, OY - WALK_LEN - 1, OZ + WATER + 4, "beam")

    # ---- bollards with rope, on the edges of the head (the boat ties up here); a ladder down to the water
    def bollard(x, y):
        cx, cy = OX + x, OY + y
        v.box(cx - 1, cy - 1, OZ, cx + 1, cy + 1, OZ + 4, "post")
        v.box(cx - 2, cy - 2, OZ + 3, cx + 2, cy + 2, OZ + 4, "beam")
        v.box(cx - 2, cy - 2, OZ + 1, cx + 2, cy + 2, OZ + 2, "paint", "#c8a467")       # a turn of rope

    bollard(HEAD_HW - 2, -WALK_LEN - 12)
    bollard(-HEAD_HW + 2, -WALK_LEN - 14)
    bollard(WALK_HW - 1, -38)
    bollard(-2, -WALK_LEN - HEAD_LEN + 2)
    # the rope from the walkway's bollard down to the boat
    for i in range(7):
        v.box(OX + WALK_HW + i, OY - 39, OZ - i, OX + WALK_HW + i + 1, OY - 38, OZ - i + 1, "paint", "#c8a467")
    # a coil of rope lying over the edge of the head (it hangs outside the deck)
    for i in range(6):
        v.box(OX - HEAD_HW - 1, OY - WALK_LEN - 20 + i, OZ - 3 - (i % 2), OX - HEAD_HW, OY - WALK_LEN - 19 + i, OZ, "paint", "#c8a467")
    # the ladder, on the east side of the walkway
    lx = OX + WALK_HW
    for y in (-60, -55):
        v.box(lx, OY + y, OZ + WATER - 4, lx + 1, OY + y + 1, OZ + 3, "post")
    for z in range(OZ + WATER - 2, OZ, 3):
        v.box(lx, OY - 60, z, lx + 1, OY - 54, z + 1, "beam")
    # a fishing net and floats hung on the west side
    for i in range(10):
        for k in range(5):
            if (i + k) % 2 == 0:
                v.box(OX - WALK_HW - 1, OY - 20 + i, OZ - 3 - k, OX - WALK_HW, OY - 19 + i, OZ - 2 - k, "paint", "#b9a27a")
    for i in (0, 4, 9):
        v.box(OX - WALK_HW - 1, OY - 20 + i, OZ - 8, OX - WALK_HW, OY - 19 + i, OZ - 7, "paint", "red")
    return V.join([v], "SM_Dock")


def build_rowboat():
    """The rowing boat that was SM_Boat until the grain ship took its place (not exported)."""
    L, W, H = 34, 14, 7
    cx, cy, wl = 17.0, 7.0, 2                    # the waterline is 2 voxels (0.25 m) above the keel
    v = Vox(L, W, H, VX, origin=(cx, cy, wl), name="boat", seed=1)
    X, Y, Z = v.grid()
    t = (X + 0.5 - cx) / 16.0                    # -1 stern .. +1 bow
    half = np.where(t > 0, 6.4 * (1.0 - np.clip(t, 0, 1) ** 2.2) ** 0.75, 6.4 * (1.0 - 0.18 * np.clip(-t, 0, 1) ** 2))
    flare = 0.70 + 0.30 * np.clip((Z + 0.5) / 5.0, 0, 1)
    keel = np.where(t > 0.55, (t - 0.55) / 0.45 * 2.2, 0.0)          # the bottom rises to the bow
    top = 5 + np.where(t > 0.6, 1, 0) + np.where(t < -0.85, 1, 0)    # a little sheer at both ends
    inside = (np.abs(Y + 0.5 - cy) <= half * flare) & (Z >= keel) & (Z < top) & (np.abs(t) <= 1.0)
    hollow = (np.abs(Y + 0.5 - cy) <= half * flare - 1.0) & (Z >= keel + 1) & (t > -0.94) & (np.abs(Y + 0.5 - cy) <= half * flare - 1.0)
    hollow &= t < 0.72                                                # the bow is decked over
    shell = inside & ~hollow
    v.where(shell, "plank")
    strake = np.array([V.rgb(c) for c in ("#e2b684", "#d6a674", "#eec696", "#c99a66", "#e2b684", "#d6a674", "#eec696")])
    v.c[shell] = strake[np.clip(Z, 0, 6)][shell]
    rim = shell & (Z == top - 1)
    v.where(rim, "beam")                                              # the gunwale
    # bottom boards inside, thwarts, a bow seat
    floor = inside & hollow & (Z == 1)
    v.where(floor, "plank", "#c99a66")
    for xs in (9, 19):
        m = inside & hollow & (X >= xs) & (X < xs + 3) & (Z == 3)
        v.where(m, "plank", "#f6d6aa")
    v.where(inside & (t >= 0.72) & (Z == top - 1) & ~rim, "plank", "#f6d6aa")
    v.where(inside & hollow & (t < -0.78) & (Z == 3), "plank", "#f6d6aa")
    # rowlocks and the keel's stem post
    for yy in (0, W - 1):
        pass
    v.box(L - 2, int(cy) - 1, 3, L - 1, int(cy) + 1, 7, "beam")
    for ys in (2, W - 3):
        v.box(15, ys, 5, 16, ys + 1, 6, "metal")
    # two oars lying on the thwarts (fine voxels)
    o = Vox(52, 14, 4, V.TEXEL, origin=(26, 7, 0), name="oars")
    for (y, flip) in ((1, 0), (10, 1)):
        o.box(8, y + 1, 1, 38, y + 2, 2, "post", "#f6d6aa")
        o.box(36, y, 1, 46, y + 3, 2, "plank", "#e2b684")
        o.box(8, y + 1, 1, 11, y + 2, 2, "beam")
    o.at(-0.15, 0.0, (3 + 1 - wl) * VX)
    return V.join([v, o], "SM_Boat")


def render(path, **kw):
    import time
    import bpy
    if CPU:
        bpy.app.handlers.render_pre.append(lambda scene, *a: setattr(scene.cycles, "device", "CPU"))
    for attempt in range(4):
        try:
            return V.render(path, samples=SAMPLES, **kw)
        except RuntimeError as e:
            print("render failed (%s); retrying" % str(e).splitlines()[0][:80])
            time.sleep(15)
            if attempt >= 1:
                bpy.app.handlers.render_pre.append(lambda scene, *a: setattr(scene.cycles, "device", "CPU"))
    raise RuntimeError("could not render " + path)


def sea():
    """A flat blue sheet at the waterline, for the previews."""
    import bpy
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, WATER * VX))
    g = bpy.context.active_object
    g.name = "PreviewGround"                                          # (V.render then adds no green ground)
    m = bpy.data.materials.new("Sea")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.03, 0.12, 0.22, 1)
    b.inputs["Roughness"].default_value = 0.25
    g.data.materials.append(m)


def main():
    V.reset_scene()
    boat = build_boat()
    V.export_gltf(boat, collision="none")
    dock = build_dock()
    V.export_gltf(dock, collision="complex", extra=dict(moor=MOOR, props=PROPS))
    for ob in (dock, boat):
        co = np.array([p.co[:] for p in ob.data.vertices])
        print("%-10s %6d faces  bounds %s .. %s" % (ob.name, ob["voxel_faces"], np.round(co.min(axis=0), 3), np.round(co.max(axis=0), 3)))
    if NO_RENDER:
        return
    boat.location = MOOR[:3]
    boat.rotation_euler = (0, 0, math.radians(MOOR[3]))
    sea()
    for tag, az, el, dist in (("", -35, 34, 62), ("_back", 150, 28, 62), ("_top", 0, 80, 62)):
        render(os.path.join(V.PREVIEWS, "dock%s.png" % tag), target=(0, -6.5, -0.3), az=az, el=el, dist=dist, res=(1200, 900))


main()
