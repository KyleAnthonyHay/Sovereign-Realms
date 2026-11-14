"""Dresses /Game/Maps/L_Battlefield as a golden-hour diorama: terraced greybox terrain, rocks,
conifers, a pond, lighting, fog and post-process. Deterministic and re-runnable: everything it
owns lives in the outliner folders Terrain / Props / Water / Lighting and is rebuilt from scratch.

Run inside the editor (see Tools/ue_py.py):
  Tools/ue_py.py Tools/build_battlefield_visuals.py            # everything
  Tools/ue_py.py -c "PARTS=['lighting']; exec(open('<abs path to this file>').read())"   # one part
Parts: terrain, props, lighting. Materials come from Tools/build_visual_materials.py.
Gameplay rules honoured (Docs/VISUAL_CONTRACT.md): the +/-3000 cm play area stays flat and open,
ledges inside it are <= 40 cm, blocking rocks are single convex boxes, trees have no collision.
"""
import math, random
import unreal

PARTS = globals().get("PARTS", ["terrain", "props", "lighting"])
MAP = "/Game/Maps/L_Battlefield"
MAT = "/Game/SR/Materials/"
BOUND = 3000.0          # playable half extent
WORLD = 7200.0          # dressed half extent (the zoomed-out camera at a map corner sees to about 5500)

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
load = unreal.EditorAssetLibrary.load_asset

CUBE = load("/Engine/BasicShapes/Cube")
CYL = load("/Engine/BasicShapes/Cylinder")
CONE = load("/Engine/BasicShapes/Cone")
SPHERE = load("/Engine/BasicShapes/Sphere")
PLANE = load("/Engine/BasicShapes/Plane")
M_TERRAIN = load(MAT + "M_Terrain")
M_ROCK = load(MAT + "MI_Terrain_Rock")
M_FOLIAGE = load(MAT + "M_Foliage")
M_TRUNK = load(MAT + "MI_Foliage_Trunk")
M_WATER = load(MAT + "M_Water")

# Lake: a recess in the far-left corner, outside the play area.
LAKE_X0, LAKE_Y1, LAKE_BED, LAKE_SURFACE = 3350.0, -1500.0, -140.0, -42.0


def clear_folder(prefix):
    for a in eas.get_all_level_actors():
        if str(a.get_folder_path()).startswith(prefix):
            eas.destroy_actor(a)


def path_centre(x):
    """Same curve as the Path parameter of M_Terrain."""
    ph = x / 5200.0 * 2.0 * math.pi
    return 60.0 + 380.0 * math.sin(ph) + 114.0 * math.sin(ph * 2.7 + 1.3)


def in_lake(x, y, margin=0.0):
    return x > LAKE_X0 - margin and y < LAKE_Y1 + margin


# ------------------------------------------------------------------ terrain
SOLIDS = []   # (kind, x, y, a, b, yaw, top) for height queries when placing props


def mesh_actor(mesh, mat, loc, rot, scale, label, folder, collide=True, shadow=True):
    a = eas.spawn_actor_from_class(unreal.StaticMeshActor, loc, rot)
    a.set_actor_label(label)
    a.set_folder_path(folder)
    c = a.static_mesh_component
    c.set_static_mesh(mesh)
    c.set_material(0, mat)
    a.set_actor_scale3d(scale)
    if not collide:
        c.set_collision_profile_name("NoCollision")
    c.set_editor_property("cast_shadow", shadow)
    return a


def disc(x, y, r, top, label, folder="Terrain/Plateaus", bottom=-30.0, mat=None):
    h = top - bottom
    mesh_actor(CYL, mat or M_TERRAIN, unreal.Vector(x, y, bottom + h * 0.5), unreal.Rotator(0, 0, 0),
               unreal.Vector(r / 50.0, r / 50.0, h / 100.0), label, folder)
    SOLIDS.append(("disc", x, y, r, r, 0.0, top))


def slab(x0, x1, y0, y1, top, label, folder="Terrain/Ground", thickness=200.0, yaw=0.0, mat=None):
    cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
    mesh_actor(CUBE, mat or M_TERRAIN, unreal.Vector(cx, cy, top - thickness * 0.5), unreal.Rotator(0, 0, yaw),
               unreal.Vector((x1 - x0) / 100.0, (y1 - y0) / 100.0, thickness / 100.0), label, folder)
    SOLIDS.append(("box", cx, cy, (x1 - x0) * 0.5, (y1 - y0) * 0.5, yaw, top))


