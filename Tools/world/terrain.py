"""The heightfield under the world generator (gen_battlefield.py): the raster the land is modelled on, the fields it is
composed from (distances to shapes, noise), and the mesh made of it.

The land is one continuous surface: a height for every metre of a 1025 x 1025 raster (1 m steps, +/-512 m about the
map's centre). Nothing in it is a wall: a slope troops can walk is gentle (under about 1 in 4), a barrier is a
mountainside (1 in 1.4 or steeper), and the game's walkability grid tells them apart by the same rule the generator
checks (a 1 m cell whose corners differ by more than a step is closed).

The mesh is a right-triangulated irregular network cut from the raster: big triangles where the ground is level, small
ones where it bends, never further than a tolerance from the raster (a few cm where troops walk, more on the far
mountains). One triangulation for the whole world, so there are no cracks; it is dealt out into chunks for culling.
"""
import math

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
import mapbox_earcut as earcut

STEP = 100.0                    # cm between raster samples
HALF = 512                      # samples either side of the centre
N = 2 * HALF + 1
ORG = -HALF * STEP              # world coordinate of sample 0
AX = ORG + np.arange(N) * STEP
X, Y = np.meshgrid(AX, AX, indexing="ij")      # arrays are indexed [ix, iy]
SS = 2                          # shapes are rasterised this many times finer than the raster, for their distance fields
FN = (N - 1) * SS + 1
FSTEP = STEP / SS


# ============================================================================================ sampling
def sample(A, x, y):
    """Bilinear read of raster A at world (x, y); arrays or scalars. Clamped at the raster's edge."""
    fx = np.clip((np.asarray(x, np.float64) - ORG) / STEP, 0.0, N - 1.001)
    fy = np.clip((np.asarray(y, np.float64) - ORG) / STEP, 0.0, N - 1.001)
    i, j = fx.astype(np.int64), fy.astype(np.int64)
    u, v = fx - i, fy - j
    return A[i, j] * (1 - u) * (1 - v) + A[i + 1, j] * u * (1 - v) + A[i, j + 1] * (1 - u) * v + A[i + 1, j + 1] * u * v


def nearest(A, x, y):
    i = np.clip(np.rint((np.asarray(x, np.float64) - ORG) / STEP).astype(np.int64), 0, N - 1)
    j = np.clip(np.rint((np.asarray(y, np.float64) - ORG) / STEP).astype(np.int64), 0, N - 1)
    return A[i, j]


def gradient(A):
    """(dA/dx, dA/dy) per cm."""
    gx, gy = np.gradient(A, STEP)
    return gx, gy


def slope(A):
    gx, gy = gradient(A)
    return np.hypot(gx, gy)


# ============================================================================================ shapes -> fields
def _polys(geom):
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    return [g for g in geom.geoms if g.geom_type == "Polygon"]


def fine_mask(geom):
    """The shape on the fine raster (bool, [ix, iy])."""
    img = Image.new("L", (FN, FN), 0)
    d = ImageDraw.Draw(img)

    def px(ring):
        return [((y - ORG) / FSTEP, (x - ORG) / FSTEP) for x, y in ring.coords]

    polys = _polys(geom)
    for p in polys:
        d.polygon(px(p.exterior), fill=255)
    for p in polys:
        for hole in p.interiors:
            d.polygon(px(hole), fill=0)
    # (a hole that holds another polygon of the same shape, an island with a pond, is not drawn right: none here)
    return np.array(img) > 0


def mask(geom):
    return fine_mask(geom)[::SS, ::SS]


def sdist(geom):
    """Signed distance to the shape's outline, cm: negative inside. Good to about a quarter of a metre."""
    m = fine_mask(geom)
    if not m.any():
        return np.full((N, N), 1e9, np.float32)
    out = ndimage.distance_transform_edt(~m) - ndimage.distance_transform_edt(m)
    return (out[::SS, ::SS] * FSTEP).astype(np.float32)


def dense(pts, step=FSTEP * 0.5):
    """Points every `step` along a polyline, and the distance along it at each."""
    p = np.asarray(pts, np.float64)
    seg = np.hypot(*np.diff(p, axis=0).T)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    t = np.linspace(0.0, s[-1], max(int(math.ceil(s[-1] / step)), 1) + 1)
    return np.stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])], 1), t


