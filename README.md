# NO LONGER WORKING AS OF Sunday, November 8, 2026 5:00 AM EST
> Macros & automation tools are now against the rules.
Some people have taken it to themselves to ruin the fun for others by making the whole game automated, with OCR etc etc, this is unfair for the people that cannot run these programs and miss out, I allowed simple macros to farm stages, but this is too far.

To follow their rules, and protect user accounts, this program automatically checks the time and will not run if it's past the cutoff.

# Blazing Automation
Macros for Naruto Blazing Rebirth (Blazing:ONLINE) that run on an Android emulator or phone over ADB. They read the screen with OCR and tap for you.

Macros included: **Infinite**, **Ninja Road**, **Phantom Castle** and **Story**.
All macros are designed to automatically navigate to where they need to be if they're on the home screen
or, at the game's main screen / intro, etc. It will also acknowledge data updates and navigate back for you.
Current behavior:
- Infinite: auto retry on defeat
- Ninja road: quit and retry on wave 13 (~1 million currency per 8 hours tested with meta team). Ninja Road macro will stop working 11/1
- Phantom Castle: automatically play the weakest opponent, and keep playing. acknowledges pearls for stamina, etc. (assuming auto pearl is on)
- Story: normal/hard choice. will play and go to the next chapter for you for the completion reward (15 pearls). will not/can't do missions for the 3 pearls

Macros can be started on any screen but they will fail for example if you start infinite macro and you're in ninja road, or if you try to have it
navigate on the home screen, but it's not started where "Story&Gaiden" is the mode in the middle. Updates will be pushed to make these less fragile.
Macros can be started mid mission as well though, for example you're playing Ninja Road, and enable the macro; now it will play it for you and keep going.
**Currently, all macros default to auto on and auto jutsu on.**

## Heads up

- **Windows only.**
- This is a hobby project. Use it at your own risk.

## Install

1. Download the latest `blazingautomation-x.x.x.zip` from the Releases page.
2. Unzip it somewhere you want to keep it.
3. Double click **Run.bat**.

The first run sets everything up for you (Python, OCR, scrcpy, ADB and FFmpeg). It's about a 200 MB download and needs around 1 GB free. After that, Run.bat opens the menu right away.

# BlueStacks
You must enable ADB. **BlueStacks Settings -> Advanced -> Android Debug Bridge**\
*tested on Pie 64 bit*

# Mumu
You must enable ADB if it's not already enabled. **Device Settings -> Developer Options -> ADB Debug: Enable local connection**

# Android Phone
you must enable debugging in developer options in the phone, then you can select android phone as an option to run the macros on

## Uninstall
You can simply delete the folder. Nothing is permanently installed, and everything is local to the folder.

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

## Development
Feel free to make PRs. The easiest way to test your local changes is to clone the repo, and you can run the included:
```
PS ...> ./bundle
[BUILD] Installer prepared: ... (version ...)
[ZIP] Created ...\blazingautomation-...zip                            

Press Enter to launch Run.bat (or Q to quit): 

  BLAZING AUTOMATION  v...
  --------------------------

  > 1. Run Macros
    2. Developer
    3. Check For Updates
    4. Reinstall
    5. Settings
    6. Quit

  up/down to move   enter to pick   q to quit
```
The bundler does all the work for you of making the folder for you, your local 'dist' folder. 
It will install deps here just like the end user, so it'll take a minute for the first run.

## AI Disclosure
I wrote this with AI assistance. I design and test everything myself, but some of the code was AI generated.
Feel free to include AI generated code in Pull Requests, just make sure everything is tested and well-thought/designed.