def height_at(x, y):
    best = LAKE_BED if in_lake(x, y) else 0.0
    for kind, sx, sy, a, b, yaw, top in SOLIDS:
        if top <= best:
            continue
        dx, dy = x - sx, y - sy
        if kind == "disc":
            inside = dx * dx + dy * dy <= a * a
        else:
            c, s = math.cos(math.radians(-yaw)), math.sin(math.radians(-yaw))
            lx, ly = dx * c - dy * s, dx * s + dy * c
            inside = abs(lx) <= a and abs(ly) <= b
        if inside:
            best = top
    return best


def push_outside_play_area(x, y, r, margin=90.0):
    """Tall pieces must not narrow the play area: slide them out until they clear +/-BOUND."""
    need = BOUND + margin + r
    if abs(x) >= need or abs(y) >= need:
        return x, y
    if need - abs(x) < need - abs(y):
        return math.copysign(need, x if x else 1.0), y
    return x, math.copysign(need, y if y else 1.0)


def south_limit(x):
    """Tallest thing allowed at world X on the camera's side of the field (screen bottom).
    Scenery there sits between the camera and the play area, so it may only hide ground that is at
    least 150 cm outside the playable bound, at every zoom (camera numbers: Docs/VISUAL_CONTRACT.md)."""
    reach = (-BOUND - 150.0) - x          # how far behind itself the object may hide ground
    if reach <= 0.0:
        return 0.0
    best = 1e9
    for i in range(41):
        z01 = i / 40.0
        dist = 1300.0 * (4800.0 / 1300.0) ** z01
        pitch = math.radians(43.0 + 17.0 * z01)
        cam_x, cam_z = -BOUND - dist * math.cos(pitch), dist * math.sin(pitch)
        if x > cam_x:
            best = min(best, reach * cam_z / ((x - cam_x) + reach))
    return best


def allowed_top(x, y, r=0.0):
    """Height cap for scenery at (x, y): only the south side is restricted (40 cm aprons always fit)."""
    if x + r > -BOUND or abs(y) > BOUND + 2200:
        return 1e9
    return max(south_limit(x + r), 40.0)


def plateau(rng, cx, cy, radius, tiers, name):
    """A stack of blobby tiers. Tier 0 is a low walkable apron (<= 40 cm); the rest are cliffs."""
    top = 0.0
    for t in range(tiers):
        if t == 0:
            top = rng.uniform(30.0, 38.0)
        else:
            top += rng.uniform(85.0, 175.0)
        shrink = 1.0 - 0.24 * t
        blobs = rng.randint(3, 5) if t < 2 else rng.randint(2, 3)
        for b in range(blobs):
            ang = rng.uniform(0, 2 * math.pi)
            off = radius * shrink * rng.uniform(0.15, 0.55) * (0.0 if b == 0 else 1.0)
            r = radius * shrink * rng.uniform(0.45, 0.72)
            x, y = cx + math.cos(ang) * off, cy + math.sin(ang) * off
            if t > 0:
                x, y = push_outside_play_area(x, y, r)
            if in_lake(x, y, r + 60.0) or abs(y - path_centre(x)) < r + 260.0 and t > 0 and abs(x) < 4600:
                continue
            if top > allowed_top(x, y, r):
                continue
            disc(x, y, r, top + rng.uniform(-4.0, 4.0), "%s_T%d_%d" % (name, t, b))


def mound(rng, cx, cy, radius, tiers, name, step=35.0, inset=None):
    """Contour-line hill for inside the play area: every tier is the one below shrunk inward, and
    every step is `step` cm (<= StepHeight 45), so units walk up it."""
    lobes = [(cx, cy, radius)]
    for i in range(rng.randint(1, 3)):
        a = rng.uniform(0, 2 * math.pi)
        r = radius * rng.uniform(0.55, 0.8)
        d = radius * rng.uniform(0.45, 0.7)
        lobes.append((cx + math.cos(a) * d, cy + math.sin(a) * d, r))
    inset = inset or radius * 0.2
    for t in range(tiers):
        for i, (x, y, r) in enumerate(lobes):
            rr = r - inset * t * rng.uniform(0.92, 1.08)
            if rr > 85.0:
                disc(x, y, rr, step * (t + 1) + rng.uniform(-2.0, 2.0), "%s_T%d_%d" % (name, t, i), "Terrain/FieldTerraces")