def line_dist(pts, want_s=False):
    """Distance from every sample to a polyline (cm), and (want_s) how far along the line its nearest point is."""
    q, s = dense(pts)
    fi = np.rint((q[:, 0] - ORG) / FSTEP).astype(np.int64)
    fj = np.rint((q[:, 1] - ORG) / FSTEP).astype(np.int64)
    ok = (fi >= 0) & (fj >= 0) & (fi < FN) & (fj < FN)
    m = np.zeros((FN, FN), bool)
    m[fi[ok], fj[ok]] = True
    if not m.any():
        far = np.full((N, N), 1e9, np.float32)
        return (far, np.zeros((N, N), np.float32)) if want_s else far
    if not want_s:
        return (ndimage.distance_transform_edt(~m)[::SS, ::SS] * FSTEP).astype(np.float32)
    S = np.zeros((FN, FN), np.float32)
    S[fi[ok], fj[ok]] = s[ok]
    d, idx = ndimage.distance_transform_edt(~m, return_indices=True)
    ii, jj = idx[0][::SS, ::SS], idx[1][::SS, ::SS]
    return (d[::SS, ::SS] * FSTEP).astype(np.float32), S[ii, jj]


def point_dist(x, y):
    return np.hypot(X - x, Y - y)


# ============================================================================================ blending
def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def ramp(t):
    """0..1 with eased ends and a straight middle: its steepest part is 1.2 x the mean slope (a smoothstep's is 1.5 x)."""
    t = np.clip(t, 0.0, 1.0)
    e = 0.2
    a = 1.0 / (1.0 - e)                         # slope of the straight part
    lo = a * t * t / (2 * e)
    mid = a * (t - e * 0.5)
    hi = 1.0 - a * (1.0 - t) ** 2 / (2 * e)
    return np.where(t < e, lo, np.where(t > 1.0 - e, hi, mid))


def smax(a, b, k=200.0):
    """The higher of two surfaces, the crease between them rounded where they come within k cm of each other (and
    exactly the higher one everywhere else: level ground stays level)."""
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.maximum(a, b) + h * h * k * 0.25


def smin(a, b, k=200.0):
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * k * 0.25


# ============================================================================================ noise
def symmetrise(A, sym):
    """The same field for every kingdom: averaged over the map's symmetry (2: a half turn; 4: quarter turns)."""
    if sym == 2:
        return 0.5 * (A + A[::-1, ::-1])
    if sym == 4:
        return 0.25 * (A + np.rot90(A, 1) + np.rot90(A, 2) + np.rot90(A, 3))
    return A


def noise(wavelength, seed, sym=0):
    """Smooth value noise, about -1..1, features about `wavelength` cm across."""
    r = np.random.default_rng(seed)
    cell = max(wavelength / STEP * 0.5, 1.0)                  # raster samples per lattice step
    n = int(math.ceil(N / cell)) + 4
    small = r.standard_normal((n, n)).astype(np.float32)
    big = ndimage.zoom(small, cell, order=3)[:N, :N]
    big = symmetrise(big, sym)
    return (big / max(float(big.std()), 1e-6) * 0.5).clip(-1.4, 1.4)


def fbm(wavelength, seed, octaves=3, gain=0.5, sym=0):
    out = np.zeros((N, N), np.float32)
    amp, tot = 1.0, 0.0
    for k in range(octaves):
        out += amp * noise(wavelength / (2 ** k), seed + 17 * k, sym)
        tot += amp
        amp *= gain
    return out / tot


def ridged(wavelength, seed, octaves=3, sym=0):
    """Ridge noise 0..1: sharp crests, broad hollows (mountains)."""
    out = np.zeros((N, N), np.float32)
    amp, tot = 1.0, 0.0
    for k in range(octaves):
        n_ = noise(wavelength / (2 ** k), seed + 31 * k, sym)
        out += amp * (1.0 - np.minimum(np.abs(n_) * 1.6, 1.0)) ** 2
        tot += amp
        amp *= 0.5
    return out / tot


