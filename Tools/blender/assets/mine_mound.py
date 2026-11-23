"""mine_mound: the hill a gold mine stands in where no cliff backs it (References/Remake/mine_mound.png).

  SM_MineMound      a hill of ground blocks round the left, back and right of SM_MineCliff's 16 x 11 m outcrop, which
                    is set into its front: it rolls off in many shallow terraces one or two blocks high (grass tops,
                    thin dirt edges) to an irregular foot 7 to 13 m out, with stone outcrops and boulders on its
                    slopes, a few trees and bushes on top and flowers about. Open at the front (-Y), where the portal,
                    the rails and the ramp are. Its pivot is the mine's: place it at the mine's own location and
                    rotation.

The mine's rock ends in sheer faces at the edge of its footprint, which only reads right against a cliff. The maps put
this round a mine that stands on open ground (the layouts: Tools/blender/minehill.py, realm_layout.py,
highland_layout.py). The game itself places none: mines are not built in a match, they are claimed where the map has
them (UVLConstruction::ClaimMine).

  * 0.5 m blocks, as the ground. The terraces come from voxlib.terraces and the foot's outline from
    voxlib.blob_outline. The lowest step is 1 m everywhere, so no unit steps onto the hill from the ground (they take
    58 cm at most): the path grid treats it as a wall, like the rock.
  * It reaches half a metre into the footprint (hidden in the rock) so no gap shows where the rock's edge blocks are
    pushed in, and 2 m below the ground, for ground that falls away behind the mine.

Run:  Blender -b --factory-startup --python Tools/blender/assets/mine_mound.py -- [--no-render]
      (with the render: SourceArt/Previews/mine_mound.png, the mound with the mine in it, from the reference's side)
"""
import math, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import voxlib as V
from voxlib import Vox, IDS

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
NO_RENDER = "--no-render" in ARGS

CELL = 0.5
REACH = (7.0, 13.0)             # metres of hill beyond the rock: the foot's outline wanders between these
SKIRT = 2.0                     # metres below the ground
HX, HY = 8.0, 5.5               # the mine's half footprint
CREST = 8.5                     # metres: the hill's top, behind the middle of the rock
# The rock's heights along its edges (range_mine.py HM, metres on a 1 m grid): the left and right columns from the
# front edge to the back, and the back row from left to right.
LEFT = [0, 1.0, 1.0, 2.0, 2.0, 2.0, 3.0, 3.0, 3.0, 3.0, 3.0]
RIGHT = [0, 0.5, 1.0, 1.5, 2.5, 2.5, 2.5, 2.5, 3.0, 3.0, 3.0]
BACK = [3.0, 4.5, 4.5, 6.0, 6.0, 6.5, 6.5, 6.5, 6.5, 6.0, 6.0, 5.0, 5.0, 4.0, 3.0, 3.0]

X0, X1 = -(HX + REACH[1]), HX + REACH[1]
Y0, Y1 = -(HY + 0.5), HY + REACH[1]
NX, NY = int((X1 - X0) / CELL), int((Y1 - Y0) / CELL)
NZ = int((SKIRT + CREST + 9.0) / CELL)          # (room for the trees)
SK = int(SKIRT / CELL)


def shoulder(px, py):
    """The rock's height at a point of its footprint's edge (metres)."""
    row = int(min(max(py + HY, 0), 10.999))                 # rows from the front
    col = int(min(max(px + HX, 0), 15.999))
    hs = [0.0]
    if px <= -HX + 1e-6:
        hs.append(LEFT[row])
    if px >= HX - 1e-6:
        hs.append(RIGHT[row])
    if py >= HY - 1e-6:
        hs.append(BACK[col])
    return max(hs)


