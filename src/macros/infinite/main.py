import argparse
import re

from api.flow import Flow, NEVER, wait, tap, do, auto_on, until
from api.runtime.ninjutsu import NINJUTSU_POINTS, apply as set_ninjutsu
from api.recognition.recognition import Screen
from api.common.flows import story_setup, reward_popups, battle_complete, reward_pages

def wave_number(text):
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("the wave must be 1 or higher")
    return value

flow = Flow(
    "Infinite",
    poll=0.2,
    confirmations=2,
    home=[("home_right", 0), ("home_selected_mode", 1.0)],
    destination=("infinite_mission_browser", "infinite_banner_list", "infinite_difficulty"),
    points={
        # the Custom tab on the Emergency Mission browser
        "infinite_custom": (708, 565),
        "infinite_banner": (569, 1269),
        "infinite_normal": (529, 1525),
        "results_next": (578, 1912),
        # the Retreat button in the battle menu and the Yes on its "are you sure" box
        "retreat_button": (331, 1195),
        "retreat_confirm": (802, 982),
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

# the launcher asks for this; leaving it empty means never leave early
flow.arg("--leave-on-wave", type=wave_number, default=None,
         help="retreat from the battle once this wave is reached (empty = play until the team is defeated)")

# open the Custom tab (retried every 3 seconds until the banner list shows), then the banner is picked below
flow.on("infinite_mission_browser", "infinite_custom", every=3)
flow.on("infinite_banner_list", "infinite_banner", every=3)
flow.on("infinite_difficulty", "infinite_normal", every=3)

# solo -> helper -> team -> start
story_setup(flow, every=4)
reward_popups(flow)

# give the battle 3s to start, then turn auto on, then turn ninjutsu on
# an Infinite battle lasts as long as the team survives (well past 15 minutes), so it has no time limit
flow.on("infinite_battle", wait(3), auto_on(), until(lambda ctx: set_ninjutsu(ctx, "on")), timeout=NEVER)
battle_complete(flow)

# ---------------------------------------------------------------- leave on a chosen wave
# the wave counter reads like "Wave 12"; a number must be read twice in a row to count and the count never goes down
WAVE_PATTERN = re.compile(r"\bwave\s*[:.\-]?\s*(\d{1,4})\b", re.I)
# how many seconds after the confirm tap a battle that is still going counts as a missed retreat
RETREAT_CHECK = 8
# warn once if no wave number could be read this long into a battle
NO_WAVE_WARNING = 45

def mark(ctx):
    ctx.run["retreat"]["menu_at"] = ctx.now

def dialog_ready(ctx):
    # go on once the "are you sure" box is read, or after 4 seconds so a bad read never blocks us
    if "are you sure" in ctx.raw.lower():
        return True
    if ctx.now - ctx.run["retreat"]["menu_at"] > 4:
        ctx.log("Retreat box not read after 4 seconds; confirming anyway")
        return True
    return False

RETREAT = [wait(1), tap("battle_menu"), wait(1), tap("retreat_button"), do(mark), until(dialog_ready), tap("retreat_confirm")]

def read_wave(ctx):
    # returns the confirmed wave, logging each new one
    run = ctx.run
    match = WAVE_PATTERN.search(ctx.raw)
    if not match:
        return run.get("wave")
    seen = int(match.group(1))
    if seen == run.get("wave_candidate"):
        run["wave_count"] = run.get("wave_count", 0) + 1
    else:
        run["wave_candidate"], run["wave_count"] = seen, 1
    if run["wave_count"] >= 2 and seen > run.get("wave", 0):
        run["wave"] = seen
        ctx.log(f"Wave {seen}")
    return run.get("wave")

# runs on every screen because the battle menu and its boxes are not read as the battle screen
@flow.always
def leave(ctx):
    target = ctx.args.leave_on_wave
    if target is None:
        return
    run = ctx.run

    if not run.get("retreating"):
        if ctx.screen != "infinite_battle":
            return
        run.setdefault("battle_since", ctx.now)
        wave = read_wave(ctx)
        if wave is None:
            if ctx.now - run["battle_since"] > NO_WAVE_WARNING and not run.get("warned"):
                run["warned"] = True
                ctx.log(f"No wave number read yet; OCR: {ctx.raw[:150]!r}")
            return
        if wave >= target:
            run["retreating"] = True
            ctx.log(f"Reached wave {wave} (leave on wave {target}); retreating")
        return

    state = run.setdefault("retreat", {"tries": 0, "active": False, "done_at": None})
    if not state["active"]:
        state["tries"] += 1
        state["active"], state["done_at"] = True, None
        run.get("_plays", {}).pop("retreat", None)
        ctx.log(f"Retreat try {state['tries']}")

    if state["done_at"] is None:
        if ctx.play("retreat", RETREAT):
            state["done_at"] = ctx.now
        return

    # still fighting a while after the confirm: the retreat missed, try again
    if ctx.screen == "infinite_battle" and ctx.now - state["done_at"] > RETREAT_CHECK:
        ctx.log("Still in battle after retreat; trying again")
        state["active"] = False

# results -> acquired rewards -> Retry
# a Special Reward box ("will be sent to the Present Box") can sit on top of the results page; its OK has to be
# pressed first, the Next button underneath does nothing while the box is open
@flow.rule("mission_results", timeout=120)
def results(ctx):
    if "present box" in ctx.raw.lower():
        ctx.tap("reward_ok", every=1.5)
    else:
        ctx.tap("results_next", every=5)
reward_pages(flow, "acquired_reward", every=3.0, delay=1.0, timeout=120)

# one run = pressing retry brought us back to team select
flow.count_run(on="select_team", after="acquired_reward")