def knoll(rng, x, y, r, h, name):
    """A small blocking outcrop (one convex cylinder, taller than a unit can step) with a turf cap."""
    disc(x, y, r, h, name, "Terrain/Knolls")
    disc(x + rng.uniform(-25, 25), y + rng.uniform(-25, 25), r * 0.62, h + 34.0, name + "_cap", "Terrain/Knolls")


# In-field features: (x, y, radius, tiers). Kept clear of both armies' ground and the lane between them.
MOUNDS = [(-300, 1800, 520, 3), (900, -1950, 560, 3), (2350, -950, 430, 2), (-2300, -1150, 480, 3),
          (-2250, 1500, 420, 2), (2200, 1950, 520, 4), (-950, -2500, 500, 3), (750, 2600, 470, 3)]
KNOLLS = [(-2650, 2500, 250, 120), (2650, -2550, 270, 135), (2750, 800, 230, 115), (-2750, -2350, 240, 110),
          (350, -2800, 220, 105), (-1350, 2750, 230, 125), (1550, 2800, 250, 120), (2800, 2700, 260, 140)]


def build_terrain():
    clear_folder("Greybox")
    clear_folder("Terrain")
    clear_folder("Water")
    rng = random.Random(7)

    # Base ground in three slabs so the lake corner can sit lower. Top faces at Z = 0.
    slab(-WORLD, LAKE_X0, -WORLD, WORLD, 0.0, "Ground_Main")
    slab(LAKE_X0, WORLD, LAKE_Y1, WORLD, 0.0, "Ground_North")
    slab(LAKE_X0, WORLD, -WORLD, LAKE_Y1, LAKE_BED, "Ground_LakeBed", thickness=100.0)
    water = mesh_actor(PLANE, M_WATER, unreal.Vector((LAKE_X0 + WORLD) * 0.5, (LAKE_Y1 - WORLD) * 0.5, LAKE_SURFACE), unreal.Rotator(0, 0, 0),
                       unreal.Vector((WORLD - LAKE_X0) / 100.0 + 1.0, (WORLD + LAKE_Y1) / 100.0 + 1.0, 1.0), "Pond", "Water", collide=False, shadow=False)
    # Scalloped shoreline: turf-topped discs along the two inner banks.
    for i in range(16):
        t = i / 15.0
        if i % 2 == 0:
            x, y = LAKE_X0 + rng.uniform(-80, 140), LAKE_Y1 - t * (WORLD + LAKE_Y1)
        else:
            x, y = LAKE_X0 + t * (WORLD - LAKE_X0), LAKE_Y1 + rng.uniform(-140, 80)
        r = rng.uniform(190, 420)
        mesh_actor(CYL, M_TERRAIN, unreal.Vector(x, y, -100.0), unreal.Rotator(0, 0, 0),
                   unreal.Vector(r / 50.0, r / 50.0, 2.0 + rng.uniform(0.0, 0.05)), "Shore_%02d" % i, "Terrain/Shore")
    for i in range(5):   # stepping stones / islets
        x, y = rng.uniform(LAKE_X0 + 500, 6200), rng.uniform(-6200, LAKE_Y1 - 500)
        r = rng.uniform(110, 260)
        disc(x, y, r, LAKE_SURFACE + rng.uniform(25, 70), "Islet_%d" % i, "Terrain/Shore", bottom=LAKE_BED - 20.0)

    # Ring of plateaus framing the field, then a taller outer ring as backdrop.
    n = 26
    for i in range(n):
        ang = 2 * math.pi * i / n + rng.uniform(-0.06, 0.06)
        # rounded-square ring: distance to a superellipse
        ca, sa = math.cos(ang), math.sin(ang)
        d = 3950.0 / max((abs(ca) ** 4 + abs(sa) ** 4) ** 0.25, 0.01) * rng.uniform(0.94, 1.08)
        x, y = ca * d, sa * d
        far = ca > 0.35     # the side at the top of the screen can be taller: nothing behind it to hide
        tiers = rng.choice([3, 4, 4, 5]) if far else rng.choice([2, 3, 3, 4])
        plateau(rng, x, y, rng.uniform(820.0, 1250.0), tiers, "Plateau_%02d" % i)
    for i in range(18):
        ang = 2 * math.pi * (i + 0.5) / 18 + rng.uniform(-0.08, 0.08)
        ca, sa = math.cos(ang), math.sin(ang)
        d = 5900.0 / max((abs(ca) ** 4 + abs(sa) ** 4) ** 0.25, 0.01) * rng.uniform(0.95, 1.06)
        plateau(rng, ca * d, sa * d, rng.uniform(1300.0, 1900.0), rng.choice([4, 5, 5, 6]), "Backdrop_%02d" % i)

    # Inside the field: walkable contour mounds (35 cm steps) and a few blocking knolls near the edges.
    for i, (x, y, r, tiers) in enumerate(MOUNDS):
        mound(rng, x, y, r, tiers, "Mound_%d" % i)
    for i, (x, y, r, h) in enumerate(KNOLLS):
        knoll(rng, x, y, r, h, "Knoll_%d" % i)
    print("terrain actors:", len(SOLIDS))
    return water


