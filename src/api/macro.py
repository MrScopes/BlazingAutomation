import re
import time
from .config import REFERENCE_W, REFERENCE_H, adb, reconnect

def send_taps(display, point, size=None, count=1, silent=False, delay_ms=150):
    x, y = point
    if size is not None:
        w, h = size
        x = x * w / REFERENCE_W
        y = y * h / REFERENCE_H
    x, y = round(x), round(y)
    if delay_ms < 0:
        raise ValueError("delay_ms must be nonnegative")
    for i in range(count):
        result = adb("shell", f"input -d {display} tap {x} {y}")
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors="replace"))
        if i + 1 < count:
            time.sleep(delay_ms / 1000)
    if not silent:
        print(f"[{'DOUBLE TAP' if count == 2 else 'TAP'}] ({x}, {y})", flush=True)

class Macro:
    def __init__(self, input_display=None, capture="headless"):
        self.input_display = input_display
        self.capture_mode = capture
        self._driver = None
        self._size = None

    def connect(self):
        from .display import game_window
        self.input_display, self._size = game_window()
        print(f"[INPUT] Game display {self.input_display}", flush=True)
        return self

    def tap(self, point, silent=False, reference=True):
        if self.input_display is None:
            self.connect()
        send_taps(self.input_display, point, self.size() if reference else None, 1, silent)

    def doubletap(self, point, silent=False, reference=True, delay_ms=150):
        if self.input_display is None:
            self.connect()
        send_taps(self.input_display, point, self.size() if reference else None, 2, silent, delay_ms)

    def wait(self, ms):
        if ms < 0:
            raise ValueError("wait must be nonnegative")
        time.sleep(ms / 1000)

    def repeat(self, callback, times=None):
        if times is not None and times < 0:
            raise ValueError("times must be nonnegative")
        index = 0
        while times is None or index < times:
            callback(self)
            index += 1

    def size(self):
        if self._size is None:
            result = adb("shell", "wm", "size")
            match = re.search(r"(?:Physical|Override) size:\s*(\d+)x(\d+)", result.stdout.decode(errors="replace"))
            if not match:
                raise RuntimeError("Could not determine display size; use pixel coordinates")
            self._size = (int(match.group(1)), int(match.group(2)))
        return self._size

    def driver(self):
        if self._driver is None:
            from .driver import Driver
            self._driver = Driver()
            self._driver.capture_mode = self.capture_mode
            self._driver.screen()
            self.input_display = self._driver.input_display
        return self._driver

    def frame(self):
        return self.driver().screen()[0]

    def read(self):
        return self.driver().screen()[1]

    def screen(self):
        return self.driver().screen()

    def identify(self, screens, raw=None, details=False):
        from .recognition import Recognizer
        recognizer = screens if isinstance(screens, Recognizer) else Recognizer(screens)
        result = recognizer.match(self.read() if raw is None else raw)
        return result if details else result.name

    def wait_for(self, text=None, screen=None, identify=None, timeout=30, interval_ms=500):
        if not text and not screen:
            raise ValueError("Provide text or screen")
        if screen is not None and not callable(identify):
            raise ValueError("Pass your macro classifier with identify=identify when waiting for a screen")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            frame, raw = self.screen()
            if (text is None or text.lower() in raw.lower()) and (screen is None or identify(raw) == screen):
                return frame, raw
            self.wait(interval_ms)
        raise TimeoutError(f"Timed out waiting for text={text!r}, screen={screen!r}")

    def close(self):
        import subprocess
        from .config import ADB

        try:
            if self._driver is not None and self._driver.live is not None:
                self._driver.live.close()
                self._driver.live = None
        finally:
            try:
                result = subprocess.run(
                    [ADB, "kill-server"],
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
                if result.returncode == 0:
                    print("[ADB] Server stopped", flush=True)
                else:
                    print(
                        f"[ADB] Shutdown failed: {result.stderr.decode(errors='replace')}",
                        flush=True,
                    )
            except Exception as exc:
                print(f"[ADB] Shutdown failed: {exc}", flush=True)
                