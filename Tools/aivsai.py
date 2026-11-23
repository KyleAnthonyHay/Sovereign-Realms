#!/usr/bin/env python3
"""Computer against computer on a battle map, for balance (README: The battle > Computer against computer).

    python3 Tools/aivsai.py run  [--map L_RealmV2] [--tag base] [--minutes 40] [--fps 20] [--scale 1] MATCHUP ...
    python3 Tools/aivsai.py report [--tag base] [--since YYYYmmdd-HHMMSS]

  MATCHUP   <team0>v<team1> by difficulty letter, e.g. HvH NvN HvN NvH (E Easy, N Normal, H Hard); "xN" after it
            repeats it (HvHx3)
  run       each match is a separate headless run of the game (the editor's binary with -game -nullrhi, a fixed time
            step of 1/fps s times the time scale, as fast as the machine goes): the map opened with
            ?Match=1?Difficulty=<team1>?AIvsAI=<team0>?MaxMinutes=..?Quit=1?Tag=..; the match log (vl.MatchLog,
            VLMatchLog.*) is written to Saved/Balance/ and the game quits. Only one Unreal process may run at a time:
            take Saved/editor.lock first (mkdir), and quit the editor.
  report    the matches in Saved/Balance/matches.csv (by tag): wins by side and difficulty, lengths, then per match the
            economy (gold / food earned, lost to full stores, spent), what was built and when, troops trained and lost
            by kind, attacks.
"""
import csv
import glob
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UE = os.environ.get("UE_ROOT", "/Users/Shared/Epic Games/UnrealInstall/UE_5.8") + "/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor"
BAL = os.path.join(ROOT, "Saved", "Balance")
LETTER = {"E": 0, "N": 1, "H": 2}
NAME = {0: "Easy", 1: "Normal", 2: "Hard"}


def opt(args, name, default):
    if name in args:
        i = args.index(name)
        v = args[i + 1]
        del args[i:i + 2]
        return v
    return default


def run_one(mapname, d0, d1, tag, minutes, fps, scale, n):
    os.makedirs(os.path.join(BAL, "logs"), exist_ok=True)
    log = os.path.join(BAL, "logs", "%s_%s_%sv%s_%d.log" % (tag, mapname, NAME[d0], NAME[d1], n))
    url = "/Game/Maps/%s?Match=1?Difficulty=%d?AIvsAI=%d?MaxMinutes=%g?Quit=1?Tag=%s%s" % (
        mapname, d1, d0, minutes, tag, "?TimeScale=%g" % scale if scale != 1 else "")
    cmd = [UE, os.path.join(ROOT, "SovereignRealms.uproject"), url, "-game", "-nullrhi", "-nosound", "-unattended", "-nosplash",
           "-benchmark", "-fps=%d" % fps, "-abslog=" + log]
    before = set(glob.glob(os.path.join(BAL, "*.json")))
    t0 = time.time()
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # a match of `minutes` at fps frames a second: give it an hour of wall time at most
    limit = 3600
    while p.poll() is None and time.time() - t0 < limit:
        time.sleep(5)
    if p.poll() is None:
        p.kill()
        print("  killed after %.0f s (no end)" % (time.time() - t0))
    new = sorted(set(glob.glob(os.path.join(BAL, "*.json"))) - before)
    if not new:
        print("  no match log written (see %s)" % log)
        return None
    with open(new[-1]) as f:
        m = json.load(f)
    print("  %s: %s v %s -> %s (%s) after %s, %.0f s of wall time" % (os.path.basename(new[-1]), m["difficulty"][0], m["difficulty"][1],
          {0: "team 0", 1: "team 1", -1: "draw"}[m["winner"]], m["reason"], clock(m["duration"]), time.time() - t0))
    return m


