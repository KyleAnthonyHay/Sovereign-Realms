"""The plans of the two battle maps, as calls on a World (worldgen.py). gen_battlefield.py --map two | four.

  two    THE RIVERLANDS     +/-240 m. Two kingdoms on high tables in opposite corners, the river in its valley between
                            them (two fords, the shrine island's two bridges), a brook and a water meadow before each,
                            the Heights beside each kingdom and the Highland with its tarn and fall beyond the brook.
  four   THE FOUR MARCHES   +/-360 m. Four kingdoms on tables in the corners round the High Moor (the middle, the great
                            circle); four rivers fall from the moor and run out along the axes to the lakes at the
                            edges, each parting two neighbours and crossed at an inner ford and at an island midway (the
                            neighbours' contested ground: veins, a relic, a tower on each bank). Played one against
                            one for now: the player in the near-left corner, the rival in the far-right; the other two
                            kingdoms are fallen (their keeps are relics to rebuild).

Coordinates are Unreal's: +X up the screen, +Y to the right; the player's kingdom is bottom-left (-X, -Y).
Everything is given for the player's kingdom and turned for the others (World.sym).
"""
import math
import os

import numpy as np
from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import substring, unary_union

import terrain as T
from terrain import N, X, Y
from worldgen import World, blob, catmull, K_WALK
import dressing as D

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SURF = -16.0                    # the rivers' surface: the datum the land is measured from


def polys(geom, min_area=0.0):
    if geom is None or geom.is_empty:
        return []
    parts = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    parts = [p for p in parts if p.geom_type == "Polygon" and p.area > min_area]
    return sorted(parts, key=lambda p: -p.area)


def wobbly(line, half, r, lo=0.85, hi=1.2, jitter=45.0, skip=None):
    """A stream's uneven banks: discs of varying size strung along its line."""
    out, d = [], 60.0
    while d < line.length:
        p = line.interpolate(d)
        if skip is None or not skip(d):
            out.append(Point(p.x + float(r.normal(0, jitter)), p.y + float(r.normal(0, jitter))).buffer(half * float(r.uniform(lo, hi)), 2))
        d += float(r.uniform(190, 330))
    return out


def ford_at(water, line, at, half_len, reach):
    """The stretch of `line`'s water `half_len` either side of the crossing at `at`."""
    dd = line.project(Point(at))
    a, b = line.interpolate(dd - 40.0), line.interpolate(dd + 40.0)
    t = np.array([b.x - a.x, b.y - a.y])
    t /= np.linalg.norm(t)
    c = np.array([line.interpolate(dd).x, line.interpolate(dd).y])
    strip = LineString([tuple(c - t * half_len), tuple(c + t * half_len)]).buffer(reach, cap_style=2)
    return polys(strip.intersection(water))[0]


def deck_for(water, road_pts, near, half_w, reach, over=110.0):
    """A bridge deck where a road crosses water near `near`: from bank to bank and a little onto each."""
    road = LineString(road_pts)
    cross = road.intersection(water)
    parts = [g for g in (cross.geoms if hasattr(cross, "geoms") else [cross]) if g.geom_type == "LineString" and g.length > 50.0 and g.centroid.distance(Point(near)) < reach]
    g = max(parts, key=lambda q: q.length)
    a, b = np.array(g.coords[0]), np.array(g.coords[-1])
    dv = (b - a) / np.linalg.norm(b - a)
    return LineString([tuple(a - dv * over), tuple(b + dv * over)]).buffer(half_w, cap_style=2)


def load_peaks(W, spec):
    for gi, x, y, size, height, yaw in spec:
        path = os.path.join(ROOT, "SourceArt", "World", "Mountains", "peak_%d.npy" % gi)
        if os.path.exists(path):
            W.peaks.append((np.load(path).astype(np.float32), x, y, size, height, yaw))
        else:
            print("no %s: run Tools/blender/build_mountains.py (the skyline goes without this peak)" % os.path.basename(path))


def kingdom(W, anchor, team, k, court=True):
    """A kingdom's starting buildings, turned for copy k: castle at the anchor, farm and mine beside it. A building's
    front (gate, adit, yard) faces -X at yaw 0, toward the game camera."""
    ax, ay = anchor
    who = "Player" if team == 0 else "Enemy"
    sg = 1.0 if k == 0 else -1.0
    W.buildings += [("castle", ax, ay, 0.0, team, "Castle_" + who),
                    ("farm", ax + sg * 250.0, ay + sg * 2500.0, 0.0, team, "Farm_" + who),
                    ("mine", ax + sg * 450.0, ay - sg * 2500.0, 0.0, team, "Mine_" + who)]
    W.starts["player" if team == 0 else "enemy"] = (ax + sg * 1500.0, ay + sg * 1400.0)


