# Setup and configuration

Modern version maintained by **Nyxolir**, based on the data, recognition
templates and code of **tmarenko/mff_auto**. These instructions apply to the
modern `app_gui.py` entry point, rather than the archived upstream controller.

## Windows installer

1. Open the repository's **Releases** section and select the latest release.
2. Expand **Assets**, download **MFF-Bot-Setup.exe**, and run the installer.
3. Open **MFF Bot** from the Start menu. The application starts idle.
4. Configure BlueStacks using sections 2 and 3 below, then click
   **Connect BlueStacks** in the bot and verify its preview before starting a queue.

The installer bundles Python and English OCR. A separate Python, Node.js or
Tesseract installation is not required for this method. BlueStacks and the game
must be installed separately. The Windows x64 installer installs for the
current user and is currently unsigned.

Finish any active game run and stop the queue before installing an update.
Installed settings, pending outcomes and custom trivia answers are stored
separately under `%LOCALAPPDATA%\Nyxolir\MFFBot`; updates and uninstall preserve
them. The release also includes the corresponding source, validation manifest
and SHA-256 checksums.

The remaining prerequisites and section 4 apply when running from source.
BlueStacks setup and queue configuration apply to both installation methods.

### Automatic app updates

Install the updater-enabled release once using the installer. Installed copies
then check for newer stable releases shortly after startup and every four
hours. No GitHub account or extra updater installation is required. The
**Updates** menu shows the installed version, **Automatic updates** preference
and **Check for updates now**. Automatic updates are enabled by default.

The app downloads in the background and verifies the release manifest and
installer SHA-256 digest. Installation waits for a verified idle screen with
no active content, pending result, saved submission or held outcome. The
**Cancel update** button postpones a pending installation. The app saves its
settings, closes normally, installs without restarting Windows, verifies the
new app offline, and reopens with the same queue selected. A running queue
resumes; a stopped queue stays stopped. New unresolved state prevents resume.
BlueStacks and the game are left running.

Downloads that fail leave the current app running. Failed installations reopen
the app with its queue stopped where possible, and the same failed version is
not attempted automatically again. **Check for updates now** allows an explicit
retry. Logs and the private update receipt remain in the app's data directory.

Source checkouts continue to use Git for code updates; the installer updater
does not switch their state directory or overwrite the working checkout.

## 1. Prerequisites for running from source

- Windows x64 and Python 3.12, including the Python launcher (`py`).
- BlueStacks with Marvel Future Fight installed.
- Tesseract 5 with English language data. Its standard Windows installation
  under `C:/Program Files/Tesseract-OCR/` is detected automatically; a Tesseract
  installation on PATH is also supported.

Use the game's English interface, since the current text readers and control
templates are built around it. Sign in to the game yourself and set up the
teams you intend to use. The repository does not provide game login details,
saved emulator/account state or preconfigured teams.

## 2. Set the BlueStacks display

Open BlueStacks Settings and choose a landscape **16:9** resolution, such as
1280 x 720, 1920 x 1080, 2560 x 1440 or 3840 x 2160. Save and restart the player
if BlueStacks requests it.

The modern bot normalizes the Android screenshot to 1280 x 720 for recognition,
then scales input coordinates back to the original Android display size. It
does not require the old specific Nox release or fixed resolution. The current
capture code requires at least 640 x 360 and a 16:9 aspect ratio; portrait and
ultrawide displays are not supported. Reconnect the bot after changing resolution.

## 3. Enable ADB in BlueStacks

1. Open the BlueStacks App Player's **Settings** using its gear icon.
2. Open **Advanced**.
3. Enable **Android Debug Bridge (ADB)** and save the setting.
4. Keep the intended App Player instance open and launch Marvel Future Fight.
   For the first connection, run only the intended BlueStacks player window
   so the bot can select it unambiguously.

A separate Android platform-tools installation is not required for the default
BlueStacks installation. The bot uses BlueStacks' `HD-Adb.exe` and reads the
selected instance's configured/runtime ADB port from `bluestacks.conf`. It
prefers the runtime status port if that differs from the original port. Do not
assume that every instance uses port 5555.

The default backend paths are:

```text
C:/Program Files/BlueStacks_nxt/HD-Adb.exe
C:/ProgramData/BlueStacks_nxt/bluestacks.conf
```

These defaults are defined by `ADB` and `CONFIG` in `lib/background_input.py`.
A nonstandard installation needs the correct backend paths; the current GUI
does not have a path picker for these two values.

The bot uses its own local ADB server on port **5042**. This is separate from
the selected Android instance's device port. It does not need remote ADB access
or router port forwarding. Leave the private server setting unchanged for a
normal setup.

## 4. Install the Python dependencies

Open PowerShell in the cloned repository folder and run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If Tesseract is installed somewhere else, set its executable path before
launching the bot. Replace the example with your installation path:

```powershell
$env:MFF_TESSERACT_CMD = 'D:/Tools/Tesseract-OCR/tesseract.exe'
```

The environment variable affects this PowerShell session. A local Tesseract.js
fallback is also supported by the code, but it is optional. This repository
intentionally excludes the development machine's `settings/ocr-runtime.local.json`;
a fresh clone should use its own Tesseract installation.

