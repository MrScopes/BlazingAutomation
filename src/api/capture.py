from pathlib import Path
import os
import time
import socket
import shutil
import subprocess
import threading
import cv2
import numpy as np
from .config import ADB, DEVICE, adb

class ScrcpyWindowCapture:
    TITLE = "Blazing Story Capture"

    def __init__(self, width, height, display_id):
        import ctypes
        import mss
        self.ctypes = ctypes
        self.user32 = ctypes.windll.user32
        self.mss = mss.MSS()
        self.width, self.height = width, height
        self.display_id = display_id
        self.process = None
        self.hwnd = None

    def start(self):
        import shutil
        if not shutil.which("scrcpy"):
            raise RuntimeError("scrcpy not found on PATH")
        cmd = [
            "scrcpy", "-s", DEVICE, f"--display-id={self.display_id}", "--no-audio",
            "--no-control", "--max-fps=60", "--video-bit-rate=8M",
            "--window-title=" + self.TITLE,
            "--window-width=540", "--window-height=960",
        ]
        self.process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("scrcpy exited before opening its window")
            hwnd = self.user32.FindWindowW(None, self.TITLE)
            if hwnd and self.user32.IsWindowVisible(hwnd):
                self.hwnd = hwnd
                time.sleep(1)
                return
            time.sleep(0.25)
        raise RuntimeError("scrcpy window did not appear")

    def get(self):
        if not self.hwnd or not self.user32.IsWindowVisible(self.hwnd):
            raise RuntimeError("scrcpy window not visible")
        if self.user32.IsIconic(self.hwnd):
            raise RuntimeError("scrcpy window minimized")
        if self.process.poll() is not None:
            raise RuntimeError("scrcpy exited")
        from ctypes import wintypes
        rect = wintypes.RECT()
        if not self.user32.GetClientRect(self.hwnd, self.ctypes.byref(rect)):
            raise RuntimeError("GetClientRect failed")
        pt = wintypes.POINT(0, 0)
        self.user32.ClientToScreen(self.hwnd, self.ctypes.byref(pt))
        w, h = rect.right, rect.bottom
        if w < 100 or h < 100:
            raise RuntimeError("scrcpy client area too small")
        shot = self.mss.grab({"left": pt.x, "top": pt.y, "width": w, "height": h})
        frame = cv2.cvtColor(np.asarray(shot), cv2.COLOR_BGRA2BGR)
        # relative
        if (w, h) != (self.width, self.height):
            frame = cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_LINEAR)
        return frame

    def close(self):
        try:
            self.mss.close()
        except Exception:
            pass
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()

