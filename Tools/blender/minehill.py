"""minehill: a mine's hill for the plans (pure numpy: the layout scripts run without Blender too).

A mine never stands alone on flat ground, and never in a drum of rock with sheer sides: References/Remake/mine_mound.png.
Two ways to give it its hill:

  mound_rect(x, y, yaw)     the ground SM_MineMound covers when it is placed at a mine's own place and turn (the mesh of
                            Tools/blender/assets/mine_mound.py). Nobody builds a mine in the game (a Builder claims one
                            where it stands) and the game adds no mound: every mine's ground is made by its plan.
                            The Flatlands place that mesh; a battle map can (MOUNDED in its layout), none does now.
  hill(X, Y, x, y, yaw, ..) the same kind of hill as heights, for a plan that has to shape its own ground (the town: its
                            tower stands too near for the mesh): metres over the mine's floor, cut into terraces as
                            voxlib.terraces cuts the mesh's (a 1 m bank at the foot, which no unit steps onto, then
                            shelves of 0.5 m and 1 m), with a foot that wanders as voxlib.blob_outline's does.
"""
import json
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MESHES = os.path.abspath(os.path.join(HERE, "..", "..", "SourceArt", "Meshes"))
HX, HY = 8.0, 5.5               # SM_MineCliff's half footprint


def _rot(x, y, yaw):
    a = math.radians(yaw)
    return x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)


def mound_bounds():
    """SM_MineMound's own box (x0, y0, x1, y1), metres, front -Y."""
    try:
        (x0, y0, _), (x1, y1, _) = json.load(open(os.path.join(MESHES, "SM_MineMound.json")))["bounds"]
        return (x0, y0, x1, y1)
    except Exception:
        return (-16.0, -4.5, 16.5, 16.5)


def mound_rect(x, y, yaw, scale=1.0):
    """The world rectangle SM_MineMound covers at a mine's place and turn: (x0, y0, x1, y1)."""
    bx0, by0, bx1, by1 = mound_bounds()
    cs = [_rot(a * scale, b * scale, yaw) for a in (bx0, bx1) for b in (by0, by1)]
    return (x + min(c[0] for c in cs), y + min(c[1] for c in cs), x + max(c[0] for c in cs), y + max(c[1] for c in cs))


def outline(n, lo, hi, seed=0, lobes=(2, 3, 5)):
    """How far the hill reaches in each of n directions (as voxlib.blob_outline)."""
    rng = np.random.default_rng(seed)
    a = np.arange(n, dtype=np.float64) * (2.0 * math.pi / n)
    w = np.zeros(n)
    for k in lobes:
        w += np.sin(a * k + rng.uniform(0, 2 * math.pi)) * rng.uniform(0.6, 1.0) / math.sqrt(k)
    w = (w - w.min()) / max(float(w.max() - w.min()), 1e-6)
    return lo + (hi - lo) * w


def terraces(h, levels=None):
    """A smooth height (metres) cut into shelves: 1 m at the foot, then 0.5 m and 1 m in turn (as voxlib.terraces with
    first=2, risers=(1, 2) on 0.5 m blocks). Below half a metre: nothing."""
    if levels is None:
        levels, z, k = [0.0, 1.0], 1.0, 0
        while z < float(np.max(h)) + 1.0:
            z += (0.5, 1.0)[k % 2]
            k += 1
            levels.append(z)
    levels = np.array(levels)
    reach = np.concatenate([[0.0], [levels[1] * 0.5], levels[2:]])
    return levels[np.clip(np.searchsorted(reach, h, side="right") - 1, 0, len(levels) - 1)]


