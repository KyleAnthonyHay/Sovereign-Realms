"""Clean style-reference renders of every character, building and nature asset, for prompting AI image generators so
new art matches the voxel style. One look everywhere: a soft light-grey studio gradient, a soft ground shadow, a warm
key sun from the front right, a cool soft fill from the left, a subtle rim from behind, AgX with a mild contrast look.

    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python Tools/blender/render_style_refs.py \
        [-- [NAME|chars|buildings|nature|sheets ...] [--gpu] [--samples N]]

Writes into References/StyleRefs/:
    <Character>_front/_three_quarter/_side/_back.png   (1200 x 1200, the figure ~80 % of the frame height)
    <Building>_three_quarter.png, <Building>_front.png  (1600 x 1200; 35 deg down from the front left, and head-on)
    Characters_sheet.png, Buildings_sheet.png (labelled grid), Nature_sheet.png
Renders on the CPU by default (Cycles on Metal can crash here); --gpu tries Metal.
"""
import json
import math
import os
import shutil
import sys
import tempfile

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import voxlib as V

ROOT = V.ROOT
OUT = os.path.join(ROOT, "References", "StyleRefs")
ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
GPU = "--gpu" in ARGV
SAMPLES = int(ARGV[ARGV.index("--samples") + 1]) if "--samples" in ARGV else 96
ONLY = [a for i, a in enumerate(ARGV) if not a.startswith("--") and (i == 0 or ARGV[i - 1] != "--samples")]
TMP = tempfile.mkdtemp(prefix="styleref_")

# (character json, file name, label)
CHARACTERS = [
    ("SM_KingB", "KingDavid", "King David"),
    ("SM_Swordsman", "Swordsman", "Swordsman"),
    ("SM_Archer", "Archer", "Archer"),
]
# character views: the figure turns, the camera and the lights stay (yaw of the figure, degrees CCW from above)
CHAR_VIEWS = [("front", 0.0), ("three_quarter", 35.0), ("side", 90.0), ("back", 180.0)]

# (mesh, file name, label)
BUILDINGS = [
    ("SM_Castle", "Castle", "Castle"),
    ("SM_TownHall", "TownHall", "Town Hall"),
    ("SM_BarracksYard", "BarracksYard", "Barracks Yard"),
    ("SM_ArcheryHall", "ArcheryHall", "Archery Hall"),
    ("SM_WatchTower", "WatchTower", "Watch Tower"),
    ("SM_Farmstead", "Farmstead", "Farmstead"),
    ("SM_MineCliff", "MineCliff", "Gold Mine Cliff"),
    ("SM_Windmill", "Windmill", "Windmill"),
    ("SM_Dock", "Dock", "Dock"),
    ("SM_Boat", "Boat", "Boat"),
    ("SM_HayCart", "HayCart", "Hay Cart"),
    ("SM_Bridge", "Bridge", "Bridge"),
    ("SM_Barracks", "Barracks", "Barracks (old)"),
    ("SM_ArcheryRange", "ArcheryRange", "Archery Range (old)"),
    ("SM_FarmCottage_A", "FarmCottage_A", "Farm Cottage A (old)"),
    ("SM_FarmCottage_B", "FarmCottage_B", "Farm Cottage B (old)"),
]

TREES = ["SM_Tree2_%s" % c for c in "ABCD"]
BUSHES = ["SM_Bush_%s" % c for c in "ABC"]
ROCKS = ["SM_Rock_%s" % c for c in "ABCDE"]

# the backdrop (display sRGB): a soft vertical gradient, lighter at the top
BG_TOP = np.array([0.900, 0.900, 0.905])
BG_BOTTOM = np.array([0.765, 0.765, 0.775])
SHEET_BG = (0.93, 0.93, 0.935)
LABEL_COL = (0.16, 0.16, 0.17)


def want(*names):
    if not ONLY:
        return True
    return any(n in ONLY for n in names)


# ------------------------------------------------------------------------------------------------------- import

