"""Taller trees for the voxel village: SM_Tree2_<A..D>_Trunk / _Leaves.

    Blender -b --factory-startup --python Tools/blender/assets/trees_tall.py -- [--no-render] [--no-export]
                                                                               [--only A,B] [--views compare_a,grove_new,...]

The same four trees as nature.py (same seeds, colours, 0.25 m leaf cubes, 0.125 m trunk voxels), built about a third
taller so that the crowns clear the hero camera's line of sight: the trunks and the crown bases go up the most, the
crowns grow in proportion (a little less in width than in height, which also keeps the face counts down). The old
SM_Tree_* meshes and nature.py are left alone; the canopy / trunk code below is a copy of nature.py's.

Two meshes share one origin (the centre of the trunk base at ground level): the trunk collides ("complex"), the
leaves do not ("none").
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import math
import numpy as np
import voxlib as V
import voxkit as K
from voxlib import Vox

import bpy

LV = 0.25            # leaf cubes
TV = 0.125           # trunks, rocks
PV = 0.0625          # flowers, grass, ferns
SKIRT = 2            # trunk / rock voxels below the ground (0.25 m), so they sit on uneven terrain without a gap

N6 = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]


# ---------------------------------------------------------------------------------------------------- small helpers

def hsh(x, y, z, seed=0):
    """Integer lattice hash -> float 0..1 (arrays or scalars)."""
    x, y, z = np.asarray(x, np.int64), np.asarray(y, np.int64), np.asarray(z, np.int64)
    h = (x * 73856093) ^ (y * 19349663) ^ (z * 83492791) ^ (int(seed) * 2654435761)
    h = (h ^ (h >> 13)) * 1274126177
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF).astype(np.float32) / float(0xFFFFFF)


def shift(a, d, fill=0):
    """a sampled at p + d (outside the grid = fill)."""
    out = np.full_like(a, fill)
    src, dst = [slice(None)] * 3, [slice(None)] * 3
    for ax, s in enumerate(d):
        if s > 0:
            dst[ax], src[ax] = slice(0, -s), slice(s, None)
        elif s < 0:
            dst[ax], src[ax] = slice(-s, None), slice(0, s)
    out[tuple(dst)] = a[tuple(src)]
    return out


def open_faces(solid):
    """Number of the six neighbours that are air, for every solid voxel (0 elsewhere)."""
    n = np.zeros(solid.shape, np.int8)
    for d in N6:
        n += ~shift(solid, d, False)
    return n * solid


def dilate(solid):
    out = solid.copy()
    for d in N6:
        out |= shift(solid, d, False)
    return out


def ramp(t, stops):
    """t (array, 0..1) -> uint8 colours along a list of colour stops."""
    cols = np.array([V.rgb(c) for c in stops], np.float32)
    x = np.clip(t, 0.0, 1.0) * (len(stops) - 1)
    i = np.clip(np.floor(x).astype(int), 0, len(stops) - 2)
    f = (x - i)[..., None]
    return np.round(cols[i] * (1 - f) + cols[i + 1] * f).astype(np.uint8)


def up2(a):
    """A 0.25 m array on the 0.125 m grid."""
    return np.repeat(np.repeat(np.repeat(a, 2, 0), 2, 1), 2, 2)


def _face_cells(a, v):
    """For the faces of mesh_arrays(): (axis, cell on the low side, cell on the high side) in voxel indices."""
    p = a["verts"] / v.voxel + np.array(v.origin, np.float32)
    axis = np.argmin(p.max(1) - p.min(1), axis=1)
    c = p.mean(1)
    ar = np.arange(len(c))
    hi = np.floor(c + 1e-3).astype(np.int64)
    hi[ar, axis] = np.rint(c[ar, axis]).astype(np.int64)
    lo = hi.copy()
    lo[ar, axis] -= 1
    return axis, lo, hi


def _lookup(arr, idx, fill=False):
    """arr[idx] with out-of-range cells = fill. idx: (F, 3)."""
    n = np.array(arr.shape)
    ok = np.all((idx >= 0) & (idx < n), axis=1)
    j = np.clip(idx, 0, n - 1)
    out = arr[j[:, 0], j[:, 1], j[:, 2]]
    return np.where(ok, out, fill)


def _keep(a, sel):
    if not sel.any():
        return None
    return dict(verts=a["verts"][sel], uvs=a["uvs"][sel], cols=a["cols"][sel], tris=a["tris"][sel],
                slot=a["slot"][sel], slots=a["slots"])


class LaceVox(Vox):
    """A 0.125 m grid laid exactly over a 0.25 m one (twice the size, twice the origin). Its faces are culled and
    corner-shaded against the coarse voxels as if both were one grid, so cutting the shell of a canopy into small
    pieces costs only the faces you can see."""
    coarse = None

    def mesh_arrays(self):
        own = self.m > 0
        if self.coarse is None or not own.any():
            return Vox.mesh_arrays(self)
        mine = self.m
        self.m = np.where(own, mine, up2(self.coarse.m))
        try:
            a = Vox.mesh_arrays(self)
        finally:
            self.m = mine
        if a is None:
            return None
        both = own | (up2(self.coarse.m) > 0)
        axis, lo, hi = _face_cells(a, self)
        owner = np.where(_lookup(both, lo)[:, None], lo, hi)
        return _keep(a, _lookup(own, owner))


class CoarseVox(Vox):
    """The 0.25 m grid under a LaceVox: drops the faces that the small pieces cover completely."""
    lace = None

    def mesh_arrays(self):
        a = Vox.mesh_arrays(self)
        if a is None or self.lace is None:
            return a
        f = self.lace.m > 0
        solid = self.m > 0
        axis, lo, hi = _face_cells(a, self)
        lo_owner = _lookup(solid, lo)
        other = np.where(lo_owner[:, None], hi, lo)                 # the air cell the face looks into
        covered = np.zeros(len(axis), bool)
        for ax in range(3):
            for low_side in (True, False):                          # which half of the air cell touches the face
                sl = [slice(None)] * 3
                sl[ax] = slice(0, None, 2) if low_side else slice(1, None, 2)
                layer = f[tuple(sl)]
                o = [0, 1, 2]
                o.remove(ax)
                full = layer
                for b in o:                                         # all four small voxels of that half present
                    s0, s1 = [slice(None)] * 3, [slice(None)] * 3
                    s0[b], s1[b] = slice(0, None, 2), slice(1, None, 2)
                    full = full[tuple(s0)] & full[tuple(s1)]
                pick = (axis == ax) & (lo_owner == low_side)
                if pick.any():
                    covered[pick] = _lookup(full, other[pick])
        return _keep(a, ~covered)


# ---------------------------------------------------------------------------------------------------- leaves

LEAF_RAMP = ["#4f7c5c", "#79a66e", "#aed088", "#e2ee9a", "#fff0a0"]       # shade under the canopy -> sunlit top


class Canopy:
    """Leaf masses made of many overlapping squarish, flat-bottomed pads ("puffs") on a 0.25 m grid."""

    def __init__(self, width, height, seed, name="leaves"):
        n = int(math.ceil(width / LV / 2.0)) * 2
        nz = int(math.ceil(height / LV))
        self.v = CoarseVox(n, n, nz, LV, origin=(n / 2, n / 2, 0), name=name, seed=seed)
        self.rng = np.random.default_rng(seed)
        self.d = np.full(self.v.n, 9.0, np.float32)
        self.tone = np.zeros(self.v.n, np.float32)
        self.rel = np.zeros(self.v.n, np.float32)
        self.lace = None

    def puff(self, x, y, z, rx, ry=None, rz=None, p=3.6, pz=3.0, flat=1.0, tone=0.0):
        """One pad: centre and radii in metres (tree space). p / pz: 2 = round, 4 = boxy (plan / profile).
        flat < 1 makes the underside shallower than the top."""
        ry = rx if ry is None else ry
        rz = rx * 0.55 if rz is None else rz
        n, o = self.v.n, self.v.origin
        c = np.array([x / LV + o[0], y / LV + o[1], z / LV + o[2]])
        r = np.array([rx, ry, rz]) / LV
        lo = np.maximum(0, np.floor(c - r * 1.5 - 2)).astype(int)
        hi = np.minimum(n, np.ceil(c + r * 1.5 + 3)).astype(int)
        if np.any(hi <= lo):
            return
        gx, gy, gz = np.meshgrid(*[np.arange(lo[i], hi[i]) + 0.5 - c[i] for i in range(3)], indexing="ij")
        h = (np.abs(gx / r[0]) ** p + np.abs(gy / r[1]) ** p) ** (1.0 / p)
        zn = np.where(gz >= 0, gz / r[2], gz / (r[2] * flat))
        d = ((h ** pz + np.abs(zn) ** pz) ** (1.0 / pz)).astype(np.float32)
        sl = tuple(slice(lo[i], hi[i]) for i in range(3))
        take = d < self.d[sl]
        self.d[sl][take] = d[take]
        self.tone[sl][take] = tone
        self.rel[sl][take] = np.clip(zn, -1.5, 1.5)[take]

    def solidify(self, noise=0.5, scale=3.0):
        nz = V.noise3(self.v.n, scale, self.v.seed + 3, octaves=3)
        solid = (self.d + (nz - 0.5) * 2.0 * noise) <= 1.0
        self.v.m[solid] = V.IDS["leaves"]
        return self

    def ragged(self, top=0.11, side=0.12, under=0.26, edge=0.30, strays=0.03, hang=0.10):
        """Break the surface up. top: single-cube holes in the tops (they read as the dark gaps between leaf cubes);
        side / under: the same on the flanks and undersides; edge: extra loss at rims and corners, which is what
        makes the outline lacy; strays: cubes added just outside; hang: little clusters hanging underneath."""
        v, rng = self.v, self.rng
        leaf = V.IDS["leaves"]
        solid = v.m > 0
        nopen = open_faces(solid)
        up = ~shift(solid, (0, 0, 1), False)
        dn = ~shift(solid, (0, 0, -1), False)
        holes = np.clip((V.noise3(v.n, 2.5, v.seed + 31, octaves=2) - 0.36) * 5.0, 0.15, 1.8)        # holes come in patches
        p = np.where(up, top * holes, np.where(dn, under, side)) + edge * np.clip(nopen - 2, 0, 2) / 2.0
        v.m[solid & (nopen > 0) & (rng.random(v.n) < p)] = 0
        solid = v.m > 0
        v.m[dilate(solid) & ~solid & (rng.random(v.n) < strays)] = leaf
        solid = v.m > 0
        under_ = solid & ~shift(solid, (0, 0, -1), False) & (rng.random(v.n) < hang)
        length = rng.integers(1, 4, v.n)
        for k in (1, 2, 3):
            put = shift(under_ & (length >= k), (0, 0, k), False) & ~(v.m > 0)
            v.m[put] = leaf
        self.prune()
        return self

    def prune(self, core=9):
        """Remove bits that float free of the canopy (keep whatever is joined, face to face, to a solid mass)."""
        v = self.v
        solid = v.m > 0
        near = np.zeros(v.n, np.int8)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    if dx or dy or dz:
                        near += shift(solid, (dx, dy, dz), False)
        reach = solid & (near >= core)
        for _ in range(200):
            grown = dilate(reach) & solid
            if grown.sum() == reach.sum():
                break
            reach = grown
        v.m[solid & ~reach] = 0
        return self

    def shade(self, lo=0.0, hi=1.0, ramp_cols=LEAF_RAMP):
        """Tint every leaf cube by how much sky it sees: tops bright and warm, the bottoms of holes, the gaps between
        tiers and the undersides dark and cool."""
        v = self.v
        solid = v.m > 0
        sf = solid.astype(np.float32)

        def mean_xy(a, r):
            out = np.zeros_like(a)
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    out += shift(a, (dx, dy, 0), 0.0)
            return out / float((2 * r + 1) ** 2)

        occ1 = mean_xy(shift(sf, (0, 0, 1), 0.0), 1)                                  # the ring just above: pits
        occ2 = mean_xy((shift(sf, (0, 0, 2), 0.0) + shift(sf, (0, 0, 3), 0.0) + shift(sf, (0, 0, 4), 0.0)) / 3.0, 2)
        far = np.zeros_like(sf)
        for k in range(5, 13):
            far = np.maximum(far, shift(sf, (0, 0, k), 0.0))
        far = mean_xy(far, 1)                                                         # a tier overhead
        sky = 1.0 - np.clip(0.55 * occ1 + 0.35 * occ2 + 0.35 * far, 0, 1)
        rim = mean_xy(1.0 - sf, 2)                                                    # open to the side: rims, hanging bits
        rim = np.clip((rim - 0.30) / 0.45, 0, 1)
        sky = np.maximum(sky, 0.62 * rim)
        zidx = np.arange(v.n[2], dtype=np.float32)[None, None, :]
        zs = np.argwhere(solid.any(axis=(0, 1)))
        z0, z1 = (float(zs.min()), float(zs.max())) if len(zs) else (0.0, 1.0)
        hgt = (zidx - z0) / max(1.0, z1 - z0)
        t = 0.04 + 0.82 * sky + 0.08 * np.clip(self.rel, -1, 1) + 0.14 * (hgt - 0.5) + self.tone
        t = t + (hsh(*np.indices(v.n), v.seed + 21) - 0.5) * 0.22
        v.c[solid] = ramp(lo + (hi - lo) * t, ramp_cols)[solid]
        return self

    def cut_lace(self, share=0.2, keep=0.70, tabs=0.06):
        """Cut a share of the surface cubes into 0.125 m pieces with notches (and add small tabs sticking out), on a
        second grid. Cubes at edges and corners and under open sky are the likeliest."""
        v, rng = self.v, self.rng
        solid = v.m > 0
        nopen = open_faces(solid)
        sky = ~shift(solid, (0, 0, 1), False)
        prob = share * (0.15 + 0.6 * np.clip(nopen - 1, 0, 3) + 0.15 * sky)
        chosen = solid & (nopen > 0) & (rng.random(v.n) < prob)
        n2 = tuple(2 * k for k in v.n)
        f = LaceVox(n2[0], n2[1], n2[2], LV / 2, origin=tuple(2 * o for o in v.origin), name=v.name + "_lace", seed=v.seed + 1)
        leaf = V.IDS["leaves"]
        fc = up2(chosen)
        pieces = fc & (rng.random(n2) < keep)
        f.m[pieces] = leaf
        f.c[:] = up2(v.c)
        # tabs: single small voxels on the faces of cubes that stay whole
        if tabs > 0:
            air = ~solid
            col = v.c.copy()
            edge = np.zeros(v.n, bool)
            for d in N6:
                s = shift(solid & ~chosen, d, False) & air & ~edge
                col[s] = shift(v.c, d, 255)[s]
                edge |= s
            cand = up2(edge & (rng.random(v.n) < tabs * 4))
            fs = up2(solid & ~chosen)
            touch = np.zeros(n2, bool)
            for d in N6:
                touch |= shift(fs, d, False)
            tab = cand & touch & (rng.random(n2) < 0.30)
            f.m[tab] = leaf
            f.c[tab] = up2(col)[tab]
        v.m[chosen] = 0
        f.coarse = v
        v.lace = f
        self.lace = f
        return f

    def grids(self):
        return [self.v] + ([self.lace] if self.lace is not None else [])


def leaf_mass(can, pads, sub=(2, 4), rim=(2, 4), hangers=0):
    """Add pads (x, y, z, rx, ry, rz, tone): each is a thick boxy slab with smaller slabs stacked on top of it,
    thinner ones stepping out and down from its rim, and little clusters hanging underneath."""
    rng = can.rng
    for (x, y, z, rx, ry, rz, tone) in pads:
        can.puff(x, y, z, rx, ry, rz, p=rng.uniform(2.8, 3.8), pz=2.5, flat=0.5, tone=tone)
        for _ in range(int(rng.integers(sub[0], sub[1] + 1))):            # stacked on top
            a = rng.uniform(0, 2 * math.pi)
            k = rng.uniform(0.0, 0.55)
            r = min(rx, ry) * rng.uniform(0.42, 0.68)
            t = rng.uniform(0.3, 0.45)
            can.puff(x + math.cos(a) * rx * k, y + math.sin(a) * ry * k, z + rz * 0.8 + t * rng.uniform(0.2, 0.7), r, r * rng.uniform(0.8, 1.25), t,
                     p=rng.uniform(3.0, 4.2), pz=3.2, tone=tone + rng.uniform(0.02, 0.08))
        for _ in range(int(rng.integers(rim[0], rim[1] + 1))):            # stepping out from the rim
            a = rng.uniform(0, 2 * math.pi)
            r = min(rx, ry) * rng.uniform(0.3, 0.5)
            t = rng.uniform(0.25, 0.4)
            can.puff(x + math.cos(a) * rx * 0.95, y + math.sin(a) * ry * 0.95, z + rz * rng.uniform(-0.7, 0.3), r, r * rng.uniform(0.8, 1.25), t,
                     p=rng.uniform(2.8, 3.8), pz=3.0, tone=tone - 0.03)
        for _ in range(hangers):
            a = rng.uniform(0, 2 * math.pi)
            r = rng.uniform(0.3, 0.5)
            can.puff(x + math.cos(a) * rx * 0.8, y + math.sin(a) * ry * 0.8, z - rz - rng.uniform(0.0, 0.3), r, r, rng.uniform(0.3, 0.5),
                     p=2.8, pz=2.6, tone=tone - 0.06)


# ---------------------------------------------------------------------------------------------------- trunks

BARK_TINTS = ["#ffffff", "#ffe9cf", "#f1dcc4", "#ffdcae", "#dcc6ae", "#fff3e2", "#c9b39b", "#f6d2a2"]
IVY_TINTS = ["#fffbc2", "#e6f0a8", "#c4dc98", "#f3f6b4", "#a9c88c"]


class Trunk:
    """A thick squarish trunk of bark plates with stepped roots, limbs, stubs, moss and ivy, on a 0.125 m grid."""

    def __init__(self, height, r0, r1, seed, reach=2.0, name="trunk", flare=(7, 0.22, 2.0)):
        self.flare = flare                                            # root flare: (height in voxels, slope, most)
        self.H = int(round(height / TV))
        self.r0, self.r1 = r0 / TV, r1 / TV
        half = int(math.ceil(max(reach, r0 + 1.2) / TV)) + 4
        self.v = Vox(2 * half, 2 * half, self.H + SKIRT + 2, TV, origin=(half, half, SKIRT), name=name, seed=seed)
        self.c = half
        self.rng = np.random.default_rng(seed)
        self.seed = seed
        self._column()

    def radius(self, z):
        """Half-width of the trunk (voxels) at height z (voxels above ground)."""
        t = np.clip(np.asarray(z, np.float32) / self.H, 0, 1)
        return self.r0 + (self.r1 - self.r0) * t ** 0.8 + np.clip((self.flare[0] - np.asarray(z, np.float32)) * self.flare[1], 0, self.flare[2])

    def _column(self):
        v, s = self.v, self.seed
        X, Y, Z = v.grid()
        x, y, z = X + 0.5 - self.c, Y + 0.5 - self.c, Z - SKIRT
        p = 3.4
        d = (np.abs(x) ** p + np.abs(y) ** p) ** (1.0 / p)
        ci, cj = (X + 1) // 2, (Y + 1) // 2                           # bark plates: 2 voxel (25 cm) wide strips
        seg_len = 5 + (hsh(ci, cj, 0, s) * 10).astype(np.int64)       # 0.6 .. 1.8 m long
        seg = (Z + (hsh(ci, cj, 1, s) * 16).astype(np.int64)) // seg_len
        hp = hsh(ci * 31 + cj * 17, seg, cj - ci, s + 2)
        add = np.select([hp < 0.20, hp < 0.56, hp < 0.88], [-1.0, 0.0, 1.0], 2.0)
        groove = (hsh(X, Y, 3, s) < 0.10) & (hsh(X, Y, Z // 9, s + 4) < 0.7)      # narrow fissures
        solid = (d <= self.radius(z) + add - groove - 0.5) & (z < self.H)
        v.m[solid] = V.IDS["log"]
        tint = np.array([V.rgb(c) for c in BARK_TINTS], np.uint8)
        v.c[solid] = tint[(hsh(ci, cj, seg, s + 5) * len(tint)).astype(int) % len(tint)][solid]

    def _tint(self):
        return BARK_TINTS[int(self.rng.integers(0, len(BARK_TINTS)))]

    def roots(self, n=6, steps=(9, 6, 4, 2), w=4, step=3, start=0.0):
        """Stepped block roots: staircases of bark cubes running out from the foot of the trunk."""
        v, rng, c = self.v, self.rng, self.c
        dirs = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
        order = list(rng.permutation(8))[:n]
        for k in order:
            dx, dy = dirs[k]
            diag = 0.74 if dx and dy else 1.0
            off = int(rng.integers(-2, 3))                            # sideways shift so roots are not all centred
            m = len(steps) - int(rng.integers(0, 2))
            for i in range(m):
                dist = (self.r0 - 1.5 + start + i * step) * diag
                h = max(1, steps[i] + int(rng.integers(-1, 2)))
                ww = w if i < 2 else max(2, w - 1)
                px = c + dx * dist + (-dy) * off * (0 if dx and dy else 1)
                py = c + dy * dist + (dx) * off * (0 if dx and dy else 1)
                x0, y0 = int(round(px - ww / 2.0)), int(round(py - ww / 2.0))
                v.box(x0, y0, 0, x0 + ww, y0 + ww, SKIRT + h, "log", self._tint())
                if rng.random() < 0.35 and i < m - 1:                 # a smaller cube sitting on the step
                    v.box(x0 + int(rng.integers(0, 2)), y0 + int(rng.integers(0, 2)), SKIRT + h, x0 + ww - 1, y0 + ww - 1, SKIRT + h + 2, "log", self._tint())
        return self

    def limb(self, p0, p1, t0=5, t1=2, lattice=2):
        """A thick stepped branch from p0 to p1 (metres, tree space): it runs out first and then climbs."""
        v, c = self.v, self.c
        a = np.array(p0, np.float32) / TV
        b = np.array(p1, np.float32) / TV
        n = int(np.abs(b - a).max()) + 1
        col = self._tint()
        for i in range(n + 1):
            t = i / n
            q = np.array([a[0] + (b[0] - a[0]) * t ** 0.75, a[1] + (b[1] - a[1]) * t ** 0.75, a[2] + (b[2] - a[2]) * t ** 1.5])
            q = np.round(q / lattice) * lattice
            th = int(round(t0 + (t1 - t0) * t))
            x0, y0, z0 = int(c + q[0] - th // 2), int(c + q[1] - th // 2), int(SKIRT + q[2] - th // 2)
            if i % 5 == 0:
                col = self._tint()
            v.box(x0, y0, z0, x0 + th, y0 + th, z0 + th, "log", col)
        return self

    def stub(self, height, direction, length=4, th=3):
        """A short broken branch on the bare trunk. direction: (dx, dy) of -1/0/1."""
        v, c = self.v, self.c
        z = int(round(height / TV))
        r = float(self.radius(z))
        dx, dy = direction
        diag = 0.8 if dx and dy else 1.0
        for i in range(length):
            dist = (r - 1 + i) * diag
            x0, y0 = int(round(c + dx * dist - th / 2.0)), int(round(c + dy * dist - th / 2.0))
            zz = SKIRT + z + (1 if i >= length - 2 else 0)
            tt = th if i < length - 1 else max(2, th - 1)
            v.box(x0, y0, zz, x0 + tt, y0 + tt, zz + tt, "log", self._tint())
        return self

    def collar(self, height, grow=2, depth=4):
        """A stepped swelling round the trunk (the corbel under the first limbs)."""
        v, c = self.v, self.c
        z = int(round(height / TV))
        for i in range(grow):
            r = float(self.radius(z)) + grow - i
            r = int(round(r))
            v.box(c - r, c - r + 2, SKIRT + z - (i + 1) * depth // 2, c + r, c + r - 2, SKIRT + z + depth, "log", self._tint())
            v.box(c - r + 2, c - r, SKIRT + z - (i + 1) * depth // 2, c + r - 2, c + r, SKIRT + z + depth, "log", self._tint())
        return self

    def moss(self, top=2.2, amount=0.45, side=(0.3, 1.0)):
        """Green patches on the bark low down (thicker on one side) and on the tops of the roots."""
        v, s = self.v, self.seed
        X, Y, Z = v.grid()
        solid = v.m > 0
        nz = V.noise3(v.n, 5, s + 9, octaves=2)
        z = (Z - SKIRT) * TV
        facing = ((X - self.c) * side[0] + (Y - self.c) * side[1]) / (self.r0 * 1.2)
        want = nz + 0.10 * np.clip(facing, -1, 1) - 0.30 * np.clip(z / top, 0, 1.5)
        surf = solid & (open_faces(solid) > 0) & (z >= 0)
        patch = surf & (want > 0.62 - 0.12 * amount) & (z < top)
        tops = surf & ~shift(solid, (0, 0, 1), False) & (z < 1.3) & (nz > 0.58 - 0.15 * amount)
        both = patch | tops
        v.m[both] = V.IDS["leaves"]
        v.c[both] = ramp(hsh(X, Y, Z, s + 6) * 0.6 + 0.3, ["#8fb07c", "#c4dc98", "#e6f0a8"])[both]
        return self

    def ivy(self, strands=5, top=2.6, side=(0.5, -1.0), spread=0.9):
        """Ivy: leaf voxels creeping up the bark from the roots, standing one or two voxels proud of it."""
        v, rng = self.v, self.rng
        leaf = V.IDS["leaves"]
        bark = v.m > 0
        shell = dilate(bark) & ~bark
        nx, ny, nz = v.n
        ang0 = math.atan2(side[1], side[0])
        cols = [V.rgb(c) for c in IVY_TINTS]
        for _ in range(strands):
            ang = ang0 + rng.uniform(-spread, spread)
            # start: walk in from outside along the ground until the shell is reached
            p = None
            for dist in np.arange(self.r0 + 16, 0, -0.5):
                x, y = int(self.c + math.cos(ang) * dist), int(self.c + math.sin(ang) * dist)
                z = SKIRT + int(rng.integers(0, 3))
                if 0 <= x < nx and 0 <= y < ny and shell[x, y, z]:
                    p = (x, y, z)
                    break
            if p is None:
                continue
            ztop = SKIRT + int(top / TV * rng.uniform(0.45, 1.0))
            for _step in range(400):
                x, y, z = p
                v.m[x, y, z] = leaf
                v.c[x, y, z] = cols[int(rng.integers(0, len(cols)))]
                for d in N6:                                           # leaves beside the stem
                    q = (x + d[0], y + d[1], z + d[2])
                    if not (0 <= q[0] < nx and 0 <= q[1] < ny and SKIRT <= q[2] < nz):
                        continue
                    if bark[q]:
                        continue
                    r = rng.random()
                    if (shell[q] and r < 0.24) or (not shell[q] and r < 0.07):
                        v.m[q] = leaf
                        v.c[q] = cols[int(rng.integers(0, len(cols)))]
                if z >= ztop:
                    break
                moves = [(0, 0, 1)] * 5 + [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)] + [(1, 0, 1), (-1, 0, 1), (0, 1, 1), (0, -1, 1)] * 2
                rng.shuffle(moves)
                for d in moves:
                    q = (x + d[0], y + d[1], z + d[2])
                    if 0 <= q[0] < nx and 0 <= q[1] < ny and q[2] < nz and shell[q]:
                        p = q
                        break
                else:
                    break
        return self

    def finish(self, rough=0.22, rough_top=12):
        """Rough the limbs and roots up a little, and cap every upward/downward bark face with dark wood (a log's
        top is pale end grain, which is wrong on bark)."""
        v = self.v
        if rough > 0:
            v.chunky("log", cell=2, depth=1, p=rough, seed=self.seed + 7, region=(0, 0, 0, v.n[0], v.n[1], SKIRT + rough_top))
        log = v.mask("log")
        solid = v.m > 0
        cap = log & (~shift(solid, (0, 0, 1), False) | ~shift(solid, (0, 0, -1), False))
        v.m[cap] = V.IDS["beam"]
        return v


# ---------------------------------------------------------------------------------------------------- the four trees

def ring(rng, n, radius, z, r, rz, a0=None, squash=1.0, centre=(0.0, 0.0), jit=0.22, tone=0.0):
    """n pads round the trunk: (x, y, z, rx, ry, rz, tone)."""
    a0 = rng.uniform(0, 2 * math.pi) if a0 is None else a0
    out = []
    for i in range(n):
        a = a0 + (i + rng.uniform(-jit, jit)) * 2 * math.pi / n
        rad = radius * rng.uniform(0.82, 1.12)
        rr = r * rng.uniform(0.85, 1.15)
        out.append((centre[0] + math.cos(a) * rad, centre[1] + math.sin(a) * rad * squash, z + rng.uniform(-0.35, 0.35),
                    rr, rr * rng.uniform(0.85, 1.15), rz * rng.uniform(0.9, 1.15), tone + rng.uniform(-0.10, 0.10)))
    return out

OLD_TREES = {            # nature.py's trees as they are (for the old-vs-new previews and the numbers)
    # a broad spreading oak: three wide tiers, the widest lowest
    "A": dict(seed=11, width=14.5, height=14.0, trunk=(10.0, 0.86, 0.36), roots=7, lace=0.5,
              tiers=[dict(n=3, radius=3.1, z=5.7, r=1.5, rz=0.8, hang=2, jit=0.3),
                     dict(n=6, radius=4.0, z=7.6, r=2.0, rz=0.95, hang=2),
                     dict(n=4, radius=2.3, z=9.7, r=2.0, rz=0.95, hang=1),
                     dict(n=2, radius=0.8, z=11.6, r=1.8, rz=0.9)],
              limbs=(0, 1), limb_t=(6, 2), stubs=[(2.6, (1, 0)), (3.3, (-1, -1)), (1.9, (0, 1)), (4.5, (-1, 0), 5, 4), (4.9, (0, -1), 5, 4), (4.3, (1, 1), 4, 4)],
              moss=dict(top=2.2, amount=0.3), ivy=dict(strands=4, top=3.0, side=(0.6, -1.0))),
    # taller and narrower, leaning tiers with gaps between them and one low bough to the side
    "B": dict(seed=23, width=13.0, height=15.0, trunk=(11.4, 0.78, 0.30), roots=6, lace=0.5,
              tiers=[dict(n=1, radius=3.4, z=4.9, r=1.7, rz=0.8, a0=3.4, hang=3),
                     dict(n=4, radius=3.1, z=6.9, r=1.8, rz=0.9, hang=2, centre=(0.4, 0.0), a0=0.4),
                     dict(n=4, radius=2.6, z=9.0, r=1.85, rz=0.9, hang=2, centre=(0.9, 0.2)),
                     dict(n=3, radius=1.6, z=11.1, r=1.75, rz=0.9, hang=1, centre=(1.2, 0.3)),
                     dict(n=1, radius=0.2, z=12.9, r=1.6, rz=0.95, centre=(1.3, 0.3))],
              limbs=(0, 1, 2), limb_t=(5, 2), stubs=[(3.0, (-1, 0)), (2.2, (1, 1)), (5.6, (0, -1), 5, 4), (4.1, (1, -1), 4, 3)],
              moss=dict(top=2.0, amount=0.25, side=(-1.0, 0.4)), ivy=dict(strands=3, top=3.6, side=(-0.8, -0.8))),
    # medium: a compact round-headed tree
    "C": dict(seed=37, width=9.5, height=9.4, trunk=(6.6, 0.48, 0.20), roots=5, lace=0.6,
              tiers=[dict(n=4, radius=2.1, z=3.9, r=1.4, rz=0.75, hang=2),
                     dict(n=3, radius=1.5, z=5.5, r=1.5, rz=0.8, hang=1),
                     dict(n=1, radius=0.2, z=7.0, r=1.5, rz=0.85)],
              limbs=(0, 1), limb_t=(3, 2), stubs=[(1.8, (1, 0)), (2.5, (-1, 1), 3, 3)], root_steps=(6, 4, 2), root_w=3,
              moss=dict(top=1.6, amount=0.25), ivy=dict(strands=3, top=2.0, side=(1.0, -0.5))),
    # small: a young tree
    "D": dict(seed=51, width=6.0, height=6.2, trunk=(4.2, 0.27, 0.13), roots=4, lace=0.8,
              tiers=[dict(n=3, radius=1.15, z=2.8, r=1.0, rz=0.6, hang=1),
                     dict(n=2, radius=0.7, z=3.9, r=1.05, rz=0.65, hang=1),
                     dict(n=1, radius=0.1, z=4.8, r=0.9, rz=0.65)],
              limbs=(0,), limb_t=(2, 1), stubs=[], root_steps=(4, 2), root_w=2, root_step=2,
              moss=dict(top=1.0, amount=0.2), ivy=dict(strands=2, top=1.2, side=(0.2, -1.0))),
}


# How much taller. Heights x SZ; the lowest tier a little more (the crown base is what the camera has to clear);
# widths and trunk girth x SR, which keeps the crowns from looking like lollipops without paying for a third more
# width in leaf faces as well.
SZ, SZ_BASE, SR, SRZ = 1.35, 1.42, 1.20, 1.20

EXTRA = {           # per tree: more stubs for the longer bare trunk (height m, direction[, length, thickness]), lace share
    "A": dict(stubs=[(1.3, (-1, 1)), (5.2, (1, -1), 5, 4)], lace=0.42),
    "B": dict(stubs=[(1.4, (0, -1)), (5.0, (-1, 1), 4, 3)], lace=0.42),
    "C": dict(stubs=[(1.1, (0, -1))], lace=0.5),
    "D": dict(stubs=[], lace=0.55),
}


def taller(key):
    """The spec of tall tree A / B / C / D, derived from the old one."""
    o = OLD_TREES[key]
    e = EXTRA[key]
    zs = [t["z"] for t in o["tiers"]]
    z0, z1 = min(zs), max(zs)
    tiers = []
    for t in o["tiers"]:
        n = dict(t)
        f = (t["z"] - z0) / max(1e-3, z1 - z0)
        n["z"] = round(t["z"] * (SZ_BASE + (SZ - SZ_BASE) * f), 3)
        n["radius"], n["r"], n["rz"] = t["radius"] * SR, t["r"] * SR, t["rz"] * SRZ
        if "centre" in t:
            n["centre"] = (t["centre"][0] * SR, t["centre"][1] * SR)
        tiers.append(n)
    th, r0, r1 = o["trunk"]
    s = dict(o)
    s.update(width=o["width"] * SR + 1.5, height=o["height"] * SZ + 1.5, trunk=(th * SZ, r0 * SR, r1 * SR), tiers=tiers, lace=e["lace"],
             limb_t=(int(round(o["limb_t"][0] * 1.2)), o["limb_t"][1]),
             stubs=[((st[0] * SZ,) + tuple(st[1:])) for st in o["stubs"]] + list(e["stubs"]),
             root_steps=tuple(max(2, int(round(h * 1.3))) for h in o.get("root_steps", (9, 6, 4, 2))),
             root_w=int(round(o.get("root_w", 4) * 1.2)), root_step=int(round(o.get("root_step", 3) * 1.2)),
             flare=(9, 0.22, 2.4), rough_top=16,
             moss=dict(o["moss"], top=o["moss"]["top"] * SZ), ivy=dict(o["ivy"], top=o["ivy"]["top"] * SZ, strands=o["ivy"]["strands"] + 1))
    return s


TREES = {k: taller(k) for k in "ABCD"}


def build_tree(key, old=False):
    """-> (trunk object, leaves object) of tree A / B / C / D. old: nature.py's tree (not exported from here)."""
    s = OLD_TREES[key] if old else TREES[key]
    rng = np.random.default_rng(s["seed"])
    can = Canopy(s["width"], s["height"], s["seed"], name="leaves")
    th, r0, r1 = s["trunk"]
    tiers = []
    for ti, t in enumerate(s["tiers"]):
        cx, cy = t.get("centre", (0.0, 0.0))
        pads = ring(rng, t["n"], t["radius"], t["z"], t["r"], t["rz"], a0=t.get("a0"), centre=(cx, cy), jit=t.get("jit", 0.22), tone=0.03 * ti)
        tiers.append(pads)
        leaf_mass(can, pads, hangers=t.get("hang", 0))
    can.solidify(noise=0.30, scale=3.0).ragged()
    can.shade()
    can.cut_lace(share=s["lace"])

    reach = max([math.hypot(p[0], p[1]) for ti in s["limbs"] for p in tiers[ti]] + [r0 + 1.0])
    tr = Trunk(th, r0, r1, s["seed"] + 1, reach=reach + 0.4, flare=s.get("flare", (7, 0.22, 2.0)))
    tr.roots(n=s["roots"], steps=s.get("root_steps", (9, 6, 4, 2)), w=s.get("root_w", 4), step=s.get("root_step", 3))
    t0, t1 = s["limb_t"]
    for ti in s["limbs"]:
        for (x, y, z, rx, ry, rz, tone) in tiers[ti]:
            dist = math.hypot(x, y)
            if dist < 0.6:
                continue
            k = 0.82
            zs = max(0.5, z - 0.32 * dist - 0.75)
            tr.limb((0, 0, zs), (x * k, y * k, z - rz * 0.25), t0=max(t1, t0 - ti), t1=t1)
    for st in s["stubs"]:
        tr.stub(st[0], st[1], length=st[2] if len(st) > 2 else (4 if r0 > 0.6 else 3), th=st[3] if len(st) > 3 else (3 if r0 > 0.6 else 2))
    tr.moss(**s["moss"])
    tr.ivy(**s["ivy"])
    tv = tr.finish(rough_top=s.get("rough_top", 12))
    fmt = "OLD_Tree_%s_%s" if old else "SM_Tree2_%s_%s"
    trunk = V.join([tv], fmt % (key, "Trunk"))
    leaves = V.join(can.grids(), fmt % (key, "Leaves"))
    return trunk, leaves


