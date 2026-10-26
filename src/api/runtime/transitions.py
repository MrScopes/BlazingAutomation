import time

class Transitions:
    def __init__(self):
        self.pending = None

    def wait_for(self, screens, timeout=18, source=None, now=None):
        self.pending = (set(screens), time.monotonic() if now is None else now, timeout, source)

    def check(self, screen, now=None):
        if self.pending is None:
            return True
        expected, started, timeout, source = self.pending
        now = time.monotonic() if now is None else now
        if screen in expected:
            self.pending = None
            print(f"[NAV] Transition reached: {screen}", flush=True)
            return True
        if now - started > timeout:
            raise TimeoutError(f"Timed out waiting for {sorted(expected)}; got {screen}")
        return False

    def clear(self):
        self.pending = None
