"""boat: the grain ship moored at the docks (References/Remake/boat_grain.png). It replaces the rowing boat SM_Boat
that dock.py used to make: same name, same pivot and waterline, so the levels' dock moorings take it as they are.

  SM_Boat   a voxel merchant ship carrying grain, about 13.5 m long (stern to the lantern at the bow), 3.5 m in the beam,
            9.1 m from the waterline to the mast's pennant:
            * the hull: two courses of mossy stone at and under the waterline, timber strakes above them, iron straps
              with rivets down the sides, riveted iron plates and chunky timber caps along the gunwale, a timber wale;
            * the stern castle: a raised deck on the after third, lit windows in its sides, its front and its transom,
              a door from the main deck and steep stairs up to it, a railing round it, two lanterns on posts at its
              front corners, and on it a little timber house with lit windows, a door and a green shingle roof, a
              flagpole behind it with a green wheat pennant;
            * one mast with iron bands, a yard across the ship, a cream square sail (patched panels) billowing forward
              with a big green wheat banner down its middle that hangs below its foot; a green wheat pennant at the
              masthead; rope rigging: forestay, backstays, shrouds, the yard's lifts and braces, the sail's sheets;
            * on deck: stacked crates, grain sacks standing and lying, barrels of grain, coils of rope, a lantern on
              a post by the mast; a lantern hanging from the stem's head at the bow;
            * green wheat banners hanging on the hull, both sides, and on the stern castle.

Pivot: the middle of the hull's length and beam on the WATERLINE (z = 0 is the water; it draws 0.75 m). Long axis X,
bow +X (as the rowing boat's). No collision. The sail, the banners and the pennants are cloth (slot "cloth": they
sway in game). The dock's sidecar "moor" (dock.py MOOR) puts it alongside the seaward face of the pier head.

Run:  Blender -b --factory-startup --python Tools/blender/assets/boat.py -- [--no-render] [--views=a,b] [--samples N] [--cpu] [--lod]
--lod also makes its far level of detail, SourceArt/Meshes/LOD/SM_Boat_L1.gltf, and lists it in lods.json (then in the
editor: python3 Tools/ue_py.py -c "ONLY=['SM_Boat']; exec(open(r'<abs>/Tools/ue/voxel_lods.py').read())"). It is made at
12.5 cm, the hull's own voxel (134k -> 31k triangles), not at the buildings' 25 cm of voxel_lods.py: that loses the sail
and turns the rigging into steps (References/Remake/lod_coarse_bad.png). It is drawn from 317 m in the overview.
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
TASK = "boat"
NAME = "SM_Boat"
REF = os.path.join(V.ROOT, "References", "Remake", "boat_grain.png")

VX = 0.125
TX = V.TEXEL

# colours (the granary's and the dock's)
WOOD_T = "#f0c090"
IRON = "#5e5c64"
STUD = "#a4a8b0"
PLATE = "#8e8c94"
ROPE = "#7a5028"
RIG = ["#d2b27a", "#b8955e"]                   # the rigging's rope, two strands
SACKS = ["#d8b47a", "#c9a46a", "#e2c088", "#bf975c"]
STRAKES = ["#e2b684", "#d6a674", "#eec696", "#c99a66", "#e8bc8a", "#d0a070"]
DECK = ["#f6d6aa", "#e2b684", "#eec696", "#d6a674", "#fbe0b8"]
STONES = ["#cfc8bc", "#bdb6ab", "#e2dbcf", "#c6beb2"]
DARKWOOD = "#b98a5a"

# the plan, in voxels of 12.5 cm about the pivot (x along the ship, bow +x; z up from the waterline)
X0, X1 = -50, 52               # stern transom .. the bow's tip (the stem stands a little beyond)
HW = 13.0                      # the half beam
KEEL = -6                      # the bottom (0.75 m under the water)
DECK_Z = 9                     # the main deck's top
RAIL_Z = 14                    # the bulwark's top amidships (exclusive); it sweeps up 9 more to the bow
CASTLE_X = -22                 # the stern castle's front wall (it covers x < this)
CASTLE_Z = 23                  # its raised deck's top
STEM_Z = 30                    # the top of the stem's head
MAST_X = 1                     # the mast: x 1..7, y -3..3 (75 cm square)
MAST_TOP = 60
YARD_Z = 48                    # the yard's underside
YARD_HW = 23
BRACE = -25.0                  # the yard and sail braced round this far (degrees about Z), as in the picture
OX, OY, OZ = 54, 26, 6         # the hull grid's voxel that is the pivot
NX, NY, NZ = 120, 52, 80
BARREL_R = [5.0, 5.4, 5.7, 5.9, 6.0, 6.0, 6.0, 6.0, 6.0, 6.0, 5.9, 5.7, 5.4, 5.4]
PWOOD = ["#ffffff", "#f0dcc0", "#e2c8a6", "#f6e8d2", "#d8bc98"]


# ---------------------------------------------------------------------------------------------------- pieces
# (copied from granary.py, unchanged: the wheat emblem, the banner, barrels, crates and sacks, the preview render)

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



def B(v, x0, y0, z0, x1, y1, z1, mat, color=None):
    """A box in the hull grid, in voxels about the pivot."""
    v.box(OX + x0, OY + y0, OZ + z0, OX + x1, OY + y1, OZ + z1, mat, color)


def half(x, z):
    """The hull's half beam (voxels) at x (a voxel's middle) and height z: square aft with rounded corners, full amidships,
    fining to the stem at the bow; a little narrower at the bottom (the flare)."""
    x = np.asarray(x, float)
    st = np.clip((X0 + 4.0 - x) / 4.0, 0, 1)
    hw = HW - 2.0 * st ** 2
    bw = np.clip((x - 16.0) / (X1 - 16.0), 0, 1)
    hw = np.where(x > 16, HW * np.clip(1 - bw ** 2, 0, 1) ** 0.85, hw)
    return hw * (0.72 + 0.28 * np.clip((np.asarray(z, float) + 6.0) / 11.0, 0, 1))


def keel(x):
    """The bottom: it rises into the forefoot at the bow and a little under the transom."""
    return KEEL + np.clip((x - (X1 - 23.0)) / 23.0, 0, 1) ** 1.6 * 10.0 + np.clip((X0 + 4.0 - x) / 4.0, 0, 1) * 2.0


def top(x):
    """The top (exclusive) of the bulwark along the ship: the stern castle's raised deck aft, a sheer rising to the bow."""
    return np.where(x < CASTLE_X, CASTLE_Z, RAIL_Z + np.round(np.clip((x - (X1 - 30.0)) / 30.0, 0, 1) ** 1.6 * 9.0))


