#!/usr/bin/env python3
"""Summarise captures of Unreal's CSV profiler (`csvprofile start` / `csvprofile stop`, Saved/Profiling/CSV/*.csv):
the numbers `stat unit` shows, averaged over the capture.

    python3 Tools/perf_csv.py <file.csv> [<file.csv> ...]          one line a file
    python3 Tools/perf_csv.py --md <label>=<file.csv> ...          rows of a Markdown table

Columns: frames, seconds, fps (frames / seconds), then milliseconds: Frame (mean, median, 99th percentile, worst),
Game, Draw (the render thread), GPU, RHIT. The header row of these files may be the first or the last one.
"""
import sys

WANT = [("FrameTime", "frame"), ("GameThreadTime", "game"), ("RenderThreadTime", "draw"), ("GPUTime", "gpu"), ("RHIThreadTime", "rhit")]


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        rows = [line.rstrip("\r\n").split(",") for line in f if line.strip()]
    header = next((r for r in rows if "FrameTime" in r and "GameThreadTime" in r), None)
    if header is None:
        raise ValueError("no header row with FrameTime in " + path)
    out = {}
    for column, name in WANT:
        if column not in header:
            continue
        i = header.index(column)
        values = []
        for r in rows:
            if r is header or len(r) <= i:
                continue
            try:
                values.append(float(r[i]))
            except ValueError:
                pass
        out[name] = values
    return out


def mean(v):
    return sum(v) / len(v) if v else 0.0


def pct(v, p):
    if not v:
        return 0.0
    s = sorted(v)
    return s[min(len(s) - 1, int(round(p * (len(s) - 1))))]


def summary(path):
    d = read(path)
    frame = d.get("frame", [])
    seconds = sum(frame) / 1000.0
    return {
        "frames": len(frame), "seconds": seconds, "fps": len(frame) / seconds if seconds > 0 else 0.0,
        "frame": mean(frame), "median": pct(frame, 0.5), "p99": pct(frame, 0.99), "worst": max(frame) if frame else 0.0,
        "game": mean(d.get("game", [])), "draw": mean(d.get("draw", [])), "gpu": mean(d.get("gpu", [])), "rhit": mean(d.get("rhit", [])),
    }


def main(a):
    if not a:
        print(__doc__)
        return 0
    md = a[0] == "--md"
    if md:
        a = a[1:]
        print("| Run | Frames | fps | Frame ms | median | 99th | worst | Game ms | Draw ms | GPU ms | RHIT ms |")
        print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for item in a:
        label, _, path = item.partition("=") if md and "=" in item else (item, "", item)
        s = summary(path)
        if md:
            print("| %s | %d | %.1f | %.2f | %.2f | %.2f | %.1f | %.2f | %.2f | %.2f | %.2f |" % (
                label, s["frames"], s["fps"], s["frame"], s["median"], s["p99"], s["worst"], s["game"], s["draw"], s["gpu"], s["rhit"]))
        else:
            print("%s: %d frames in %.1f s, %.1f fps | frame %.2f ms (median %.2f, 99th %.2f, worst %.1f) | game %.2f, draw %.2f, gpu %.2f, rhit %.2f" % (
                label, s["frames"], s["seconds"], s["fps"], s["frame"], s["median"], s["p99"], s["worst"], s["game"], s["draw"], s["gpu"], s["rhit"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
