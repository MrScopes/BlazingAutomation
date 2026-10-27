# the whole user interface: Run.bat starts this and nothing else
# stays light on purpose (no cv2 or OCR imports) so setup can replace packages while the menu is open
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

SRC = Path(__file__).resolve().parent
APP = SRC.parent
sys.path.insert(0, str(SRC))

from api import ui, devices 
from config import VERSION  

STATE_FILE = APP / ".launcher.json"
SETUP = APP / "scripts" / "setup.ps1"
POWERSHELL = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SETUP)]
DEV_TOOLS = [("Live coordinate picker", "coordinates.py"), ("Live raw OCR stream", "ocr.py"), ("Button test", "toggles.py")]

def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_state(state):
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError:
        pass                     

def pretty(name):
    return name.replace("_", " ").title()

def macro_names():
    return sorted(
        folder.name for folder in (SRC / "macros").iterdir()
        if folder.is_dir() and not folder.name.startswith("_") and (folder / "main.py").is_file()
    )

def setup_problems():
    needed = {
        "scrcpy": APP / "tools" / "scrcpy" / "scrcpy.exe",
        "scrcpy server": APP / "tools" / "scrcpy" / "scrcpy-server",
        "adb": APP / "tools" / "scrcpy" / "adb.exe",
        "ffmpeg": APP / "tools" / "ffmpeg" / "ffmpeg.exe",
    }
    return [name for name, path in needed.items() if not path.exists()]

def run(command, env=None):
    try:
        process = subprocess.Popen(command, env=env)
    except OSError as exc:
        ui.say(f"Could not start {command[0]}: {exc}", "red")
        return 127
    while True:
        try:
            return process.wait()
        except KeyboardInterrupt:
            pass

def python(*args, env=None):
    return run([sys.executable, "-u", *map(str, args)], env)

def describe(name):
    result = subprocess.run([sys.executable, "-u", str(SRC / "main.py"), "--macro", name, "--describe"],
                            capture_output=True, text=True, timeout=120)
    for line in result.stdout.splitlines():
        if line.startswith("@@DESCRIBE@@"):
            return json.loads(line[len("@@DESCRIBE@@"):]), ""
    return None, (result.stdout + result.stderr).strip().splitlines()[-1:] or ["no details"]

def positive_int(text):
    if text and (not text.isdigit() or int(text) <= 0):
        return "Enter a whole number above 0, or leave it blank"
    return None

class UpdateCheck:
    def __init__(self):
        self.version, self.done = "", False
        threading.Thread(target=self.check, daemon=True).start()

    def check(self):
        self.version = latest_version()[0]
        self.done = True

def latest_version():
    try:
        result = subprocess.run([sys.executable, "-u", str(SRC / "updater.py"), "--check"],
                                capture_output=True, text=True, timeout=20)
    except Exception:
        return "", False
    lines = result.stdout.strip().splitlines()
    return (lines[-1].strip() if lines else ""), result.returncode == 0

def release_notes():
    try:
        result = subprocess.run([sys.executable, "-u", str(SRC / "updater.py"), "--notes"],
                                capture_output=True, text=True, timeout=25)
    except Exception:
        return []
    lines = result.stdout.rstrip().splitlines()
    return lines[:60] + (["    ..."] if len(lines) > 60 else [])

def check_updates():
    ui.clear()
    ui.say("Checking for updates...", "gray")
    version, reached = latest_version()
    ui.clear()
    if not version:
        ui.header("Check For Updates")
        if reached:
            ui.say(f"You are up to date (v{VERSION}).", "green")
        else:
            ui.say("Could not reach GitHub. Check your internet connection and try again.", "red")
        ui.pause()
        return False
    notes = release_notes()
    if notes:
        ui.header(f"Version {version} is available", f"You have v{VERSION}. What's new:")
        for line in notes:
            ui.say(line, "gray")
        print()
    if not ui.confirm(f"Install v{version}?", yes=f"Install v{version}", no="Not now",
                      detail="" if notes else f"You have v{VERSION}"):
        return False
    ui.clear()
    code = python(SRC / "updater.py", "--yes")
    if code == 10:
        ui.say("Update installed. Close this window and open Run.bat again to use the new version.", "green")
        ui.pause("Press Enter to close")
        return True
    if code != 0:
        ui.say(f"Update failed (exit code {code}).", "red")
    ui.pause()
    return False

