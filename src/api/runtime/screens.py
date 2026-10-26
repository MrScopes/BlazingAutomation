class ScreenTracker:
    def __init__(self, identify, confirmations=1):
        self.identify = identify
        self.confirmations = confirmations
        self.current = None
        self.candidate = None
        self.count = 0
        self.changed = False

    def update(self, raw):
        observed = self.identify(raw, previous=self.current)
        if observed == self.candidate:
            self.count += 1
        else:
            self.candidate, self.count = observed, 1
        self.changed = False
        if self.count >= self.confirmations and observed != self.current:
            self.current = observed
            self.changed = True
        return self.current