# ------------------------------------------------------------------ props
def add_ism(owner, mesh, mat, name, shadow=True):
    root = sds.k2_gather_subobject_data_for_instance(owner)[0]
    p = unreal.AddNewSubobjectParams()
    p.set_editor_property("parent_handle", root)
    p.set_editor_property("new_class", unreal.InstancedStaticMeshComponent)
    handle, _ = sds.add_new_subobject(p)
    sds.rename_subobject(handle, unreal.Text(name))
    comp = [c for c in owner.get_components_by_class(unreal.InstancedStaticMeshComponent) if c.get_instance_count() == 0 and c.static_mesh is None][0]
    comp.set_static_mesh(mesh)
    comp.set_material(0, mat)
    comp.set_collision_profile_name("NoCollision")       # contract: foliage must not be WorldStatic
    comp.set_editor_property("cast_shadow", shadow)
    comp.set_editor_property("mobility", unreal.ComponentMobility.STATIC)
    return comp


def xf(x, y, z, sx, sy, sz, yaw=0.0, pitch=0.0, roll=0.0):
    return unreal.Transform(unreal.Vector(x, y, z), unreal.Rotator(roll, pitch, yaw), unreal.Vector(sx, sy, sz))


def rock(rng, x, y, size, yaw, name, blocking):
    """A boulder pile. Gameplay sees one convex box (the core); the rounded stones heaped over it
    have no collision, so the blocking shape stays exactly the footprint in `size`."""
    z = height_at(x, y)
    sx, sy, sz = size
    folder = "Props/Rocks"
    if blocking:
        core = mesh_actor(CUBE, M_ROCK, unreal.Vector(x, y, z + sz * 0.5 - 12.0), unreal.Rotator(0, 0, yaw),
                          unreal.Vector(sx / 100.0, sy / 100.0, sz / 100.0), name + "_Collision", folder, shadow=False)
        core.static_mesh_component.set_editor_property("visible", False)     # collision only
        core.tags = ["SRBlocker"]
    # main stone covers the core; two or three smaller ones lean on it
    mesh_actor(SPHERE, M_ROCK, unreal.Vector(x, y, z + sz * 0.42), unreal.Rotator(rng.uniform(-8, 8), yaw, rng.uniform(-8, 8)),
               unreal.Vector(sx * 1.2 / 100.0, sy * 1.2 / 100.0, sz * 1.5 / 100.0), name + "_stone", folder, collide=False)
    for i in range(rng.randint(2, 3)):
        a = math.radians(yaw) + rng.uniform(0, 2 * math.pi)
        k = rng.uniform(0.36, 0.52)
        px, py = x + math.cos(a) * sx * 0.42, y + math.sin(a) * sy * 0.42
        mesh_actor(SPHERE, M_ROCK, unreal.Vector(px, py, height_at(px, py) + sz * k * 0.38),
                   unreal.Rotator(rng.uniform(-15, 15), rng.uniform(0, 180), rng.uniform(-15, 15)),
                   unreal.Vector(sx * k * 1.1 / 100.0, sy * k / 100.0, sz * k * 1.15 / 100.0), "%s_stone%d" % (name, i), folder, collide=False)
    for i in range(rng.randint(2, 4)):   # pebbles
        a = rng.uniform(0, 2 * math.pi)
        d = max(sx, sy) * rng.uniform(0.85, 1.25)
        s = rng.uniform(24, 50)
        px, py = x + math.cos(a) * d, y + math.sin(a) * d
        mesh_actor(SPHERE, M_ROCK, unreal.Vector(px, py, height_at(px, py) + s * 0.22),
                   unreal.Rotator(rng.uniform(-20, 20), rng.uniform(0, 90), rng.uniform(-20, 20)),
                   unreal.Vector(s / 100.0, s * rng.uniform(0.7, 1.2) / 100.0, s * 0.62 / 100.0), "%s_pebble%d" % (name, i), folder, collide=False)


