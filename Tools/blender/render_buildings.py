"""Reference renders of every building on flat grass, at the size it stands in the village, King David beside it for
scale. For planning buildings and a quick look-and-feel check.

    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python Tools/blender/render_buildings.py [-- NAME ...]

Writes References/Buildings/<Name>.png (three-quarter view from the front left, the village's own angle),
<Name>_front.png and Lineup.png (all of them side by side, the same scale). BUILD_CPU=1 renders on the CPU.
"""
import json
import math
import os
import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import voxlib as V

ROOT = V.ROOT
OUT = os.path.join(ROOT, "References", "Buildings")
LAYOUT = json.load(open(os.path.join(ROOT, "SourceArt", "layout.json")))

# mesh -> what it is called in the game (the overview's names)
# (the set the Flatlands shows: the barracks, archery range and farm are the remakes with their yards; renders of the
# village's older versions are in References/Buildings/Old)
BUILDINGS = [
    ("SM_Castle", "Castle"),
    ("SM_TownHall", "Town Hall"),
    ("SM_BarracksYard", "Barracks"),
    ("SM_ArcheryHall", "Archery Range"),
    ("SM_WatchTower", "Watch Tower"),
    ("SM_MineCliff", "Gold Mine"),
    ("SM_Farmstead", "Farm"),
    ("SM_Bridge", "Bridge"),
]
KING = ["Body", "Head", "ArmL", "ArmR", "LegL", "LegR", "Cape", "Sword", "Sheath"]
ONLY = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def village_scale(mesh):
    for it in LAYOUT["instances"]:
        if it["mesh"] == mesh:
            return it.get("scale", 1.0)
    return 1.0


def import_gltf(name):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(V.MESHES, name + ".gltf"))
    obs = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    for ob in obs:
        # the importer makes plain materials named after the slots: swap in the textured preview materials
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


def place_props(mesh, x, y, z, s):
    """The instances an asset asks for in its sidecar JSON (dummies, wheat, sheep): linked copies at their places."""
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


def bounds(obs):
    pts = []
    for ob in obs:
        mw = np.array(ob.matrix_world)
        co = np.zeros(len(ob.data.vertices) * 3, np.float32)
        ob.data.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]
        pts.append(co)
    pts = np.concatenate(pts)
    return pts.min(axis=0), pts.max(axis=0)


