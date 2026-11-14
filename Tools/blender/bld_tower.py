"""The watchtower: a defensive tower the player builds. Authored in Unreal cm, front toward -X (bldkit.py).

A tall square sandstone shaft on a battered footing, a bronze-strapped door at its foot, arrow slits up the faces,
a corbelled fighting top with crow-stepped merlons, a timber hoarding gallery on beam ends overhanging the front, a
team-coloured glazed frieze under the parapet, a banner on the roof and a brazier for the night watch. Archers on
the top shoot at enemies within range (Sovereign Feel > Buildings > Tower).
"""
from bldkit import inset_ring, rect

NAME = "tower"
MESH = "SM_Bld_Tower"
SEED = 31
HALF = 200.0           # shaft half width at the base
H = 900.0              # parapet top
FOOTPRINT = [-220.0, -220.0, 220.0, 220.0]
RING_RADIUS = 320.0
PREVIEW_FIGURES = [(-330, 120), (-380, -90)]


def build(k):
    u0 = 12.0
    r0 = rect(-HALF, -HALF, HALF, HALF)
    # battered footing of big blocks
    r1 = k.wall("Bld_AshlarLarge", r0, 0, 36, inset=18, u0=u0, bleach=False)
    k.band("Bld_Trim", r1, 36, 44, out=4, u0=u0)
    side = 2 * (HALF - 18)
    ops = {
        2: [dict(a=side / 2 - 46, b=side / 2 + 46, z0=44, z1=214, depth=40, back="Bld_Door", reveal="Bld_AshlarLarge", shade=0.62, back_shade=0.8),
            dict(a=side / 2 - 6, b=side / 2 + 6, z0=420, z1=484, depth=14, back="Bld_Dark", shade=0.5)],
        0: [dict(a=side / 2 - 6, b=side / 2 + 6, z0=z, z1=z + 64, depth=14, back="Bld_Dark", shade=0.5) for z in (300, 520)],
        1: [dict(a=side / 2 - 6, b=side / 2 + 6, z0=360, z1=424, depth=14, back="Bld_Dark", shade=0.5)],
        3: [dict(a=side / 2 - 6, b=side / 2 + 6, z0=z, z1=z + 64, depth=14, back="Bld_Dark", shade=0.5) for z in (260, 480)]
           + [dict(a=side * 0.25, b=side * 0.25 + 30, z0=220, z1=236, depth=8, back="Bld_Dark", shade=0.55)],
    }
    top = H - 150
    r2 = k.wall("Bld_Ashlar", r1, 44, top, inset=10, u0=u0, openings=ops)
    # lintel and step at the door
    k.obox("Bld_Beam", (-HALF + 22, 0, 224), (24, 124, 18), grain="y")
    k.steps("Bld_AshlarLarge", -HALF - 60, -HALF + 18, -64, 64, 0, 44, 2, top="Bld_Trim")
    # corbelled fighting top
    k.band("Bld_Trim", r2, top, top + 12, out=10, u0=u0)
    r3 = inset_ring(r2, -22)
    k.cap("Bld_AshlarLarge", r3, top + 12, down=True, shade=0.55)
    k.wall("Bld_Frieze", r3, top + 12, top + 70, v0=0.0, bleach=False, u0=u0)
    k.wall("Bld_AshlarLarge", r3, top + 70, H - 40, u0=u0)
    k.parapet("Bld_Ashlar", r3, H - 40, H, thick=24, top="Bld_Trim")
    k.stepped_merlons("Bld_Ashlar", r3, H, width=48, gap=28, thick=24, h1=26, h2=22, broken=0.1, cap="Bld_Trim")
    # timber hoarding over the front: beam ends carrying a plank gallery with a rail
    hx = -HALF - 22
    k.beam_ends("Bld_Beam", (hx, -170), (hx, 170), top - 40, 4, size=(20, 20), out=60)
    k.obox("Bld_Planks", (hx - 36, 0, top - 22), (76, 380, 12), grain="y")
    k.obox("Bld_Beam", (hx - 70, 0, top + 40), (10, 380, 10), grain="y")
    for y in (-180, -60, 60, 180):
        k.obox("Bld_Beam", (hx - 70, y, top + 10), (10, 10, 60), grain="z")
    # banner on the roof, brazier at the parapet
    k.pole_banner((60, 70, H - 30), height=330, cloth_w=56, cloth_h=150)
    k.brazier((-40, -90, H - 30), h=70)
    # a few stones tumbled at the foot
    for x, y, s in ((-250, 150, 26), (-230, -170, 20), (150, -250, 22)):
        k.blob("Bld_Rock", (x, y, 4), (s * 2.2, s * 1.8, s * 1.4), points=8)
    k.collider((-220, -220, 0), (220, 220, H))
    k.sockets["label"] = (0.0, 0.0, H + 150.0)
    k.sockets["popup"] = (0.0, 0.0, 700.0)
    k.sockets["muzzle"] = (0.0, 0.0, H - 40.0)
