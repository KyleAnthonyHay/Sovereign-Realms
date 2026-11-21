"""voxlib: build voxel models in Blender Python and turn them into meshes in the Sovereign Realms voxel style.

    import voxlib as V
    v = V.Vox(40, 32, 40, voxel=0.125, origin=(20, 16, 0))       # a 5 x 4 x 5 m volume, pivot under its middle
    v.box(0, 0, 0, 40, 32, 4, "stone")                             # x0 y0 z0 x1 y1 z1 (half-open), in voxels
    v.chunky("stone", seed=3)                                      # some blocks stick out, like dry stone
    ob = v.to_object("SM_Thing")                                   # culled faces, baked corner shading, UVs, slots
    V.export_gltf(ob, "/abs/path/SM_Thing.gltf")

Conventions
  * Blender axes: +X east (right), +Y north (away from the viewer), +Z up. A building's FRONT faces -Y.
  * One texel is 6.25 cm everywhere. Usual voxel sizes: 0.5 m terrain blocks (8 texels), 0.125 m for buildings and props
    (2 texels), 0.25 m leaf cubes (4 texels), 0.0625 m for pixel-art pieces such as banners (1 texel).
  * A voxel has a material (voxmats.MATS) and a tint colour; faces between solid voxels are never drawn.
  * Several Vox grids of different voxel sizes are combined with V.join([...]) into one mesh.
"""
import json
import math
import os
import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import voxmats
from voxmats import IDS, MATS, NAMES, PAL, TEXEL, TEX_SIZE

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
TEXTURES = os.path.join(ROOT, "SourceArt", "Textures")
MESHES = os.path.join(ROOT, "SourceArt", "Meshes")
PREVIEWS = os.path.join(ROOT, "SourceArt", "Previews")

AO_LEVELS = np.array([1.0, 0.86, 0.73, 0.62], dtype=np.float32)       # brightness for 0..3 occluding neighbours


# ---------------------------------------------------------------------------------------------------- colour

def srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def rgb(color):
    """'#rrggbb', a PAL name, or (r, g, b) in 0..255 -> uint8 triple (as seen on screen)."""
    if isinstance(color, str):
        if color in PAL:
            color = PAL[color]
        h = color.lstrip("#")
        return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.uint8)
    return np.array(color, dtype=np.uint8)


def _hash3(x, y, z, seed=0):
    """Integer lattice hash -> float 0..1 (arrays)."""
    h = (x.astype(np.int64) * 73856093) ^ (y.astype(np.int64) * 19349663) ^ (z.astype(np.int64) * 83492791) ^ (seed * 2654435761)
    h = (h ^ (h >> 13)) * 1274126177
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF).astype(np.float32) / float(0xFFFFFF)


def noise3(shape, scale, seed=0, octaves=3):
    """Smooth tiling-free value noise over a grid of `shape`, features about `scale` voxels wide. Returns 0..1."""
    out = np.zeros(shape, np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        s = max(1.0, scale / (2 ** o))
        gx, gy, gz = [np.arange(n, dtype=np.float32) / s for n in shape]
        X, Y, Z = np.meshgrid(gx, gy, gz, indexing="ij")
        x0, y0, z0 = np.floor(X).astype(np.int64), np.floor(Y).astype(np.int64), np.floor(Z).astype(np.int64)
        fx, fy, fz = X - x0, Y - y0, Z - z0
        fx, fy, fz = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy), fz * fz * (3 - 2 * fz)
        acc = 0
        for dx in (0, 1):
            for dy in (0, 1):
                for dz in (0, 1):
                    w = (fx if dx else 1 - fx) * (fy if dy else 1 - fy) * (fz if dz else 1 - fz)
                    acc = acc + w * _hash3(x0 + dx, y0 + dy, z0 + dz, seed + o * 17)
        out += acc * amp
        total += amp
        amp *= 0.5
    return out / total


def terraces(h, voxel=0.5, risers=(2, 1), first=None):
    """A smooth height field (metres over the ground, any shape) cut into the shallow terraces of a voxel hill: returns
    the height in whole blocks. The steps up from the ground are `risers` blocks high in turn, again and again
    ((2, 1): a 1 m bank, then half a metre, then 1 m, ...), so a gentle slope becomes many low grass shelves with thin
    dirt edges and not one ruled ramp or a sheer wall. `first`: the height of the lowest step alone, if it is to differ
    (2 blocks of 0.5 m and no unit steps onto the hill from the ground). Heights below half the lowest step are 0."""
    h = np.asarray(h, np.float32) / float(voxel)
    levels = [0]
    seq = ([int(first)] if first else []) + list(risers) * 64
    for r in seq:
        levels.append(levels[-1] + int(r))
        if levels[-1] > float(h.max()) + 1:
            break
    levels = np.array(levels, np.int32)
    # a column takes the highest level it reaches (the lowest: once it is half way up it)
    reach = np.concatenate([[0.0], [levels[1] * 0.5], levels[2:].astype(np.float32)])
    idx = np.clip(np.searchsorted(reach, h, side="right") - 1, 0, len(levels) - 1)
    return levels[idx]


