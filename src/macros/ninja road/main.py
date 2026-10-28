from datetime import datetime, timezone

import cv2

from api.flow import Flow, NEVER, wait, tap, do, until
from api.recognition.recognition import Screen
from api.common.flows import battle_complete, reward_pages
from api.runtime.ninjutsu import NINJUTSU_POINTS, SECRET_POINTS, ninjutsu as ninjutsu_button, secret as secret_button, apply as set_ninjutsu, apply_secret as set_secret

# retreat once this wave is ready
RETREAT_WAVE = 16
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
        # the Retreat button on the team select screen, left of Ready
        "retreat_planning": (302, 1518),
        "retreat_confirm": (802, 982),
        "results_next": (582, 1910),
        # OK on the box that says Ninja Road is closing
        "closed_ok": (566, 1000),
        **NINJUTSU_POINTS,
        **SECRET_POINTS,
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

        # the game closes Ninja Road when no team is left to fight with, this is the OK box
        Screen("ninja_road_closed",
            phrases=("all teams defeated", "no teams ready to participate"),
            required=("closing ninja road",),
            min_hits=1),

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
        "battle": ("battle_complete", "ninja_road_closed"),
        "ninja_road_closed": ("home", "ninja_road_challenge"),
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
# when the game closes Ninja Road tap OK to go back to a known screen
flow.on("ninja_road_closed", "closed_ok", every=2)

# after the battle
# on mission complete tap continue
battle_complete(flow)
# on each result page tap the middle 3 times then keep tapping next
reward_pages(flow, RESULT_PAGES, every=2.0, gap=0.4, delay=1.5, timeout=30)

# One run = back at the Challenge screen after the reward pages
# count one run when we are back on the challenge menu after the results
flow.count_run(on="ninja_road_challenge", after=RESULT_PAGES)

# keep trying the retreat for as long as we are still in the battle (only a screenshot is saved for the first few)
RETREAT_SHOTS = 5
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
# on the team select screen use its own Retreat button, no need to press Ready at all
RETREAT_PLANNING = [wait(0.5), tap("retreat_planning"), do(mark), until(dialog_ready), tap("retreat_confirm")]
# fallback: the menu only has Retreat once Ready has been pressed, so press Ready first
RETREAT_FROM_READY = [tap("ready"), wait(2), *RETREAT]
# tries with the team select button before falling back to Ready then the menu
PLANNING_TRIES = 2

def planning(ctx):
    return "select a team" in ctx.raw.lower()

def pick_steps(ctx, state):
    if planning(ctx) and state["planning"] < PLANNING_TRIES:
        state["planning"] += 1
        return RETREAT_PLANNING, "team select Retreat button"
    if waiting_for_ready(ctx):
        return RETREAT_FROM_READY, "press Ready first"
    return RETREAT, "menu"

def waiting_for_ready(ctx):
    # the team select screen is showing and we did not just press Ready (that screen can linger a moment)
    raw = ctx.raw.lower()
    return "select a team" in raw and "ready" in raw and ctx.now - ctx.run.get("ready_at", float("-inf")) > 3

# the buttons are covered by the Ready screen until Ready is pressed, so they are only set after it
# last state each button was confirmed in this session; lets the first tap go out the moment Ready is pressed
KNOWN = {}
BUTTONS = {"ninjutsu": ninjutsu_button, "secret": secret_button}

def switch_now(ctx, wanted):
    # a button we know is in the wrong state gets tapped right away, the normal check afterwards confirms it
    for name, want in wanted.items():
        if want and KNOWN.get(name) and KNOWN[name] != want:
            BUTTONS[name].flip(ctx.engine)

# the jutsu plan, one wave at a time:
#   waves 1-4   ninjutsu off, secret off
#   wave 5      secret only
#   waves 6-13  ninjutsu only
#   wave 14     both off
#   wave 15     secret only
#   wave 16     retreat (Ready is never pressed on it)
SECRET_WAVES = (5, 15)
NINJUTSU_WAVES = range(6, 14)

