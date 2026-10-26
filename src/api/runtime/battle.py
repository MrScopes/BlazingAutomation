import re

READY_PATTERN = re.compile(r"\bready\s*!*", re.I)

class Battle:
    def __init__(self):
        self.ready = False
        self.ready_seen = 0
        self.auto_enabled = None

    def update(self, raw, wave_changed=False):
        if wave_changed:
            self.ready_seen = 0
        self.ready = bool(READY_PATTERN.search(raw)) and "select a team" in raw.lower()
        self.ready_seen = self.ready_seen + 1 if self.ready else 0

    def reset(self):
        self.ready = False
        self.ready_seen = 0
        self.auto_enabled = None