def verts_of(ob):
    co = np.zeros(len(ob.data.vertices) * 3, np.float32)
    ob.data.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


def stats(trunk, leaves):
    """Height, crown base (lowest leaf, and where the body of the crown starts: the lowest 0.25 m layer that holds at
    least 15 % of the fullest layer's leaf faces), crown radius (furthest leaf from the trunk axis and the 95th
    percentile), face counts."""
    co = verts_of(leaves)
    layer = np.floor(co[:, 2] / LV + 1e-3).astype(int)
    cnt = np.bincount(layer - layer.min())
    body = (int(np.argmax(cnt >= 0.15 * cnt.max())) + layer.min()) * LV
    rad = np.hypot(co[:, 0], co[:, 1])
    return dict(height=float(max(co[:, 2].max(), verts_of(trunk)[:, 2].max())), lowest=float(co[:, 2].min()), base=float(body),
                rmax=float(rad.max()), r95=float(np.percentile(rad, 95)), width=float(max(np.ptp(co[:, 0]), np.ptp(co[:, 1]))),
                trunk_top=float(verts_of(trunk)[:, 2].max()),
                trunk_faces=int(trunk["voxel_faces"]), leaf_faces=int(leaves["voxel_faces"]))


def put(ob, x=0.0, y=0.0, z=0.0, rot=0.0):
    ob.location = (x, y, z)
    ob.rotation_euler = (0, 0, math.radians(rot))
    return ob