def import_gltf(name):
    """Import a mesh and swap the importer's plain materials for the textured preview materials (as render_buildings)."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(V.MESHES, name + ".gltf"))
    obs = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    for ob in obs:
        attr = ob.data.color_attributes[0].name if ob.data.color_attributes else "Col"
        for i, m in enumerate(ob.data.materials):
            if m is None:
                continue
            slot = m.name.split(".")[0]
            slot = slot[4:] if slot.startswith("Vox_") else slot
            if not m.get("vox_preview"):
                m.name = "imported_" + m.name
            pm = V.material(slot)
            pm["vox_preview"] = True
            for n in pm.node_tree.nodes:
                if n.type == "VERTEX_COLOR":
                    n.layer_name = attr
            ob.data.materials[i] = pm
    return obs


_prop_lib = {}


def place_props(mesh, x=0.0, y=0.0, z=0.0, s=1.0):
    """The instances an asset lists in its sidecar "props" (dummies, wheat, sheep, crates), as render_buildings does."""
    out = []
    for pr in json.load(open(os.path.join(V.MESHES, mesh + ".json"))).get("props", []):
        name = pr["mesh"]
        if name not in _prop_lib:
            src = import_gltf(name)
            for o in src:
                o.hide_render = True
                o.hide_viewport = True
            _prop_lib[name] = src
        for o in _prop_lib[name]:
            c = o.copy()
            bpy.context.scene.collection.objects.link(c)
            c.hide_render = c.hide_viewport = False
            px, py, pz = pr["pos"]
            k = float(pr.get("scale", 1.0)) * s
            c.location = (x + px * s, y + py * s, z + pz * s)
            c.rotation_euler = (0.0, 0.0, math.radians(float(pr.get("yaw", 0.0))))
            c.scale = (k, k, k)
            out.append(c)
    return out


def place_character(rig, x=0.0, y=0.0, yaw=0.0):
    """Assemble a character from the parts in its json. The pivots are absolute (rest pose, figure facing -Y), so every
    part goes at its own pivot under one root, ignoring the rig's parent chain."""
    meta = json.load(open(os.path.join(V.MESHES, rig + ".json")))
    root = bpy.data.objects.new(rig + "_root", None)
    bpy.context.scene.collection.objects.link(root)
    obs = []
    for key, part in meta["parts"].items():
        if not os.path.exists(os.path.join(V.MESHES, part["mesh"] + ".gltf")):
            print("missing part", part["mesh"])
            continue
        for o in import_gltf(part["mesh"]):
            o.parent = None
            o.location = part["pivot"]
            o.rotation_euler = (0.0, 0.0, 0.0)
            o.parent = root
            obs.append(o)
    root.location = (x, y, 0.0)
    root.rotation_euler = (0.0, 0.0, math.radians(yaw))
    return root, obs


def place_building(mesh, x=0.0, y=0.0):
    obs = import_gltf(mesh)
    for ob in obs:
        if ob.parent is None:
            ob.location.x += x
            ob.location.y += y
    meta = json.load(open(os.path.join(V.MESHES, mesh + ".json")))
    if mesh == "SM_Windmill" and "hub" in meta:
        hx, hy, hz = meta["hub"]
        for s in import_gltf("SM_Windmill_Sails"):
            s.location = (x + hx, y + hy, hz)
            s.rotation_euler = (0.0, math.radians(45.0), 0.0)     # the X of the reference picture
            obs.append(s)
    obs += place_props(mesh, x, y, 0.0, 1.0)
    return obs


def world_points(obs=None):
    bpy.context.view_layer.update()
    if obs is None:
        obs = [o for o in bpy.context.scene.objects if o.type == "MESH" and not o.hide_render and not o.get("catcher")]
    pts = []
    for ob in obs:
        n = len(ob.data.vertices)
        if not n:
            continue
        mw = np.array(ob.matrix_world)
        co = np.empty(n * 3, np.float32)
        ob.data.vertices.foreach_get("co", co)
        pts.append(co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3])
    return np.concatenate(pts)


# ------------------------------------------------------------------------------------------------------- studio