def hill_heights():
    """The smooth hill (metres over the ground) on the block grid, 0 where there is none: from the rock's shoulders,
    lifted to the crest behind it, down to nothing at the wandering foot."""
    reach = V.blob_outline(96, REACH[0], REACH[1], seed=31)
    wob = V.noise3((NX, NY, 1), 7.0, seed=4)[:, :, 0]       # slow: the terraces' lines wander
    h = np.zeros((NX, NY), np.float32)
    inside = np.zeros((NX, NY), bool)
    for i in range(NX):
        for j in range(NY):
            x, y = X0 + (i + 0.5) * CELL, Y0 + (j + 0.5) * CELL
            if (abs(x) < HX - 0.5 and abs(y) < HY - 0.5) or (abs(x) < HX and y < HY - 0.5):
                inside[i, j] = True                         # the rock itself
                continue
            if y < -HY:
                continue                                    # the front stays open
            px, py = min(max(x, -HX), HX), min(max(y, -HY), HY)
            d = math.hypot(x - px, y - py)
            ang = math.atan2(y + 1.0, x)
            m = reach[int((ang / (2 * math.pi)) % 1.0 * 96) % 96]
            t = d / m
            if t >= 1.0:
                continue
            # at the rock: its shoulder there, and behind the rock the hill's own crest, highest behind the middle
            e = shoulder(px, py)
            back = max(0.0, min(1.0, (y + 2.5) / 5.0))                   # 0 beside the forecourt, 1 beside the rock's mass and behind it
            crest = CREST * back * (1.0 - 0.35 * (px / HX) ** 2)
            e = max(e - 0.25, crest * (0.55 + 0.45 * min(1.0, d / 3.0)))   # (it tops out a few metres behind the wall)
            # a long roll-off: steeper under the top, an easy foot
            s = 1.0 - t
            v = e * s ** 1.25
            v += (wob[i, j] - 0.5) * 1.6 * min(1.0, d / 1.5) * s
            # toward the front the wings run down, so the way to the portal and the ramp stays clear
            v *= min(1.0, max(0.0, (y + HY) / 2.0))
            if d < 0.75 and y > -HY + 1.0:
                v = max(v, min(shoulder(px, py), 1.0))       # (hard against the rock there is always a bank)
            h[i, j] = max(v, 0.0)
    return h, inside


def tree(v, x, y, z, rng):
    """A blocky tree on the block grid: a trunk of logs, a lumpy crown of leaves (voxel indices; z: its foot)."""
    th = int(rng.integers(5, 8))
    r = float(rng.uniform(2.3, 3.2))
    v.ellipsoid(x + 0.5, y + 0.5, z + th + r * 0.45, r, r, r * 0.9, "leaves", "#5f9a2a", noise=0.45, noise_scale=3.0, seed=int(rng.integers(0, 99)))
    v.ellipsoid(x + 0.5 + rng.uniform(-1, 1), y + 0.5 + rng.uniform(-1, 1), z + th + r * 1.1, r * 0.6, r * 0.6, r * 0.6, "leaves", "#6cab30", noise=0.3, noise_scale=3.0)
    v.box(x, y, z, x + 1, y + 1, z + th, "log", "#6a4220")