def copy_of(obs, x, y, rot=0.0, z=0.0):
    out = []
    for ob in obs:
        o = ob.copy()
        bpy.context.scene.collection.objects.link(o)
        out.append(put(o, x, y, z, rot))
    return out


def build_figure():
    """A 1.7 m stand-in for the king (preview only): red tunic, so he is easy to find among the trees."""
    v = Vox(12, 6, 28, PV, origin=(6, 3, 0), name="figure")
    v.box(2, 1, 0, 5, 5, 12, "paint", "#34344e")                      # legs
    v.box(7, 1, 0, 10, 5, 12, "paint", "#34344e")
    v.box(2, 1, 12, 10, 5, 21, "paint", "#d8301e")                    # tunic
    v.box(0, 1, 13, 2, 5, 21, "paint", "#b82414")                     # arms
    v.box(10, 1, 13, 12, 5, 21, "paint", "#b82414")
    v.box(3, 0, 21, 9, 6, 27, "paint", "#f0c090")                     # head: top at 27 x 6.25 cm = 1.69 m
    v.box(3, 0, 26, 9, 6, 27, "paint", "#f2c22a")                     # crown
    return V.join([v], "Figure")


# ---------------------------------------------------------------------------------------------------- previews

CPU = False


def render(path, **kw):
    """V.render; --cpu (or a failing GPU) renders on the CPU instead."""
    import time
    if CPU:
        def to_cpu(scene, *a):
            scene.cycles.device = "CPU"
        bpy.app.handlers.render_init.append(to_cpu)
    for attempt in range(1 if CPU else 2):
        try:
            return V.render(path, **kw)
        except Exception as e:
            print("render failed (%s), attempt %d" % (str(e).strip().splitlines()[-1][:120], attempt + 1))
            time.sleep(20)
    bpy.context.scene.cycles.device = "CPU"
    bpy.ops.render.render(write_still=True)
    print("rendered on the CPU", path)
    return path


