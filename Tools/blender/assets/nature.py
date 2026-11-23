"""Nature set of the voxel village: puffy trees (trunk + leaves), bushes, rock piles, flowers, grass, lily pads, vines.

    Blender -b --factory-startup --python Tools/blender/assets/nature.py -- [--no-render] [--no-export]
                                                                           [--only Tree_A,Rock_B,...] [--views forest,rocks,...]

Trees are two meshes that share one origin (the centre of the trunk base at ground level): SM_Tree_X_Trunk (collides)
and SM_Tree_X_Leaves (no collision). Leaves are 0.25 m cubes with a share of the outer shell cut into 0.125 m pieces
("lace") so that the canopy has the notched, see-through edge of the reference instead of a smooth blob.
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

    def __init__(self, height, r0, r1, seed, reach=2.0, name="trunk"):
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
        return self.r0 + (self.r1 - self.r0) * t ** 0.8 + np.clip((7 - np.asarray(z, np.float32)) * 0.22, 0, 2)

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

    def finish(self, rough=0.22):
        """Rough the limbs and roots up a little, and cap every upward/downward bark face with dark wood (a log's
        top is pale end grain, which is wrong on bark)."""
        v = self.v
        if rough > 0:
            v.chunky("log", cell=2, depth=1, p=rough, seed=self.seed + 7, region=(0, 0, 0, v.n[0], v.n[1], SKIRT + 12))
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


TREES = {
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


def build_tree(key):
    """-> (trunk object, leaves object) of tree A / B / C / D."""
    s = TREES[key]
    rng = np.random.default_rng(s["seed"])
    can = Canopy(s["width"], s["height"], s["seed"], name="leaves")
    lean = s.get("lean", (0.0, 0.0))
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
    tr = Trunk(th, r0, r1, s["seed"] + 1, reach=reach + 0.4)
    tr.roots(n=s["roots"], steps=s.get("root_steps", (9, 6, 4, 2)), w=s.get("root_w", 4), step=s.get("root_step", 3))
    if s.get("collar"):
        tr.collar(s["collar"])
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
    tv = tr.finish()
    trunk = V.join([tv], "SM_Tree_%s_Trunk" % key)
    leaves = V.join(can.grids(), "SM_Tree_%s_Leaves" % key)
    return trunk, leaves


# ---------------------------------------------------------------------------------------------------- small plants (6.25 cm voxels)

GREENS = ["#8fd02a", "#72b526", "#57981f", "#a9de3c", "#c6e85a"]
STEM = "#5c9a26"


def blade(v, x, y, h, col, w=1, lean=(1, 0), bend=0.55):
    """A grass blade: a thin upright strip that steps sideways once or twice towards its tip."""
    hb = max(1, int(h * bend))
    h2 = max(hb + 1, int(h * 0.85))
    for z in range(h):
        k = 0 if z < hb else (1 if z < h2 or h < 7 else 2)
        px, py = x + lean[0] * k, y + lean[1] * k
        ww = w if z < h - 2 else 1
        if lean[0]:
            v.box(px, py, z, px + 1, py + ww, z + 1, "paint", col)
        else:
            v.box(px, py, z, px + ww, py + 1, z + 1, "paint", col)
        if k and z in (hb, h2):                                       # the step is a full voxel, not a diagonal
            v.box(x + lean[0] * (k - 1), y + lean[1] * (k - 1), z, x + lean[0] * (k - 1) + 1, y + lean[1] * (k - 1) + 1, z + 1, "paint", col)


def frond(v, x, y, h, col, lean=(1, 0), reach=4, leaflets=True):
    """A fern frond: a stem that climbs and arches over in steps, with small leaflets on alternating sides."""
    side = (-lean[1], lean[0])
    for z in range(h):
        k = int(round(reach * (z / max(1, h - 1)) ** 2.0))
        px, py = x + lean[0] * k, y + lean[1] * k
        v.set(px, py, z, "paint", col)
        if z > 0:
            k0 = int(round(reach * ((z - 1) / max(1, h - 1)) ** 2.0))
            for kk in range(k0 + 1, k):
                v.set(x + lean[0] * kk, y + lean[1] * kk, z, "paint", col)
        if leaflets and z >= 2 and z % 2 == 0 and z < h - 1:
            sgn = 1 if (z // 2) % 2 else -1
            v.set(px + side[0] * sgn, py + side[1] * sgn, z, "paint", col)
            if z < h - 3:
                v.set(px + side[0] * sgn * 2, py + side[1] * sgn * 2, z + 1, "paint", col)


def head(v, x, y, z, petal, centre, face=(0, -1), full=False):
    """A flower head as a tilted plus: it reads as a flower from the front, from above and from the village view.
    (x, y, z) is the centre voxel; face is the way it looks."""
    side = (-face[1], face[0])
    v.set(x + side[0], y + side[1], z, "paint", petal)
    v.set(x - side[0], y - side[1], z, "paint", petal)
    v.set(x - face[0], y - face[1], z + 1, "paint", petal)
    v.set(x + face[0], y + face[1], z - 1, "paint", petal)
    if full:
        v.set(x + side[0] - face[0], y + side[1] - face[1], z + 1, "paint", petal)
        v.set(x - side[0] - face[0], y - side[1] - face[1], z + 1, "paint", petal)
        v.set(x + side[0] + face[0], y + side[1] + face[1], z - 1, "paint", petal)
        v.set(x - side[0] + face[0], y - side[1] + face[1], z - 1, "paint", petal)
    v.set(x, y, z, "paint", centre)


DIRS4 = [(1, 0), (-1, 0), (0, 1), (0, -1)]


def tuft_into(v, rng, cx, cy, radius, count, hmin, hmax, greens=GREENS, wide=0.3, fern=0.0):
    """Scatter grass blades (and fern fronds) round (cx, cy) in a plant grid; taller towards the middle."""
    for _ in range(count):
        a, d = rng.uniform(0, 2 * math.pi), radius * math.sqrt(rng.uniform(0, 1))
        x, y = int(round(cx + math.cos(a) * d)), int(round(cy + math.sin(a) * d))
        h = int(round(hmin + (hmax - hmin) * (1 - d / max(1e-3, radius)) ** 0.7 * rng.uniform(0.6, 1.0)))
        col = greens[int(rng.integers(0, len(greens)))]
        out = (int(np.sign(round(math.cos(a)))), 0) if abs(math.cos(a)) > abs(math.sin(a)) else (0, int(np.sign(round(math.sin(a)))))
        lean = out if rng.random() < 0.7 else DIRS4[int(rng.integers(0, 4))]
        if rng.random() < fern:
            frond(v, x, y, h + 2, col, lean=lean, reach=int(rng.integers(2, 5)))
        else:
            blade(v, x, y, max(2, h), col, w=2 if (rng.random() < wide and h >= 5) else 1, lean=lean, bend=rng.uniform(0.45, 0.75))


def plant_grid(size, height, seed, name):
    n = int(round(size / PV / 2.0)) * 2 + 8
    return Vox(n, n, int(round(height / PV)) + 4, PV, origin=(n / 2, n / 2, 0), name=name, seed=seed)


def flower_on_stem(v, rng, x, y, h, petal, centre, full=False, stem=STEM, leaf=True):
    lean = DIRS4[int(rng.integers(0, 4))]
    hb = int(h * 0.6)
    for z in range(h):
        k = 0 if z < hb else 1
        v.set(x + lean[0] * k, y + lean[1] * k, z, "paint", stem)
    v.set(x, y, hb, "paint", stem)
    if leaf and h >= 5:
        s = DIRS4[int(rng.integers(0, 4))]
        v.set(x + s[0], y + s[1], int(h * 0.35), "paint", GREENS[1])
        v.set(x + 2 * s[0], y + 2 * s[1], int(h * 0.35) + 1, "paint", GREENS[0])
    face = DIRS4[int(rng.integers(0, 4))]
    head(v, x + lean[0], y + lean[1], h, petal, centre, face=face, full=full)


FLOWER_SETS = {
    # name: (size m, seed, [(count, petal, centre, hmin, hmax, full)], grass blades, grass height range)
    "A": (0.9, 3, [(7, "flower_white", "flower_yellow", 4, 8, False)], 20, (3, 7)),                 # daisies
    "B": (1.0, 8, [(5, "flower_yellow", "flower_orange", 6, 11, True), (2, "flower_orange", "#c85a18", 5, 9, False)], 22, (4, 10)),
    "C": (0.8, 15, [(4, "flower_orange", "flower_yellow", 6, 10, True), (2, "flower_white", "flower_yellow", 4, 6, False), (2, "flower_yellow", "flower_orange", 5, 8, False)], 16, (3, 8)),
    "D": (1.1, 21, [(3, "flower_white", "flower_yellow", 4, 7, False)], 18, (3, 7)),                # + pink spires, below
}


def build_flowers(key):
    size, seed, kinds, nblades, (g0, g1) = FLOWER_SETS[key]
    rng = np.random.default_rng(seed)
    v = plant_grid(size, 1.0, seed, "flowers")
    c = v.n[0] / 2
    rad = size / PV / 2.0
    tuft_into(v, rng, c, c, rad * 0.9, nblades, g0, g1, wide=0.25, fern=0.08)
    for (count, petal, centre, hmin, hmax, full) in kinds:
        for _ in range(count):
            a, d = rng.uniform(0, 2 * math.pi), rad * 0.85 * math.sqrt(rng.uniform(0.02, 1))
            flower_on_stem(v, rng, int(round(c + math.cos(a) * d)), int(round(c + math.sin(a) * d)), int(rng.integers(hmin, hmax + 1)), petal, centre, full=full)
    if key == "D":                                                    # pink flower spires (like the ones by the paths)
        for _ in range(4):
            a, d = rng.uniform(0, 2 * math.pi), rad * 0.7 * math.sqrt(rng.uniform(0.02, 1))
            x, y = int(round(c + math.cos(a) * d)), int(round(c + math.sin(a) * d))
            h = int(rng.integers(8, 13))
            for z in range(h):
                v.set(x, y, z, "paint", STEM)
            for z in range(h - 5, h + 1):
                s = DIRS4[(z + int(rng.integers(0, 2))) % 4]
                v.set(x + s[0], y + s[1], z, "paint", "flower_pink" if (z % 3) else "#f4c2d2")
                if z < h - 2 and rng.random() < 0.6:
                    v.set(x - s[0], y - s[1], z, "paint", "#d86a90")
            v.set(x, y, h, "paint", "#f4c2d2")
    return V.join([v], "SM_Flowers_%s" % key)


GRASS_SETS = {"A": (0.45, 5, 16, (2, 5), 0.0, 0.0), "B": (0.6, 9, 22, (3, 8), 0.3, 0.1), "C": (0.75, 14, 26, (4, 10), 0.4, 0.25)}


def build_grass(key):
    size, seed, count, (h0, h1), wide, fern = GRASS_SETS[key]
    rng = np.random.default_rng(seed)
    v = plant_grid(size, 0.8, seed, "grass")
    c = v.n[0] / 2
    tuft_into(v, rng, c, c, size / PV / 2.0, count, h0, h1, wide=wide, fern=fern)
    return V.join([v], "SM_GrassTuft_%s" % key)


def build_lilypad(key):
    """A flat pad about 0.6 m across with a notch, lying in the water surface (origin = centre, at the water level;
    the pad is 6 cm thick and sits half in the water). B carries a small pink and white flower."""
    flower = key == "B"
    seed = 4 if flower else 2
    n = 12
    v = Vox(n, n, 6, PV, origin=(n / 2, n / 2, 0.5), name="lilypad", seed=seed)
    notch = 0.6 if flower else 2.4
    for i in range(n):
        for j in range(n):
            dx, dy = i + 0.5 - n / 2, j + 0.5 - n / 2
            r = math.hypot(dx, dy)
            if r > 4.9:
                continue
            a = math.atan2(dy, dx)
            da = abs((a - notch + math.pi) % (2 * math.pi) - math.pi)
            if da < 0.36 and r > 0.9:
                continue
            col = "#2f7d3a"
            if r > 3.9:
                col = "#3f9444"
            elif (abs(dx) < 0.6 or abs(dy) < 0.6 or abs(abs(dx) - abs(dy)) < 0.6) and r > 0.8:
                col = "#256a34"
            v.set(i, j, 0, "paint", col)
    if flower:
        cx, cy = 7, 5
        for (dx, dy) in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            v.set(cx + dx, cy + dy, 1, "paint", "flower_pink")
        for (dx, dy) in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            v.set(cx + dx, cy + dy, 1, "paint", "#f4c2d2")
        v.set(cx, cy, 1, "paint", "flower_white")
        for (dx, dy) in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            v.set(cx + dx, cy + dy, 2, "paint", "flower_white")
        v.set(cx, cy, 2, "paint", "flower_yellow")
        v.set(cx, cy, 3, "paint", "flower_yellow")
    return V.join([v], "SM_LilyPad_%s" % key)


def build_vines():
    """A hanging curtain of vine leaves, 1 m wide and 1.5 m long. Origin: the middle of its top edge, at the wall
    face; it hangs down from there (z from 0 to -1.5) and stands 12-37 cm proud of the wall towards -Y."""
    rng = np.random.default_rng(17)
    w, h = 8, 12
    v = Vox(w, 3, h, TV, origin=(w / 2, 3, h), name="vines", seed=6)
    tones = ["#fffbc2", "#e2eeaa", "#c4dc98", "#a4c488"]
    length = [int(rng.integers(6, h + 1)) for _ in range(w)]
    length[int(rng.integers(0, w))] = h
    length[int(rng.integers(0, w))] = h
    for x in range(w):
        for k in range(length[x]):
            z = h - 1 - k
            t = k / float(h)
            if k > 1 and rng.random() < 0.10 + 0.12 * t:              # gaps
                continue
            tone = tones[min(3, int(rng.integers(0, 2)) + (1 if t > 0.35 else 0) + (1 if t > 0.75 else 0))]
            v.set(x, 2, z, "leaves", tone)
            if rng.random() < 0.34 - 0.15 * t:                        # leaves standing proud
                v.set(x, 1, z, "leaves", tones[int(rng.integers(0, 2))])
                if rng.random() < 0.25:
                    v.set(x, 0, z, "leaves", tones[0])
        if rng.random() < 0.6:                                        # a tip that hangs a little forward
            v.set(x, 1, h - length[x], "leaves", tones[1])
    v.box(0, 1, h - 1, w, 3, h, "leaves", tones[1])                   # the top where it hangs from the eave
    v.tint("leaves", tones[0], p=0.3, seed=3)
    return V.join([v], "SM_Vines_A")


# ---------------------------------------------------------------------------------------------------- bushes

BUSHES = {
    # name: (seed, [(x, y, z, rx, ry, rz)], flowers [(colour, centre, count)])
    "A": (61, [(0.0, 0.0, 0.45, 0.95, 0.85, 0.75), (-0.55, 0.35, 0.35, 0.6, 0.6, 0.55), (0.6, -0.3, 0.3, 0.6, 0.55, 0.5),
               (0.25, 0.55, 0.3, 0.5, 0.5, 0.45), (-0.35, -0.55, 0.25, 0.5, 0.5, 0.42)], []),
    "B": (67, [(0.0, 0.0, 0.35, 0.7, 0.62, 0.6), (0.45, 0.25, 0.25, 0.45, 0.45, 0.42), (-0.4, -0.3, 0.25, 0.45, 0.42, 0.4)],
          [("flower_white", "flower_yellow", 6), ("flower_pink", "flower_white", 4)]),
    "C": (73, [(0.0, 0.0, 0.25, 0.5, 0.48, 0.42), (0.3, -0.2, 0.2, 0.34, 0.34, 0.3)], [("flower_yellow", "flower_orange", 5)]),
}


def build_bush(key):
    seed, puffs, flowers = BUSHES[key]
    rng = np.random.default_rng(seed)
    width = 2.0 * max(abs(p[0]) + p[3] for p in puffs) + 1.0
    can = Canopy(width, max(p[2] + p[5] for p in puffs) + 0.75, seed, name="bush")
    for (x, y, z, rx, ry, rz) in puffs:
        can.puff(x, y, z, rx, ry, rz, p=2.8, flat=1.0, tone=rng.uniform(-0.05, 0.05))
    can.solidify(noise=0.5, scale=2.5)
    can.ragged(top=0.10, side=0.10, under=0.0, edge=0.22, strays=0.04, hang=0.0)
    can.v.m[:, :, 0][can.d[:, :, 0] > 1.15] = 0
    can.shade(lo=0.12, hi=1.0)
    can.cut_lace(share=1.4, keep=0.72, tabs=0.10)
    grids = can.grids()
    if flowers:                                                       # small flower heads sitting on the leaves
        fv = Vox(can.v.n[0] * 4, can.v.n[1] * 4, can.v.n[2] * 4 + 8, PV, origin=(can.v.origin[0] * 4, can.v.origin[1] * 4, 0), name="bushflowers", seed=seed)
        solid = (can.v.m > 0) | (can.lace.m.reshape(can.v.n[0], 2, can.v.n[1], 2, can.v.n[2], 2).any(axis=(1, 3, 5)))
        tops = np.argwhere(solid & ~shift(solid, (0, 0, 1), False))
        sides = np.argwhere(solid & (open_faces(solid) >= 2) & shift(solid, (0, 0, 1), False))
        for (petal, centre, count) in flowers:
            for _ in range(count):
                src = tops if (rng.random() < 0.75 or len(sides) == 0) else sides
                i, j, k = src[int(rng.integers(0, len(src)))]
                x, y, z = i * 4 + int(rng.integers(1, 3)), j * 4 + int(rng.integers(1, 3)), (k + 1) * 4
                fv.set(x, y, z, "paint", STEM)
                head(fv, x, y, z + 1, petal, centre, face=DIRS4[int(rng.integers(0, 4))])
        grids.append(fv)
    return V.join(grids, "SM_Bush_%s" % key)


# ---------------------------------------------------------------------------------------------------- rocks

STONE_TINTS = ["#ffffff", "#f4ece0", "#e8e0d4", "#fff6e8", "#ece6e2", "#dcd4c8"]

ROCKS = {
    # blocks: (x, y, z, sx, sy, sz[, kind]) in 0.5 m units; kind: "s" stone, "m" stone with a mossy top, "d" dirt
    # A: the big pile, 3 m across and 2.5 m tall: a tall back wall, a mossy step on the left, two cubes in front,
    #    a block of earth on the right
    "A": dict(seed=5, size=(6, 6, 5), ferns=10, blocks=[
        (1, 3, 0, 2, 2, 2), (3, 3, 0, 2, 2, 2), (1, 3, 2, 2, 2, 2), (3, 3, 2, 2, 2, 2, "m"), (2, 3, 4, 2, 2, 1, "m"),
        (0, 2, 0, 1, 2, 2), (0, 2, 2, 1, 2, 1, "m"), (0, 4, 0, 1, 1, 1, "m"),
        (1, 1, 0, 2, 2, 2), (3, 1, 0, 2, 2, 2, "m"), (1, 2, 2, 1, 1, 1),
        (2, 0, 0, 2, 1, 1), (0, 1, 0, 1, 1, 1, "m"),
        (5, 2, 0, 1, 2, 3, "d"), (5, 4, 0, 1, 1, 2, "m"), (5, 1, 0, 1, 1, 1), (4, 0, 0, 1, 1, 1, "m")]),
    # B: medium, a tall back stack and a low cube in front of it
    "B": dict(seed=9, size=(4, 4, 4), ferns=7, blocks=[
        (1, 1, 0, 2, 2, 2), (1, 1, 2, 2, 2, 1), (1, 2, 3, 2, 1, 1, "m"), (2, 1, 3, 1, 1, 1),
        (0, 0, 0, 2, 2, 2, "m"), (3, 1, 0, 1, 2, 2, "m"), (0, 2, 0, 1, 1, 1), (2, 0, 0, 1, 1, 1),
        (1, 3, 0, 2, 1, 1, "m"), (3, 3, 0, 1, 1, 1, "d")]),
    # C: small, one cube with two little ones
    "C": dict(seed=14, size=(3, 3, 3), ferns=4, blocks=[
        (0, 1, 0, 2, 2, 2, "m"), (2, 1, 0, 1, 1, 1), (1, 0, 0, 1, 1, 1, "m"), (2, 2, 0, 1, 1, 1, "d")]),
    # D: a long low ledge
    "D": dict(seed=19, size=(8, 3, 3), ferns=10, blocks=[
        (0, 1, 0, 2, 2, 1, "m"), (2, 1, 0, 2, 2, 2), (4, 1, 0, 2, 2, 2, "m"), (6, 1, 0, 2, 2, 1, "m"),
        (1, 0, 0, 1, 1, 1), (3, 0, 0, 2, 1, 1, "m"), (5, 0, 0, 1, 1, 1, "d"), (2, 2, 2, 1, 1, 1, "m"), (7, 0, 0, 1, 1, 1, "d")]),
    # E: tall and narrow
    "E": dict(seed=27, size=(3, 3, 7), ferns=6, blocks=[
        (0, 0, 0, 2, 2, 2), (0, 0, 2, 2, 2, 2), (0, 0, 4, 2, 2, 1, "m"), (1, 1, 5, 1, 1, 2, "m"), (0, 1, 5, 1, 1, 1),
        (2, 0, 0, 1, 2, 2, "m"), (2, 1, 2, 1, 1, 1), (0, 2, 0, 2, 1, 3), (1, 2, 3, 1, 1, 1, "m"), (2, 2, 0, 1, 1, 1, "d")]),
}


def build_rock(key):
    s = ROCKS[key]
    seed = s["seed"]
    rng = np.random.default_rng(seed)
    bx, by, bz = s["size"]
    M = 4                                                             # margin voxels round the pile
    v = Vox(bx * 4 + 2 * M, by * 4 + 2 * M, bz * 4 + SKIRT + 4, TV, origin=(bx * 2 + M, by * 2 + M, SKIRT), name="rock", seed=seed)
    mossy = np.zeros(v.n, bool)
    for b in s["blocks"]:
        x, y, z, sx, sy, sz = b[:6]
        kind = b[6] if len(b) > 6 else "s"
        g = [int(rng.choice([0, 0, 0, 1])) for _ in range(5)]         # a face may stand a voxel proud
        x0, y0, x1, y1 = M + x * 4 - g[0], M + y * 4 - g[1], M + (x + sx) * 4 + g[2], M + (y + sy) * 4 + g[3]
        z0, z1 = (0 if z == 0 else SKIRT + z * 4), SKIRT + (z + sz) * 4 + (g[4] if kind != "d" else 0)
        v.box(x0, y0, z0, x1, y1, z1, "dirt" if kind == "d" else "stone", STONE_TINTS[int(rng.integers(0, len(STONE_TINTS)))] if kind != "d" else None)
        mossy[x0:x1, y0:y1, z0:z1] = kind in ("m", "d")
    v.chunky("stone", cell=4, depth=1, p=0.07, seed=seed + 1)
    stone = v.mask("stone")
    solid = v.m > 0
    top = solid & ~shift(solid, (0, 0, 1), False)
    nz = V.noise3(v.n, 7, seed + 4, octaves=2)
    X, Y, Z = v.grid()
    # moss: the tops of the mossy blocks (most of them) and stray patches on the others
    patch = top & ((mossy & (nz > 0.36)) | (~mossy & (nz > 0.60))) & (Z >= SKIRT + 2)
    # the stone under a mossy top shows the texture with moss hanging from the block's upper edge
    under = np.zeros(v.n, bool)
    for k in range(0, 4):
        under |= shift(patch, (0, 0, k), False)
    v.m[under & stone] = V.IDS["mossy_stone"]
    # a moss carpet one voxel thick on the inner part of each patch
    carpet = shift(patch & (nz > 0.44), (0, 0, -1), False) & ~solid
    v.m[carpet] = V.IDS["moss"]
    v.c[carpet] = ramp(hsh(X, Y, Z, seed) * 0.8 + 0.2, ["#cfe0a0", "#f0f6c0", "#ffffff"])[carpet]
    # moss dripping down the sides from the edge of the patches
    solid = v.m > 0
    for d in N6[:4]:
        edge = shift(patch, (-d[0], -d[1], 0), False) & ~solid                    # the air cell beside a mossy top voxel
        length = (hsh(X, Y, 7, seed + d[0] * 3 + d[1] * 5) ** 1.3 * 8).astype(np.int64)
        length = np.where(hsh(X // 3, Y // 3, 11, seed) < 0.7, length, 0)
        for k in range(0, 8):
            cell = shift(edge & (length > k), (0, 0, k), False)
            cell &= ~solid & shift(solid, d, False)                               # hugging the face
            v.m[cell] = V.IDS["moss"]
            v.c[cell] = ramp(hsh(X, Y, Z, seed + 2) * 0.7 + 0.3 - 0.05 * k, ["#b8d088", "#e8f2b8", "#ffffff"])[cell]
    grids = [v]
    # ferns and grass growing at the foot
    foot = (v.m[:, :, SKIRT:SKIRT + 3] > 0).any(axis=2)
    ring_ = dilate(foot[:, :, None])[:, :, 0] & ~foot
    cells = np.argwhere(ring_)
    if len(cells):
        for _ in range(s["ferns"]):
            i, j = cells[int(rng.integers(0, len(cells)))]
            wx, wy = (i + 0.5 - v.origin[0]) * TV, (j + 0.5 - v.origin[1]) * TV
            out = np.array([wx, wy]) / max(1e-3, math.hypot(wx, wy))
            pv = plant_grid(0.6, 1.0, int(rng.integers(0, 9999)), "fern")
            c = pv.n[0] / 2
            tuft_into(pv, rng, c, c, 4.0, int(rng.integers(5, 10)), 4, int(rng.integers(8, 14)), greens=GREENS[:4], wide=0.3, fern=0.5)
            grids.append(pv.at(wx + out[0] * 0.12, wy + out[1] * 0.12, 0.0))
    return V.join(grids, "SM_Rock_%s" % key)


# ---------------------------------------------------------------------------------------------------- the asset list

ASSETS = {}            # name -> (builder returning one object or a tuple of objects, collision of each)
for _k in "ABCD":
    ASSETS["Tree_" + _k] = (lambda k=_k: build_tree(k), ("complex", "none"))
for _k in "ABC":
    ASSETS["Bush_" + _k] = (lambda k=_k: build_bush(k), ("none",))
for _k in "ABCDE":
    ASSETS["Rock_" + _k] = (lambda k=_k: build_rock(k), ("complex",))
for _k in "ABCD":
    ASSETS["Flowers_" + _k] = (lambda k=_k: build_flowers(k), ("none",))
for _k in "ABC":
    ASSETS["GrassTuft_" + _k] = (lambda k=_k: build_grass(k), ("none",))
for _k in "AB":
    ASSETS["LilyPad_" + _k] = (lambda k=_k: build_lilypad(k), ("none",))
ASSETS["Vines_A"] = (build_vines, ("none",))


def make(name):
    obs = ASSETS[name][0]()
    return obs if isinstance(obs, tuple) else (obs,)


def size_of(ob):
    co = np.zeros(len(ob.data.vertices) * 3, np.float32)
    ob.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    return co.min(axis=0), co.max(axis=0)


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


# ---------------------------------------------------------------------------------------------------- previews

def render(path, **kw):
    """V.render, but if the GPU is busy (other jobs share it) wait and try again, then fall back to the CPU."""
    import time
    for attempt in range(3):
        try:
            return V.render(path, **kw)
        except Exception as e:
            print("render failed (%s), attempt %d" % (str(e).strip().splitlines()[-1][:120], attempt + 1))
            time.sleep(25)
    scene = bpy.context.scene
    scene.cycles.device = "CPU"
    bpy.ops.render.render(write_still=True)
    print("rendered on the CPU", path)
    return path


def view_tree(key, path, **kw):
    V.reset_scene()
    make("Tree_" + key)
    s = TREES[key]
    h = s["height"]
    a = dict(target=(0, 0, h * 0.47), az=28, el=32, dist=h * 3.4, lens=85, samples=48)
    a.update(kw)
    render(path, **a)


def view_close(key, path, cam=(-5.5, -11.0, 1.7), look=(0.5, 0.0, 5.0), lens=24):
    """Standing under the tree, looking up into it (the framing of References/forest.png)."""
    V.reset_scene()
    make("Tree_" + key)
    d = np.array(look, np.float32) - np.array(cam, np.float32)
    dist = float(np.linalg.norm(d))
    render(path, target=look, az=math.degrees(math.atan2(-d[0], d[1])), el=math.degrees(math.asin(-d[2] / dist)), dist=dist, lens=lens,
             res=(1600, 900), samples=64, sun_az=-35, sun_el=30)


def view_trees_village(path, az=28, el=32):
    V.reset_scene()
    xs = {"A": -12.5, "B": 1.5, "C": 12.5, "D": 20.0}
    for k, x in xs.items():
        for ob in make("Tree_" + k):
            put(ob, x, 0)
    render(path, target=(3.0, 0, 5.6), az=az, el=el, dist=118, lens=85, res=(1600, 800), samples=48)


def view_forest(path, cam=(2.0, -24.0, 2.2), look=(1.0, 0.0, 5.2), lens=32, sun_az=-35, sun_el=30, res=(1600, 900)):
    """A little forest from eye level, like References/forest.png."""
    V.reset_scene()
    rng = np.random.default_rng(4)
    A, B, C, D = make("Tree_A"), make("Tree_B"), make("Tree_C"), make("Tree_D")
    for ob in A:
        put(ob, -7.5, -6.0, 0, 0)
    for ob in B:
        put(ob, 9.5, -5.0, 0, 90)
    copy_of(A, 3.5, 9.0, 180)
    copy_of(B, -12.0, 12.0, 270)
    copy_of(A, 19.0, 15.0, 90)
    copy_of(B, -3.0, 24.0, 0)
    copy_of(A, -24.0, 26.0, 270)
    copy_of(B, 13.0, 30.0, 180)
    for ob in C:
        put(ob, 1.0, -1.0, 0, 0)
    copy_of(C, -17.0, 2.0, 90)
    copy_of(C, 22.0, 2.0, 180)
    for ob in D:
        put(ob, 4.5, -11.0, 0, 0)
    copy_of(D, -1.5, -13.5, 90)
    copy_of(D, 15.0, -11.0, 180)
    rocks = {k: make("Rock_" + k) for k in "ABCDE"}
    put(rocks["A"][0], -1.5, -9.0, 0, 0)
    put(rocks["B"][0], 6.0, -14.0, 0, 90)
    put(rocks["C"][0], -5.0, -15.5, 0, 0)
    put(rocks["D"][0], 2.5, -6.0, 0, 0)
    put(rocks["E"][0], -11.5, -8.5, 0, 0)
    bushes = [make("Bush_" + k) for k in "ABC"]
    small = [make("Flowers_" + k) for k in "ABCD"] + [make("GrassTuft_" + k) for k in "ABC"]
    for i, b in enumerate(bushes):
        put(b[0], (-3.5, 3.5, 0.5)[i], (-13.0, -16.0, -16.5)[i])
    for (x, y, i) in [(-9.0, -12.0, 0), (8.5, -9.5, 1), (-4.0, -5.0, 0), (11.5, -13.0, 2), (-13.0, -4.0, 1), (0.5, -11.5, 2), (6.0, -4.5, 0), (-7.0, -17.5, 1)]:
        copy_of(bushes[i], x, y, int(rng.integers(0, 4)) * 90)
    for ob in small:
        put(ob[0], rng.uniform(-6, 9), rng.uniform(-19, -9))
    for _ in range(170):
        copy_of(small[int(rng.integers(0, len(small)))], rng.uniform(-16, 20), rng.uniform(-20.5, 2), int(rng.integers(0, 4)) * 90)
    d = np.array(look, np.float32) - np.array(cam, np.float32)
    dist = float(np.linalg.norm(d))
    az = math.degrees(math.atan2(-d[0], d[1]))
    el = math.degrees(math.asin(-d[2] / dist))
    render(path, target=look, az=az, el=el, dist=dist, lens=lens, res=res, samples=64, sun_az=sun_az, sun_el=sun_el)


def view_sheet(rows, path, spacing=0.6, row_gap=None, lift=None, **kw):
    """Assets side by side. rows: a list of rows (back row first), each a list of asset names."""
    V.reset_scene()
    lift = lift or {}
    y = 0.0
    tall, wide, y_front = 0.0, 0.0, 0.0
    prev_depth = None
    for names in rows:
        obs = [make(n) for n in names]
        boxes = [size_of(o[0]) for o in obs]
        widths = [max(hi[0] - lo[0], 0.3) for lo, hi in boxes]
        depth = max(hi[1] - lo[1] for lo, hi in boxes)
        if prev_depth is not None:
            y -= prev_depth / 2.0 + depth / 2.0 + (row_gap if row_gap is not None else spacing)
        total = sum(widths) + spacing * (len(obs) - 1)
        x = -total / 2.0
        for n, o, (lo, hi), w in zip(names, obs, boxes, widths):
            for ob in o:
                put(ob, x - lo[0], y - (lo[1] + hi[1]) / 2.0, lift.get(n, 0.0))
            x += w + spacing
            tall = max(tall, hi[2] + lift.get(n, 0.0))
        wide = max(wide, total)
        prev_depth = depth
        y_front = y - depth / 2.0
    a = dict(target=(0, y_front / 2.0, tall * 0.35), az=28, el=30, dist=max(wide, tall * 1.6, -y_front * 1.4) * 2.35 + 3, lens=85, samples=64)
    a.update(kw)
    render(path, **a)


VIEWS = {
    "tree_a": lambda p: view_tree("A", p),
    "tree_b": lambda p: view_tree("B", p),
    "tree_c": lambda p: view_tree("C", p),
    "tree_d": lambda p: view_tree("D", p),
    "tree_a_back": lambda p: view_tree("A", p, az=200, el=22),
    "tree_a_low": lambda p: view_tree("A", p, target=(0, 0, 5.5), az=20, el=-4, dist=30, lens=40),
    "tree_a_close": lambda p: view_close("A", p),
    "tree_b_close": lambda p: view_close("B", p),
    "trees_village": lambda p: view_trees_village(p),
    "trees_back": lambda p: view_trees_village(p, az=205, el=20),
    "forest": lambda p: view_forest(p),
    "rocks": lambda p: view_sheet([["Rock_A", "Rock_E", "Rock_B"], ["Rock_D", "Rock_C"]], p, spacing=1.2, row_gap=0.8, el=24, res=(1600, 900)),
    "rocks_back": lambda p: view_sheet([["Rock_A", "Rock_E", "Rock_B"], ["Rock_D", "Rock_C"]], p, spacing=1.2, row_gap=0.8, az=208, el=24, res=(1600, 900)),
    "rock_a": lambda p: view_sheet([["Rock_A", "Rock_B"]], p, spacing=1.0, az=35, el=24, res=(1600, 900)),
    "plants": lambda p: view_sheet([["Bush_A", "Bush_B", "Bush_C", "Vines_A"],
                                    ["Flowers_A", "Flowers_B", "Flowers_C", "Flowers_D", "GrassTuft_A", "GrassTuft_B", "GrassTuft_C", "LilyPad_A", "LilyPad_B"]],
                                   p, spacing=0.35, row_gap=0.5, el=24, lift={"Vines_A": 1.6}, res=(1600, 900)),
    "plants_back": lambda p: view_sheet([["Flowers_A", "Flowers_B", "Flowers_C", "Flowers_D", "GrassTuft_A", "GrassTuft_B", "GrassTuft_C", "LilyPad_A", "LilyPad_B"],
                                         ["Bush_A", "Bush_B", "Bush_C", "Vines_A"]],
                                        p, spacing=0.35, row_gap=0.5, az=200, el=24, lift={"Vines_A": 1.6}, res=(1600, 900)),
    "small": lambda p: view_sheet([["Flowers_A", "Flowers_B", "Flowers_C", "Flowers_D"], ["GrassTuft_A", "GrassTuft_B", "GrassTuft_C", "LilyPad_A", "LilyPad_B"]],
                                  p, spacing=0.3, row_gap=0.3, el=20, res=(1600, 900)),
}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    only = None
    views = None
    for i, a in enumerate(argv):
        if a == "--only":
            only = argv[i + 1].split(",")
        if a == "--views":
            views = argv[i + 1].split(",")
    names = [n for n in ASSETS if only is None or n in only]
    if "--no-export" not in argv:
        for n in names:
            V.reset_scene()
            obs = make(n)
            for ob, col in zip(obs, ASSETS[n][1]):
                lo, hi = size_of(ob)
                print("ASSET %-22s faces %6d  size %.2f x %.2f x %.2f m  z %.2f .. %.2f  slots %s" % (
                    ob.name, ob["voxel_faces"], hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2], lo[2], hi[2], [m.name[4:] for m in ob.data.materials]))
                V.export_gltf(ob, collision=col)
    if "--no-render" not in argv:
        for k in (views if views is not None else VIEWS):
            VIEWS[k](os.path.join(V.PREVIEWS, "nature_%s.png" % k))


main()