# ============================================================================================ the mesh
def rtin(H, tol):
    """Triangles (index triples into the flattened raster) of a crack-free triangulation that stays within `tol` (a
    raster of tolerances, cm) of H at every sample. Restricted quadtree / right-triangulated irregular network: a
    sample is kept when the straight edge that would replace it misses it by more than its tolerance, or when a finer
    sample that depends on it is kept."""
    n = H.shape[0]
    E = np.zeros((n, n), np.float32)
    H = H.astype(np.float64)
    size = 2
    while size <= n - 1:
        h, q = size // 2, size // 4
        m = (n - 1) // size
        # edge midpoints of the size-squares: on edges along x, then along y
        ex = np.abs(H[h::size, ::size] - 0.5 * (H[0:n - 1:size, ::size] + H[size::size, ::size])) / tol[h::size, ::size]
        ey = np.abs(H[::size, h::size] - 0.5 * (H[::size, 0:n - 1:size] + H[::size, size::size])) / tol[::size, h::size]
        if q:
            P = np.pad(E, q)                                   # their children: the four half-square centres round them
            for di in (-q, q):
                for dj in (-q, q):
                    ex = np.maximum(ex, P[h + di + q::size, dj + q::size][:m, :m + 1])
                    ey = np.maximum(ey, P[di + q::size, h + dj + q::size][:m + 1, :m])
        E[h::size, ::size] = ex
        E[::size, h::size] = ey
        # centres of the size-squares (either diagonal may be the edge that replaces one)
        c = H[h::size, h::size]
        d1 = np.abs(c - 0.5 * (H[0:n - 1:size, 0:n - 1:size] + H[size::size, size::size]))
        d2 = np.abs(c - 0.5 * (H[0:n - 1:size, size::size] + H[size::size, 0:n - 1:size]))
        ec = np.maximum(d1, d2) / tol[h::size, h::size]
        ec = np.maximum(ec, np.maximum(np.maximum(E[0:n - 1:size, h::size], E[size::size, h::size]), np.maximum(E[h::size, 0:n - 1:size], E[h::size, size::size])))
        E[h::size, h::size] = ec
        size *= 2
    keep = E > 1.0
    # split from the two halves of the whole square downward
    a = np.array([[0, 0], [n - 1, n - 1]], np.int32)
    b = np.array([[n - 1, n - 1], [0, 0]], np.int32)
    c = np.array([[n - 1, 0], [0, n - 1]], np.int32)
    done = []
    while len(a):
        mid = (a + b) // 2
        can = np.abs(a - b).max(axis=1) >= 2
        split = can & keep[mid[:, 0], mid[:, 1]]
        if (~split).any():
            done.append(np.stack([a[~split], b[~split], c[~split]], 1))
        a2, b2, c2, m2 = a[split], b[split], c[split], mid[split]
        a = np.concatenate([c2, b2])
        b = np.concatenate([a2, c2])
        c = np.concatenate([m2, m2])
    tris = np.concatenate(done)                                 # (T, 3, 2)
    return tris[:, :, 0].astype(np.int64) * n + tris[:, :, 1]


class ArrayMesh:
    """A mesh held as arrays (meshlib.write_gltf takes it like a Mesh)."""

    def __init__(self, name, p, n, uv0, uv1, idx):
        self.name = name
        self.p, self.n, self.uv0, self.uv1, self.idx = p, n, uv0, uv1, idx
        self.col = np.ones((len(p), 4), np.float32)

    def empty(self):
        return len(self.idx) == 0

    def recenter(self):
        c = np.round(np.array([(self.p[:, 0].min() + self.p[:, 0].max()) * 0.5, (self.p[:, 1].min() + self.p[:, 1].max()) * 0.5, 0.0]))
        self.p = self.p - c
        return tuple(float(v) for v in c)


def terrain_meshes(H, tol, box, chunk=6400.0, prefix="SM_T_Land"):
    """The land as chunk meshes. `box` = (x0, x1, y0, y1): triangles wholly outside it are dropped. UV0 = (y, -x) in
    cm (the materials' world-aligned frame), UV1 = (0, 2): the mark of the smooth land for M_Terrain. Smooth normals
    from the raster."""
    tris = rtin(H, tol)
    n = H.shape[0]
    hx, hy = gradient(H)
    px, py, pz = X.reshape(-1), Y.reshape(-1), H.reshape(-1)
    nrm = np.stack([-hx.reshape(-1), -hy.reshape(-1), np.ones(n * n)], 1)
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
    # counter-clockwise seen from above
    ax_, ay_ = px[tris[:, 0]], py[tris[:, 0]]
    cross = (px[tris[:, 1]] - ax_) * (py[tris[:, 2]] - ay_) - (py[tris[:, 1]] - ay_) * (px[tris[:, 2]] - ax_)
    flip = cross < 0
    tris[flip] = tris[flip][:, [0, 2, 1]]
    cx, cy = px[tris].mean(axis=1), py[tris].mean(axis=1)
    x0, x1, y0, y1 = box
    inside = (cx > x0) & (cx < x1) & (cy > y0) & (cy < y1)
    tris, cx, cy = tris[inside], cx[inside], cy[inside]
    ci = np.floor((cx - x0) / chunk).astype(np.int64)
    cj = np.floor((cy - y0) / chunk).astype(np.int64)
    key = ci * 1000 + cj
    order = np.argsort(key, kind="stable")
    tris, key = tris[order], key[order]
    out = []
    starts = np.flatnonzero(np.concatenate([[True], key[1:] != key[:-1]]))
    ends = np.concatenate([starts[1:], [len(key)]])
    for k, (s, e) in enumerate(zip(starts, ends)):
        t = tris[s:e]
        ids, inv = np.unique(t.reshape(-1), return_inverse=True)
        p = np.stack([px[ids], py[ids], pz[ids]], 1)
        uv0 = np.stack([py[ids], -px[ids]], 1)
        uv1 = np.tile(np.array([[0.0, 2.0]]), (len(ids), 1))
        out.append(ArrayMesh("%s_%03d" % (prefix, k), p, nrm[ids], uv0, uv1, inv.reshape(-1, 3)))
    return out, len(tris)