def sun(name, az, el, energy, color, angle, shadow=True):
    """az: where the light comes FROM, degrees clockwise from the south (0 = from the camera side, + = from the right)."""
    lt = bpy.data.lights.new(name, "SUN")
    lt.energy = energy
    lt.color = color
    lt.angle = math.radians(angle)
    lt.use_shadow = shadow
    ob = bpy.data.objects.new(name, lt)
    bpy.context.scene.collection.objects.link(ob)
    a, e = math.radians(az), math.radians(el)
    ob.location = (math.sin(a) * math.cos(e) * 50, -math.cos(a) * math.cos(e) * 50, math.sin(e) * 50)
    V.look_at(ob, (0, 0, 0))
    return ob


def studio(floor_z=0.0):
    scene = bpy.context.scene
    world = bpy.data.worlds.new("Studio")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.62, 0.64, 0.68, 1.0)     # soft neutral-cool ambient
    bg.inputs["Strength"].default_value = 0.55
    scene.world = world
    sun("Key", az=40.0, el=45.0, energy=3.6, color=(1.0, 0.9, 0.77), angle=10.0)           # warm golden key
    sun("Fill", az=-65.0, el=22.0, energy=0.9, color=(0.84, 0.90, 1.0), angle=40.0, shadow=False)   # cool soft fill
    sun("Rim", az=-155.0, el=35.0, energy=2.2, color=(1.0, 0.94, 0.85), angle=6.0, shadow=False)    # subtle rim
    bpy.ops.mesh.primitive_plane_add(size=600, location=(0, 0, floor_z - 0.002))
    g = bpy.context.active_object
    g.name = "Catcher"
    g["catcher"] = True
    g.is_shadow_catcher = True
    m = bpy.data.materials.new("Catcher")
    g.data.materials.append(m)
    scene.render.film_transparent = True
    scene.render.engine = "CYCLES"
    scene.cycles.samples = SAMPLES
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 4
    scene.cycles.device = "CPU"
    if GPU:
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            prefs.compute_device_type = "METAL"
            prefs.get_devices()
            for dev in prefs.devices:
                dev.use = True
            scene.cycles.device = "GPU"
        except Exception as e:
            print("no GPU:", e)
    scene.view_settings.view_transform = "AgX"
    for look in ("AgX - Medium High Contrast", "Medium High Contrast"):
        try:
            scene.view_settings.look = look
            break
        except Exception:
            continue
    scene.view_settings.exposure = 0.0
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"


def frame(pts, az, el, res, fill_w, fill_h, lens):
    """Aim a perspective camera from (az, el) at the points and set its distance and lens shift so their projection is
    centred and fills fill_w x fill_h of the frame (whichever is tighter)."""
    scene = bpy.context.scene
    cam = bpy.data.objects.get("StyleCam")
    if cam is None:
        cam = bpy.data.objects.new("StyleCam", bpy.data.cameras.new("StyleCam"))
        scene.collection.objects.link(cam)
    scene.camera = cam
    cd = cam.data
    cd.lens = lens
    cd.sensor_fit = "HORIZONTAL"
    cd.sensor_width = 36.0
    cd.clip_start = 0.05
    cd.clip_end = 5000.0
    cd.shift_x = cd.shift_y = 0.0
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    W = 36.0 / lens
    H = W * res[1] / res[0]
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    c = (lo + hi) / 2.0
    a, e = math.radians(az), math.radians(el)
    dirv = np.array([math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)])
    d = float(np.linalg.norm(hi - lo)) * lens / 36.0 * 1.5 + 1.0
    for _ in range(12):
        cam.location = tuple(c + dirv * d)
        V.look_at(cam, tuple(c))
        bpy.context.view_layer.update()
        M = np.array(cam.matrix_world.inverted())
        pc = pts @ M[:3, :3].T + M[:3, 3]
        z = np.maximum(-pc[:, 2], 1e-3)
        tx, ty = pc[:, 0] / z, pc[:, 1] / z
        k = max((tx.max() - tx.min()) / (W * fill_w), (ty.max() - ty.min()) / (H * fill_h))
        if abs(k - 1.0) < 0.002:
            break
        d *= k
    largest = W if res[0] >= res[1] else H
    cd.shift_x = float((tx.max() + tx.min()) / 2.0 / largest)
    cd.shift_y = float((ty.max() + ty.min()) / 2.0 / largest)
    return cam


