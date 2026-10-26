# finding Android devices on the network. Stays stdlib-only so the launcher can use it before anything else loads
import re
import shutil
import subprocess
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent.parent
SERVICE = re.compile(r"^(\S+)\s+(_adb[\w-]*\._tcp)\.?\s+(\S+:\d+)\s*$")

def adb_path():
    for folder in ("scrcpy", "adb"):
        path = APP / "tools" / folder / "adb.exe"
        if path.is_file():
            return str(path)
    return shutil.which("adb") or "adb"

def run_adb(*args, timeout=15):
    try:
        result = subprocess.run([adb_path(), *args], capture_output=True, text=True, errors="replace",
                                timeout=timeout, stdin=subprocess.DEVNULL,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return result.returncode, result.stdout + result.stderr

def services():
    """(name, kind, ip:port) for everything the network is announcing as ADB (wireless debugging)."""
    run_adb("start-server")
    _, output = run_adb("mdns", "services")
    return [match.groups() for match in map(SERVICE.match, (line.strip() for line in output.splitlines())) if match]

def serial_of(name):
    # "adb-R5CX40AWHZJ-4Q1kyM": the middle part is the phone's serial, the last part can change
    parts = name.split("-")
    return parts[1] if len(parts) >= 3 else name

def wait_for(kind, seconds=4.0):
    """[(name, address)] of the announced services of one kind ('connect' or 'pairing'), polling for a while."""
    deadline = time.monotonic() + seconds
    while True:
        found = [(name, address) for name, service, address in services() if f"tls-{kind}" in service]
        if found or time.monotonic() >= deadline:
            return found
        time.sleep(1.0)

def phones(seconds=4.0):
    return wait_for("connect", seconds)

def resolve_phone(preferred=None, seconds=4.0):
    """(name, ip:port) of the phone to use: the one used last time if it is around, else the first one found."""
    found = phones(seconds)
    for name, address in found:
        if preferred and serial_of(name) == preferred:
            return name, address
    return found[0] if found else None

def connect(address):
    _, output = run_adb("connect", address, timeout=20)
    return "connected" in output.lower() and "cannot" not in output.lower() and "failed" not in output.lower(), output.strip()

def pair(address, code):
    _, output = run_adb("pair", address, code, timeout=30)
    return "successfully paired" in output.lower(), output.strip()
