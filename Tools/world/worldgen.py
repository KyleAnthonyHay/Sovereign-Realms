"""The land-shaping tools of the world generator: a World is a heightfield plus everything a map's plan puts on it.

A map's plan (maps.py) calls these in the order a landscape is read: the country (a base level rising away from the
rivers), tables and benches (plate: level ground with a hillside or a mountainside down from its rim), hills, mountains,
valleys and basins, then the water, the roads, the gold veins and the old ruins. finish() then makes it one surface:
the rim of mountains round the field, the bridgeheads and beaches, level pads, the small unevenness of real ground, the
roads graded into the slopes, and last the beds cut under the water.

Slopes are the rule everything keeps to (the game's grid closes a 1 m cell whose corners differ by more than a step,
45 cm): ground meant for walking is no steeper than about 1 in 5 (K_WALK); a barrier is a mountainside of 1 in 1.1 or
steeper (K_STEEP); the ground between the two is only ever the narrow band where one turns into the other.

Every map is symmetric (sym = 2: a half turn; 4: quarter turns): a feature given once is put down for every kingdom.
"""
import math

import numpy as np
from scipy import ndimage
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

import terrain as T
from terrain import N, X, Y

K_WALK, K_STEEP = 0.175, 0.95
WADE = 14.0                     # water deeper than this is a wall (USRFeelSettings::WadeDepth)
FORD_DEPTH = 8.0


def catmull(points, per=10):
    pts = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = (np.array(p, float) for p in pts[i - 1:i + 3])
        for k in range(per):
            t = k / per
            out.append(tuple(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3)))
    out.append(tuple(points[-1]))
    return out


def blob(cx, cy, rx, ry, seed, wobble=0.12, turn=0.0, n=72):
    """A rounded natural outline: an ellipse whose radius swells and narrows a little as it goes round."""
    r = np.random.default_rng(seed)
    ph = r.uniform(0, 2 * math.pi, 4)
    amp = r.uniform(0.4, 1.0, 4) * wobble / np.array([1.0, 1.4, 2.0, 2.6])
    pts = []
    ct, st = math.cos(math.radians(turn)), math.sin(math.radians(turn))
    for i in range(n):
        a = 2 * math.pi * i / n
        k = 1.0 + sum(amp[j] * math.sin((j + 2) * a + ph[j]) for j in range(4))
        x, y = rx * k * math.cos(a), ry * k * math.sin(a)
        pts.append((cx + x * ct - y * st, cy + x * st + y * ct))
    return Polygon(pts)


def wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