def clock(s):
    s = int(round(s))
    return "%d:%02d" % (s // 60, s % 60)


def cmd_run(args):
    mapname = opt(args, "--map", "L_RealmV2")
    tag = opt(args, "--tag", "base")
    minutes = float(opt(args, "--minutes", "40"))
    fps = int(opt(args, "--fps", "30"))
    scale = float(opt(args, "--scale", "1"))
    jobs = []
    for a in args:
        rep = 1
        if "x" in a:
            a, r = a.split("x")
            rep = int(r)
        d0, d1 = LETTER[a[0].upper()], LETTER[a[2].upper()]
        jobs += [(d0, d1)] * rep
    for n, (d0, d1) in enumerate(jobs):
        print("match %d of %d: team 0 %s against team 1 %s on %s" % (n + 1, len(jobs), NAME[d0], NAME[d1], mapname))
        run_one(mapname, d0, d1, tag, minutes, fps, scale, n)


def load(tag=None, since=None):
    out = []
    for p in sorted(glob.glob(os.path.join(BAL, "*.json"))):
        try:
            with open(p) as f:
                m = json.load(f)
        except Exception:
            continue
        if tag and m.get("tag") != tag:
            continue
        if since and os.path.basename(p) < since:
            continue
        out.append(m)
    return out


def at(m, t, team):
    best = None
    for s in m["samples"]:
        if s["t"] <= t + 0.5:
            best = s["teams"][team]
    return best


def cmd_report(args):
    tag = opt(args, "--tag", None)
    since = opt(args, "--since", None)
    ms = load(tag, since)
    if not ms:
        print("no matches")
        return
    print("%d match(es)%s" % (len(ms), " tagged " + tag if tag else ""))
    by = {}
    for m in ms:
        k = "%s v %s" % tuple(m["difficulty"])
        r = by.setdefault(k, [0, 0, 0, []])
        r[{0: 0, 1: 1, -1: 2}[m["winner"]]] += 1
        r[3].append(m["duration"])
    print("%-18s %6s %6s %6s  %s" % ("team0 v team1", "t0 win", "t1 win", "draw", "lengths"))
    for k, r in sorted(by.items()):
        print("%-18s %6d %6d %6d  %s" % (k, r[0], r[1], r[2], " ".join(clock(x) for x in r[3])))
    for m in ms:
        print()
        print("== %s: %s v %s, %s (%s) at %s" % (m["id"], m["difficulty"][0], m["difficulty"][1],
              {0: "team 0 won", 1: "team 1 won", -1: "draw"}[m["winner"]], m["reason"], clock(m["duration"])))
        for t in (0, 1):
            f = m["final"][t]
            last = m["samples"][-1]["teams"][t]
            print("  team %d: trained %d swordsmen %d archers, lost %d / %d, killed %d, buildings lost %d, attacks %d (first %s), raids %d" % (
                t, f["trained_swordsmen"], f["trained_archers"], f["lost_swordsmen"], f["lost_archers"], f["killed"], f["buildings_lost"],
                f["attacks"], clock(f["first_attack"]) if f["first_attack"] >= 0 else "-", f["raids"]))
            print("          earned %d gold %d food, lost to full stores %d / %d, spent %d / %d; castle %d" % (
                last["earned"][0], last["earned"][1], last["wasted"][0], last["wasted"][1], last["spent"][0], last["spent"][1], last["castle"]))
            row = []
            for mm in (2, 4, 6, 8, 10, 15, 20, 30, 40):
                s = at(m, mm * 60, t)
                if s and mm * 60 <= m["duration"]:
                    b = s["buildings"]
                    row.append("%d' g%d f%d +%d/+%d %ds%da f%dm%db%dr%dt%d" % (mm, s["gold"], s["food"], s["gold_min"], s["food_min"],
                               s["alive"]["swordsman"], s["alive"]["archer"], b["farms"], b["mines"], b["barracks"], b["ranges"], b["towers"]))
            print("          " + " | ".join(row))
            built = ["%s %s" % (clock(e["t"]), e["what"]) for e in m["events"] if e["team"] == t and e["type"] in ("built", "claim")]
            print("          built: " + ", ".join(built[:24]))
            att = ["%s %s %s (%s)" % (clock(e["t"]), e["type"], e["what"], e["detail"]) for e in m["events"] if e["team"] == t and e["type"] in ("attack", "flank", "attack_end")]
            print("          attacks: " + "; ".join(att[:12]))


def main(a):
    if not a or a[0] not in ("run", "report"):
        print(__doc__)
        return 1
    (cmd_run if a[0] == "run" else cmd_report)(a[1:])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
