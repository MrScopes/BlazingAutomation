import time
import struct
import cv2
import numpy as np
from .config import APP_ROOT, REFERENCE_W, REFERENCE_H, adb, reconnect
from .capture import ScrcpyWindowCapture, ScrcpyHeadlessCapture
from .ocr import OCR

class Driver:
    def __init__(self):
        self.reader = OCR()
        self.display_id = None
        self.input_display = None
        self.capture_mode = "raw"
        self.raw_fallbacks = 0
        self.live = None
        self.live_failed = False
        self.width = REFERENCE_W
        self.height = REFERENCE_H

    def capture_png(self, display):
        result = adb("exec-out", "screencap", "-d", display, "-p")
        signature = b"\x89PNG\r\n\x1a\n"
        offset = result.stdout.find(signature)
        if result.returncode != 0 or offset < 0:
            raise RuntimeError("PNG screenshot failed: " + result.stderr.decode(errors="replace"))
        frame = cv2.imdecode(np.frombuffer(result.stdout[offset:], np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise RuntimeError("PNG screenshot decoding failed")
        return frame

    def capture_raw(self, display):
        result = adb("exec-out", "screencap", "-d", display)
        if result.returncode != 0:
            raise RuntimeError("Raw screenshot failed: " + result.stderr.decode(errors="replace"))
        data = result.stdout
        if len(data) < 12:
            raise RuntimeError("Raw screenshot is too short")
        w, h, fmt = struct.unpack_from("<III", data)
        if not (100 <= w <= 8192 and 100 <= h <= 8192):
            raise RuntimeError(f"Invalid raw dimensions {w}x{h}")
        channels = {1: 4, 2: 4, 3: 3, 4: 2}.get(fmt)
        if channels is None:
            raise RuntimeError(f"Unsupported raw pixel format {fmt}")
        size = w * h * channels
        if len(data) - 12 == size:
            offset = 12
        elif len(data) - 16 == size:
            offset = 16
        else:
            raise RuntimeError(f"Unexpected raw payload: {len(data)} bytes, expected {size + 12} or {size + 16}")
        pixels = np.frombuffer(data, dtype=np.uint8, count=size, offset=offset)
        if channels == 4:
            rgba = pixels.reshape(h, w, 4)
            return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
        if channels == 3:
            return cv2.cvtColor(pixels.reshape(h, w, 3), cv2.COLOR_RGB2BGR)
        packed = np.frombuffer(data, dtype="<u2", count=w*h, offset=offset).reshape(h, w)
        return cv2.cvtColor(packed, cv2.COLOR_BGR5652BGR)

    def capture(self, display):
        if self.capture_mode == "png":
            return self.capture_png(display)
        try:
            return self.capture_raw(display)
        except Exception as exc:
            self.raw_fallbacks += 1
            if self.raw_fallbacks <= 3:
                print(f"[RAW FALLBACK] {exc}; using PNG", flush=True)
            return self.capture_png(display)

    def ocr(self, frame):
        return self.reader.read(frame)

    def find_display(self):
        from .display import resolve_game_display
        selected = resolve_game_display()
        self.input_display = selected.logical_id
        self.display_id = selected.physical_id
        self.capture_port = selected.port
        frame = self.capture(self.display_id)
        self.height, self.width = frame.shape[:2]
        if selected.size and (self.width, self.height) != selected.size:
            raise RuntimeError(
                f"Game viewport reports {selected.size}, but screenshot is "
                f"{self.width}x{self.height}"
            )
        print(f"[GAME] Input display {self.input_display}; screenshot display "
              f"{self.display_id}; scrcpy port {self.capture_port}; "
              f"{self.width}x{self.height}", flush=True)
        return frame

    def screen(self):
        start = time.monotonic()

        if self.display_id is None:
            frame = self.find_display()
        else:
            if self.capture_mode in ("scrcpy", "headless") and not self.live_failed:
                if self.live is None:
                    try:
                        live = (ScrcpyHeadlessCapture(self.width, self.height, display_id=self.input_display)
                                if self.capture_mode == "headless"
                                else ScrcpyWindowCapture(self.width, self.height, display_id=self.input_display))
                        live.start()
                        test = live.get()
                        test_text = self.ocr(test).lower()
                        if not test_text.strip() or any(s in test_text for s in ("search games", "mumu store", "app cloner")):
                            raise RuntimeError("stream did not show recognizable game content")
                        self.live = live
                        print("[SCRCPY] Live capture verified (" + self.capture_mode + ")", flush=True)
                    except Exception as exc:
                        try:
                            live.close()
                        except Exception:
                            pass
                        self.live_failed = True
                        print(f"[SCRCPY] {exc}; falling back to raw ADB", flush=True)
                if self.live is not None:
                    try:
                        frame = self.live.get()
                    except Exception as exc:
                        print(f"[SCRCPY] {exc}; falling back to raw ADB", flush=True)
                        self.live.close()
                        self.live = None
                        self.live_failed = True
                        frame = self.capture_raw(self.display_id)
                else:
                    frame = self.capture_raw(self.display_id)
            else:
                frame = self.capture(self.display_id)

        capture_time = time.monotonic() - start
        self.height, self.width = frame.shape[:2]

        start_ocr = time.monotonic()
        raw = self.ocr(frame)
        ocr_time = time.monotonic() - start_ocr

        if getattr(self, "debug_scans", False):
            print(
                f"[SCAN] capture={capture_time:.2f}s "
                f"ocr={ocr_time:.2f}s",
                flush=True,
            )

        return frame, raw

    def tap(self, point, silent=False, reference=True):
        if self.input_display is None:
            self.find_display()
        from .macro import send_taps
        send_taps(self.input_display, point, (self.width, self.height) if reference else None, 1, silent)

    def doubletap(self, point, silent=False, reference=True, delay_ms=150):
        if self.input_display is None:
            self.find_display()
        from .macro import send_taps
        send_taps(self.input_display, point, (self.width, self.height) if reference else None, 2, silent, delay_ms)

    def swipe(self, start, end, duration_ms=300, silent=False, reference=True):
        if self.input_display is None:
            self.find_display()

        if reference:
            sx = round(start[0] * self.width / REFERENCE_W)
            sy = round(start[1] * self.height / REFERENCE_H)
            ex = round(end[0] * self.width / REFERENCE_W)
            ey = round(end[1] * self.height / REFERENCE_H)
        else:
            sx, sy = start
            ex, ey = end

        result = adb(
            "shell", "input", "-d", self.input_display,
            "swipe", sx, sy, ex, ey, max(1, int(duration_ms)),
        )

        if result.returncode != 0:
            raise RuntimeError(
                "Swipe failed: " + result.stderr.decode(errors="replace")
            )

        if not silent:
            print(f"[SWIPE] ({sx}, {sy}) -> ({ex}, {ey}) {duration_ms}ms", flush=True)
            