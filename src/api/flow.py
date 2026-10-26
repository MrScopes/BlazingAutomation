import re
import time
from datetime import timezone, datetime
from difflib import SequenceMatcher
from types import SimpleNamespace

import cv2

from api.common.points import COMMON_POINTS
from api.common.screens import COMMON_SCREENS
from api.recognition.recognition import Recognizer
from api.runtime import MacroEngine

NEVER = float("inf")      # rule timeout that disables the stall check
START_MODE = "main"
CALL_GAP = 5.0            # a longer pause between handler calls restarts the stall clock

class Step:
    def run(self, ctx, st):
        raise NotImplementedError

    def refs(self):
        return [], []

def _screens(value):
    return (value,) if isinstance(value, str) else tuple(value)

class Tap(Step):
    def __init__(self, name, every=None, expect=None):
        self.name, self.every, self.expect = name, every, expect

    def run(self, ctx, st):
        name = self.name(ctx) if callable(self.name) else self.name
        return ctx.tap(name, every=self.every, expect=self.expect) and self.every is None

    def refs(self):
        points = [self.name] if isinstance(self.name, str) else []
        return points, list(_screens(self.expect[0])) if self.expect else []

class Taps(Step):
    def __init__(self, name, count, gap=0.35):
        self.name, self.count, self.gap = name, count, gap

    def run(self, ctx, st):
        done = st.get("n", 0)
        if done >= self.count:
            return True
        if done and ctx.now - st["at"] < self.gap:
            return False
        if ctx.tap(self.name):
            st["n"], st["at"] = done + 1, ctx.now
        return st.get("n", 0) >= self.count

    def refs(self):
        return [self.name], []

class Wait(Step):
    def __init__(self, seconds):
        self.seconds = seconds

    def run(self, ctx, st):
        st.setdefault("t0", ctx.now)
        return ctx.now - st["t0"] >= self.seconds

class Do(Step):
    def __init__(self, fn):
        self.fn = fn

    def run(self, ctx, st):
        self.fn(ctx)
        return True

class Until(Step):
    def __init__(self, fn):
        self.fn = fn

    def run(self, ctx, st):
        return self.fn(ctx) is True

class AutoOn(Step):
    def run(self, ctx, st):
        if ctx.auto_on():
            ctx.log("Auto confirmed ON")
            return True
        return False

class Settle(Step):
    def __init__(self, point, min_s=5.0, quiet=1.5, max_s=9.0, every=0.5):
        self.point, self.min_s, self.quiet, self.max_s, self.every = point, min_s, quiet, max_s, every

    def run(self, ctx, st):
        now = ctx.now
        if not st:
            st.update(t0=now, tapped=0.0, changed=now, previous=None)
        text = re.sub(r"\s+", " ", ctx.raw.lower()).strip()
        if st["previous"] is not None and SequenceMatcher(None, text, st["previous"]).ratio() < 0.90:
            st["changed"] = now
        st["previous"] = text
        elapsed = now - st["t0"]
        if elapsed < self.min_s:
            if now - st["tapped"] >= self.every and ctx.tap(self.point, spacing=0):
                st["tapped"] = st["changed"] = now
            return False
        if now - max(st["changed"], st["tapped"]) >= self.quiet or elapsed >= self.max_s:
            ctx.log(f"Reward settled after {elapsed:.1f}s")
            return True
        return False

    def refs(self):
        return [self.point], []

def tap(name, every=None, expect=None):
    return Tap(name, every, expect)

def taps(name, count, gap=0.35):
    return Taps(name, count, gap)

def wait(seconds):
    return Wait(seconds)

def do(fn):
    return Do(fn)

def until(fn):
    return Until(fn)

def auto_on():
    return AutoOn()

def settle(point, **kwargs):
    return Settle(point, **kwargs)

class Progress:
    def __init__(self, count):
        self.idx = 0
        self.states = [{} for _ in range(count)]
        self.mem = {}

def advance(steps, progress, ctx):
    while progress.idx < len(steps):
        if not steps[progress.idx].run(ctx, progress.states[progress.idx]):
            return False
        progress.idx += 1
    return True

def _normalize(items, every):
    steps = []
    for index, item in enumerate(items):
        last = index == len(items) - 1
        if isinstance(item, Step):
            steps.append(item)
        elif isinstance(item, str):
            steps.append(Tap(item, every=every if last else None))
        elif callable(item):
            steps.append(Until(item))
        else:
            raise TypeError(f"Not a step: {item!r}")
    return steps

class Rule:
    def __init__(self, screen, steps, mode, timeout):
        self.screen, self.steps, self.mode, self.timeout = screen, steps, mode, timeout