## 5. Start and connect the modern GUI

For an installed copy, use **Start menu > Nyxolir > MFF Bot**. For a source
checkout, run:

```powershell
.\.venv\Scripts\python.exe app_gui.py
```

1. In the bot's **File** menu, keep **Background control (ADB, no mouse)** checked.
2. Click **Connect BlueStacks**.
3. Wait for a fresh game preview and a successful connection message.
4. Click **Check Screen** while a recognized game page is visible to confirm
   that OCR and screen recognition work.

Background mode captures and sends taps/swipes through ADB without moving the
physical mouse. It does not silently fall back to foreground mouse input if
ADB fails. The previous desktop launchers refer to a local development Python
environment and a separately built executable; use the source command above
on a new installation.

## 6. Configure the queue

Use the GUI's queue profiles and Add/Edit/Remove controls to select and enable
the supported content you want to run. Save the queue normally through the
GUI. Start with the game on its Home screen or a recognized content page.
Choose **Start Queue** only when ready for the bot to perform enabled tasks.

The saved queue order does not override the priority rules described in the
[README](README.md#how-the-queue-chooses-work): early trivia at safe boundaries,
fresh objective checks, GBR reward clearance before boosted farming, then
required Dimension clears/contribution ahead of other boosted farms. Content
with an explicit no-GBR/no-boost rule can remain eligible during waits. The
bot protects already-submitted batches and does not interrupt them for trivia.

The modern policy checks enough **boost points** for a full boosted batch; it
does not require OCR of energy balances or ticket stock. Remaining entries,
selected batch size, ticket/start control identity, mode identity and
zero-crystal protection still matter. Set up your game teams beforehand; only
Zombie Survival deliberately selects the top five current roster positions.

Completed work displays at the bottom of the queue. You can scroll while it
runs, but queue editing and drag/drop are locked during execution. **Stop Queue**
stops new bot inputs; an in-game auto battle already submitted may continue.

## 7. Local settings and daily state

The bot creates its local GUI settings under `settings/gui/`, including queue
configuration, verified daily completion, GBR clearance and pending outcomes.
For an installed copy, this is `%LOCALAPPDATA%\Nyxolir\MFFBot\settings\gui`;
for source runs, it remains the existing folder in the checkout. Logs follow
the same distinction. Installing a release does not import account state from
a development checkout.
Daily completion and GBR clearance expire at **15:00 UTC**. Passive Dispatch
claim scheduling has its own clock.

These local files are ignored by Git, except for the portable trivia additions
file. Do not copy another account's saved state into your setup. Keep your own
pending-state files when restarting or updating: deleting them can discard the
evidence needed to avoid replaying an uncertain submission. Local diagnostics
are written under `diagnostics/` and are also excluded from Git.

## Missing trivia answers

**The trivia bank is incomplete.** Game updates can add questions that are not
in the original data or the verified additions. Unknown wording, conflicting
answers or ambiguous options stop that trivia attempt without guessing or
marking the day complete. Early checks give you time to resolve missing answers
before the next reset.

You can answer in the game yourself. To add a question for future attempts,
first verify the correct answer from the game, then add it to the `answers`
object in `settings/gui/trivia-answers.json`. Preserve the existing entries and
the top-level `version: 1` field. The structure is:

For an installed copy, edit
`%LOCALAPPDATA%\Nyxolir\MFFBot\settings\gui\trivia-answers.json`; create the
file with the structure below if it does not exist. Bundled verified answers
and your separate additions are merged when a question is checked. Updating
the app refreshes bundled answers without overwriting your additions.

```json
{
  "version": 1,
  "answers": {
    "Exact question text shown in the game": "Exact confirmed answer text"
  }
}
```

This is a format example, not a question/answer to add. Use the actual question
and answer wording, valid JSON with double quotes, and no trailing commas.
The bot reloads verified additions when looking up questions. If a new entry
conflicts with an existing known answer, the loader rejects the override;
resolve the discrepancy instead of forcing an unverified answer.

A verified completed question-and-answer summary is sufficient to finish
trivia for that day; the bot does not need to scroll through all five rows.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| ADB disabled or connection refused | Enable ADB in BlueStacks Advanced settings, keep the intended player open and click Connect BlueStacks again. |
| Multiple or unmatched instances | Close other player windows for the initial connection; the selected window must match a uniquely configured instance. Do not guess a port. |
| Missing ADB installation/configuration | Confirm the standard backend paths above, or configure the actual installation paths in the backend. |
| Landscape/size error | Use a 16:9 landscape Android resolution of at least 640 x 360, then reconnect. |
| Resolution changed during the session | Reconnect so capture and tap scaling are recalculated. |
| No OCR runtime | Install Tesseract 5 with English data, check PATH/default installation, or set MFF_TESSERACT_CMD. |
| Unknown screen or missing trivia answer | Keep the outcome unverified; inspect the actual page and local log rather than forcing a completion or answer. |
| Waiting for GBR or Dimension boost | Check the priority rules; a resource wait is not completion, and other boosted farms cannot consume reserved boost. |

The raw screenshot regression fixtures are private and are not included in the
repository. Tests that depend on them require the local fixture set; see
`tests/fixtures/README.md`.