def build_mound():
    h, inside = hill_heights()
    top = V.terraces(h, CELL, risers=(1, 2), first=2)        # a 1 m bank at the foot, then shelves of 0.5 m and 1 m
    top[inside] = 0
    # no lone blocks at the foot, no pinnacles
    for _ in range(2):
        pad = np.pad(top, 1)
        nb = np.stack([pad[2:, 1:-1], pad[:-2, 1:-1], pad[1:-1, 2:], pad[1:-1, :-2]])
        top[(top > 0) & ((nb > 0).sum(axis=0) <= 1)] = 0
        top = np.minimum(top, nb.max(axis=0) + 2)
    v = Vox(NX, NY, NZ, CELL, origin=(-X0 / CELL, -Y0 / CELL, SK), name="mound", seed=11)
    rng = np.random.default_rng(23)
    K = np.arange(NZ, dtype=np.int32)[None, None, :]
    solid = (top[:, :, None] > 0) & (K < top[:, :, None] + SK)
    depth = top[:, :, None] + SK - 1 - K
    v.m[:] = np.where(solid, np.where(depth == 0, IDS["grass"], IDS["dirt"]), 0).astype(np.uint8)
    hill = np.argwhere(top > 0)
    # ---- stone outcrops in the slopes (a few blocks of a terrace's edge are rock) and boulders on them
    pad = np.pad(top, 1)
    low = np.minimum.reduce([pad[2:, 1:-1], pad[:-2, 1:-1], pad[1:-1, 2:], pad[1:-1, :-2]])
    edge = np.argwhere((top > 0) & (low < top))             # columns with a bare side
    for (i, j) in edge[rng.choice(len(edge), size=min(16, len(edge)), replace=False)]:
        w, d2 = int(rng.integers(1, 4)), int(rng.integers(1, 3))
        for a in range(i, min(NX, i + w)):
            for b in range(j, min(NY, j + d2)):
                if top[a, b] > 0 and not inside[a, b]:
                    z1 = SK + top[a, b]
                    v.box(a, b, max(0, z1 - int(rng.integers(2, 4))), a + 1, b + 1, z1, "stone")
                    v.set(a, b, z1 - 1, "mossy_stone" if rng.random() < 0.6 else "stone")
    for (i, j) in hill[rng.choice(len(hill), size=14, replace=False)]:
        if top[i, j] >= 2 and not inside[i, j]:
            z1 = SK + top[i, j]
            v.box(i, j, z1, i + int(rng.integers(1, 3)), j + int(rng.integers(1, 3)), z1 + 1, "stone")
            if rng.random() < 0.5:
                v.set(i, j, z1 + 1, "mossy_stone")
    # ---- trees on the top shelves behind the rock, bushes lower down
    high = np.argwhere(top >= max(int(top.max()) - 3, 6))
    planted = []
    for (i, j) in high[rng.permutation(len(high))]:
        y = Y0 + (j + 0.5) * CELL
        if y < HY + 2.0 or any(abs(i - a) + abs(j - b) < 9 for (a, b) in planted) or v.m[i, j, SK + top[i, j]] != 0:
            continue
        tree(v, i, j, SK + top[i, j], rng)
        planted.append((i, j))
        if len(planted) >= 5:
            break
    bushes = 0
    for (i, j) in hill[rng.permutation(len(hill))]:
        if bushes >= 7 or top[i, j] < 2 or any(abs(i - a) + abs(j - b) < 5 for (a, b) in planted):
            continue
        z1 = SK + top[i, j]
        if v.m[i, j, z1] == 0 and top[min(i + 1, NX - 1), j] == top[i, j]:
            v.ellipsoid(i + 1.0, j + 0.5, z1 + 0.7, 1.3, 1.1, 1.0, "leaves", "#7ab428", noise=0.3, noise_scale=2.0, seed=bushes)
            planted.append((i, j))
            bushes += 1
    # ---- flowers and tufts of grass on the shelves (pixel pieces, 12.5 cm)
    F = 4
    f = Vox(NX * F, NY * F, (NZ - 8) * F, CELL / F, origin=(-X0 / CELL * F, -Y0 / CELL * F, SK * F), name="mound_flowers", seed=3)
    heads = ["flower_white", "flower_yellow", "flower_pink", "#b07ae0", "flower_orange"]
    for (i, j) in hill[rng.choice(len(hill), size=min(260, len(hill)), replace=False)]:
        z1 = SK + top[i, j]
        if v.m[i, j, z1] != 0 or v.m[i, j, z1 - 1] != IDS["grass"]:
            continue
        fx, fy, fz = i * F + int(rng.integers(0, F)), j * F + int(rng.integers(0, F)), z1 * F
        if rng.random() < 0.3:
            hgt = int(rng.integers(2, 4))
            f.box(fx, fy, fz, fx + 1, fy + 1, fz + hgt, "leaves", "#b8e070")
            f.set(fx, fy, fz + hgt, "paint", heads[int(rng.integers(0, len(heads)))])
        else:
            f.box(fx, fy, fz, fx + 1, fy + 1, fz + int(rng.integers(1, 3)), "leaves", "#a4d23c")
    return V.join([v, f], "SM_MineMound")


def main():
    V.reset_scene()
    ob = build_mound()
    V.export_gltf(ob)
    if NO_RENDER:
        return
    # the mine in it, for the look: range_mine's own rock (its module builds nothing when asked for none of its parts)
    argv = sys.argv
    sys.argv = argv[:1] + ["--", "--no-render", "--only=none"]
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import range_mine
    sys.argv = argv
    range_mine.build_cliff()
    V.render(os.path.join(V.PREVIEWS, "mine_mound.png"), target=(1.0, 3.0, 2.5), az=24, el=40, dist=120, lens=85, res=(1500, 1046), samples=32)


main()