class Ctx:
    def __init__(self, runner):
        self._r = runner
        self.engine = runner.engine
        self.flow = runner.flow
        self.args = runner.args
        self.local = {}

    def bind(self, tick):
        self.screen, self.raw, self.frame, self.now = tick.screen, tick.raw, tick.frame, tick.now

    # state
    mode = property(lambda self: self._r.mode)
    runs = property(lambda self: self._r.runs)
    finishing = property(lambda self: self._r.finishing)
    since = property(lambda self: self.now - self._r.since)       # seconds on the current screen
    run = property(lambda self: self.engine.state.run)            # per-run memory, cleared on every counted run
    wave = property(lambda self: self.engine.wave)
    battle = property(lambda self: self.engine.battle)

    def log(self, message):
        print(f"[{self.flow.name.upper()}] {message}", flush=True)

    # actions
    def tap(self, name, every=None, expect=None, spacing=None):
        sent = self.local.setdefault("_tapped_at", {})
        if every is not None and name in sent and self.now - sent[name] < every:
            return False
        if not self.engine.tap(name, spacing=self.flow.tap_spacing if spacing is None else spacing):
            return False
        sent[name] = self.now
        self.log(f"Tap: {name}")
        if expect:
            self.expect(*expect)
        return True

    def expect(self, screens, timeout=18):
        self.engine.transitions.wait_for(_screens(screens), timeout, self.screen)

    def auto_on(self):
        auto = self.engine.auto
        return True if auto is None else auto.enable(self.engine)

    def play(self, key, steps):
        store = self.run.setdefault("_plays", {})
        if key not in store:
            store[key] = Progress(len(steps))
        return advance(steps, store[key], self)

    def set_mode(self, mode):
        self._r.mode = mode

    def stop(self):
        self._r.stopped = True

    def fail(self, message):
        path = re.sub(r"\W+", "_", self.flow.name.lower()) + "_failure.png"
        try:
            saved = cv2.imwrite(path, self.frame)
        except Exception:
            saved = False
        raise RuntimeError(
            f"{self.flow.name}: {message}; screen={self.screen}; OCR: {self.raw[:180]!r}"
            + (f"; screenshot saved to {path}" if saved else "")
        )

class Runner:
    phase = "navigate"   # tells the engine a Home screen is never "unexpected"

    def __init__(self, flow, engine, args, times):
        self.flow, self.engine, self.args, self.times = flow, engine, args, times
        self.runs = 0
        self.finishing = False
        self.stopped = False
        self.ctx = Ctx(self)
        self.reset()

    @property
    def allow_home(self):
        return self.mode in self.flow.home_modes

    def reset(self):
        self.mode = self.flow.finish_mode if self.finishing and self.flow.finish_mode else START_MODE
        self.anchor = None
        self.since = None
        self.last_call = None
        self.progress = {}
        self.always_mem = {}
        self.seen = set()

    def lookup(self, screen):
        rules = self.flow.rules
        return rules.get((screen, self.mode)) or rules.get((screen, None))

    def new_run(self):
        e = self.engine
        e.state.reset_run()
        e.wave.reset()
        e.battle.reset()
        e.actions.reset()
        if e.auto is not None:
            e.auto.reset()

    def enter(self, screen, now):
        self.anchor, self.since = screen, now
        self.progress.clear()
        counter = self.flow.counter
        if counter and screen == counter.on and (not counter.after or self.seen & counter.after):
            self.runs += 1
            self.seen.clear()
            print(f"[CLEAR] {counter.label} {self.runs}", flush=True)
            self.new_run()
            if self.times is not None and self.runs >= self.times:
                self.finishing = True
                if self.flow.finish_mode:
                    self.mode = self.flow.finish_mode
                else:
                    self.stopped = True
        self.seen.add(screen)

    def __call__(self, engine):
        tick, ctx = engine.tick, self.ctx
        ctx.bind(tick)
        now, screen = tick.now, tick.screen

        if self.since is None or (self.last_call is not None and now - self.last_call > CALL_GAP):
            self.since = now
        self.last_call = now

        if screen != "unknown" and screen != self.anchor:
            self.enter(screen, now)

        if not self.stopped:
            self.step(ctx, screen, now)

        return False if self.stopped else None

    def step(self, ctx, screen, now):
        anchor_rule = self.lookup(self.anchor) if self.anchor else None
        limit = anchor_rule.timeout if anchor_rule and anchor_rule.timeout is not None else self.flow.stall
        if now - self.since > limit:
            ctx.fail(f"Stalled on {self.anchor or 'unknown'} for {limit:.0f}s")

        try:
            if not self.engine.transitions.check(screen, now):
                return
        except TimeoutError as exc:
            ctx.fail(str(exc))

        ctx.local = self.always_mem
        for fn in self.flow.always_fns:
            fn(ctx)
        if self.stopped:
            return

        rule = self.lookup(screen) if screen != "unknown" else None
        if rule is None:
            return
        progress = self.progress.get(id(rule))
        if progress is None:
            progress = self.progress[id(rule)] = Progress(len(rule.steps))
        ctx.local = progress.mem
        advance(rule.steps, progress, ctx)