def hill(X, Y, x, y, yaw, crest=6.0, reach=(6.0, 10.0), seed=0, wobble=None):
    """Heights of a mine's hill, metres over the mine's floor (0: none), on the plan's cells X, Y: round the left, back
    and right of the mine at (x, y) turned yaw (front -Y at 0), open in front, highest behind its middle, rolling off in
    terraces to a wandering foot between reach[0] and reach[1] metres out. wobble: a noise field 0..1 on the same cells
    (the terraces' lines wander with it)."""
    a = math.radians(-yaw)
    lx = (X - x) * math.cos(a) - (Y - y) * math.sin(a)
    ly = (X - x) * math.sin(a) + (Y - y) * math.cos(a)
    px, py = np.clip(lx, -HX, HX), np.clip(ly, -HY, HY)
    d = np.hypot(lx - px, ly - py)
    out = outline(96, reach[0], reach[1], seed)
    m = out[(np.floor((np.arctan2(ly + 1.0, lx) / (2 * math.pi)) % 1.0 * 96).astype(np.int64)) % 96]
    s = np.clip(1.0 - d / m, 0.0, 1.0)
    back = np.clip((ly + 2.5) / 5.0, 0.0, 1.0)                    # 0 beside the forecourt, 1 beside the rock's mass and behind it
    e = crest * back * (1.0 - 0.35 * (px / HX) ** 2) * (0.55 + 0.45 * np.minimum(1.0, d / 3.0))
    e = np.maximum(e, 3.25 * back)                                # (never under the rock's own shoulders, which are 3 m)
    v = e * s ** 1.25
    if wobble is not None:
        v = v + (wobble - 0.5) * 1.6 * np.minimum(1.0, d / 1.5) * s
    v = v * np.clip((ly + HY) / 2.0, 0.0, 1.0)                    # the wings run down toward the front
    v = np.where((d <= 0.0) | (ly < -HY), 0.0, np.maximum(v, 0.0))
    return terraces(v)


# ---------------------------------------------------------------------------------------------------- a mine in a wall
# SM_MineCliff's rock, metres on a 1 m grid (Tools/blender/assets/range_mine.py HM): first row the back (y = +5), last
# the front edge (y = -5.5); columns from x = -8 (left) to x = +8. The portal stands on the landing (the 1.0s), the
# rail ramp and the steps come down the zeros at the front right.
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
BAY = (-1.0, 8.0, -0.5)         # the portal's bay in the mine's own space: from x, to x, back to y (its landing, ramp and steps)
# The tunnel behind the portal (range_mine.py: 2.5 m wide and high, 3 m in, dark walls, a roof of the mine's own rock):
# from x, to x, from y, to y, in the mine's own space, a little wider than its walls (the bounds between the plan's cell
# centres, so that a mine and its twin turned half round cut the same cells). The ground is a height field, so
# where it stands higher than the mine's floor there it fills the tunnel and its face closes the mouth (owner,
# 2026-11-24: "no proper hole in the mines"); embed takes it down under the tunnel's floor. The mine's rock is the roof.
TUNNEL = (0.8, 4.2, -1.0, 2.8)
TUNNEL_FLOOR = 0.75             # metres over the mine's floor: just under the tunnel's gravel (0.875 .. 1.0 m)


def embed(X, Y, h, x, y, z, yaw, apron=2.0):
    """A mine set INTO a wall (References/Remake/mine_in_wall.png): returns the ground with the mine at (x, y, z), turned
    yaw, cut into it. The cliff is left as it stands right up to the mine and over it (no pad round it, no trench: the
    wall beside it stays one wall, its terraces run on over the mine's rock, which is buried where the hill is higher
    and stands proud of it where it is lower); only the portal's bay is carved out of the rock, down to the mine's own
    landing, ramp and steps, and `apron` metres of level ground before the bay, for the road. Returns (h, bay mask)."""
    a = math.radians(-yaw)
    lx = (X - x) * math.cos(a) - (Y - y) * math.sin(a)
    ly = (X - x) * math.sin(a) + (Y - y) * math.cos(a)
    H = np.array(HM[::-1], np.float64)                             # H[row from the front, column]
    r = np.clip(np.floor(ly + HY).astype(np.int64), 0, 10)
    c = np.clip(np.floor(lx + HX).astype(np.int64), 0, 15)
    inside = (np.abs(lx) < HX) & (np.abs(ly) < HY)
    bay = inside & (lx > BAY[0]) & (lx < BAY[1]) & (ly < BAY[2])
    out = np.where(bay, np.minimum(h, z + np.maximum(H[r, c] - 0.25, 0.0)), h)
    front = (lx > BAY[0]) & (lx < BAY[1]) & (ly <= -HY) & (ly > -HY - apron)
    out = np.where(front, np.minimum(out, z), out)
    # under the rest of the mine the ground is never below its floor (no gap under its rock where the land falls away)
    tunnel = (lx > TUNNEL[0]) & (lx < TUNNEL[1]) & (ly > TUNNEL[2]) & (ly < TUNNEL[3])
    out = np.where(inside & ~bay & ~tunnel, np.maximum(out, z - 0.25), out)
    # the tunnel is open: no ground in it (its floor, walls and roof are the mine's own)
    out = np.where(tunnel, np.minimum(out, z + TUNNEL_FLOOR), out)
    return out, bay | front
