# console look and feel: colors, log styling, menus and prompts
# standard library only so it works before anything else is installed
import os
import re
import sys
import time

_CODES = {"bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33",
          "blue": "34", "cyan": "36", "gray": "90"}

def _out():
    return sys.__stdout__

def enable_ansi():
    if os.name != "nt":
        return
    try:
        import ctypes
        kernel = ctypes.windll.kernel32
        for handle_id in (-11, -12):
            handle = kernel.GetStdHandle(handle_id)
            mode = ctypes.c_uint32()
            if kernel.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        os.system("")

def color_on():
    return _out().isatty() and "NO_COLOR" not in os.environ

def paint(text, *styles):
    if not styles or not color_on():
        return text
    return f"\x1b[{';'.join(_CODES[s] for s in styles)}m{text}\x1b[0m"

def interactive():
    return sys.__stdin__ is not None and sys.__stdin__.isatty() and _out().isatty()

# ---------------------------------------------------------------- log styling

TAG = re.compile(r"^\[([A-Z][A-Z0-9 ]*)\]\s?(.*)$")
# setup chatter that only matters when something is wrong
HIDE = {"TOOLS", "TAP", "DOUBLE TAP", "SWIPE", "INPUT", "GAME", "ADB", "HEADLESS"}
WARN = re.compile(r"fall(ing)? ?back|fail|error|unavailable|timed out|not found|missing|exception|cannot|could not", re.I)
TAG_STYLE = {
    "START": ("bold", "green"), "CLEAR": ("bold", "green"), "DONE": ("bold", "green"),
    "ERROR": ("bold", "red"), "EXIT": ("yellow",), "RECOVERY": ("yellow",),
    "SCREEN": ("gray",), "OCR": ("gray",), "SCRCPY": ("gray",),
    "NAV": ("blue",), "GLOBAL": ("blue",), "UPDATE": ("green",),
}

class LogFilter:
    def __init__(self, stream, verbose=False):
        self.stream, self.verbose, self.buffer = stream, verbose, ""
        self.last_line, self.repeats = None, 0

    def format(self, line):
        match = TAG.match(line)
        if not match:
            return line
        tag, message = match.groups()
        warn = bool(WARN.search(message)) and tag != "ERROR"
        if not self.verbose:
            if tag in HIDE and not warn:
                return None
            if tag == "SCREEN":
                message = message.split(": ", 1)[0]
        stamp = paint(time.strftime("%H:%M:%S"), "gray")
        label = paint(f"[{tag}]".ljust(13), *TAG_STYLE.get(tag, ("cyan",)))
        return f"{stamp} {label} {paint(message, 'yellow') if warn else message}"

    def write(self, text):
        if "\n" not in text and not self.buffer and not text.startswith("["):
            self.stream.write(text)          # prompts and partial lines pass straight through
            return len(text)
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            line = line.rstrip("\r")
            styled = self.format(line)
            if styled is None:
                continue                      # hidden lines do not break up a run of repeats
            if styled != line and line == self.last_line and not self.verbose:
                self.repeats += 1             # same tagged line again: count it instead of printing it
                continue
            self.end_repeats()
            self.last_line = line if styled != line else None
            self.stream.write(styled + "\n")
        return len(text)

    def end_repeats(self):
        if self.repeats:
            more = "once more" if self.repeats == 1 else f"{self.repeats} more times"
            self.stream.write(" " * 23 + paint(f"(repeated {more})", "gray") + "\n")
        self.repeats = 0

    def flush(self):
        self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)

def install(verbose=False):
    enable_ansi()
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    if isinstance(sys.stdout, LogFilter):
        sys.stdout.verbose = verbose
    else:
        sys.stdout = LogFilter(sys.stdout, verbose)

def set_verbose(verbose):
    if isinstance(sys.stdout, LogFilter):
        sys.stdout.verbose = verbose

# ---------------------------------------------------------------- keys

