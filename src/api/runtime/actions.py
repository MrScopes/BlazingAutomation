import time

class Actions:
    def __init__(self, driver, points, double_tap=()):
        self.driver = driver
        self.points = points
        self.double_tap = set(double_tap)
        self.last = {}
        self.global_at = 0.0
        self.global_name = None

    def tap(self, name, cooldown=0, group=None, spacing=0, now=None):
        now = time.monotonic() if now is None else now
        key = group or name
        if now - self.last.get(key, float('-inf')) < cooldown:
            return False
        if spacing and now - self.global_at < spacing:
            return False
        if name not in self.points or self.points[name] is None:
            raise RuntimeError(f"Point {name!r} is not defined; add it to the macro's points")
        method = self.driver.doubletap if name in self.double_tap else self.driver.tap
        method(self.points[name])
        stamp = time.monotonic()
        self.last[key] = stamp
        self.global_at = stamp
        self.global_name = name
        return True

    def reset(self):
        self.last.clear()
        self.global_at = 0.0
        self.global_name = None
