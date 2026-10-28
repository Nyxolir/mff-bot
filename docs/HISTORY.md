# Archived upstream and development notes

These historical notes are retained for provenance. Some describe older behavior; use the root README and current FARMING_RULES.md for current operation.

# Local farming port

**Windows app:** double-click **MFF Auto.exe**. The original-style GUI includes editable queues, a live BlueStacks preview, screen checks and logs. Battle controls are shelved. Keep the launcher in this folder; it uses this PC's existing Python environment.

**Check Resources** reuses verified daily GBR clearance until reset, including after app restarts. Without clearance it navigates to GBR and reads both counters. File → Recheck GBR now forces a new inspection. Mission spending always needs fresh resource balances.

**Start Queue / Stop Queue** now control a continuous energy-farming queue. GBR clearance is cached until 15:00 UTC (17:00 in Albanian summer, 16:00 in winter), then checked again. A mission must have enough boost points, energy and clear tickets for every remaining entry; partial or unboosted batches are blocked. Completed missions stay complete until reset.

Incomplete GBR rewards pause boosted farms and Dispatch 7-1. Timeline (Team 1), Otherworld, Normal Alliance Battle and Story remain eligible. The queue rechecks incomplete GBR every minute between tasks, while verified clearance is reused until reset. Built-in battles finish before the next resource check.

Add **STORY ULTIMATE** to a queue to launch the game's **Auto Progress**, with **Start from Stage 1-1** checked. It uses energy without a GBR or boost-point requirement, advances through the themes using the saved game teams, and is launched once per reset. The game usually takes about an hour; the bot monitors it and does not restart a submitted run. Stop Queue stops new bot inputs; an already submitted in-game Auto Progress run continues until stopped in the game.

**Check Objectives** inspects Daily Challenges and discovers the current Special Benefits event titles. It skips Otherworld Battle Pass and Future Pass. Outstanding requirements choose one Dimension clear, or five plus a contribution claim; no requirement means no Dimension clears. Dispatch requests using energy target 7-1 with the same GBR and boost guards. Alliance Battle is limited to Normal with built-in auto.

**Validation:** live inspection of the current event completed, and one Dimension ticket clear and one Normal Alliance Battle were verified. The five-clear contribution branch is tested offline; Dispatch preparation was inspected without starting a run. The common Epic Quest immediate-sweep popup is supported: inspect preparation, verify the full batch, submit once, and verify the exact result count. Beginning of the Chaos was cleared live (two entries, eight energy, eight boost, two tickets). Unknown layouts remain blocked.

See [PORTING.md](PORTING.md) for setup and validation details. The legacy GUI must not be used for unattended farming.

The documentation below describes the archived upstream release, including its historical game compatibility.

