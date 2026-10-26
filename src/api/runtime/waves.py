import re
import time

WAVE_PATTERN = re.compile(r"\bMAP\s*(\d{1,3})\s*/\s*(\d{1,3})\b", re.I)

class WaveTracker:
    def __init__(self, confirmations=1):
        self.confirmations = confirmations
        self.reset()

    def reset(self):
        self.current = None
        self.total = None
        self.previous = None
        self.changed = False
        self.since = None
        self._candidate = None
        self._count = 0

    @property
    def elapsed(self):
        return 0.0 if self.since is None else time.monotonic() - self.since

    def update(self, raw, now=None):
        self.changed = False
        match = WAVE_PATTERN.search(raw)
        if not match:
            self._candidate = None
            self._count = 0
            return self.current
        wave, total = map(int, match.groups())
        if not 1 <= wave <= total <= 999:
            return self.current
        value = wave, total
        if value == self._candidate:
            self._count += 1
        else:
            self._candidate, self._count = value, 1
        if self._count >= self.confirmations and value != (self.current, self.total):
            self.previous = self.current
            self.current, self.total = value
            self.changed = True
            self.since = time.monotonic() if now is None else now
        return self.current
