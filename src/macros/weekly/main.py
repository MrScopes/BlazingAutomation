from api.common.layout import to_reference
from api.flow import Flow, wait, taps, auto_on, until
from api.runtime.ninjutsu import NINJUTSU_POINTS, SECRET_POINTS, apply as set_ninjutsu, apply_secret as set_secret
from api.recognition.recognition import Screen
from api.common.flows import story_setup, reward_popups, battle_complete

# screens on the way in; the play style, helper and team screens are the shared ones
PLAY_SCREENS = ("select_story_play_style", "select_helper", "select_team")

# the banners on the Weekly tab, as they read on screen
BANNERS = ("getting rich quick", "searching for body scrolls", "ramen report", "energizing cup", "ryo acquisition")

flow = Flow(
    "Weekly Missions",
    poll=0.2,
    confirmations=2,
    # from home slide right to the Emergency Mission browser
    home=[("home_right", 0), ("home_selected_mode", 1.0)],
    destination=("weekly_browser", "weekly_list", "weekly_mission_list"),
    # a double tap on the difficulty opens the mission
    double_tap=("weekly_ss", "weekly_s", "weekly_a"),
    points={
        # the Weekly tab
        "weekly_tab": (251, 456),
        # banners on the Weekly tab: scroll and ramen sit above Getting Rich Quick
        "weekly_scroll": (545, 865),
        "weekly_ramen": (539, 1224),
        # Getting Rich Quick is found from its text; this is only where it is expected when the text cannot be located
        "weekly_rich": (539, 1583),
        "weekly_ss": (535, 883),
        "weekly_s": (535, 1207),
        "weekly_a": (535, 1527),
        "results_next": (578, 1912),
        # Retry on the Acquired Reward page
        "retry": (562, 1915),
        **NINJUTSU_POINTS,
        **SECRET_POINTS,
    },
    screens=[
        # difficulty list of the chosen mission with its [SS] [S] [A] entries
        Screen("weekly_mission_list",
            phrases=("complete", "perfect", "[ss]"),
            required=("details", "stamina required"),
            negative=("select play style", "gather friends", "solo mission", "select team", "mission results", "select a helper", "weekly"),
            min_hits=0),

        # Weekly tab with its banners
        Screen("weekly_list",
            phrases=BANNERS,
            required=("weekly", "select a mission"),
            negative=("details", "stamina required", "select play style", "gather friends", "solo mission", "select team"),
            min_hits=1),

        # Emergency Mission browser before the Weekly tab is open
        Screen("weekly_browser",
            phrases=("trial mission", "super impact", "custom"),
            required=("emergency mission", "weekly"),
            negative=(*BANNERS[:4], "rich quick", "details", "stamina required", "select play style", "endless waves", "mission results"),
            min_hits=1),
    ],
    transitions={
        "home": ("weekly_browser", "weekly_list"),
        "weekly_browser": ("weekly_list",),
        "weekly_list": ("weekly_mission_list",),
        "weekly_mission_list": ("select_story_play_style",),
        "select_story_play_style": ("select_helper",),
        "select_helper": ("select_team",),
        "select_team": ("battle",),
        "battle": ("battle_complete", "mission_results"),
        "battle_complete": ("mission_results",),
        "mission_results": ("acquired_reward",),
    },
)

flow.arg("--mission", choices=["rich", "scroll", "ramen"], default="rich",
         help="rich = Getting Rich Quick, scroll = Searching for Body Scrolls, ramen = Ramen Report.")
flow.arg("--difficulty", choices=["ss", "s", "a"], default="ss",
         help="SS costs the most stamina and has the best reward.")

# open the Weekly tab, retry every 3 seconds until the banners show
flow.on("weekly_browser", "weekly_tab", every=3)

def rich_point(ctx):
    # Getting Rich Quick has no fixed spot given, so tap where its text is read
    items = getattr(getattr(ctx.engine.driver, "reader", None), "items", ()) or ()
    for words in (("rich", "quick"), ("getting",)):
        for text, x, y in items:
            low = text.lower()
            if all(word in low for word in words):
                driver = ctx.engine.driver
                return to_reference(x, y, driver.width, driver.height)
    return None

@flow.rule("weekly_list")
def weekly_list(ctx):
    if ctx.since < 0.5:
        return
    point = f"weekly_{ctx.args.mission}"
    if ctx.args.mission == "rich":
        found = rich_point(ctx)
        if found:
            ctx.engine.actions.points[point] = tuple(round(v) for v in found)
    ctx.tap(point, every=4, expect=((("weekly_mission_list",) + PLAY_SCREENS), 15))

# choose the difficulty (double tap), retry every 5 seconds
@flow.rule("weekly_mission_list")
def mission_list(ctx):
    if ctx.since < 0.5:
        return
    ctx.tap(f"weekly_{ctx.args.difficulty}", every=5, expect=(PLAY_SCREENS, 15))

# solo -> first helper -> start mission
story_setup(flow, every=4)
reward_popups(flow)

# 3 seconds for the battle to start, then auto on, then secret off and ninjutsu on
flow.on("battle",
        wait(3), auto_on(),
        until(lambda ctx: set_secret(ctx, "off")),
        until(lambda ctx: set_ninjutsu(ctx, "on")),
        timeout=600)
battle_complete(flow)

# results: a Special Reward box can sit on top of the page, its OK has to be pressed before Next works
@flow.rule("mission_results", timeout=120)
def results(ctx):
    if "present box" in ctx.raw.lower():
        ctx.tap("reward_ok", every=1.5)
    else:
        ctx.tap("results_next", every=5)

# acquired rewards: tap through the drops (5 taps, 0.5 seconds apart), then Retry
flow.on("acquired_reward", taps("screen_center", 5, 0.5), wait(1.0), "retry", every=3.0, timeout=120)

# one run = Retry brought us back to team select
flow.count_run(on="select_team", after="acquired_reward")
