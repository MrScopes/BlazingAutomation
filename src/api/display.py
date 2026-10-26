import re
from dataclasses import dataclass
from .config import adb, reconnect, GAME_REGION

GAME_PACKAGE = "dev.blazingonline.gameapp"

@dataclass(frozen=True)
class GameDisplay:
    logical_id: int
    physical_id: str
    port: int
    size: tuple | None = None
    frame: tuple | None = None     # (left, top, right, bottom) of the game window on its display

FRAME_PATTERNS = (
    re.compile(r"\bframe=\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]"),      # Android 11+:  Frames: parent=.. frame=[l,t][r,b]
    re.compile(r"\bmFrame=\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]"),     # older Android
)

def window_frame(window):
    for pattern in FRAME_PATTERNS:
        match = pattern.search(window)
        if match:
            left, top, right, bottom = map(int, match.groups())
            if right > left and bottom > top:
                return left, top, right, bottom
    return None

def game_region(frame, size, shot_w, shot_h):
    """(left, top, width, height) of the game inside a full-display screenshot, and how it was found.

    The game fills its window (no bars), and on phones the window sits below the status bar. Taps and
    screenshots are both in full-display pixels, so this rectangle is what turns reference coordinates into
    real ones. GAME_REGION in config overrides everything."""
    if GAME_REGION:
        return tuple(GAME_REGION), "config GAME_REGION"
    container, source = (0, 0, shot_w, shot_h), "whole screen (window position not reported)"
    if frame:
        left, top, right, bottom = frame
        left, top = max(0, left), max(0, top)
        right, bottom = min(shot_w, right), min(shot_h, bottom)
        # tiny or outside the screenshot: those numbers aren't in this display's pixels
        if right - left >= shot_w * 0.5 and bottom - top >= shot_h * 0.5:
            container, source = (left, top, right - left, bottom - top), "window frame"
    return container, source

def game_window_info(package=GAME_PACKAGE):
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
        # older Android (BlueStacks) has no isVisible= line; mViewVisibility=0x0 means visible there
        visible = re.search(r"\bisVisible=true\b", window) or (
            "isVisible=" not in window and re.search(r"\bmViewVisibility=0x0\b", window))
        if visible:
            size = re.search(r"Requested w=(\d+) h=(\d+)", window)
            return (int(match.group(1)) if match else 0), (int(size.group(1)), int(size.group(2))) if size else None, window_frame(window)
    raise RuntimeError(f"No visible game window for {package}; launch the game first")

def game_window(package=GAME_PACKAGE):
    logical, size, _ = game_window_info(package)
    return logical, size

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
    logical, size, frame = game_window_info(package)
    try:
        mapping = display_viewports()
    except RuntimeError:
        mapping = {}       # BlueStacks and other older Android builds don't report viewports
    if logical not in mapping:
        if mapping and logical != 0:
            raise RuntimeError(f"No active physical viewport for game logical display {logical}; available={sorted(mapping)}")
        # one display: everything (screenshots, taps, video) uses the default
        print("[GAME] Android reports no display mapping; using the default display", flush=True)
        return GameDisplay(logical, "", 0, size, frame)
    physical, port = mapping[logical]
    # cross-check with SurfaceFlinger instead of inferring from image size.
    sf = dict(physical_displays())
    if physical not in sf or sf[physical] != port:
        raise RuntimeError(f"SurfaceFlinger mapping mismatch for logical {logical}: physical={physical}, port={port}")
    return GameDisplay(logical, physical, port, size, frame)