def view_compare(key, path):
    """The old tree (left) and the tall one (right) at the same scale, the 1.7 m figure between them."""
    V.reset_scene()
    old, new = build_tree(key, old=True), build_tree(key)
    so, sn = stats(*old), stats(*new)
    gap = 1.2
    xo, xn = -(so["r95"] + gap), sn["r95"] + gap
    for ob in old:
        put(ob, xo, 0)
    for ob in new:
        put(ob, xn, 0)
    put(build_figure(), 0, -0.5)
    h = sn["height"]
    x0, x1 = xo - so["rmax"], xn + sn["rmax"]
    render(path, target=((x0 + x1) / 2.0, 0, h * 0.47), az=10, el=10, dist=max(h * 4.5, (x1 - x0) * 2.7), lens=85, res=(1600, 1000), samples=48)


GROVE = [("A", 4.5, -7.5, 0), ("B", -6.5, -3.5, 90), ("C", 7.5, 2.5, 0), ("D", -3.0, 3.5, 0), ("A", -9.5, 8.0, 180), ("B", 5.5, 11.0, 270),
         ("C", -13.5, -9.0, 90), ("D", 3.0, -1.5, 90), ("A", 15.0, -4.0, 90), ("B", -2.0, 17.0, 0)]


def view_grove(path, old, dist=15.0, pitch=30.0, az=0.0):
    """The hero camera (FOV 40 degrees, like the game's) looking down at a figure standing in a small grove."""
    V.reset_scene()
    made = {}
    for (k, x, y, rot) in GROVE:
        if k not in made:
            made[k] = build_tree(k, old=old)
            for ob in made[k]:
                put(ob, x, y, 0, rot)
        else:
            copy_of(made[k], x, y, rot)
    put(build_figure(), 0, 0, 0, 0)
    render(path, target=(0, 0, 1.0), az=az, el=pitch, dist=dist, lens=18.0 / math.tan(math.radians(20.0)), res=(1600, 900), samples=48)


