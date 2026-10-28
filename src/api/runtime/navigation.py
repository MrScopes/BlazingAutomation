import re

class HomeNavigation:
    FOLLOW_UP_WINDOW = 3.0   # how long after its due time a follow-up Home tap may still go out on an unread screen
    AWAY_RESET = 5.0     # seconds of unrecognised screens after which Home selection starts over

    def __init__(self, steps, destination, retry_seconds=8.0):
        self.steps = tuple(steps)
        self.destination = set(destination if isinstance(destination, (tuple, list, set)) else (destination,))
        self.retry_seconds = retry_seconds
        self.failures = 0
        self.last_back = float('-inf')
        self.reset()

    def reset(self):
        self.index = 0
        self.last_tap = None
        self.waiting_since = None
        self.away_since = None

    def handle(self, engine, screen, now):
        if screen in self.destination:
            self.failures = 0
            self.reset()
            return False
        if screen == 'unknown':
            if 0 < self.index < len(self.steps) and self.last_tap is not None and self.waiting_since is None:
                action, delay = self.steps[self.index]
                since = now - self.last_tap
                if delay <= since <= delay + self.FOLLOW_UP_WINDOW and engine.tap(action, spacing=0.35):
                    self.last_tap = engine.actions.global_at
                    self.index += 1
                    print(f'[NAV] Home: {action} (screen was still sliding)', flush=True)
                    if self.index == len(self.steps):
                        self.waiting_since = self.last_tap
                    self.away_since = None
                    return True
            # a carousel sliding or a screen fading: not a reason to forget which steps are done
            if self.away_since is None:
                self.away_since = now
            elif now - self.away_since > 6 and now - self.last_back > 6:
                # stuck on a page the macro does not know (Shop, Character List...): a Back button means we can leave it
                tick = getattr(engine, 'tick', None)
                if tick is not None and re.search(r'\bback\b', tick.raw, re.I):
                    self.last_back = now
                    print('[NAV] Unknown page with a Back button; pressing Back', flush=True)
                    engine.driver.back()
            return False
        if screen != 'home':
            self.failures = 0
            self.reset()
            return False
        if self.away_since is not None:
            away, self.away_since = now - self.away_since, None
            if away > self.AWAY_RESET:
                self.reset()
        if not self.steps:
            return False
        if self.waiting_since is not None:
            if now - self.waiting_since >= self.retry_seconds:
                self.failures += 1
                print('[NAV] Mode did not open; retrying Home selection', flush=True)
                self.reset()
                # the real Home has no Back button, so a Back on screen means a page opened by mistake
                tick = getattr(engine, 'tick', None)
                if self.failures >= 2 and tick is not None and re.search(r'\bback\b', tick.raw, re.I):
                    print('[NAV] This is not the Home screen (it has a Back button); pressing Back', flush=True)
                    engine.driver.back()
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
    