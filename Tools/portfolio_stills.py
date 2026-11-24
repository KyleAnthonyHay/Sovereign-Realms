#!/usr/bin/env python3
"""Portfolio stills (Saved/Portfolio): single 4K frames from the packaged Development build.

The game runs at the screen's own 3840 x 2160 (vl.Shot saves the window's backbuffer, so that is the still's size):
    Builds/Windows/SovereignRealms-Development/SovereignRealms.exe /Game/Maps/L_RealmV3?Match=1?Difficulty=0
        -windowed -ResX=3840 -ResY=2160 -VLNoEnter
    VL_SAVED=Builds/Windows/SovereignRealms-Development/SovereignRealms/Saved

    python Tools/portfolio_stills.py <shot> [...]     each shot to Saved/Portfolio/_work/raw/<shot>.png, or, for an
                                                      action shot, a burst of frames to _work/burst/<shot>/ to pick from
    python Tools/portfolio_stills.py finish <src.png> <final_name> [ui]
                                                      a final: Saved/Portfolio[/gameplay_ui]/<final_name>.png + .jpg (q 92)

The clean shots: HUD hidden, vl.Opt.Silhouette 0, vl.Opt.HitFlash 0, vl.Music 0, fog of war off (vl.Fog 0). The
gameplay shots ("ui_*"): the HUD on (vl.Shot <name> ui), the same two capture variables. Camera keys: plan metres
(+X east, +Y north, +Z up), as Tools/showreel*.py. Battle staging, the castle's assault and the ship are reused from
Tools/showreel2_shots.py.
"""
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("VL_SAVED", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                               "Builds", "Windows", "SovereignRealms-Development", "SovereignRealms", "Saved"))
import showreel as R          # noqa: E402
R.SAVED = os.environ["VL_SAVED"]
R.INBOX = os.path.join(R.SAVED, "VLCommands.txt")
R.SHOTS_DIR = os.path.join(R.SAVED, "Screenshots", "VL")
import showreel2_shots as S2  # noqa: E402
import showreel_shots as S1   # noqa: E402

U = S2.U
PORT = os.path.join(R.ROOT, "Saved", "Portfolio")
RAW = os.path.join(PORT, "_work", "raw")
BURST = os.path.join(PORT, "_work", "burst")
CLEAN = ["vl.Fog 0", "vl.Music 0", "vl.Opt.HitFlash 0", "vl.Opt.Silhouette 0"]
MIDDAY = ["vl.Sun reset", "vl.Opt.Clouds 1"]
GOLDEN = ["vl.Sun -11 35 7 4300", "vl.Opt.Clouds 0"]


def V(c, t, fov=50.0):
    return R.view_cmd(c, t, fov)


def hud(on):
    s = S2.state()
    if s.get("hud", True) != on:
        R.send(["ShowHUD"])
        s["hud"] = on
        S2.save_state(s)


def snap(name, settle=3.0, ui=False):
    """one still of the view as it is now, to _work/raw/<name>.png"""
    if R.hot():
        wait_cool()
    path = os.path.join(R.SHOTS_DIR, name + ".png")
    if os.path.exists(path):
        os.remove(path)
    time.sleep(settle)
    R.send(["vl.Shot %s%s" % (name, " ui" if ui else "")])
    end = time.time() + 30
    while not os.path.exists(path) and time.time() < end:
        time.sleep(0.1)
    time.sleep(1.0)
    os.makedirs(RAW, exist_ok=True)
    if os.path.exists(path):
        dst = os.path.join(RAW, name + ".png")
        shutil.move(path, dst)
        print(dst)
    else:
        print("no screenshot for", name)


def burst(name, frames, at, step=30, settle=1.0, first=None):
    """frames at a fixed time step (vl.Record), to _work/burst/<name>/f_NNNN.png"""
    if R.hot():
        wait_cool()
    R.FRAMES = BURST
    os.makedirs(BURST, exist_ok=True)
    return R.record(name, frames, at, step, settle, first)


def wait_cool():
    print("OVERHEAT.flag is up: waiting")
    while R.hot():
        time.sleep(30)


SHOTS = {}


def shot(fn):
    SHOTS[fn.__name__] = fn
    return fn


def scene(views, look=MIDDAY, ui=False, settle=3.0):
    """static shots: [(name, cam, target, fov)]"""
    hud(ui)
    R.send(CLEAN + look)
    for name, c, t, fov in views:
        R.send([V(c, t, fov)])
        snap(name, settle, ui)


def main(a):
    if not a:
        print(__doc__)
        print("shots:", " ".join(sorted(SHOTS)))
        return 0
    if a[0] == "send":
        R.send(a[1:])
        return 0
    if a[0] == "finish":
        finish(a[1], a[2], len(a) > 3 and a[3] == "ui")
        return 0
    if a[0] == "look":
        v = [float(x) for x in a[1:]]
        R.send([V(v[0:3], v[3:6], v[6] if len(v) > 6 else 50.0)])
        return 0
    if a[0] == "snap":
        snap(a[1], 3.0, len(a) > 2 and a[2] == "ui")
        return 0
    import portfolio_shots as PS   # the shot list (it registers itself with its own import of this module)
    for n in a:
        PS.P.SHOTS[n]()
    return 0


def finish(src, final, ui=False):
    from PIL import Image
    d = os.path.join(PORT, "gameplay_ui") if ui else PORT
    os.makedirs(d, exist_ok=True)
    im = Image.open(src).convert("RGB")
    im.save(os.path.join(d, final + ".png"), optimize=False)
    im.save(os.path.join(d, final + ".jpg"), quality=92, subsampling=0, optimize=True)
    print(os.path.join(d, final + ".png"), im.size)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