# ============================================================================================ THE RIVERLANDS
def plan_two():
    B = 24000.0
    DOWNS, TABLE_Z = 750.0, 1750.0                           # the rolling country and the kingdoms' tables, cm over the river
    W = World("two", "The Riverlands", B, 2, (-B - 6500.0, B + 13500.0, -B - 9500.0, B + 9500.0), 20262,
              note="Two kingdoms across the river")
    AXIS, PERP = (0.8160, -0.5780), (0.5780, 0.8160)        # upstream; toward the enemy's bank
    W.flow = (-AXIS[0], -AXIS[1])

    def sn(s, n):
        return (s * AXIS[0] + n * PERP[0], s * AXIS[1] + n * PERP[1])

    def mir(p):
        return (-p[0], -p[1])

    def rot(g):
        return affinity.rotate(g, 180.0, origin=(0, 0))

    r = np.random.default_rng(77)
    world = box(*[W.box[i] for i in (0, 2, 1, 3)])
    P = (-11400.0, -10500.0)                                 # the player's castle; the enemy's is its twin
    W.anchors = [P, mir(P)]

    # ---------------------------------------------------------------- water
    # The river runs between the kingdoms from the lake beyond the far-left corner to the lake beyond the near-right
    # one, in river coordinates: s = distance upstream from the centre, n = offset toward the enemy's bank. It parts
    # round the shrine island at the centre and is deep everywhere but at the two fords.
    ISLE_S = 3500.0
    up_keys = [(ISLE_S, 0), (5400, -600), (7000, 170), (8600, 1030), (9950, 740), (11300, 70), (12900, -740), (14600, -1310), (16300, -800),
               (18000, 170), (19800, 570), (21600, 110), (23500, -570), (25600, -800), (27800, -340), (30300, 230), (33700, 0), (39500, 0)]
    ch_keys = [(ISLE_S, 0), (2450, -1250), (900, -2000), (-900, -2000), (-2450, -1250), (-ISLE_S, 0)]
    RIVER_UP = catmull([sn(*k) for k in up_keys], 8)
    CHANNEL = catmull([sn(*k) for k in ch_keys], 8)
    FORD_A = sn(11300, 70)
    FORD_HALF, FORD_SPREAD = 1000.0, 820.0
    up, ch = LineString(RIVER_UP), LineString(CHANNEL)
    d_ford, d_arm = up.project(Point(FORD_A)), up.project(Point(sn(23000, -400)))
    parts = [up.buffer(320.0, 3), ch.buffer(245.0, 3), Point(sn(ISLE_S, 0)).buffer(430.0, 3)]
    d = 60.0
    while d < up.length:                                     # uneven banks; the river opens out into the lake's arm
        p = up.interpolate(d)
        if abs(d - d_ford) > FORD_HALF + 500.0:
            k = float(r.uniform(0.82, 1.22)) + (min((d - d_arm) / 5600.0, 1.0) * 2.5 if d > d_arm else 0.0)
            parts.append(Point(p.x + float(r.normal(0, 45)), p.y + float(r.normal(0, 45))).buffer(320.0 * k, 2))
        d += float(r.uniform(190, 330))
    parts += wobbly(ch, 245.0, r, 0.9, 1.12)
    parts.append(substring(up, d_ford - FORD_HALF - 320.0, d_ford + FORD_HALF + 320.0).buffer(FORD_SPREAD, 3))
    lake = unary_union([blob(*sn(34200, 100), 3900, 3600, 1), blob(*sn(31000, -300), 2300, 2000, 2), blob(*sn(37800, -900), 3000, 2700, 3)])
    islets = [blob(*sn(s_, n_), rx, ry, 10 + i, 0.2) for i, (s_, n_, rx, ry) in enumerate(((25600.0, -150.0, 460.0, 270.0), (27400.0, 450.0, 330.0, 400.0), (29000.0, -480.0, 380.0, 320.0)))]
    main = unary_union(parts + [lake]).difference(unary_union(islets))
    # The brook: each kingdom's second stream. It falls from the Highland's tarn into a pool and runs down to the river
    # just above the island: deep, a wall like the river, crossed at the lane bridge and the upper ford. Between it
    # and the river lies the water meadow, where a foe who has forced ford A lands with a second crossing still to make.
    POOL = (8900.0, -17900.0)
    brook_keys = [POOL, (8100.0, -16400.0), (7300.0, -14900.0), (6200.0, -14100.0), (5000.0, -12500.0), (5300.0, -10600.0), (4200.0, -9000.0),
                  (2900.0, -8100.0), (2400.0, -6400.0), (3300.0, -5000.0), sn(5400, -600)]
    BROOK = catmull(brook_keys, 8)
    st = LineString(BROOK)
    GC, GZ = (13400.0, -18800.0), 1650.0                     # the Highland's bench (below): its fall drops into the brook's pool
    bench = blob(GC[0], GC[1], 3900.0, 3300.0, 44, 0.05)
    brook = unary_union([st.buffer(170.0, 3), Point(POOL).buffer(560.0, 8)] + wobbly(st, 170.0, r, 0.92, 1.2, 22.0)).difference(bench.buffer(560.0))    # the pool lies at the foot of the rock face, not under it
    STREAM_FORD, LANE_BRIDGE = (6800.0, -14520.0), (3500.0, -8550.0)
    marsh_spec = [(7300.0, -1000.0, 320.0), (6600.0, -1650.0, 280.0), (7500.0, -2150.0, 250.0), (9700.0, -1450.0, 260.0), (6100.0, -1150.0, 250.0)]
    deep = unary_union([main, brook])
    marsh = unary_union([blob(*sn(s_, n_), rad, rad * 0.8, 20 + i, 0.2) for i, (s_, n_, rad) in enumerate(marsh_spec)]).difference(deep.buffer(140.0))
    marsh = polys(marsh.buffer(-30, 2).buffer(30, 2), 30000.0)
    half = unary_union([deep] + marsh)
    water = unary_union([half, rot(half)]).intersection(world).buffer(-40, 2).buffer(40, 2)
    LAKE = MultiPolygon([p.simplify(8.0) for p in polys(water, 30000.0)])
    RIVER = unary_union([main, rot(main)]).intersection(world)
    ISLAND = max([Polygon(i) for part in LAKE.geoms for i in part.interiors], key=lambda h_: h_.area)
    W.island = ISLAND

    # roads' key points (the bridges are cut where they cross water)
    king_p = [(P[0] - 950.0, P[1]), (P[0] - 700.0, P[1] + 1500.0), (P[0] + 900.0, P[1] + 2300.0), (-8300.0, -7000.0), (-5600.0, -5000.0), (-3200.0, -2900.0), (-1300.0, -1250.0)]
    KING = king_p + [(0.0, 0.0)] + [mir(p) for p in king_p[::-1]]
    TL = [(-8300.0, -7000.0), (-5600.0, -9400.0), (-2000.0, -9900.0), (1100.0, -9400.0), LANE_BRIDGE, (5700.0, -8000.0), (7700.0, -7400.0), FORD_A,
          (10900.0, -4100.0), (11700.0, -700.0), (11300.0, 2700.0), (10000.0, 5700.0), (8300.0, 7000.0)]
    ford = ford_at(LAKE, up, FORD_A, FORD_HALF, 1900.0)
    sford = ford_at(LAKE, st, STREAM_FORD, 520.0, 600.0)
    king_deck = deck_for(LAKE, catmull(KING), sn(-300, -2000), 350.0, 1500.0)
    lane_deck = deck_for(LAKE, catmull(TL), LANE_BRIDGE, 320.0, 1200.0)

    # ---------------------------------------------------------------- the country
    # The river lies in a broad valley: its floor half a metre over the water, the land rising from it to rolling
    # downs five to six metres up, where the kingdoms' tables and the hills stand.
    dr = np.maximum(T.sdist(LAKE), 0.0)
    roll = T.smoothstep((dr - 2500.0) / 5000.0)
    W.H = (45.0 + (DOWNS - 45.0) * T.ramp((dr - 1300.0) / 7600.0) + roll * (170.0 * T.fbm(9000.0, 301, 3, sym=2) + 50.0 * T.noise(3200.0, 302, 2))).astype(np.float32)
    W.pad(0.0, 0.0, 1700.0, 52.0, 900.0, sym=False)          # the island: level round the shrine
    W.valley(BROOK, 330.0, 60.0, 0.3)                        # the brook's own small valley
    # the Black Mere: a deep hollow in the downs with dark water at its bottom, eight metres under the river
    MERE = (-14600.0, -600.0)
    mere = blob(MERE[0], MERE[1], 820.0, 1000.0, 47, 0.12)
    W.basin(mere.buffer(250.0), -640.0, 0.85)

    # ---- the kingdoms' tables: a broad level height, eleven metres over the downs, with a long hillside down toward
    # the river and mountainsides behind
    TC = (P[0] - 1500.0, P[1] - 1300.0)
    table = blob(TC[0], TC[1], 5600.0, 5000.0, 41, 0.07)
    W.tables = [(0, P, t) if i == 0 else (1, mir(P), t) for i, t in enumerate(W.plate(table, TABLE_Z, gentle=[(42.0, 66.0)], c=TC))]
    for k, (team, a, _) in enumerate(W.tables):
        kingdom(W, a, team, k)
    # ---- the Heights: the kingdom's own high ground beside it (the safe vein on the bench, the relic on the crown)
    HB, HC = (-19000.0, -2600.0), (-20300.0, -2300.0)
    W.plate(blob(HB[0], HB[1], 2500.0, 3000.0, 42, 0.08), 2300.0, gentle=[(-52.0, 30.0)], c=HB)
    W.plate(blob(HC[0], HC[1], 800.0, 800.0, 43, 0.05), 2600.0, gentle=[(-80.0, 24.0)], c=HC)
    W.ruin(HC[0], HC[1], relic=True, name="the Heights")
    W.vein(-18100.0, -1300.0, pad=False)
    # ---- the Overlook: a whaleback between the centre lane and the stone lane
    W.mount([(-9300.0, -300.0), (-8900.0, 1700.0), (-9000.0, 3900.0)], 2200.0, crest=220.0, k=0.95, shoulder=2800.0, rough=0.14)
    # ---- the Highland: the upland beyond the brook, as far from one castle as from the other. Two veins on its
    # bench, the tarn and its fall, the old stone circle on the crown.
    fall_b = math.degrees(math.atan2(POOL[1] - GC[1], POOL[0] - GC[0]))
    W.plate(bench, GZ, gentle=[(196.0, 13.0), (124.0, 15.0)], cliffs=[(fall_b, 9.0, 3.2)], c=GC)
    KC = (15700.0, -20100.0)
    W.plate(blob(KC[0], KC[1], 820.0, 820.0, 45, 0.05), GZ + 300.0, gentle=[(146.0, 22.0)], c=KC)
    W.ruin(KC[0], KC[1], relic=True, name="the Highland")
    W.vein(12500.0, -20500.0, pad=False)
    W.vein(14300.0, -16800.0, pad=False)
    rim = bench.exterior.interpolate(bench.exterior.project(Point(POOL)))
    o = np.array([POOL[0] - rim.x, POOL[1] - rim.y])
    o /= np.linalg.norm(o)
    tc = np.array([rim.x, rim.y]) - o * 640.0
    tarn = unary_union([blob(tc[0], tc[1], 440.0, 380.0, 46, 0.15), LineString([tuple(tc), (rim.x + o[0] * 40.0, rim.y + o[1] * 40.0)]).buffer(120.0, 3)]).intersection(bench.buffer(30.0))
    # ---- mountains inside the field, on its rim and corners (the camera's side is squashed: World.near_squash)
    for pts, h, crest in (((23300.0, -23300.0), 5000.0, 1100.0),                     # the far-left corner, behind the Highland
                          ([(-23300.0, 6200.0), (-23000.0, 10500.0)], 3400.0, 500.0),    # near edge, right of the Heights
                          ([(-23400.0, -18000.0), (-22400.0, -11500.0)], 3000.0, 500.0), # near edge, behind the castle
                          ([(-1500.0, -23600.0), (2800.0, -23800.0)], 2700.0, 400.0),    # left edge, off the wooded lane
                          ([(-12500.0, -23400.0), (-7000.0, -23200.0)], 2500.0, 400.0),  # left edge, behind the home mine
                          ((-22700.0, -22700.0), 2800.0, 900.0),                         # the near-left corner
                          ([(23300.0, -17500.0), (23600.0, -13500.0)], 3000.0, 400.0)):  # the far edge, right of the Highland
        W.mount(pts, h, crest=crest)
    # barrows on the downs by the stone lane: three grassed mounds (their doors are dressing)
    for bx, by in ((-14800.0, 6900.0), (-16300.0, 8300.0), (-14300.0, 8900.0)):
        W.knoll(bx, by, 700.0, 210.0)

    # ---------------------------------------------------------------- water, crossings
    W.water(LAKE, SURF, 154.0, "river")
    W.shore(unary_union([lake] + [g for g in parts if g.centroid.distance(Point(sn(23000, -400))) > 0 and up.project(g.centroid) > d_arm]), 30.0)
    for t_ in (tarn, rot(tarn)):
        W.water(t_, GZ - 16.0, 90.0, "tarn", bank=120.0, current=False)
    for m_ in (mere, rot(mere)):
        W.water(m_, -560.0, 150.0, "mere", bank=160.0, current=False)
    for f_ in (ford, sford):
        W.ford(f_); W.ford(rot(f_))
    for m_ in marsh:
        W.ford(m_); W.ford(rot(m_))
    for dk, nm in ((king_deck, "King"), (lane_deck, "Lane")):
        W.deck(dk, "SM_T_Bridge_%s_0" % nm, width=700.0 if nm == "King" else 640.0)
        W.deck(rot(dk), "SM_T_Bridge_%s_1" % nm, width=700.0 if nm == "King" else 640.0)
    W.decks.append(dict(geom=Polygon([(620.0 * math.cos(math.radians(11.25 + 22.5 * k)), 620.0 * math.sin(math.radians(11.25 + 22.5 * k))) for k in range(16)]),
                        z=52.0 + 24.0, name="SM_T_Shrine", width=0.0, kind="dais"))
    for sg in (1.0, -1.0):
        W.falls.append(dict(lip=(sg * rim.x, sg * rim.y), out=(sg * float(o[0]), sg * float(o[1])), top=GZ - 16.0, bottom=SURF, width=240.0))
    W.current_lines = [RIVER_UP[:int(len(RIVER_UP) * 0.72)], [mir(p) for p in RIVER_UP[:int(len(RIVER_UP) * 0.72)]], CHANNEL, [mir(p) for p in CHANNEL], BROOK, [mir(p) for p in BROOK]]

    # ---------------------------------------------------------------- roads
    W.road(KING, half=560.0, kind="paved", sym=False, name="king's road")
    W.road(TL, name="top-left lane")
    W.road([(-2000.0, -9900.0), (1400.0, -12800.0), (3900.0, -16300.0), (5300.0, -19000.0), (7900.0, -19900.0), (10900.0, -19500.0)], name="highland road")   # home -> the Highland's home side
    W.road([(3900.0, -16300.0), (5600.0, -15400.0), STREAM_FORD, (7900.0, -13100.0), (7500.0, -11800.0), (7100.0, -9500.0), (7700.0, -7400.0)], name="meadow road")   # over the upper ford to ford A
    W.road([(7900.0, -13100.0), (9300.0, -13700.0), (10800.0, -15300.0), (12100.0, -16900.0)], name="meadow spur")       # water meadow -> the Highland's field side
    W.road([(P[0] - 700.0, P[1] + 1500.0), (-14600.0, -7300.0), (-16300.0, -5700.0), (-17400.0, -4300.0), (-18800.0, -4500.0)], half=420.0, name="heights road")

    # ---------------------------------------------------------------- veins, ruins
    W.vein(P[0] + 450.0, P[1] - 2500.0, pad=False)           # home, under the starting mine
    W.vein(*sn(1800, 0))                                      # the shrine island's two
    W.vein(9400.0, -10900.0)                                  # the water meadow
    for x, y in ((-4000.0, -900.0), (6000.0, -9400.0), (-13300.0, 3300.0)):
        W.ruin(x, y)                                          # old towers: the plain, the water meadow, the stone lane
    # greens: level ground to build on out in the country (by the lane bridge, on the plain, on the home bank of ford B)
    for x, y in ((1700.0, -11000.0), (-7000.0, -3600.0), (-10400.0, 5200.0)):
        W.green(x, y)

    # ---------------------------------------------------------------- woods, landmarks, dressing
    for x, y, rx, ry, n in ((-1500.0, -13500.0, 3200.0, 2300.0, 44), (1200.0, -18800.0, 2400.0, 2000.0, 30), (8900.0, -9600.0, 1500.0, 2300.0, 22),
                            (-16500.0, 12500.0, 2600.0, 2300.0, 30), (-6500.0, -17700.0, 2400.0, 1700.0, 22), (-19600.0, -8800.0, 1300.0, 1900.0, 14),
                            (12500.0, -5500.0, 1700.0, 1200.0, 16), (-3300.0, 5400.0, 1500.0, 1200.0, 12), (19500.0, -17500.0, 1500.0, 2500.0, 18)):
        W.forest(x, y, rx, ry, n)
    W.landmark = dict(name="shrine", pos=[0.0, 0.0], radius=780.0)
    road_ang = math.degrees(math.atan2(2500.0, 2600.0))
    W.site(D.shrine, 0.0, 0.0, road_ang, sym=False, clear=1000.0)
    W.site(D.bridge_dressing, 0.0, 0.0, 0.0, sym=False, clear=0.0)
    W.site(D.ruin, -3800.0, -6100.0, 35.0, n=0)
    W.site(D.ruin, 700.0, -11400.0, -10.0, n=1)
    W.site(D.ruin, -13100.0, 4700.0, 75.0, n=2)
    W.site(D.stone_circle, -19300.0, 6400.0, 0.0, n=0)
    W.site(None, -5600.0, -2500.0, 20.0, variants=[D.colossus, D.obelisks])              # beside the king's road: a king of the old realm / his obelisks
    W.site(None, 9900.0, -12100.0, 0.0, variants=[D.wyrm, D.sword_field], clear=1600.0)                # in the water meadows: the wyrm's bones / the field of swords
    W.site(D.barrows, -15100.0, 8000.0, 0.0, mounds=[(300.0, -1100.0), (-1200.0, 300.0), (800.0, 900.0)], clear=1900.0)
    W.site(D.fallen_bridge, *sn(15600.0, -1085.0), 0.0, line=RIVER_UP)
    W.site(D.aqueduct, 2600.0, -6300.0, 0.0, a=(900.0, -7300.0), b=(4300.0, -5300.0), clear=2100.0)  # the old aqueduct over the brook's mouth
    W.site(D.jetty, *sn(26500.0, -1500.0), 0.0)
    W.site(D.drowned_tower, *sn(27400.0, 450.0), 0.0)
    W.site(D.ford_stones, FORD_A[0], FORD_A[1], 0.0, poly=ford)
    for want in (tuple(np.array(FORD_A) - np.array(PERP) * (FORD_SPREAD + 520.0) + np.array(AXIS) * (FORD_HALF + 330.0)), (LANE_BRIDGE[0] - 1000.0, LANE_BRIDGE[1] - 500.0),
                 (-6400.0, -6500.0), (STREAM_FORD[0] - 900.0, STREAM_FORD[1] - 900.0), (6000.0, -20600.0), (9500.0, -12600.0)):
        W.site(D.watch_post, want[0], want[1], 0.0, sym=False, clear=0.0)
    for want in ((7500.0, -11700.0), (1400.0, -12800.0), (7900.0, -13300.0), (-3200.0, -9900.0), (-15600.0, -6900.0), (-12700.0, 1100.0), (3900.0, -16500.0)):
        W.site(D.cairn, want[0], want[1], 0.0, sym=False, clear=0.0)
    W.site(D.gate, P[0] - 3200.0, P[1] + 600.0, 0.0)

    # ---------------------------------------------------------------- the air
    for sg in (1.0, -1.0):
        lk, mw = sn(33500.0, 0.0), sn(8000.0, -1600.0)
        W.mist += [[sg * lk[0], sg * lk[1], SURF, 5000.0, 170.0], [sg * mw[0], sg * mw[1], 30.0, 2300.0, 130.0],
                   [sg * (POOL[0] - 200.0), sg * POOL[1], 0.0, 1000.0, 120.0], [sg * (POOL[0] + 150.0), sg * POOL[1], 0.0, 560.0, 300.0],
                   [sg * 9900.0, sg * -12100.0, 330.0, 1500.0, 110.0]]
    W.mist += [[0.0, 0.0, 40.0, 2600.0, 150.0]]

    # ---------------------------------------------------------------- what must hold
    fords_ = [ford, rot(ford)]
    decks_ = [king_deck, rot(king_deck)]
    W.checks.append(("the river (fords and island bridges closed)", fords_ + decks_, "player", "enemy"))
    W.crossings = [("ford A (top-left)", [fords_[0]]), ("ford B (bottom-right)", [fords_[1]]), ("island bridges", decks_)]
    W.river_all = fords_ + decks_
    mv = (9400.0, -10900.0)
    W.checks.append(("the brook (lane bridge, upper ford and the way over the Highland closed; river crossings closed)", fords_ + decks_ + [lane_deck, sford, Point(GC).buffer(5600.0)], "player", (mv[0] - 700.0, mv[1])))
    W.reach += [("the island", 300.0, 900.0), ("the Highland's bench", 13400.0, -18500.0), ("the Heights' bench", -18600.0, -3000.0)]
    for i, (name, x, y) in enumerate((("THE HEIGHTS", HB[0] + 700.0, HB[1] - 900.0), ("THE OVERLOOK", -8900.0, 1700.0), ("THE HIGHLAND", GC[0], GC[1] + 900.0))):
        W.label(x, y, name, sym=True)
    W.label(0.0, 0.0, "SHRINE ISLE")
    W.label(FORD_A[0] + 1300.0, FORD_A[1] - 600.0, "FORD A"); W.label(-FORD_A[0] - 1300.0, -FORD_A[1] + 600.0, "FORD B")
    W.label(POOL[0] - 900.0, POOL[1], "falls", sym=True, small=True)
    W.label(LANE_BRIDGE[0] - 600.0, LANE_BRIDGE[1], "lane bridge", sym=True, small=True)
    W.label(STREAM_FORD[0] - 700.0, STREAM_FORD[1], "upper ford", sym=True, small=True)
    W.zone_water = RIVER
    W.scatter_hills(9, 611, clear=1250.0, region=lambda x, y: x * PERP[0] + y * PERP[1] < -900.0, extra_keep=[Point(MERE).buffer(3400.0), Point(mir(MERE)).buffer(3400.0), Point(8600.0, -10600.0).buffer(4200.0), Point(-8600.0, 10600.0).buffer(4200.0)])     # (and none in the water meadows: they are narrow enough)
    W.label(MERE[0], MERE[1] + 1500.0, "the Black Mere", sym=True, small=True)
    for sg in (1.0, -1.0):
        W.mist.append([sg * MERE[0], sg * MERE[1], -540.0, 1500.0, 260.0])
    load_peaks(W, [(0, B + 5600.0, -9700.0, 12500.0, 9200.0, 20.0), (2, B + 6700.0, 2900.0, 14500.0, 11500.0, 100.0), (4, B + 5600.0, 14900.0, 12000.0, 8800.0, 250.0),
                   (5, 8600.0, -(B + 5000.0), 10000.0, 6200.0, 60.0), (1, 5700.0, B + 5000.0, 10000.0, 6000.0, 140.0),
                   (1, 18900.0, -(B + 6000.0), 10500.0, 7600.0, 300.0), (5, 17700.0, B + 6200.0, 10500.0, 7400.0, 200.0)])
    return W


