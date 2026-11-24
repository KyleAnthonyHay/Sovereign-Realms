"""A film of the loading screen, from the frames the game itself paints.

    1. in a standalone game (not Shipping), the console command
           vl.LoadingPreview [seconds 18] [ready after 11] [fps 30] [seed 7]
       paints the real loading-screen widget off screen at 1920 x 1080, its clock set by hand (King David plays by
       himself throughout; the level is "ready" after the given time), into
       Saved/Screenshots/VL/loading_preview/frame_NNNN.png
    2. Tools/.venv/Scripts/python Tools/loading_preview.py [fps 30]
       -> Saved/Screenshots/VL/loading_preview.mp4   H.264, through Blender's sequencer (there is no ffmpeg here)
          Saved/Screenshots/VL/loading_preview.gif   640 x 360, 15 frames a second

Blender: $BLENDER, else the installed 5.3 (Windows), else `blender` on the PATH.
"""
import glob
import os
import subprocess
import sys
import tempfile

from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SHOTS = os.path.join(ROOT, "Saved", "Screenshots", "VL")
FRAMES = os.path.join(SHOTS, "loading_preview")

SEQUENCER = r'''
import bpy, sys
frames, out, fps = sys.argv[-3], sys.argv[-2], int(sys.argv[-1])
import glob, os
files = sorted(glob.glob(os.path.join(frames, "frame_*.png")))
scene = bpy.context.scene
scene.sequence_editor_create()
se = scene.sequence_editor
strips = se.strips if hasattr(se, "strips") else se.sequences
strip = strips.new_image("frames", files[0], 1, 1)
for f in files[1:]:
    strip.elements.append(os.path.basename(f))
strip.frame_final_duration = len(files)
scene.frame_start, scene.frame_end = 1, len(files)
scene.render.fps = fps
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


def main():
    fps = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    files = sorted(glob.glob(os.path.join(FRAMES, "frame_*.png")))
    if not files:
        sys.exit("no frames in %s: run vl.LoadingPreview in a standalone game first" % FRAMES)
    mp4 = os.path.join(SHOTS, "loading_preview.mp4")
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(SEQUENCER)
    try:
        subprocess.run([blender(), "-b", "--factory-startup", "--python", f.name, "--", FRAMES, mp4, str(fps)], check=True,
                       stdout=subprocess.DEVNULL)
    finally:
        os.unlink(f.name)
    print("wrote %s (%d frames, %.1f s, %.1f MB)" % (mp4, len(files), len(files) / fps, os.path.getsize(mp4) / 1e6))

    step = max(fps // 15, 1)
    small = [Image.open(p).convert("RGB").resize((640, 360), Image.NEAREST) for p in files[::step]]
    pal = small[len(small) // 2].quantize(64, method=Image.MEDIANCUT, dither=Image.NONE)
    small = [im.quantize(palette=pal, dither=Image.NONE) for im in small]
    gif = os.path.join(SHOTS, "loading_preview.gif")
    small[0].save(gif, save_all=True, append_images=small[1:], duration=int(round(1000.0 * step / fps)), loop=0, optimize=False)
    print("wrote %s (%d frames, %.1f MB)" % (gif, len(small), os.path.getsize(gif) / 1e6))


if __name__ == "__main__":
    main()
