class GlobalHandler:
    INTRO_SCREENS = {"game_intro_disclaimer", "game_intro_main"}

    def __init__(self, engine):
        self.engine = engine

    def handle(self, screen):
        if screen in self.INTRO_SCREENS:
            if self.engine.tap("screen_center", cooldown=2.0):
                print(f"[GLOBAL] Dismissing {screen}", flush=True)
            return True

        if screen == "news":
            if self.engine.tap("news_close", cooldown=2.0):
                print("[GLOBAL] Closing news", flush=True)
            return True

        if screen == "game_data_updated":
            if self.engine.tap("game_data_updated_ok", cooldown=2.0):
                print("[GLOBAL] Dismissing game data update", flush=True)
            return True

        return False
    