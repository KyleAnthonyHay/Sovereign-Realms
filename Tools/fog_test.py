#!/usr/bin/env python3
"""The fog of war (UVLFog, VLFog.*) in Play-In-Editor: PIE running (python Tools/pie.py start), any map.

    Tools/.venv/Scripts/python Tools/fog_test.py [realmv3] [realmv2] [perf]
    Tools/.venv/Scripts/python Tools/fog_test.py views <suffix> [realmv3] [realmv2]

For each map: opens it (vl.Map), starts a match, and
  - logs the fog's state at the start (vl.Fog.Info: visible / explored share) and every eye (vl.Fog.Eyes: the towers'
    view radius against 1.35 x their reach);
  - puts King David on the basin floor / low ground, on the plateau's (or a terrace's) edge, and on a tower's lookout
    height, and logs his view radius each time (it must grow with the height over the ground round);
  - spawns an enemy swordsman next to him and one far off, and logs how many units the fog hides;
  - screenshots Saved/Screenshots/VL/fog_<map>_*.png from the default (overview) camera and the hero camera, and the
    minimap with the interface.
perf: ProfileGPU with vl.Fog 0 and 1 at the same view (Tools/gpuprof.py's parse), the post-process material's pass.
"""
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "Tools"))
import pie

# UE cm (the json's metres: x * 100, -y * 100)
MAPS = {
    "realmv3": dict(home=(-13000, -13800, 1400), low=(0, 0, 400), edge=(-7800, -7200, 1400), tower=(-16800, -10000, 1400),
                    enemy_far=(13000, 13800), look=(-13000, -12000), towers=(11000, 9000),
                    mist=(-7800, -7200, 2300, -9, 47)),
    "realmv2": dict(home=(-17600, 12800, 0), low=(-15400, 13600, 0), edge=(2400, 1200, 1200), tower=(-22100, 8000, 0),
                    enemy_far=(23800, -15200), look=(-17600, 11000), towers=(25000, -17000),
                    mist=(-15000, 9000, 2600, -8, -31)),
}


def log_since(mark, pattern):
    out = []
    with open(pie.LOG, encoding="utf-8", errors="replace") as f:
        f.seek(mark)
        for l in f:
            if re.search(pattern, l):
                out.append(re.sub(r"^\[[^\]]*\]\[[ \d]*\]", "", l.rstrip()))
    return out


def cmd(cmds, pattern=None, wait=0.8):
    mark = os.path.getsize(pie.LOG)
    pie.run(cmds)
    time.sleep(wait)
    if pattern:
        lines = log_since(mark, pattern)
        for l in lines:
            print("   ", l.split("LogSovereignRealms: ")[-1])
        return lines
    return []


def radius(lines):
    for l in lines:
        m = re.search(r"sees ([\d.]+) m mean, ([\d.]+) min, ([\d.]+) max \(eye ([\d.]+) m", l)
        if m:
            return [float(v) for v in m.groups()]
    return None


def one_map(name):
    P = MAPS[name]
    print("== %s" % name)
    cmd(["vl.Map " + name], None, 45)
    cmd(["vl.StartMatch 0"], None, 6)
    cmd(["vl.Fog.Info"], r"fog: ")
    cmd(["vl.Fog.Eyes"], r"fog eye: .*Watch Tower|fog eye: .*Castle")
    cmd(["vl.Mode overview", "vl.Look %d %d 0.85" % P["look"]], None, 3)
    pie.main(["shot", "fog_%s_start" % name, "2.5"])
    cmd(["vl.Shot fog_%s_minimap ui" % name], None, 3)
    res = {}
    for where in ("low", "edge", "tower"):
        x, y, z = P[where]
        zz = z + (1050 + 120 if where == "tower" else 120)
        # (the tower: the king put at its lookout's floor, 10.5 m up, and read before he falls off it)
        cmd(["vl.Mode hero", "vl.Teleport %d %d %d" % (x, y, zz)], None, 2.0 if where != "tower" else 0.25)
        lines = cmd(["vl.Fog.Info"], r"fog: played", 0.4)
        res[where] = radius(lines)
        if where != "tower":
            cmd(["vl.View follow"], None, 1.5)
            pie.main(["shot", "fog_%s_hero_%s" % (name, where), "1.5"])
    print("  radius (mean, min, max, eye):", res)
    # the enemy's towers' tips out of the fog: from the overview, and from a hero-height camera over the low ground
    cmd(["vl.Mode overview", "vl.Look %d %d 0.6" % P["towers"]], None, 3)
    pie.main(["shot", "fog_%s_towers" % name, "2.5"])
    cmd(["vl.Mode hero", "vl.View free %d %d %d %d %d 60" % P["mist"]], None, 2)
    pie.main(["shot", "fog_%s_hero_mist" % name, "2.5"])
    cmd(["vl.View follow"], None, 0.5)
    # enemies: one beside the king, one far off
    x, y, z = P["low"]
    cmd(["vl.Teleport %d %d %d" % (x, y, z + 120)], None, 1.5)
    cmd(["vl.SpawnTeam Swordsman 1 %d %d" % (x + 900, y), "vl.SpawnTeam Swordsman 1 %d %d" % P["enemy_far"]], None, 1.5)
    cmd(["vl.Fog.Info"], r"fog: (on|off)")
    cmd(["vl.Mode overview", "vl.Look %d %d 0.6" % (x, y)], None, 3)
    pie.main(["shot", "fog_%s_enemy_near" % name, "1.5"])
    return res


