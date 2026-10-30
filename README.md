# MFF Bot

**Modern version created and maintained by Nyxolir.**

A Windows automation bot for Marvel Future Fight, built on
[tmarenko/mff_auto](https://github.com/tmarenko/mff_auto). This fork reuses the
previous bot's game data, recognition templates, interface and selected code,
and adds the current queue, screen readers, persistence and recovery behavior.
Upstream and third-party license notices are preserved.

## Run on Windows

The Windows installer is available in this repository's Releases section.
See [SETUP.md](SETUP.md) for installation, BlueStacks ADB, display settings and
queue configuration, plus the alternative instructions for running from source.

The app starts idle. Connect BlueStacks, verify the preview and choose your
queue before starting it. Finish any active game run and stop the queue before
updating. Preserve saved queues, pending outcomes and custom trivia
answers when updating.

## BlueStacks instead of a fixed Nox setup

The modern queue supports BlueStacks through background ADB capture and input.
It does not require the old specific Nox release or one fixed pixel resolution.
Landscape **16:9 resolutions** are normalized to a 1280 x 720 working image, and
taps and swipes are scaled back to the actual Android display. The regression
coverage includes 3840 x 2160 capture normalization. Reconnect after changing
the emulator resolution. Other aspect ratios are not currently supported.

Background mode avoids taking over the mouse. Enable Android Debug Bridge in
BlueStacks, connect the selected instance in the bot, and use the modern queue.

## How the queue chooses work

The bot uses fresh screen evidence and remembered, reset-bound state. Queue
position alone does not authorize a run or prove that content is complete.

1. **Protect anything already submitted.** A pending sweep, battle, quiz answer
   or claim is verified before another submission. Unknown outcomes are not
   replayed. Active battles and Story Auto Progress are protected from unrelated
   navigation.
2. **Try Daily Trivia early after reset.** At a safe boundary, trivia takes
   priority over board checks and GBR/boost waits. Incomplete checks retry after
   two minutes without abandoning active mission preparation. Answers come
   from the local knowledge bank; unknown or ambiguous questions are not
   guessed. A verified completed question-and-answer summary completes trivia
   for the day without scrolling through every row.
3. **Inspect today's work before boosted farming.** Check the Content Status
   Board and refresh Daily Challenges, Event Quest and eligible Special
   Benefits requirements at each queue start. A same-day cached objective plan
   does not replace that refresh. A verified max-level pass can be excluded
   without discarding requirements from other events.
4. **Finish GBR rewards before boosted farming.** Both remaining reward
   counters must be verified at zero. This clearance is remembered until the
   daily reset. The bot checks rewards; it does not automatically fight GBR.
5. **Reserve boost for required Dimension Missions.** After GBR clearance,
   enabled Dimension clears and contribution collection required by current
   objectives take priority over other boosted farms. The remaining count is
   derived from the actual objectives, including requirements above five.
   A boost wait or unresolved Dimension result does not release that priority
   to other boosted content. Story is also deferred while this priority is active.
6. **Continue eligible content.** Other boosted farms follow the enabled queue
   after the required Dimension work. An objective-requested Dispatch clear
   uses sector 7-1 and shares the GBR/boost guards. Content without those guards
   can remain eligible while GBR is incomplete: arenas, Normal Alliance,
   Zombie Survival and Story, plus the explicit Converging Fates exceptions.
   Story is placed after ordinary queue work.

**Boost points are the only resource-amount gate.** The modern queue does not
require an energy balance or ticket-stock amount. It still verifies content
identity, remaining entries, full-batch quantity, the relevant ticket/start
controls, GBR clearance where applicable, and zero-crystal protection.

## Content-specific behavior

- **Converging Fates Normal and Hidden:** separate ticket sweeps for all
  remaining entries, with no boost or GBR gate. The bot can go directly from
  one variant to the other through the chapter links.
- **Zombie Survival:** Survival Level 1, the top five current roster positions,
  ticket entry and MAX repeats. Verified five-clear completion enables Acquire
  All on its Challenges screen. Completion is checked from the board instead
  of assuming a weekly reset date.
- **Alliance Battle:** Normal uses the game's auto mode. The verified weekly
  Relay / Infinite Challenge screen is treated as a manual event and skipped
  for that day.
- **World Event:** a cached board 0/2 is not enough. Daily completion needs
  three fresh zero-entry observations on distinct reopened World Event page
  visits, at least three seconds apart.
- **Passive Dispatch rewards:** checked between missions using the saved
  claim schedule and verified reward controls. An uncertain claim is not
  submitted again.
- **Completed work:** verified completion is remembered until **15:00 UTC**
  daily reset. Cleared entries display at the bottom while preserving queue
  priorities, and the list remains scrollable while running.

## Recovery

Recognized network notices are acknowledged with bounded OK attempts. Fresh
screens decide whether the game retried loading or returned to login; an OK
tap never proves completion. A missing ADB device alone does not prove that
BlueStacks exited. Recovery reconnects first and can relaunch the selected
instance after a verified exit or targeted persistent-ADB-failure recovery.
Pending outcomes survive recovery and are not replayed just because the game
reopened.

## Run from source

See [SETUP.md](SETUP.md) for the complete BlueStacks, ADB, OCR, connection and
queue configuration walkthrough, including troubleshooting and missing trivia
answers.

Use Windows x64, Python 3.12, BlueStacks with Marvel Future Fight, and Tesseract
5 with English language data. Tesseract can be installed on PATH or selected
with the `MFF_TESSERACT_CMD` environment variable.

From the repository folder in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app_gui.py
```

The old desktop launchers refer to a local development environment; use the
source command above for a fresh clone. Runtime settings are created locally.

## Trivia answers are not complete

Some questions, especially ones added by game updates, will be missing from
the answer bank. The bot does not guess: an unknown or ambiguous question
leaves trivia incomplete so it can be checked again. You can answer manually
or add a game-confirmed question/answer to `settings/gui/trivia-answers.json`.
See the [trivia setup notes](SETUP.md#missing-trivia-answers) for the file format.

## Repository contents and tests

Source, test code, recognition templates and verified trivia additions are
included. Credentials, local machine paths, saved queue/account state,
diagnostics, raw screenshot fixtures and compiled binaries are excluded.
Screenshot tests require the private local fixture set and cannot all run from
a fresh clone. The source's full test command is:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

See [AGENTS.md](AGENTS.md) for the current repair and verification rules.
[Archived development notes](docs/HISTORY.md), [PORTING.md](PORTING.md),
[FARMING_RULES.md](FARMING_RULES.md) and reliability reports retain historical
details; older passages can describe superseded behavior. The queue policy
above describes the current implementation.

## Credits and license

- Modern version: **Nyxolir**.
- Original bot and reused data/templates: **tmarenko/mff_auto**.
- Bot source: Apache-2.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE). The complete
  installer also includes GPL-3.0 PyQt5 and LGPL Qt, with their component notices
  and corresponding-source pointers. See [installer licensing](installer/LICENSING.md).

Marvel Future Fight and its game assets belong to their respective owners.
