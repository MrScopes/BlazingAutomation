from pathlib import Path
import json
import os
import sys
import shutil
import subprocess

def _app_root():
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent

APP_ROOT = _app_root()

def _configure_external_tools():
    names = ("adb", "ffmpeg", "scrcpy")
    search_dirs = [APP_ROOT / "tools" / name for name in names]
    search_dirs += [APP_ROOT.parent / "tools" / name for name in names]      # installed layout: app/tools next to app/src
    search_dirs += [APP_ROOT / "_internal" / "tools" / name for name in ("adb", "ffmpeg", "scrcpy")]
    valid = [str(folder) for folder in search_dirs if folder.is_dir()]
    if valid:
        os.environ["PATH"] = os.pathsep.join(valid + [os.environ.get("PATH", "")])
    for executable in ("adb", "ffmpeg", "scrcpy"):
        found = shutil.which(executable)
        print(f"[TOOLS] {executable}: {found or 'not found'}", flush=True)

_configure_external_tools()
ADB = shutil.which("adb") or "adb"

DEFAULT_DEVICE = "127.0.0.1:5555"

def _saved_device():
    # the launcher's Settings > ADB address (stored next to the other launcher settings)
    try:
        value = json.loads((APP_ROOT.parent / ".launcher.json").read_text(encoding="utf-8")).get("device")
        return value.strip() if isinstance(value, str) and value.strip() else None
    except Exception:
        return None

DEVICE = os.environ.get("BLAZING_DEVICE") or _saved_device() or DEFAULT_DEVICE
REFERENCE_W = 1131
REFERENCE_H = 2011
# Leave None to detect the game area on screen. If detection is ever wrong, set it by hand:
# (left, top, width, height) in device pixels, e.g. (0, 129, 1440, 2991)
GAME_REGION = None

def adb(*args, timeout=30):
    return subprocess.run(
        [ADB, "-s", DEVICE, *map(str, args)],
        capture_output=True,
        timeout=timeout,
        check=False,
    )

def reconnect():
    result = adb("get-state")
    if result.returncode == 0 and result.stdout.strip() == b"device":
        return

    subprocess.run(
        [ADB, "connect", DEVICE],
        capture_output=True,
        timeout=15,
    )

    result = adb("get-state")
    if result.returncode != 0:
        raise RuntimeError("ADB device unavailable")
    