def beam(p0, p1, colour, width=0.07):
    """A glowing bar from p0 to p1 (preview only): a camera's line of sight."""
    from mathutils import Vector
    p0, p1 = Vector(p0), Vector(p1)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(p0 + p1) / 2.0)
    ob = bpy.context.active_object
    ob.scale = (width, width, (p1 - p0).length)
    ob.rotation_euler = (p1 - p0).to_track_quat("Z", "Y").to_euler()
    m = bpy.data.materials.new("beam")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = colour + (1.0,)
    b.inputs["Emission Color"].default_value = colour + (1.0,)
    b.inputs["Emission Strength"].default_value = 6.0
    ob.data.materials.append(m)
    bpy.ops.mesh.primitive_cube_add(size=0.5, location=p0)             # the camera
    bpy.context.active_object.data.materials.append(m)


def view_sightline(path, old):
    """The grove seen level from the east, with the hero camera's line of sight to the figure drawn in: red = 15 m
    away at 30 degrees, yellow = 9 m at 24 degrees. Where a bar disappears into a crown the view is blocked."""
    V.reset_scene()
    made = {}
    for (k, x, y, rot) in GROVE:
        if abs(x) > 8 or y > 6:
            continue
        if k not in made:
            made[k] = build_tree(k, old=old)
            for ob in made[k]:
                put(ob, x, y, 0, rot)
        else:
            copy_of(made[k], x, y, rot)
    put(build_figure(), 0, 0, 0, 90)
    for (dist, pitch, col) in ((15.0, 30.0, (1.0, 0.05, 0.02)), (9.0, 24.0, (1.0, 0.75, 0.0))):
        e = math.radians(pitch)
        beam((0, -math.cos(e) * dist, 1.0 + math.sin(e) * dist), (0, 0, 1.0), col)
    render(path, target=(0, -6.0, 8.5), az=90, el=1.5, dist=95, lens=85, res=(1600, 1000), samples=48)


