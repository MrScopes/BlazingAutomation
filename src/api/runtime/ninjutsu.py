from .auto import ToggleDetector
 
# where each button is tapped
NINJUTSU_POINTS = {"ninjutsu_button": (213, 1780)}
SECRET_POINTS = {"secret_button": (584, 1782)}
 
# each dot sits left of and a little above its button's tap point
ninjutsu = ToggleDetector(
    NINJUTSU_POINTS["ninjutsu_button"], tap="ninjutsu_button", group="ninjutsu_toggle",
    label="Ninjutsu", dot=(-118, -3),
)
secret = ToggleDetector(
    SECRET_POINTS["secret_button"], tap="secret_button", group="secret_toggle",
    label="Secret", dot=(-114, -6),
)
 
def add_option(flow, default="keep"):
    flow.arg("--ninjutsu", choices=["keep", "on", "off"], default=default,
             help="ninjutsu button at the start of each fight: keep leaves it alone")
 
def _apply(ctx, detector, want):
    if want not in ("on", "off"):
        return True
    if detector.set(ctx.engine, want == "on"):
        ctx.log(f"{detector.label} confirmed {want.upper()}")
        return True
    return False
 
def apply(ctx, want=None):
    return _apply(ctx, ninjutsu, want or getattr(ctx.args, "ninjutsu", "keep"))
 
def apply_secret(ctx, want):
    return _apply(ctx, secret, want)
 