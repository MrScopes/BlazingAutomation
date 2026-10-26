# Blazing Automation
Macros for Naruto Blazing Rebirth (Blazing:ONLINE) that run on an Android emulator or phone over ADB. They read the screen with OCR and tap for you.

Macros included: **Infinite**, **Ninja Road**, **Phantom Castle** and **Story**.

## Heads up

- **Windows only.**
- **Only MuMu is tested.** BlueStacks needs more work to support, so it may not work yet.
- This is a hobby project. Use it at your own risk.

## Install

1. Download the latest `blazingautomation-x.x.x.zip` from the Releases page.
2. Unzip it somewhere you want to keep it.
3. Double click **Run.bat**.

The first run sets everything up for you (Python, OCR, scrcpy, ADB and FFmpeg). It's about a 200 MB download and needs around 1 GB free. After that, Run.bat opens the menu right away.

## Uninstall
You can simply delete the folder. Nothing is permanently installed, and everything is local to the folder.

## Set up your emulator

1. Turn on ADB in your emulator's settings.
2. Set the game to portrait and keep it on screen while a macro runs.
3. Make sure the ADB address in `app/src/api/config.py` (`DEVICE`) matches your emulator.

## Use it

1. Open the game.
2. Double click **Run.bat**.
3. Pick **Run Macros**, then pick a macro.
4. Answer the options it asks for. Leave the repeat count blank to run until you stop it.
5. Press **Ctrl+C** to stop.

Menu in a nutshell:

| Option | What it does |
| --- | --- |
| Run Macros | Pick a macro and start it |
| Developer | Coordinate picker, live OCR stream and a button test |
| Check For Updates | Looks for a newer version and installs it |
| Reinstall | Re-downloads the tools if something is broken |
| Settings | Turn on verbose logs (shows OCR text and tap spots) |

Use the arrow keys and Enter to move around. Press `q` to go back.

## Update

1. Run.bat, then **Check For Updates**.
2. If there's a new version, pick **Install**.
3. Close the window and open Run.bat again.

Your settings are kept.

## Stuck?

- Macro says a package is missing or setup is incomplete: pick **Reinstall**.
- Macro stalls on a screen: turn on **Settings > Verbose log**, run it again and check what the OCR is reading.
- If a macro fails it saves a screenshot next to the app so you can see where it got stuck.

## AI Disclosure
I wrote this with AI assistance. I design and test everything myself, but some of the code was AI generated.
Feel free to include AI generated code in Pull Requests, just make sure everything is tested and well-thought/designed.