def composite(src, dst):
    """Lay the transparent render (with its shadow-catcher alpha) over the studio gradient."""
    img = bpy.data.images.load(src)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    t = np.linspace(0.0, 1.0, h)[:, None, None]                  # row 0 is the bottom
    bg = BG_BOTTOM[None, None, :] * (1 - t) + BG_TOP[None, None, :] * t
    # a very light vignette so the subject sits in a soft pool of light
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    bg = bg * (1.0 - 0.06 * np.clip(r - 0.4, 0, 1))[:, :, None]
    a = px[:, :, 3:4]
    out = np.ones((h, w, 4), np.float32)
    out[:, :, :3] = px[:, :, :3] * a + bg * (1.0 - a)
    o = bpy.data.images.new("out", w, h, alpha=False)
    o.pixels.foreach_set(out.ravel())
    o.filepath_raw = dst
    o.file_format = "PNG"
    o.save()
    bpy.data.images.remove(o)
    bpy.data.images.remove(img)
    print("wrote", dst)


def shoot(dst, az, el, res, fill_w, fill_h, lens, pts=None):
    if pts is None:
        pts = world_points()
    frame(pts, az, el, res, fill_w, fill_h, lens)
    tmp = os.path.join(TMP, os.path.basename(dst))
    bpy.context.scene.render.filepath = tmp
    bpy.ops.render.render(write_still=True)
    composite(tmp, dst)


def fresh(floor_z=0.0):
    V.reset_scene()
    _prop_lib.clear()
    studio(floor_z)


# ------------------------------------------------------------------------------------------------------- jobs

def render_characters():
    for rig, fname, _ in CHARACTERS:
        if not want(fname, "chars"):
            continue
        fresh()
        root, obs = place_character(rig)
        for view, yaw in CHAR_VIEWS:
            root.rotation_euler = (0.0, 0.0, math.radians(yaw))
            shoot(os.path.join(OUT, "%s_%s.png" % (fname, view)), az=0.0, el=8.0, res=(1200, 1200),
                  fill_w=0.86, fill_h=0.80, lens=85.0, pts=world_points(obs))


def render_buildings():
    for mesh, fname, _ in BUILDINGS:
        if not want(fname, mesh, "buildings"):
            continue
        fresh()
        obs = place_building(mesh)
        pts = world_points(obs)
        bpy.data.objects["Catcher"].location.z = float(pts[:, 2].min()) - 0.002
        shoot(os.path.join(OUT, fname + "_three_quarter.png"), az=-35.0, el=35.0, res=(1600, 1200),
              fill_w=0.86, fill_h=0.82, lens=60.0, pts=pts)
        shoot(os.path.join(OUT, fname + "_front.png"), az=0.0, el=12.0, res=(1600, 1200),
              fill_w=0.86, fill_h=0.82, lens=60.0, pts=pts)


def render_character_sheet():
    fresh()
    x, every = 0.0, []
    for rig, _, _ in CHARACTERS:
        _, obs = place_character(rig, x=x, yaw=35.0)
        every += obs
        x += 1.6
    shoot(os.path.join(OUT, "Characters_sheet.png"), az=0.0, el=8.0, res=(2400, 1200), fill_w=0.86, fill_h=0.80,
          lens=85.0, pts=world_points(every))