def views(name, suffix):
    """The same views before and after a change of the look: the default overview zoom over home (with a patch of
    explored ground beside it) and over the enemy's towers, the furthest overview, and the hero camera's height."""
    P = MAPS[name]
    print("== %s views (%s)" % (name, suffix))
    cmd(["vl.Map " + name], None, 45)
    cmd(["vl.StartMatch 0"], None, 6)
    x, y, z = P["low"]
    cmd(["vl.Mode hero", "vl.Teleport %d %d %d" % (x, y, z + 120)], None, 1.5)      # (explored ground out there)
    hx, hy, hz = P["home"]
    cmd(["vl.Teleport %d %d %d" % (hx, hy, hz + 120)], None, 1.5)
    shots = [
        ("overview", ["vl.Mode overview", "vl.Look %d %d 0.18" % P["look"]]),
        ("overview_towers", ["vl.Mode overview", "vl.Look %d %d 0.18" % P["towers"]]),
        ("overview_far", ["vl.Mode overview", "vl.Look %d %d 1.0" % P["look"]]),
        ("hero", ["vl.Mode hero", "vl.View follow"]),
        ("hero_mist", ["vl.Mode hero", "vl.View free %d %d %d %d %d 60" % P["mist"]]),
    ]
    for tag, c in shots:
        cmd(c, None, 3)
        pie.main(["shot", "fog_%s_%s_%s" % (name, tag, suffix), "1.5"])
    cmd(["vl.View follow"], None, 0.5)


def perf(name):
    P = MAPS[name]
    cmd(["vl.Mode overview", "vl.Look %d %d 0.6" % P["look"]], None, 3)
    for on in (0, 1, 0, 1):
        cmd(["vl.Fog %d" % on, "r.ProfileGPU.ShowUI 0"], None, 2)
        mark = os.path.getsize(pie.LOG)
        cmd(["ProfileGPU"], None, 4)
        lines = log_since(mark, r"LogRHI: Display:.*┃")
        rows = []
        for l in lines:
            parts = l.split("┃")
            if len(parts) >= 4:
                ms = re.findall(r"([\d.]+) ms", parts[2])
                if ms:
                    rows.append((float(ms[-1]), parts[3].strip()))
        frame = [r for r in rows if r[1].startswith("Frame")]
        fog = [r for r in rows if r[1].startswith("PostProcessMaterial") and "FogOfWar" in r[1]]
        print("  vl.Fog %d: frame %s ms, fog pass %s" % (on, frame[0][0] if frame else "?", ", ".join("%.3f ms (%s)" % r for r in fog) or "none"))
    cmd(["vl.Fog 1"], None, 0.5)


if __name__ == "__main__":
    which = sys.argv[1:] or ["realmv3", "realmv2"]
    if which[0] == "views":
        for m in which[2:] or ["realmv3", "realmv2"]:
            views(m, which[1])
        sys.exit(0)
    for w in which:
        if w == "perf":
            continue
        one_map(w)
        if "perf" in which:
            perf(w)
