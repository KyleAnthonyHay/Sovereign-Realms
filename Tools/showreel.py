#!/usr/bin/env python3
"""Scripted camera moves, recorded frame by frame, for the showreel (Saved/Showreel).

The game (the packaged Development build, or PIE) polls Saved/VLCommands.txt. A shot here is a list of camera keys;
the path between them is a Catmull-Rom spline through the positions and the look-at points, its clock eased in and
out, sampled once a frame into `vl.At <frame> vl.View free ...` lines, and `vl.Record` saves one screenshot a frame at
a fixed time step (the motion is perfectly even however slowly the frames really render).

    python Tools/showreel.py send "<cmd>" ...                 console commands
    python Tools/showreel.py shot <name> [settle]             one still, Saved/Showreel/stills/<name>.png
    python Tools/showreel.py look x y z tx ty tz [fov]        a free camera, plan metres (+Y north) looking at a point
    python Tools/showreel.py rec <shot> [...]                 record shots (showreel_shots.py) into Saved/Showreel/frames/<shot>

The game: the packaged Development build, started straight into a match and with nobody to press Enter:
    Saved/StagedBuilds/Windows/SovereignRealms.exe /Game/Maps/L_RealmV3?Match=1?Difficulty=0 -windowed -ResX=1920 -ResY=1080 -VLNoEnter
then `send ShowHUD "vl.Fog 0" "vl.Music 0"` (the shots that restart the match do that themselves). Realm v2's shot:
`send "vl.Map realmv2"`, then `send "vl.StartMatch 0"` and the same three. Shots: Tools/showreel_shots.py; the edit:
Tools/showreel_edit.py.

Positions are the maps' plan metres (+X east, +Y north, +Z up); Unreal's are cm with Y south.
SAVED: $VL_SAVED, else the packaged game's (Saved/StagedBuilds/Windows/SovereignRealms/Saved).
"""
import glob
import math
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVED = os.environ.get("VL_SAVED") or os.path.join(ROOT, "Saved", "StagedBuilds", "Windows", "SovereignRealms", "Saved")
INBOX = os.path.join(SAVED, "VLCommands.txt")
SHOTS_DIR = os.path.join(SAVED, "Screenshots", "VL")
OUT = os.path.join(ROOT, "Saved", "Showreel")
FLAG = r"C:\Dev\ThermalWatchdog\OVERHEAT.flag"
STILLS = os.environ.get("VL_STILLS") or os.path.join(OUT, "stills")
FRAMES = os.path.join(OUT, "frames")      # where a recording's frames go (Tools/showreel2_shots.py points it per reel)


def hot():
    return os.path.exists(FLAG)


def send(cmds, timeout=30.0):
    tmp = INBOX + ".tmp"
    with open(tmp, "w", newline="\n") as f:
        f.write("\n".join(cmds) + "\n")
    os.replace(tmp, INBOX)
    end = time.time() + timeout
    while os.path.exists(INBOX) and time.time() < end:
        time.sleep(0.05)
    if os.path.exists(INBOX):
        print("commands were not picked up (is the game running?)")
        return False
    return True


def view_cmd(c, t, fov, dpitch=0.0, dyaw=0.0):
    """vl.View free from a camera and a look-at point, plan metres (dpitch / dyaw: a hand's shake, degrees)."""
    dx, dy, dz = t[0] - c[0], t[1] - c[1], t[2] - c[2]
    yaw = math.degrees(math.atan2(-dy, dx)) + dyaw
    pitch = math.degrees(math.atan2(dz, math.hypot(dx, dy))) + dpitch
    return "vl.View free %.1f %.1f %.1f %.3f %.3f %.2f" % (c[0] * 100, -c[1] * 100, c[2] * 100, pitch, yaw, fov)


def _cr(p0, p1, p2, p3, u):
    # centripetal-free uniform Catmull-Rom (keys are spaced evenly enough)
    u2, u3 = u * u, u * u * u
    return tuple(0.5 * ((2 * b) + (-a + c) * u + (2 * a - 5 * b + 4 * c - d) * u2 + (-a + 3 * b - 3 * c + d) * u3)
                 for a, b, c, d in zip(p0, p1, p2, p3))


def spline(pts, s):
    """s in 0..1 along the keys (uniform per segment)."""
    n = len(pts)
    if n == 1:
        return tuple(pts[0])
    f = s * (n - 1)
    i = min(int(f), n - 2)
    u = f - i
    p0 = pts[max(i - 1, 0)]
    p3 = pts[min(i + 2, n - 1)]
    p1, p2 = pts[i], pts[i + 1]
    if i == 0:
        p0 = tuple(2 * a - b for a, b in zip(p1, p2))
    if i + 2 > n - 1:
        p3 = tuple(2 * b - a for a, b in zip(p1, p2))
    return _cr(p0, p1, p2, p3, u)


def ease(s, kind="inout", k=2.0):
    if kind == "linear":
        return s
    if kind == "in":
        return s ** k
    if kind == "out":
        return 1 - (1 - s) ** k
    # smooth in-out with a linear middle when k is small: a blend of smootherstep and linear
    sm = s * s * s * (s * (s * 6 - 15) + 10)
    return (1 - 1 / k) * sm + (1 / k) * s if k > 1 else sm


