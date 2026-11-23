"""The woods where nobody can go (the realm's mountain, highland and ridge; the highlands' peaks, spurs, highland and
ridge): where the trees stand. Pure numpy; used by realm_layout.py and highland_layout.py.

These were SM_RealmWoods / SM_HighlandWoods, one mesh of trees of 1 m blocks (a log and a few big leaf cubes) baked by
the terrain scripts. Next to the real trees they read as a coarse, dark, wrong forest (owner, 2026-11-21:
References/Remake/trees_wrong_set.png): they are now the same trees as everywhere else (SM_Tree2_D, a few C), instances
of the level's AVLForest, with their levels of detail (assets/tree_lods.py).

spots() picks one candidate in every GRID x GRID metres (jittered, so the trees do not stand in rows), keeps it where
the ground is wild, grassy, level enough for the trunk and far enough from anywhere people walk that the crown does
not hang over it, and thins it with a slow noise so that the woods come in stands and clearings, as the baked ones did.
"""
import numpy as np

from town_layout import hash2, noise2

GRID = 4.0           # metres: a little under TREE_GAP["D"] (4.8): the crowns meet, as in a wild wood
CLEAR = 2.5          # metres the crown keeps from any ground people walk on


def shrink(mask, k):
    """mask eroded by k cells (a square)."""
    out = mask.copy()
    for ax in (0, 1):
        acc = out.copy()
        for sh in range(1, k + 1):
            acc &= np.roll(out, sh, axis=ax) & np.roll(out, -sh, axis=ax)
        out = acc
    return out


def spots(G, s, cell, grassy, top, keep_out, seed=301, share=(0.45, 1.25)):
    """-> [(x, y, z, kind, scale)] of the wild woods' trees.
    G: the layout's heights() dict; s: its surfaces; cell: the grid's cell (m); grassy: the surface ids trees stand on;
    top: no trees above this height (bare rock); keep_out: extra cells to leave bare (buildings, mounds);
    share: the chance a candidate is kept, from the thinnest stand to the thickest (noise 0 .. 1)."""
    X, Y, h = G["X"], G["Y"], G["h"]
    n = h.shape[0]
    ok = shrink(G["wild"] | ~G["land"], int(round(CLEAR / cell)))         # (not hanging over the ground people walk on)
    ok &= G["wild"] & G["land"] & ~G["path"] & ~G["wet"] & ~keep_out & np.isin(s, grassy) & (h < top)
    k = int(round(GRID / cell))
    nb = n // k
    I, J = np.meshgrid(np.arange(nb), np.arange(nb), indexing="ij")
    ci = (I * k + 2 + (hash2(I, J, seed) * (k - 4)).astype(int)).ravel()
    cj = (J * k + 2 + (hash2(I, J, seed + 2) * (k - 4)).astype(int)).ravel()
    keep = ok[ci, cj]
    ci, cj = ci[keep], cj[keep]
    # the trunk's ground: level to a half block over a metre (the trunk stands on the lower side)
    r = int(round(0.5 / cell))
    lo = np.full(len(ci), 1e9)
    hi = np.full(len(ci), -1e9)
    for di in range(-r, r + 1):
        for dj in range(-r, r + 1):
            v = h[np.clip(ci + di, 0, n - 1), np.clip(cj + dj, 0, n - 1)]
            lo, hi = np.minimum(lo, v), np.maximum(hi, v)
    flat = (hi - lo) <= 0.51                                              # (a half-block step under the trunk: it stands in it)
    ci, cj, lo = ci[flat], cj[flat], lo[flat]
    x, y = X[ci, cj], Y[ci, cj]
    dense = noise2(x, y, 26.0, seed + 10)
    keep = hash2(ci, cj, seed + 4) < share[0] + dense * (share[1] - share[0])
    x, y, z, dense = x[keep], y[keep], lo[keep], dense[keep]
    r1 = hash2(np.round(x * 4), np.round(y * 4), seed + 6)
    r2 = hash2(np.round(x * 4), np.round(y * 4), seed + 8)
    out = []
    for xi, yi, zi, a, b in zip(x, y, z, r1, r2):
        kind = "C" if a < 0.08 else "D"
        out.append((float(xi), float(yi), float(zi), kind, float(0.85 + b * 0.35)))
    return out


def budget(counts, meta):
    """The trees' faces (millions) if every one were drawn at its LOD 0 / LOD 1 / LOD 2 (assets/tree_lods.py; LOD 1 keeps
    the trunk's own mesh): what a view costs lies between, by how far its trees are."""
    def f(name):
        return meta(name).get("faces", 0)
    out = [0.0, 0.0, 0.0]
    for k, n in counts.items():
        out[0] += n * (f("SM_Tree2_%s_Trunk" % k) + f("SM_Tree2_%s_Leaves" % k))
        out[1] += n * (f("SM_Tree2_%s_Trunk" % k) + f("SM_Tree2_%s_Leaves_L1" % k))
        out[2] += n * (f("SM_Tree2_%s_Trunk_L2" % k) + f("SM_Tree2_%s_Leaves_L2" % k))
    return [round(v / 1e6, 3) for v in out]
