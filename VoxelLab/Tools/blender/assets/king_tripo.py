"""King David from the owner's own mesh (References/king.glb), painted from his picture by Tools/blender/king_paint.py.

    ../Tools/.venv/bin/python Tools/blender/king_paint.py                 (first: writes Saved/king/mesh.npz + colors.npz)
    Blender -b --factory-startup --python Tools/blender/assets/king_tripo.py -- [--no-render]

The mesh is kept exactly as modelled and flat-shaded, as it looks in the modelling tool. It already comes in separate
pieces, which become the rigid parts the engine swings: Body, Head, ArmL, ArmR (with the sword), LegL, LegR, Cape.
Exports SM_KingT_<Part> (origin at the joint) and SM_KingT.json.
"""
import json
import math
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bpy
import numpy as np
import voxlib as V

HEIGHT = 1.7
SRC = os.path.join(V.ROOT, "Saved", "king")


def load():
    m = np.load(os.path.join(SRC, "mesh.npz"))
    c = np.load(os.path.join(SRC, "colors.npz"))
    verts, tris = m["V"] * HEIGHT, m["I"]
    cols = c["colors"].astype(np.float32) / 255.0
    return verts, tris, cols, float(c["az"]), float(c["el"]), c["part"]


def components(nv, tris):
    parent = np.arange(nv)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for t in tris:
        a, b, c = find(t[0]), find(t[1]), find(t[2])
        parent[b] = a
        parent[c] = a
    roots = np.array([find(i) for i in range(nv)])
    return roots[tris[:, 0]]


def split(verts, tris):
    """Which part each triangle belongs to, from the mesh's own separate pieces."""
    comp = components(len(verts), tris)
    part = np.empty(len(tris), dtype=object)
    H = HEIGHT
    for r in np.unique(comp):
        f = comp == r
        vv = verts[np.unique(tris[f])]
        lo, hi, n = vv.min(axis=0) / H, vv.max(axis=0) / H, int(f.sum())
        cx, cz = (lo[0] + hi[0]) / 2.0, (lo[2] + hi[2]) / 2.0
        if lo[2] > 0.72:
            name = "Head"
        elif n > 2000 and lo[2] < 0.05 and hi[0] - lo[0] > 0.6:
            name = "Cape"
        elif hi[2] < 0.30 and n > 200:
            name = "LegR" if cx < 0 else "LegL"
        elif n > 500 and hi[0] < -0.05 and lo[1] < -0.2:
            name = "ArmR"                                    # the sword, in his right hand
        elif 0.30 < cz < 0.56 and abs(cx) > 0.14 and hi[2] < 0.70 and lo[2] > 0.28:
            name = "ArmR" if cx < 0 else "ArmL"              # forearms and hands
        else:
            name = "Body"
        part[f] = name
    return part


# joints, as fractions of his height (x right of the viewer = his left, y back, z up)
PIVOT = {"Body": (0.0, 0.02, 0.32), "Head": (0.0, 0.06, 0.76), "ArmL": (0.215, 0.02, 0.655), "ArmR": (-0.17, 0.02, 0.655),
         "LegL": (0.125, -0.01, 0.275), "LegR": (-0.075, -0.01, 0.275), "Cape": (0.0, 0.16, 0.56)}


def make(name, verts, tris, cols, pivot):
    F = len(tris)
    co = (verts[tris].reshape(-1, 3) - np.array(pivot)).astype(np.float32)        # every face its own corners: flat
    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(F * 3)
    mesh.vertices.foreach_set("co", co.reshape(-1))
    mesh.loops.add(F * 3)
    mesh.loops.foreach_set("vertex_index", np.arange(F * 3, dtype=np.int32))
    mesh.polygons.add(F)
    mesh.polygons.foreach_set("loop_start", np.arange(0, F * 3, 3, dtype=np.int32))
    try:
        mesh.polygons.foreach_set("loop_total", np.full(F, 3, dtype=np.int32))
    except Exception:
        pass
    uv = mesh.uv_layers.new(name="UVMap")
    uv.data.foreach_set("uv", (co[:, [0, 2]] * 0.25).reshape(-1))
    attr = mesh.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="CORNER")
    rgba = np.ones((F * 3, 4), np.float32)
    rgba[:, :3] = np.repeat(V.srgb_to_linear(cols), 3, axis=0)
    attr.data.foreach_set("color", rgba.reshape(-1))
    mesh.color_attributes.active_color = attr
    mesh.color_attributes.render_color_index = 0
    mesh.materials.append(V.material("paint"))
    mesh.update()
    ob = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = pivot
    ob["voxel_faces"] = F
    ob["lights"] = "[]"
    return ob


