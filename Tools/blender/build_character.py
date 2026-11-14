"""Build one character from script: mesh, rig, actions, render setup -> .blend and .fbx.

    /Applications/Blender.app/Contents/MacOS/Blender -b -P Tools/blender/build_character.py -- shieldbearer [--no-fbx]

Writes SourceArt/Characters/blender/<name>.blend and SourceArt/Characters/fbx/<name>.fbx.
"""

import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = os.path.normpath(os.path.join(HERE, "..", "..", "SourceArt", "Characters"))

import bpy  # noqa: E402

import srkit as K  # noqa: E402
import srrender  # noqa: E402


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    name = args[0]
    mod = importlib.import_module("char_" + name)
    sc, col = K.new_scene()
    rig = K.Rig(name, mod.bones(), col, ik_prefixes=getattr(mod, "IK_PREFIXES", ("",)),
                ik_chains=getattr(mod, "IK_CHAINS", ()))
    b = K.Builder(name)
    mod.build_mesh(b)
    ob = b.build(rig.ob, col)
    for prop, socket in getattr(mod, "PROPS", {}).items():
        rig.attach_prop(prop, socket)
    mod.animate(rig)
    rig.finish_actions()
    srrender.setup(sc, **srrender.DEFAULTS)
    srrender.setup_passes(sc)
    srrender.set_clay(False)
    # leave the file showing the idle stance
    rig.ob.animation_data.action = rig.actions.get("idle") or next(iter(rig.actions.values()))
    sc.frame_start, sc.frame_end = 0, 7
    sc.frame_set(0)
    sc["sr_character"] = name
    sc["sr_body_height_cm"] = mod.BODY_HEIGHT_CM
    # bigger units (horseman, catapult) declare their own cell / pivot; render_sprites.py takes them as defaults
    for k, v in getattr(mod, "RENDER", {}).items():
        sc["sr_render_" + k] = list(v) if isinstance(v, (tuple, list)) else v
    os.makedirs(os.path.join(OUT, "blender"), exist_ok=True)
    blend = os.path.join(OUT, "blender", name + ".blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)
    print("saved", blend, "verts", len(ob.data.vertices), "actions", list(rig.actions))

    if "--no-fbx" not in args:
        os.makedirs(os.path.join(OUT, "fbx"), exist_ok=True)
        bpy.ops.object.select_all(action="DESELECT")
        rig.ob.select_set(True)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = rig.ob
        fbx = os.path.join(OUT, "fbx", name + ".fbx")
        bpy.ops.export_scene.fbx(
            filepath=fbx, use_selection=True, object_types={"ARMATURE", "MESH"},
            add_leaf_bones=False, use_armature_deform_only=True, mesh_smooth_type="FACE",
            bake_anim=True, bake_anim_use_all_actions=True, bake_anim_use_nla_strips=False,
            bake_anim_use_all_bones=True, bake_anim_step=1.0, bake_anim_simplify_factor=0.0,
            bake_anim_force_startend_keying=True)
        print("exported", fbx)


main()