STRAPS = [X0 + 1, CASTLE_X - 3, -14, -3, 9, 21, 33, 43]       # the iron straps down the sides (their aft edge, 2 voxels wide)


def hull():
    v = Vox(NX, NY, NZ, VX, origin=(OX, OY, OZ), name="hull", seed=2)
    X, Y, Z = v.grid()
    xs, ys, zs = X - OX + 0.5, np.abs(Y - OY + 0.5), Z - OZ
    hw = half(xs, zs)
    inx = (xs > X0) & (xs < X1)
    kb = keel(xs)
    tp = top(xs)
    deck = np.where(xs < CASTLE_X, CASTLE_Z, DECK_Z)
    body = inx & (ys <= hw) & (zs >= kb)
    solid = body & (zs < deck)
    wall = body & (zs >= deck) & (zs < tp) & (ys > hw - 2.0)
    shell = solid | wall
    # ---- timber strakes: two voxels high, planks about a metre long with staggered butts, each its own shade
    v.where(shell, "plank")
    strake = np.array([V.rgb(c) for c in STRAKES], np.uint8)
    k = ((zs // 2) * 3 + (X + (zs // 2) * 5) // 9) % len(STRAKES)
    v.c[shell] = strake[k[shell]]
    # ---- the stone courses: from the keel to 60 cm above the water, chunky and mossy at the waterline
    st = shell & (zs < 6)
    v.where(st, "stone")
    stc = np.array([V.rgb(c) for c in STONES], np.uint8)
    ks = ((X + (zs // 3) * 2) // 4 + zs // 3) % len(STONES)
    v.c[st] = stc[ks[st]]
    # ---- the decks: boards along the ship, two voxels wide, each its own shade
    dk = solid & (zs == deck - 1) & (ys <= hw - 2.0)
    dc = np.array([V.rgb(c) for c in DECK], np.uint8)
    kd = ((Y // 2) * 3 + (X + (Y // 2) * 7) // 12) % len(DECK)
    v.where(dk, "plank")
    v.c[dk] = dc[kd[dk]]
    # ---- one voxel outside the planking: the wales, the straps, the plates
    out1 = inx & (ys > hw) & (ys <= hw + 1.0) & (zs >= kb) & (zs < tp)
    out2 = inx & (ys > hw + 1.0) & (ys <= hw + 2.0) & (zs >= kb) & (zs < tp)
    v.where(out1 & ((zs == 6) | (zs == 7)), "beam", DARKWOOD)                      # the wale over the stone
    v.where(out1 & ((zs == DECK_Z - 1) | (zs == DECK_Z)), "beam", DARKWOOD)        # the wale at the deck
    v.where(out1 & (xs < CASTLE_X) & ((zs == CASTLE_Z - 2) | (zs == CASTLE_Z - 1)), "beam", DARKWOOD)   # ... at the raised deck
    for xp in STRAPS:
        m = out1 & (xs >= xp) & (xs < xp + 2) & (zs >= -1)
        v.where(m, "paint", IRON)
        v.where(out2 & (xs >= xp) & (xs < xp + 1) & (zs >= 0) & (zs % 4 == 1), "paint", STUD)           # rivets
    # riveted plates along the bulwark, between the straps (and on the castle's sides under its rail)
    for a, b_ in zip(STRAPS[:-1], STRAPS[1:]):
        if b_ - a < 8:
            continue
        mid = (a + 2 + b_) // 2
        zp = (DECK_Z + 1, DECK_Z + 4) if a >= CASTLE_X else (CASTLE_Z - 6, CASTLE_Z - 3)
        for xq in ((mid - 4, mid + 1) if a >= CASTLE_X else (mid - 1,)):
            m = out1 & (xs >= xq) & (xs < xq + 3) & (zs >= zp[0]) & (zs < zp[1])
            v.where(m, "paint", PLATE)
            v.where(out2 & (xs >= xq + 1) & (xs < xq + 2) & (zs == zp[0] + 1), "paint", STUD)
    # the gunwale's cap rail: one voxel over the planking each side, and chunky timber caps with a bolt on top
    capz = tp - 1
    cap = inx & (xs >= CASTLE_X) & (ys > hw - 3.0) & (ys <= hw + 1.0) & (zs == capz)
    v.where(cap, "beam", WOOD_T)
    for xc in range(CASTLE_X + 2, X1 - 5, 7):
        m = inx & (xs >= xc) & (xs < xc + 3) & (ys > hw - 3.0) & (ys <= hw + 1.0) & (zs >= capz) & (zs < capz + 2)
        v.where(m, "beam", "#e8b480")
        v.where(m & (zs == capz + 1) & (xs >= xc + 1) & (xs < xc + 2) & (ys > hw - 1.0) & (ys <= hw), "paint", STUD)
    v.chunky("stone", cell=4, depth=1, p=0.25, seed=9)
    v.scatter("stone", "mossy_stone", p=0.18, seed=4, region=(0, 0, OZ - 2, NX, NY, OZ + 2))
    v.scatter("stone", "mossy_stone", p=0.05, seed=5, region=(0, 0, OZ + 2, NX, NY, OZ + 6))

    # ---- the stem: a heavy timber rising out of the bow and curving forward, iron-banded, a lantern hung from its head
    s0 = X1 - 3
    for z in range(int(keel(X1 - 1.0)), STEM_Z):
        off = int(round(3.0 * np.clip((z - 12) / float(STEM_Z - 12), 0, 1) ** 2))
        B(v, s0 + off, -2, z, s0 + 4 + off, 2, z + 1, "beam", "#e2a870")
        if z in (8, 16, 24):
            B(v, s0 + off, -3, z, s0 + 5 + off, 3, z + 1, "paint", IRON)
    B(v, s0 + 2, -3, STEM_Z, s0 + 8, 3, STEM_Z + 2, "beam", "#e8b480")                # its head
    B(v, s0 + 6, -1, STEM_Z - 3, s0 + 11, 1, STEM_Z - 2, "paint", IRON)               # the lantern's bracket
    B(v, s0 + 9, -1, STEM_Z - 5, s0 + 10, 1, STEM_Z - 3, "paint", IRON)
    K.lantern(v, OX + s0 + 10, OY, OZ + STEM_Z - 13, 4)

    # ---- the stern castle: lit windows in its sides and its transom, a door and a window in its front
    for (plane, out) in ((OY + 12, 1), (OY - 13, -1)):
        for a0 in (X0 + 4, CASTLE_X - 10):
            K.window(v, "y", plane, OX + a0, OZ + DECK_Z + 4, w=4, h=7, out=out)
    for a0 in (-8, 3):
        K.window(v, "x", OX + X0, OY + a0, OZ + DECK_Z + 4, w=5, h=7, out=-1)
    K.door(v, "x", OX + CASTLE_X - 1, OY - 4, OZ + DECK_Z, w=8, h=11, out=1)
    K.window(v, "x", OX + CASTLE_X - 1, OY + 7, OZ + DECK_Z + 5, w=4, h=6, out=1)
    # the steep stairs up to it on the starboard side, with stringers and a hand rail
    n = (CASTLE_Z - DECK_Z) // 2
    for k_ in range(1, n + 1):
        x = CASTLE_X + n + 1 - k_
        B(v, x, -11, DECK_Z + 2 * k_ - 1, x + 1, -6, DECK_Z + 2 * k_, "beam", WOOD_T)
        for y in (-12, -6):
            B(v, x, y, DECK_Z + 2 * k_ - 3, x + 1, y + 1, DECK_Z + 2 * k_ + 1, "beam", DARKWOOD)
        B(v, x, -12, DECK_Z + 2 * k_ + 5, x + 1, -11, DECK_Z + 2 * k_ + 6, "beam", WOOD_T)
    B(v, CASTLE_X + n, -12, DECK_Z, CASTLE_X + n + 1, -11, DECK_Z + 8, "post", WOOD_T)
    # the railing round the raised deck (open at the stairs' head)
    RZ0 = CASTLE_Z
    xa, xf = X0 + 1, CASTLE_X - 1                                 # its aft and front rails
    for (x0, x1, y0, y1) in ((xa, xf + 1, -12, -11), (xa, xf + 1, 11, 12), (xa, xa + 1, -12, 12), (xf, xf + 1, -6, 12)):
        B(v, x0, y0, RZ0 + 4, x1, y1, RZ0 + 5, "beam", WOOD_T)
        B(v, x0, y0, RZ0 + 1, x1, y1, RZ0 + 2, "beam", DARKWOOD)
    for x in range(xa, xf + 1, 4):
        for y in (-12, 11):
            B(v, x, y, RZ0, x + 1, y + 1, RZ0 + 6, "post", "#e8b480")
    for y in (-8, -4, 0, 4):
        B(v, xa, y, RZ0, xa + 1, y + 1, RZ0 + 6, "post", "#e8b480")
    for y in (-6, -1, 5):
        B(v, xf, y, RZ0, xf + 1, y + 1, RZ0 + 6, "post", "#e8b480")
    # two lanterns on posts at its front corners
    for y in (-11, 11):
        B(v, xf - 3, y - 1, RZ0, xf - 1, y + 1, RZ0 + 9, "post", "#d8a070")
        B(v, xf - 4, y - 2, RZ0, xf, y + 2, RZ0 + 1, "beam", DARKWOOD)
        K.lantern(v, OX + xf - 2, OY + y, OZ + RZ0 + 9, 4)

    # ---- the house on the raised deck: timber walls, a heavy frame, lit windows, a door, a green shingle roof
    HX0, HX1, HY = X0 + 6, X0 + 22, 9
    B(v, HX0, -HY, RZ0, HX1, HY, RZ0 + 12, "plank", "#f0c898")
    Xh, Yh, Zh = v.grid()
    wallm = (Xh >= OX + HX0) & (Xh < OX + HX1) & (np.abs(Yh - OY + 0.5) < HY) & (Zh >= OZ + RZ0) & (Zh < OZ + RZ0 + 12)
    hk = ((Zh - OZ) // 2 + (Xh + Yh) // 5) % len(STRAKES)
    v.c[wallm] = strake[hk[wallm]]
    for (x0, y0) in ((HX0 - 1, -HY - 1), (HX1 - 1, -HY - 1), (HX0 - 1, HY - 1), (HX1 - 1, HY - 1)):
        B(v, x0, y0, RZ0, x0 + 2, y0 + 2, RZ0 + 13, "post", "#d89a62")               # corner posts
    for z in (RZ0, RZ0 + 11):                                                         # sill and top plate
        B(v, HX0 - 1, -HY - 1, z, HX1 + 1, -HY, z + 1, "beam", DARKWOOD)
        B(v, HX0 - 1, HY, z, HX1 + 1, HY + 1, z + 1, "beam", DARKWOOD)
        B(v, HX0 - 1, -HY, z, HX0, HY, z + 1, "beam", DARKWOOD)
        B(v, HX1, -HY, z, HX1 + 1, HY, z + 1, "beam", DARKWOOD)
    for a0 in (-7, 3):
        K.window(v, "x", OX + HX1 - 1, OY + a0, OZ + RZ0 + 3, w=4, h=6, out=1)        # the front, toward the mast
    K.window(v, "x", OX + HX0, OY - 2, OZ + RZ0 + 3, w=4, h=6, out=-1)
    for a0 in (HX0 + 3, HX0 + 10):
        K.window(v, "y", OY - HY, OX + a0, OZ + RZ0 + 3, w=4, h=6, out=-1)
    K.window(v, "y", OY + HY - 1, OX + HX0 + 3, OZ + RZ0 + 3, w=4, h=6, out=1)
    K.door(v, "y", OY + HY - 1, OX + HX0 + 10, OZ + RZ0, w=5, h=10, out=1)
    rtop = K.gable_roof(v, OX + HX0 - 3, OY - HY - 3, OX + HX1 + 3, OY + HY + 3, OZ + RZ0 + 12, ridge="x", run=4, rise=2,
                        thick=3, tile="roof", trim="beam", ridge_mat="beam")
    B(v, HX0 + 3, -2, rtop - OZ, HX0 + 5, 2, rtop - OZ + 1, "beam", DARKWOOD)        # a ridge block
    # the flagpole behind the house
    B(v, X0, -1, RZ0, X0 + 2, 1, MAST_TOP - 2, "post", "#e8b480")
    B(v, X0 - 1, -2, MAST_TOP - 2, X0 + 3, 2, MAST_TOP - 1, "beam", "#e8b480")
    B(v, X0, -1, RZ0 + 8, X0 + 2, 1, RZ0 + 9, "paint", IRON)

    # ---- the mast, its step, its bands and cap, and the yard with its lashings
    B(v, MAST_X - 2, -5, DECK_Z, MAST_X + 8, 5, DECK_Z + 3, "beam", DARKWOOD)
    for (x, y) in ((MAST_X - 2, -5), (MAST_X + 7, -5), (MAST_X - 2, 4), (MAST_X + 7, 4)):
        B(v, x, y, DECK_Z + 2, x + 1, y + 1, DECK_Z + 3, "paint", STUD)
    B(v, MAST_X, -3, DECK_Z, MAST_X + 6, 3, MAST_TOP, "post", "#e8b07a")
    for z in (DECK_Z + 7, 24, 34, 42, 54):
        B(v, MAST_X - 1, -4, z, MAST_X + 7, 4, z + 1, "paint", IRON)
        B(v, MAST_X + 2, -5, z, MAST_X + 4, -4, z + 1, "paint", STUD)
    B(v, MAST_X - 1, -4, MAST_TOP, MAST_X + 7, 4, MAST_TOP + 2, "beam", DARKWOOD)
    B(v, MAST_X + 2, -1, MAST_TOP + 2, MAST_X + 4, 1, MAST_TOP + 9, "post", "#e8b07a")
    B(v, MAST_X - 1, -4, YARD_Z - 1, MAST_X + 7, 4, YARD_Z, "paint", RIG[1])          # the parrel holding the yard to the mast
    B(v, MAST_X - 1, -4, YARD_Z + 3, MAST_X + 7, 4, YARD_Z + 4, "paint", RIG[1])
    return v



# ---------------------------------------------------------------------------------------------------- the cloth

def sail():
    """The square sail (6.25 cm voxels): cream canvas in patched panels with seams and a bolt rope round it, billowing
    forward (+x), and down its middle a big green banner with a gold wheat sheaf and a gold border that hangs below
    the sail's foot to a point with a gold fringe. Origin: the middle of its head, on the yard's front face."""
    W2, H, TAIL = 44, 46, 12
    # built square to the ship in the mast's frame (x forward from the mast's middle, 6.25 cm voxels), then turned
    v = Vox(26, 2 * W2 + 8, H + TAIL + 8, TX, origin=(0, W2 + 4, H + TAIL), name="sail", seed=3)
    rng = np.random.default_rng(5)
    yy = np.arange(2 * W2) + 0.5 - W2
    jj = np.arange(H + TAIL)
    bel = np.clip(1 - (yy / W2) ** 2, 0, 1) ** 0.7
    dep = np.zeros((2 * W2, H + TAIL), int)
    for j in range(H + TAIL):
        jc = min(j, H - 1)
        dep[:, j] = np.round(5.0 * bel)                       # (a curve across it only: no contour rings)
    panel = ["#efe2c0", "#e9dab4", "#f3e8cc", "#e4d4aa", "#ece0bc"]
    emb = wheat_emblem(21, 30, 26.0)
    BW = 16                                                    # the banner's half width
    for i in range(2 * W2):
        yc = yy[i]
        for j in range(H + TAIL):
            ab = abs(yc)
            if j >= H:                                         # the banner's tail below the foot
                k = j - H
                lim = BW * (1.0 - (k + 1) / float(TAIL + 1))
                if ab >= lim:
                    continue
                edge = ab >= lim - 1.0 or ab >= BW - 1
                col = ("gold" if (i + j) % 2 else "gold_dark") if edge else ("banner_dark" if (i * 7 + j * 3) % 11 == 0 else "banner")
            elif ab < BW and j >= 2:                           # the banner on the sail
                col = "banner_dark" if (i * 7 + j * 3) % 11 == 0 else "banner"
                if ab >= BW - 1.5:
                    col = "gold"
                pj, pi = j - 7, int(yc + 10.5)
                if 0 <= pj < len(emb) and 0 <= pi < len(emb[pj]) and emb[pj][pi] != ".":
                    col = {"T": "gold", "L": "gold_light", "S": "gold_dark", "B": "gold_light"}[emb[pj][pi]]
            else:
                p_ = (int(yc + W2) // 16 + j // 14 + 3) % len(panel)
                col = panel[p_]
                if int(yc + W2) % 16 == 0 or j % 14 == 0:
                    col = "#cfbb90"                            # the seams
                elif (int(yc + W2) % 16 in (1, 15) or j % 14 in (1, 13)) and (i + j) % 3 == 0:
                    col = "#ddc99f"                            # stitching
                if i == 0 or i == 2 * W2 - 1 or j == 0 or j == H - 1:
                    col = "#c2a878"                            # the bolt rope round it
            z = H + TAIL - 1 - j
            d0 = dep[i, j]
            lo = min(d0, dep[max(i - 1, 0), j], dep[min(i + 1, 2 * W2 - 1), j], dep[i, max(j - 1, 0)], dep[i, min(j + 1, H + TAIL - 1)])
            for x in range(lo, d0 + 1):
                v.box(12 + x, i + 4, z, 13 + x, i + 5, z + 1, "paint", col)
    # the yard it hangs from: a squared spar with iron ends and rope lashings, on the mast's front face
    zy = H + TAIL
    v.box(6, 2, zy, 12, 2 * W2 + 6, zy + 6, "beam", "#e8b07a")
    for y in (2, 2 * W2 + 4):
        v.box(5, y, zy - 1, 13, y + 2, zy + 7, "metal", "#8a8890")
    for y in (12, 30, 64, 82):
        v.box(5, y, zy - 1, 13, y + 2, zy + 7, "wool", RIG[0])
    v.hang(region=(0, 0, 0, v.n[0], v.n[1], zy))               # (the cloth only, not the yard)
    t = turned(v, BRACE, "sail")
    a = math.radians(BRACE)
    rot = lambda x, y: (x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a))
    # (in hull voxels about the mast's middle): the yard's ends and the foot's corners, turned with it
    sail.yard_ends = [rot(4.5, sy * (YARD_HW - 1.0)) for sy in (1, -1)]
    sail.corners = [rot((12 + dep[0, H - 1]) / 2.0, sy * (W2 - 1) / 2.0) + ((zy - H) / 2.0,) for sy in (1, -1)]
    return t


def turned(src, ang, name):
    """The grid turned by ang degrees about Z (counter-clockwise from above) about its origin, resampled on a grid of
    the same voxel (each new voxel takes the old one its middle falls in: a thin sheet stays whole, one voxel thick)."""
    a = math.radians(ang)
    c, s_ = math.cos(a), math.sin(a)
    ox, oy, oz = src.origin
    nx, ny, nz = src.n
    cx = [(x * c - y * s_, x * s_ + y * c) for x in (-ox, nx - ox) for y in (-oy, ny - oy)]
    x0, x1 = int(math.floor(min(p[0] for p in cx))) - 1, int(math.ceil(max(p[0] for p in cx))) + 1
    y0, y1 = int(math.floor(min(p[1] for p in cx))) - 1, int(math.ceil(max(p[1] for p in cx))) + 1
    v = Vox(x1 - x0, y1 - y0, nz, src.voxel, origin=(-x0, -y0, oz), name=name, seed=src.seed)
    gx, gy = np.meshgrid(np.arange(x1 - x0) + x0 + 0.5, np.arange(y1 - y0) + y0 + 0.5, indexing="ij")
    ix = np.floor(gx * c + gy * s_ + ox).astype(int)
    iy = np.floor(-gx * s_ + gy * c + oy).astype(int)
    ok = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
    v.m[ok] = src.m[ix[ok], iy[ok]]
    v.c[ok] = src.c[ix[ok], iy[ok]]
    # the cloth's sway, carried over
    for (mask, axis, sign, lo, hi) in src.sways:
        mm = np.zeros(v.n, bool)
        mm[ok] = mask[ix[ok], iy[ok]]
        v.sways.append((mm, axis, sign, lo, hi))
    return v


def pennant(name, w=24, h=12, notch=6):
    """A swallow-tailed pennant (6.25 cm voxels) flying toward +X from its hoist: green with a gold wheat sheaf, its
    tails gold like flames. Origin: the top of the hoist."""
    v = Vox(w, 1, h, TX, origin=(0, 0.5, h), name=name)
    emb = wheat_emblem(7, 10, 30.0)
    for i in range(w):
        for j in range(h):
            k = i - (w - notch)
            if k >= 0 and abs(j + 0.5 - h / 2.0) < (k + 1) / float(notch) * (h / 2.0):
                continue                                       # the swallow tail's notch
            taper = 1 if i > w * 0.5 else 0
            if taper and (j == 0 or j == h - 1) and i > w * 0.75:
                continue
            if i >= w - notch - 2:
                col = "gold_light" if (i + j) % 2 else "gold"
            elif j == 0 or j == h - 1:
                col = "gold_dark"
            else:
                col = "banner_dark" if (i * 5 + j * 3) % 13 == 0 else "banner"
                pj, pi = j - 1, i - 3
                if 0 <= pj < len(emb) and 0 <= pi < len(emb[pj]) and emb[pj][pi] != ".":
                    col = {"T": "gold", "L": "gold_light", "S": "gold_dark", "B": "gold_light"}[emb[pj][pi]]
            v.box(i, 0, h - 1 - j, i + 1, 1, h - j, "paint", col)
    v.fly()
    return v


# ---------------------------------------------------------------------------------------------------- rope

def rigging(corner):
    """The rope (6.25 cm voxels, about 11 cm thick, two strands): forestay, backstays, shrouds, the yard's lifts and
    braces, the sail's sheets. Ends in hull voxels (12.5 cm) about the pivot."""
    nx, ny, nz = 236, 108, 140
    org = (104, 54, -16)                                       # index (104, 54, 0) is (0, 0, 1.0 m)
    v = Vox(nx, ny, nz, TX, origin=org, name="rigging", seed=8)
    cols = [V.rgb(c) for c in RIG]
    oi = np.array(org, float)

    def rope(a, b, sag=0.0, r=0.95):
        a, b = np.array(a, float) * 2.0, np.array(b, float) * 2.0         # hull voxels -> fine voxels
        n = int(np.linalg.norm(b - a) / 0.35) + 2
        for s, t in enumerate(np.linspace(0.0, 1.0, n)):
            p = a + (b - a) * t
            p[2] -= sag * 2.0 * 4.0 * t * (1 - t)
            q = p + oi
            base = np.floor(q - 1.5).astype(int)
            for dx in range(4):
                for dy in range(4):
                    for dz in range(4):
                        c = base + (dx, dy, dz)
                        if np.linalg.norm(c + 0.5 - q) <= r and 0 <= c[0] < nx and 0 <= c[1] < ny and 0 <= c[2] < nz:
                            v.m[c[0], c[1], c[2]] = V.IDS["paint"]
                            v.c[c[0], c[1], c[2]] = cols[(s // 4) % 2]

    mt = (MAST_X + 3, 0, MAST_TOP - 1)
    rope(mt, (X1 + 3.0, 0, STEM_Z + 1.5), 0.6)                                         # forestay to the stem's head
    for sy in (1, -1):
        for xs_ in (-4.0, 9.0):
            rope((MAST_X + 3, sy * 3.5, YARD_Z + 5), (xs_, sy * 12.8, RAIL_Z - 0.5), 0.3)           # shrouds to the gunwale
    for k_, sy in enumerate((1, -1)):
        ex, ey = sail.yard_ends[k_]
        rope((MAST_X + 3 + ex, ey, YARD_Z + 1.5), (CASTLE_X - 2.0, sy * 11.5, CASTLE_Z + 5.5), 1.4)   # braces aft
        cx_, cy_, cz_ = sail.corners[k_]
        rope((MAST_X + 3 + cx_, cy_, YARD_Z - cz_ + 0.5), (-12.0, sy * 12.8, RAIL_Z - 0.5), 0.8)       # sheets
    return v


# ---------------------------------------------------------------------------------------------------- the cargo

def coil(v, cx, cy, z0, r=5.0, turns=2):
    """A flat coil of rope on the deck."""
    X, Y, Z = v.grid()
    d = np.hypot(X + 0.5 - cx, Y + 0.5 - cy)
    for t in range(turns):
        rr = r - t * 1.2
        m = (d <= rr) & (d > rr - 1.6) & (Z == z0 + t)
        v.where(m, "paint", RIG[t % 2])
    v.where((d <= r - 2.6) & (Z == z0), "paint", RIG[1])


def hung_coil(name):
    """Two loops of rope hanging from the gunwale over the hull's side (6.25 cm voxels), facing -Y. Origin: the middle
    of the top, where it hangs from."""
    v = Vox(20, 2, 22, TX, origin=(10, 1, 22), name=name)
    for (rx, rz, c) in ((7.5, 16.0, RIG[0]), (6.0, 13.0, RIG[1])):
        for i in range(20):
            for k in range(22):
                dx, dz = (i + 0.5 - 10) / rx, (k + 0.5 - 22) / rz
                d = dx * dx + dz * dz
                if 0.72 <= d <= 1.0 and k < 22:
                    v.box(i, 0, k, i + 1, 2, k + 1, "paint", c)
    v.box(8, 0, 19, 12, 2, 22, "paint", RIG[1])               # the turns over the rail
    return v


def cargo():
    """Crates, grain sacks, barrels of grain, rope and a lantern on a post, on the main deck (6.25 cm voxels). Origin:
    the middle of the ship on the deck's top."""
    v = Vox(130, 48, 44, TX, origin=(36, 24, 0), name="cargo", seed=6)
    o = lambda x, y: (x + 36, y + 24)
    # aft of the mast, on the port side: a stack of crates
    for (x, y, z, s, fl) in ((-30, 9, 0, 12, False), (-18, 9, 0, 12, True), (-30, 9, 12, 12, True), (-29, -1, 0, 10, False),
                             (-6, 10, 0, 11, False), (-18, 10, 12, 11, False), (-25, 9, 24, 11, True), (-29, -1, 10, 10, True)):
        crate(v, *o(x, y), z, s=s, seed=abs(x + y) % 5, flip=fl)
    sack(v, *o(-14, -4), 0, 4.4, 4.0, SACKS[2])
    sack_lying(v, *o(-6, 2), 0, "y", SACKS[1], length=5.5, fat=4.0, end=1)
    sack(v, *o(-4, -12), 0, 4.2, 3.8, SACKS[0], open_top=True)
    coil(v, *o(-14, -16), 0, 4.5)
    # round the mast
    sack(v, *o(21, -14), 0, 4.4, 4.0, SACKS[3])
    sack(v, *o(21, 14), 0, 4.0, 3.8, SACKS[1])
    barrel(v, *o(10, 15), 0, seed=3, full="wheat")
    sack(v, *o(0, 15), 11, 4.0, 3.6, SACKS[2])
    # the lantern on a post by the mast
    px, py = o(24, -18)
    v.box(px - 1, py - 1, 0, px + 1, py + 1, 22, "post", "#d8a070")
    v.box(px - 3, py - 3, 0, px + 3, py + 3, 2, "beam", DARKWOOD)
    v.box(px - 3, py - 3, 22, px + 3, py + 3, 23, "paint", IRON)
    v.box(px - 3, py - 3, 23, px + 3, py + 3, 29, "glow", "lantern")
    for dx in (px - 3, px + 2):
        for dy in (py - 3, py + 2):
            v.box(dx, dy, 23, dx + 1, dy + 1, 29, "paint", IRON)
    v.box(px - 3, py - 3, 29, px + 3, py + 3, 30, "paint", IRON)
    v.box(px - 1, py - 1, 30, px + 1, py + 1, 32, "paint", IRON)
    # fore of the mast: crates, sacks heaped on them and round them, a barrel of grain, a coil of rope
    for (x, y, z, s, fl) in ((30, -20, 0, 12, False), (42, -18, 0, 11, True), (34, -19, 12, 11, True), (30, 8, 0, 12, True),
                             (30, 8, 12, 11, False), (42, -6, 0, 10, False)):
        crate(v, *o(x, y), z, s=s, seed=abs(x + y) % 5, flip=fl)
    sack(v, *o(36, 14), 23, 4.0, 3.6, SACKS[2])
    sack(v, *o(39, -13), 23, 4.2, 3.8, SACKS[0])
    sack_lying(v, *o(48, 0), 0, "y", SACKS[0], length=6.0, fat=4.2, end=-1)
    sack(v, *o(56, -8), 0, 4.4, 4.0, SACKS[1], open_top=True)
    sack(v, *o(58, 6), 0, 4.2, 3.8, SACKS[3])
    sack(v, *o(46, 12), 0, 4.0, 3.8, SACKS[0])
    sack_lying(v, *o(48, 1), 6, "x", SACKS[2], length=5.5, fat=3.8, end=1)
    barrel(v, *o(66, -2), 0, seed=6, full="wheat")
    coil(v, *o(12, -15), 0, 4.0)
    return v


# ---------------------------------------------------------------------------------------------------- assembly

def build():
    v = hull()
    parts = [v]
    m = lambda q: q * VX
    s = sail()
    parts.append(s.at(m(MAST_X + 3), 0.0, m(YARD_Z)))
    parts.append(rigging(None))
    parts.append(cargo().at(0.0, 0.0, m(DECK_Z)))
    parts.append(pennant("pennantMast", 26, 12, 6).at(m(MAST_X + 2), 0.0, m(MAST_TOP + 9), rot=2))
    parts.append(pennant("pennantStern", 24, 11, 6).at(m(X0 + 1), 0.0, m(MAST_TOP - 3), rot=2))
    # banners hanging on the hull, both sides: amidships and on the bow (from the gunwale), and on the stern castle
    k = 0
    for (x, w, h, tip) in ((3.5, 10, 16, 4), (28.0, 10, 14, 4), (CASTLE_X - 16.5, 10, 20, 4)):
        ho = float(half(np.array([x]), 10)[0]) + 1.0
        zt = float(top(np.array([x]))[0])
        for side in (-1, 1):
            b_ = banner(w=w, h=h, tip=tip, shape="point", name="banner%d" % k, emblem=wheat_emblem(7, 11, 30.0), ey0=3)
            parts.append(b_.at(m(x), side * (m(ho) + TX), m(zt), rot=0 if side < 0 else 2))
            k += 1
    # a coil of rope hung over each side amidships
    for side in (-1, 1):
        ho = float(half(np.array([-9.0]), 10)[0]) + 1.0
        parts.append(hung_coil("coil%d" % (side > 0)).at(m(-9.0), side * (m(ho) + TX), m(RAIL_Z), rot=0 if side < 0 else 2))
    for q in parts:
        a = q.mesh_arrays()
        print("  part %-12s %6d faces" % (q.name, 0 if a is None else len(a["verts"])))
    ob = V.join(parts, NAME)
    co = np.array([p.co[:] for p in ob.data.vertices])
    print("SM_Boat bounds %s .. %s" % (np.round(co.min(axis=0), 3), np.round(co.max(axis=0), 3)))
    return ob


# ---------------------------------------------------------------------------------------------------- previews

def sea():
    """A flat blue sheet at the waterline, for the previews (named so that render() adds no grass)."""
    import bpy
    bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, 0.0))
    g = bpy.context.active_object
    g.name = "PreviewGround"
    mt = bpy.data.materials.new("Sea")
    mt.use_nodes = True
    bs = mt.node_tree.nodes["Principled BSDF"]
    bs.inputs["Base Color"].default_value = (0.03, 0.12, 0.22, 1)
    bs.inputs["Roughness"].default_value = 0.25
    g.data.materials.append(mt)


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


def make_lod(voxel=0.125):
    """LOD 1 at the hull's own voxel, with voxel_lods.py's rebuild (see the top of this file)."""
    import json
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voxel_lods.py")
    ns = {"__file__": p, "__name__": "voxel_lods"}
    exec(compile(open(p).read().replace("\nmain()\n", "\n"), p, "exec"), ns)
    src = ns["read"](os.path.join(V.MESHES, NAME + ".gltf"))
    lob, tris = ns["rebuild"](NAME, voxel, 1, src, ns["TOL"]["buildings"])
    file = "%s_L1.gltf" % NAME
    V.export_gltf(lob, path=os.path.join(ns["OUT"], file), collision="none", extra=dict(lod_of=NAME, voxel=voxel, triangles=tris))
    bp = os.path.join(ns["OUT"], "lods.json")
    book = json.load(open(bp)) if os.path.exists(bp) else {}
    book[NAME] = dict(set="buildings", triangles=len(src[0]), levels=[dict(level=1, file=file, voxel=voxel, triangles=tris,
                      slots=[mt.name.replace("Vox_", "") for mt in lob.data.materials])])
    with open(bp, "w") as fh:
        json.dump(book, fh, indent=1)
    print("LOD %s: %d -> %d triangles" % (NAME, len(src[0]), tris))


def main():
    V.reset_scene()
    ob = build()
    print("faces", ob["voxel_faces"])
    V.export_gltf(ob, collision="none")
    if NO_RENDER:
        if "--lod" in ARGS:
            make_lod()
        return
    sea()
    preview("ref", target=(0, 0, 3.4), az=30, el=17, dist=60, lens=85, res=(1600, 900), sun_az=-130, sun_el=28)
    preview("three", target=(0, 0, 3.4), az=35, el=28, dist=38, lens=50, res=(1280, 860), sun_az=-130, sun_el=30)
    preview("front", target=(0, 0, 3.8), az=90, el=8, dist=34, lens=50, res=(1280, 860), sun_az=-150, sun_el=30)
    preview("side", target=(0, 0, 3.8), az=0, el=6, dist=36, lens=50, res=(1280, 860), sun_az=-150, sun_el=30)
    preview("back", target=(0, 0, 3.4), az=-140, el=26, dist=38, lens=50, res=(1280, 860), sun_az=-130, sun_el=30)
    preview("play", target=(0, 0, 1.5), az=28, el=48, dist=120, lens=50, res=(1280, 860), sun_az=-130, sun_el=35)
    if "--lod" in ARGS:
        make_lod()                                             # (last: it clears the scene)


if __name__ == "__main__":
    main()