def build_props():
    clear_folder("Props")
    rng = random.Random(21)
    if not SOLIDS:
        raise RuntimeError("props need the terrain built in the same run (height queries)")

    # Blocking rocks. The first three stand where the gameplay test blocks stood, same footprints.
    rock(rng, 150, -260, (230, 190, 150), 20, "Rock_Centre", True)
    rock(rng, -250, 820, (300, 220, 210), -35, "Rock_East", True)
    rock(rng, 650, -900, (260, 260, 180), 50, "Rock_West", True)
    rock(rng, -1900, -1350, (210, 170, 130), 70, "Rock_SW", True)
    rock(rng, 2150, 1250, (240, 200, 160), -15, "Rock_NE", True)
    for i in range(14):   # dressing outcrops on the surrounding terraces
        for _ in range(30):
            x, y = rng.uniform(-6000, 6000), rng.uniform(-6000, 6000)
            if max(abs(x), abs(y)) > BOUND + 350 and not in_lake(x, y, 250) and abs(y - path_centre(x)) > 400:
                break
        s = rng.uniform(150, 330)
        rock(rng, x, y, (s, s * rng.uniform(0.7, 1.0), s * rng.uniform(0.55, 0.9)), rng.uniform(0, 180), "Outcrop_%02d" % i, False)

    # Conifers: instanced, no collision. Clusters outside the play area; the sun side (screen bottom-right)
    # gets a dense stand so long shadows and light shafts rake across the field.
    trees = eas.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0))
    trees.set_actor_label("Conifers")
    trees.set_folder_path("Props/Foliage")
    cones = add_ism(trees, CONE, M_FOLIAGE, "Boughs")
    trunks = add_ism(trees, CYL, M_TRUNK, "Trunks")
    bushes = add_ism(trees, SPHERE, M_FOLIAGE, "Bushes")

    tufts = add_ism(trees, CONE, load(MAT + "MI_Foliage_Tuft"), "Tufts", shadow=False)

    def tree(x, y, s, slim=1.0):
        z = height_at(x, y)
        tiers = rng.choice([4, 4, 5])
        base_r, tier_h = rng.uniform(105.0, 135.0) * s * slim, rng.uniform(170.0, 205.0) * s
        trunk_h, trunk_r = 170.0 * s, 17.0 * s
        total = trunk_h * 0.55 + sum(tier_h * (0.92 + 0.1 * t) * 0.5 for t in range(tiers)) + tier_h * 0.6
        cap = allowed_top(x, y)
        if z + total > cap:
            s2 = s * (cap - z) / total
            if s2 < 0.42:
                return False
            return tree(x, y, s2, slim)
        yaw = rng.uniform(0, 360)
        trunks.add_instance(xf(x, y, z + trunk_h * 0.5 - 10.0, trunk_r / 50.0, trunk_r / 50.0, trunk_h / 100.0, yaw), True)
        zc = z + trunk_h * 0.55
        for t in range(tiers):
            f = 1.0 - t / float(tiers) * 0.72
            h = tier_h * (0.92 + 0.1 * t)
            cones.add_instance(xf(x, y, zc + h * 0.5, base_r * f / 50.0, base_r * f / 50.0, h / 100.0, yaw + t * 37.0), True)
            zc += h * 0.5
        return True

    def bush(x, y):
        bs = rng.uniform(0.55, 1.1)
        bushes.add_instance(xf(x, y, height_at(x, y) + 18.0 * bs, bs, bs * rng.uniform(0.8, 1.2), bs * 0.62, rng.uniform(0, 360)), True)

    clusters = []
    for i in range(46):
        for _ in range(40):
            x, y = rng.uniform(-6300, 6300), rng.uniform(-6300, 6300)
            if max(abs(x), abs(y)) > BOUND + 260:
                break
        clusters.append((x, y, rng.randint(4, 9), rng.uniform(260, 520)))
    # hand-placed stands: the sun side (screen right) and the far edge (screen top), where height hides nothing
    clusters += [(-2300, 3550, 8, 400), (-900, 3500, 7, 380), (700, 3560, 8, 420), (2200, 3650, 7, 400), (-3300, 3700, 7, 380),
                 (3500, 1500, 9, 460), (3700, 0, 6, 340), (3450, 2900, 8, 420), (3600, -900, 7, 380),
                 (1200, -3550, 7, 380), (-1000, -3600, 6, 360), (2600, -3600, 6, 360)]
    count = 0
    placed = []
    for cx, cy, num, spread in clusters:
        for k in range(num):
            a, d = rng.uniform(0, 2 * math.pi), spread * math.sqrt(rng.uniform(0.02, 1.0))
            x, y = cx + math.cos(a) * d, cy + math.sin(a) * d
            if max(abs(x), abs(y)) < BOUND + 130 or max(abs(x), abs(y)) > WORLD - 300:
                continue
            if in_lake(x, y, 120) or abs(y - path_centre(x)) < 330:
                continue
            if any((x - px) ** 2 + (y - py) ** 2 < 150 ** 2 for px, py in placed):
                continue
            if not tree(x, y, rng.uniform(0.75, 1.35)):
                continue
            placed.append((x, y))
            count += 1
            if rng.random() < 0.55:   # undergrowth
                a2 = rng.uniform(0, 2 * math.pi)
                bx, by = x + math.cos(a2) * rng.uniform(90, 190), y + math.sin(a2) * rng.uniform(90, 190)
                if max(abs(bx), abs(by)) > BOUND + 60 and not in_lake(bx, by, 60):
                    bush(bx, by)
    # one or two smaller trees on each knoll: unreachable ground, so no collision is needed
    for x, y, r, h in KNOLLS:
        if tree(x + rng.uniform(-30, 30), y + rng.uniform(-30, 30), rng.uniform(0.62, 0.85), 0.9):
            count += 1
        bush(x + r * 0.75, y + rng.uniform(-60, 60))
    print("conifers:", count)

    # Grass tufts: tiny shadowless cones in clumps, everywhere except the track. Units wade through them.
    n_tufts = 0
    for i in range(520):
        cx, cy = rng.uniform(-4200, 4200), rng.uniform(-4200, 4200)
        if in_lake(cx, cy, 80) or abs(cy - path_centre(cx)) < 300:
            continue
        for k in range(rng.randint(6, 11)):
            x, y = cx + rng.gauss(0, 24), cy + rng.gauss(0, 24)
            h = rng.uniform(22, 52)
            r = rng.uniform(3.0, 6.0)
            tufts.add_instance(xf(x, y, height_at(x, y) + h * 0.5 - 2.0, r / 50.0, r / 50.0, h / 100.0, rng.uniform(0, 360),
                                  rng.uniform(-20, 20), rng.uniform(-20, 20)), True)
            n_tufts += 1
    print("tufts:", n_tufts)


