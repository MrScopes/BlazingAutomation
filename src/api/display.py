import re
from dataclasses import dataclass
from .config import adb, reconnect

GAME_PACKAGE = "dev.blazingonline.gameapp"

@dataclass(frozen=True)
class GameDisplay:
    logical_id: int
    physical_id: str
    port: int
    size: tuple | None = None

def game_window(package=GAME_PACKAGE):
    reconnect()
    result = adb("shell", "dumpsys", "window", "windows")
    if result.returncode:
        raise RuntimeError("Cannot inspect Android windows: " + result.stderr.decode(errors="replace"))
    output = result.stdout.decode(errors="replace")
    windows = re.split(r"(?=^\s*Window #\d+\b)", output, flags=re.MULTILINE)
    for window in windows:
        header = window.splitlines()[0] if window.splitlines() else ""
        if package not in header:
            continue
        match = re.search(r"\bmDisplayId=(\d+)", window)
        if match and re.search(r"\bisVisible=true\b", window):
            size = re.search(r"Requested w=(\d+) h=(\d+)", window)
            return int(match.group(1)), (int(size.group(1)), int(size.group(2))) if size else None
    raise RuntimeError(f"No visible game window for {package}; launch the game first")

def physical_displays():
    result = adb("shell", "dumpsys", "SurfaceFlinger", "--display-id")
    if result.returncode:
        raise RuntimeError("Cannot enumerate SurfaceFlinger displays")
    output = result.stdout.decode(errors="replace")
    return [(display, int(port)) for display, port in re.findall(
        r"Display\s+(\d+)\s+\(HWC display\s+\d+\).*?port=(\d+)", output)]

def display_viewports():
    result = adb("shell", "dumpsys", "display")
    if result.returncode:
        raise RuntimeError("Cannot inspect Android display mappings: " + result.stderr.decode(errors="replace"))
    output = result.stdout.decode(errors="replace")
    # the android input/display manager explicitly binds logical displayId to
    # local:<physical SurfaceFlinger ID> and physicalPort in mViewports.
    viewports = re.search(r"\bmViewports\s*=\s*\[(.*?)\]\s*(?:\r?\n|$)", output, re.DOTALL)
    if not viewports:
        raise RuntimeError("Android dumpsys display did not report mViewports")
    mapping = {}
    for entry in re.findall(r"DisplayViewport\{([^}]*)\}", viewports.group(1)):
        logical = re.search(r"\bdisplayId\s*=\s*(\d+)", entry)
        physical = re.search(r"\buniqueId\s*=\s*['\"]?local:(\d+)", entry)
        port = re.search(r"\bphysicalPort\s*=\s*(\d+)", entry)
        if logical and physical and port and "valid=true" in entry and "isActive=true" in entry:
            key = int(logical.group(1))
            item = (physical.group(1), int(port.group(1)))
            if key in mapping and mapping[key] != item:
                raise RuntimeError(f"Conflicting viewport mappings for logical display {key}")
            mapping[key] = item
    return mapping

def resolve_game_display(package=GAME_PACKAGE):
    logical, size = game_window(package)
    mapping = display_viewports()
    if logical not in mapping:
        raise RuntimeError(f"No active physical viewport for game logical display {logical}; available={sorted(mapping)}")
    physical, port = mapping[logical]
    # cross-check with SurfaceFlinger instead of inferring from image size.
    sf = dict(physical_displays())
    if physical not in sf or sf[physical] != port:
        raise RuntimeError(f"SurfaceFlinger mapping mismatch for logical {logical}: physical={physical}, port={port}")
    return GameDisplay(logical, physical, port, size)