def view_lineup(path):
    V.reset_scene()
    x = 0.0
    for k in "ABCD":
        obs = build_tree(k)
        s = stats(*obs)
        x += s["r95"]
        for ob in obs:
            put(ob, x, 0)
        x += s["r95"] + 1.5
    put(build_figure(), -2.0, -1.0)
    render(path, target=(x / 2.0 - 2, 0, 7.5), az=28, el=28, dist=x * 2.6, lens=85, res=(1600, 800), samples=48)


VIEWS = {
    "compare_a": lambda p: view_compare("A", p),
    "compare_b": lambda p: view_compare("B", p),
    "compare_c": lambda p: view_compare("C", p),
    "compare_d": lambda p: view_compare("D", p),
    "grove_old": lambda p: view_grove(p, True),
    "grove_new": lambda p: view_grove(p, False),
    "grove_close_old": lambda p: view_grove(p, True, dist=9.0, pitch=24.0),
    "grove_close_new": lambda p: view_grove(p, False, dist=9.0, pitch=24.0),
    "sightline_old": lambda p: view_sightline(p, True),
    "sightline_new": lambda p: view_sightline(p, False),
    "lineup": view_lineup,
}


def main():
    global CPU
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    only, views = "ABCD", None
    for i, a in enumerate(argv):
        if a == "--only":
            only = argv[i + 1].split(",")
        if a == "--views":
            views = argv[i + 1].split(",")
    CPU = "--cpu" in argv
    for k in only:
        V.reset_scene()
        so = stats(*build_tree(k, old=True))
        V.reset_scene()
        trunk, leaves = build_tree(k)
        sn = stats(trunk, leaves)
        fo, fn = so["trunk_faces"] + so["leaf_faces"], sn["trunk_faces"] + sn["leaf_faces"]
        print("TREE %s  height %.2f -> %.2f m (x%.2f)  crown base %.2f -> %.2f (lowest leaf %.2f -> %.2f)  crown radius %.2f -> %.2f (furthest %.2f -> %.2f)  "
              "trunk top %.2f -> %.2f" % (k, so["height"], sn["height"], sn["height"] / so["height"], so["base"], sn["base"], so["lowest"], sn["lowest"],
                                          so["r95"], sn["r95"], so["rmax"], sn["rmax"], so["trunk_top"], sn["trunk_top"]))
        print("     %s  faces trunk %d -> %d, leaves %d -> %d, total %d -> %d (x%.2f)" % (k, so["trunk_faces"], sn["trunk_faces"], so["leaf_faces"], sn["leaf_faces"], fo, fn, fn / float(fo)))
        if "--no-export" not in argv:
            V.export_gltf(trunk, collision="complex")
            V.export_gltf(leaves, collision="none")
    if "--no-render" not in argv:
        for k in (views if views is not None else VIEWS):
            VIEWS[k](os.path.join(V.PREVIEWS, "trees_tall_%s.png" % k))


main()
