"""Render setup and the hi-res -> sprite-cell reduction. Runs inside Blender (bpy + numpy + OpenImageIO)."""

import math
import os

import bpy
import numpy as np
from mathutils import Vector

import srmats

FACINGS = ["S", "SW", "W", "NW", "N", "NE", "E", "SE"]
# Rotation of the model about +Z. The model faces -Y, the camera sits on the -Y side, so 0 degrees = S
# (facing the camera) and +90 degrees turns it to face +X = screen right = E.
FACING_ANGLE = {"S": 0, "SE": 45, "E": 90, "NE": 135, "N": 180, "NW": -135, "W": -90, "SW": -45}

DEFAULTS = dict(elev=30.0, cm_per_px=1.75, cell=160, pivot=(80, 118), ss=4, samples=24)


def setup(scene, elev=30.0, cm_per_px=1.75, cell=160, pivot=(80, 118), ss=4, samples=24):
    """Camera, light rig, EEVEE settings and passes. Lights are fixed to the camera, not the character."""
    for name in ("SR_Camera", "SR_Key", "SR_Fill", "SR_Rim"):
        ob = bpy.data.objects.get(name)
        if ob:
            bpy.data.objects.remove(ob, do_unlink=True)
    col = scene.collection
    e = math.radians(elev)
    view = Vector((0.0, math.cos(e), -math.sin(e)))          # direction the camera looks in
    up = Vector((0.0, math.sin(e), math.cos(e)))             # screen up in world space
    right = Vector((1.0, 0.0, 0.0))
    px = cm_per_px / 100.0
    # world origin (the feet pivot) must land on pixel `pivot` (from the top-left of the cell)
    centre = right * ((cell / 2 - pivot[0]) * px) + up * ((pivot[1] - cell / 2) * px)

    cam_d = bpy.data.cameras.new("SR_Camera")
    cam_d.type = "ORTHO"
    cam_d.ortho_scale = cell * px
    cam_d.clip_start, cam_d.clip_end = 0.1, 30.0
    cam = bpy.data.objects.new("SR_Camera", cam_d)
    col.objects.link(cam)
    cam.location = centre - view * 8.0
    cam.rotation_euler = (-view).to_track_quat("Z", "Y").to_euler()
    scene.camera = cam

    def sun(name, travel, energy, color, shadow, angle):
        d = bpy.data.lights.new(name, "SUN")
        d.energy, d.color, d.angle = energy, color, math.radians(angle)
        d.use_shadow = shadow
        if hasattr(d, "use_shadow_jitter"):
            d.use_shadow_jitter = True
        o = bpy.data.objects.new(name, d)
        col.objects.link(o)
        o.rotation_euler = (-Vector(travel).normalized()).to_track_quat("Z", "Y").to_euler()
        return o

    # Key: warm, from the top-left and a little toward the camera. Fill: cool, low, from the right.
    # Rim: from behind on the right, so the shadow side keeps a lit edge.
    sun("SR_Key", (0.50, 0.62, -0.60), 3.2, (1.0, 0.93, 0.82), True, 6.0)
    sun("SR_Fill", (-0.75, 0.55, -0.25), 0.40, (0.62, 0.72, 1.0), False, 20.0)
    sun("SR_Rim", (-0.55, -0.62, -0.56), 1.1, (1.0, 0.9, 0.75), False, 10.0)

    world = scene.world or bpy.data.worlds.new("SR_World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0.55, 0.62, 0.80, 1.0)
    bg.inputs[1].default_value = 0.26

    r = scene.render
    r.engine = "BLENDER_EEVEE"
    r.resolution_x = r.resolution_y = cell * ss
    r.resolution_percentage = 100
    r.film_transparent = True
    r.filter_size = 0.8
    ee = scene.eevee
    ee.taa_render_samples = samples
    ee.use_shadows = True
    ee.use_raytracing = False
    for attr, val in (("shadow_ray_count", 2), ("shadow_step_count", 6)):
        if hasattr(ee, attr):
            setattr(ee, attr, val)
    scene.view_settings.view_transform = "Standard"
    scene["sr_render"] = dict(elev=elev, cm_per_px=cm_per_px, cell=cell, pivot=list(pivot), ss=ss)
    return cam


def setup_passes(scene):
    vl = scene.view_layers[0]
    vl.use_pass_combined = True
    vl.use_pass_z = True
    vl.use_pass_normal = True
    vl.use_pass_ambient_occlusion = True
    if hasattr(vl.eevee, "ambient_occlusion_distance"):
        vl.eevee.ambient_occlusion_distance = 0.22
    if "matid" not in vl.aovs:
        a = vl.aovs.add()
        a.name = "matid"
        a.type = "COLOR"
    s = scene.render.image_settings
    s.media_type = "MULTI_LAYER_IMAGE"
    s.color_depth = "32"
    s.exr_codec = "ZIP"


def set_clay(on):
    """Swap every SR_ material between its Principled look and a white clay + material-id AOV.

    Materials with a 'tex' entry get a cell pattern multiplied into the clay albedo (scale armour). It is
    driven by Generated coordinates, i.e. rest-pose positions, so it sticks to the surface when the rig moves.
    """
    mesh = next((o for o in bpy.data.objects if o.type == "MESH"), None)
    bb = [Vector(c) for c in mesh.bound_box] if mesh else [Vector((0, 0, 0)), Vector((1, 1, 1))]
    lo = Vector((min(c.x for c in bb), min(c.y for c in bb), min(c.z for c in bb)))
    hi = Vector((max(c.x for c in bb), max(c.y for c in bb), max(c.z for c in bb)))
    for m in bpy.data.materials:
        if not m.name.startswith("SR_"):
            continue
        d = srmats.BY_NAME[m.name[3:]]
        nt = m.node_tree
        out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
        clay = nt.nodes.get("SR_Clay")
        if clay is None:
            clay = nt.nodes.new("ShaderNodeBsdfDiffuse")
            clay.name = "SR_Clay"
            clay.inputs["Color"].default_value = (0.8, 0.8, 0.8, 1.0)
            aov = nt.nodes.new("ShaderNodeOutputAOV")
            aov.name = "SR_MatId"
            aov.aov_name = "matid"
            aov.inputs["Color"].default_value = (*srmats.id_color(int(m["sr_id"])), 1.0)
            if d["tex"]:
                t = d["tex"]
                tc = nt.nodes.new("ShaderNodeTexCoord")
                mp = nt.nodes.new("ShaderNodeMapping")
                mp.inputs["Location"].default_value = lo
                mp.inputs["Scale"].default_value = hi - lo
                nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
                edge = nt.nodes.new("ShaderNodeTexVoronoi")
                edge.feature = "DISTANCE_TO_EDGE"
                edge.inputs["Scale"].default_value = 1.0 / t["size"]
                cellv = nt.nodes.new("ShaderNodeTexVoronoi")
                cellv.feature = "F1"
                cellv.inputs["Scale"].default_value = 1.0 / t["size"]
                nt.links.new(mp.outputs["Vector"], edge.inputs["Vector"])
                nt.links.new(mp.outputs["Vector"], cellv.inputs["Vector"])
                r1 = nt.nodes.new("ShaderNodeMapRange")
                r1.inputs["From Min"].default_value, r1.inputs["From Max"].default_value = 0.0, 0.16
                r1.inputs["To Min"].default_value, r1.inputs["To Max"].default_value = 1.0 - t["edge"], 1.0
                nt.links.new(edge.outputs["Distance"], r1.inputs["Value"])
                bw = nt.nodes.new("ShaderNodeRGBToBW")
                nt.links.new(cellv.outputs["Color"], bw.inputs["Color"])
                r2 = nt.nodes.new("ShaderNodeMapRange")
                r2.inputs["To Min"].default_value, r2.inputs["To Max"].default_value = 1.0 - t["cell"], 1.0
                nt.links.new(bw.outputs["Val"], r2.inputs["Value"])
                mul = nt.nodes.new("ShaderNodeMath")
                mul.operation = "MULTIPLY"
                nt.links.new(r1.outputs["Result"], mul.inputs[0])
                nt.links.new(r2.outputs["Result"], mul.inputs[1])
                mul2 = nt.nodes.new("ShaderNodeMath")
                mul2.operation = "MULTIPLY"
                mul2.inputs[1].default_value = 0.8
                nt.links.new(mul.outputs[0], mul2.inputs[0])
                nt.links.new(mul2.outputs[0], clay.inputs["Color"])
        src = clay if on else nt.nodes.get("Principled BSDF")
        nt.links.new(src.outputs[0], out.inputs["Surface"])


def read_exr(path):
    import OpenImageIO as oiio
    inp = oiio.ImageInput.open(path)
    out = {}
    i = 0
    while inp.seek_subimage(i, 0):
        spec = inp.spec()
        name = spec.channelnames[0].split(".")[-2]
        out[name] = np.asarray(inp.read_image(i, 0, 0, spec.nchannels, "float"))
        i += 1
    inp.close()
    return out


def camera_axes(cam):
    m = cam.matrix_world.to_3x3()
    return np.array([list(m.col[0]), list(m.col[1]), list(m.col[2])], dtype=np.float32)   # right, up, back


def reduce_cell(p, ss, cam_axes):
    """Collapse a supersampled render to one sprite cell.

    Each output pixel takes ONE material (the most common among its fully-covered sub-samples; wire-like
    'thin' materials win at a lower count) and the mean lighting / normal / depth of that material's
    sub-samples only, so nothing is ever blended across a material edge or with the background.
    """
    comb = p["Combined"]
    H, W = comb.shape[:2]
    h, w = H // ss, W // ss
    alpha = comb[..., 3]
    lum = comb[..., 0] * 0.3 + comb[..., 1] * 0.6 + comb[..., 2] * 0.1
    mid = p["matid"][..., :3] * 3.0
    q = np.rint(mid)
    pure = (np.abs(mid - q).max(-1) < 0.03) & (alpha > 0.995)
    code = (q[..., 0] + 4 * q[..., 1] + 16 * q[..., 2]).astype(np.int32) - 1
    code_loose = np.where(alpha > 0.5, code, -1)
    code = np.where(pure, code, -1)

    def blocks(a):
        return a.reshape(h, ss, w, ss, *a.shape[2:]).swapaxes(1, 2).reshape(h, w, ss * ss, *a.shape[2:])

    cb, cl = blocks(code), blocks(code_loose)
    nmat = len(srmats.MATERIALS)
    counts = np.stack([(cb == k).sum(-1) for k in range(nmat)], -1)
    counts_loose = np.stack([(cl == k).sum(-1) for k in range(nmat)], -1)
    cover = blocks(alpha).mean(-1)
    thin = np.array([m["thin"] for m in srmats.MATERIALS])
    n = ss * ss
    best = counts.argmax(-1)
    none_pure = counts.max(-1) == 0
    best = np.where(none_pure, counts_loose.argmax(-1), best)
    tc = np.where(thin[None, None, :], counts, 0)
    thin_best = tc.argmax(-1)
    thin_win = tc.max(-1) >= 0.35 * n
    best = np.where(thin_win, thin_best, best)
    opaque = ((cover >= 0.5) & ((counts.max(-1) > 0) | (counts_loose.max(-1) > 0))) | thin_win
    ident = np.where(opaque, best, 255).astype(np.uint8)

    sel = (cb == best[..., None]) | (none_pure[..., None] & (cl == best[..., None]))
    cnt = np.maximum(sel.sum(-1), 1)

    def mean(a):
        b = blocks(a)
        if b.ndim == 4:
            return (b * sel[..., None]).sum(2) / cnt[..., None]
        return (b * sel).sum(2) / cnt

    L = mean(lum)
    ao = mean(p["Ambient Occlusion"][..., 0]) if "Ambient Occlusion" in p else np.ones_like(L)
    z = mean(p["Depth"][..., 0] if p["Depth"].ndim == 3 else p["Depth"])
    nw = mean(p["Normal"][..., :3])
    nc = nw @ cam_axes.T                       # -> (right, up, toward camera)
    ln = np.linalg.norm(nc, axis=-1, keepdims=True)
    nc = np.where(ln > 1e-5, nc / np.maximum(ln, 1e-5), np.array([0, 0, 1], dtype=np.float32))
    return dict(id=ident, L=L.astype(np.float16), ao=ao.astype(np.float16),
                z=np.where(opaque, z, 1e4).astype(np.float32), n=nc.astype(np.float16))
