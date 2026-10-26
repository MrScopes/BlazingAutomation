from api.flow import tap, taps, wait

# popup screens that just need their OK button pressed
REWARD_OK = {
    "completion_reward": "reward_ok",
    "first_time_reward": "first_time_reward_ok",
    "stamina_restored": "stamina_restored_ok",
    "reward_popup": "reward_ok",
}

def reward_popups(flow, every=1.5):
    for screen, point in REWARD_OK.items():
        flow.on(screen, point, every=every)

def battle_complete(flow, every=1.5):
    flow.on("battle_complete", "battle_continue", every=every)

def story_setup(flow, every=4.0, expect=False):
    def go(point, *screens_timeout):
        return tap(point, every=every, expect=screens_timeout if expect else None)

    flow.on("select_story_play_style", go("solo", ("select_helper", "select_team"), 18))
    flow.on("select_helper", go("first_helper", ("select_team", "battle", "battle_complete", "mission_results"), 18))
    flow.on("select_team", go("start_mission", ("battle", "battle_complete", "mission_results"), 45), timeout=65)

def reward_pages(flow, screens, every=2.0, first_taps=3, gap=0.35, delay=1.0, timeout=None):
    flow.on(screens, taps("screen_center", first_taps, gap), wait(delay), "results_next", every=every, timeout=timeout)