def blob_outline(n, lo, hi, seed=0, lobes=(2, 3, 5)):
    """How far a hill reaches in each of n directions round its middle (metres, between lo and hi): a few slow waves of
    random phase, so the foot is an irregular, organic line and never a circle or the building's own rectangle."""
    rng = np.random.default_rng(seed)
    a = np.arange(n, dtype=np.float32) * (2.0 * math.pi / n)
    w = np.zeros(n, np.float32)
    for k in lobes:
        w += np.sin(a * k + rng.uniform(0, 2 * math.pi)) * rng.uniform(0.6, 1.0) / math.sqrt(k)
    w = (w - w.min()) / max(float(w.max() - w.min()), 1e-6)
    return lo + (hi - lo) * w


# ---------------------------------------------------------------------------------------------------- the grid

class Vox:
    """A box of voxels. All coordinates are voxel indices; boxes are half-open (x0 <= x < x1) and are clipped."""

    def __init__(self, nx, ny, nz, voxel=0.125, origin=(0, 0, 0), name="vox", seed=0):
        self.n = (int(nx), int(ny), int(nz))
        self.voxel = float(voxel)
        self.origin = tuple(float(o) for o in origin)      # the voxel coordinate that becomes the mesh's (0, 0, 0)
        self.name = name
        self.seed = seed
        self.m = np.zeros(self.n, np.uint8)                # material id, 0 = air
        self.c = np.full(self.n + (3,), 255, np.uint8)     # tint, sRGB
        self.sways = []                                    # (mask, axis, sign, lo, hi): cloth that moves in the wind (hang / fly)
        self.offset = (0.0, 0.0, 0.0)                      # metres, added when joined into an asset
        self.rot = 0                                       # quarter turns about Z (counter-clockwise from above), when joined

    # ---- basic shapes
    def _clip(self, x0, y0, z0, x1, y1, z1):
        x0, x1 = sorted((int(round(x0)), int(round(x1))))
        y0, y1 = sorted((int(round(y0)), int(round(y1))))
        z0, z1 = sorted((int(round(z0)), int(round(z1))))
        nx, ny, nz = self.n
        return max(0, x0), max(0, y0), max(0, z0), min(nx, x1), min(ny, y1), min(nz, z1)

    def box(self, x0, y0, z0, x1, y1, z1, mat, color=None):
        """Fill a box. mat: material name, or None / "air" to carve."""
        x0, y0, z0, x1, y1, z1 = self._clip(x0, y0, z0, x1, y1, z1)
        if x1 <= x0 or y1 <= y0 or z1 <= z0:
            return self
        self.m[x0:x1, y0:y1, z0:z1] = 0 if mat in (None, "air") else IDS[mat]
        self.c[x0:x1, y0:y1, z0:z1] = 255 if color is None else rgb(color)
        return self

    def clear(self, x0, y0, z0, x1, y1, z1):
        return self.box(x0, y0, z0, x1, y1, z1, None)

    def set(self, x, y, z, mat, color=None):
        return self.box(x, y, z, x + 1, y + 1, z + 1, mat, color)

    def get(self, x, y, z):
        nx, ny, nz = self.n
        if 0 <= x < nx and 0 <= y < ny and 0 <= z < nz:
            return NAMES[self.m[x, y, z]]
        return None

    def frame(self, x0, y0, z0, x1, y1, z1, mat, color=None, t=1):
        """Only the 12 edges of a box, t voxels thick (timber frames, lantern cages)."""
        for (a0, a1) in ((x0, x0 + t), (x1 - t, x1)):
            for (b0, b1) in ((y0, y0 + t), (y1 - t, y1)):
                self.box(a0, b0, z0, a1, b1, z1, mat, color)
        for (a0, a1) in ((x0, x0 + t), (x1 - t, x1)):
            for (c0, c1) in ((z0, z0 + t), (z1 - t, z1)):
                self.box(a0, y0, c0, a1, y1, c1, mat, color)
        for (b0, b1) in ((y0, y0 + t), (y1 - t, y1)):
            for (c0, c1) in ((z0, z0 + t), (z1 - t, z1)):
                self.box(x0, b0, c0, x1, b1, c1, mat, color)
        return self

    def grid(self):
        nx, ny, nz = self.n
        return np.meshgrid(np.arange(nx), np.arange(ny), np.arange(nz), indexing="ij")

    def where(self, mask, mat, color=None):
        """Fill wherever a boolean array (same shape as the grid) is True."""
        self.m[mask] = 0 if mat in (None, "air") else IDS[mat]
        self.c[mask] = 255 if color is None else rgb(color)
        return self

    def ellipsoid(self, cx, cy, cz, rx, ry, rz, mat, color=None, noise=0.0, noise_scale=6.0, seed=0):
        """A filled ellipsoid (centre and radii in voxels, may be fractional). noise > 0 makes the surface lumpy."""
        X, Y, Z = self.grid()
        d = ((X + 0.5 - cx) / rx) ** 2 + ((Y + 0.5 - cy) / ry) ** 2 + ((Z + 0.5 - cz) / rz) ** 2
        if noise > 0:
            d = d + (noise3(self.n, noise_scale, seed + self.seed) - 0.5) * 2.0 * noise
        return self.where(d <= 1.0, mat, color)

    def cylinder(self, cx, cy, z0, z1, r, mat, color=None, axis="z"):
        """A filled cylinder along an axis; (cx, cy) is the centre in the other two axes (x,y for z; y,z for x; x,z for y)."""
        X, Y, Z = self.grid()
        a, b, c = {"z": (X, Y, Z), "x": (Y, Z, X), "y": (X, Z, Y)}[axis]
        mask = ((a + 0.5 - cx) ** 2 + (b + 0.5 - cy) ** 2 <= r * r) & (c >= min(z0, z1)) & (c < max(z0, z1))
        return self.where(mask, mat, color)

    # ---- cloth
    def _sway(self, region, axis, sign, mats):
        m = self.mask(*mats)
        if region is not None:
            x0, y0, z0, x1, y1, z1 = self._clip(*region)
            keep = np.zeros_like(m)
            keep[x0:x1, y0:y1, z0:z1] = True
            m &= keep
        idx = np.argwhere(m)
        if len(idx):
            self.sways.append((m, axis, sign, float(idx[:, axis].min()), float(idx[:, axis].max() + 1)))
        return self

    def hang(self, region=None, mats=("paint",)):
        """Mark the painted voxels (of the whole grid, or of a box) as hanging cloth: a banner. In the engine it sways,
        not at all along its top edge and most at its foot (the weight goes into the vertex colours' alpha)."""
        return self._sway(region, 2, -1, mats)

    def fly(self, region=None, mats=("paint",)):
        """Mark the painted voxels as a flag flying towards +X from its hoist (the low-x edge stays put)."""
        return self._sway(region, 0, 1, mats)

    # ---- queries
    def mask(self, *mats):
        """Boolean array: voxels made of any of the materials (no names = any solid voxel)."""
        if not mats:
            return self.m > 0
        return np.isin(self.m, [IDS[n] for n in mats])

    def exposed(self, direction="+z"):
        """Boolean array: solid voxels whose neighbour in `direction` ('+x' '-x' '+y' '-y' '+z' '-z') is air."""
        axis = "xyz".index(direction[1])
        sign = 1 if direction[0] == "+" else -1
        solid = self.m > 0
        nb = np.zeros_like(solid)
        src = [slice(None)] * 3
        dst = [slice(None)] * 3
        if sign > 0:
            dst[axis], src[axis] = slice(0, -1), slice(1, None)
        else:
            dst[axis], src[axis] = slice(1, None), slice(0, -1)
        nb[tuple(dst)] = solid[tuple(src)]
        return solid & ~nb

    def bounds(self):
        """(min, max) corner of the solid voxels in voxel coordinates, or None if empty."""
        idx = np.argwhere(self.m > 0)
        if len(idx) == 0:
            return None
        return idx.min(axis=0), idx.max(axis=0) + 1

    # ---- surface treatments
    def scatter(self, src, dst, p=0.2, seed=0, direction=None, color=None, region=None):
        """Turn a random share p of `src` voxels into `dst` (moss on stone, gold in ore). direction: only voxels whose
        face that way is open, e.g. '+z' for tops. region: (x0, y0, z0, x1, y1, z1) limits it."""
        rng = np.random.default_rng(seed + self.seed * 7919)
        mask = self.mask(*([src] if isinstance(src, str) else src))
        if direction:
            mask &= self.exposed(direction)
        if region:
            x0, y0, z0, x1, y1, z1 = self._clip(*region)
            keep = np.zeros_like(mask)
            keep[x0:x1, y0:y1, z0:z1] = True
            mask &= keep
        mask &= rng.random(self.n) < p
        return self.where(mask, dst, color)

    def chunky(self, mats, cell=4, depth=1, p=0.3, seed=0, region=None):
        """Dry-stone look: a share p of the cell x cell x cell blocks of these materials swell outward by `depth` voxels
        wherever there is air next to them, so walls and rocks stop being flat. Cells are aligned to the grid."""
        mats = [mats] if isinstance(mats, str) else list(mats)
        X, Y, Z = self.grid()
        pick = _hash3(X // cell, Y // cell, Z // cell, seed + self.seed * 31 + 5) < p
        src = self.mask(*mats) & pick
        if region:
            x0, y0, z0, x1, y1, z1 = self._clip(*region)
            keep = np.zeros_like(src)
            keep[x0:x1, y0:y1, z0:z1] = True
            src &= keep
        for _ in range(depth):
            grow_m = np.zeros_like(self.m)
            grow_c = np.zeros_like(self.c)
            for axis in range(3):
                for sign in (1, -1):
                    sm = np.roll(np.where(src, self.m, 0), sign, axis=axis)
                    sc = np.roll(self.c, sign, axis=axis)
                    edge = [slice(None)] * 3
                    edge[axis] = 0 if sign > 0 else -1
                    sm[tuple(edge)] = 0
                    take = (sm > 0) & (self.m == 0) & (grow_m == 0)
                    grow_m[take] = sm[take]
                    grow_c[take] = sc[take]
            new = grow_m > 0
            self.m[new] = grow_m[new]
            self.c[new] = grow_c[new]
            src = new
        return self

    def erode(self, mats, p=0.2, seed=0, direction=None):
        """Remove a random share p of the surface voxels of these materials (ragged leaf clumps, crumbling edges)."""
        rng = np.random.default_rng(seed + self.seed * 104729)
        mats = [mats] if isinstance(mats, str) else list(mats)
        mask = self.mask(*mats)
        if direction:
            mask &= self.exposed(direction)
        else:
            surf = np.zeros_like(mask)
            for d in ("+x", "-x", "+y", "-y", "+z", "-z"):
                surf |= self.exposed(d)
            mask &= surf
        mask &= rng.random(self.n) < p
        self.m[mask] = 0
        return self

    def tint(self, mats, color, p=1.0, seed=0, cell=1):
        """Give (a share p of the cells of) these materials a tint colour: yellower leaves, a browner stone."""
        mats = [mats] if isinstance(mats, str) else list(mats)
        X, Y, Z = self.grid()
        pick = _hash3(X // cell, Y // cell, Z // cell, seed + self.seed * 13 + 3) < p
        mask = self.mask(*mats) & pick
        self.c[mask] = rgb(color)
        return self

    # ---- composing
    def stamp(self, other, x, y, z, rot=0, overwrite=True):
        """Paste another grid of the SAME voxel size so that its origin lands on voxel (x, y, z). rot: quarter turns
        about Z, counter-clockwise seen from above. Air in `other` never erases."""
        om, oc = other.m, other.c
        ox, oy, oz = [int(round(v)) for v in other.origin]
        k = rot % 4
        if k:
            om = np.rot90(om, k, axes=(0, 1))
            oc = np.rot90(oc, k, axes=(0, 1))
            nx, ny = other.n[0], other.n[1]
            for _ in range(k):                                # the origin turns with it
                ox, oy, nx, ny = ny - oy, ox, ny, nx
        sx, sy, sz = int(round(x)) - ox, int(round(y)) - oy, int(round(z)) - oz
        nx, ny, nz = self.n
        mx, my, mz = om.shape
        ax0, ay0, az0 = max(0, sx), max(0, sy), max(0, sz)
        ax1, ay1, az1 = min(nx, sx + mx), min(ny, sy + my), min(nz, sz + mz)
        if ax1 <= ax0 or ay1 <= ay0 or az1 <= az0:
            return self
        sub_m = om[ax0 - sx:ax1 - sx, ay0 - sy:ay1 - sy, az0 - sz:az1 - sz]
        sub_c = oc[ax0 - sx:ax1 - sx, ay0 - sy:ay1 - sy, az0 - sz:az1 - sz]
        take = sub_m > 0
        if not overwrite:
            take &= self.m[ax0:ax1, ay0:ay1, az0:az1] == 0
        self.m[ax0:ax1, ay0:ay1, az0:az1][take] = sub_m[take]
        self.c[ax0:ax1, ay0:ay1, az0:az1][take] = sub_c[take]
        return self

    def at(self, x=0.0, y=0.0, z=0.0, rot=0):
        """Where this grid's origin sits (metres) and its quarter turns about Z when joined into an asset."""
        self.offset = (float(x), float(y), float(z))
        self.rot = int(rot) % 4
        return self

    # ---- meshing
    def mesh_arrays(self):
        """-> dict(verts (F,4,3) metres, uvs (F,4,2), cols (F,4,3) linear, tris (F,6) corner order, slots [names], slot (F,))"""
        pad = 2
        m = np.pad(self.m, pad)
        solid = m > 0
        nx, ny, nz = self.n
        inner = (slice(pad, pad + nx), slice(pad, pad + ny), slice(pad, pad + nz))
        vox = self.voxel
        tpv = vox / TEXEL                                   # texels per voxel
        uv_scale = tpv / TEX_SIZE
        org = np.array(self.origin, np.float32)

        def shifted(arr, d):
            """arr sampled at p + d for every inner voxel p."""
            return arr[pad + d[0]:pad + d[0] + nx, pad + d[1]:pad + d[1] + ny, pad + d[2]:pad + d[2] + nz]

        slot_names = []
        slot_index = {}
        slot_of = np.zeros((len(NAMES), 3), np.int32)       # material id x (top, side, bottom) -> slot index
        for mid in range(1, len(NAMES)):
            for k, s in enumerate(MATS[NAMES[mid]]["slots"]):
                if s not in slot_index:
                    slot_index[s] = len(slot_names)
                    slot_names.append(s)
                slot_of[mid, k] = slot_index[s]
        jit = np.array([0.0] + [MATS[n]["jitter"] for n in NAMES[1:]], np.float32)
        warm = np.array([0.0] + [MATS[n]["warm"] for n in NAMES[1:]], np.float32)
        cell = np.array([1.0] + [max(1.0, round(MATS[n]["cell"] / vox)) for n in NAMES[1:]], np.float32)

        if self.sways and "cloth" not in slot_index:
            slot_index["cloth"] = len(slot_names)
            slot_names.append("cloth")
        V_, UV_, C_, T_, S_, A_ = [], [], [], [], [], []
        for axis in range(3):
            ua, va = [(1, 2), (0, 2), (0, 1)][axis]
            for sign in (1, -1):
                d = [0, 0, 0]
                d[axis] = sign
                face = solid[inner] & ~shifted(solid, d)
                idx = np.argwhere(face)
                if len(idx) == 0:
                    continue
                F = len(idx)
                mats = self.m[idx[:, 0], idx[:, 1], idx[:, 2]]
                # corner positions (voxel units) and occlusion
                corners = [(0, 0), (1, 0), (1, 1), (0, 1)]
                pos = np.zeros((F, 4, 3), np.float32)
                ao = np.zeros((F, 4), np.int32)
                for k, (cu, cv) in enumerate(corners):
                    p = idx.astype(np.float32).copy()
                    p[:, axis] += 1.0 if sign > 0 else 0.0
                    p[:, ua] += cu
                    p[:, va] += cv
                    pos[:, k] = p
                    du = [0, 0, 0]
                    dv = [0, 0, 0]
                    du[ua] = 1 if cu else -1
                    dv[va] = 1 if cv else -1
                    f1 = [d[i] + du[i] for i in range(3)]
                    f2 = [d[i] + dv[i] for i in range(3)]
                    f3 = [d[i] + du[i] + dv[i] for i in range(3)]
                    s1 = shifted(solid, f1)[idx[:, 0], idx[:, 1], idx[:, 2]]
                    s2 = shifted(solid, f2)[idx[:, 0], idx[:, 1], idx[:, 2]]
                    s3 = shifted(solid, f3)[idx[:, 0], idx[:, 1], idx[:, 2]]
                    ao[:, k] = np.where(s1 & s2, 3, s1.astype(np.int32) + s2 + s3)
                bright = AO_LEVELS[ao]
                # winding: (0,0) (1,0) (1,1) (0,1) faces +axis when (ua, va, axis) is a right-handed triple
                right_handed = (axis, ua, va) in ((0, 1, 2), (2, 0, 1))      # e_ua x e_va = +e_axis
                order = [0, 1, 2, 3] if (right_handed == (sign > 0)) else [0, 3, 2, 1]
                pos = pos[:, order]
                bright = bright[:, order]
                uv = np.stack([pos[:, :, ua], pos[:, :, va]], axis=-1) * uv_scale
                # split along the brighter diagonal (keeps corner shading symmetrical)
                flip = (bright[:, 1] + bright[:, 3]) > (bright[:, 0] + bright[:, 2])
                tris = np.where(flip[:, None], np.array([1, 2, 3, 1, 3, 0]), np.array([0, 1, 2, 0, 2, 3]))
                # tint: the voxel's colour, with the material's cell-to-cell variation
                cl = cell[mats].astype(np.int64)
                h = _hash3(idx[:, 0] // cl, idx[:, 1] // cl, idx[:, 2] // cl, self.seed + 11)
                h2 = _hash3(idx[:, 0] // cl, idx[:, 1] // cl, idx[:, 2] // cl, self.seed + 97)
                b = 1.0 + (h - 0.5) * 2.0 * jit[mats]
                w = (h2 - 0.5) * 2.0 * warm[mats]
                tint = srgb_to_linear(self.c[idx[:, 0], idx[:, 1], idx[:, 2]].astype(np.float32) / 255.0)
                tint = tint * b[:, None] * np.stack([1.0 + w, 1.0 + w * 0.35, 1.0 - w], axis=-1)
                col = tint[:, None, :] * bright[:, :, None]
                which = 2 if axis != 2 else (0 if sign > 0 else 1)
                face_slot = slot_of[mats, 1 if which == 2 else (0 if which == 0 else 2)].copy()
                weight = np.zeros((F, 4), np.float32)
                for (smask, sax, ssign, slo, shi) in self.sways:
                    sel = smask[idx[:, 0], idx[:, 1], idx[:, 2]]
                    if sel.any():
                        t = (pos[sel][:, :, sax] - slo) / max(1.0, shi - slo)
                        weight[sel] = np.clip(t if ssign > 0 else 1.0 - t, 0.0, 1.0)
                        face_slot[sel] = slot_index["cloth"]
                V_.append((pos - org) * vox)
                UV_.append(uv)
                C_.append(col)
                T_.append(tris)
                S_.append(face_slot)
                A_.append(weight)
        if not V_:
            return None
        return dict(verts=np.concatenate(V_), uvs=np.concatenate(UV_), cols=np.concatenate(C_), tris=np.concatenate(T_),
                    slot=np.concatenate(S_), slots=slot_names, alpha=np.concatenate(A_))

    def lights(self):
        """Centres (metres, this grid's own space) of each connected lump of 'glow' voxels: where a lamp's light goes."""
        cells = set(map(tuple, np.argwhere(self.m == IDS["glow"]).tolist()))
        out = []
        while cells:
            seed = cells.pop()
            lump, todo = [seed], [seed]
            while todo:
                x, y, z = todo.pop()
                for d in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
                    q = (x + d[0], y + d[1], z + d[2])
                    if q in cells:
                        cells.remove(q)
                        lump.append(q)
                        todo.append(q)
            c = (np.array(lump, np.float32).mean(axis=0) + 0.5 - np.array(self.origin, np.float32)) * self.voxel
            out.append((float(c[0]), float(c[1]), float(c[2]), len(lump) * self.voxel ** 3))
        return out

    def to_object(self, name=None, collection=None):
        return join([self], name or self.name, collection)


# ---------------------------------------------------------------------------------------------------- pixel art

def sprite(rows, palette, voxel=TEXEL, depth=1, axis="y", name="sprite", mat="paint"):
    """A flat pixel-art piece (banner, target, emblem) as voxels, one voxel per character.
    rows: strings, top row first; '.' or ' ' = empty. palette: {char: colour or (material, colour)}.
    The piece stands in the XZ plane (axis='y', facing -Y and +Y) `depth` voxels thick, or lies flat (axis='z').
    Its origin is the middle of its bottom edge (axis='y') or its centre (axis='z')."""
    h = len(rows)
    w = max(len(r) for r in rows)
    if axis == "y":
        v = Vox(w, depth, h, voxel, origin=(w / 2.0, depth / 2.0, 0), name=name)
    else:
        v = Vox(w, h, depth, voxel, origin=(w / 2.0, h / 2.0, 0), name=name)
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch in ". ":
                continue
            entry = palette[ch]
            m, c = (entry if isinstance(entry, tuple) and isinstance(entry[0], str) and entry[0] in IDS else (mat, entry))
            if axis == "y":
                v.box(i, 0, h - 1 - j, i + 1, depth, h - j, m, c)
            else:
                v.box(i, h - 1 - j, 0, i + 1, h - j, depth, m, c)
    return v


# ---------------------------------------------------------------------------------------------------- Blender side

def material(slot):
    """The preview material of a slot (texture x vertex colour; emission for the glowing ones)."""
    name = "Vox_" + slot
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    tex = nt.nodes.new("ShaderNodeTexImage")
    path = os.path.join(TEXTURES, "T_Vox_%s.png" % slot)
    if os.path.exists(path):
        tex.image = bpy.data.images.load(path, check_existing=True)
    tex.interpolation = "Closest"
    col = nt.nodes.new("ShaderNodeVertexColor")
    col.layer_name = "Col"
    mul = nt.nodes.new("ShaderNodeMixRGB")
    mul.blend_type = "MULTIPLY"
    mul.inputs[0].default_value = 1.0
    nt.links.new(tex.outputs["Color"], mul.inputs[1])
    nt.links.new(col.outputs["Color"], mul.inputs[2])
    nt.links.new(mul.outputs[0], bsdf.inputs["Base Color"])
    em, rough, metal = voxmats.SLOT_SURFACE.get(slot, (0.0, 0.9, 0.0))
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if em > 0:
        nt.links.new(mul.outputs[0], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = em * 0.3      # Cycles preview; Unreal uses the full value with bloom
    if slot == "water":
        bsdf.inputs["Roughness"].default_value = 0.08
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    return mat


def join(voxes, name="SM_Vox", collection=None):
    """One Blender mesh object from several grids (each placed by its .at(x, y, z, rot))."""
    parts = []
    slots = []
    lights = []
    for v in voxes:
        a = v.mesh_arrays()
        if a is None:
            continue
        for (lx, ly, lz, vol) in v.lights():
            for _ in range(v.rot % 4):
                lx, ly = -ly, lx
            lights.append([round(lx + v.offset[0], 4), round(ly + v.offset[1], 4), round(lz + v.offset[2], 4), round(vol, 5)])
        verts = a["verts"]
        k = v.rot % 4
        if k:
            ang = k * math.pi / 2
            ca, sa = round(math.cos(ang)), round(math.sin(ang))
            x, y = verts[..., 0].copy(), verts[..., 1].copy()
            verts = verts.copy()
            verts[..., 0] = x * ca - y * sa
            verts[..., 1] = x * sa + y * ca
        verts = verts + np.array(v.offset, np.float32)
        remap = []
        for s in a["slots"]:
            if s not in slots:
                slots.append(s)
            remap.append(slots.index(s))
        parts.append((verts, a["uvs"], a["cols"], a["tris"], np.array(remap, np.int32)[a["slot"]],
                      a["alpha"] if "alpha" in a else np.zeros(a["verts"].shape[:2], np.float32)))
    if not parts:
        raise RuntimeError("join: nothing to mesh in %s" % name)
    verts = np.concatenate([p[0] for p in parts])
    uvs = np.concatenate([p[1] for p in parts])
    cols = np.concatenate([p[2] for p in parts])
    tris = np.concatenate([p[3] for p in parts])
    slot = np.concatenate([p[4] for p in parts])
    alpha = np.concatenate([p[5] for p in parts])
    return mesh_object(name, verts, uvs, cols, tris, slot, slots, lights, collection, alpha)


def split(vox, name, chunk=24.0, collection=None):
    """Mesh ONE big grid (terrain) into several objects, one per chunk x chunk metre tile of the ground plan, so the
    engine can cull and light them separately. Faces between solid voxels stay culled across the tile borders.
    Returns the objects, named <name>_<i>_<j>."""
    a = vox.mesh_arrays()
    centre = a["verts"].mean(axis=1) + np.array(vox.offset, np.float32)
    ci = np.floor(centre[:, 0] / chunk).astype(np.int64)
    cj = np.floor(centre[:, 1] / chunk).astype(np.int64)
    out = []
    for i in sorted(set(ci.tolist())):
        for j in sorted(set(cj[ci == i].tolist())):
            m = (ci == i) & (cj == j)
            out.append(mesh_object("%s_%d_%d" % (name, i - ci.min(), j - cj.min()), a["verts"][m] + np.array(vox.offset, np.float32),
                                   a["uvs"][m], a["cols"][m], a["tris"][m], a["slot"][m], list(a["slots"]), [], collection, a["alpha"][m]))
    return out


def mesh_object(name, verts, uvs, cols, tris, slot, slots, lights=(), collection=None, alpha=None):
    """Blender mesh object from face arrays (see Vox.mesh_arrays)."""
    lights = list(lights)
    F = len(verts)
    used = sorted(set(slot.tolist()))                      # drop slots without faces
    lut = np.zeros(len(slots), np.int32)
    for i, s in enumerate(used):
        lut[s] = i
    slot = lut[slot]
    slots = [slots[s] for s in used]

    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(F * 4)
    mesh.vertices.foreach_set("co", verts.reshape(-1).astype(np.float32))
    loop_verts = (np.arange(F, dtype=np.int32)[:, None] * 4 + tris).reshape(-1)
    mesh.loops.add(F * 6)
    mesh.loops.foreach_set("vertex_index", loop_verts)
    mesh.polygons.add(F * 2)
    mesh.polygons.foreach_set("loop_start", np.arange(0, F * 6, 3, dtype=np.int32))
    try:
        mesh.polygons.foreach_set("loop_total", np.full(F * 2, 3, dtype=np.int32))
    except Exception:
        pass
    mesh.polygons.foreach_set("material_index", np.repeat(slot, 2).astype(np.int32))
    corner = (np.arange(F, dtype=np.int64)[:, None] * 4 + tris).reshape(-1)
    uv_layer = mesh.uv_layers.new(name="UVMap")
    uv_layer.data.foreach_set("uv", uvs.reshape(-1, 2)[corner].reshape(-1).astype(np.float32))
    attr = mesh.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="CORNER")
    rgba = np.zeros((F * 6, 4), np.float32)                 # alpha = how much the wind moves this corner (cloth only)
    rgba[:, :3] = np.clip(cols.reshape(-1, 3)[corner], 0.0, 4.0)
    if alpha is not None:
        rgba[:, 3] = alpha.reshape(-1)[corner]
    attr.data.foreach_set("color", rgba.reshape(-1))
    mesh.color_attributes.active_color = attr
    mesh.color_attributes.render_color_index = 0
    for s in slots:
        mesh.materials.append(material(s))
    mesh.update()
    mesh.validate()
    ob = bpy.data.objects.new(name, mesh)
    (collection or bpy.context.scene.collection).objects.link(ob)
    ob["voxel_faces"] = int(F)
    ob["lights"] = json.dumps(lights)
    return ob


def export_gltf(ob, path=None, collision="complex", extra=None):
    """Write one object as <name>.gltf (+ .bin) into SourceArt/Meshes; the file name becomes the Unreal asset name.
    A <name>.json goes with it: bounds, the lamp positions (every lump of 'glow' voxels; metres, Blender axes) and
    the collision the importer should give it: "complex" (walk on / bump into the exact voxels), "none" (walk
    through: leaves, flowers, cloth) or "box"."""
    path = path or os.path.join(MESHES, ob.name + ".gltf")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for o in bpy.context.scene.objects:
        o.select_set(o is ob)
    bpy.context.view_layer.objects.active = ob
    kw = dict(filepath=path, export_format="GLTF_SEPARATE", use_selection=True, export_apply=True, export_yup=True,
              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="NONE",
              export_animations=False, export_skins=False, export_morph=False, export_cameras=False, export_lights=False)
    try:
        bpy.ops.export_scene.gltf(export_vertex_color="ACTIVE", export_all_vertex_colors=False, **kw)
    except TypeError:
        bpy.ops.export_scene.gltf(**kw)
    co = np.zeros(len(ob.data.vertices) * 3, np.float32)
    ob.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    meta = dict(name=ob.name, faces=int(ob.get("voxel_faces", 0)), collision=collision,
                bounds=[[round(float(x), 4) for x in co.min(axis=0)], [round(float(x), 4) for x in co.max(axis=0)]],
                lights=json.loads(ob.get("lights", "[]")))
    meta.update(extra or {})
    with open(os.path.splitext(path)[0] + ".json", "w") as f:
        json.dump(meta, f, indent=1)
    print("exported %s (%d faces, %d lights)" % (path, meta["faces"], len(meta["lights"])))
    return path


# ---------------------------------------------------------------------------------------------------- previews

def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene


def look_at(ob, target):
    from mathutils import Vector
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def setup_light(scene, sun_az=-55.0, sun_el=30.0, strength=5.0, sky=0.9):
    """The style's light: a low warm sun from the side and a cool sky fill. sun_az: direction the light comes FROM,
    degrees clockwise from north (+Y) seen from above."""
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.80, 0.84, 0.92, 1.0)      # a pale, slightly warm sky: the shadows stay neutral, not blue
    bg.inputs[1].default_value = sky
    sun = bpy.data.lights.new("Sun", "SUN")
    sun.energy = strength
    sun.color = (1.0, 0.86, 0.66)
    sun.angle = math.radians(2.5)
    so = bpy.data.objects.new("Sun", sun)
    scene.collection.objects.link(so)
    a, e = math.radians(sun_az), math.radians(sun_el)
    so.location = (math.sin(a) * math.cos(e) * 50, math.cos(a) * math.cos(e) * 50, math.sin(e) * 50)
    look_at(so, (0, 0, 0))
    return so


def render(path, target=(0, 0, 1.5), az=28.0, el=32.0, dist=22.0, lens=85.0, res=(1280, 800), samples=48, ground=True,
           sun_az=-60.0, sun_el=32.0, exposure=0.0, engine="CYCLES"):
    """Render the current scene to a PNG. az: camera position in degrees clockwise from SOUTH seen from above
    (0 = straight in front of a building's front, positive = moved towards the east/right); el: elevation."""
    scene = bpy.context.scene
    if "Sun" not in bpy.data.objects:
        setup_light(scene, sun_az, sun_el)
    if ground and "PreviewGround" not in bpy.data.objects:
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
    cam.location = (target[0] + math.sin(a) * math.cos(e) * dist, target[1] - math.cos(a) * math.cos(e) * dist, target[2] + math.sin(e) * dist)
    look_at(cam, target)
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
    scene.view_settings.exposure = exposure
    if engine == "CYCLES":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
        scene.cycles.max_bounces = 4
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            prefs.compute_device_type = "METAL"
            prefs.get_devices()
            for dev in prefs.devices:
                dev.use = True
            scene.cycles.device = "GPU"
        except Exception:
            pass
    else:
        scene.render.engine = "BLENDER_EEVEE"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.render.render(write_still=True)
    print("rendered", path)
    return path
