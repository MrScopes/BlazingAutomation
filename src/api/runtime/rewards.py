class RewardSequence:
    def __init__(self, middle='screen_center', next_action='results_next', middle_taps=3, timeout=30):
        self.middle = middle
        self.next_action = next_action
        self.middle_taps = middle_taps
        self.timeout = timeout
        self.reset()

    def reset(self):
        self.screen = None
        self.started = None
        self.last_tap = None
        self.taps = 0
        self.next_at = None

    def handle(self, engine, screen, now, raw=''):
        if self.screen != screen:
            self.reset()
            self.screen = screen
            self.started = now
            print(f'[REWARD] {screen}: acknowledging drops', flush=True)
        if now - self.started > self.timeout:
            raise RuntimeError(f'Reward screen {screen} did not advance; OCR: {raw[:180]!r}')
        if self.taps < self.middle_taps:
            if self.last_tap is None or now - self.last_tap >= 0.4:
                if engine.tap(self.middle, spacing=0.35):
                    self.taps += 1
                    self.last_tap = engine.actions.global_at
            return
        if self.next_at is None:
            if now - self.last_tap >= 1.5 and engine.tap(self.next_action, spacing=0.35):
                self.next_at = engine.actions.global_at
                print(f'[REWARD] Next ({screen})', flush=True)
        elif now - self.next_at >= 2.0:
            if engine.tap(self.next_action, spacing=0.35):
                self.next_at = engine.actions.global_at
