"""Ground shapes shared by the battle maps' plans (realm_layout.py, highland_layout.py). Pure numpy.

soft_rise   the owner's terrain rule (README, "Terrain rule: no hard edges in open ground"; References/Remake/
            terrain_hard_edge_bad.png): where open ground rises, it rises in shelves of a quarter block that wander and
            step back, never in one long straight bank of dirt. A unit walks up them (a step is half a block) and a
            building's footprint may straddle one (VLBuild::LevelTolerance is 30 cm).
islet       an island off the coast: a rounded square (so that a building's square footprint fits on it), flat on top,
            its rim ragged a little; the coast's ledges and the rocks at its foot come from the plan's coast code as
            for the mainland (References/Remake/lod_detail_good.png: grass on top, a band of dirt over stone, rocks at
            the waterline).
"""
import numpy as np

from town_layout import noise2


def soft_rise(d, X, Y, seed, top=1.0, steps=4, width=(1.4, 3.2)):
    """Height (0 .. top) of ground that rises across the line d = 0 (d: signed metres, > 0 on the high side) in
    `steps` equal shelves. The shelves are centred on the old edge; each is width[0] .. width[1] deep (a slow noise),
    and each wanders on its own, so the risers never run straight or stack into one bank."""
    W = width[0] + (width[1] - width[0]) * noise2(X, Y, 13.0, seed)
    out = np.zeros(np.shape(X))
    for i in range(steps):
        wob = (noise2(X, Y, 5.0 + i, seed + 3 + i) - 0.5) * 2.2
        out = out + ((d + wob) > (i - (steps - 1) / 2.0) * W)
    return out * (top / steps)


def islet(X, Y, x, y, r, rag, p=3.2):
    """Signed metres inside an islet (> 0 on it): a superellipse of half size r (p 2 = round, higher = squarer)."""
    sx, sy = np.abs(X - x) / r, np.abs(Y - y) / r
    e = (sx ** p + sy ** p) ** (1.0 / p)
    return (1.0 - e) * r + rag


def bridge_rect(X, Y, cx, cy, yaw, half_len, half_w):
    """The cells of a bridge's corridor: half_len along it, half_w across. yaw 0 runs north-south, 90 east-west."""
    if abs(yaw) % 180 < 45:
        return (np.abs(X - cx) <= half_w) & (np.abs(Y - cy) <= half_len)
    return (np.abs(X - cx) <= half_len) & (np.abs(Y - cy) <= half_w)
