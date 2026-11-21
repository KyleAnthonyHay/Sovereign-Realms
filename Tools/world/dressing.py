"""What stands on the finished land: gold veins, the old ruins, landmarks, woods, boulders, grass.

Dressing (the class) holds the three lists the level is built from (instances: the instanced families; actors: single
static mesh actors; blockers: one hidden box per thing troops must walk round) and scatters the general dressing.
The functions below it are the landmarks a map's plan asks for with World.site(): each puts its pieces down at one
spot, turned for the kingdom it belongs to. Anything that blocks is a single box, like every other obstacle.

Fairness: whatever takes ground troops could walk on (trunks, boulders, ruins) is placed for the player's kingdom and
turned for the others, so every kingdom has the same ground. Two different landmarks may share a site across kingdoms
(a colossus here, obelisks there): they take the same boxes.
"""
import math
import zlib

import numpy as np
from scipy import ndimage
from shapely.geometry import LineString, Point

import terrain as T
from terrain import N, X, Y
import props

TAGS = "abcd"


class Dressing:
    def __init__(self, W, fast=False):
        self.W, self.fast = W, fast
        self.rng = np.random.default_rng(W.seed + 1000)
        self.instances, self.actors, self.blockers = {}, [], []
        self.unique = []            # meshes made for this map alone (boulders, aqueducts)
        self.trees = []
        self.wood_trees = []        # (x, y, crown radius, wood index, mesh): the trees of the woods (the forest floor is laid under them)
        self.structures = []        # (kind, x, y) for the report
        # ground kept clear of scattered dressing: level building ground, roads, water, pads, landmarks' sites
        keep = ndimage.binary_dilation(W.flat, iterations=2) | (W.ROAD < 700.0) | (W.WD < 130.0)
        for px, py, r, z, skirt, late in W.pads:
            keep |= T.point_dist(px, py) < r + 250.0
        for _, x, y, _, _, kw in W.sites:
            keep |= T.point_dist(x, y) < kw.get("clear", 1200.0)
        for x, y in list(W.starts.values()):
            keep |= T.point_dist(x, y) < 1000.0
        self.keep = keep

    def U(self, a, b):
        return float(self.rng.uniform(a, b))

    # ---------------------------------------------------------------- the three lists
    def inst(self, mesh, x, y, yaw=None, scale=1.0, z=None, sink=0.0):
        self.instances.setdefault(mesh, []).append([round(x, 1), round(y, 1), round((self.W.z(x, y) if z is None else z) - sink, 1),
                                                    round(self.U(0, 360) if yaw is None else yaw, 1), round(scale, 3)])

    def actor(self, mesh, x, y, yaw, label, folder, z=None, tags=None, scale=1.0):
        a = {"mesh": mesh, "pos": [round(x, 1), round(y, 1), round(self.W.z(x, y) if z is None else z, 1)], "yaw": round(yaw, 1), "label": label, "folder": folder}
        if tags:
            a["tags"] = list(tags)
        if scale != 1.0:
            a["scale"] = scale
        self.actors.append(a)

    def block(self, label, x, y, size, yaw=0.0, z=None):
        zz = self.W.z(x, y) if z is None else z
        self.blockers.append({"label": label + "_Collision", "pos": [round(x, 1), round(y, 1), round(zz + size[2] * 0.5 - 8.0, 1)], "size": [float(s) for s in size], "yaw": round(yaw, 1)})

    def at(self, x, y, yaw, lx, ly):
        c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        return (x + lx * c - ly * s, y + lx * s + ly * c)

    def kept(self, x, y):
        return bool(T.nearest(self.keep, x, y))

    def free(self, x, y, r=0.0):
        """Open, dry, walkable ground clear of every blocker so far (within r)."""
        W = self.W
        if W.water_d(x, y) < r + 110.0 or W.slope_at(x, y) > 0.3:
            return False
        return all(math.hypot(b["pos"][0] - x, b["pos"][1] - y) > r + 110.0 + max(b["size"][0], b["size"][1]) * 0.5 for b in self.blockers[-600:])

    def spot(self, x, y, r, spread=500.0, tries=200, off_road=True, tol=0.09):
        """A dry spot near (x, y), level enough for something r across, whose copies in the other kingdoms are as good
        (what is put there is put in all of them)."""
        W = self.W

        def good(px, py):
            if not W.in_field(px, py, -r - 300.0) or W.water_d(px, py) < r + 150.0 or not W.level(px, py, r, tol):
                return False
            if off_road and W.road_d(px, py) < r + 560.0:
                return False
            return not self.kept(px, py) and self.free(px, py, r)

        for k in range(tries):
            sp = spread * k / tries
            px, py = (x, y) if k == 0 else (x + self.U(-sp, sp), y + self.U(-sp, sp))
            if all(good(qx, qy) for qx, qy in W.orbit((px, py))):
                return px, py
        return None

    # ---------------------------------------------------------------- veins and ruins
    def gameplay(self):
        W = self.W
        for i, (x, y) in enumerate(W.veins):
            self.actor("SM_GoldVein", x, y, self.U(0, 360), "GoldVein_%02d" % i, "Props/Veins")
        # A relic: the ancient ruin a Relic Tower is raised on (tag SRRelic; the game shows it as a Relic Tower's ruin).
        # An old tower: a Watchtower can be raised on it (tag SRRuinTower).
        for i, (x, y, name) in enumerate(W.relics):
            yaw = (i * 53.0) % 360.0
            self.actor("SM_Dolmen", x, y, yaw, "Relic_%02d" % i, "Props/Ruin", tags=["SRRelic"])
            self.block("Relic_%02d" % i, x, y, (300, 280, 200), yaw)
        for i, (x, y, name) in enumerate(W.towers):
            yaw = float(self.rng.integers(0, 4)) * 90.0 + self.U(-12, 12)
            self.actor("SM_Ruin_Tower", x, y, yaw, "RuinTower_%02d" % i, "Props/Ruin", tags=["SRRuinTower"])
            self.block("RuinTower_%02d" % i, x, y, (410, 410, 420), yaw)
        for fn, x, y, yaw, tag, kw in W.sites:
            fn(W, self, x, y, yaw, tag, **kw)

    # ---------------------------------------------------------------- woods, boulders, grass
    # what grows in a wood, by its character (the wood's index picks one): fir, oak, maple, birch, snag
    WOODS = [("pine", (0.80, 0.04, 0.0, 0.14, 0.02)), ("mixed", (0.40, 0.33, 0.10, 0.15, 0.02)), ("oak", (0.12, 0.56, 0.14, 0.13, 0.05)),
             ("autumn", (0.10, 0.17, 0.43, 0.28, 0.02))]
    CROWN = {"SM_Conifer_A": 115, "SM_Conifer_B": 150, "SM_Conifer_C": 185, "SM_Conifer_D": 225, "SM_Conifer_E": 265, "SM_Tree_Oak_A": 300, "SM_Tree_Oak_B": 390,
             "SM_Tree_Oak_C": 480, "SM_Tree_Maple_A": 250, "SM_Tree_Maple_B": 320, "SM_Tree_Birch_A": 150, "SM_Tree_Birch_B": 185, "SM_Tree_Snag": 60}

    @staticmethod
    def roll(x, y, salt=0):
        """A fixed number 0..1 for a spot (no random stream is drawn on: adding species moved nothing else on the maps)."""
        return (zlib.crc32(("%d,%d,%d" % (round(x), round(y), salt)).encode()) & 0xFFFFFF) / float(0x1000000)

    def wood_mesh(self, wood, kind, x, y):
        """The tree that stands at (x, y) in wood number `wood`, where the plan asked for a fir of size `kind` (A..E)."""
        _, mix = self.WOODS[wood % len(self.WOODS)]
        r, big = self.roll(x, y, 1), "ABCDE".index(kind)
        acc = 0.0
        for species, share in zip(("fir", "oak", "maple", "birch", "snag"), mix):
            acc += share
            if r < acc:
                break
        if species == "oak":
            return "SM_Tree_Oak_" + ("A" if big == 0 else ("B" if big < 3 else ("C" if self.roll(x, y, 2) < 0.6 else "B")))
        if species == "maple":
            return "SM_Tree_Maple_" + ("A" if big < 2 else "B")
        if species == "birch":
            return "SM_Tree_Birch_" + ("A" if big < 2 else "B")
        if species == "snag":
            return "SM_Tree_Snag"
        return "SM_Conifer_" + kind

    def tree(self, x, y, kind, scale=None, trunk=None, wood=None, key=None):
        """A tree; trunk: the label of its blocker box (a tree troops must walk round). wood: the index of the wood it
        stands in (its species follows the wood's character and the spot `key`, the same in every kingdom); None: a fir."""
        mesh = "SM_Conifer_" + kind if wood is None else self.wood_mesh(wood, kind, *(key or (x, y)))
        self.inst(mesh, x, y, scale=scale or self.U(0.92, 1.08), sink=6.0)
        self.trees.append((x, y))
        if wood is not None:
            self.wood_trees.append((x, y, self.CROWN.get(mesh, 150), wood, mesh))
        if trunk:
            self.block(trunk, x, y, (46, 46, 200))

    def scatter(self):
        W, B, rng, U = self.W, self.W.B, self.rng, self.U
        tree_line, rock_line = W.relief["tree_line"], W.relief["rock_line"]

        def near_tree(x, y, d=150.0, last=500):
            return any((x - tx) ** 2 + (y - ty) ** 2 < d * d for tx, ty in self.trees[-last:])

        # ---- woods in the field: stands of firs, each tree a small blocker (troops thread between the trunks). Given
        # for the player's kingdom, turned for the others.
        n_wood = 0
        for fi, (fx, fy, rx, ry, count, kinds, turn, sym) in enumerate(W.forests):
            ct, st = math.cos(math.radians(turn)), math.sin(math.radians(turn))
            made = 0
            for _ in range(count * 6):
                if made >= count:
                    break
                a, d = U(0, 2 * math.pi), math.sqrt(U(0.02, 1.0))
                lx, ly = rx * d * math.cos(a), ry * d * math.sin(a)
                cx, cy = fx + lx * ct - ly * st, fy + lx * st + ly * ct
                spread = U(300, 520)
                made += 1
                for _ in range(int(rng.integers(5, 10))):
                    a2, d2 = U(0, 2 * math.pi), spread * math.sqrt(U(0.02, 1.0))
                    x, y = cx + math.cos(a2) * d2, cy + math.sin(a2) * d2
                    pts = W.orbit((x, y)) if sym else [(x, y)]
                    ok = True
                    for px, py in pts:
                        if not W.in_field(px, py, -120.0) or self.kept(px, py) or W.z(px, py) > tree_line or near_tree(px, py, 150.0, 4000):
                            ok = False
                            break
                    if not ok:
                        continue
                    kind, s = kinds[int(rng.integers(0, len(kinds)))], U(0.92, 1.08)
                    for k, (px, py) in enumerate(pts):
                        walk = W.slope_at(px, py) < 0.34
                        self.tree(px, py, kind, s, trunk=("Fir_%d_%04d%s" % (fi, n_wood, "" if k == 0 else "_" + TAGS[k])) if walk else None, wood=fi, key=pts[0])
                        if rng.random() < 0.5:
                            a3 = U(0, 2 * math.pi)
                            fx_, fy_ = px + math.cos(a3) * U(80, 170), py + math.sin(a3) * U(80, 170)
                            if W.water_d(fx_, fy_) > 30.0 and W.road_d(fx_, fy_) > 200.0:
                                self.inst("SM_Tuft_Fern", fx_, fy_, yaw=U(-35, 35))
                    n_wood += 1
        # ---- firs on the hillsides and mountainsides (nobody walks there: no blockers), thinning toward the tree line
        n_hill = 0
        for _ in range(int((2 * B / 100.0) ** 2 * (0.06 if not self.fast else 0.02))):
            x, y = U(-B, B), U(-B, B)
            z, sl = W.z(x, y), W.slope_at(x, y)
            if sl < 0.5 or sl > 1.5 or z > tree_line or W.water_d(x, y) < 150.0 or rng.random() > 1.0 - 0.75 * z / tree_line or near_tree(x, y, 190.0):
                continue
            if x < -B * 0.55 and rng.random() < 0.6:           # fewer on the camera's side: they would stand in front of the field
                continue
            self.tree(x, y, "ABCD"[int(rng.choice(4, p=[0.3, 0.34, 0.26, 0.1]))])
            n_hill += 1
        # ---- stands beyond the field (dressing only)
        x0, x1, y0, y1 = W.box
        n_out = 0
        for _ in range(int((x1 - x0) * (y1 - y0) / 1e8 * (2.2 if not self.fast else 0.7))):
            cx, cy = U(-B - 500, x1 - 600), U(y0 + 600, y1 - 600)
            if W.in_field(cx, cy, 300.0):
                continue
            for _ in range(int(rng.integers(4, 10))):
                a, d = U(0, 2 * math.pi), U(240, 520) * math.sqrt(U(0.02, 1.0))
                x, y = cx + math.cos(a) * d, cy + math.sin(a) * d
                if W.in_field(x, y, 80.0) or x < -B or W.water_d(x, y) < 100.0 or W.z(x, y) > tree_line or W.slope_at(x, y) > 1.3 or near_tree(x, y):
                    continue
                self.tree(x, y, "ABCDE"[int(rng.choice(5, p=[0.12, 0.26, 0.3, 0.22, 0.10]))], U(1.0, 1.35))
                n_out += 1
        # ---- boulders troops walk round (a box each, a mesh of its own), strewn about the open country
        n_rock = 0
        self.block_rocks = []
        want = int(26 * (B / 24000.0) ** 2)
        for _ in range(20000):
            if n_rock >= want:
                break
            x, y = U(-B + 400, B - 400), U(-B + 400, B - 400)
            pts = W.orbit((x, y))
            if any(self.kept(px, py) or W.slope_at(px, py) > 0.2 or not self.free(px, py, 150.0) for px, py in pts):
                continue
            if any(math.hypot(pts[0][0] - px, pts[0][1] - py) < 800.0 for px, py in pts[1:]):
                continue
            size, yaw = (U(200, 330), U(170, 250), U(130, 220)), U(-60, 60)
            for k, (px, py) in enumerate(pts):
                name = "Rock_%02d%s" % (n_rock, "" if k == 0 else "_" + TAGS[k])
                self.block(name, px, py, size, yaw + W.ang(k), z=W.z(px, py) - 4.0)
                self.block_rocks.append((name, px, py, size, yaw + W.ang(k)))
                self.actor("SM_" + name, px, py, 0.0, name, "Props/Rocks")
                for _ in range(int(rng.integers(3, 6))):
                    a, d = U(0, 2 * math.pi), max(size[0], size[1]) * U(0.62, 0.95)
                    self.inst("SM_Rock_S%d" % rng.integers(0, 3), px + math.cos(a) * d, py + math.sin(a) * d, sink=4.0)
                for _ in range(3):
                    a, d = U(0, 2 * math.pi), max(size[0], size[1]) * U(0.6, 0.85)
                    self.inst("SM_Tuft_Fern", px + math.cos(a) * d, py + math.sin(a) * d, yaw=U(-30, 30))
            n_rock += 1
        # ---- rocks at the feet of the mountainsides and on them; outcrops beyond the field
        n_scree = 0
        for _ in range(int((2 * B / 100.0) ** 2 * (0.02 if not self.fast else 0.006))):
            x, y = U(-B - 800, B + 800), U(-B - 800, B + 800)
            sl = W.slope_at(x, y)
            if sl < 0.42 or W.water_d(x, y) < 60.0 or W.road_d(x, y) < 500.0:
                continue
            roll = rng.random()
            if roll < 0.5:
                self.inst("SM_Rock_S%d" % rng.integers(0, 3), x, y, sink=6.0)
            elif roll < 0.8:
                self.inst("SM_Rock_M%d" % rng.integers(0, 3), x, y, sink=24.0)
            elif sl > 0.7 and not W.in_field(x, y, -600.0) or sl > 0.9:
                self.inst("SM_Rock_L%d" % rng.integers(0, 3), x, y, sink=60.0)
            n_scree += 1
        for _ in range(240):
            x, y = U(-B - 1300, x1 - 800), U(y0 + 800, y1 - 800)
            if W.in_field(x, y, 320.0) or W.water_d(x, y) < 200.0 or W.slope_at(x, y) > 0.5:
                continue
            self.inst("SM_Rock_%s%d" % ("M" if (x < -B or rng.random() < 0.45) else "L", rng.integers(0, 3)), x, y, sink=12.0)
            for _ in range(int(rng.integers(2, 5))):
                a, d = U(0, 2 * math.pi), U(110, 220)
                self.inst("SM_Rock_S%d" % rng.integers(0, 3), x + math.cos(a) * d, y + math.sin(a) * d, sink=4.0)
        for _ in range(int(260 * (B / 24000.0) ** 2)):         # loose stones in the field (ankle high: dressing only)
            cx, cy = U(-B + 200, B - 200), U(-B + 200, B - 200)
            if self.kept(cx, cy) or W.water_d(cx, cy) < 120.0:
                continue
            for _ in range(int(rng.integers(2, 5))):
                self.inst("SM_Rock_S%d" % rng.integers(0, 3), cx + float(rng.normal(0, 45)), cy + float(rng.normal(0, 45)), sink=9.0)
        # ---- grass: blade cards in clumps over the turf (troops wade through them; no collision, no shadow)
        n_tuft = 0
        area = (2 * B / 100.0) ** 2
        clumps = int(area * (0.3 if B < 30000.0 else 0.2) * (1.0 if not self.fast else 0.1))
        cx_, cy_ = rng.uniform(-B - 300, B + 300, clumps), rng.uniform(-B - 300, B + 300, clumps)
        zz, ss = T.sample(W.H, cx_, cy_), T.sample(W.SL, cx_, cy_)
        wd, rd, dry = T.sample(W.WD, cx_, cy_), T.sample(W.ROAD, cx_, cy_), T.sample(W.DRY, cx_, cy_)
        ok = (wd > 12.0) & (zz < rock_line) & (ss < 0.6) & (rd > 190.0)
        for i in np.flatnonzero(ok):
            kind = "SM_Tuft_Dry" if rng.random() < dry[i] * 0.6 else ("SM_Tuft_Tall" if rng.random() < 0.55 else "SM_Tuft_Short")
            for _ in range(int(rng.integers(2, 5))):
                x, y = cx_[i] + float(rng.normal(0, 34)), cy_[i] + float(rng.normal(0, 34))
                self.inst(kind, x, y, yaw=U(-32, 32))
                n_tuft += 1
        for _ in range(int(area * (0.03 if not self.fast else 0.003))):       # sparser beyond the field, seen only far off
            cx, cy = U(-B - 1300, B + 4600), U(-B - 3600, B + 3600)
            if W.in_field(cx, cy) or W.water_d(cx, cy) < 12.0 or W.z(cx, cy) > rock_line or W.slope_at(cx, cy) > 0.6:
                continue
            for _ in range(int(rng.integers(2, 5))):
                self.inst("SM_Tuft_Tall" if rng.random() < 0.55 else "SM_Tuft_Short", cx + float(rng.normal(0, 34)), cy + float(rng.normal(0, 34)), yaw=U(-32, 32))
        for _ in range(int(420 * (B / 24000.0) ** 2)):         # flower patches
            cx, cy = U(-B, B), U(-B, B)
            if W.water_d(cx, cy) < 40.0 or W.road_d(cx, cy) < 260.0 or W.z(cx, cy) > rock_line or W.slope_at(cx, cy) > 0.4:
                continue
            for _ in range(int(rng.integers(2, 5))):
                self.inst("SM_Tuft_Flower", cx + float(rng.normal(0, 50)), cy + float(rng.normal(0, 50)), yaw=U(-30, 30))
        # ---- reeds along the banks and standing in the fords' and marshes' shallows
        n_reed = 0
        for _ in range(int(area * (0.05 if not self.fast else 0.01))):
            x, y = U(-B - 300, B + 300), U(-B - 300, B + 300)
            d = W.water_d(x, y)
            if not (6.0 < d < 85.0) or W.road_d(x, y) < 600.0 or T.sample(W.FORD, x, y) < 300.0 or not np.isnan(T.nearest(W.DECK, x, y)):
                continue
            kind = "SM_Tuft_Dry" if rng.random() < 0.65 else "SM_Tuft_Tall"
            for _ in range(int(rng.integers(2, 5))):
                px, py = x + U(-35, 35), y + U(-35, 35)
                if W.water_d(px, py) > 4.0:
                    self.inst(kind, px, py, yaw=U(-32, 32))
                    n_reed += 1
        for f in W.fords:
            minx, miny, maxx, maxy = f["geom"].bounds
            if f["geom"].area > 1.2e6:                          # a ford proper: left clear for the crossing
                continue
            for _ in range(int(f["geom"].area / 5200.0)):
                x, y = U(minx, maxx), U(miny, maxy)
                if f["geom"].contains(Point(x, y)):
                    self.inst("SM_Tuft_Dry" if rng.random() < 0.7 else "SM_Tuft_Tall", x, y, yaw=U(-32, 32), scale=U(1.0, 1.25), z=max(W.z(x, y), f["surface"] - 6.0))
        # ---- fences, stumps and logs round the kingdoms
        fi = 0
        for kind, bx, by, yaw, team, label in W.buildings:
            if kind != "castle":
                continue
            for j in range(9):
                a, d = U(0, 2 * math.pi), U(1700, 3300)
                x, y = bx + math.cos(a) * d, by + math.sin(a) * d
                if W.road_d(x, y) < 700.0 or W.slope_at(x, y) > 0.1 or W.water_d(x, y) < 100.0:
                    continue
                if j < 5:
                    self.actor("SM_Fence_" + "AB"[fi % 2], x, y, U(0, 180), "Fence_%02d" % fi, "Props/Fences")
                elif j < 8:
                    self.actor("SM_Stump", x, y, U(0, 360), "Stump_%02d" % fi, "Props/Logs")
                else:
                    self.actor("SM_Log", x, y, U(0, 180), "Log_%02d" % fi, "Props/Logs")
                fi += 1
        print("firs: %d in the woods (trunks block), %d on the hillsides, %d beyond the field; boulders %d (x%d), scree %d, tufts %d, reeds %d" % (
            sum(1 for b in self.blockers if b["label"].startswith("Fir_")), n_hill, n_out, n_rock, W.sym, n_scree, n_tuft, n_reed))

    def groves(self):
        """The woods made into forests (after scatter(), on a random stream of its own, so nothing scatter() placed moves):
        more trees between the stands until the crowns close (each a trunk box like the rest, never nearer than 2.6 m to
        another trunk or 3.2 m across a ride left open through the wood, so troops still thread through), then the
        forest floor: bracken, bramble, bluebells, toadstools, saplings, shrubs at the edges, fallen timber and stumps.
        The undergrowth blocks nothing. Also thins the meadow grass under the canopy."""
        W, B = self.W, self.W.B
        rng = np.random.default_rng(W.seed + 7777)
        U = lambda a, b: float(rng.uniform(a, b))
        tree_line = W.relief["tree_line"]
        from scipy.spatial import cKDTree
        pts_all = list(self.trees)
        kd = cKDTree(np.array(pts_all)) if pts_all else None
        added = []                                              # trunks added here (the tree above is not rebuilt)
        bx = np.array([[b["pos"][0], b["pos"][1], max(b["size"][0], b["size"][1]) * 0.5] for b in self.blockers if not b["label"].startswith("Fir_")] or [[1e9, 1e9, 0.0]])

        def clear(x, y, gap):
            if kd is not None and kd.query_ball_point((x, y), gap):
                return False
            if any((x - ax) ** 2 + (y - ay) ** 2 < gap * gap for ax, ay in added[-400:]):
                return False
            return bool(np.all(np.hypot(bx[:, 0] - x, bx[:, 1] - y) > bx[:, 2] + 230.0))

        n_new = n_under = n_wood = 0
        for fi, (fx, fy, rx, ry, count, kinds, turn, sym) in enumerate(W.forests):
            ct, st = math.cos(math.radians(turn)), math.sin(math.radians(turn))
            name = self.WOODS[fi % len(self.WOODS)][0]
            # the ride: a way left open through the wood along its long axis, wandering a little
            long_x = rx >= ry
            ph, amp = U(0, 6.28), U(0.12, 0.26)

            def ride_d(lx, ly):
                a, b_, ra, rb = (lx, ly, rx, ry) if long_x else (ly, lx, ry, rx)
                return abs(b_ - rb * amp * math.sin(a / ra * 2.6 + ph))

            # ---- more trees between the stands
            added.clear()
            mine = 0
            for _ in range(int(count * 26)):
                a, d = U(0, 2 * math.pi), math.sqrt(U(0.0, 1.0)) * 0.96
                lx, ly = rx * d * math.cos(a), ry * d * math.sin(a)
                if ride_d(lx, ly) < 170.0:
                    continue
                x, y = fx + lx * ct - ly * st, fy + lx * st + ly * ct
                pts = W.orbit((x, y)) if sym else [(x, y)]
                gap = 250.0 + 70.0 * d                          # closest in the heart of the wood, looser at its edge
                if any(not W.in_field(px, py, -120.0) or self.kept(px, py) or W.z(px, py) > tree_line or W.water_d(px, py) < 140.0 or not clear(px, py, gap) for px, py in pts):
                    continue
                kind = kinds[int(rng.integers(0, len(kinds)))]
                if d < 0.55 and rng.random() < 0.3:
                    kind = "D"                                  # old trees in the heart of it
                sc = U(0.9, 1.12)
                for k, (px, py) in enumerate(pts):
                    walk = W.slope_at(px, py) < 0.34
                    self.tree(px, py, kind, sc, trunk=("Fir_%d_g%04d%s" % (fi, n_wood, "" if k == 0 else "_" + TAGS[k])) if walk else None, wood=fi, key=pts[0])
                    added.append((px, py))
                    n_new += 1
                n_wood += 1
                mine += 1
            # ---- the forest floor (dressing: no collision, its own copies in each kingdom need not match)
            for x, y, crown, wood, mesh in [t for t in self.wood_trees if t[3] == fi]:
                def near(lo, hi):
                    a, d = U(0, 2 * math.pi), U(lo, hi)
                    return x + math.cos(a) * d, y + math.sin(a) * d
                def ok(px, py):
                    return W.water_d(px, py) > 40.0 and W.road_d(px, py) > 260.0 and W.slope_at(px, py) < 0.6
                for _ in range(int(rng.integers(1, 4))):                    # bracken round the trunks
                    px, py = near(60, 230)
                    if ok(px, py):
                        self.inst("SM_Under_DeadBracken" if (name == "autumn" and rng.random() < 0.55) or rng.random() < 0.12 else "SM_Under_Bracken", px, py, yaw=U(-35, 35), scale=U(0.85, 1.3))
                        n_under += 1
                roll = rng.random()
                if roll < 0.16:                                             # toadstools at a trunk's foot
                    for _ in range(int(rng.integers(1, 4))):
                        px, py = near(34, 80)
                        if ok(px, py):
                            self.inst("SM_Under_Toadstool", px, py, yaw=U(-30, 30), scale=U(0.7, 1.1))
                            n_under += 1
                elif roll < 0.30:                                           # bramble
                    px, py = near(90, 260)
                    if ok(px, py):
                        self.inst("SM_Under_Bramble", px, py, yaw=U(-35, 35), scale=U(0.9, 1.4))
                        n_under += 1
                elif roll < 0.42:                                           # a sapling reaching for a gap
                    px, py = near(170, 330)
                    if ok(px, py):
                        self.inst("SM_Under_Sapling", px, py, yaw=U(-35, 35), scale=U(1.0, 1.7))
                        n_under += 1
                elif roll < 0.50 and name in ("oak", "mixed"):               # a drift of bluebells
                    cx, cy = near(120, 300)
                    for _ in range(int(rng.integers(6, 14))):
                        px, py = cx + float(rng.normal(0, 70)), cy + float(rng.normal(0, 70))
                        if ok(px, py):
                            self.inst("SM_Under_Bluebell", px, py, yaw=U(-30, 30), scale=U(0.8, 1.15))
                            n_under += 1
                elif roll < 0.56:                                           # fallen timber, a stump
                    px, py = near(130, 300)
                    if ok(px, py) and W.slope_at(px, py) < 0.3:
                        self.inst(("SM_Log_Mossy", "SM_Log_Broken", "SM_Log_Stump")[int(rng.integers(0, 3))], px, py, scale=U(0.85, 1.15), sink=3.0)
                        for _ in range(2):
                            qx, qy = px + U(-90, 90), py + U(-90, 90)
                            if ok(qx, qy):
                                self.inst("SM_Under_Toadstool", qx, qy, yaw=U(-30, 30), scale=U(0.7, 1.0))
            # shrubs along the wood's edge and in the ride's mouths (waist to head high; troops push through)
            for _ in range(int(count * 2.2)):
                a = U(0, 2 * math.pi)
                d = U(0.86, 1.08)
                lx, ly = rx * d * math.cos(a), ry * d * math.sin(a)
                if ride_d(lx, ly) < 260.0:
                    continue
                x, y = fx + lx * ct - ly * st, fy + lx * st + ly * ct
                for px, py in (W.orbit((x, y)) if sym else [(x, y)]):
                    if W.in_field(px, py, -100.0) and not self.kept(px, py) and W.water_d(px, py) > 120.0 and W.slope_at(px, py) < 0.5 and W.z(px, py) < tree_line:
                        self.inst("SM_Bush_A" if rng.random() < 0.6 else "SM_Bush_B", px, py, scale=U(0.85, 1.25), sink=4.0)
                        n_under += 1
        # ---- the canopy (for the forest floor's map and the grass under it)
        self.canopy = self.canopy_field()
        thinned = 0
        for mesh in ("SM_Tuft_Tall", "SM_Tuft_Short", "SM_Tuft_Dry", "SM_Tuft_Flower"):
            items = self.instances.get(mesh)
            if not items:
                continue
            arr = np.array([(it[0], it[1]) for it in items])
            c = T.sample(self.canopy, arr[:, 0], arr[:, 1])
            keep = [it for it, cv in zip(items, c) if cv < 0.35 or self.roll(it[0], it[1], 9) < 0.22]
            thinned += len(items) - len(keep)
            self.instances[mesh] = keep
        print("woods: %d trees added between the stands (%d in all, trunks block), undergrowth %d, grass thinned under the canopy %d" % (
            n_new, len(self.wood_trees), n_under, thinned))

    def canopy_field(self):
        """How closed the canopy is over each metre of the land (0 open sky .. 1 deep in a wood), from the woods' trees."""
        C = np.zeros((N, N), np.float32)
        for x, y, crown, wood, mesh in self.wood_trees:
            i, j = int(round((x - T.ORG) / T.STEP)), int(round((y - T.ORG) / T.STEP))
            if 2 <= i < N - 2 and 2 <= j < N - 2:
                C[i, j] += (crown / 200.0) ** 2
        C = ndimage.gaussian_filter(C, 3.2) * 2.0 * math.pi * 3.2 * 3.2 / 9.0     # roughly: crown area per 9 m2 of ground
        return np.clip(C * 1.15, 0.0, 1.0).astype(np.float32)

    def rubble(self):
        """Loose stone where turf gives way to rock (the crest of every mountainside: M_Terrain's RockSlope) and pebbles
        along the banks. Dressing only (ankle high, no collision). Its own random stream, so nothing else on the map
        moves when this is tuned."""
        W, B = self.W, self.W.B
        rng = np.random.default_rng(W.seed + 4242)
        n = int((2 * B / 100.0) ** 2 * (2.4 if not self.fast else 0.05))          # the first sixth of the samples make the crests, all of them the banks
        x, y = rng.uniform(-B - 600, B + 600, n), rng.uniform(-B - 600, B + 600, n)
        sl, wd, rd = T.sample(W.SL, x, y), T.sample(W.WD, x, y), T.sample(W.ROAD, x, y)
        roll, yaw, sc = rng.random(n), rng.uniform(0, 360, n), rng.uniform(0.55, 1.25, n)
        # the broken lip: a band either side of the slope where the rock starts (0.59), thickest right on it
        crest = (np.abs(sl - 0.57) < 0.11 * (0.35 + roll)) & (wd > 60.0) & (rd > 320.0) & (np.arange(n) < n // 6)
        n_crest = n_bank = 0
        for i in np.nonzero(crest)[0]:
            k = int(yaw[i] * 7.0) % 3
            if roll[i] < 0.8:
                self.inst("SM_Rock_S%d" % k, float(x[i]), float(y[i]), yaw=float(yaw[i]), scale=float(sc[i]), sink=5.0 * sc[i])
            else:
                self.inst("SM_Rock_M%d" % k, float(x[i]), float(y[i]), yaw=float(yaw[i]), scale=float(sc[i] * 0.8), sink=20.0 * sc[i])
            n_crest += 1
        # pebbles on the banks (not on the fords, the roads or the kingdoms' level ground)
        fd = T.sample(W.FORD, x, y)
        bank = (wd > 12.0) & (wd < 95.0) & (roll < 0.3) & (rd > 420.0) & (fd > 260.0) & (sl < 0.5)
        for i in np.nonzero(bank)[0]:
            self.inst("SM_Rock_S%d" % (int(yaw[i] * 7.0) % 3), float(x[i]), float(y[i]), yaw=float(yaw[i]), scale=float(sc[i] * 0.6), sink=5.0)
            n_bank += 1
        print("rubble: %d stones along the crests, %d pebbles on the banks" % (n_crest, n_bank))

    def rock_meshes(self):
        """A mesh of its own for each blocking boulder, over its box."""
        out = []
        for name, x, y, size, yaw in self.block_rocks:
            m = props.Mesh("SM_" + name)
            seed = zlib.crc32(name.split("_")[0].encode() + name.split("_")[1].encode())
            props.hull_rock(None, (size[0] * 1.22, size[1] * 1.22, size[2] * 1.15), 17, seed=seed % 1000, into=m, yaw=yaw)
            r2 = np.random.default_rng(seed % 977)
            for _ in range(int(r2.integers(2, 4))):
                a = math.radians(yaw) + r2.uniform(0, 2 * math.pi)
                k = r2.uniform(0.38, 0.55)
                props.hull_rock(None, (size[0] * k * 1.2, size[1] * k * 1.1, size[2] * k), 13, seed=int(r2.integers(1e6)), into=m,
                                offset=(math.cos(a) * size[0] * 0.5, math.sin(a) * size[1] * 0.5, 0.0), yaw=r2.uniform(0, 180))
            out.append(m)
        return out


# ============================================================================================ landmarks
def _piece(D, mesh, x, y, yaw, label, block=None, folder="Props/Ruin", z=None):
    D.actor(mesh, x, y, yaw, label, folder, z=z)
    if block:
        D.block(label, x, y, block, yaw, z=z)


def shrine(W, D, x, y, yaw, tag, **kw):
    """The shrine on the river island, the map's landmark: a paved dais ringed by standing stones, with pillars where
    the king's road enters and leaves it. The stones block; the road and the sides toward the veins stay open."""
    for sg, t2 in ((1.0, ""), (-1.0, "m")):
        for i, off in enumerate((45.0, 70.0, 110.0, 135.0)):
            a = math.radians(yaw + off) + (math.pi if sg < 0 else 0.0)
            sx, sy = x + 780.0 * math.cos(a), y + 780.0 * math.sin(a)
            _piece(D, "SM_Menhir_%d" % (i % 3), sx, sy, math.degrees(a) + 90.0, "Shrine_Stone_%d%s" % (i, t2), (84, 64, 220), "Props/Ruin")
        for i, (off, mesh, hgt) in enumerate(((21.0, "SM_Ruin_Pillar", 320), (-21.0, "SM_Ruin_PillarBroken", 190))):
            a = math.radians(yaw + off) + (math.pi if sg < 0 else 0.0)
            _piece(D, mesh, x + 700.0 * math.cos(a), y + 700.0 * math.sin(a), yaw, "Shrine_Pillar_%d%s" % (i, t2), (88, 88, hgt))
        for i, (along, across, yw) in enumerate(((120.0, 300.0, 35.0), (-60.0, 380.0, -50.0), (260.0, 430.0, 8.0))):
            px, py = D.at(x, y, yaw + (180.0 if sg < 0 else 0.0), along, across)
            _piece(D, "SM_Ruin_Block", px, py, yaw + yw, "Shrine_Block_%d%s" % (i, t2))
        bx, by = D.at(x, y, yaw + (180.0 if sg < 0 else 0.0), 0.0, 470.0)
        D.actor("SM_BannerPole", bx, by, 0, "Shrine_BannerPole" + t2, "Props/Ruin")
        D.actor("SM_BannerCloth", bx, by, 0, "Shrine_Banner" + t2, "Props/Ruin")
    D.structures.append(("shrine", x, y))


def bridge_dressing(W, D, x, y, yaw, tag, **kw):
    """Every bridge: a pillar pair at each end (blocking, on the banks beside the deck) and a low parapet along each
    side of the slab, one run of it fallen into the stream."""
    n = 0
    for dk in W.decks:
        if dk.get("kind") == "dais":
            continue
        mid, dv, span, half = np.array(dk["mid"]), dk["dir"], dk["span"], dk["width"] * 0.5
        pv = np.array([-dv[1], dv[0]])
        dyaw = math.degrees(math.atan2(dv[1], dv[0]))
        for end in (-1.0, 1.0):
            for sd in (-1.0, 1.0):
                p = mid + dv * end * (span * 0.5 + 40.0) + pv * sd * (half + 90.0)
                if W.water_d(p[0], p[1]) < 60.0:
                    p = mid + dv * end * (span * 0.5 + 170.0) + pv * sd * (half + 90.0)
                mesh, hgt = (("SM_Ruin_Pillar", 320) if (end * sd) > 0 else ("SM_Ruin_PillarBroken", 190))
                _piece(D, mesh, p[0], p[1], dyaw, "Bridge_Pillar_%02d" % n, (88, 88, hgt))
                n += 1
        runs = max(int(span // 300.0), 1)
        for sd in (-1.0, 1.0):
            for j in range(runs):
                if (sd > 0 and j == 1) or (sd < 0 and j == runs - 1):
                    continue
                p = mid + dv * (-0.5 * runs * 300.0 + 150.0 + j * 300.0) + pv * sd * (half - 22.0)
                D.actor("SM_Ruin_Parapet", p[0], p[1], dyaw - 90.0, "Bridge_Parapet_%02d" % n, "Props/Ruin", z=dk["z"])
                n += 1


def ruin(W, D, x, y, yaw, tag, n=0, **kw):
    """The old kingdom's ruins: an arch with a run of wall, a broken pillar and fallen blocks round it."""
    lab = "Ruin_%d%s" % (n, tag)
    D.actor("SM_Ruin_Arch", x, y, yaw, lab + "_Arch", "Props/Ruin")
    for j, ly in enumerate((-190.0, 190.0)):
        D.block("%s_Arch%d" % (lab, j), *D.at(x, y, yaw, 0.0, ly), (88, 88, 320), yaw)
    _piece(D, "SM_Ruin_Wall", *D.at(x, y, yaw, 30.0, 470.0), yaw + 8.0, lab + "_Wall", (60, 372, 170))
    _piece(D, "SM_Ruin_PillarBroken", *D.at(x, y, yaw, -60.0, -430.0), yaw + 30.0, lab + "_Pillar", (88, 88, 190))
    for j, (lx, ly, yw) in enumerate(((150.0, -60.0, 35.0), (-170.0, 250.0, -40.0), (210.0, 330.0, 12.0))):
        _piece(D, "SM_Ruin_Block", *D.at(x, y, yaw, lx, ly), yaw + yw, "%s_Block%d" % (lab, j))
    D.structures.append(("ruin", x, y))


def stone_circle(W, D, x, y, yaw, tag, n=0, **kw):
    """A ring of standing stones round a dolmen (dressing: not a relic)."""
    lab = "Circle_%d%s" % (n, tag)
    _piece(D, "SM_Dolmen", x, y, 20.0 + yaw, lab + "_Dolmen", (300, 280, 200), "Props/Rocks")
    for j in range(7):
        if j == 2:
            continue                                            # one stone has fallen: the way in
        a = math.radians(yaw + 12.0 + j * 360.0 / 7.0)
        sx, sy = x + 420.0 * math.cos(a), y + 420.0 * math.sin(a)
        _piece(D, "SM_Menhir_%d" % (j % 3), sx, sy, math.degrees(a) + 90.0, "%s_Stone%d" % (lab, j), (84, 64, 220), "Props/Rocks")
    D.structures.append(("stone circle", x, y))


def great_circle(W, D, x, y, yaw, tag, **kw):
    """The Great Circle on the High Moor: two rings of standing stones round the relic at the map's heart, open toward
    each kingdom, with an avenue of stones leading in along each road and four obelisks at the quarters."""
    k = 0
    for ring, count, gap in ((980.0, 16, 14.0), (1500.0, 24, 10.0)):
        for j in range(count):
            a = 360.0 * (j + 0.5) / count
            if min(abs((a - d + 180.0) % 360.0 - 180.0) for d in (45.0, 135.0, 225.0, 315.0)) < gap:
                continue                                        # the ways in, toward the four kingdoms
            ar = math.radians(a)
            sx, sy = x + ring * math.cos(ar), y + ring * math.sin(ar)
            _piece(D, "SM_Menhir_%d" % (k % 3), sx, sy, a + 90.0, "Great_Stone_%02d" % k, (84, 64, 220), "Props/Rocks")
            k += 1
    for q in range(4):
        a = math.radians(45.0 + 90.0 * q)
        for j, dist in enumerate((2300.0, 2900.0, 3500.0)):     # the avenues
            for sd in (-1.0, 1.0):
                sx = x + dist * math.cos(a) - sd * 620.0 * math.sin(a)
                sy = y + dist * math.sin(a) + sd * 620.0 * math.cos(a)
                _piece(D, "SM_Menhir_%d" % ((j + q) % 3), sx, sy, math.degrees(a), "Great_Avenue_%d_%d_%d" % (q, j, int(sd > 0)), (84, 64, 220), "Props/Rocks")
        b = math.radians(90.0 * q + 22.0)
        ox, oy = x + 2100.0 * math.cos(b), y + 2100.0 * math.sin(b)
        _piece(D, "SM_Ruin_Obelisk" if q != 2 else "SM_Ruin_ObeliskBroken", ox, oy, 45.0, "Great_Obelisk_%d" % q, (124, 124, 420))
    D.structures.append(("the Great Circle", x, y))


def colossus(W, D, x, y, yaw, tag, **kw):
    """A king of the old realm, broken off at the knees; his head lies in the grass."""
    _piece(D, "SM_Ruin_Colossus", x, y, yaw, "Colossus" + tag, (340, 460, 300))
    D.block("Colossus_Head" + tag, *D.at(x, y, yaw, -330.0, 150.0), (200, 180, 170), yaw)
    for j, (lx, ly) in enumerate(((620.0, -420.0), (-650.0, -380.0), (560.0, 520.0))):
        _piece(D, "SM_Ruin_Block", *D.at(x, y, yaw, lx, ly), yaw + 30.0 * j, "Colossus_Block%d%s" % (j, tag))
    D.structures.append(("the colossus", x, y))


def obelisks(W, D, x, y, yaw, tag, **kw):
    """Three obelisks of the old realm, one snapped (they take the ground the colossus takes elsewhere)."""
    _piece(D, "SM_Ruin_Obelisk", x, y, yaw + 10.0, "Obelisk_0" + tag, (340, 460, 300))
    hx, hy = D.at(x, y, yaw, -330.0, 150.0)
    _piece(D, "SM_Ruin_ObeliskBroken", hx, hy, yaw + 200.0, "Obelisk_1" + tag, (200, 180, 170))
    ox, oy = D.at(x, y, yaw, 420.0, 330.0)
    D.actor("SM_Ruin_Obelisk", ox, oy, yaw - 20.0, "Obelisk_2" + tag, "Props/Ruin", scale=0.8)
    for j, (lx, ly) in enumerate(((620.0, -420.0), (-650.0, -380.0))):
        _piece(D, "SM_Ruin_Block", *D.at(x, y, yaw, lx, ly), yaw + 40.0 * j, "Obelisk_Block%d%s" % (j, tag))
    D.structures.append(("obelisks", x, y))


WYRM_BOXES = [(-520.0, 0.0, (300, 330, 190)), (0.0, 0.0, (130, 130, 110)), (380.0, 0.0, (130, 130, 110)), (760.0, 0.0, (130, 130, 110))]      # the same boxes under the bones and the swords


def wyrm(W, D, x, y, yaw, tag, ribs=6, **kw):
    """The wyrm's bones: the skull, the spine and the great ribs of something that died here before the kingdoms."""
    lab = "Wyrm" + tag
    D.actor("SM_Bones_Skull", *D.at(x, y, yaw, -520.0, 0.0), yaw + 90.0, lab + "_Skull", "Props/Bones")
    for j in range(ribs):
        lx = -120.0 + j * 190.0
        k = 1.0 - 0.09 * j
        px, py = D.at(x, y, yaw, lx, 0.0)
        D.actor("SM_Bones_Spine", px, py, yaw + 90.0 + D.U(-6, 6), "%s_Spine%d" % (lab, j), "Props/Bones", scale=max(k, 0.5))
        if j % 2 == 0 or j == ribs - 1:
            for sd in (-1.0, 1.0):
                rx, ry = D.at(x, y, yaw, lx, sd * 60.0 * k)
                D.actor("SM_Bones_Rib", rx, ry, yaw + (0.0 if sd > 0 else 180.0) + D.U(-7, 7), "%s_Rib%d%s" % (lab, j, "LR"[sd > 0]), "Props/Bones", scale=1.15 * k)
    for j, (lx, ly, size) in enumerate(WYRM_BOXES):
        D.block("%s_%d" % (lab, j), *D.at(x, y, yaw, lx, ly), size, yaw)
    D.structures.append(("the wyrm's bones", x, y))


def wyrm_small(W, D, x, y, yaw, tag, **kw):
    wyrm(W, D, x, y, yaw, tag, ribs=5)


def sword_field(W, D, x, y, yaw, tag, **kw):
    """The field of swords: an old battle's leavings. Great-swords standing in the turf, spears, shields, a broken
    cart, the losers' banner poles, a cairn over the dead."""
    lab = "Swords" + tag
    r = np.random.default_rng(zlib.crc32(lab.encode()))
    D.actor("SM_Cart_Wreck", *D.at(x, y, yaw, -520.0, 0.0), yaw + 20.0, lab + "_Cart", "Props/Relics")
    D.actor("SM_Cairn", *D.at(x, y, yaw, 0.0, 0.0), 0.0, lab + "_Cairn", "Props/Rocks", scale=1.5)
    for j in (1, 2, 3):
        px, py = D.at(x, y, yaw, WYRM_BOXES[j][0], WYRM_BOXES[j][1])
        if j == 1:
            continue
        D.actor("SM_BannerPole", px, py, 0.0, "%s_Pole%d" % (lab, j), "Props/Relics")
        if j == 3:
            D.actor("SM_BannerCloth", px, py, 0.0, "%s_Banner%d" % (lab, j), "Props/Relics")
    for j, (lx, ly, size) in enumerate(WYRM_BOXES):
        D.block("%s_%d" % (lab, j), *D.at(x, y, yaw, lx, ly), size, yaw)
    for j in range(26):
        a, d = float(r.uniform(0, 2 * math.pi)), 1100.0 * math.sqrt(float(r.uniform(0.03, 1.0)))
        px, py = x + math.cos(a) * d * 1.3, y + math.sin(a) * d
        if W.water_d(px, py) < 60.0 or W.slope_at(px, py) > 0.3:
            continue
        mesh = ("SM_Relic_Sword", "SM_Relic_Sword", "SM_Relic_SwordFallen", "SM_Spear", "SM_Spear", "SM_Shield")[int(r.integers(0, 6))]
        D.actor(mesh, px, py, float(r.uniform(0, 360)), "%s_%02d" % (lab, j), "Props/Relics", scale=float(r.uniform(0.9, 1.2)))
    D.structures.append(("the field of swords", x, y))


def barrows(W, D, x, y, yaw, tag, mounds=(), **kw):
    """The barrows: grassed burial mounds (the land's own knolls), each with a stone doorway facing the camera and a
    marker stone on top."""
    for j, (dx, dy) in enumerate(mounds):
        mx, my = D.at(x, y, yaw, dx, dy)
        _piece(D, "SM_Barrow_Door", mx - 470.0, my, 0.0, "Barrow_%d%s_Door" % (j, tag), (120, 330, 230), "Props/Rocks")
        D.actor("SM_Menhir_%d" % (j % 3), mx, my, 30.0 * j, "Barrow_%d%s_Stone" % (j, tag), "Props/Rocks", scale=0.7)
    D.structures.append(("barrows", x, y))


def _turned(pts, yaw):
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    return [(px * c - py * s, px * s + py * c) for px, py in pts]


def fallen_bridge(W, D, x, y, yaw, tag, line=(), **kw):
    """The fallen bridge, where the old road crossed before the fords were found: an abutment on each bank, a pier in
    the stream, the spans gone. Nobody crosses here."""
    ln = LineString(_turned(line, yaw))
    d0 = ln.project(Point(x, y))
    pc, pn = ln.interpolate(d0), ln.interpolate(d0 + 30.0)
    tx_, ty_ = pn.x - pc.x, pn.y - pc.y
    l_ = math.hypot(tx_, ty_)
    nx_, ny_ = -ty_ / l_, tx_ / l_
    for j, sgn in enumerate((-1.0, 1.0)):
        off = 200.0
        while W.water_d(pc.x + sgn * nx_ * off, pc.y + sgn * ny_ * off) < 150.0 and off < 1600.0:
            off += 20.0
        ex, ey = pc.x + sgn * nx_ * off, pc.y + sgn * ny_ * off
        ay = math.degrees(math.atan2(-sgn * ny_, -sgn * nx_))
        D.actor("SM_Ruin_BridgeEnd", ex, ey, ay, "OldBridge_End%d%s" % (j, tag), "Props/Ruin")
        c, s = math.cos(math.radians(ay)), math.sin(math.radians(ay))
        D.block("OldBridge_End%d%s" % (j, tag), ex - 75.0 * c, ey - 75.0 * s, (240, 310, 130), ay)
    D.actor("SM_Ruin_Pier", pc.x, pc.y, math.degrees(math.atan2(ny_, nx_)), "OldBridge_Pier" + tag, "Props/Ruin", z=-16.0)
    D.structures.append(("fallen bridge", pc.x, pc.y))


def aqueduct(W, D, x, y, yaw, tag, a=(0, 0), b=(0, 0), **kw):
    """The old aqueduct: a line of tall piers striding across a valley, the water channel still on some of them."""
    (ax, ay), (bx, by) = _turned([a, b], yaw)
    ln = math.hypot(bx - ax, by - ay)
    n = max(int(round(ln / 620.0)), 2)
    piers = []
    for i in range(n + 1):
        px, py = ax + (bx - ax) * i / n, ay + (by - ay) * i / n
        piers.append((px, py, W.z(px, py)))
    top = max(p[2] for p in piers if W.water_d(p[0], p[1]) > 100.0) + 330.0
    wet = [i for i, p in enumerate(piers) if W.water_d(p[0], p[1]) < 60.0]
    missing = set()
    for i in wet:                                               # the spans over the water have fallen
        missing |= {i - 1, i}
    missing |= {n - 2} if n > 5 else set()
    name = "SM_Aqueduct_%d" % len([m for m in D.unique if m.name.startswith("SM_Aqueduct")])
    m = props.aqueduct_mesh(name, [(px - x, py - y, pz) for px, py, pz in piers], top, missing)
    D.unique.append(m)
    D.actors.append({"mesh": name, "pos": [round(x, 1), round(y, 1), 0.0], "yaw": 0.0, "label": "Aqueduct" + tag, "folder": "Props/Ruin"})
    for i, (px, py, pz) in enumerate(piers):
        if W.water_d(px, py) > 60.0:
            D.block("Aqueduct%s_%d" % (tag, i), px, py, (180, 180, 400), math.degrees(math.atan2(by - ay, bx - ax)))
    D.structures.append(("aqueduct", x, y))


def jetty(W, D, x, y, yaw, tag, **kw):
    """A fishing jetty on a lake's shore, running out over the water."""
    gx, gy = T.gradient(W.WD)
    px, py = x, y
    for _ in range(400):                                        # walk down to the water's edge
        d = W.water_d(px, py)
        if abs(d) < 25.0:
            break
        vx, vy = float(T.sample(gx, px, py)), float(T.sample(gy, px, py))
        l_ = math.hypot(vx, vy) or 1.0
        px, py = px - vx / l_ * min(abs(d), 150.0) * (1 if d > 0 else -1), py - vy / l_ * min(abs(d), 150.0) * (1 if d > 0 else -1)
    vx, vy = float(T.sample(gx, px, py)), float(T.sample(gy, px, py))
    ang = math.degrees(math.atan2(-vy, -vx))                    # out over the water
    c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    D.actor("SM_Jetty", px - c * 90.0, py - s * 90.0, ang, "Jetty" + tag, "Props/Structures", z=-16.0 - 6.0)
    D.actor("SM_Stump", px - c * 260.0 + s * 150.0, py - s * 260.0 - c * 150.0, 0.0, "Jetty_Stump" + tag, "Props/Logs")
    D.structures.append(("jetty", px, py))


def drowned_tower(W, D, x, y, yaw, tag, **kw):
    """A broken tower on an islet out in the lake: nobody lands there."""
    D.actor("SM_Ruin_Tower", x, y, 20.0 + yaw, "DrownedTower" + tag, "Props/Ruin")
    D.structures.append(("drowned tower", x, y))


def ford_stones(W, D, x, y, yaw, tag, poly=None, **kw):
    """A standing stone at each corner of a ford, on the banks: they mark the crossing from afar."""
    cs = _turned(list(poly.minimum_rotated_rectangle.exterior.coords)[:4], yaw)
    for i, (cx, cy) in enumerate(cs):
        vx, vy = cx - x, cy - y
        l_ = math.hypot(vx, vy) or 1.0
        px, py = cx + vx / l_ * 190.0, cy + vy / l_ * 190.0
        if W.water_d(px, py) > 40.0 and W.road_d(px, py) > 600.0:
            D.actor("SM_Menhir_%d" % (i % 3), px, py, D.U(0, 360), "Ford_Stone_%d%s" % (i, tag), "Props/Rocks")


def watch_post(W, D, x, y, yaw, tag, **kw):
    """A timber watch post where a lane narrows or a road forks (one in each kingdom's copy of the spot)."""
    p = D.spot(x, y, 170.0, 1000.0, tries=400, tol=0.2)
    if p is None:
        print("  no room for a watch post near (%.0f, %.0f)" % (x, y))
        return
    n = sum(1 for k, _, _ in D.structures if k == "watch post")
    yw = float(D.rng.integers(0, 4)) * 90.0
    for k, (px, py) in enumerate(W.orbit(p)):
        _piece(D, "SM_WatchPost", px, py, yw + W.ang(k), "WatchPost_%02d%s" % (n, "" if k == 0 else "_" + TAGS[k]), (230, 230, 420), "Props/Structures", z=W.z(px, py) - 14.0)
    D.structures.append(("watch post", p[0], p[1]))


def cairn(W, D, x, y, yaw, tag, **kw):
    """A waymark of piled stones (one in each kingdom's copy of the spot)."""
    p = D.spot(x, y, 90.0, 400.0, tol=0.2)
    if p is not None:
        n = sum(1 for k, _, _ in D.structures if k == "cairn")
        for k, (px, py) in enumerate(W.orbit(p)):
            D.actor("SM_Cairn", px, py, (n * 67.0) % 360.0, "Cairn_%02d%s" % (n, "" if k == 0 else "_" + TAGS[k]), "Props/Rocks")
        D.structures.append(("cairn", p[0], p[1]))


def gate(W, D, x, y, yaw, tag, **kw):
    """The old gate behind a kingdom: two pillars, the stubs of its wall, a banner."""
    for j, (lx, ly, mesh, yw) in enumerate(((0.0, -300.0, "SM_Ruin_Pillar", 4.0), (40.0, 330.0, "SM_Ruin_Pillar", -5.0), (20.0, -560.0, "SM_Ruin_Wall", 2.0), (70.0, 600.0, "SM_Ruin_Wall", 184.0))):
        px, py = D.at(x, y, yaw, lx, ly)
        _piece(D, mesh, px, py, yaw + yw, "Gate_%d%s" % (j, tag), (88, 88, 320) if "Pillar" in mesh else (60, 372, 170))
    bx, by = D.at(x, y, yaw, -30.0, 250.0)
    D.actor("SM_BannerPole", bx, by, 0, "Gate_BannerPole" + tag, "Props/Ruin")
    D.actor("SM_BannerCloth", bx, by, 0, "Gate_Banner" + tag, "Props/Ruin")


def fallen_keep(W, D, x, y, yaw, tag, **kw):
    """A fallen kingdom: what is left of its keep round the relic at its heart (the ruin a Relic Tower can be raised
    on), its walls and gate, an obelisk to its kings."""
    lab = "FallenKeep_%d" % int(round(yaw / 90.0))
    k = 0
    for j in range(10):
        a = 360.0 * j / 10.0 + 12.0
        if j in (0, 5):
            continue                                            # the gates
        ar = math.radians(a + yaw)
        px, py = x + 1150.0 * math.cos(ar), y + 1150.0 * math.sin(ar)
        mesh = ("SM_Ruin_Wall", "SM_Ruin_Wall", "SM_Ruin_Pillar", "SM_Ruin_PillarBroken")[j % 4]
        _piece(D, mesh, px, py, a + yaw, "%s_%d" % (lab, k), (60, 372, 170) if "Wall" in mesh else (88, 88, 300))
        k += 1
    ax, ay = D.at(x, y, yaw, 1150.0 * math.cos(math.radians(12.0)), 1150.0 * math.sin(math.radians(12.0)))
    D.actor("SM_Ruin_Arch", ax, ay, yaw + 12.0, lab + "_Arch", "Props/Ruin")
    for j, ly in enumerate((-190.0, 190.0)):
        D.block("%s_Arch%d" % (lab, j), *D.at(ax, ay, yaw + 12.0, 0.0, ly), (88, 88, 320), yaw)
    ox, oy = D.at(x, y, yaw, -1700.0, 600.0)
    _piece(D, "SM_Ruin_ObeliskBroken", ox, oy, yaw + 30.0, lab + "_Obelisk", (124, 124, 240))
    for j, (lx, ly) in enumerate(((700.0, 500.0), (-600.0, -700.0), (300.0, -900.0), (-900.0, 300.0), (1500.0, -300.0))):
        D.actor("SM_Ruin_Block", *D.at(x, y, yaw, lx, ly), yaw + 37.0 * j, "%s_Block%d" % (lab, j), "Props/Ruin")
    bx, by = D.at(x, y, yaw, 1500.0, 500.0)
    D.actor("SM_BannerPole", bx, by, 0, lab + "_BannerPole", "Props/Ruin")
    D.structures.append(("fallen keep", x, y))