def ground(w, d):
    """Flat grass of 0.5 m blocks, one block deep, top at z = 0."""
    nx, ny = int(math.ceil(w / 0.5)), int(math.ceil(d / 0.5))
    g = V.Vox(nx, ny, 2, voxel=0.5, origin=(nx // 2, ny // 2, 2), name="ground")
    g.box(0, 0, 0, nx, ny, 1, "dirt")
    g.box(0, 0, 1, nx, ny, 2, "grass")
    ob = g.to_object("Ground")
    attr = ob.data.color_attributes[0].name if ob.data.color_attributes else "Col"
    for m in ob.data.materials:
        for n in m.node_tree.nodes:
            if n.type == "VERTEX_COLOR":
                n.layer_name = attr
    return ob


def place_king(x, y, yaw=0.0):
    obs = []
    root = bpy.data.objects.new("King", None)
    bpy.context.scene.collection.objects.link(root)
    for part in KING:
        name = "SM_KingB_" + part
        if not os.path.exists(os.path.join(V.MESHES, name + ".gltf")):
            continue
        meta = json.load(open(os.path.join(V.MESHES, name + ".json")))
        got = import_gltf(name)
        for o in got:
            o.location = meta.get("pivot", (0, 0, 0))          # each part is modelled about its joint
            o.parent = root
        obs += got
    root.location = (x, y, 0.0)
    root.rotation_euler = (0, 0, math.radians(yaw))
    return obs


def setup(engine_cpu):
    scene = bpy.context.scene
    world = bpy.data.worlds.new("Sky")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.62, 0.74, 0.88, 1.0)
    bg.inputs["Strength"].default_value = 0.9
    scene.world = world
    V.setup_light(scene, sun_az=-35.0, sun_el=42.0, strength=4.5, sky=0.9)
    if engine_cpu:
        scene.cycles.device = "CPU"


def shot(path, lo, hi, az, el, res=(1600, 1000), lens=50.0, samples=40, tight=1.0):
    c = (lo + hi) / 2.0
    size = hi - lo
    target = (float(c[0]), float(c[1]), float(min(size[2] * 0.42, 6.0)))
    # far enough that the whole footprint and height fit the frame, with a margin
    span = max(size[0] * 1.15, size[1] * 0.9, size[2] * 1.6) + 3.0
    dist = span * lens / 36.0 * 1.05 * tight
    V.render(path, target=target, az=az, el=el, dist=dist, lens=lens, res=res, samples=samples, ground=False,
             sun_az=-35.0, sun_el=42.0)
    if os.environ.get("BUILD_CPU"):
        bpy.context.scene.cycles.device = "CPU"


def main():
    os.makedirs(OUT, exist_ok=True)
    cpu = bool(os.environ.get("BUILD_CPU"))
    todo = [b for b in BUILDINGS if not ONLY or b[0] in ONLY or b[1] in ONLY]
    lineup = not ONLY or "LINEUP" in ONLY
    # one building at a time
    for mesh, title in todo:
        V.reset_scene()
        setup(cpu)
        obs = import_gltf(mesh)
        s = village_scale(mesh)
        for ob in obs:
            if ob.parent is None:
                ob.scale = (s, s, s)
                ob.location.z = -0.01                          # the underside of its floor under the grass, not on it
        place_props(mesh, 0.0, 0.0, -0.01, s)
        bpy.context.view_layer.update()
        lo, hi = bounds(obs)
        lo[2] = max(lo[2], 0.0)
        ground(max(hi[0] - lo[0], 10) + 40, max(hi[1] - lo[1], 10) + 40)
        place_king(hi[0] + 1.6, lo[1] - 0.6, yaw=-20.0)
        bpy.context.view_layer.update()
        lo2, hi2 = bounds(obs)
        lo2[2] = 0.0
        hi2[0] += 2.4                                   # keep the king in the frame
        base = os.path.join(OUT, title.replace(" ", ""))
        shot(base + ".png", lo2, hi2, az=-28.0, el=28.0)
        shot(base + "_front.png", lo2, hi2, az=0.0, el=12.0)
        print("building %s: scale %.3f, footprint %.1f x %.1f m, height %.1f m" % (
            title, s, hi[0] - lo[0], hi[1] - lo[1], hi[2]))

    if not lineup:
        return
    # the lineup: all of them in a row on one field, fronts to the camera, the same scale
    V.reset_scene()
    _prop_lib.clear()                                   # the scene reset deleted the prop originals
    setup(cpu)
    x = 0.0
    every = []
    for mesh, title in BUILDINGS:
        obs = import_gltf(mesh)
        s = village_scale(mesh)
        tops = [o for o in obs if o.parent is None]
        for ob in tops:
            ob.scale = (s, s, s)
            ob.location.z = -0.01
        bpy.context.view_layer.update()
        lo, hi = bounds(obs)
        for ob in tops:
            ob.location.x += x - lo[0]
        place_props(mesh, x - lo[0], 0.0, -0.01, s)
        x += (hi[0] - lo[0]) + 3.0
        every += obs
    place_king(x - 1.0, -4.0)
    bpy.context.view_layer.update()
    lo, hi = bounds(every)
    ground(hi[0] - lo[0] + 60, 60).location.x = (lo[0] + hi[0]) / 2.0
    lo[2] = 0.0
    shot(os.path.join(OUT, "Lineup.png"), lo, hi, az=-10.0, el=16.0, res=(3200, 1100), lens=60.0, samples=48, tight=0.93)


main()
