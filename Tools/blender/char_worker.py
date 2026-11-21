"""Workers: the kingdom's miners, farmhands and builders. Cosmetic people who make the farms and mines feel worked.

Shared body (lighter than a soldier, no armour): linen tunic with a team sash and hem, leather wraps, a basket on
the back. Two variants (char_miner.py, char_farmer.py):
  miner  - leather skullcap, pickaxe, a basket of ore with gold flecks
  farmer - wide straw hat, long hoe, a basket of cut sheaves
  builder - team-coloured hood, leather apron, a big mallet, planks on the back (a troop: char_builder.py)
  scout   - a deep team-coloured hood and a long cloak instead of the basket, a light spear on the shoulder, and a
            sprinter's stride: 192 cm to the run cycle instead of 124 (a troop: char_scout.py)
  medic   - a field medic: bare-headed with a team headband, a leather bib apron, team armbands, a big medical bag
            slung across the body instead of the basket, a rolled bandage in the hand instead of a tool. "attack" is
            the heal: he kneels and binds a wound in front of him (a troop: char_medic.py)
Sheet layout is the troops' (spawn, idle, walk, attack, hit, death) so the game drives them with the same code;
"attack" is the work swing (pick into rock / hoe into soil) and loops while they work. Death is a simple fall.
"""

import math

from mathutils import Matrix, Vector

import srkit as K
from srkit import E, V, aim, capsule, ellipsoid, lathe, place, sheet, tube

BODY_HEIGHT_CM = 132.0

P = dict(
    pelvis=0.52, waist=0.62, chest=0.77, neck=0.955,
    hip=(0.092, 0.0, 0.545), knee=(0.108, -0.028, 0.305), ankle=(0.12, 0.0, 0.085), foot_len=0.17,
    shoulder=(0.225, 0.0, 0.885), elbow=(0.262, 0.032, 0.705), wrist=(0.275, -0.005, 0.545),
)

FIST_L = Vector((0.2775, -0.012, 0.487))
FIST_R = Vector((-FIST_L.x, FIST_L.y, FIST_L.z))
WRIST_L = Vector(P["wrist"])
WRIST_R = Vector((-WRIST_L.x, WRIST_L.y, WRIST_L.z))
PROPS = {"tool": "hand.R"}
STEP = 0.155          # 8 walk frames = 124 cm = WalkCycleDistance
HANDLE = 0.78         # tool handle length from the right fist
GRIP2 = 0.30          # where the left hand holds the handle, from the right fist


def bones():
    B = K.humanoid_bones(P)
    wr, el = Vector(WRIST_R), Vector((-P["elbow"][0], P["elbow"][1], P["elbow"][2]))
    tail = wr + (wr - el).normalized() * 0.10
    B += [
        ("tool", tuple(wr), tuple(tail), "root", True),
        ("basket", (0, 0.15, 0.70), (0, 0.17, 0.95), "chest", True),
        ("skirt", (0, 0, 0.62), (0, 0, 0.42), "hips", True),
        ("sash_tail", (0.13, -0.12, 0.63), (0.15, -0.15, 0.43), "hips", True),
    ]
    return B