def render_nature_sheet():
    fresh()
    every = []
    # back row: the tall trees
    x = 0.0
    for t in TREES:
        got = import_gltf(t + "_Trunk") + import_gltf(t + "_Leaves")
        lo, hi = world_points(got).min(axis=0), world_points(got).max(axis=0)
        for o in got:
            o.location.x += x - lo[0]
        x += (hi[0] - lo[0]) + 1.5
        every += got
    row_w = x - 1.5
    # front row: bushes and rocks, centred under the trees
    smalls = []
    for n in BUSHES + ROCKS:
        got = import_gltf(n)
        smalls.append(got)
    widths = [np.ptp(world_points(g)[:, 0]) for g in smalls]
    gap = 1.2
    x = row_w / 2.0 - (sum(widths) + gap * (len(widths) - 1)) / 2.0
    for g, wdt in zip(smalls, widths):
        lo = world_points(g).min(axis=0)
        for o in g:
            o.location.x += x - lo[0]
            o.location.y -= 11.0
        x += wdt + gap
        every += g
    shoot(os.path.join(OUT, "Nature_sheet.png"), az=-12.0, el=20.0, res=(3200, 1800), fill_w=0.92, fill_h=0.88,
          lens=60.0, pts=world_points(every))


def srgb_lin(c):
    c = np.asarray(c, float)
    return tuple(np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4))


def emission_mat(name, color=None, image=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 1.0
    if image is not None:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = image
        tex.interpolation = "Linear"
        nt.links.new(tex.outputs["Color"], em.inputs["Color"])
    else:
        em.inputs["Color"].default_value = (*srgb_lin(color), 1.0)
    nt.links.new(em.outputs[0], out.inputs[0])
    return m


def render_buildings_sheet():
    """A labelled grid of the three-quarter renders, laid out as image cards under an orthographic camera."""
    V.reset_scene()
    scene = bpy.context.scene
    cols = 4
    cw, ch, lab, pad = 4.0, 3.0, 0.42, 0.18                         # cell, label strip, padding (scene units)
    items = [(f, l) for _, f, l in BUILDINGS if os.path.exists(os.path.join(OUT, f + "_three_quarter.png"))]
    rows = int(math.ceil(len(items) / cols))
    tw, th = cols * (cw + pad) + pad, rows * (ch + lab + pad) + pad
    lab_mat = emission_mat("Label", LABEL_COL)
    for i, (fname, label) in enumerate(items):
        r, c = divmod(i, cols)
        x0 = pad + c * (cw + pad) - tw / 2
        ytop = th / 2 - pad - r * (ch + lab + pad)
        img = bpy.data.images.load(os.path.join(OUT, fname + "_three_quarter.png"))
        bpy.ops.mesh.primitive_plane_add(size=1.0, location=(x0 + cw / 2, ytop - ch / 2, 0.0))
        p = bpy.context.active_object
        p.scale = (cw, ch, 1.0)
        p.data.materials.append(emission_mat("Card_" + fname, image=img))
        cu = bpy.data.curves.new("T_" + fname, "FONT")
        cu.body = label
        cu.align_x = "CENTER"
        cu.align_y = "CENTER"
        cu.size = 0.24
        t = bpy.data.objects.new("T_" + fname, cu)
        scene.collection.objects.link(t)
        t.location = (x0 + cw / 2, ytop - ch - lab / 2 + 0.02, 0.01)
        t.data.materials.append(lab_mat)
    world = bpy.data.worlds.new("Sheet")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (*srgb_lin(SHEET_BG), 1.0)
    scene.world = world
    cam = bpy.data.objects.new("SheetCam", bpy.data.cameras.new("SheetCam"))
    scene.collection.objects.link(cam)
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = tw
    cam.location = (0, 0, 10)
    scene.camera = cam
    px = 820                                                         # pixels per cell width
    scene.render.resolution_x = int(round(tw / cw * px))
    scene.render.resolution_y = int(round(th / cw * px))
    scene.render.resolution_percentage = 100
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 16
    scene.cycles.use_denoising = False
    scene.cycles.max_bounces = 0
    scene.cycles.filter_width = 1.0
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.filepath = os.path.join(OUT, "Buildings_sheet.png")
    bpy.ops.render.render(write_still=True)
    print("wrote", scene.render.filepath)


def main():
    os.makedirs(OUT, exist_ok=True)
    render_characters()
    render_buildings()
    if want("sheets", "Characters_sheet"):
        render_character_sheet()
    if want("sheets", "Nature_sheet", "nature"):
        render_nature_sheet()
    if want("sheets", "Buildings_sheet"):
        render_buildings_sheet()
    shutil.rmtree(TMP, ignore_errors=True)


main()
