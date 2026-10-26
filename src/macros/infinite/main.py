from api.flow import Flow, wait, auto_on, until
from api.runtime.ninjutsu import NINJUTSU_POINTS, apply as set_ninjutsu
from api.recognition.recognition import Screen
from api.common.flows import story_setup, reward_popups, battle_complete, reward_pages

flow = Flow(
    "Infinite",
    poll=0.2,
    confirmations=2,
    home=[("home_right", 0), ("home_selected_mode", 1.0)],
    destination=("infinite_mission_browser", "infinite_banner_list", "infinite_difficulty"),
    points={
        "infinite_scroll": (1113, 778),
        "infinite_banner": (569, 1269),
        "infinite_normal": (529, 1525),
        "results_next": (578, 1912),
        **NINJUTSU_POINTS,
    },
    screens=[
        Screen("infinite_battle",
            phrases=("wave", "kills", "auto", "menu", "ninjutsu", "secret", "latent techniques"),
            required=("wave", "auto"),
            negative=("mission complete",),
            min_hits=3),

        Screen("infinite_difficulty",
            phrases=("infinite [ss]", "infinite [hard]", "infinite [normal]"),
            required=("endless waves", "infinite [normal]"),
            negative=("select play style",),
            min_hits=1),

        Screen("infinite_banner_list",
            phrases=("new ninja race", "impact", "custom"),
            required=("endless waves", "infinite"),
            negative=("infinite [normal]", "select play style"),
            min_hits=1),

        Screen("infinite_mission_browser",
            phrases=("trial mission", "super impact", "custom"),
            required=("emergency mission", "custom"),
            negative=("endless waves", "select play style"),
            min_hits=1),
    ],
)

flow.on("infinite_mission_browser", "infinite_scroll", every=3)
flow.on("infinite_banner_list", "infinite_banner", every=3)
flow.on("infinite_difficulty", "infinite_normal", every=3)

# solo -> helper -> team -> start
story_setup(flow, every=4)
reward_popups(flow)

# give the battle 3s to start, then turn auto on, then turn ninjutsu on
flow.on("infinite_battle", wait(3), auto_on(), until(lambda ctx: set_ninjutsu(ctx, "on")), timeout=900)
battle_complete(flow)

# results -> acquired rewards -> Retry
flow.on("mission_results", "results_next", every=5, timeout=120)
reward_pages(flow, "acquired_reward", every=3.0, delay=1.0, timeout=120)

# one run = pressing retry brought us back to team select
flow.count_run(on="select_team", after="acquired_reward")
