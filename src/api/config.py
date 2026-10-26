from pathlib import Path
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
DEVICE = "192.168.1.118:5555"
REFERENCE_W = 1131
REFERENCE_H = 2011

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
