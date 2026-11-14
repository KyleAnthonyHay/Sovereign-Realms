"""Rig sanity report: IK reach error on every frame, and the stance-foot travel of the walk cycle.

    Blender -b SourceArt/Characters/blender/<name>.blend -P Tools/blender/check_rig.py
"""
import bpy

arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
sc = bpy.context.scene
worst = {}
for act in bpy.data.actions:
    arm.animation_data.action = act
    for fr in range(int(act["sr_frames"])):
        sc.frame_set(fr)
        bpy.context.view_layer.update()
        for limb, ctl in (("foot.L", "ik_foot.L"), ("foot.R", "ik_foot.R"), ("hand.L", "ik_hand.L"), ("hand.R", "ik_hand.R")):
            e = (arm.pose.bones[limb].head - arm.pose.bones[ctl].head).length * 100
            if e > worst.get((act.name, limb), (0, 0))[0]:
                worst[(act.name, limb)] = (e, fr)
for k, (e, fr) in sorted(worst.items()):
    if e > 3.0:
        print("reach error %-7s %-7s %5.1f cm at frame %d" % (k[0], k[1], e, fr))
act = bpy.data.actions["walk"]
arm.animation_data.action = act
n = int(act["sr_frames"])
step = float(act["sr_cycle_cm"]) / n
for foot, first in (("foot.L", 0), ("foot.R", n // 2)):
    ys = []
    for k in range(3):
        sc.frame_set((first + k) % n)
        bpy.context.view_layer.update()
        ys.append(arm.pose.bones[foot].head.y * 100)
    print("walk %s stance travel per frame: %.2f, %.2f cm (body travels %.2f cm per frame)"
          % (foot, ys[1] - ys[0], ys[2] - ys[1], step))
