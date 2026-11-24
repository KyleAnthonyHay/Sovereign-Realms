#!/usr/bin/env python3
"""The showreel's edit, from the frames Tools/showreel.py recorded (Saved/Showreel/frames/<clip>/f_NNNN.png).

    python Tools/showreel_edit.py clips        -> Saved/Showreel/clips/<clip>.mp4   (each take whole, no sound)
    python Tools/showreel_edit.py edit         -> Saved/Showreel/SovereignRealms_Showreel.mp4

The edit: EDL below, cut on Ruach's beat (0.42 s; the song from 187.55 s, its last loud section and the drop at
218.7 s). The frames are composed here (cuts, a fade from black, a light grade, the logo over the end), then Blender's
sequencer encodes them with the song (H.264 / AAC, 1920 x 1080, 30 fps). There is no ffmpeg on this machine.
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "Saved", "Showreel")
FRAMES = os.path.join(OUT, "frames")
SONG = os.path.join(ROOT, "SourceArt", "Audio", "Music", "Ruach.mp3")
LOGO = os.path.join(ROOT, "References", "Branding", "sovereign_realms_logo_full.png")
FPS = 30
BEAT = 0.42
SONG_IN = 187.55          # a beat of the song: the edit's 0
LENGTH = 31.9             # seconds

# (clip, cut-in time in the edit [s], source in-frame); each runs until the next one's cut
EDL = [
    ("01_island_push", 0.00, 37),
    ("02_mountain_orbit", 3.78, 40),
    ("03_parallax_castle", 7.14, 60),
    ("12_canopy_fly", 9.45, 70),        # (9.45: the section's big entry, half a beat off the grid)
    ("04_fpv_pass", 11.34, 45),
    ("05_king_run", 13.02, 40),
    ("06_troop_ship", 14.70, 150),
    ("10_fog_towers", 16.38, 60),
    ("07_battle_line", 17.64, 120),
    ("09_archer_volley", 19.74, 100),
    ("08_king_charge", 21.00, 20),
    ("11_raze_farm", 22.68, 40),
    ("13_king_castle", 24.78, 0),
]
LOGO_IN = 27.30           # the logo fades in on this bar
DARK_FROM, DARK_TO = 28.6, 30.2   # the picture goes down to black under it
FADE_IN = 0.42
END_FADE = 1.0            # everything (logo, music) out over the last second

BLENDER_ENCODE = r'''
import bpy, sys, glob, os
a = sys.argv[sys.argv.index("--") + 1:]
frames, out, fps = a[0], a[1], int(a[2])
song = a[3] if len(a) > 3 else ""
files = sorted(glob.glob(os.path.join(frames, "*.png")))
scene = bpy.context.scene
scene.sequence_editor_create()
se = scene.sequence_editor
strips = se.strips if hasattr(se, "strips") else se.sequences
strip = strips.new_image("frames", files[0], 1, 1)
for f in files[1:]:
    strip.elements.append(os.path.basename(f))
n = len(files)
strip.frame_final_duration = n
scene.frame_start, scene.frame_end = 1, n
scene.render.fps = fps
scene.render.fps_base = 1.0
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 1920, 1080, 100
scene.view_settings.view_transform = "Standard"
try:
    scene.render.image_settings.media_type = "VIDEO"
except Exception:
    pass
scene.render.image_settings.file_format = "FFMPEG"
scene.render.ffmpeg.format = "MPEG4"
scene.render.ffmpeg.codec = "H264"
scene.render.ffmpeg.constant_rate_factor = "HIGH"
scene.render.ffmpeg.ffmpeg_preset = "GOOD"
scene.render.ffmpeg.gopsize = fps
if song:
    song_in, fade_in, fade_out = float(a[4]), float(a[5]), float(a[6])
    snd = strips.new_sound("song", song, 2, 1)
    # start the song song_in seconds in: the strip begins earlier, its head trimmed off
    off = int(round(song_in * fps))
    snd.frame_start = 1 - off
    snd.frame_offset_start = off
    snd.frame_final_end = n + 1
    fi, fo = int(round(fade_in * fps)), int(round(fade_out * fps))
    for f, v in ((1, 0.0), (1 + fi, 1.0), (n + 1 - fo, 1.0), (n, 0.0)):
        snd.volume = v
        snd.keyframe_insert("volume", frame=f)
    scene.render.ffmpeg.audio_codec = "AAC"
    scene.render.ffmpeg.audio_bitrate = 256
    scene.render.ffmpeg.audio_channels = "STEREO"
    scene.render.ffmpeg.audio_mixrate = 48000
else:
    scene.render.ffmpeg.audio_codec = "NONE"
scene.render.use_file_extension = False
scene.render.filepath = out
bpy.ops.render.render(animation=True)
'''


def blender():
    for p in (os.environ.get("BLENDER"), r"C:\Program Files\Blender Foundation\Blender 5.3\blender.exe"):
        if p and os.path.exists(p):
            return p
    return "blender"


def encode(frames_dir, out, extra=()):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(BLENDER_ENCODE)
    try:
        subprocess.run([blender(), "-b", "--factory-startup", "--python", f.name, "--", frames_dir, out, str(FPS)] + list(extra),
                       check=True, stdout=subprocess.DEVNULL)
    finally:
        os.unlink(f.name)
    print("wrote %s (%.1f MB)" % (out, os.path.getsize(out) / 1e6))


def clips():
    os.makedirs(os.path.join(OUT, "clips"), exist_ok=True)
    for d in sorted(glob.glob(os.path.join(FRAMES, "[0-9][0-9]_*"))):
        if os.path.isdir(d):
            encode(d, os.path.join(OUT, "clips", os.path.basename(d) + ".mp4"))


def grade(a):
    # a light, even grade: a touch more contrast and colour (the game's look is a little flat at noon)
    x = a.astype(np.float32) / 255.0
    lum = (x * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1, keepdims=True)
    x = lum + (x - lum) * 1.10
    x = (x - 0.5) * 1.06 + 0.5
    return x


def logo_layer():
    lg = Image.open(LOGO).convert("RGBA")
    w = 900
    lg = lg.resize((w, int(lg.height * w / lg.width)), Image.LANCZOS)
    layer = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    layer.paste(lg, ((1920 - lg.width) // 2, (1080 - lg.height) // 2), lg)
    a = np.asarray(layer).astype(np.float32) / 255.0
    return a[..., :3], a[..., 3:4]


def smooth(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def edit():
    n = int(round(LENGTH * FPS))
    cuts = [int(round(t * FPS)) for _, t, _ in EDL] + [n]
    work = os.path.join(OUT, "work", "edit_frames")
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    lrgb, lalpha = logo_layer()
    rows = []
    k = 0
    for i, (name, t, src0) in enumerate(EDL):
        a, b = cuts[i], cuts[i + 1]
        src_files = sorted(glob.glob(os.path.join(FRAMES, name, "f_*.png")))
        for f in range(a, b):
            s = src0 + (f - a)
            s = min(s, len(src_files) - 1)   # (held on its last frame if the take is short)
            img = np.asarray(Image.open(src_files[s]).convert("RGB"))
            x = grade(img)
            tt = f / FPS
            v = 1.0
            if tt < FADE_IN:
                v *= smooth(tt / FADE_IN)
            if tt > DARK_FROM:
                v *= 1.0 - 0.92 * smooth((tt - DARK_FROM) / (DARK_TO - DARK_FROM))
            x = x * v
            la = smooth((tt - LOGO_IN) / 1.0) * (1.0 - smooth((tt - (LENGTH - END_FADE)) / END_FADE))
            if la > 0:
                al = lalpha * la
                x = x * (1 - al) + lrgb * al
            if tt > LENGTH - END_FADE:
                x = x * (1.0 - smooth((tt - (LENGTH - END_FADE)) / END_FADE))
            out = (np.clip(x, 0, 1) * 255 + 0.5).astype(np.uint8)
            Image.fromarray(out).save(os.path.join(work, "e_%04d.png" % f), compress_level=1)
            k += 1
        rows.append((name, a, b, src0, src0 + (b - a) - 1))
    print("composed %d frames" % k)
    for r in rows:
        print("  %-20s edit %5.2f-%5.2f s (frames %d-%d), source frames %d-%d" % (r[0], r[1] / FPS, r[2] / FPS, r[1], r[2] - 1, r[3], r[4]))
    encode(work, os.path.join(OUT, "SovereignRealms_Showreel.mp4"), [SONG, str(SONG_IN), "0.35", str(END_FADE + 0.2)])


if __name__ == "__main__":
    {"clips": clips, "edit": edit}[sys.argv[1] if len(sys.argv) > 1 else "edit"]()