def pick_options(name, info, remembered):
    args, chosen = [], {}
    for option in info["arguments"]:
        flag = option["flags"][-1]
        label = flag.lstrip("-").replace("-", " ").capitalize()
        default = remembered.get(flag, option.get("default"))
        if option.get("action") == "store_true":
            pick = ui.choose(f"{pretty(name)}: {label}", ["No", "Yes"], default=1 if default else 0, subtitle=option.get("help") or "")
            if pick is None:
                return None
            if pick:
                args.append(flag)
            chosen[flag] = bool(pick)
        elif option.get("choices"):
            choices = [str(c) for c in option["choices"]]
            pick = ui.choose(f"{pretty(name)}: {label}", [c.title() for c in choices],
                             default=choices.index(str(default)) if str(default) in choices else 0,
                             subtitle=option.get("help") or "")
            if pick is None:
                return None
            args += [flag, choices[pick]]
            chosen[flag] = choices[pick]
        else:
            value = ui.ask(label, str(default or ""))
            if value:
                args += [flag, value]
            chosen[flag] = value

    if info["counts"]:     
        ui.clear()
        ui.header(f"{pretty(name)}: repeat count")
        times = ui.ask("Repeat count (blank = until you stop it)", "", positive_int)
        if times:
            args += ["--times", times]
    return args, chosen

def start_macro(name, state):
    env = prepare_device(state)
    if env is None:
        return
    ui.clear()
    ui.say("Loading...", "gray")
    try:
        info, problem = describe(name)
    except subprocess.TimeoutExpired:
        info, problem = None, ["took too long to load"]
    if info is None:
        ui.say(f"Could not load {pretty(name)}: {problem[-1]}", "red")
        ui.say("If this keeps happening, choose Reinstall from the main menu.", "gray")
        ui.pause()
        return

    options = state.setdefault("options", {})
    picked = pick_options(name, info, options.get(name, {}))
    if picked is None:
        return
    args, options[name] = picked
    state["last_macro"] = name
    save_state(state)

    command = ["--macro", name, "--background", "--skip-update", *args]
    if state.get("verbose"):
        command.append("--verbose")

    ui.clear()
    ui.header(f"Running {pretty(name)}", "Press Ctrl+C to stop")
    print()
    code = python(SRC / "main.py", *command, env=env)
    print()
    if code == 0:
        ui.say(f"{pretty(name)} finished.", "green")
    else:
        ui.say(f"{pretty(name)} stopped with an error (exit code {code}).", "red")
        ui.say("If it says a package is missing, choose Reinstall from the main menu.", "gray")
    ui.pause("Press Enter to go back to the menu")

def run_macros(state):
    names = macro_names()
    if not names:
        ui.say("No macros found in src/macros.", "red")
        ui.pause()
        return
    last = names.index(state["last_macro"]) if state.get("last_macro") in names else 0
    pick = ui.choose("Run Macros", [pretty(n) for n in names], default=last, subtitle="Pick a macro")
    if pick is not None:
        start_macro(names[pick], state)

def dev_ready():
    probe = "import tkinter; from PIL import Image, ImageTk"
    return subprocess.run([sys.executable, "-c", probe], capture_output=True).returncode == 0

def developer(state):
    if not dev_ready():
        if not ui.confirm("Developer tools need one more download", yes="Download now", no="Back",
                          detail="Installs Pillow (small). Needs an internet connection."):
            return
        ui.clear()
        if run(POWERSHELL + ["-Dev"]) != 0 or not dev_ready():
            ui.say("Developer setup did not finish.", "red")
            ui.pause()
            return
    while True:
        pick = ui.choose("Developer", [label for label, _ in DEV_TOOLS], subtitle="Tools for coordinates, OCR text and button tests")
        if pick is None:
            return
        env = prepare_device(state)
        if env is None:
            continue
        ui.clear()
        # the dev tools import "src.api...", so the folder above src must be on the path
        code = python(SRC / "dev" / DEV_TOOLS[pick][1], env={**env, "PYTHONPATH": str(APP)})
        if code:
            ui.say(f"Tool exited with code {code}.", "red")
            ui.pause()

def reinstall():
    if not ui.confirm("Reinstall Blazing Automation?", yes="Reinstall", no="Cancel",
                      detail="Re-downloads tools and packages (about 200 MB). Your settings are kept."):
        return
    ui.clear()
    code = run(POWERSHELL + ["-Force"])
    print()
    if code == 0:
        ui.say("Reinstall finished.", "green")
    else:
        ui.say(f"Reinstall failed (exit code {code}).", "red")
    ui.pause()

DEFAULT_DEVICE = "127.0.0.1:5555"          # same default as api/config.py

def valid_device(text):
    host, _, port = text.rpartition(":")
    if text and (not host or not port.isdigit() or not 0 < int(port) < 65536 or " " in text):
        return "Use the form address:port, for example 127.0.0.1:5555"
    return None

def device_label(state):
    mode = state.get("device_mode") or "emulator"
    return "Android Phone" if mode == "phone" else "Emulator"

def ask_device(state):
    stop = True                  # the "Stop asking" box starts ticked
    default = 1 if state.get("device_mode") == "phone" else 0
    while True:
        ui.clear()
        pick = ui.choose("Where is the game running?",
                         ["Emulator", "Android Phone", f"[{'x' if stop else ''}] Stop asking? You can change this later."],
                         default=default, subtitle="Pick one to start, or tick the box first to remember the choice")
        if pick is None:
            return False
        if pick == 2:
            stop, default = not stop, 2
            continue
        break
    state["device_mode"] = "phone" if pick == 1 else "emulator"
    if stop:
        state["ask_device"] = False
    if pick == 0 and "device" not in state:         # first time with an emulator: which address
        set_emulator_address(state)
    save_state(state)
    return True