class World:
    def __init__(self, map_id, name, bound, sym, box, seed, note=""):
        self.id, self.name, self.note = map_id, name, note
        self.B, self.sym, self.box, self.seed = float(bound), sym, box, seed
        self.rng = np.random.default_rng(seed)
        self.H = np.zeros((N, N), np.float32)
        self.flat = np.zeros((N, N), bool)          # level ground (tables, pads): no unevenness is added here
        self.waters, self.fords, self.decks, self.roads, self.pads, self.shores = [], [], [], [], [], []
        self.veins, self.relics, self.towers, self.buildings = [], [], [], []
        self.forests, self.labels, self.mist, self.falls, self.tables, self.greens = [], [], [], [], [], []
        self.sites = []                             # (function, args): dressing that waits for the finished land
        self.keep = []                              # shapes kept clear of trees and boulders
        self.checks = []                            # (name, [masks' shapes closed], from, to): must NOT be walkable
        self.reach = []                             # (name, x, y): must be walkable from the player's start
        self.peaks = []                             # backdrop: (height grid, x, y, footprint, height, yaw)
        self.rim = dict(near=700.0, far=5200.0, start=-300.0, run=3800.0)
        self.starts = {}
        self.landmark = None
        self.relief = dict(tree_line=3000.0, rock_line=3300.0, snow_line=6200.0)
        self.flow = (-0.816, 0.578)
        self._rid = T.ridged(2600.0, seed + 5, 3, sym)
        self._warp = 260.0 * T.noise(2300.0, seed + 6, sym) + 90.0 * T.noise(900.0, seed + 7, sym)      # mountains' feet wander by this
        self._sd = {}

    # ---------------------------------------------------------------- symmetry
    def U(self, a, b):
        return float(self.rng.uniform(a, b))

    def ang(self, k):
        return 360.0 * k / self.sym

    def turn(self, p, k):
        a = math.radians(self.ang(k))
        c, s = round(math.cos(a), 12), round(math.sin(a), 12)
        return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)

    def orbit(self, p):
        return [self.turn(p, k) for k in range(self.sym)]

    def turn_geom(self, g, k):
        return g if k == 0 else affinity.rotate(g, self.ang(k), origin=(0, 0))

    def ks(self, sym):
        return range(self.sym) if sym else range(1)

    def near_squash(self, x):
        """Mountains keep their plan for every kingdom but not their height: toward the camera's side (-X) the summits
        are lower, so nothing tall stands between the camera and the troops."""
        return float(np.clip(0.34 + 0.66 * (x + self.B) / (1.5 * self.B), 0.34, 1.0))

    def sdist(self, g):
        key = id(g)
        if key not in self._sd:
            self._sd[key] = (g, T.sdist(g))
        return self._sd[key][1]

    # ---------------------------------------------------------------- the land
    def plate(self, poly, z, gentle=(), cliffs=(), c=None, kg=K_WALK, ks=K_STEEP, sym=True, blend=28.0, flat=True):
        """Level ground at height z inside `poly`, falling away from its rim: a hillside troops can climb (1 in 5) on
        the arcs listed in `gentle` [(bearing from the centre in degrees from +X, half width)], a mountainside
        elsewhere, and a rock face (its own slope) on `cliffs` [(bearing, half width, slope)]: a waterfall's cove."""
        c = c or (poly.centroid.x, poly.centroid.y)
        out = []
        for k in self.ks(sym):
            g, cc = self.turn_geom(poly, k), self.turn(c, k)
            d = T.sdist(g)
            th = np.degrees(np.arctan2(Y - cc[1], X - cc[0]))
            kf = np.full((N, N), ks, np.float32)
            for b, hw in gentle:
                w = 1.0 - T.smoothstep((np.abs(wrap180(th - b - self.ang(k))) - hw) / blend)
                kf = kf + (kg - kf) * w
            for b, hw, kc in cliffs:
                w = 1.0 - T.smoothstep((np.abs(wrap180(th - b - self.ang(k))) - hw) / 10.0)
                kf = kf + (kc - kf) * w
            p = z - kf * np.maximum(d, 0.0)
            self.H = np.where(d <= 0.0, z, T.smax(self.H, p, 160.0)).astype(np.float32)
            if flat:
                self.flat |= d < 120.0
            out.append(g)
        return out

    def knoll(self, x, y, r, h, sym=True):
        """A smooth rise (h over a radius r) added to the ground: walkable while h / r stays under about 0.12."""
        for k in self.ks(sym):
            px, py = self.turn((x, y), k)
            t = np.clip(T.point_dist(px, py) / r, 0.0, 1.0)
            self.H += (h * (1.0 - t * t) ** 2).astype(np.float32)

    def mount(self, pts, h, crest=300.0, k=1.1, shoulder=1500.0, rough=0.3, sym=True, warp=1.0):
        """A mountain: a mountainside (slope k) down from a crest line or point at height h, ragged with ridges. Above
        `shoulder` its summit is squashed on the camera's side of the map (near_squash); the foot is the same for all."""
        pts = [pts] if isinstance(pts[0], (int, float)) else list(pts)
        for kk in self.ks(sym):
            q = [self.turn(p, kk) for p in pts]
            d = (T.point_dist(*q[0]) if len(q) == 1 else T.line_dist(q)) - crest + self._warp * warp
            cone = h - k * np.maximum(d, 0.0)
            rag = (self._rid - 0.45) * rough * np.clip(cone - 600.0, 0.0, 2600.0)
            cone = cone + rag
            sq = self.near_squash(float(np.mean([p[0] for p in q])))
            p = np.minimum(cone, shoulder) + sq * np.maximum(cone - shoulder, 0.0)
            self.H = T.smax(self.H, p, 220.0).astype(np.float32)

    def basin(self, geom, z, k=0.3, sym=True, round_=160.0):
        """Low ground: nothing inside `geom` stays above z, and the land climbs out of it at slope k."""
        for kk in self.ks(sym):
            d = T.sdist(self.turn_geom(geom, kk))
            self.H = T.smin(self.H, z + k * np.maximum(d, 0.0), round_).astype(np.float32)

    def valley(self, pts, half, z, k=0.25, sym=True):
        for kk in self.ks(sym):
            d = T.line_dist([self.turn(p, kk) for p in pts]) - half
            self.H = T.smin(self.H, z + k * np.maximum(d, 0.0), 160.0).astype(np.float32)

    # ---------------------------------------------------------------- water, roads, places
    def water(self, geom, surface=-16.0, depth=154.0, name="water", bank=200.0, current=True):
        """A body of water (already in its final place: no symmetry is applied)."""
        self.waters.append(dict(geom=geom, surface=float(surface), depth=float(depth), name=name, bank=bank, current=current))

    def shore(self, geom, z, k=0.42, sym=True):
        """The land round `geom` is opened out to a shore climbing at slope k from height z, after the rim is raised
        (the lakes beyond the field, which would otherwise lie under the rim's mountains)."""
        for kk in self.ks(sym):
            self.shores.append((self.turn_geom(geom, kk), z, k))

    def ford(self, geom, surface=-16.0):
        self.fords.append(dict(geom=geom, surface=float(surface)))

    def deck(self, geom, name, surface=-16.0, lift=62.0, width=700.0):
        self.decks.append(dict(geom=geom, z=float(surface + lift), name=name, width=width))

    def road(self, pts, half=480.0, shoulder=1300.0, grade=0.175, fill=1.0, kind="earth", sym=True, name="road", smooth=10):
        for k in self.ks(sym):
            q = catmull([self.turn(p, k) for p in pts], smooth) if smooth else [self.turn(p, k) for p in pts]
            self.roads.append(dict(pts=q, half=half, shoulder=shoulder, grade=grade, fill=fill, kind=kind, name=name, keys=[self.turn(p, k) for p in pts]))

    def pad(self, x, y, r, z=None, skirt=600.0, sym=True, late=False):
        """Level ground within r of a spot (at height z, or the ground's own mean), eased back into the land over
        `skirt`. late: laid after the roads are graded (a vein, a ruin: its ground stays level whatever passes near)."""
        for k in self.ks(sym):
            px, py = self.turn((x, y), k)
            self.pads.append((px, py, r, z, skirt, late))

    def vein(self, x, y, sym=True, pad=True):
        for k in self.ks(sym):
            px, py = self.turn((x, y), k)
            self.veins.append((px, py))
            if pad:
                self.pads.append((px, py, 1250.0, None, 950.0, True))    # room for the mine and a tower beside it

    def green(self, x, y, r=1500.0, sym=True):
        """A level green in the open country: ground to build on away from home (a tower by a ford, a camp at a
        crossroads). Buildings need level ground and cannot make it."""
        for k in self.ks(sym):
            px, py = self.turn((x, y), k)
            self.pads.append((px, py, r, None, r * 0.75, True))
            self.greens.append((px, py, r))

    def ruin(self, x, y, relic=False, sym=True, pad=True, name=None):
        """An old tower (a Watchtower can be raised on it) or a relic (a Relic Tower)."""
        for k in self.ks(sym):
            px, py = self.turn((x, y), k)
            (self.relics if relic else self.towers).append((px, py, name))
            if pad:
                self.pads.append((px, py, 900.0, None, 750.0, True))

    def forest(self, x, y, rx, ry, count, sym=True, kinds="ABBCCD", turn=0.0):
        self.forests.append((x, y, rx, ry, count, kinds, turn, sym))    # (scattered for the player's kingdom, turned for the others)

    def label(self, x, y, text, sym=False, small=False):
        for k in self.ks(sym):
            px, py = self.turn((x, y), k)
            self.labels.append((px, py, text, small))

    def site(self, fn, x, y, yaw=0.0, sym=True, variants=None, **kw):
        """Dressing put down once the land is finished: fn(world, dress, x, y, yaw, tag, **kw) for every kingdom's
        copy. `variants`: a different function per copy (the same ground taken, a different thing standing on it)."""
        for k in self.ks(sym):
            px, py = self.turn((x, y), k)
            f = variants[k % len(variants)] if variants else fn
            self.sites.append((f, px, py, yaw + self.ang(k), "" if k == 0 else "_" + "abcd"[k], kw))

    # ---------------------------------------------------------------- finishing
    def finish(self, log=print):
        B = self.B
        out = np.maximum(np.abs(X), np.abs(Y)) - B
        # ---- the rim: mountains round the field, low on the camera's side, a wall on the far side
        far = np.clip((X + B) / (2.0 * B), 0.0, 1.0)
        amp = self.rim["near"] + (self.rim["far"] - self.rim["near"]) * far ** 1.4
        amp = amp * np.where(X > B, 1.25, 1.0) * np.where(X < -B, 0.75, 1.0)
        rz = T.smoothstep((out - self.rim["start"]) / self.rim["run"]) * amp * (0.35 + 0.95 * T.ridged(8000.0, self.seed + 71, 4))
        rz += T.smoothstep((out - 1500.0) / 6000.0) * amp * 0.5
        w = T.smoothstep((out - self.rim["start"]) / 500.0)
        self.H = (self.H * (1.0 - w) + T.smax(self.H, 380.0 + rz, 250.0) * w).astype(np.float32)
        for grid, px, py, size, height, yaw in self.peaks:      # the sculpted peaks of the far wall
            c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
            lx, ly = (X - px) * c + (Y - py) * s, -(X - px) * s + (Y - py) * c
            n = grid.shape[0]
            u, v = (lx / size + 0.5) * (n - 1), (ly / size + 0.5) * (n - 1)
            ok = (u >= 0) & (v >= 0) & (u <= n - 1) & (v <= n - 1)
            st = ndimage.map_coordinates(grid, [np.clip(u, 0, n - 1), np.clip(v, 0, n - 1)], order=1) * height
            self.H = np.where(ok, T.smax(self.H, st - 20.0, 200.0), self.H).astype(np.float32)
        # ---- shores of the outer lakes, the fords' beaches, the bridgeheads
        for geom, z, k in self.shores:
            self.H = T.smin(self.H, z + k * np.maximum(T.sdist(geom), 0.0), 200.0).astype(np.float32)
        for f in self.fords:
            d = self.sdist(f["geom"])
            near = 1.0 - T.smoothstep((d - 1200.0) / 1200.0)      # a beach: the banks come down gently to a ford, nowhere else
            self.H = (self.H * (1.0 - near) + T.smin(self.H, f["surface"] + 14.0 + 0.09 * np.maximum(d, 0.0), 60.0) * near).astype(np.float32)
        for dk in self.decks:
            mrr = dk["geom"].minimum_rotated_rectangle
            cs = np.array(mrr.exterior.coords)[:4]
            e0, e1 = cs[1] - cs[0], cs[2] - cs[1]
            if np.linalg.norm(e0) < np.linalg.norm(e1):
                e0, e1 = e1, e0
            mid = cs.mean(axis=0)
            dk["dir"] = e0 / np.linalg.norm(e0)
            dk["span"] = float(np.linalg.norm(e0))
            dk["mid"] = (float(mid[0]), float(mid[1]))
            for sg in (-1.0, 1.0):
                end = mid + dk["dir"] * sg * (dk["span"] * 0.5 + 150.0)
                self.pads.append((float(end[0]), float(end[1]), dk["width"] * 0.5 + 250.0, dk["z"], 700.0, False))
        # ---- level pads: the bridgeheads and the like now, the veins' and ruins' after the roads
        def lay(late):
            for px, py, r, z, skirt, when in self.pads:
                if when != late:
                    continue
                d = T.point_dist(px, py)
                if z is None:
                    z = float(self.H[d < r].mean())
                w = 1.0 - T.smoothstep((d - r) / skirt)
                self.H = (self.H * (1.0 - w) + z * w).astype(np.float32)
                self.flat |= d < r + 50.0
        lay(False)
        late_flat = np.zeros((N, N), bool)
        for px, py, r, z, skirt, when in self.pads:
            if when:
                late_flat |= T.point_dist(px, py) < r + 200.0
        # ---- the unevenness of real ground: slight where troops walk, craggy on the mountainsides, none on level ground
        sl = ndimage.gaussian_filter(T.slope(self.H), 2.0)
        steep = T.smoothstep((sl - 0.45) / 0.3)
        soft = 1.0 - np.clip(ndimage.gaussian_filter((self.flat | late_flat).astype(np.float32), 3.0) * 2.2, 0.0, 1.0)
        inside = 1.0 - T.smoothstep((out - 0.0) / 1500.0)
        detail = 13.0 * T.noise(1400.0, self.seed + 11, self.sym) + 5.0 * T.noise(520.0, self.seed + 12, self.sym)
        crag = 46.0 * T.noise(1250.0, self.seed + 13, self.sym) + 18.0 * T.noise(560.0, self.seed + 14, self.sym)
        wild = 70.0 * T.noise(2100.0, self.seed + 15) + 26.0 * T.noise(700.0, self.seed + 16)
        calm = np.clip(1.0 - sl / 0.3, 0.3, 1.0)                # a hillside troops climb is already near what they can: smoother there
        self.H += (soft * (detail * np.maximum(calm, steep) + steep * crag) * inside + (1.0 - inside) * wild * (0.3 + steep)).astype(np.float32)
        # ---- roads: graded into the land
        self._graded = np.full((N, N), 1e9, np.float32)         # distance to the roads laid so far: a later road meets them at their height
        for r in self.roads:
            self._grade(r)
        lay(True)
        # ---- water: the beds
        self.WS = np.full((N, N), np.nan, np.float32)           # water surface over each sample (nan: dry land)
        self.WD = np.full((N, N), 1e9, np.float32)              # signed distance to the nearest water's edge
        self.CUR = np.full((N, N), 1e9, np.float32)             # distance to running water (the rivers, not the still lakes)
        for wt in self.waters:
            d = self.sdist(wt["geom"])
            ins = d < 0.0
            bed = wt["surface"] - wt["depth"] * T.smoothstep((-d - 25.0) / wt["bank"])
            self.H = np.where(ins, np.minimum(self.H, bed), self.H)
            band = (d >= 0.0) & (d < 180.0)
            self.H = np.where(band, np.maximum(self.H, wt["surface"] + 10.0), self.H).astype(np.float32)
            self.WS = np.where(ins & ~(self.WS > wt["surface"]), wt["surface"], self.WS)
            self.WD = np.minimum(self.WD, d)
            if wt["current"]:
                self.CUR = np.minimum(self.CUR, np.maximum(d, 0.0))
        self.FORD = np.full((N, N), 1e9, np.float32)
        for f in self.fords:
            d = self.sdist(f["geom"])
            wet = (d < 0.0) & ~np.isnan(self.WS)
            self.H = np.where(wet, f["surface"] - FORD_DEPTH, self.H).astype(np.float32)
            self.FORD = np.minimum(self.FORD, d)
        self.H = np.maximum(self.H, -2500.0)
        # ---- what the rest of the generator reads
        self.SL = T.slope(self.H)
        self.ROAD = np.full((N, N), 1e9, np.float32)
        self.PAVED = np.full((N, N), 1e9, np.float32)
        for r in self.roads:
            d = T.line_dist(r["pts"])
            self.ROAD = np.minimum(self.ROAD, d)
            if r["kind"] == "paved":
                self.PAVED = np.minimum(self.PAVED, d)
        self.DECK = np.full((N, N), np.nan, np.float32)         # deck height over each sample (nan: none)
        for dk in self.decks:
            self.DECK = np.where(T.mask(dk["geom"]), dk["z"], self.DECK)
        self.OUT = out
        log("land: %.0f .. %.0f cm inside the field; water bodies %d, roads %d, pads %d" % (
            float(self.H[out < 0].min()), float(self.H[out < 0].max()), len(self.waters), len(self.roads), len(self.pads)))

    def _grade(self, r):
        """Lays one road into the land: its height along the way is the land's own, eased so that it never climbs
        steeper than its grade (cut into the rises, banked up over the dips; cut only where it comes down to a bridge,
        a ford or a road laid before it, whose height is given). Across, it keeps a little of the hillside's lean, so a road along a slope
        is a shelf in it, not a wall beside it; the land comes back to its own shape over the shoulders."""
        q, s = T.dense(r["pts"], 100.0)
        z0 = T.sample(self.H, q[:, 0], q[:, 1]).astype(np.float64)
        z0 = ndimage.gaussian_filter1d(z0, 3.0, mode="nearest")
        ds = np.diff(s, prepend=s[0])
        g = r["grade"]
        up, lo = z0.copy(), z0.copy()
        for i in range(1, len(z0)):
            up[i] = max(up[i], up[i - 1] - g * ds[i])
            lo[i] = min(lo[i], lo[i - 1] + g * ds[i])
        for i in range(len(z0) - 2, -1, -1):
            up[i] = max(up[i], up[i + 1] - g * ds[i + 1])
            lo[i] = min(lo[i], lo[i + 1] + g * ds[i + 1])
        # Level ground the road crosses keeps its height (a table, a bench, a bridgehead, a ford's beach): the road may
        # not rise faster than its grade away from it, so it comes down to a bridge in a cutting, never on a bank.
        cross = [dk["geom"] for dk in self.decks if dk.get("kind") != "dais"] + [f["geom"] for f in self.fords]
        near = np.full(len(q), 1e9)
        if cross:
            nn = np.array([min(c.distance(Point(x, y)) for c in cross) for x, y in q[::3]])
            near = np.interp(np.arange(len(q)), np.arange(len(q))[::3], nn)
        pin = T.nearest(self.flat, q[:, 0], q[:, 1]) | (near < 250.0) | (T.sample(self._graded, q[:, 0], q[:, 1]) < 320.0)
        zr = r["fill"] * up + (1.0 - r["fill"]) * lo
        if pin.any():
            cap = np.where(pin, z0, 1e9)
            for i in range(1, len(z0)):
                cap[i] = min(cap[i], cap[i - 1] + g * ds[i])
            for i in range(len(z0) - 2, -1, -1):
                cap[i] = min(cap[i], cap[i + 1] + g * ds[i + 1])
            zr = np.minimum(zr, cap)
        zr = ndimage.gaussian_filter1d(zr, 3.0, mode="nearest")
        tan = np.gradient(q, axis=0)
        tan /= np.maximum(np.linalg.norm(tan, axis=1, keepdims=True), 1e-9)
        nx, ny = -tan[:, 1], tan[:, 0]
        gx, gy = T.gradient(self.H)
        lean = T.sample(gx, q[:, 0], q[:, 1]) * nx + T.sample(gy, q[:, 0], q[:, 1]) * ny
        lean = np.clip(ndimage.gaussian_filter1d(lean, 8.0, mode="nearest"), -0.15, 0.15)
        d, sf = T.line_dist(r["pts"], want_s=True)
        w = 1.0 - T.smoothstep((d - r["half"]) / r["shoulder"])
        w = np.where(d > r["half"] + r["shoulder"], 0.0, w)
        w = np.where(self.flat & (d > r["half"]), 0.0, w)       # level ground beside the road stays level
        w = w * T.smoothstep(sf / 900.0) * T.smoothstep((s[-1] - sf) / 900.0)     # and a road's end eases into what it meets (another road, a table)
        # The road's surface, spread to the ground beside it: every stretch of the road says what height the ground
        # should have (its own, leaning as it leans), and the nearer stretches count for more. Inside a bend, where two
        # stretches at different heights are as near as each other, the ground is their blend, not a step between them.
        reach = r["half"] + r["shoulder"] + 150.0
        nc = int(math.ceil(reach / T.STEP))
        num = np.zeros((N, N), np.float64)
        den = np.zeros((N, N), np.float64)
        for k in range(len(q)):
            ci, cj = int(round((q[k, 0] - T.ORG) / T.STEP)), int(round((q[k, 1] - T.ORG) / T.STEP))
            i0_, i1_, j0_, j1_ = max(ci - nc, 0), min(ci + nc + 1, N), max(cj - nc, 0), min(cj + nc + 1, N)
            if i0_ >= i1_ or j0_ >= j1_:
                continue
            dx, dy = X[i0_:i1_, j0_:j1_] - q[k, 0], Y[i0_:i1_, j0_:j1_] - q[k, 1]
            wk = 1.0 / (dx * dx + dy * dy + 120.0 ** 2) ** 2
            num[i0_:i1_, j0_:j1_] += wk * (zr[k] + lean[k] * np.clip(dx * nx[k] + dy * ny[k], -reach, reach))
            den[i0_:i1_, j0_:j1_] += wk
        zf = np.where(den > 0.0, num / np.maximum(den, 1e-30), self.H)
        self.H = (self.H * (1.0 - w) + zf * w).astype(np.float32)
        self._graded = np.minimum(self._graded, d)
        r["profile"] = (s, zr)

    def scatter_hills(self, n, seed, h=(700.0, 1500.0), crest=(120.0, 320.0), clear=1500.0, k=0.95, edge=1500.0, region=None, extra_keep=()):
        """Rocky hills (tors) strewn over the open country of the player's part of the map and turned for the others:
        clear of roads, water, the level ground of tables and benches, veins, ruins, landmarks and each other."""
        keep = [LineString(r["keys"]).buffer(clear) for r in self.roads if len(r["keys"]) > 1]
        keep += [wt["geom"].buffer(1100.0) for wt in self.waters]
        keep += [Point(x, y).buffer(clear) for x, y in self.veins] + [Point(x, y).buffer(clear) for x, y, _ in self.relics + self.towers]
        keep += [Point(x, y).buffer(clear + 300.0) for _, x, y, _, _, _ in self.sites] + [Point(a).buffer(7600.0) for a in self.anchors]
        keep += [Point(x, y).buffer(max(rx, ry) * 0.6) for x, y, rx, ry, *_ in self.forests] + list(extra_keep)
        keep = unary_union(keep)
        from shapely.prepared import prep
        kp = prep(keep)
        flat = ndimage.binary_dilation(self.flat, iterations=14)
        r = np.random.default_rng(seed)
        made = []
        for _ in range(6000):
            if len(made) >= n:
                break
            x, y = float(r.uniform(-self.B + edge, self.B - edge)), float(r.uniform(-self.B + edge, self.B - edge))
            if region is not None and not region(x, y):
                continue
            pts = self.orbit((x, y))
            if any(kp.contains(Point(p)) or T.nearest(flat, p[0], p[1]) for p in pts):
                continue
            if any(math.hypot(px - mx, py - my) < 2600.0 for px, py in pts for mx, my in made):
                continue
            if any(math.hypot(pts[0][0] - px, pts[0][1] - py) < 2600.0 for px, py in pts[1:]):
                continue
            made += pts
            base = float(T.sample(self.H, x, y))
            hh, cr = float(r.uniform(*h)), float(r.uniform(*crest))
            a, ln = float(r.uniform(0, math.pi)), float(r.uniform(0.0, 900.0))
            pts_ = [(x - math.cos(a) * ln, y - math.sin(a) * ln), (x + float(r.normal(0, 200)), y + float(r.normal(0, 200))), (x + math.cos(a) * ln, y + math.sin(a) * ln)]
            self.mount(pts_ if ln > 250.0 else (x, y), base + hh, crest=cr, k=k * float(r.uniform(0.95, 1.25)), shoulder=base + 1000.0, rough=0.22, warp=1.5)
        self.tors = made
        return made

    # ---------------------------------------------------------------- reading the finished land
    def z(self, x, y):
        return float(T.sample(self.H, x, y))

    def slope_at(self, x, y):
        return float(T.sample(self.SL, x, y))

    def water_d(self, x, y):
        return float(T.sample(self.WD, x, y))

    def road_d(self, x, y):
        return float(T.sample(self.ROAD, x, y))

    def in_field(self, x, y, m=0.0):
        return abs(x) < self.B + m and abs(y) < self.B + m

    def level(self, x, y, r, tol=0.06):
        """Is the ground within r of (x, y) near enough level to stand something on (slope under tol)?"""
        for k in range(8):
            a = k * math.pi / 4
            if self.slope_at(x + math.cos(a) * r, y + math.sin(a) * r) > tol:
                return False
        return self.slope_at(x, y) <= tol