class Flow:
    def __init__(self, name, points=None, screens=(), transitions=None, poll=0.2, confirmations=1,
                 wave_confirmations=1, double_tap=(), home=(), destination=None, tap_spacing=0.35,
                 retry=3.0, stall=65.0, finish_mode=None, home_modes=(), expires=None):
        """
        points / screens   added on top of the shared COMMON_POINTS / COMMON_SCREENS
        home, destination  Home -> mode navigation: [(point, delay_after_previous), ...] and the screen(s) it should reach
        tap_spacing        minimum seconds between any two taps
        retry              default ``every`` for a rule's last tap
        stall              seconds on one screen before failing (per-rule ``timeout=`` overrides; NEVER disables)
        finish_mode        mode to enter when ``--times`` is reached instead of stopping at once
        home_modes         modes in which being on Home is expected (no automatic Home navigation)
        expires            (datetime, message): refuse to start after that moment
        """
        if home and not destination:
            raise ValueError("home navigation needs a destination screen")
        self.name = name
        self.points = {**COMMON_POINTS, **(points or {})}
        self.screens = [*COMMON_SCREENS, *screens]
        self.transitions = transitions
        self.poll, self.confirmations, self.wave_confirmations = poll, confirmations, wave_confirmations
        self.double_tap = tuple(double_tap)
        self.home, self.destination = tuple(home), destination
        self.tap_spacing, self.retry, self.stall = tap_spacing, retry, stall
        self.finish_mode, self.home_modes, self.expires = finish_mode, tuple(home_modes), expires
        self.rules, self.counter, self.arguments, self.always_fns = {}, None, [], []

    def on(self, screen, *steps, mode=None, timeout=None, every=None):
        built = _normalize(steps, self.retry if every is None else every)
        for name in _screens(screen):
            self.rules[(name, mode)] = Rule(name, built, mode, timeout)
        return self

    def rule(self, screen, mode=None, timeout=None):
        def register(fn):
            self.on(screen, Until(fn), mode=mode, timeout=timeout)
            return fn
        return register

    def always(self, fn):
        self.always_fns.append(fn)
        return fn

    def count_run(self, on, after=None, label="Run"):
        self.counter = SimpleNamespace(on=on, after=set(_screens(after)) if after else set(), label=label)
        return self

    def arg(self, *flags, **kwargs):
        self.arguments.append((flags, kwargs))
        return self

    def add_args(self, parser):
        for flags, kwargs in self.arguments:
            parser.add_argument(*flags, **kwargs)

    def validate(self):
        known = {screen.name for screen in self.screens}
        for (screen, mode), rule in self.rules.items():
            if screen not in known:
                raise ValueError(f"{self.name}: rule for undefined screen {screen!r}")
            for step in rule.steps:
                points, screens = step.refs()
                for point in points:
                    if point not in self.points:
                        raise ValueError(f"{self.name}: screen {screen!r} taps undefined point {point!r}")
                for other in screens:
                    if other not in known:
                        raise ValueError(f"{self.name}: screen {screen!r} expects undefined screen {other!r}")
        for name, _ in self.home:
            if name not in self.points:
                raise ValueError(f"{self.name}: home navigation taps undefined point {name!r}")
        if self.counter and self.counter.on not in known:
            raise ValueError(f"{self.name}: count_run on undefined screen {self.counter.on!r}")

    def run(self, macro, times=None, **args):
        if self.expires and datetime.now(timezone.utc) >= self.expires[0]:
            raise RuntimeError(self.expires[1])
        self.validate()
        recognizer = Recognizer(self.screens, transitions=self.transitions)
        engine = MacroEngine(
            macro.driver(),
            lambda raw, previous=None: recognizer.identify(raw, previous=previous),
            self.points,
            poll=self.poll,
            confirmations=self.confirmations,
            double_tap=self.double_tap,
            wave_confirmations=self.wave_confirmations,
            home_navigation=self.home,
            destination=self.destination,
        )
        print(f"[START] {self.name}", flush=True)
        runner = Runner(self, engine, SimpleNamespace(**args), times)
        started = time.monotonic()
        try:
            engine.run(runner)
        finally:
            minutes, seconds = divmod(int(time.monotonic() - started), 60)
            counted = f"{runner.runs} {self.counter.label.lower()}(s) in " if self.counter else ""
            print(f"[DONE] {self.name}: {counted}{minutes}m {seconds:02d}s", flush=True)
