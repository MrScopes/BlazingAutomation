import re
import time
from .config import adb, reconnect
from .common.layout import to_pixels

def display_args(display):
    # the default display needs no -d (and older Android's input command has no such option)
    return [] if display in (None, "", 0, "0") else ["-d", str(display)]

def send_taps(display, point, size=None, count=1, silent=False, delay_ms=150, origin=(0, 0), anchor=None):
    # size = the game area in device pixels, origin = its top-left corner on the display
    x, y = point
    if size is not None:
        x, y = to_pixels(point, *size, anchor=anchor)
        x, y = x + origin[0], y + origin[1]
    x, y = round(x), round(y)
    if delay_ms < 0:
        raise ValueError("delay_ms must be nonnegative")
    for i in range(count):
        result = adb("shell", " ".join(["input", *display_args(display), "tap", str(x), str(y)]))
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
        self._origin = (0, 0)

    def connect(self):
        from .display import game_window_info
        self.input_display, self._size, frame = game_window_info()
        if frame:
            self._origin = (max(0, frame[0]), max(0, frame[1]))
            self._size = (frame[2] - frame[0], frame[3] - frame[1])
        print(f"[INPUT] Game display {self.input_display}", flush=True)
        return self

    def tap(self, point, silent=False, reference=True):
        if self.input_display is None:
            self.connect()
        send_taps(self.input_display, point, self.size() if reference else None, 1, silent, origin=self._origin)

    def doubletap(self, point, silent=False, reference=True, delay_ms=150):
        if self.input_display is None:
            self.connect()
        send_taps(self.input_display, point, self.size() if reference else None, 2, silent, delay_ms, origin=self._origin)

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
                