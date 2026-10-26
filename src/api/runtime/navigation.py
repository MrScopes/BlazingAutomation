class HomeNavigation:
    def __init__(self, steps, destination, retry_seconds=8.0):
        self.steps = tuple(steps)
        self.destination = set(destination if isinstance(destination, (tuple, list, set)) else (destination,))
        self.retry_seconds = retry_seconds
        self.reset()

    def reset(self):
        self.index = 0
        self.last_tap = None
        self.waiting_since = None

    def handle(self, engine, screen, now):
        if screen in self.destination:
            self.reset()
            return False
        if screen != 'home':
            self.reset()
            return False
        if not self.steps:
            return False
        if self.waiting_since is not None:
            if now - self.waiting_since >= self.retry_seconds:
                print('[NAV] Mode did not open; retrying Home selection', flush=True)
                self.reset()
            return True
        if self.index >= len(self.steps):
            self.waiting_since = now
            return True
        action, delay = self.steps[self.index]
        if self.last_tap is not None and now - self.last_tap < delay:
            return True
        if engine.tap(action, spacing=0.35):
            self.last_tap = engine.actions.global_at
            self.index += 1
            print(f'[NAV] Home: {action}', flush=True)
            if self.index == len(self.steps):
                self.waiting_since = self.last_tap
        return True