# mff_auto (archived upstream)
Game bot for [Marvel Future Fight](https://play.google.com/store/apps/details?id=com.netmarble.mherosgb&hl=ru) game.
Compatible with **7.5.1** version.

## FAQ
**Q**: What this bot can do?

**A**: **mff_auto** can play almost all game modes: 
  World Bosses, Alliance Battle, Co-op missions, Dimension missions, Timeline battles, Legendary battles, 
  World Boss Invasions, Epic Quests, Danger Room, Giant Boss Raid, Shadowland.

Also it can enable *Autoplay++* feature anywhere and do your daily routines.

**Q**: Which Android emulators are supported?

**A**: [NoxPlayer](https://bignox.com) (up to 7.0.1.0) and [BlueStacks](https://www.bluestacks.com).

**Q**: Why are you suggesting to use **NoxPlayer**?

**A**: NoxPlayer has shortcut to force close applications (requires to reset game's state).
 **Shifter's biometric farming is available only using NoxPlayer!**

## Video example

Video footage of all game modes running by **mff_auto**: https://youtu.be/QcgZcAwBL-I

## Installation

- Install [NoxPlayer](https://bignox.com) (or [BlueStacks](https://www.bluestacks.com))
 and then install and run [Marvel Future Fight](https://play.google.com/store/apps/details?id=com.netmarble.mherosgb).

- Set [NoxPlayer](https://bignox.com)
 (or [BlueStacks](https://www.bluestacks.com))
 screen resolution at least **1280x720**. If you encounter problems then try **1920x1080**.
 
- Set in [Marvel Future Fight](https://play.google.com/store/apps/details?id=com.netmarble.mherosgb) 
  setting **GRAPHICS** to at least **Medium**. Lesser settings will lead to blurried text.

  In the same setting's menu turn off this notifications: 
  `Mission Navigation Auto Popup` and `Future Pass Point Acquired`.

- Download last release: [Link to releases](https://github.com/tmarenko/mff_auto/releases)

- Run `start.bat`

## Usage

### Setup window

On first start you will see `Setup` window. Follow the instructions in the window:
- You need to select one of opened emulators. Name of the emulator will be stored in `settings/gui/game.json`.

  You can change it manually after or delete `settings/gui/game.json` if you want to run `Setup` again.

- **(Only for NoxPlayer)** Then you will be asked questions. Read instructions and select `Yes` or `No`.

  At the end you will be asked to click at **MFF** app in the window. 
  Position of app icon will be stored in `settings/gui/game.json`.
 
  You need to **restart NoxPlayer** and **mff_auto** to apply changes.

  This will allow **mff_auto** to close and start the game.
  
### Main window

![main_window](gui_preview.png)

- `Game screen` shows you game's image at 6-7 fps.

- `Missions Queue` allows you to add, edit or remove available missions in **mff_auto**.

  `Run` button will run all checked missions from top to bottom.
  
- `Setting` allows you to edit available settings.

- `Quick Start` allows you to quick run a few modes without adding them to mission queue.

- `Autoplay++` enables casting skills in the battles (also skips cutscenes).

- `Debug Log` at bottom shows you messages about current running code.

  You can also check it in `logs\debug.log` file.

## Development

At current state Marvel Future Fight bot is at beta stage.

- Timeline battle do not check if your team is available for battle. Please setup team manually.
- Alliance and World Boss battles do not check if your characters can do these modes. 
  Make sure that you have strong characters.
- Shadowland requires a big roaster of powerful heroes. 
  Make sure that you have at least 60 to 90 T2 characters and uniforms for them.

## Contribution

Feel free to contribute. Don't forget about [license](LICENSE).

### Running from source code

- Install [Python 3.6.5](https://www.python.org/downloads/release/python-365)
- Install [Tesseract OCR 3.05.02](https://digi.bib.uni-mannheim.de/tesseract) 
  and add path to Tesseract to your `PATH` environment.
- Download source code and install all requirements: ```pip install -r requirements.txt```
- Copy `tessdata` folder to your Tesseract folder.
- Add `lib` folder to your `PYTHONPATH` or mark it as lib source.

Check `example.py` for examples of running any modes.

### Capture video for debugging

```python
from lib.emulators.nox_player import NoxPlayer
from lib.game.game import Game
from lib.video_capture import EmulatorCapture

nox = NoxPlayer("NoxPlayer")
game = Game(nox)
with EmulatorCapture(nox) as recorder:
    # video file is in `logs` folder
    # ... do your stuff here ...
    recorder.pause()
       # pause recording
    recorder.resume()
```

### Building release package from source code

- Run `build.py`


## Background control without the mouse

File → Background control (ADB, no mouse) is enabled by default. It sends taps, Back and swipes directly to the local Android emulator and captures Android screenshots, without moving the Windows cursor or activating BlueStacks. It never falls back to foreground mouse input. Existing farming guards, full-batch checks and Stop Queue remain in place. Landscape 16:9 displays, including 3840×2160, are normalized to the reader's 1280×720 working image; taps and swipes scale back to the captured Android resolution. Reconnect if the resolution changes during a session.

One manual setup step is required: BlueStacks Settings → Advanced → enable Android Debug Bridge. Then click Connect BlueStacks and Start Queue in MFF Auto. The installed BlueStacks HD-Adb executable is used, with the native local emulator transport when available or the explicit local address 127.0.0.1 and configured instance port; remote ADB access is not enabled or required. File → Background control can be unchecked explicitly to return to the old foreground mouse mode. Incomplete screenshots are retried up to three times; capture reconnection never retries a potentially submitted spending input.

## Saved objective checks and passive Dispatch rewards

The continuous queue saves the Daily Challenges and active-event Dimension/Dispatch requirements in `settings/gui/objective-checks.json`. It reuses them across queue cycles and app restarts until 15:00 UTC reset. Verified clears update the saved plan; an interrupted submission requires a fresh inspection. File → Recheck Dimension/Dispatch requirements forces an inspection before reset.

Verified completed quests are saved separately in `settings/gui/completed-missions.json` until reset. The queue remembers all completed tiles on each observed board page, skips them without opening them again, and restores these completions after restarting the app. When exactly one Epic rewarded entry remains, the verified Use x1 button is the full batch; a disabled Use up to 10 button is never used as its quantity.

After four failed reads/navigation attempts, or 90 seconds of repeated failure, the queue holds that mission until reset, backs out to Home, and continues with other unfinished quests. A held quest is not marked completed. If a spending input may already have been sent, the hold is saved before dropping its pending state so that mission cannot be retried after a restart. Fresh verified zero-entry preparation or board evidence can resolve a pending clear even after its result screen has been closed. Ordinary boost/energy/ticket waits are excluded from stuck recovery. Recovery stops after eight unsuccessful Back/Home steps instead of sending inputs indefinitely.

While running, the queue checks passive Dispatch supplies every 15 minutes. A pink notification dot on a verified Acquire reward button authorizes Claim All Rewards. It does not open sector timers. Header notifications and supply bars alone do not authorize collection. The claim is submitted once and verified from the reward result/map; an uncertain outcome is never retried. Stop Queue stops this check.

## Current Daily Trivia addition

The modern GUI has a Daily Trivia button. It opens Challenges → Daily Trivia, checks the local answer bank against the supplied Quizlet set, and scans the current list. Already-answered entries are skipped. Matching rejects unknown questions, ambiguous answers and missing/duplicate options; there is no random fallback. New unanswered-dialog controls still require live validation, so this release reports known answers and stops rather than submitting to an unverified layout. Today's five entries were already answered. Source: https://quizlet.com/hk/699399827/future-fight-daily-trivia-flash-cards/. The source is an older community list; four newer answers were read directly from the game's completed list.


World Event is monitored independently while the queue runs, including boost-point waits and after daily energy farming finishes. It uses built-in Auto Play+, skips an already-scored slot, and checks future availability until the lobby shows 0/2 daily entries. Closed/unrecognized availability is revisited after five minutes; completed-slot timers defer the next inspection until that slot ends. The 0/2 completion and pending-entry latch survive app restarts and reset at 15:00 UTC. Manual skill controls remain shelved.