def build_mesh(b, variant):
    miner = variant == "miner"
    medic = variant == "medic"
    # ---------------------------------------------------------------- legs: bare shins with wraps, low boots
    hip, knee, ankle = V(P["hip"]), V(P["knee"]), V(P["ankle"])
    b.add(capsule(hip, knee, 0.086, 0.072, seg=14), "leather_dark" if medic else "skin", "upper_leg.L", mirror=True)   # (the Medic wears leggings)
    b.add(capsule(knee, ankle + V(0, 0, 0.02), 0.072, 0.058, seg=14), "skin", "lower_leg.L", mirror=True)
    b.add(capsule(knee.lerp(ankle, 0.25), ankle + V(0, 0, 0.03), 0.075, 0.063, seg=12, caps=2), "linen" if miner else "leather",
          "lower_leg.L", mirror=True)
    for t in (0.35, 0.6, 0.85):
        c = knee.lerp(ankle, t)
        b.add(lathe([(0.077, -0.01), (0.08, 0.0), (0.077, 0.01)], seg=12), "leather_dark", "lower_leg.L", place(c), mirror=True)
    b.add(ellipsoid((0.072, 0.072, 0.064), seg=12, rings=8), "leather", "foot.L", place(ankle + V(0, 0.008, -0.012)), mirror=True)
    b.add(ellipsoid((0.07, 0.124, 0.052), seg=14, rings=8, e1=0.7, e2=0.8), "leather", "foot.L", place(V(ankle.x, -0.058, 0.052)), mirror=True)
    b.add(ellipsoid((0.075, 0.13, 0.018), seg=14, rings=6, e1=0.5, e2=0.8), "leather_dark", "foot.L", place(V(ankle.x, -0.058, 0.016)), mirror=True)

    # ---------------------------------------------------------------- tunic: knee length, rolled sleeves, team sash
    b.add(ellipsoid((0.16, 0.12, 0.095), seg=16, rings=8), "linen", "hips", place((0, 0, 0.56)))
    b.add(lathe([(0.0, 0.65), (0.165, 0.65), (0.19, 0.56), (0.22, 0.45), (0.224, 0.42), (0.0, 0.42)], seg=24, sy=0.8), "linen", "skirt")
    b.add(lathe([(0.0, 0.425), (0.225, 0.425), (0.232, 0.39), (0.226, 0.38), (0.0, 0.38)], seg=24, sy=0.8), "team", "skirt")
    b.add(lathe([(0.0, 0.376), (0.226, 0.376), (0.0, 0.372)], seg=24, sy=0.8), "leather_dark", "skirt")
    b.add(lathe([(0.0, 0.63), (0.17, 0.63), (0.176, 0.70), (0.186, 0.775), (0.0, 0.775)], seg=24, sy=0.74), "linen", "spine")
    b.add(lathe([(0.0, 0.765), (0.188, 0.765), (0.198, 0.84), (0.19, 0.9), (0.15, 0.94), (0.0, 0.95)], seg=24, sy=0.74), "linen", "chest")
    b.add(capsule((0, 0, 0.92), (0, -0.005, 1.0), 0.07, 0.066, seg=12), "skin", "chest")
    b.add(lathe([(0.0, 0.60), (0.176, 0.60), (0.184, 0.632), (0.176, 0.664), (0.0, 0.664)], seg=24, sy=0.78), "team", "hips")
    ts = -1 if medic else 1      # the Medic's sash tail hangs on the right: the bag is on the left hip
    b.add(sheet([[V(ts * 0.095, -0.12 - (0.05 if medic else 0.0), 0.62), V(ts * 0.155, -0.10 - (0.05 if medic else 0.0), 0.62)],
                 [V(ts * 0.10, -0.15 - (0.06 if medic else 0.0), 0.53), V(ts * 0.168, -0.128 - (0.06 if medic else 0.0), 0.53)]], 0.026),
          "team", "sash_tail")
    if variant == "builder":
        # leather work apron over the tunic front, waist to knee
        b.add(sheet([[V(-0.13, -0.158, 0.66), V(0.13, -0.158, 0.66)],
                     [V(-0.15, -0.205, 0.40), V(0.15, -0.205, 0.40)]], 0.022), "leather", "skirt")
        b.add(lathe([(0.0, 0.655), (0.177, 0.655), (0.177, 0.675), (0.0, 0.675)], seg=24, sy=0.78), "leather_dark", "hips")
    if medic:
        # a canvas bib apron: bib over the chest (a strap round the neck), the team sash tied over it at the waist,
        # the skirt of it to the knee; a few dark stains
        b.add(sheet([[V(-0.085, -0.150, 0.90), V(0.085, -0.150, 0.90)],
                     [V(-0.12, -0.172, 0.80), V(0.12, -0.172, 0.80)],
                     [V(-0.13, -0.158, 0.655), V(0.13, -0.158, 0.655)]], 0.022), "rope", "chest")
        b.add(tube([V(-0.08, -0.155, 0.895), V(-0.085, -0.06, 0.975), V(0.0, 0.075, 0.985), V(0.085, -0.06, 0.975), V(0.08, -0.155, 0.895)],
                   0.014, seg=6), "leather_dark", "chest")
        b.add(sheet([[V(-0.13, -0.162, 0.61), V(0.13, -0.162, 0.61)],
                     [V(-0.15, -0.205, 0.40), V(0.15, -0.205, 0.40)]], 0.022), "rope", "skirt")
        b.add(ellipsoid((0.035, 0.012, 0.03), seg=8, rings=5), "leather_dark", "chest", place((0.045, -0.178, 0.76)))
        b.add(ellipsoid((0.04, 0.012, 0.035), seg=8, rings=5), "leather_dark", "skirt", place((-0.06, -0.20, 0.49)))
        b.add(ellipsoid((0.028, 0.012, 0.024), seg=8, rings=5), "leather_dark", "skirt", place((0.07, -0.205, 0.44)))
        # a neckerchief in the team's lighter colour
        b.add(lathe([(0.0, 0.93), (0.135, 0.93), (0.15, 0.965), (0.10, 1.0), (0.0, 1.005)], seg=20, sy=0.85), "team_trim", "chest")
        # the bag's strap, right shoulder to left hip; rolled bandages tied to it on the chest
        b.add(tube([V(-0.13, 0.02, 1.0), V(-0.10, -0.15, 0.95), V(-0.02, -0.195, 0.87), V(0.07, -0.20, 0.79), V(0.15, -0.165, 0.70),
                    V(0.21, -0.13, 0.60)], 0.021, seg=6, squash=(1.0, 0.6)), "leather_dark", "chest")
        b.add(tube([V(-0.13, 0.02, 1.0), V(-0.09, 0.17, 0.94), V(0.02, 0.195, 0.85), V(0.13, 0.165, 0.74), V(0.215, 0.07, 0.65),
                    V(0.235, -0.02, 0.61)], 0.021, seg=6, squash=(1.0, 0.6)), "leather_dark", "chest")
        for c in (V(-0.06, -0.195, 0.905), V(0.025, -0.22, 0.83)):
            ax = V(0.62, 0.0, 0.62)
            b.add(capsule(c - ax * 0.05, c + ax * 0.05, 0.034, seg=8, caps=2), "feather", "chest")
        # a small flask on the belt at the right hip
        b.add(ellipsoid((0.042, 0.036, 0.058), seg=8, rings=6), "straw", "hips", place((-0.20, -0.045, 0.555)))
        b.add(capsule((-0.20, -0.045, 0.60), (-0.20, -0.045, 0.635), 0.016, seg=6, caps=1), "leather_dark", "hips")
    # basket straps over both shoulders (the Scout: one baldric; the Medic has its satchel strap instead)
    for s in (() if medic else (1, -1) if variant != "scout" else (1,)):
        b.add(tube([V(s * 0.12, 0.05, 0.95), V(s * 0.15, -0.10, 0.88), V(s * 0.16, -0.12, 0.74), V(s * 0.16, -0.02, 0.66),
                    V(s * 0.12, 0.13, 0.68)], 0.017, seg=6, squash=(1.0, 0.6)), "leather_dark", "chest")

    # ---------------------------------------------------------------- arms: bare forearms, sleeve to the elbow
    sh, el, wr = V(P["shoulder"]), V(P["elbow"]), V(P["wrist"])
    b.add(ellipsoid((0.086, 0.09, 0.075), seg=14, rings=8), "linen", "upper_arm.L", place(sh + V(0.004, 0, 0.012)), mirror=True)
    b.add(capsule(sh, el, 0.07, 0.064, seg=12), "linen", "upper_arm.L", mirror=True)
    if medic:       # team armbands
        b.add(capsule(sh.lerp(el, 0.38), sh.lerp(el, 0.72), 0.077, 0.073, seg=12, caps=1), "team", "upper_arm.L", mirror=True)
    b.add(capsule(el, wr, 0.058, 0.05, seg=12), "skin", "lower_arm.L", mirror=True)
    fist = wr + (wr - el).normalized() * 0.058
    b.add(ellipsoid((0.07, 0.076, 0.073), seg=12, rings=8, e1=0.8, e2=0.85), "skin", "hand.L", place(fist), mirror=True)

    # ---------------------------------------------------------------- head
    hz = 1.105
    b.add(ellipsoid((0.14, 0.148, 0.148), seg=18, rings=12), "skin", "head", place((0, -0.005, hz)))
    b.add(ellipsoid((0.036, 0.046, 0.046), seg=10, rings=6), "skin", "head", place((0, -0.152, hz - 0.02)))
    b.add(ellipsoid((0.026, 0.019, 0.021), seg=8, rings=6), "eye", "head", place((0.058, -0.136, hz + 0.012)), mirror=True)
    b.add(capsule((0.024, -0.148, hz + 0.036), (0.094, -0.126, hz + 0.046), 0.013, 0.011, seg=8, caps=2), "hair", "head", mirror=True)
    b.add(ellipsoid((0.13, 0.11, 0.07), seg=16, rings=8), "beard" if variant != "farmer" else "hair", "head", place((0, -0.05, hz - 0.115), rx=-10))
    b.add(ellipsoid((0.15, 0.15, 0.12), seg=16, rings=8), "hair", "head", place((0, 0.02, hz + 0.03)))
    if miner:
        # leather skullcap with a team band
        cap = place((0, 0.006, hz + 0.02), rx=-10)
        b.add(lathe([(0.0, 0.03), (0.155, 0.03), (0.16, 0.07), (0.145, 0.12), (0.1, 0.155), (0.0, 0.165)], seg=24, sy=1.04), "leather", "head", cap)
        b.add(lathe([(0.0, 0.02), (0.164, 0.02), (0.168, 0.05), (0.164, 0.07), (0.0, 0.07)], seg=24, sy=1.04), "team", "head", cap)
    elif variant in ("builder", "scout"):
        # a team-coloured hood over the head and shoulders, the face left open, a dark band round the brow
        # (the Scout's is pulled further forward, and has no brow band: the face sits in its shadow)
        hood = place((0, 0.02, hz + 0.0), rx=-12)
        b.add(lathe([(0.0, -0.02), (0.17, -0.02), (0.175, 0.04), (0.165, 0.10), (0.12, 0.155), (0.0, 0.175)], seg=24, sy=1.06), "team", "head", hood)
        if variant == "builder":
            b.add(lathe([(0.0, 0.03), (0.177, 0.03), (0.18, 0.06), (0.0, 0.06)], seg=24, sy=1.06), "leather_dark", "head", hood)
        else:
            b.add(lathe([(0.0, 0.10), (0.172, 0.10), (0.176, 0.125), (0.0, 0.125)], seg=24, sy=1.12), "team", "head", place((0, -0.03, hz - 0.02), rx=-12))
        b.add(lathe([(0.0, 0.90), (0.20, 0.90), (0.215, 0.95), (0.16, 1.0), (0.0, 1.0)], seg=24, sy=0.8), "team", "chest")
    elif medic:
        # bare-headed, short hair; a cloth headband in the team's colour
        b.add(ellipsoid((0.153, 0.158, 0.136), seg=16, rings=8), "hair", "head", place((0, 0.014, hz + 0.04)))
        b.add(lathe([(0.0, 0.045), (0.158, 0.045), (0.163, 0.065), (0.158, 0.088), (0.0, 0.088)], seg=24, sy=1.04), "team", "head",
              place((0, 0.012, hz), rx=-10))
    else:
        # wide straw hat, crown banded in the team colour
        hat = place((0, 0.004, hz + 0.08), rx=-8)
        b.add(lathe([(0.0, 0.0), (0.33, 0.0), (0.34, 0.014), (0.3, 0.03), (0.17, 0.045), (0.0, 0.05)], seg=28, sy=1.0), "straw", "head", hat)
        b.add(lathe([(0.0, 0.04), (0.15, 0.04), (0.14, 0.13), (0.09, 0.16), (0.0, 0.165)], seg=24, sy=1.0), "straw", "head", hat)
        b.add(lathe([(0.0, 0.045), (0.155, 0.045), (0.152, 0.075), (0.0, 0.075)], seg=24, sy=1.0), "team", "head", hat)

    # ---------------------------------------------------------------- basket on the back (the Scout wears a cloak instead)
    if medic:
        # no basket: a roll of clean linen across the small of the back, and the big leather medical bag on the left
        # hip (flap, buckle, bandage rolls showing under the flap). The bag rides on the basket bone, so it bounces.
        b.add(capsule((-0.13, 0.165, 0.69), (0.13, 0.165, 0.69), 0.05, seg=10, caps=2), "linen", "chest")
        for x in (-0.07, 0.07):
            b.add(capsule((x - 0.012, 0.165, 0.69), (x + 0.012, 0.165, 0.69), 0.055, seg=10, caps=1), "leather_dark", "chest")
        sm = place((0.255, -0.085, 0.47), rz=58)
        b.add(ellipsoid((0.155, 0.09, 0.13), seg=14, rings=8, e1=0.55, e2=0.6), "leather", "basket", sm)
        b.add(ellipsoid((0.162, 0.097, 0.065), seg=14, rings=6, e1=0.55, e2=0.6), "leather_dark", "basket", sm @ place((0, 0, 0.075)))
        b.add(ellipsoid((0.028, 0.016, 0.034), seg=6, rings=5), "gold", "basket", sm @ place((0, -0.097, 0.02)))
        for dx in (-0.07, 0.07):
            b.add(capsule(sm @ V(dx, -0.025, 0.14), sm @ V(dx, 0.025, 0.14), 0.034, seg=8, caps=2), "feather", "basket")
    elif variant == "scout":
        # a long cloak in the team's colour, shoulders to calves, a dark hem; it rides on the basket bone so it
        # swings with the stride
        rows = [[V(-0.17, 0.10, 0.97), V(0.0, 0.135, 0.985), V(0.17, 0.10, 0.97)],
                [V(-0.23, 0.17, 0.74), V(0.0, 0.215, 0.74), V(0.23, 0.17, 0.74)],
                [V(-0.27, 0.20, 0.50), V(0.0, 0.255, 0.50), V(0.27, 0.20, 0.50)],
                [V(-0.29, 0.21, 0.31), V(0.0, 0.275, 0.31), V(0.29, 0.21, 0.31)]]
        b.add(sheet(rows, 0.03), "team", "basket")
        b.add(sheet([[V(-0.295, 0.212, 0.315), V(0.0, 0.278, 0.315), V(0.295, 0.212, 0.315)],
                     [V(-0.30, 0.215, 0.275), V(0.0, 0.283, 0.275), V(0.30, 0.215, 0.275)]], 0.036), "leather_dark", "basket")
        # a leather belt pouch and a rolled blanket across the small of the back
        b.add(ellipsoid((0.05, 0.04, 0.055), seg=8, rings=6), "leather", "hips", place((0.15, -0.10, 0.58)))
    else:
        bm = place((0, 0.20, 0.80), rx=8)
        b.add(lathe([(0.0, -0.13), (0.11, -0.13), (0.14, -0.05), (0.155, 0.08), (0.16, 0.12), (0.0, 0.12)], seg=16, sy=0.75), "straw", "basket", bm)
        b.add(lathe([(0.0, 0.11), (0.165, 0.11), (0.168, 0.135), (0.0, 0.135)], seg=16, sy=0.75), "leather_dark", "basket", bm)
        if variant == "builder":
            # planks standing up out of the basket, leaning a little apart
            for k, (dx, lean, ln) in enumerate(((-0.07, -10, 0.46), (-0.01, -3, 0.52), (0.05, 5, 0.44), (0.10, 12, 0.38))):
                base = V(dx, 0.21 + 0.012 * k, 0.86)
                top = base + V(math.sin(math.radians(lean)) * ln, 0.03, math.cos(math.radians(lean)) * ln)
                b.add(tube([base, top], 0.034, seg=4, squash=(1.0, 0.28), up=(0, 1, 0)), "wood", "basket")
        elif miner:
            for dx, dy, r, mat in ((-0.06, 0.18, 0.06, "ore"), (0.05, 0.21, 0.055, "ore"), (0.0, 0.17, 0.045, "gold"), (0.07, 0.17, 0.04, "ore"),
                                   (-0.08, 0.22, 0.035, "gold")):
                b.add(ellipsoid((r, r * 0.9, r * 0.8), seg=8, rings=5), mat, "basket", place((dx, dy, 0.93 + r * 0.4)))
        else:
            for k in range(7):
                a = -0.35 + k * 0.12
                base = V(0.05 * math.sin(k * 2.1), 0.20, 0.90)
                top = base + V(math.sin(a) * 0.12, 0.04, 0.30 + 0.03 * math.cos(k))
                b.add(capsule(base, top, 0.018, 0.012, seg=6, caps=1), "straw", "basket")
                b.add(ellipsoid((0.03, 0.026, 0.06), seg=6, rings=5), "straw", "basket", place(top + V(0, 0, 0.03)))

    # ---------------------------------------------------------------- the tool, built along -Y from the right fist
    f = FIST_R
    if not medic:
        b.add(capsule(f + V(0, 0.06, 0), f + V(0, -HANDLE, 0), 0.022, 0.02, seg=8, caps=2), "wood", "tool")
    h = f + V(0, -HANDLE + 0.04, 0)
    if medic:
        # no tool: a rolled bandage in the fist (a short pale cylinder along the fist), its loose end trailing (-Z at rest)
        b.add(capsule(f + V(0, 0.035, 0), f + V(0, -0.105, 0), 0.05, seg=10, caps=1), "feather", "tool")
        b.add(sheet([[V(f.x - 0.045, f.y - 0.09, f.z - 0.03), V(f.x - 0.045, f.y - 0.02, f.z - 0.03)],
                     [V(f.x - 0.05, f.y - 0.10, f.z - 0.12), V(f.x - 0.05, f.y - 0.03, f.z - 0.12)],
                     [V(f.x - 0.035, f.y - 0.125, f.z - 0.22), V(f.x - 0.035, f.y - 0.055, f.z - 0.22)]], 0.016), "feather", "tool")
    elif variant == "builder":
        # mallet: a fat wooden head across the end of the handle, iron-banded at both faces (face = -Z at rest)
        b.add(capsule(h + V(0, 0.0, 0.10), h + V(0, 0.0, -0.10), 0.068, seg=10, caps=2), "wood", "tool")
        for z in (0.085, -0.085):
            b.add(capsule(h + V(0, 0.0, z + 0.012), h + V(0, 0.0, z - 0.012), 0.072, seg=10, caps=1), "iron", "tool")
    elif variant == "scout":
        # a light spear: a leaf-shaped iron head on the end of the shaft, a leather binding under it
        b.add(tube([h + V(0, 0.01, 0), h + V(0, -0.04, 0), h + V(0, -0.10, 0), h + V(0, -0.15, 0)], [0.02, 0.046, 0.034, 0.004], seg=6,
                   squash=(1.0, 0.35), up=(0, 0, 1)), "iron", "tool")
        b.add(capsule(h + V(0, 0.07, 0), h + V(0, 0.02, 0), 0.027, seg=8, caps=2), "leather_dark", "tool")
    elif miner:
        # pick head: an iron bar across the end, curved down to a point (edge = -Z at rest)
        b.add(tube([h + V(0, 0.03, 0.17), h + V(0, 0.0, 0.08), h + V(0, -0.01, 0.0), h + V(0, 0.0, -0.10), h + V(0, 0.05, -0.22)],
                   [0.016, 0.03, 0.036, 0.028, 0.004], seg=6, squash=(0.8, 1.0)), "iron", "tool")
        b.add(capsule(h + V(0, 0.03, 0.02), h + V(0, -0.03, 0.02), 0.03, seg=8, caps=2), "leather_dark", "tool")
    else:
        # hoe: a broad iron blade hanging down from the end (edge = -Z at rest)
        b.add(tube([h + V(0, 0.0, 0.02), h + V(0, 0.03, -0.06), h + V(0, 0.07, -0.15)], [0.05, 0.075, 0.08], seg=6, squash=(0.18, 1.0),
                   up=(1, 0, 0)), "iron", "tool")
        b.add(capsule(h + V(0, 0.03, 0.03), h + V(0, -0.03, 0.03), 0.026, seg=8, caps=2), "leather_dark", "tool")


