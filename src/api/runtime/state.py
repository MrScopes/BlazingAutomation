import time

class State:
    def __init__(self):
        self.session = {}
        self.reset_run()

    def reset_run(self):
        self.run = {}
        self.timers = {}
        self.once_keys = set()

    def mark(self, name, now=None):
        self.timers[name] = time.monotonic() if now is None else now

    def elapsed(self, name, now=None):
        start = self.timers.get(name)
        return None if start is None else (time.monotonic() if now is None else now) - start

    def once(self, name):
        if name in self.once_keys:
            return False
        self.once_keys.add(name)
        return True

    def increment(self, name, amount=1):
        self.run[name] = self.run.get(name, 0) + amount
        return self.run[name]