# ---- flat pieces laid on the land: bridge decks, a shrine's dais (the terraces' cap and wall, kept for masonry)
def ring_ccw(coords, ccw=True):
    pts = [(float(x), float(y)) for x, y in coords[:-1]]
    area = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        area += x0 * y1 - x1 * y0
    if (area > 0) != ccw:
        pts.reverse()
    return pts


def add_cap(mesh, poly, z, uv1=(0.0, 0.0)):
    rings = [ring_ccw(list(poly.exterior.coords))] + [ring_ccw(list(r.coords), False) for r in poly.interiors]
    verts = np.array([p for r in rings for p in r], np.float64)
    ends = np.cumsum([len(r) for r in rings]).astype(np.uint32)
    tris = earcut.triangulate_float64(verts, ends).reshape(-1, 3)
    zf = z if callable(z) else (lambda x, y: z)
    base = [mesh.vert((x, y, zf(x, y)), (0, 0, 1), (y, -x), uv1) for x, y in verts]
    for a, b, c in tris:
        pa, pb, pc = verts[a], verts[b], verts[c]
        if (pb[0] - pa[0]) * (pc[1] - pa[1]) - (pb[1] - pa[1]) * (pc[0] - pa[0]) > 0:
            mesh.tri(base[a], base[b], base[c])
        else:
            mesh.tri(base[a], base[c], base[b])


def add_wall(mesh, ring, top, bottom, smooth_deg=38.0, rock=0.0, tile=512.0):
    """Wall down from a ring with the solid on its left (exterior rings counter-clockwise, holes clockwise).
    UV0 = (distance along the outline, depth below the top) in cm; UV1.x = wall height; UV1.y = 1 for living rock."""
    pts = ring
    n = len(pts)
    seg = [np.array(pts[(i + 1) % n]) - np.array(pts[i]) for i in range(n)]
    seg_len = [float(np.linalg.norm(s)) for s in seg]
    nrm = [np.array([s[1], -s[0]]) / max(l, 1e-6) for s, l in zip(seg, seg_len)]
    total = sum(seg_len)
    scale = (max(round(total / tile), 1) * tile) / total if total > tile * 0.75 else 1.0
    cos_t = math.cos(math.radians(smooth_deg))
    height = top - bottom
    s = 0.0
    for i in range(n):
        if seg_len[i] < 1e-4:
            continue
        p0, p1 = pts[i], pts[(i + 1) % n]
        prev_n, next_n = nrm[(i - 1) % n], nrm[(i + 1) % n]
        n0 = nrm[i] + prev_n if float(np.dot(nrm[i], prev_n)) > cos_t else nrm[i]
        n1 = nrm[i] + next_n if float(np.dot(nrm[i], next_n)) > cos_t else nrm[i]
        n0 = n0 / np.linalg.norm(n0); n1 = n1 / np.linalg.norm(n1)
        s1 = s + seg_len[i]
        a = mesh.vert((p0[0], p0[1], top), (n0[0], n0[1], 0), (s * scale, 0.0), (height, rock))
        b = mesh.vert((p1[0], p1[1], top), (n1[0], n1[1], 0), (s1 * scale, 0.0), (height, rock))
        c = mesh.vert((p1[0], p1[1], bottom), (n1[0], n1[1], 0), (s1 * scale, height), (height, rock))
        d = mesh.vert((p0[0], p0[1], bottom), (n0[0], n0[1], 0), (s * scale, height), (height, rock))
        mesh.quad(a, d, c, b)
        s = s1
