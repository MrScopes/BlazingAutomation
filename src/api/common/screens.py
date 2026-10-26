from api.recognition.recognition import Screen

COMMON_SCREENS = [
    Screen("game_data_updated",
        phrases=("game data changed", "load the new data", "title screen", "nothing is lost"),
        required=("game data updated",),
        min_hits=2),

    Screen("game_intro_disclaimer",
        phrases=("free to play", "in-app purchase", "enjoy playing"),
        required=("naruto shippuden",),
        min_hits=2),

    Screen("game_intro_main",
        phrases=("delete cache", "data transfer", "check encyclopedia", "linked", "dl all"),
        required=("tap to start",),
        min_hits=2),
        
    Screen("news",
        phrases=("important", "event", "notice", "information", "update"),
        required=("news", "close"),
        negative=("mission results", "select a helper", "select team"),
        min_hits=3),

    Screen("home",
        phrases=("summon", "multiplayer", "teams", "shop"),
        required=("villages",),
        negative=(
            "back story",
            "gaiden",
            "select mode",
            "select a helper",
            "select team",
            "select play style",
            "solo mission",
            "gather friends",
            "stamina required",
            "mission results",
            "emergency mission",
            "ninja road",
            "farthest point",
            "total map completion reward",
            "game data updated",
        ),
        min_hits=1),

    Screen("battle_complete",
        required=("mission complete",),
        negative=("mission results", "acquired reward", "completion reward conditions", "next mission"),
        min_hits=0),

    # solo/gather friends
    Screen("select_story_play_style",
        phrases=("solo mission", "gather friends"),
        required=("select play style",),
        negative=("mission results",),
        min_hits=1),

    Screen("select_helper",
        phrases=("friend points", "syncable"),
        required=("select a helper",),
        negative=("select team",),
        min_hits=1),

    Screen("select_team",
        phrases=("start mission", "sync skill", "total cost", "total health", "change placement", "lucky drop rate"),
        required=("select team",),
        negative=("select mode", "select helper", "select style", "ninja road"),
        min_hits=1),

    Screen("completion_reward",
        phrases=("ninja pearl", "present box", "will be sent", "ok"),
        required=("completion reward",),
        negative=("first time",),
        min_hits=1),

    Screen("first_time_reward",
        phrases=("first time completion", "ninja pearl", "reward", "ok"),
        required=("first time",),
        min_hits=1),

    Screen("stamina_restored",
        phrases=("phantom castle stamina", "fully restored", "ok"),
        required=("your stamina has been fully restored",),
        min_hits=1),

    Screen("reward_popup",
        phrases=("special reward", "will be sent"),
        required=("present box",),
        negative=("granny cat coins", "8 map", "12 map", "ninja road"),
        min_hits=1),

    Screen("acquired_reward",
        phrases=("mission results", "completion reward conditions", "retry", "next mission"),
        required=("acquired reward",),
        min_hits=1),

    Screen("mission_results",
        phrases=("special reward condition", "ryo earned", "next ninja rank", "exp"),
        required=("mission results",),
        negative=("acquired reward", "select style", "solo mission"),
        min_hits=1),

    Screen("battle",
        phrases=("auto play", "ninjutsu", "secret technique", "auto", "menu", "map", "x3", "x2"),
        required=("map", "auto"),
        negative=("mission complete",),
        min_hits=2),
]