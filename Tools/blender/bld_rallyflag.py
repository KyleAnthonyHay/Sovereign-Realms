"""The castle's rally flag: a short pole in a stone footing with a team-coloured pennon. Unreal cm, front toward -X."""
NAME = "rallyflag"
MESH = "SM_Bld_RallyFlag"
SEED = 5
FOOTPRINT = [-30.0, -30.0, 30.0, 30.0]
RING_RADIUS = 60.0
PREVIEW_FIGURES = [(-120, 80)]


def build(k):
    for (x, y, s) in ((10, 8, 30), (-12, 4, 24), (2, -14, 22)):
        k.blob("Bld_Rock", (x, y, 4), (s, s, s * 0.7), points=9)
    k.cyl("Bld_Beam", (0, 0, -4), (0, 0, 196), 4.5, 3.5, sides=6)
    k.cyl("Bld_Bronze", (0, 0, 196), (0, 0, 210), 5.5, 0.6, sides=6)
    k.obox("Bld_Beam", (0, 0, 178), (5, 76, 5), grain="y")
    k.hang_cloth((-3, -32, 175), (-3, 32, 175), 104.0)
    k.sockets["label"] = (0.0, 0.0, 220.0)