# ------------------------------------------------------------------ lighting
def find_or_spawn(cls, label, folder="Lighting", loc=unreal.Vector(0, 0, 1000)):
    for a in eas.get_all_level_actors():
        if a.get_actor_label() == label and isinstance(a, cls):
            a.set_folder_path(folder)
            return a
    a = eas.spawn_actor_from_class(cls, loc)
    a.set_actor_label(label)
    a.set_folder_path(folder)
    return a


def set_pp(volume, **values):
    """Sets post-process fields and ticks their override flags."""
    s = volume.settings
    for k, v in values.items():
        s.set_editor_property("override_" + k, True)
        s.set_editor_property(k, v)
    volume.settings = s


def build_lighting():
    V4 = unreal.Vector4
    # Sun: low and warm, from behind-right of the gameplay camera, so unit fronts are lit and shadows fall up-left.
    sun = find_or_spawn(unreal.DirectionalLight, "Sun")
    sun.set_actor_rotation(unreal.Rotator(0, -31.0, -42.0), False)
    lc = sun.light_component
    lc.set_mobility(unreal.ComponentMobility.MOVABLE)
    lc.set_editor_property("intensity", 8.0)
    lc.set_editor_property("light_color", unreal.Color(r=255, g=230, b=200, a=255))
    lc.set_editor_property("light_source_angle", 1.6)             # wider than the real sun: softer, miniature-scale penumbrae
    lc.set_editor_property("atmosphere_sun_light", True)
    lc.set_editor_property("volumetric_scattering_intensity", 2.2)  # light shafts in the volumetric fog
    lc.set_editor_property("cast_shadows", True)

    sky = find_or_spawn(unreal.SkyLight, "SkyLight")
    sc = sky.light_component
    sc.set_mobility(unreal.ComponentMobility.MOVABLE)
    sc.set_editor_property("real_time_capture", True)
    sc.set_editor_property("intensity", 6.5)
    sc.set_editor_property("light_color", unreal.Color(r=215, g=228, b=255, a=255))   # cool fill for the shadow side
    sc.set_editor_property("volumetric_scattering_intensity", 0.6)

    find_or_spawn(unreal.SkyAtmosphere, "SkyAtmosphere", loc=unreal.Vector(0, 0, 0))

    fog = find_or_spawn(unreal.ExponentialHeightFog, "HeightFog", loc=unreal.Vector(0, 0, 0))
    fog.set_actor_location(unreal.Vector(0, 0, 0), False, False)
    fc = fog.component
    fc.set_editor_property("fog_density", 0.22)
    fc.set_editor_property("fog_height_falloff", 1.6)             # hugs the ground: the terraces rise out of it
    fc.set_editor_property("fog_inscattering_luminance", unreal.LinearColor(0.0, 0.0, 0.0))
    fc.set_editor_property("directional_inscattering_luminance", unreal.LinearColor(0.0, 0.0, 0.0))
    fc.set_editor_property("start_distance", 0.0)
    fc.set_editor_property("enable_volumetric_fog", True)
    fc.set_editor_property("volumetric_fog_scattering_distribution", 0.35)
    fc.set_editor_property("volumetric_fog_albedo", unreal.Color(r=255, g=244, b=226, a=255))
    fc.set_editor_property("volumetric_fog_extinction_scale", 1.0)
    fc.set_editor_property("volumetric_fog_distance", 9000.0)
    fc.set_editor_property("volumetric_fog_near_fade_in_distance", 300.0)

    pp = find_or_spawn(unreal.PostProcessVolume, "PostProcess", loc=unreal.Vector(0, 0, 0))
    pp.set_editor_property("unbound", True)
    pp.set_editor_property("priority", 0.0)
    set_pp(pp,
           # exposure: fixed, never adapts (auto exposure is also off project-wide)
           auto_exposure_method=unreal.AutoExposureMethod.AEM_MANUAL,
           auto_exposure_apply_physical_camera_exposure=False,
           auto_exposure_bias=-0.25,
           # bloom: only the hottest highlights and the hit flash
           bloom_intensity=0.45, bloom_threshold=-1.0,
           vignette_intensity=0.4,
           # grade: warm highlights, cool shadows, a touch of contrast, slightly held-back saturation
           color_saturation=V4(0.92, 0.92, 0.92, 1.0),
           color_contrast=V4(1.07, 1.07, 1.07, 1.0),
           color_gain_shadows=V4(0.93, 0.98, 1.10, 1.0),
           color_gain_highlights=V4(1.07, 1.0, 0.90, 1.0),
           color_saturation_shadows=V4(0.92, 0.92, 0.92, 1.0),
           film_toe=0.6, film_slope=0.9,
           film_grain_intensity=0.12,
           scene_fringe_intensity=0.0,
           motion_blur_amount=0.0)
    print("lighting done")


# ------------------------------------------------------------------ run
if "terrain" in PARTS:
    build_terrain()
if "props" in PARTS:
    build_props()
if "lighting" in PARTS:
    build_lighting()
les.save_current_level()
print("saved", MAP)
