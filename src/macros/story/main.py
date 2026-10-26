import cv2

from api.common.layout import box_pixels
from api.flow import Flow, tap, wait, do, settle, auto_on, until
from api.recognition.recognition import Screen
from api.common.flows import story_setup, reward_popups, battle_complete
from api.runtime.ninjutsu import NINJUTSU_POINTS, apply as set_ninjutsu

BACK_SCREENS = (
    "story_stage_list", "story_mission_list", "select_story_difficulty",
    "select_helper", "select_team", "select_story_play_style",
)

HOME_ARRIVALS = ("story_mission_list", "story_stage_list", "home")

flow = Flow(
    "Story",
    poll=0.2,
    confirmations=2,
    tap_spacing=0.65,
    double_tap=("top_stage", "top_mission"),
    home=[("home_selected_mode", 0)],
    destination=("select_story_difficulty", "story_stage_list"),
    finish_mode="return_home",
    home_modes=("return_home",),
    points={
        "story_normal": (290, 955),
        "story_hard": (825, 955),
        "top_stage": (470, 540),
        "top_mission": (597, 876),
        "results_next": (570, 1920),
        "next_mission": (932, 1914),
        "back": (105, 355),
        **NINJUTSU_POINTS,
    },
    screens=[
        Screen("select_story_difficulty",
            phrases=("normal", "hard"),
            required=("select mode",),
            min_hits=1),

        Screen("story_mission_list",
            phrases=("details", "mission"),
            required=("stamina required",),
            negative=("select team", "select mode", "select style"),
            min_hits=1),

        Screen("story_stage_list",
            phrases=("gaiden", "complete all missions", "emergency mission"),
            required=("stage",),
            negative=("select mode", "select team", "stamina required", "select style", "mission results",
                      "special reward condition", "ryo earned"),
            min_hits=1),
    ],
    transitions={
        "game_intro_disclaimer": ("game_intro_main",),
        "game_intro_main": ("news", "home"),
        "news": ("home",),
        "home": ("select_story_difficulty", "story_stage_list"),
        "select_story_difficulty": ("story_stage_list",),
        "story_stage_list": ("story_mission_list",),
        "story_mission_list": ("select_story_play_style", "select_helper"),
        "select_story_play_style": ("select_helper",),
        "select_helper": ("select_team",),
        "select_team": ("battle",),
        "battle": ("battle_complete", "mission_results"),
        "battle_complete": ("mission_results", "completion_reward", "first_time_reward"),
        "mission_results": ("acquired_reward", "completion_reward", "first_time_reward", "home"),
    },
)
flow.arg("--difficulty", choices=["normal", "hard"], default="normal")

# home -> chapter -> top mission
flow.on("select_story_difficulty",
        tap(lambda ctx: "story_hard" if ctx.args.difficulty == "hard" else "story_normal",
            every=12, expect=("story_stage_list", 18)))
flow.on("story_stage_list", tap("top_stage"))

def top_mission_complete(frame):
    # the chapter's top mission shows a blue 'complete' badge on the left edge
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = box_pixels(0, 760, 160, 1020, w, h)
    region = frame[y1:y2, x1:x2]
    if region.size == 0:
        return None
    mask = cv2.inRange(cv2.cvtColor(region, cv2.COLOR_BGR2HSV), (80, 70, 100), (110, 255, 255))
    return cv2.countNonZero(mask) / mask.size >= 0.08

@flow.rule("story_mission_list")
def mission_list(ctx):
    if ctx.since < 0.5:
        return
    done = top_mission_complete(ctx.frame)
    if done is None:
        return
    if done:
        ctx.log("All missions in chapter complete")
        ctx.stop()
        return
    attempts = ctx.local.get("attempts", 0)
    if attempts >= 3:
        ctx.fail("Mission did not open after 3 attempts")
    if ctx.tap("top_mission", every=12, expect=(("select_story_play_style", "select_helper", "select_team"), 15)):
        ctx.local["attempts"] = attempts + 1

# play style -> helper -> team -> battle -> results
story_setup(flow, every=12, expect=True)
reward_popups(flow, every=0.65)
# give the battle 3s to start, then turn auto on, then turn ninjutsu on
flow.on("battle", wait(3), auto_on(), until(lambda ctx: set_ninjutsu(ctx, "on")))
battle_complete(flow, every=12)
flow.on("mission_results", "results_next", every=0.65)

# acquired rewards: skip the animation, then straight into the next mission
# if the next mission never opens (nothing left / not enough stamina), leave via Mission Complete and go Home
REWARD_SETTLE = settle("screen_center", min_s=5, quiet=1.5, max_s=9, every=0.5)
LEAVE = tap("mission_complete", expect=(HOME_ARRIVALS, 15))

flow.on("acquired_reward",
        REWARD_SETTLE,
        tap("next_mission"),
        wait(5),
        LEAVE,
        do(lambda ctx: ctx.set_mode("return_home")))
flow.count_run(on="acquired_reward", after=("select_team", "battle", "battle_complete"), label="Mission")

# return home mode: back out of whatever is open, then continue or stop
flow.on(BACK_SCREENS, tap("back", every=12), mode="return_home")
flow.on("acquired_reward", REWARD_SETTLE, LEAVE, mode="return_home")

@flow.rule("home", mode="return_home")
def arrived_home(ctx):
    ctx.log(f"Returned home; completed {ctx.runs} mission(s)")
    if ctx.finishing:
        ctx.stop()
    else:
        ctx.set_mode("main")
        