def read_key(timeout=None):
    if os.name == "nt":
        import msvcrt
        if timeout is not None:
            end = time.monotonic() + timeout
            while not msvcrt.kbhit():
                if time.monotonic() >= end:
                    return None
                time.sleep(0.03)
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            return {"H": "up", "P": "down"}.get(msvcrt.getwch(), "")
        if ch == "\x03":
            raise KeyboardInterrupt
        return {"\r": "enter", "\n": "enter", "\x1b": "esc"}.get(ch, ch)
    import select
    import termios
    import tty
    fd = sys.__stdin__.fileno()
    saved = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        if timeout is not None and not select.select([fd], [], [], timeout)[0]:
            return None
        ch = os.read(fd, 1).decode(errors="ignore")     # raw reads: buffered stdin would swallow the rest of an arrow key
        if ch == "\x1b":
            if select.select([fd], [], [], 0.05)[0]:
                rest = os.read(fd, 2).decode(errors="ignore")
                return {"[A": "up", "[B": "down"}.get(rest, "")
            return "esc"
        if ch == "\x03":
            raise KeyboardInterrupt
        return {"\r": "enter", "\n": "enter"}.get(ch, ch)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)

# ---------------------------------------------------------------- menus and prompts

def clear():
    if interactive():
        _out().write("\x1b[2J\x1b[H")
        _out().flush()

def header(title, subtitle=""):
    out = _out()
    out.write("\n  " + paint(title, "bold", "cyan") + "\n")
    out.write("  " + paint("-" * max(len(title), 24), "gray") + "\n")
    if subtitle:
        out.write("  " + paint(subtitle, "gray") + "\n")
    out.flush()

def say(message, *styles):
    _out().write("  " + paint(message, *styles) + "\n")
    _out().flush()

def choose(title, options, default=0, subtitle="", hint="up/down to move   enter to pick   q to go back", refresh=None):
    out = _out()
    default = min(max(default, 0), len(options) - 1)
    if not interactive():
        return _choose_plain(title, options, default)

    index, drawn, dirty = default, 0, True
    out.write("\x1b[?25l")                                   # hide cursor
    try:
        while True:
            if dirty:
                lines = ["", "  " + paint(title, "bold", "cyan"), "  " + paint("-" * max(len(title), 24), "gray")]
                if subtitle:
                    lines.append("  " + paint(subtitle, "gray"))
                lines.append("")
                for i, label in enumerate(options):
                    number = f"{i + 1}." if i < 9 else "  "
                    if i == index:
                        lines.append("  " + paint(f"> {number} {label}", "bold", "cyan"))
                    else:
                        lines.append(f"    {number} {label}")
                lines += ["", "  " + paint(hint, "gray")]
                if drawn:
                    out.write(f"\x1b[{drawn}A\x1b[J")
                out.write("\n".join(lines) + "\n")
                out.flush()
                drawn, dirty = len(lines), False

            key = read_key(timeout=0.3 if refresh else None)
            if key is None:
                fresh = refresh()
                if fresh != options:
                    options, dirty = fresh, True
            elif key in ("up", "k"):
                index, dirty = (index - 1) % len(options), True
            elif key in ("down", "j"):
                index, dirty = (index + 1) % len(options), True
            elif key in ("enter", " "):
                return index
            elif key in ("esc", "q", "Q"):
                return None
            elif key.isdigit() and 1 <= int(key) <= min(9, len(options)):
                return int(key) - 1
    finally:
        out.write("\x1b[?25h")
        out.flush()

def _choose_plain(title, options, default):
    out = _out()
    out.write(f"\n{title}\n")
    for i, label in enumerate(options):
        out.write(f"  {i + 1}. {label}\n")
    while True:
        out.write(f"Choose [1-{len(options)}, Enter = {default + 1}, q = back]: ")
        out.flush()
        answer = (sys.__stdin__.readline() or "q").strip().lower()
        if not answer:
            return default
        if answer == "q":
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return int(answer) - 1

def ask(prompt, default="", validate=None):
    out = _out()
    while True:
        shown = f" [{default}]" if default else ""
        out.write("  " + paint(prompt, "bold") + paint(shown, "gray") + ": ")
        out.flush()
        line = sys.__stdin__.readline()
        if line == "":
            raise KeyboardInterrupt
        text = line.strip() or default
        problem = validate(text) if validate else None
        if not problem:
            return text
        say(problem, "red")

def pause(message="Press Enter to go back"):
    _out().write("\n  " + paint(message, "gray") + " ")
    _out().flush()
    sys.__stdin__.readline()

def confirm(question, yes="Yes", no="No", detail=""):
    return choose(question, [no, yes], default=0, subtitle=detail) == 1
