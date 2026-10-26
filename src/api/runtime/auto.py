import time
import cv2

class ToggleDetector:
    """A button with a dot that is yellow when on and white when off (auto, ninjutsu, ...).

    point  the button's tap point
    dot    where the dot is, relative to ``point``
    tap    name of the point to tap to flip it
    """

    def __init__(self, point, tap, group, label, dot=(0, 0), reference_size=(1145, 2011),
                 confirmations=3, cooldown=1.0):
        self.point = point
        self.tap_name = tap
        self.group = group
        self.label = label
        self.dot = dot
        self.reference_size = reference_size
        self.confirmations = confirmations
        self.cooldown = cooldown
        self.last_tap = 0.0
        self.last_state = None
        self.state_count = 0

    def reset(self):
        self.last_state = None
        self.state_count = 0

    def box(self, frame):
        height, width = frame.shape[:2]
        rw, rh = self.reference_size

        x = round((self.point[0] + self.dot[0]) * width / rw)
        y = round((self.point[1] + self.dot[1]) * height / rh)

        rx = max(1, round(25 * width / rw))
        ry = max(1, round(20 * height / rh))

        return max(0, x - rx), max(0, y - ry), min(width, x + rx), min(height, y + ry)

    def crop(self, frame):
        x1, y1, x2, y2 = self.box(frame)
        return frame[y1:y2, x1:x2].copy()

    def ratios(self, frame):
        #(yellow, white) share of the dot area, or None when the area is empty
        image = self.crop(frame)

        if image.size == 0:
            return None

        h, w = image.shape[:2]
        indicator = image[
            int(h * 0.20):int(h * 0.80),
            int(w * 0.20):int(w * 0.80)
        ]

        if indicator.size == 0:
            return None

        hsv = cv2.cvtColor(indicator, cv2.COLOR_BGR2HSV)

        yellow = cv2.inRange(hsv, (15, 100, 120), (40, 255, 255))
        white = cv2.inRange(hsv, (0, 0, 150), (179, 80, 255))

        return cv2.countNonZero(yellow) / yellow.size, cv2.countNonZero(white) / white.size

    def detect(self, frame):
        found = self.ratios(frame)

        if found is None:
            return None

        yellow_ratio, white_ratio = found

        if yellow_ratio >= 0.15:
            return True

        if white_ratio >= 0.15 and yellow_ratio < 0.05:
            return False

        return None

    def check(self, frame):
        state = self.detect(frame)

        if state is None:
            self.last_state = None
            self.state_count = 0
            return None

        if state == self.last_state:
            self.state_count += 1
        else:
            self.last_state = state
            self.state_count = 1

        if self.state_count >= self.confirmations:
            return state

        return None

    def set(self, engine, enabled):
        if engine.tick is None:
            return False

        state = self.check(engine.tick.frame)

        if state is None:
            return False

        if state == enabled:
            return True

        now = time.monotonic()

        if now - self.last_tap < self.cooldown:
            return False

        if engine.tap(self.tap_name, cooldown=self.cooldown, group=self.group):
            self.last_tap = now
            self.last_state = None
            self.state_count = 0

            print(
                f"[{self.label.upper()}] {'Enabling' if enabled else 'Disabling'} {self.label}",
                flush=True
            )

        return False

    def enable(self, engine):
        return self.set(engine, True)

    def disable(self, engine):
        return self.set(engine, False)
    
class AutoDetector(ToggleDetector):
    def __init__(self, point, **kwargs):
        # the auto dot sits 60 to the left of the auto button point
        super().__init__(point, tap="auto_button", group="auto_toggle", label="Auto", dot=(-60, 0), **kwargs)
