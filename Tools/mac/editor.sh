#!/bin/sh
# Editor lifecycle for scripted work on macOS (Live Coding does not work there).
#   Tools/mac/editor.sh quit      save dirty packages, quit, wait until the process and the MCP port are gone
#   Tools/mac/editor.sh build     build SovereignRealmsEditor (editor must be closed)
#   Tools/mac/editor.sh start     launch on the project and wait for the MCP server (port 8000)
#   Tools/mac/editor.sh rebuild   quit + build + start
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
UE="${UE_ROOT:-/Users/Shared/Epic Games/UnrealInstall/UE_5.8}"
running() { pgrep -f "UnrealEditor.app/Contents/MacOS/UnrealEditor" >/dev/null; }
listening() { lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; }
quit() {
    # unsaved packages put up a save dialog that blocks the quit: save them through the Python bridge first
    running && python3 "$ROOT/Tools/ue_py.py" -c "import unreal; unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)" 20 >/dev/null 2>&1
    running && osascript -e 'quit app "UnrealEditor"' >/dev/null 2>&1
    i=0
    while running || listening; do
        i=$((i + 1))
        [ $i -eq 40 ] && pkill -f "UnrealEditor.app/Contents/MacOS/UnrealEditor"
        [ $i -gt 45 ] && pkill -f CrashReportClient
        [ $i -gt 90 ] && { echo "editor did not quit"; return 1; }
        sleep 1
    done
    echo "editor closed"
}
build() {
    "$UE/Engine/Build/BatchFiles/Mac/Build.sh" SovereignRealmsEditor Mac Development -Project="$ROOT/SovereignRealms.uproject" -WaitMutex 2>&1 \
        | grep -E "error|warning: |Result:|Total execution|Undefined symbols|ld:" | grep -v "^$" | tail -40
}
start() {
    # A leftover crash reporter can hold the MCP port; and the OS keeps the port in TIME_WAIT for a while after the
    # editor quits, during which the new editor's MCP server fails to bind (silently). Clear both first.
    pkill -9 -f CrashReportClient 2>/dev/null
    k=0
    while lsof -nP -iTCP:8000 >/dev/null 2>&1 && [ $k -lt 40 ]; do k=$((k + 1)); sleep 1; done
    sleep 3
    open -a "$UE/Engine/Binaries/Mac/UnrealEditor.app" --args "$ROOT/SovereignRealms.uproject"
    i=0
    until listening; do
        i=$((i + 1)); [ $i -gt 240 ] && { echo "editor did not start (or its MCP server could not bind port 8000: quit it and start again)"; return 1; }
        sleep 1
    done
    # the port opens before the editor ticks: wait until the Python bridge (Content/Python/init_unreal.py) answers
    j=0
    until python3 "$ROOT/Tools/ue_py.py" -c "print('ok')" 15 >/dev/null 2>&1; do
        rm -f "$ROOT"/Saved/PyInbox/*.py 2>/dev/null
        j=$((j + 1)); [ $j -gt 30 ] && { echo "bridge did not answer"; return 1; }
    done
    echo "editor up (port after ${i}s, bridge after $((j * 15))s more)"
}
case "$1" in
    quit) quit ;;
    build) build ;;
    start) start ;;
    rebuild) quit && build && sleep 30 && start ;;
    *) sed -n 2,7p "$0" ;;
esac