# ------------------------------------------------------------------------------------------------ poses
import sranim as A  # noqa: E402
from srkit import pose_lerp, pose_merge  # noqa: E402


def tool_rot(d, edge):
    """Right-hand rotation that points the handle along d (from the fist toward the head) with the head's edge toward edge."""
    return aim(d, edge, s0=(0, 0, -1))


def blank():
    return {b: {} for b in ("root", "hips", "spine", "chest", "head", "ik_foot.L", "ik_foot.R", "pole_knee.L", "pole_knee.R",
                            "ik_hand.L", "ik_hand.R", "pole_elbow.L", "pole_elbow.R", "tool", "basket", "skirt", "sash_tail")}


def make(rig, hips, spine, chest, head, footL, footR, grip, d, edge, lhand=None, two_hands=False,
         kneeL=(0.2, -1.0, 0.3), kneeR=(-0.2, -1.0, 0.3), elbowL=(0.9, 0.5, 0.4), elbowR=(-0.9, 0.6, 0.5),
         basket=0.0, skirt=0.0, sash=0.0):
    """One pose. grip = right fist position (character space), d = handle direction, edge = head edge direction.
    two_hands puts the left fist on the handle GRIP2 further along; otherwise lhand is a free left wrist position."""
    p = blank()
    p["hips"] = {"loc": hips[0], "rot": hips[1]}
    p["spine"] = {"rot": spine}
    p["chest"] = {"rot": chest}
    p["ik_foot.L"] = {"pos": footL[0], "rot": footL[1]}
    p["ik_foot.R"] = {"pos": footR[0], "rot": footR[1]}
    p["pole_knee.L"] = {"pos": kneeL}
    p["pole_knee.R"] = {"pos": kneeR}
    q = tool_rot(d, edge)
    rw = Vector(grip) - q @ (FIST_R - WRIST_R)
    if two_hands:
        lf = Vector(grip) + Vector(d).normalized() * GRIP2
        ql = q
        lw = lf - ql @ (FIST_L - WRIST_L)
        lspec = {"pos": tuple(lw), "rot": ql}
    else:
        lspec = {"pos": lhand or (0.31, -0.02, 0.58), "rot": E(0, 0, 0)}
    A.hands(rig, p, {"ik_hand.R": {"pos": tuple(rw), "rot": q}, "ik_hand.L": lspec,
                     "pole_elbow.L": {"pos": elbowL}, "pole_elbow.R": {"pos": elbowR}})
    if isinstance(head, tuple):
        A.look(rig, p, yaw=head[0], pitch=head[1], roll=head[2] if len(head) > 2 else 0.0)
    else:
        p["head"] = {"rot": head}
    p["basket"] = {"rot": E(basket, 0, 0)}
    p["skirt"] = {"rot": E(skirt, 0, 0)}
    p["sash_tail"] = {"rot": E(sash, 0, 0)}
    return p


