from datetime import datetime, timezone

import cv2

from api.flow import Flow, NEVER, wait, tap, do, until
from api.recognition.recognition import Screen
from api.common.flows import battle_complete, reward_pages
from api.runtime.ninjutsu import NINJUTSU_POINTS, apply as set_ninjutsu

# retreat once this wave is ready
RETREAT_WAVE = 13
# the three result pages after a run
REWARDS = ("ninja_road_reward_1", "ninja_road_reward_2", "ninja_road_reward_3")
# the first result page can also be read as mission_results because both match equally
RESULT_PAGES = (*REWARDS, "mission_results")

flow = Flow(
    "Ninja Road",
    # check the screen 5 times a second
    poll=0.2,
    # a wave must be read twice in a row to count
    wave_confirmations=2,
    # fail if one screen lasts over 90 seconds
    stall=90,
    # from home tap ninja road then tap the selected mode
    home=[("select_ninja_road", 0), ("home_selected_mode", 0.5)],
    # home navigation is done when this screen shows
    destination="ninja_road_challenge",

    expires=(datetime(2026, 11, 1, 11, 0, tzinfo=timezone.utc), "Ninja Road has changed! Wait for updates."),

    points={
        "select_ninja_road": (1021, 1336),
        "challenge": (560, 1605),
        "start_mission": (560, 1605),
        "initial_ready": (544, 1515),
        "ready": (807, 1525),
        "retreat_button": (331, 1195),
        "retreat_confirm": (800, 980),
        "results_next": (582, 1910),
        **NINJUTSU_POINTS,
    },

    screens=[
        # first result page
        Screen("ninja_road_reward_1",
            phrases=("special reward condition", "ryo earned", "next ninja rank"),
            required=("ninja road",),
            min_hits=2),

        # map rewards page
        Screen("ninja_road_reward_2",
            required=("ninja road", "map rewards", "present box"),
            min_hits=0),

        # final results page
        Screen("ninja_road_reward_3",
            required=("ninja road", "rare map completion reward", "final results"),
            min_hits=0),

        # menu with the challenge button
        Screen("ninja_road_challenge",
            required=("ninja road", "challenge"),
            negative=("mission results",),
            min_hits=0),

        # team screen with the start button
        Screen("select_ninja_road_team",
            required=("ninja road", "start mission"),
            negative=("mission results",),
            min_hits=0),
    ],
    # helps the reader guess the next screen from the last one
    transitions={
        "game_intro_disclaimer": ("game_intro_main",),
        "game_intro_main": ("news", "home"),
        "news": ("home",),
        "home": ("ninja_road_challenge",),
        "ninja_road_challenge": ("select_ninja_road_team",),
        "select_ninja_road_team": ("battle",),
        "battle": ("battle_complete",),
        "battle_complete": ("ninja_road_reward_1",),
        "ninja_road_reward_1": ("ninja_road_reward_2",),
        "ninja_road_reward_2": ("ninja_road_reward_3",),
        "ninja_road_reward_3": ("ninja_road_challenge",),
    },
)

# on the challenge menu tap challenge and retry every 5 seconds
flow.on("ninja_road_challenge", "challenge", every=5)
# on team select tap start mission and retry every 5 seconds
flow.on("select_ninja_road_team", "start_mission", every=5)

# after the battle
# on mission complete tap continue
battle_complete(flow)
# on each result page tap the middle 3 times then keep tapping next
reward_pages(flow, RESULT_PAGES, every=2.0, gap=0.4, delay=1.5, timeout=30)

# One run = back at the Challenge screen after the reward pages
# count one run when we are back on the challenge menu after the results
flow.count_run(on="ninja_road_challenge", after=RESULT_PAGES)

# how many times to try the retreat before giving up loudly
RETREAT_TRIES = 4
# if still in battle this many seconds after the last confirm tap the retreat did not work
RETREAT_CHECK = 8

def mark(ctx):
    ctx.run["retreat"]["menu_at"] = ctx.now

