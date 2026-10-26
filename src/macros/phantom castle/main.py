import re

from api.flow import Flow, START_MODE
from api.runtime.ninjutsu import NINJUTSU_POINTS, apply as set_ninjutsu
from api.recognition.recognition import Screen

# the three taps that finish a fight and get back to the menu
FINISH = ("finish_a", "finish_b", "finish_c")

flow = Flow(
    "Phantom Castle",
    # check the screen 10 times a second
    poll=0.1,
    # 0.1 seconds between taps so the finish taps go fast
    tap_spacing=0.1,
    # we handle home ourselves below because the built in home steps restart
    # whenever the screen flickers while the home banners slide
    home_modes=(START_MODE,),

    points={
        "challenge": (549, 1614),
        "opponent_1": (233, 1639),
        "opponent_2": (573, 1641),
        "opponent_3": (865, 1648),
        "stamina_yes": (744, 1336),
        "stamina_ok": (562, 1092),
        **NINJUTSU_POINTS,
        "finish_a": (571, 1635),
        "finish_b": (595, 1053),
        "finish_c": (851, 1296),
    },

    screens=[
        # main menu with the team setup and challenge buttons
        Screen("phantom_castle_menu",
            phrases=("history", "rankings", "reward", "team setup", "challenge", "until next recovery"),
            required=("phantom castle", "team setup"),
            negative=("opponent update", "field effects", "recover pc stamina", "stamina restored"),
            min_hits=2),

        # popup asking to spend a ninja pearl to refill stamina
        Screen("phantom_castle_stamina",
            phrases=("not enough phantom castle stamina", "ninja pearl", "refill", "no yes"),
            required=("recover pc stamina",),
            min_hits=1),

        # popup saying the stamina was refilled
        Screen("phantom_castle_stamina_restored",
            phrases=("phantom castle", "ok"),
            required=("stamina restored",),
            negative=("recover pc stamina", "not enough"),
            min_hits=1),

        # list of opponents with a battle button each
        Screen("phantom_castle_opponents",
            phrases=("opponent update", "battle", "team 1/7", "vs"),
            required=("phantom castle", "field effects"),
            negative=("recover pc stamina", "stamina restored"),
            min_hits=1),

        # the fight itself
        Screen("phantom_castle_battle",
            phrases=("auto play", "autoplay", "latent techniques", "skill", "ghost of"),
            required=("ninjutsu", "secret"),
            negative=("mission complete", "points earned"),
            min_hits=1),

        # points counting up after the win
        Screen("phantom_castle_results",
            phrases=("total po", "next floor", "highest floor"),
            required=("points earned",),
            min_hits=0),
    ],
)

# the menu also shows the home bar at the bottom so home ties with it at 100
# list our screens first so they win ties
mine = [screen for screen in flow.screens if screen.name.startswith("phantom_castle")]
flow.screens = mine + [screen for screen in flow.screens if screen not in mine]

# on home tap left 3 times 0.2 seconds apart then tap the selected mode
# the count lives with this screen visit so a flicker to an unknown screen does not restart it
@flow.rule("home", timeout=40)
def open_phantom_castle(ctx):
    # a stray home read right after a fight must not send us back through the banners
    if ctx.run.get("fought"):
        return
    st = ctx.local
    if st.get("lefts", 0) < 3:
        if ctx.tap("home_left", spacing=0.2):
            st["lefts"] = st.get("lefts", 0) + 1
            st["last"] = ctx.now
        return
    # short pause after the last left tap
    if ctx.now - st["last"] < 0.5:
        return
    if ctx.tap("home_selected_mode", every=6):
        st["opens"] = st.get("opens", 0) + 1
        # the mode did not open after 2 tries so start over from the left taps
        if st["opens"] >= 2:
            ctx.log("Mode did not open; starting over")
            st.clear()

# on the menu tap challenge and retry every 3 seconds
flow.on("phantom_castle_menu", "challenge", every=3)

# out of stamina so press yes to refill it with a ninja pearl
flow.on("phantom_castle_stamina", "stamina_yes", every=2)

# stamina is full again so press ok
flow.on("phantom_castle_stamina_restored", "stamina_ok", every=2)

# a bigger rank number means a weaker opponent so we fight the biggest one
@flow.rule("phantom_castle_opponents")
def pick_opponent(ctx):
    st = ctx.local
    # the ranks come after the words opponent update and the first 3 are left to right
    text = ctx.raw.lower()
    after = text.split("opponent update", 1)[-1] if "opponent update" in text else ""
    ranks = tuple(int(n) for n in re.findall(r"rank\s*(\d{1,5})", after))[:3]
    # need all 3 ranks and the same read twice in a row before we trust it
    if len(ranks) < 3 or ranks != st.get("seen"):
        st["seen"] = ranks
        return
    best = ranks.index(max(ranks)) + 1
    if ctx.tap(f"opponent_{best}", every=3):
        ctx.log(f"Ranks {ranks[0]} / {ranks[1]} / {ranks[2]}; fighting opponent {best}")

# one run = back at the menu after a fight
flow.count_run(on="phantom_castle_menu", after="phantom_castle_battle")

# seconds between finish taps
FINISH_GAP = 0.2

# fights can take a while so the battle has a long limit
@flow.rule("phantom_castle_battle", timeout=600)
def battle(ctx):
    ctx.run["fought"] = True
    # turn auto on once at the start of each fight and log when it is confirmed
    if not ctx.run.get("auto") and not ctx.run.get("victory") and ctx.auto_on():
        ctx.run["auto"] = True
        ctx.log("Auto confirmed ON")
    # once auto is on turn ninjutsu on too and log when it is confirmed
    if ctx.run.get("auto") and not ctx.run.get("ninjutsu") and not ctx.run.get("victory"):
        if set_ninjutsu(ctx, "on"):
            ctx.run["ninjutsu"] = True

    # the big Victory or Defeat banner shows on the fight screen
    # the reader often drops the first letter so look for ictory and efeat
    if not ctx.run.get("victory"):
        text = ctx.raw.lower()
        result = "Victory" if "ictory" in text else "Defeat" if "efeat" in text else None
        if result:
            ctx.run["victory"] = True
            ctx.log(f"{result}; tapping until the challenge menu")

# once victory shows keep tapping the 3 finish points until the menu shows again
@flow.always
def finish(ctx):
    run = ctx.run
    if not run.get("victory"):
        return
    if ctx.screen in ("phantom_castle_menu", "phantom_castle_opponents"):
        return
    # wait the gap between taps
    if ctx.now - run.get("finish_at", 0) < FINISH_GAP:
        return
    # one point per check and go round the 3 in order
    n = run.get("finish_i", 0)
    if ctx.tap(FINISH[n % len(FINISH)]):
        run["finish_i"] = n + 1
        run["finish_at"] = ctx.now
        