def wanted_toggles(ctx, wave):
    # (ninjutsu, secret) for this wave
    if wave in SECRET_WAVES:
        return "off", "on"
    if wave in NINJUTSU_WAVES:
        return "on", "off"
    return "off", "off"

# shown once when the macro starts
TESTED_WITH = (
    "Tested team:",
    "  Duo, Madara, Bee",
    "  Passive healing bench",
    "  8 minute run",
)
intro_shown = False

@flow.always
def intro(ctx):
    global intro_shown
    if intro_shown:
        return
    intro_shown = True
    for line in TESTED_WITH:
        ctx.log(line)

# runs on every screen because the retreat menu is not read as battle
@flow.always
def retreat(ctx):
    run = ctx.run
    if not run.get("retreating"):
        return
    state = run.setdefault("retreat", {"tries": 0, "planning": 0, "active": False, "done_at": None})

    # start a fresh attempt or give up after too many
    if not state["active"]:
        state["tries"] += 1
        state["active"], state["done_at"] = True, None
        state["steps"], how = pick_steps(ctx, state)
        run.get("_plays", {}).pop("retreat", None)
        ctx.log(f"Retreat try {state['tries']} ({how})")

    # run the steps and note when the last tap went out
    if state["done_at"] is None:
        if ctx.play("retreat", state["steps"]):
            state["done_at"] = ctx.now
        return

    # still fighting a while after the confirm so the retreat missed and we try again
    # the team select screen counts too since the game can land back on it
    if (ctx.screen == "battle" or "select a team" in ctx.raw.lower()) and ctx.now - state["done_at"] > RETREAT_CHECK:
        note = ""
        if state["tries"] <= RETREAT_SHOTS:
            path = f"ninja_road_retreat_{state['tries']}.png"
            cv2.imwrite(path, ctx.frame)
            note = f" (screenshot {path}; OCR: {ctx.raw[:120]!r})"
        ctx.log(f"Still in battle after retreat; trying again{note}")
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
        # look at the buttons again every wave in case an earlier read was wrong (this does not hold Ready back)
        run["checked"] = {}

    # retreat is running so do nothing else
    if run.get("retreating"):
        return

    # in wave 1 turn auto on once
    if wave.current == 1 and not run.get("auto") and ctx.auto_on():
        run["auto"] = True
        ctx.log("Auto confirmed ON for wave 1")

    # once auto is on set the buttons for this wave and keep trying until each is confirmed
    # secret goes first so it is off before ninjutsu comes on
    if run.get("auto"):
        want_ninjutsu, want_secret = wanted_toggles(ctx, wave.current)
        done = run.setdefault("toggles", {})
        checked = run.setdefault("checked", {})
        # only once Ready is pressed for this wave, before that the Ready screen covers the buttons
        if wave.current in run.get("ready", ()):
            if want_secret and (done.get("secret") != want_secret or not checked.get("secret")) and set_secret(ctx, want_secret):
                done["secret"] = checked["secret"] = KNOWN["secret"] = want_secret
            if want_ninjutsu and (done.get("ninjutsu") != want_ninjutsu or not checked.get("ninjutsu")) and set_ninjutsu(ctx, want_ninjutsu):
                done["ninjutsu"] = checked["ninjutsu"] = KNOWN["ninjutsu"] = want_ninjutsu

    # wait until the ready button has shown on 2 reads
    if ctx.battle.ready_seen < 2:
        return

    # waves we already pressed ready on
    ready = run.setdefault("ready", set())

    # on the wave we leave from do not press Ready, the retreat handler uses the Retreat button here
    if wave.current >= RETREAT_WAVE:
        run["retreating"] = True
        ctx.log(f"Wave {wave.current} team select; retreating")
        return

    # press ready once per wave and use the first ready button in wave 1
    if wave.current not in ready and ctx.tap("initial_ready" if wave.current == 1 else "ready", spacing=0.5):
        ready.add(wave.current)
        run["ready_at"] = ctx.now
        # switch the buttons the same moment, before the units can use a technique
        if run.get("auto"):
            want_ninjutsu, want_secret = wanted_toggles(ctx, wave.current)
            switch_now(ctx, {"ninjutsu": want_ninjutsu, "secret": want_secret})
            