FOOT_L = ((0.13, -0.08, 0.085), E(0, 0, 6))
FOOT_R = ((-0.14, 0.06, 0.085), E(0, 0, -12))
# tool on the right shoulder: fist in front of the chest, handle up and back over the shoulder, head behind
SHOULDER = dict(grip=(-0.20, -0.16, 0.86), d=(0.08, 0.55, 0.83), edge=(0, 0.6, -0.8))
# the Medic's bandage roll: in the right fist in front of the waist, pointing forward, the loose end hanging
ROLL = dict(grip=(-0.25, -0.20, 0.69), d=(0.25, -0.9, 0.2), edge=(0, 0, -1))
# the roll in the shared spawn / hit / death poses (grip, d, edge)
MEDIC_TOOL = {
    "h0": ((-0.29, -0.10, 0.84), (0.2, -0.6, 0.6), (0, 0, -1)),
    "s0": ((-0.24, -0.22, 0.50), (0.2, -0.9, 0.1), (0, 0, -1)),
    "s3": ((-0.25, -0.20, 0.74), ROLL["d"], ROLL["edge"]),
    "d0": ((-0.36, 0.02, 0.88), (0.2, -0.5, 0.8), (0, 0, -1)),
    "d1": ((-0.20, -0.20, 0.62), (0.3, -0.8, -0.2), (0, 0, -1)),
    "d2": ((-0.30, -0.22, 0.36), (0.3, -0.8, -0.2), (0, 0, -1)),
    "d3": ((-0.36, -0.30, 0.22), (0.5, -0.8, 0.0), (0, 0, -1)),
    "d5": ((-0.36, -0.60, 0.07), (0.6, -0.8, 0.0), (-0.8, -0.6, 0)),
    "d7": ((-0.36, -0.62, 0.055), (0.6, -0.8, 0.0), (-0.8, -0.6, 0)),
}


