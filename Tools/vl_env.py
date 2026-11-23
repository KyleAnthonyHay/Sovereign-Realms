"""Where things are on this machine, for the tools that run on both macOS and Windows.

    ROOT                the repo
    engine_root()       the Unreal install: $UE_ROOT if set, else the platform's default
                        (macOS: /Users/Shared/Epic Games/UnrealInstall/UE_5.8;
                         Windows: C:/Program Files/Epic Games/UE_5.8, else the newest UE_5.* there)
    editor_binary()     UnrealEditor (the windowed one), editor_cmd_binary() the one for headless runs
    editor_log()        the editor's log of this project
    blender_binary()    $BLENDER if set, else the platform's usual place

The shell side says the same thing: Tools/mac/*.sh (UE_ROOT, BLENDER) and Tools/windows/_env.ps1.
`python Tools/vl_env.py` prints what was found.
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = os.path.join(ROOT, "SovereignRealms.uproject")
WINDOWS = sys.platform.startswith("win")
MAC = sys.platform == "darwin"
PREFERRED = "5.8"      # the project's EngineAssociation


def engine_root():
    env = os.environ.get("UE_ROOT")
    if env:
        return env
    if WINDOWS:
        base = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Epic Games")
        preferred = os.path.join(base, "UE_" + PREFERRED)
        if os.path.isdir(os.path.join(preferred, "Engine")):
            return preferred

        def version(path):
            return [int(n) for n in re.findall(r"\d+", os.path.basename(path))]
        found = sorted((p for p in glob.glob(os.path.join(base, "UE_5.*")) if os.path.isdir(os.path.join(p, "Engine"))), key=version)
        return found[-1] if found else preferred
    if MAC:
        return "/Users/Shared/Epic Games/UnrealInstall/UE_" + PREFERRED
    return os.path.expanduser("~/UnrealEngine")


def editor_binary():
    ue = engine_root()
    if WINDOWS:
        return os.path.join(ue, "Engine", "Binaries", "Win64", "UnrealEditor.exe")
    if MAC:
        return os.path.join(ue, "Engine", "Binaries", "Mac", "UnrealEditor.app", "Contents", "MacOS", "UnrealEditor")
    return os.path.join(ue, "Engine", "Binaries", "Linux", "UnrealEditor")


def editor_cmd_binary():
    """Headless runs: on Windows UnrealEditor-Cmd.exe (a console program: its exit is waited for); elsewhere the editor's own."""
    if WINDOWS:
        return os.path.join(engine_root(), "Engine", "Binaries", "Win64", "UnrealEditor-Cmd.exe")
    return editor_binary()


def editor_log():
    if MAC:      # (the editor's log is outside the project there)
        return os.path.expanduser("~/Library/Logs/Unreal Engine/SovereignRealmsEditor/SovereignRealms.log")
    return os.path.join(ROOT, "Saved", "Logs", "SovereignRealms.log")


def blender_binary():
    env = os.environ.get("BLENDER")
    if env:
        return env
    if WINDOWS:
        base = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Blender Foundation")
        found = sorted(glob.glob(os.path.join(base, "Blender*", "blender.exe")))
        return found[-1] if found else "blender"
    if MAC:
        return "/Applications/Blender.app/Contents/MacOS/Blender"
    return "blender"


if __name__ == "__main__":
    for name, value in (("root", ROOT), ("engine", engine_root()), ("editor", editor_binary()), ("editor log", editor_log()), ("blender", blender_binary())):
        print("%-11s %s%s" % (name, value, "" if os.path.exists(value) else "   (not found)"))