def build():
    verts, tris, cols, az, el, part = load()                 # the parts were sorted out by king_paint.py
    obs = {}
    for name in ("Body", "Head", "ArmL", "ArmR", "LegL", "LegR", "Cape"):
        f = part == name
        if not f.any():
            print("no faces for", name)
            continue
        pivot = tuple(p * HEIGHT for p in PIVOT[name])
        obs[name] = make("SM_KingT_" + name, verts, tris[f], cols[f], pivot)
        print("%-5s %5d faces, joint (%.2f, %.2f, %.2f)" % (name, int(f.sum()), *pivot))
    return obs, az, el


def studio(scene):
    """Dark grey backdrop, warm key from the front-left, rim light from behind: the reference picture's light."""
    world = bpy.data.worlds.new("W")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.06, 0.06, 0.065, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    for nm, loc, energy, color, size in (("Key", (-3.2, -4.0, 3.6), 260, (1.0, 0.93, 0.82), 2.0), ("Rim", (2.6, 3.4, 3.2), 220, (0.9, 0.95, 1.0), 1.5),
                                         ("Fill", (3.5, -3.0, 1.0), 60, (0.8, 0.85, 1.0), 3.0)):
        l = bpy.data.lights.new(nm, "AREA")
        l.energy, l.color, l.size = energy, color, size
        o = bpy.data.objects.new("Sun" if nm == "Key" else nm, l)
        scene.collection.objects.link(o)
        o.location = loc
        V.look_at(o, (0, 0, 0.9))
    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0))
    g = bpy.context.active_object
    g.name = "PreviewGround"
    gm = bpy.data.materials.new("floor")
    gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.05, 0.05, 0.055, 1)
    g.data.materials.append(gm)


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    scene = V.reset_scene()
    obs, az, el = build()
    info = dict(height=HEIGHT, radius=0.45, stride=1.35, parts={})
    for name, ob in obs.items():
        loc = tuple(ob.location)
        ob.location = (0, 0, 0)
        V.export_gltf(ob, collision="none")
        ob.location = loc
        info["parts"][name] = dict(mesh=ob.name, pivot=[round(v, 4) for v in loc])
    with open(os.path.join(V.MESHES, "SM_KingT.json"), "w") as f:
        json.dump(info, f, indent=1)
    if "--no-render" in args:
        return
    studio(scene)
    kw = dict(lens=70, res=(1005, 1565), samples=64, ground=False)
    V.render(os.path.join(V.PREVIEWS, "king_t_front.png"), target=(0, 0, 0.86), az=az, el=el, dist=5.6, **kw)
    V.render(os.path.join(V.PREVIEWS, "king_t_back.png"), target=(0, 0, 0.86), az=az + 180, el=12, dist=5.6, **kw)
    V.render(os.path.join(V.PREVIEWS, "king_t_left.png"), target=(0, 0, 0.86), az=60, el=8, dist=5.6, **kw)
    # a walking pose, to see the joints
    for name, deg in (("LegL", 32), ("LegR", -32), ("ArmL", -24), ("ArmR", 12), ("Cape", -16)):
        if name in obs:
            obs[name].rotation_euler[0] = math.radians(deg)
    V.render(os.path.join(V.PREVIEWS, "king_t_walk.png"), target=(0, 0, 0.86), az=-70, el=6, dist=5.6, **kw)


main()