def dialog_ready(ctx):
    # go on once the are you sure box is read or after 4 seconds so a bad read never blocks us
    if "are you sure" in ctx.raw.lower():
        return True
    if ctx.now - ctx.run["retreat"]["menu_at"] > 4:
        ctx.log("Retreat box not read after 4 seconds; confirming anyway")
        return True
    return False

# retreat steps are menu then retreat then wait for the box then confirm
RETREAT = [wait(1), tap("battle_menu"), wait(1), tap("retreat_button"), do(mark), until(dialog_ready), tap("retreat_confirm")]
# the menu only has Retreat once Ready has been pressed, so from the team select screen press Ready first
RETREAT_FROM_READY = [tap("ready"), wait(2), *RETREAT]

def waiting_for_ready(ctx):
    # the team select screen is showing and we did not just press Ready (that screen can linger a moment)
    raw = ctx.raw.lower()
    return "select a team" in raw and "ready" in raw and ctx.now - ctx.run.get("ready_at", float("-inf")) > 3

# runs on every screen because the retreat menu is not read as battle
@flow.always
def retreat(ctx):
    run = ctx.run
    if not run.get("retreating"):
        return
    state = run.setdefault("retreat", {"tries": 0, "active": False, "done_at": None})

    # start a fresh attempt or give up after too many
    if not state["active"]:
        if state["tries"] >= RETREAT_TRIES:
            ctx.fail(f"Retreat did not leave the battle after {RETREAT_TRIES} tries")
        state["tries"] += 1
        state["active"], state["done_at"] = True, None
        state["steps"] = RETREAT_FROM_READY if waiting_for_ready(ctx) else RETREAT
        run.get("_plays", {}).pop("retreat", None)
        ctx.log(f"Retreat try {state['tries']}/{RETREAT_TRIES} ({'press Ready first' if state['steps'] is RETREAT_FROM_READY else 'menu'})")

    # run the steps and note when the last tap went out
    if state["done_at"] is None:
        if ctx.play("retreat", state["steps"]):
            state["done_at"] = ctx.now
        return

    # still fighting a while after the confirm so the retreat missed and we try again
    if ctx.screen == "battle" and ctx.now - state["done_at"] > RETREAT_CHECK:
        path = f"ninja_road_retreat_{state['tries']}.png"
        cv2.imwrite(path, ctx.frame)
        ctx.log(f"Still in battle after retreat; trying again (screenshot {path}; OCR: {ctx.raw[:120]!r})")
        state["active"] = False

# runs again and again while in battle with no time limit
@flow.rule("battle", timeout=NEVER)
def battle(ctx):
    wave, run = ctx.wave, ctx.run
    # no wave read yet so do nothing
    if wave.current is None:
        return
    # log each new wave
    if wave.changed:
        ctx.log(f"Wave {wave.current}/{wave.total}")

    # retreat is running so do nothing else
    if run.get("retreating"):
        return

    # in wave 1 turn auto on once
    if wave.current == 1 and not run.get("auto") and ctx.auto_on():
        run["auto"] = True
        ctx.log("Auto confirmed ON for wave 1")

    # once auto is on turn ninjutsu on too and keep trying each wave until it is confirmed
    if run.get("auto") and not run.get("ninjutsu") and set_ninjutsu(ctx, "on"):
        run["ninjutsu"] = True

    # wait until the ready button has shown on 2 reads
    if ctx.battle.ready_seen < 2:
        return

    # waves we already pressed ready on
    ready = run.setdefault("ready", set())

    # press ready once per wave and use the first ready button in wave 1
    if wave.current not in ready and ctx.tap("initial_ready" if wave.current == 1 else "ready", spacing=0.5):
        ready.add(wave.current)
        run["ready_at"] = ctx.now

        if wave.current >= RETREAT_WAVE:
            run["retreating"] = True
            ctx.log(f"Wave {wave.current} ready; retreating")
            