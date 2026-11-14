"""Animation helpers shared by the characters: root-space hand authoring, head look-at, the run cycle.

All poses are plain dicts (see srkit.Rig.key). Hands are IK targets parented to the chest, which is what makes
a guard stance breathe and twist with the torso for free; `hands()` lets a pose still be authored in character
space ("sword hand HERE, blade pointing THERE") by converting through the posed chest transform.
"""

import math

from mathutils import Matrix, Quaternion, Vector

from srkit import E, aim, pose_lerp, pose_merge, smooth  # noqa: F401


# World height that moves the sprite by exactly one pixel at the default render (1.75 cm / px, 30 degrees).
# The idle is authored in whole-pixel steps so the breathing never makes the shading crawl.
PX_Z = 0.0175 / math.cos(math.radians(30.0))

# idle beats, 8 frames: torso rises on 2 and drops on 5; the hands follow one frame late; the weapon settles after
IDLE_UP = [0, 0, 1, 1, 1, 0, 0, 0]
IDLE_HAND_LAG = [0, 0, -1, 0, 0, 1, 0, 0]
IDLE_TILT = [0.0, 0.0, 0.0, 0.6, 1.0, 1.0, 0.5, 0.0]
IDLE_SWAY = [0.0, -0.6, 0.3, 1.0, 0.6, -0.4, -1.0, -0.3]


def _delta(rig, name, spec):
    h = rig.rest_head[name]
    t = Vector(spec.get("loc", (0, 0, 0)))
    r = spec.get("rot", Quaternion()).to_matrix().to_4x4()
    return Matrix.Translation(h + t) @ r @ Matrix.Translation(-h)


def chest_matrix(rig, pose):
    m = Matrix.Identity(4)
    for b in ("root", "hips", "spine", "chest"):
        m = m @ _delta(rig, b, pose.get(b, {}))
    return m


def hands(rig, pose, specs):
    """specs: {bone: {'pos': character-space point, 'rot': character-space rotation}} for chest-parented controls."""
    m = chest_matrix(rig, pose)
    mi = m.inverted()
    qi = m.to_quaternion().inverted()
    for bone, spec in specs.items():
        out = dict(pose.get(bone, {}))
        if "pos" in spec:
            out["pos"] = tuple(mi @ Vector(spec["pos"]))
        if "rot" in spec:
            out["rot"] = qi @ spec["rot"]
        pose[bone] = out
    return pose


def chest_heading(rig, pose):
    f = chest_matrix(rig, pose).to_3x3() @ Vector((0, -1, 0))
    yaw = math.degrees(math.atan2(f.x, -f.y))
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, -f.z))))
    return yaw, pitch


def look(rig, pose, yaw=0.0, pitch=-8.0, roll=0.0, follow=0.75):
    """Point the head at a character-space yaw / pitch regardless of what the torso is doing."""
    cy, cp = chest_heading(rig, pose)
    pose["head"] = dict(pose.get("head", {}), rot=E(pitch - follow * cp, roll, yaw - cy))
    return pose


def seq(keys, n):
    """keys: [(frame, pose)] sorted. Returns n poses, linear between keys (ease in the keys themselves)."""
    out = []
    for f in range(n):
        prev = max((k for k in keys if k[0] <= f), key=lambda k: k[0])
        nxt = min((k for k in keys if k[0] >= f), key=lambda k: k[0])
        if prev[0] == nxt[0]:
            out.append(pose_merge(prev[1]))
        else:
            out.append(pose_lerp(prev[1], nxt[1], (f - prev[0]) / (nxt[0] - prev[0])))
    return out


# ------------------------------------------------------------------------------------------------ run cycle

def run_legs(phase, step, ankle_z, lift=0.13, side=1, foot_x=0.14, toe_out=6.0):
    """Foot target for one leg of an 8-frame run. phase 0 = this foot's contact.

    Stance covers phase 0, 1/8, 2/8: the foot is on the ground and moves back exactly `step` per frame, which is
    the distance the body travels per frame, so there is no sliding. The other five frames are the swing.
    """
    p = phase % 1.0
    if p <= 0.25 + 1e-6:
        y = -step + step * (p / 0.125)
        if p < 0.06:
            rx, z = -16.0, 0.012          # heel strike, toes up
        elif p < 0.19:
            rx, z = 0.0, 0.0              # flat, weight on it
        else:
            rx, z = 22.0, 0.028           # heel peeling off
    else:
        u = (p - 0.25) / 0.75
        y = step * math.cos(math.pi * u) + 0.35 * step * math.sin(math.pi * u) * (1 - u) ** 2
        z = 0.028 + lift * math.sin(math.pi * min(u / 0.85, 1.0) ** 0.8) * (1.0 if u < 0.85 else 0.0)
        if u >= 0.85:
            z = 0.02
        rx = 55.0 * (1 - u) ** 1.2 - 22.0 * u ** 2
    return {"pos": (side * foot_x, y, ankle_z + z), "rot": E(rx, 0, side * toe_out)}


def run_body(i, n=8, bob=0.028, drop=-0.05, lean=9.0, sway=0.014, yaw=9.0, roll=3.5, counter=1.7):
    """Hips / spine / chest for frame i of the run. Left foot contacts on frame 0, right on frame n/2."""
    ph = i / n
    two = 2 * math.pi * 2 * ph
    one = 2 * math.pi * ph
    z = drop - bob * math.cos(two - 2 * math.pi * 0.25)          # lowest one frame after each contact
    x = sway * math.sin(one + math.pi / 4)                        # over the stance leg
    hy = -yaw * math.cos(one)                                     # leading hip forward
    hr = -roll * math.sin(one + math.pi / 4)                      # swing-side hip drops
    return {
        "hips": {"loc": (x, 0.0, z), "rot": E(lean * 0.45, hr, hy)},
        "spine": {"rot": E(lean * 0.35, -hr * 0.8, -hy * counter * 0.6)},
        "chest": {"rot": E(lean * 0.2, 0, -hy * counter * 0.4)},
    }