class ScrcpyHeadlessCapture:
    def __init__(self, width, height, display_id, fps=30):
        self.width, self.height = width, height
        self.display_id = display_id
        self.fps = fps
        self.frame_width, self.frame_height = 720, 1280
        self.frame_bytes = self.frame_width * self.frame_height * 3
        self.port = None
        self.server = None
        self.ffmpeg = None
        self.sock = None
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.latest = None
        self.last_frame = 0.0
        self.frame_count = 0
        self.error = None
        self.threads = []

    def _server_path(self):
        scrcpy = shutil.which("scrcpy")
        if not scrcpy:
            raise RuntimeError("scrcpy executable not found")
        folder = Path(scrcpy).resolve().parent
        for name in ("scrcpy-server", "scrcpy-server.jar"):
            path = folder / name
            if path.is_file():
                return path
        raise RuntimeError("scrcpy-server not found beside scrcpy.exe")

    def _run_adb(self, *args, timeout=20):
        proc = adb(*args, timeout=timeout)
        if proc.returncode != 0:
            raise RuntimeError("adb " + " ".join(map(str, args)) + ": " + proc.stderr.decode(errors="replace")[:400])
        return proc

    def start(self):
        if not shutil.which("ffmpeg"):
            raise RuntimeError("ffmpeg not found on PATH")
        self.listener = None
        self.socket_name = None
        try:
            jar = self._server_path()
            self._run_adb("push", str(jar), "/data/local/tmp/scrcpy-server.jar", timeout=35)

            self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.listener.bind(("0.0.0.0", 0))
            self.listener.listen(1)
            self.listener.settimeout(12)
            self.port = self.listener.getsockname()[1]

            scid = f"{((os.getpid() * 1009) ^ (time.time_ns() & 0xffffffff)) & 0x7fffffff:08x}"
            self.socket_name = f"scrcpy_{scid}"

            self._run_adb(
                "reverse",
                f"localabstract:{self.socket_name}",
                f"tcp:{self.port}"
            )

            command = [
                ADB, "-s", DEVICE, "shell", "-T",
                "CLASSPATH=/data/local/tmp/scrcpy-server.jar",
                "app_process", "/", "com.genymobile.scrcpy.Server", "4.1",
                f"scid={scid}",
                "log_level=debug",
                "video_bit_rate=4000000",
                "audio=false",
                f"max_fps={self.fps}",
                "control=false",
                f"display_id={self.display_id}",
                "max_size=1280",
                "send_device_meta=false",
                "send_dummy_byte=false",
                "send_stream_meta=false",
                "send_frame_meta=false",
            ]

            self.server_log = open("scrcpy_headless_server.log", "wb")
            self.server = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=self.server_log,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )

            try:
                self.sock, address = self.listener.accept()
            except socket.timeout:
                raise RuntimeError("Timed out waiting for reverse video connection")

            self.sock.settimeout(5)
            print("[HEADLESS] Reverse socket connected", flush=True)

            # keep the reverse mapping until close(). Some ADB builds may
            # disrupt the existing transport when the mapping is removed
            self.listener.close()
            self.listener = None

            ffcommand = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                "-probesize", "32768", "-analyzeduration", "0",
                "-flags", "low_delay", "-f", "h264", "-i", "pipe:0",
                "-an", "-vf", f"scale={self.frame_width}:{self.frame_height}",
                "-pix_fmt", "bgr24", "-f", "rawvideo", "pipe:1",
            ]

            self.ffmpeg_log = open("scrcpy_headless_ffmpeg.log", "wb")
            self.ffmpeg = subprocess.Popen(
                ffcommand,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self.ffmpeg_log,
                bufsize=0,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )

            self.threads = [
                threading.Thread(target=self._feed, daemon=True, name="scrcpy-feed"),
                threading.Thread(target=self._decode, daemon=True, name="scrcpy-decode"),
            ]
            for thread in self.threads:
                thread.start()

            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                with self.lock:
                    ready = self.latest is not None
                if ready:
                    print(
                        f"[HEADLESS] H.264 stream active, display={self.display_id}, "
                        f"decode={self.frame_width}x{self.frame_height}",
                        flush=True
                    )
                    return
                if self.error:
                    raise RuntimeError(self.error)
                if self.ffmpeg.poll() is not None:
                    raise RuntimeError("FFmpeg decoder exited before first frame")
                time.sleep(0.1)

            raise RuntimeError("Timed out waiting for first decoded H.264 frame")
        except Exception:
            self.close()
            raise

    def _feed(self):
        try:
            while not self.stop.is_set():
                data = self.sock.recv(262144)

                if not data:
                    raise RuntimeError("scrcpy video socket closed")

                try:
                    self.ffmpeg.stdin.write(data)
                except BrokenPipeError as exc:
                    code = self.ffmpeg.poll()
                    raise RuntimeError(
                        f"FFmpeg closed its input (exit code={code}); "
                        "inspect scrcpy_headless_ffmpeg.log"
                    ) from exc

        except Exception as exc:
            if not self.stop.is_set():
                self.error = f"video feed: {exc}"
                print(f"[HEADLESS] {self.error}", flush=True)

                for filename, label in (
                    ("scrcpy_headless_server.log", "Server"),
                    ("scrcpy_headless_ffmpeg.log", "FFmpeg"),
                ):
                    stream = getattr(self, "server_log" if label == "Server" else "ffmpeg_log", None)
                    if stream is not None and not stream.closed:
                        try:
                            stream.flush()
                        except (OSError, ValueError):
                            pass
                    log_path = Path(filename)
                    if log_path.exists():
                        try:
                            log = log_path.read_text(
                                encoding="utf-8", errors="replace"
                            ).strip()
                            if log:
                                print(f"[HEADLESS] {label} log: " + log[-2500:], flush=True)
                        except OSError:
                            pass
        finally:
            try:
                self.ffmpeg.stdin.close()
            except Exception:
                pass

    def _decode(self):
        try:
            while not self.stop.is_set():
                parts = bytearray(self.frame_bytes)
                view = memoryview(parts)
                pos = 0
                while pos < self.frame_bytes:
                    n = self.ffmpeg.stdout.readinto(view[pos:])
                    if not n:
                        raise RuntimeError("FFmpeg frame pipe closed")
                    pos += n
                frame = np.frombuffer(parts, np.uint8).reshape(
                    self.frame_height, self.frame_width, 3).copy()
                with self.lock:
                    self.latest = frame
                    self.last_frame = time.monotonic()
                    self.frame_count += 1
        except Exception as exc:
            if not self.stop.is_set():
                self.error = f"video decode: {exc}"

    def get(self):
        with self.lock:
            frame = self.latest
            age = time.monotonic() - self.last_frame
        if frame is None:
            raise RuntimeError(self.error or "no decoded frame yet")
        if age > 3:
            raise RuntimeError(self.error or f"video stalled, last decoded frame {age:.1f}s ago")
        # keep the original screenshot resolution so all tap coordinates match
        return cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_LINEAR)

    def close(self):
        listener = getattr(self, "listener", None)
        if listener is not None:
            try:
                listener.close()
            except OSError:
                pass
            self.listener = None

        self.stop.set()
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.sock.close()
            self.sock = None
        for proc in (self.ffmpeg, self.server):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
        for log_name in ("ffmpeg_log", "server_log"):
            log = getattr(self, log_name, None)
            if log and not log.closed:
                log.close()
        if self.port:
            try:
                adb("reverse", "--remove", f"localabstract:{self.socket_name}", timeout=5)
            except Exception:
                pass
            self.port = None
