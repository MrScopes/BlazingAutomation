import time
from dataclasses import dataclass

from .actions import Actions
from .battle import Battle
from .navigation import HomeNavigation
from .screens import ScreenTracker
from .state import State
from .transitions import Transitions
from .waves import WaveTracker
from .auto import AutoDetector
from api.common.globalhandler import GlobalHandler

@dataclass
class Tick:
    frame: object
    raw: str
    screen: str
    now: float
    changed: bool

class MacroEngine:
    def __init__(self, driver, identify, points, poll=0.2, confirmations=1,
                 double_tap=(), wave_confirmations=1, home_navigation=(), destination=None):
        self.driver = driver
        self.poll = poll
        self.screens = ScreenTracker(identify, confirmations)
        self.actions = Actions(driver, points, double_tap)
        self.auto = AutoDetector(point=points["auto_button"]) if "auto_button" in points else None
        self.transitions = Transitions()
        self.state = State()
        self.wave = WaveTracker(wave_confirmations)
        self.battle = Battle()
        self.global_handler = GlobalHandler(self)
        self.navigation = HomeNavigation(home_navigation, destination) if destination else None
        self.tick = None
        self._in_restart = False
        self._last_home = False

    def tap(self, name, cooldown=0, group=None, spacing=0):
        return self.actions.tap(name, cooldown, group, spacing)

    def _recover(self, handler):
        self.transitions.clear()
        self.state.reset_run()
        self.wave.reset()
        self.battle.reset()
        self.actions.reset()
        self._last_home = False

        if self.navigation:
            self.navigation.reset()

        if hasattr(handler, "reset"):
            handler.reset()
        elif hasattr(handler, "on_restart"):
            handler.on_restart()

    def run(self, handler):
        restart_screens = {
            "game_intro_disclaimer",
            "game_intro_main",
            "game_data_updated",
        }

        while True:
            frame, raw = self.driver.screen()
            now = time.monotonic()

            if not raw.strip() or "now loading" in raw.lower():
                time.sleep(self.poll)
                continue

            screen = self.screens.update(raw)

            if screen is None:
                time.sleep(min(self.poll, 0.12))
                continue

            if self.screens.changed and screen != "unknown":
                print(f"[SCREEN] {screen}: {raw[:210]!r}", flush=True)

            self.tick = Tick(frame, raw, screen, now, self.screens.changed)

            if screen in restart_screens and not self._in_restart:
                print(f"[RECOVERY] {screen} detected; resetting macro state", flush=True)
                self._recover(handler)
                self._in_restart = True

            if self.global_handler.handle(screen):
                time.sleep(self.poll)
                continue

            if self._in_restart and screen not in ("unknown", "news"):
                self._in_restart = False

            # Home is normal when a macro intentionally returns there.
            # Only reset on an unexpected return after the macro was active.
            if screen == "home" and not self._last_home and self.screens.changed:
                if getattr(handler, "phase", None) not in ("navigate", "return_home", "ninja_road_challenge"):
                    print("[RECOVERY] Unexpected Home; resetting macro state", flush=True)
                    self._recover(handler)

            self._last_home = screen == "home"

            if self.navigation and not getattr(handler, "allow_home", False):
                if self.navigation.handle(self, screen, now):
                    time.sleep(self.poll)
                    continue

            self.wave.update(raw, now)
            self.battle.update(raw, self.wave.changed)

            if handler(self) is False:
                return

            time.sleep(self.poll)