def rest(rig, variant=None):
    if variant == "medic":      # standing ready: the bandage roll in the right hand, the left hand on the bag
        return make(rig, ((0, 0, -0.02), E(0, 0, -4)), E(1, 0, 0), E(0, 0, -2), (0, -8), FOOT_L, FOOT_R,
                    ROLL["grip"], ROLL["d"], ROLL["edge"], lhand=(0.315, 0.0, 0.645), elbowL=(0.9, 0.7, 0.5))
    return make(rig, ((0, 0, -0.02), E(0, 0, -4)), E(1, 0, 0), E(0, 0, -2), (0, -8), FOOT_L, FOOT_R,
                SHOULDER["grip"], SHOULDER["d"], SHOULDER["edge"], lhand=(0.30, -0.03, 0.57))


def animate(rig, variant):
    miner = variant == "miner"
    scout = variant == "scout"
    medic = variant == "medic"
    step = 0.24 if scout else STEP        # the Scout sprints: 8 frames = 192 cm (FSRUnitStats::WalkCycleDistance)
    G = rest(rig, variant)

    def tp(key, grip, d, edge):
        """Tool placement of a shared pose: the Medic's bandage roll has its own."""
        return MEDIC_TOOL[key] if medic else (grip, d, edge)
    sin, cos, pi = math.sin, math.cos, math.pi

    # ---------------------------------------------------------------- idle: breathing, a shrug of the tool
    rig.new_action("idle", 8, loop=True, drive="time", fps=5.0)
    for i in range(8):
        p = pose_merge(G)
        p["hips"] = {"loc": (G["hips"]["loc"][0], 0, -0.02 + A.IDLE_UP[i] * A.PX_Z), "rot": G["hips"]["rot"]}
        hl, hr = dict(G["ik_hand.L"]), dict(G["ik_hand.R"])
        lag = A.IDLE_HAND_LAG[i] * A.PX_Z
        hl["pos"] = tuple(Vector(hl["pos"]) + Vector((0, 0, -lag)))
        hr["pos"] = tuple(Vector(hr["pos"]) + Vector((0, 0, lag)))
        p["ik_hand.L"], p["ik_hand.R"] = hl, hr
        p["basket"] = {"rot": E(2 * A.IDLE_SWAY[i], 0, 0)}
        p["sash_tail"] = {"rot": E(4 * A.IDLE_SWAY[i], 0, 0)}
        rig.key(p, i)

    # ---------------------------------------------------------------- walk: an easy trudge, tool on the shoulder
    rig.new_action("walk", 8, loop=True, drive="distance", cycle_cm=step * 800,
                   contact_frames=[0, 4], roles=["contact L", "down", "passing", "up", "contact R", "down", "passing", "up"])
    for i in range(8):
        ph = i / 8
        if scout:       # head down, long low strides, the cloak streaming
            body = A.run_body(i, bob=0.03, drop=-0.085, lean=17.0, sway=0.012, yaw=12.0, roll=4.0)
        elif medic:     # brisk and purposeful
            body = A.run_body(i, bob=0.026, drop=-0.035, lean=10.0, sway=0.012, yaw=10.0, roll=3.0)
        else:
            body = A.run_body(i, bob=0.022, drop=-0.035, lean=6.0, sway=0.012, yaw=8.0, roll=3.0)
        fl = A.run_legs(ph, step, 0.085, lift=0.17 if scout else 0.11, side=1, foot_x=0.11)
        fr = A.run_legs(ph + 0.5, step, 0.085, lift=0.17 if scout else 0.11, side=-1, foot_x=0.11)
        lag = -0.022 * cos(4 * pi * ph - pi / 2 - 0.9)
        c1 = cos(2 * pi * ph)
        g, td, te = Vector(SHOULDER["grip"]) + Vector((0, 0, lag)), SHOULDER["d"], SHOULDER["edge"]
        if medic:       # the roll in the right hand, the arm swinging against the left; the bag bounces on its strap
            g, td, te = Vector((-0.27, -0.14 - 0.13 * c1, 0.69 + lag)), (0.2, -0.9, 0.25), ROLL["edge"]
        p = make(rig, (body["hips"]["loc"], body["hips"]["rot"]), body["spine"]["rot"], body["chest"]["rot"], (0, -6),
                 (fl["pos"], fl["rot"]), (fr["pos"], fr["rot"]), tuple(g), td, te,
                 lhand=(0.35 if medic else 0.30, -0.02 + (0.24 if scout else 0.14) * c1, 0.60 + lag), kneeL=(0.16, -1.0, 0.3),
                 kneeR=(-0.16, -1.0, 0.3),
                 basket=(-26 + 6 * cos(4 * pi * ph - 2.0)) if scout else (7 if medic else 3) * cos(4 * pi * ph - 2.0),
                 sash=8 + 8 * cos(4 * pi * ph - 2.0), skirt=3 * cos(4 * pi * ph - 1.0))
        rig.key(p, i)

    # ---------------------------------------------------------------- attack = work: lift overhead, swing down into
    # the rock / soil (frame 4), bounce, pull it free, back to ready. Looped by the game while the worker works.
    rig.new_action("attack", 8, drive="attack_phase", strike_frame=4, windup_frames=[0, 1, 2, 3], recovery_frames=[4, 5, 6, 7],
                   windup_phase_map=[0.0, 0.25, 0.5, 0.75], recovery_phase_map=[0.0, 0.25, 0.5, 0.75])
    edge_fwd = (0, -1, 0.2)
    stance_l = ((0.14, -0.22, 0.085), E(0, 0, 4))
    stance_r = ((-0.15, 0.10, 0.085), E(0, 0, -16))
    w0 = make(rig, ((0, 0.0, -0.05), E(4, 0, -6)), E(6, 0, -2), E(4, 0, -2), (0, 6), stance_l, stance_r,
              (-0.10, -0.30, 0.70), (0.0, -0.7, -0.7), edge_fwd, two_hands=True, elbowL=(0.9, 0.2, 0.2), elbowR=(-0.9, 0.3, 0.3))
    w1 = make(rig, ((0, 0.03, -0.035), E(-4, 0, -10)), E(-6, 0, -4), E(-4, 0, -6), (0, -6), stance_l, stance_r,
              (-0.08, -0.12, 1.02), (0.0, 0.3, 0.95), (0, 0.95, -0.3), two_hands=True, elbowL=(0.9, 0.3, 0.6), elbowR=(-0.9, 0.4, 0.8),
              basket=-4)
    w2 = make(rig, ((0, 0.06, -0.02), E(-10, 0, -12)), E(-12, 0, -4), E(-8, 0, -6), (0, -14), stance_l, stance_r,
              (-0.06, 0.02, 1.20), (0.0, 0.85, 0.5), (0, 0.5, -0.85), two_hands=True, elbowL=(0.9, 0.3, 0.9), elbowR=(-0.9, 0.4, 1.0),
              basket=-8, sash=-6)
    w3 = make(rig, ((0, -0.02, -0.06), E(8, 0, -6)), E(10, 0, -2), E(8, 0, -2), (0, 4), stance_l, stance_r,
              (-0.06, -0.32, 1.02), (0.0, -0.9, 0.42), (0, -0.42, -0.9), two_hands=True, elbowL=(0.9, 0.1, 0.4), elbowR=(-0.9, 0.2, 0.4),
              basket=4)
    w4 = make(rig, ((0, -0.09, -0.12), E(18, 0, -4)), E(18, 0, 0), E(10, 0, 0), (0, 18), stance_l, stance_r,
              (-0.05, -0.42, 0.52), (0.0, -0.55, -0.83), (0, -0.83, 0.55), two_hands=True, elbowL=(0.9, 0.0, 0.2), elbowR=(-0.9, 0.1, 0.2),
              kneeL=(0.2, -1.2, 0.3), basket=10, sash=8, skirt=4)
    w5 = make(rig, ((0, -0.08, -0.11), E(16, 0, -4)), E(16, 0, 0), E(9, 0, 0), (0, 14), stance_l, stance_r,
              (-0.05, -0.41, 0.56), (0.0, -0.58, -0.81), (0, -0.81, 0.58), two_hands=True, elbowL=(0.9, 0.0, 0.2), elbowR=(-0.9, 0.1, 0.2),
              basket=6, sash=4)
    w6 = make(rig, ((0, -0.03, -0.07), E(6, 0, -6)), E(6, 0, -2), E(4, 0, -2), (0, 6), stance_l, stance_r,
              (-0.08, -0.34, 0.66), (0.0, -0.75, -0.6), edge_fwd, two_hands=True, elbowL=(0.9, 0.2, 0.2), elbowR=(-0.9, 0.3, 0.3),
              basket=-2)
    w7 = pose_lerp(w6, w0, 0.6)
    if medic:
        # the heal: he drops to his right knee toward the wounded in front of him, takes the bandage across in both
        # hands (1-3), presses it on low and forward with both hands (4, the moment the heal goes out), holds, rises
        dn = ROLL["edge"]
        back = lambda y, z, rx: ((-0.14, y, z), E(rx, 0, -12))        # the right foot goes back onto its toes  # noqa: E731
        knee = (-0.2, -1.0, -0.3)
        w0 = make(rig, ((0, 0.0, -0.08), E(6, 0, -4)), E(6, 0, 0), E(4, 0, -2), (0, 6), FOOT_L, FOOT_R,
                  (-0.21, -0.26, 0.68), (0.4, -0.85, 0.1), dn, lhand=(0.28, -0.13, 0.60), elbowL=(0.9, 0.7, 0.5))
        w1 = make(rig, ((0, -0.01, -0.20), E(10, 0, -4)), E(10, 0, 0), E(6, 0, -2), (0, 14), FOOT_L, back(0.16, 0.10, 35),
                  (-0.17, -0.31, 0.54), (0.7, -0.6, 0.0), dn, lhand=(0.29, -0.14, 0.50), elbowL=(0.9, 0.7, 0.5), kneeR=knee,
                  basket=3, skirt=-6)
        w2 = make(rig, ((0, -0.02, -0.30), E(14, 0, -4)), E(13, 0, 0), E(8, 0, -2), (0, 20), FOOT_L, back(0.22, 0.12, 55),
                  (-0.11, -0.36, 0.42), (1.0, -0.25, 0.0), (0, -0.3, -1), lhand=(0.13, -0.30, 0.44), elbowL=(0.9, 0.2, 0.3),
                  elbowR=(-0.9, 0.2, 0.3), kneeR=knee, basket=5, skirt=-10)
        w3 = make(rig, ((0, -0.03, -0.305), E(16, 0, -4)), E(15, 0, 0), E(10, 0, -2), (0, 24), FOOT_L, back(0.22, 0.12, 55),
                  (-0.19, -0.42, 0.37), (1.0, -0.2, 0.0), (0, -0.3, -1), lhand=(0.15, -0.42, 0.36), elbowL=(0.9, 0.2, 0.3),
                  elbowR=(-0.9, 0.2, 0.3), kneeR=knee, basket=6, skirt=-10)
        w4 = make(rig, ((0, -0.06, -0.31), E(21, 0, -4)), E(18, 0, 0), E(12, 0, -2), (0, 28), FOOT_L, back(0.22, 0.12, 55),
                  (-0.10, -0.50, 0.23), (1.0, -0.1, 0.0), (0, -0.2, -1), lhand=(0.10, -0.50, 0.27), elbowL=(0.9, 0.1, 0.3),
                  elbowR=(-0.9, 0.1, 0.3), kneeR=knee, basket=8, sash=6, skirt=-10)
        w5 = make(rig, ((0, -0.055, -0.305), E(19, 0, -4)), E(17, 0, 0), E(11, 0, -2), (0, 26), FOOT_L, back(0.22, 0.12, 55),
                  (-0.11, -0.49, 0.25), (1.0, -0.1, 0.0), (0, -0.2, -1), lhand=(0.11, -0.49, 0.29), elbowL=(0.9, 0.1, 0.3),
                  elbowR=(-0.9, 0.1, 0.3), kneeR=knee, basket=6, sash=4, skirt=-10)
        w6 = make(rig, ((0, -0.02, -0.19), E(9, 0, -4)), E(9, 0, 0), E(6, 0, -2), (0, 12), FOOT_L, back(0.13, 0.095, 22),
                  (-0.20, -0.31, 0.55), (0.5, -0.8, 0.05), dn, lhand=(0.28, -0.15, 0.53), elbowL=(0.9, 0.6, 0.5), kneeR=knee,
                  basket=-3, skirt=-5)
        w7 = pose_lerp(w6, w0, 0.6)
    rig.key_all([w0, w1, w2, w3, w4, w5, w6, w7])

    # ---------------------------------------------------------------- hit: flinch
    rig.new_action("hit", 3, drive="time", fps=18.0)
    h0 = make(rig, ((0, 0.07, -0.03), E(-10, 0, -4)), E(-12, 0, -2), E(-8, 0, 0), (4, -24, 8), FOOT_L, ((-0.14, 0.18, 0.085), E(0, 0, -12)),
              *tp("h0", (-0.26, -0.06, 0.94), SHOULDER["d"], SHOULDER["edge"]), lhand=(0.38, 0.06, 0.82), basket=-6)
    h1 = pose_lerp(h0, G, 0.6)
    h2 = pose_lerp(h1, G, 0.7)
    rig.key_all([h0, h1, h2])

    # ---------------------------------------------------------------- spawn: steps out, settles the tool
    rig.new_action("spawn", 6, drive="time", fps=12.0, active_frame=5)
    s0 = make(rig, ((0, 0.02, -0.16), E(10, 0, -4)), E(12, 0, -2), E(8, 0, -2), (0, 12), FOOT_L, FOOT_R,
              *tp("s0", (-0.24, -0.20, 0.50), (0.0, -0.6, -0.8), (0, -0.8, 0.6)), lhand=(0.28, -0.12, 0.48), basket=6)
    s3 = make(rig, ((0, 0.0, -0.005), E(-3, 0, -4)), E(-4, 0, 0), E(-3, 0, -2), (0, -14), FOOT_L, FOOT_R,
              *tp("s3", (-0.22, -0.18, 0.92), SHOULDER["d"], SHOULDER["edge"]), lhand=(0.30, -0.03, 0.62), basket=-6)
    rig.key_all([s0, pose_lerp(s0, s3, 0.3), pose_lerp(s0, s3, 0.75), s3, pose_lerp(G, s0, 0.08), G])

    # ---------------------------------------------------------------- death: drops the tool, sinks to his knees, falls forward
    rig.new_action("death", 8, drive="time", fps=12.0, hold_last=True)
    d0 = make(rig, ((0, 0.08, -0.03), E(-12, 0, -4)), E(-14, 0, 0), E(-10, 0, 4), (6, -30, 8), FOOT_L, ((-0.14, 0.2, 0.085), E(0, 0, -12)),
              *tp("d0", (-0.36, 0.02, 0.88), (0.3, 0.2, 1), (0, 1, 0)), lhand=(0.40, 0.10, 0.86))
    d1 = make(rig, ((0, 0.06, -0.14), E(10, 0, -2)), E(12, 0, 2), E(10, 0, 2), (0, 18), FOOT_L, ((-0.14, 0.2, 0.085), E(0, 0, -12)),
              *tp("d1", (-0.20, -0.20, 0.62), (0.3, -0.6, -0.7), (0, -0.7, 0.6)), lhand=(0.10, -0.18, 0.70))
    d2 = make(rig, ((0, 0.02, -0.30), E(18, 0, -2)), E(14, 0, 2), E(12, 0, 2), (0, 24),
              ((0.13, -0.04, 0.085), E(0, 0, 6)), ((-0.14, 0.24, 0.085), E(30, 0, -12)),
              *tp("d2", (-0.30, -0.22, 0.36), (0.5, -0.5, -0.7), (0, -0.7, 0.5)), lhand=(0.12, -0.24, 0.44))
    d3 = make(rig, ((0, -0.02, -0.33), E(30, 0, -4)), E(12, 0, 0), E(10, 0, 2), (0, 28),
              ((0.13, 0.28, 0.07), E(78, 0, 8)), ((-0.15, 0.36, 0.07), E(78, 0, -12)),
              *tp("d3", (-0.36, -0.30, 0.22), (0.7, -0.3, -0.4), (0, -0.5, 0.8)), lhand=(0.24, -0.34, 0.30),
              kneeL=(0.2, -1.0, -0.3), kneeR=(-0.25, -1.0, -0.3))
    d5 = make(rig, ((0, -0.14, -0.37), E(86, 0, -8)), E(-6, 0, 0), E(-4, 0, 0), E(-24, 0, 30),
              ((0.13, 0.26, 0.11), E(150, 0, 10)), ((-0.15, 0.30, 0.14), E(140, 0, -14)),
              *tp("d5", (-0.36, -0.60, 0.10), (0.95, -0.2, 0.0), (0, 0, 1)), lhand=(0.30, -0.56, 0.10),
              kneeL=(0.2, 0.05, -1.2), kneeR=(-0.25, 0.05, -1.2), elbowL=(1.2, -0.2, 0.5), elbowR=(-1.2, -0.2, 0.5))
    d7 = make(rig, ((0, -0.15, -0.38), E(90, 0, -10)), E(-2, 0, -2), E(0, 0, 0), E(-14, 4, 50),
              ((0.13, 0.27, 0.075), E(168, 0, 14)), ((-0.18, 0.2, 0.075), E(160, 0, -30)),
              *tp("d7", (-0.36, -0.62, 0.085), (0.95, -0.2, 0.0), (0, 0, 1)), lhand=(0.32, -0.58, 0.085),
              kneeL=(0.2, 0.05, -1.2), kneeR=(-0.8, 0.0, -0.6), elbowL=(1.2, -0.2, 0.3), elbowR=(-1.2, -0.1, 0.3))
    d4 = pose_lerp(d3, d5, 0.5)
    d6 = pose_lerp(d5, d7, 0.7)
    rig.key_all([d0, d1, d2, d3, d4, d5, d6, d7])