def shake(i, fps, amp, hz, seed=0):
    """A hand-held camera's wander: (dx, dy, dz, dpitch, dyaw) at frame i; amp = (metres, degrees). Sums of sines at
    unrelated rates (smooth, never repeating within a shot), plus a faster, smaller tremor."""
    t = i / float(fps)
    out = []
    for k in range(5):
        v = 0.0
        for j, (f, w) in enumerate(((1.0, 1.0), (1.73, 0.55), (2.91, 0.3), (5.3, 0.12))):
            ph = math.sin((seed + 1) * 12.9898 + k * 78.233 + j * 37.719) * 43758.5453
            ph = (ph - math.floor(ph)) * 2 * math.pi
            v += w * math.sin(2 * math.pi * hz * f * t + ph)
        out.append(v / 1.4 * (amp[0] if k < 3 else amp[1]))
    return out


def path_cmds(cam, frames, easing="inout", k=2.0, fps=30, seed=0):
    """cam: dict(pos=[...], look=[...], fov=[...]) of keys, and optionally shake=(metres, degrees, hz); returns one
    vl.View per frame."""
    out = []
    sh = cam.get("shake")
    for i in range(frames):
        s = ease(i / max(frames - 1, 1), easing, k)
        c = spline(cam["pos"], s)
        if "ahead" in cam:
            # look where the path goes: a point further along it (past the end: straight on), dropped by `drop` m
            d, drop = cam["ahead"]
            a, b = spline(cam["pos"], min(s + d, 1.0)), None
            if s + d > 1.0:
                b = spline(cam["pos"], 1.0 - 1e-3)
                e = spline(cam["pos"], 1.0)
                k = (s + d - 1.0) / 1e-3
                a = tuple(ei + (ei - bi) * k for ei, bi in zip(e, b))
            t = (a[0], a[1], a[2] - drop)
        else:
            t = spline(cam["look"], s) if len(cam["look"]) > 1 else cam["look"][0]
        fovs = cam.get("fov", [60.0])
        fov = spline([(f,) for f in fovs], s)[0] if len(fovs) > 1 else fovs[0]
        if sh:
            d = shake(i, fps, sh[:2], sh[2], seed)
            c = (c[0] + d[0], c[1] + d[1], c[2] + d[2])
            out.append(view_cmd(c, t, fov, d[3], d[4]))
        else:
            out.append(view_cmd(c, t, fov))
    return out


def record(name, frames, at, fps=30, settle=3.0, first=None):
    """at: list of (frame, command). Frames land in Saved/Showreel/frames/<name>/f_NNNN.png."""
    if hot():
        sys.exit("OVERHEAT.flag is up: stopping")
    for p in glob.glob(os.path.join(SHOTS_DIR, "sr_%s_*.png" % name)):
        os.remove(p)
    if first:
        send(first)
    time.sleep(settle)
    # vl.At runs same-frame commands last-given first: give them reversed so they run in order
    lines = []
    for f, c in sorted(at, key=lambda x: x[0]):
        lines.append((f, c))
    grouped = {}
    for f, c in lines:
        grouped.setdefault(f, []).append(c)
    out = []
    for f in sorted(grouped):
        for c in reversed(grouped[f]):
            out.append("vl.At %d %s" % (f, c))
    out.append("vl.Record sr_%s %d %d" % (name, frames, fps))
    # (one file: the game reads it at once; a few thousand lines are fine)
    send(out, timeout=60)
    last = os.path.join(SHOTS_DIR, "sr_%s_%03d.png" % (name, frames - 1))
    t0 = time.time()
    while not os.path.exists(last):
        if hot():
            sys.exit("OVERHEAT.flag is up: stopping")
        if time.time() - t0 > 60 + frames * 1.5:
            print("recording %s did not finish" % name)
            break
        time.sleep(0.25)
    time.sleep(0.8)
    dst = os.path.join(FRAMES, name)
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(dst)
    n = 0
    for i in range(frames):
        src = os.path.join(SHOTS_DIR, "sr_%s_%03d.png" % (name, i))
        if os.path.exists(src):
            shutil.move(src, os.path.join(dst, "f_%04d.png" % i))
            n += 1
    print("recorded %s: %d/%d frames in %.0f s" % (name, n, frames, time.time() - t0))
    return dst


def still(name, settle=2.5):
    path = os.path.join(SHOTS_DIR, name + ".png")
    if os.path.exists(path):
        os.remove(path)
    time.sleep(settle)
    send(["vl.Shot " + name])
    end = time.time() + 15
    while not os.path.exists(path) and time.time() < end:
        time.sleep(0.1)
    time.sleep(0.4)
    dst = STILLS
    os.makedirs(dst, exist_ok=True)
    if os.path.exists(path):
        shutil.move(path, os.path.join(dst, name + ".png"))
        print(os.path.join(dst, name + ".png"))
    else:
        print("no screenshot written")


def main(a):
    if not a:
        print(__doc__)
        return 0
    if a[0] == "send":
        return 0 if send(a[1:]) else 1
    if a[0] == "shot":
        still(a[1], float(a[2]) if len(a) > 2 else 2.5)
    elif a[0] == "look":
        v = [float(x) for x in a[1:]]
        send([view_cmd(v[0:3], v[3:6], v[6] if len(v) > 6 else 60.0)])
    elif a[0] == "rec":
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import showreel_shots as S
        for name in a[1:]:
            S.run(name)
    elif a[0] == "rec2":
        # the second and third reels' shots (Tools/showreel2_shots.py): frames to Saved/Showreel/<reel>/frames/<shot>
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import showreel2_shots as S2
        for name in a[1:]:
            S2.run(name)
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
