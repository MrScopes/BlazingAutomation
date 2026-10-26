import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import cv2

# adb and scrcpy are started without a stdin, so they read the keyboard and swallow what is typed at the menu.
# Every process this tool starts gets an empty stdin unless the code asks for something else.
_popen_init = subprocess.Popen.__init__

def _popen_no_stdin(self, *args, **kwargs):
    kwargs.setdefault("stdin", subprocess.DEVNULL)
    _popen_init(self, *args, **kwargs)

subprocess.Popen.__init__ = _popen_no_stdin

# the runtime code imports itself as "api...", so put the src folder on the path like the macros do
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.macro import Macro
from api.common.points import COMMON_POINTS
from api.runtime.actions import Actions
from api.runtime.auto import AutoDetector
from api.runtime.ninjutsu import NINJUTSU_POINTS, SECRET_POINTS, ninjutsu, secret

POINTS = {**COMMON_POINTS, **NINJUTSU_POINTS, **SECRET_POINTS}

# the same detectors the macros use
BUTTONS = [
    ("Auto", AutoDetector(point=POINTS["auto_button"])),
    ("Ninjutsu", ninjutsu),
    ("Secret", secret),
]
ACTIONS = ("on", "off", "toggle")

# seconds to wait for a readable dot and for a tap to take effect
READ_TIMEOUT = 8.0
SET_TIMEOUT = 10.0

def console_mode():
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        handle = ctypes.windll.kernel32.GetStdHandle(-10)
        mode = ctypes.c_uint32()
        if ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return handle, mode.value
    except Exception:
        pass
    return None

def restore_console(saved):
    if saved:
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(saved[0], saved[1])
        except Exception:
            pass

def ask(saved):
    # adb can leave the console in raw mode, where Enter no longer ends a line
    restore_console(saved)
    return input("Select: ").strip().lower()

class Probe:
    def __init__(self, driver):
        self.driver = driver
        self.actions = Actions(driver, POINTS)
        self.tick = None

    def look(self):
        frame, raw = self.driver.screen()
        self.tick = SimpleNamespace(frame=frame, raw=raw)
        return frame

    def tap(self, name, cooldown=0, group=None, spacing=0):
        return self.actions.tap(name, cooldown, group, spacing)

def show(det, frame):
    found = det.ratios(frame)
    if found is None:
        return "dot area is empty"
    return f"yellow {found[0]:.0%}  white {found[1]:.0%}"

def save_debug(det, frame):
    x1, y1, x2, y2 = det.box(frame)
    image = frame.copy()
    cv2.rectangle(image, (x1, y1), (x2, y2), (0, 0, 255), 3)
    path = f"toggle_{det.label.lower()}_debug.png"
    cv2.imwrite(path, image)
    return path

def read_state(probe, det):
    det.reset()
    end = time.monotonic() + READ_TIMEOUT
    while time.monotonic() < end:
        state = det.check(probe.look())
        if state is not None:
            return state
    return None

def run(probe, det, action):
    name = det.label
    state = read_state(probe, det)
    if state is None:
        print(f"[{name}] could not read the dot ({show(det, probe.tick.frame)})")
        print(f"[{name}] saved {save_debug(det, probe.tick.frame)} - the red box should sit on the dot")
        return False
    print(f"[{name}] currently {'ON' if state else 'OFF'}")
    target = (not state) if action == "toggle" else action == "on"
    if state == target:
        print(f"[{name}] already {'ON' if target else 'OFF'}, nothing to do")
        return True
    # the detector taps the button and waits for the dot to change
    det.reset()
    det.last_tap = 0.0
    started = time.monotonic()
    end = started + SET_TIMEOUT
    while time.monotonic() < end:
        probe.look()
        if det.set(probe, target):
            print(f"[{name}] confirmed {'ON' if target else 'OFF'} after {time.monotonic() - started:.1f}s")
            return True
    print(f"[{name}] still not {'ON' if target else 'OFF'} after {SET_TIMEOUT:.0f}s ({show(det, probe.tick.frame)})")
    print(f"[{name}] saved {save_debug(det, probe.tick.frame)}")
    return False

def read_all(probe):
    probe.look()
    for name, det in BUTTONS:
        state = det.detect(probe.tick.frame)
        word = "unreadable" if state is None else "ON" if state else "OFF"
        print(f"  {name:<9} {word:<10} ({show(det, probe.tick.frame)})")

def menu():
    print("\n=== BUTTON TEST ===")
    rows = [(name, det, action) for name, det in BUTTONS for action in ACTIONS]
    for number, (name, _, action) in enumerate(rows, 1):
        print(f"{number}. {name}: {action}")
    print("R. Read all button states")
    print("Q. Back")
    return rows

def main():
    saved = console_mode()
    macro = Macro(capture="headless")
    try:
        print("[TEST] Connecting to the game...", flush=True)
        probe = Probe(macro.driver())
        print("[TEST] Connected. Open a battle screen first; the buttons only exist there.", flush=True)
        rows = menu()
        while True:
            choice = ask(saved)
            if choice in ("q", "quit", "back"):
                return
            if choice == "r":
                read_all(probe)
            elif choice.isdigit() and 1 <= int(choice) <= len(rows):
                _, det, action = rows[int(choice) - 1]
                run(probe, det, action)
            else:
                print("Invalid selection")
                continue
            menu()
    except KeyboardInterrupt:
        print("\n[TEST] Stopped")
    finally:
        macro.close()

if __name__ == "__main__":
    main()
    