# ============================================================================================ THE FOUR MARCHES
def plan_four():
    B = 36000.0
    DOWNS, TABLE_Z, MOOR_Z = 750.0, 1750.0, 2300.0
    W = World("four", "The Four Marches", B, 4, (-B - 6500.0, B + 12800.0, -B - 9000.0, B + 9000.0), 40441,
              note="Four kingdoms round the High Moor")
    W.flow = (-0.7071, -0.7071)
    world = box(*[W.box[i] for i in (0, 2, 1, 3)])
    r = np.random.default_rng(99)

    def q4(g):
        return [W.turn_geom(g, k) for k in range(4)]

    P = (-23800.0, -23800.0)                                 # the player's castle (near-left); the others are its quarter turns
    W.anchors = W.orbit(P)

    # ---------------------------------------------------------------- water
    # Four rivers rise under the High Moor's falls and run out along the axes to the lakes at the field's edges. Given
    # here: the one down the -X axis (toward the camera), between the near-left and near-right kingdoms.
    ISLE = (-21500.0, 0.0)
    POOL = (-7250.0, 0.0)
    head = catmull([POOL, (-9200.0, 500.0), (-11200.0, -300.0), (-13200.0, -650.0), (-15000.0, 100.0), (-16600.0, 500.0), (-17700.0, 0.0)], 8)
    cha = catmull([(-17700.0, 0.0), (-18700.0, -1500.0), (-20200.0, -2500.0), (-22800.0, -2500.0), (-24300.0, -1500.0), (-25300.0, 0.0)], 8)
    chb = [(x, -y) for x, y in cha]
    tail = catmull([(-25300.0, 0.0), (-27000.0, -450.0), (-28800.0, 300.0), (-30500.0, 0.0), (-33500.0, 0.0), (-39500.0, 0.0)], 8)
    FORD = (-12200.0, -520.0)
    hl, tl = LineString(head), LineString(tail)
    d_ford = hl.project(Point(FORD))
    parts = [hl.buffer(300.0, 3), tl.buffer(330.0, 3), LineString(cha).buffer(245.0, 3), LineString(chb).buffer(245.0, 3),
             Point(-17700.0, 0.0).buffer(420.0, 3), Point(-25300.0, 0.0).buffer(420.0, 3), Point(POOL).buffer(620.0, 8)]
    parts += wobbly(hl, 300.0, r, 0.85, 1.2, 40.0, skip=lambda d_: abs(d_ - d_ford) < 1400.0)
    parts += wobbly(LineString(cha), 245.0, r, 0.9, 1.12) + wobbly(LineString(chb), 245.0, r, 0.9, 1.12)
    d = 60.0
    while d < tl.length:
        p = tl.interpolate(d)
        k = float(r.uniform(0.85, 1.2)) + min(d / 6500.0, 1.0) * 2.2
        parts.append(Point(p.x + float(r.normal(0, 45)), p.y + float(r.normal(0, 45))).buffer(330.0 * k, 2))
        d += float(r.uniform(190, 330))
    parts.append(substring(hl, d_ford - 1300.0, d_ford + 1300.0).buffer(760.0, 3))
    lake = unary_union([blob(-37800.0, 300.0, 4300.0, 5200.0, 5, 0.1), blob(-34600.0, -900.0, 2300.0, 2600.0, 6, 0.12), blob(-40500.0, 2500.0, 3000.0, 3600.0, 7, 0.1)])
    islet = blob(-36200.0, 1500.0, 420.0, 520.0, 8, 0.2)
    one = unary_union(parts + [lake]).difference(islet)
    water = unary_union(q4(one)).intersection(world).buffer(-40, 2).buffer(40, 2)
    LAKE = MultiPolygon([p.simplify(8.0) for p in polys(water, 30000.0)])
    islands = sorted([Polygon(i) for part in LAKE.geoms for i in part.interiors], key=lambda h_: -h_.area)[:4]
    ISLAND = min(islands, key=lambda h_: h_.centroid.distance(Point(ISLE)))
    W.island = ISLAND

    # roads' key points
    HUB, FOOT = (-17200.0, -17200.0), (-12800.0, -12800.0)
    HIGH = [(P[0] - 950.0, P[1]), (P[0] - 600.0, P[1] + 1500.0), (P[0] + 1300.0, P[1] + 1900.0), (-21000.0, -21000.0), HUB, FOOT, (-9000.0, -9000.0), (-4600.0, -4600.0), (-1500.0, -1500.0)]
    ISLE_A = [HUB, (-19400.0, -12500.0), (-21000.0, -7500.0), (-21500.0, -4300.0), ISLE]          # to the island on the -X river
    ISLE_B = [HUB, (-12500.0, -19400.0), (-7500.0, -21000.0), (-4300.0, -21500.0), (0.0, -21500.0)]   # and to the one on the -Y river (its mirror)
    FORD_A = [FOOT, (-12700.0, -8200.0), (-12400.0, -3600.0), FORD]
    FORD_B = [FOOT, (-8200.0, -12700.0), (-3600.0, -12400.0), W.turn(FORD, 1), ]                 # the -Y river's ford is the -X river's, turned
    ford = ford_at(LAKE, hl, FORD, 1000.0, 1700.0)
    deck_a = deck_for(LAKE, catmull(ISLE_A), (-21500.0, -2500.0), 350.0, 1500.0)
    deck_b = deck_for(LAKE, catmull([(x, -y) for x, y in ISLE_A]), (-21500.0, 2500.0), 350.0, 1500.0)

    # ---------------------------------------------------------------- the country
    dr = np.maximum(T.sdist(LAKE), 0.0)
    roll = T.smoothstep((dr - 2500.0) / 5000.0)
    W.H = (45.0 + (DOWNS - 45.0) * T.ramp((dr - 1300.0) / 7600.0) + roll * (180.0 * T.fbm(9500.0, 401, 3, sym=4) + 50.0 * T.noise(3200.0, 402, 4))).astype(np.float32)
    # the Black Meres: a deep hollow in each march with dark water at its bottom
    MERE = (-27600.0, -3900.0)
    mere = blob(MERE[0], MERE[1], 900.0, 1050.0, 57, 0.12)
    W.basin(mere.buffer(250.0), -640.0, 0.85)
    W.pad(ISLE[0], ISLE[1], 2100.0, 55.0, 900.0)

    # ---- the High Moor: the middle of the map, twenty metres up. A hillside toward each kingdom, a rock face over
    # each river's pool (the falls), the great circle at its heart.
    moor = Point(0.0, 0.0).buffer(5900.0, 24)
    W.plate(moor, MOOR_Z, gentle=[(45.0 + 90.0 * k, 21.0) for k in range(4)], cliffs=[(90.0 * k, 9.0, 3.4) for k in range(4)], c=(0.0, 0.0), sym=False)
    tarn = unary_union([blob(-4700.0, 0.0, 520.0, 620.0, 9, 0.12), LineString([(-4700.0, 0.0), (-5940.0, 0.0)]).buffer(125.0, 3)]).intersection(moor.buffer(25.0))
    # ---- the kingdoms' tables
    tc = (P[0] - 1300.0, P[1] - 1300.0)
    table = blob(tc[0], tc[1], 5500.0, 5500.0, 51, 0.06)
    tabs = W.plate(table, TABLE_Z, gentle=[(45.0, 68.0)], c=tc)
    W.tables = [((0 if k == 0 else (1 if k == 2 else None)), W.turn(P, k), t) for k, t in enumerate(tabs)]
    for k, (team, a, _) in enumerate(W.tables):
        if team is not None:
            kingdom(W, a, team, k)
    # ---- each march's own high ground: the Shoulder (a bench by the kingdom with the safe vein) and the Watch (a hill
    # looking over the river toward the neighbour, an old relic on its crown)
    SH = (-17500.0, -29300.0)
    W.plate(blob(SH[0], SH[1], 2300.0, 2000.0, 52, 0.07), 2250.0, gentle=[(128.0, 30.0)], c=SH)
    W.vein(SH[0] + 300.0, SH[1] - 200.0, pad=False)
    WT = (-29300.0, -15800.0)
    W.plate(blob(WT[0], WT[1], 1700.0, 1700.0, 53, 0.06), 2150.0, gentle=[(-58.0, 28.0)], c=WT)
    WC = (WT[0] - 550.0, WT[1] + 650.0)
    W.plate(blob(WC[0], WC[1], 720.0, 720.0, 54, 0.05), 2450.0, gentle=[(-50.0, 30.0)], c=WC)
    W.ruin(WC[0], WC[1], relic=True, name="the Watch")
    # ---- mountains: behind each kingdom, along the edges to the lakes, and the Teeth: a broken ridge in each march
    for pts, h, crest in (((-33500.0, -33500.0), 5200.0, 1800.0),
                          ([(-34800.0, -24500.0), (-34500.0, -19500.0)], 3400.0, 500.0), ([(-24500.0, -34800.0), (-19500.0, -34500.0)], 3400.0, 500.0),
                          ([(-35000.0, -12500.0), (-34500.0, -8500.0)], 2800.0, 400.0), ([(-12500.0, -35000.0), (-8500.0, -34500.0)], 2800.0, 400.0)):
        W.mount(pts, h, crest=crest)
    W.mount([(-27600.0, -9600.0), (-26800.0, -8200.0), (-25200.0, -7300.0)], 2600.0, crest=200.0, k=1.0, shoulder=3200.0, rough=0.22, warp=1.4)       # the Teeth, over the isle road
    W.mount([(-9600.0, -27600.0), (-8200.0, -26800.0), (-7300.0, -25200.0)], 2600.0, crest=200.0, k=1.0, shoulder=3200.0, rough=0.22, warp=1.4)
    W.mount([(-16300.0, -9300.0), (-16900.0, -7600.0)], 2000.0, crest=180.0, k=0.95, shoulder=3000.0, rough=0.16, warp=1.4)                          # whalebacks between the lanes
    W.mount([(-9300.0, -16300.0), (-7600.0, -16900.0)], 2000.0, crest=180.0, k=0.95, shoulder=3000.0, rough=0.16, warp=1.4)
    for bx, by in ((-29900.0, -11200.0), (-31300.0, -10300.0), (-29700.0, -9600.0)):
        W.knoll(bx, by, 700.0, 210.0)

    # ---------------------------------------------------------------- water, crossings
    W.water(LAKE, SURF, 154.0, "river")
    W.shore(unary_union([lake, tl.buffer(900.0)]), 30.0)
    for k in range(4):
        W.water(W.turn_geom(mere, k), -560.0, 150.0, "mere", bank=160.0, current=False)
        W.mist.append([*W.turn(MERE, k), -540.0, 1500.0, 260.0])
        W.water(W.turn_geom(tarn, k), MOOR_Z - 16.0, 90.0, "tarn", bank=120.0, current=False)
        W.ford(W.turn_geom(ford, k))
        W.deck(W.turn_geom(deck_a, k), "SM_T_Bridge_A_%d" % k)
        W.deck(W.turn_geom(deck_b, k), "SM_T_Bridge_B_%d" % k)
        lip, out = W.turn((-5900.0, 0.0), k), W.turn((-1.0, 0.0), k)
        W.falls.append(dict(lip=lip, out=out, top=MOOR_Z - 16.0, bottom=SURF, width=250.0))
    W.current_lines = [W.turn_geom(LineString(l), k).coords[:] for l in (head, cha, chb, tail[:int(len(tail) * 0.6)]) for k in range(4)]

    # ---------------------------------------------------------------- roads
    W.road(HIGH, half=560.0, kind="paved", name="high road")
    W.road(ISLE_A, name="isle road"); W.road(ISLE_B, name="isle road")
    W.road(FORD_A, name="ford road"); W.road(FORD_B, name="ford road")
    W.road([(-21000.0, -21000.0), (-19800.0, -24500.0), (-18300.0, -27300.0), (SH[0] - 200.0, SH[1] + 600.0)], half=420.0, name="shoulder road")
    W.road([(-19400.0, -12500.0), (-23500.0, -13000.0), (-26800.0, -14300.0), (WT[0] + 700.0, WT[1] - 500.0)], half=420.0, name="watch road")
    W.road([(-2600.0, 0.0), (0.0, -2600.0), (2600.0, 0.0), (0.0, 2600.0), (-2600.0, 0.0)], half=380.0, shoulder=300.0, sym=False, name="moor ring", smooth=6)

    # ---------------------------------------------------------------- veins, ruins
    W.vein(P[0] + 450.0, P[1] - 2500.0, pad=False)           # home (under the starting mine where a kingdom stands)
    W.vein(-15600.0, -10900.0); W.vein(-10900.0, -15600.0)   # the march's two, out toward the moor
    W.vein(ISLE[0] - 1250.0, 700.0); W.vein(ISLE[0] + 1250.0, -700.0)        # each island's two
    W.vein(-3700.0, -1550.0, pad=False)                      # the moor's four
    W.ruin(ISLE[0] + 2500.0, 100.0, relic=True, name="the Isle")             # each island's relic, at its upstream end
    W.ruin(0.0, 0.0, relic=True, sym=False, pad=False, name="the Great Circle")
    W.ruin(ISLE[0] - 1600.0, -4700.0); W.ruin(ISLE[0] + 1600.0, 4700.0)        # a tower on each bank at the island's bridges
    W.ruin(-11500.0, -9100.0)                                                 # the moor's foot, by the high road
    W.ruin(-22300.0, -13200.0)                                                # in the march's wood, on the watch road
    # greens: level ground to build on out in the march (by the hub, at the moor's foot, by the ford, by the isle's bridge)
    for x, y in ((-18900.0, -15300.0), (-15300.0, -18900.0), (-11000.0, -14300.0), (-14300.0, -11000.0), (-14000.0, -3400.0), (-3400.0, -14000.0), (-23300.0, -5800.0), (-5800.0, -23300.0)):
        W.green(x, y, 1400.0)
    for k in (1, 3):                                                           # the fallen kingdoms: their keep is a relic
        a = W.turn(P, k)
        W.ruin(a[0], a[1], relic=True, sym=False, pad=False, name="the Fallen Keep")

    # ---------------------------------------------------------------- woods, landmarks, dressing
    for x, y, rx, ry, n in ((-20500.0, -11500.0, 2100.0, 2500.0, 26), (-11500.0, -20500.0, 2500.0, 2100.0, 26), (-27500.0, -19500.0, 1700.0, 2300.0, 20),
                            (-19500.0, -27500.0, 2300.0, 1700.0, 16), (-15500.0, -5200.0, 2300.0, 1700.0, 22), (-5200.0, -15500.0, 1700.0, 2300.0, 22),
                            (-30000.0, -5500.0, 2300.0, 2000.0, 22), (-5500.0, -30000.0, 2000.0, 2300.0, 22), (-14500.0, -24500.0, 1700.0, 1500.0, 14),
                            (-8200.0, -8600.0, 1200.0, 2100.0, 12)):
        W.forest(x, y, rx, ry, n)
    W.landmark = dict(name="the Great Circle", pos=[0.0, 0.0], radius=900.0)
    W.site(D.great_circle, 0.0, 0.0, 0.0, sym=False, clear=3900.0)
    W.site(D.bridge_dressing, 0.0, 0.0, 0.0, sym=False, clear=0.0)
    W.site(None, ISLE[0] - 2500.0, 0.0, 0.0, variants=[D.colossus, D.wyrm_small, D.obelisks, D.sword_field])       # each island's own wonder, at its downstream end
    W.site(None, -15900.0, -13300.0, 0.0, variants=[D.obelisks, D.ruin, D.colossus, D.ruin], n=10)             # by the high road
    W.site(None, -23800.0, -8700.0, 0.0, variants=[D.sword_field, D.wyrm, D.sword_field, D.wyrm], clear=1600.0)                     # under the Teeth
    W.site(D.barrows, -30300.0, -10400.0, 0.0, mounds=[(400.0, -800.0), (-1000.0, 100.0), (600.0, 800.0)], clear=1900.0)
    W.site(D.stone_circle, -12700.0, -25300.0, 0.0, n=0)
    W.site(D.ruin, -17300.0, -13800.0, 40.0, n=0)
    W.site(D.ruin, -6200.0, -18800.0, -20.0, n=1)
    W.site(D.aqueduct, -16400.0, 0.0, 0.0, a=(-16900.0, -3300.0), b=(-15900.0, 3300.0), clear=1200.0)
    W.site(D.jetty, -33200.0, -2500.0, 0.0)
    W.site(D.drowned_tower, -36200.0, 1500.0, 0.0)
    W.site(D.ford_stones, FORD[0], FORD[1], 0.0, poly=ford)
    for k in (1, 3):
        a = W.turn(P, k)
        W.site(D.fallen_keep, a[0], a[1], W.ang(k), sym=False, clear=2100.0)
    for want in ((-12000.0, -2900.0), (-2900.0, -12000.0), (-20300.0, -5200.0), (-5200.0, -20300.0), (-19900.0, -19900.0), (-10500.0, -11300.0)):
        W.site(D.watch_post, want[0], want[1], 0.0, sym=False, clear=0.0)
    for want in ((-19400.0, -12900.0), (-12900.0, -19400.0), (-8700.0, -9300.0), (-23500.0, -13400.0), (-19800.0, -24900.0), (-5200.0, -4300.0)):
        W.site(D.cairn, want[0], want[1], 0.0, sym=False, clear=0.0)
    W.site(D.gate, P[0] - 3200.0, P[1] + 600.0, 0.0, sym=False)
    W.site(D.gate, -P[0] + 3200.0, -P[1] - 600.0, 180.0, sym=False)

    # ---------------------------------------------------------------- the air
    for k in range(4):
        for m in ([-37500.0, 500.0, SURF, 5600.0, 170.0], [-7600.0, 0.0, 0.0, 1100.0, 130.0], [-6900.0, 0.0, 0.0, 600.0, 420.0], [ISLE[0], 0.0, 40.0, 2900.0, 150.0],
                  [-13500.0, -400.0, 30.0, 2200.0, 120.0], [-23800.0, -8700.0, 500.0, 1500.0, 110.0]):
            px, py = W.turn((m[0], m[1]), k)
            W.mist.append([px, py, m[2], m[3], m[4]])

    # ---------------------------------------------------------------- what must hold
    all_cross = [W.turn_geom(g, k) for g in (ford, deck_a, deck_b) for k in range(4)]
    W.river_all = all_cross
    W.crossings = [("inner fords", [W.turn_geom(ford, k) for k in range(4)]), ("island bridges", [W.turn_geom(g, k) for g in (deck_a, deck_b) for k in range(4)])]
    hub = Point(0.0, 0.0).buffer(15500.0)
    W.checks.append(("the rivers (every ford and bridge closed, the High Moor closed)", all_cross + [hub], "player", W.turn(P, 1)))
    W.checks.append(("the rivers, toward the other neighbour", all_cross + [hub], "player", W.turn(P, 3)))
    W.reach += [("the High Moor", 800.0, 800.0)] + [("an island", *W.turn((ISLE[0], -300.0), k)) for k in range(4)] + [("the fallen kingdom's table", *W.turn((P[0] + 1500.0, P[1] + 1400.0), k)) for k in (1, 3)]
    W.label(0.0, 0.0, "THE HIGH MOOR")
    W.label(ISLE[0], 0.0, "ISLE", sym=True)
    W.label(FORD[0] - 900.0, FORD[1], "ford", sym=True, small=True)
    W.label(SH[0], SH[1] + 900.0, "the Shoulder", sym=True, small=True)
    W.label(WT[0], WT[1] - 900.0, "the Watch", sym=True, small=True)
    W.label(POOL[0] - 600.0, 600.0, "falls", sym=True, small=True)
    W.zone_water = LAKE
    W.scatter_hills(9, 811, clear=1250.0, region=lambda x, y: x < -1200.0 and y < -1200.0, extra_keep=[Point(W.turn(MERE, k)).buffer(3400.0) for k in range(4)] + [Point(0, 0).buffer(15000.0)])
    W.label(MERE[0], MERE[1] + 1500.0, "the Black Mere", sym=True, small=True)
    load_peaks(W, [(0, B + 5600.0, -22000.0, 13000.0, 9400.0, 20.0), (2, B + 6900.0, -7000.0, 15000.0, 11500.0, 100.0), (4, B + 5800.0, 9000.0, 13000.0, 9800.0, 250.0),
                   (3, B + 6200.0, 24000.0, 13000.0, 8800.0, 40.0), (5, 12000.0, -(B + 5200.0), 10500.0, 6200.0, 60.0), (1, 9000.0, B + 5200.0, 10500.0, 6000.0, 140.0),
                   (1, 27000.0, -(B + 6200.0), 11000.0, 7800.0, 300.0), (5, 26000.0, B + 6400.0, 11000.0, 7600.0, 200.0)])
    return W


PLANS = {"two": plan_two, "four": plan_four}