def set_emulator_address(state):
    ui.clear()
    ui.header("Emulator address", "Usually 127.0.0.1:5555")
    value = ui.ask("ADB address", state.get("device") or DEFAULT_DEVICE, valid_device)
    state["device"] = "" if value == DEFAULT_DEVICE else value
    save_state(state)

def find_phone(state):
    """(name, ip:port) of the phone to use, asking when several are around. None when there is none."""
    found = devices.phones()
    if not found:
        return None
    saved = [item for item in found if devices.serial_of(item[0]) == state.get("phone")]
    if saved:
        return saved[0]
    if len(found) == 1:
        return found[0]
    pick = ui.choose("Which phone?", [f"{devices.serial_of(name)}  {address}" for name, address in found])
    return None if pick is None else found[pick]

def prepare_device(state):
    if not state.get("device_mode") and state.get("device") is not None:
        state["device_mode"] = "emulator"           # an address saved before phones were supported
    if state.get("ask_device", True) or not state.get("device_mode"):
        if not ask_device(state):
            return None
    if state["device_mode"] != "phone":
        return dict(os.environ)
    ui.clear()
    ui.say("Looking for your phone...", "gray")
    found = find_phone(state)
    if not found:
        ui.say("No Android phone found.", "red")
        ui.say("Turn on Wireless debugging on the phone, on the same Wi-Fi as this PC.", "gray")
        ui.say("Not paired yet? Settings > Pair a new phone.   Using an emulator? Pick Emulator when asked.", "gray")
        ui.pause()
        return None
    state["phone"] = devices.serial_of(found[0])
    save_state(state)
    ui.say(f"Phone found at {found[1]}", "green")
    return {**os.environ, "BLAZING_DEVICE": found[1]}

def pair_phone():
    ui.clear()
    ui.header("Pair a new phone", "Only needed once per phone")
    ui.say("On the phone: Settings > Developer options > Wireless debugging > Pair device with pairing code.", "gray")
    ui.say("Leave that pairing screen open.", "gray")
    ui.say("")
    ui.say("Looking for the pairing screen...", "gray")
    found = devices.wait_for("pairing", 25)
    if found:
        address = found[0][1]
        ui.say(f"Found it at {address}", "green")
    else:
        ui.say("Could not find it automatically.", "yellow")
        address = ui.ask("Pairing address shown on the phone (ip:port, blank to cancel)", "", valid_device)
        if not address:
            return
    code = ui.ask("Pairing code (6 digits, blank to cancel)", "")
    if not code:
        return
    ok, message = devices.pair(address, code)
    ui.say(message or ("Paired." if ok else "Pairing failed."), "green" if ok else "red")
    if ok:
        ui.say("Done. Pick Android Phone the next time you start something.", "gray")
    ui.pause()

def settings(state):
    while True:
        ui.clear()
        asking = state.get("ask_device", True)
        pick = ui.choose("Settings", [f"Verbose log: {'on' if state.get('verbose') else 'off'}",
                                      f"Ask which device to use: {'yes' if asking else 'no'}",
                                      f"Device when not asking: {device_label(state)}",
                                      f"Emulator address: {state.get('device') or DEFAULT_DEVICE}",
                                      "Pair a new phone", "Back"],
                         subtitle="Verbose shows OCR text and tap coordinates")
        if pick == 0:
            state["verbose"] = not state.get("verbose")
            ui.set_verbose(state["verbose"])
        elif pick == 1:
            state["ask_device"] = not asking
        elif pick == 2:
            state["device_mode"] = "emulator" if state.get("device_mode") == "phone" else "phone"
        elif pick == 3:
            set_emulator_address(state)
        elif pick == 4:
            pair_phone()
        else:
            return
        save_state(state)

def main():
    ui.enable_ansi()
    state = load_state()
    ui.install(state.get("verbose", False))
    update = UpdateCheck()
    last = 0

    def labels():
        if update.done and update.version:
            check = f"Check For Updates  (v{update.version} available)"
        else:
            check = "Check For Updates"
        return ["Run Macros", "Developer", check, "Reinstall", "Settings", "Quit"]

    while True:
        ui.clear()
        problems = setup_problems()
        subtitle = ("Setup incomplete (" + ", ".join(problems) + "). Choose Reinstall to fix it."
                    if problems else "")
        pick = ui.choose(f"BLAZING AUTOMATION  v{VERSION}", labels(), default=3 if problems and not last else last,
                         subtitle=subtitle, hint="up/down to move   enter to pick   q to quit", refresh=labels)
        if pick is None or pick == 5:
            return 0
        last = pick
        if pick == 0:
            run_macros(state)
        elif pick == 1:
            developer(state)
        elif pick == 2:
            if check_updates():
                return 0
        elif pick == 3:
            reinstall()
        elif pick == 4:
            settings(state)

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
