import argparse
import importlib
import json
import os
import sys
import traceback
from pathlib import Path

from api import ui

MACROS = sorted(
    folder.name
    for folder in (Path(__file__).resolve().parent / "macros").iterdir()
    if folder.is_dir()
    and not folder.name.startswith("_")
    and (folder / "main.py").is_file()
)

def main():
    from api.cutoff import exit_if_expired
    exit_if_expired()
    # Find the macro first: each macro declares its own extra options (e.g. story's --difficulty).
    early = argparse.ArgumentParser(add_help=False)
    early.add_argument("--macro", choices=MACROS)
    early.add_argument("--verbose", action="store_true")
    known, _ = early.parse_known_args()

    # style the output before anything else prints
    verbose = known.verbose or os.environ.get("BLAZING_VERBOSE") == "1"
    ui.install(verbose)
    from api.macro import Macro

    parser = argparse.ArgumentParser(description="Blazing Online Macro Runner")
    parser.add_argument("--macro", choices=MACROS, required=True)
    parser.add_argument("--capture", choices=["raw", "png", "scrcpy", "headless"], default="headless")
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--skip-update", action="store_true")
    parser.add_argument("--times", type=int, help="stop after this many runs")
    parser.add_argument("--verbose", action="store_true", help="show OCR text, tap coordinates and setup details")
    parser.add_argument("--describe", action="store_true", help=argparse.SUPPRESS)

    module = importlib.import_module(f"macros.{known.macro}.main") if known.macro else None
    flow = getattr(module, "flow", None)
    if flow:
        flow.add_args(parser)

    args = parser.parse_args()
    if args.describe:
        # the launcher reads this line to build its option menus
        arguments = [{"flags": flags, **{k: v for k, v in kwargs.items() if k in ("choices", "default", "action", "help")}}
                     for flags, kwargs in (flow.arguments if flow else [])]
        print("@@DESCRIBE@@" + json.dumps({"arguments": arguments, "counts": bool(flow and flow.counter)}, default=str), flush=True)
        return
    if args.times is not None and args.times <= 0:
        parser.error("--times must be a positive integer")

    options = {k: v for k, v in vars(args).items()
               if k not in ("macro", "capture", "background", "skip_update", "times", "verbose", "describe")}
    macro = Macro(capture="headless" if args.background else args.capture)

    try:
        if flow:
            flow.run(macro, times=args.times, **options)
        else:
            module.run(macro, times=args.times, **options)
    except (RuntimeError, TimeoutError, ImportError) as exc:
        # expected failures (stalls, timeouts, missing device or package) get one clean line instead of a traceback
        print(f"[ERROR] {exc}", flush=True)
        if args.verbose:
            traceback.print_exc()
        sys.exit(1)
    finally:
        macro.close()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[EXIT] Stopped by user", flush=True)
