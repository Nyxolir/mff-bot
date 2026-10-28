# Current MFF farming port — first implementation

This is a local Apache-2.0 fork of tmarenko/mff_auto. The upstream project targeted MFF 7.5.1. That remains a historical reference, not a current-game compatibility claim.

## Implemented

- Python 3.12 / Windows x64 dependencies, replacing the old Python 3.6 pins and redundant win32gui package.
- Maintained scikit-image SSIM API instead of the bundled CPython-3.6-only SciPy extension.
- Lazy Tesseract 5 OCR, with a configured local Tesseract.js fallback. Screenshots remain local; only the English model is downloaded on first use.
- Packaging-based version comparison, replacing removed distutils imports.
- Disabled archived upstream auto-update at GUI launch; the port's GUI settings use a separate namespace.
- Strict farming decisions: both GBR counters must be zero before energy/boost spending; fresh evidence required; no crystals, upgrades or refills; Team 1 required for Timeline; ticket icon required for arena repeat; existing World Event score skips the mode.
- Bounded queue controller: never retries an action with an unknown outcome, never starts a second run while one is pending, and verifies completion before marking a mode done.
- Current-screen reader with real screenshot regression fixtures: GBR Soul/Seed counters, World Event score, Otherworld reward count and ticket icon, Timeline entries, selected Team 1 and refill control, and completed arena-board marks.
- Read-only live BlueStacks bridge (`scripts/sky_live_reader.mjs`) tested through Computer Use. It captures fresh screenshots and invokes the same Python detector; it cannot send input. `lib/screen_policy.py` connects evidence to skip/stop decisions with a 30-second freshness limit.

## Desktop app

### Continuous queue update

The GUI now has Start Queue / Stop Queue. Its daily gate retains observed Soul 0/165 plus Seed 0/300 until the next 15:00 UTC reset, including across Stop/Start and app restarts through the validated local clearance cache. Daily completion records expire at reset. The queue stays active while waiting for GBR completion, resources or the next reset.

Full-batch authorization requires the selected quantity to equal all remaining entries, verified total energy/boost/ticket costs, sufficient balances, boosted mode, zero crystal cost, a fresh screenshot and a current GBR clearance. Stop and reset are rechecked immediately before submitting a clear. An unresolved clear cannot be retried. Manual skill controls remain shelved; Normal Alliance Battle uses built-in auto.

Current objective inspection discovers active Special Benefits titles rather than matching a weekly event name. Otherworld Battle Pass and Future Pass are excluded. See VERIFIED_RUNS.md for the latest live checks and FARMING_RULES.md for the conditional mission rules. Dimension and the current common Epic Quest sweep layouts are supported. Epic popup submission uses fresh verified preparation costs, the exact full remaining quantity, and the popup ticket cost/balances. Its result Close control is separate from Dimension and never repeats the mission. Unknown layouts remain blocked. Contribution claiming and Dispatch execution have offline coverage, with Dispatch preparation inspected live.

Double-click **MFF Auto.exe** on this PC. This opens the original MFF Auto layout with four editable queue profiles, Add/Edit/Remove, checkboxes and drag ordering, saved settings, a live BlueStacks preview, quick checks and logs. The app uses the existing isolated Python environment; no install command is needed. Keep the launcher in this folder. Its buildable source is `scripts/DesktopLauncher.cs`; it is a launcher rather than a standalone bundle of Python dependencies.

1. Open one BlueStacks App Player window and keep it restored.
2. Click **Connect BlueStacks** for the live preview.
3. Navigate in the game yourself and click **Check Screen** to read it.
4. Use **Check Queue** to report current queue status. Queues save when edited and on exit.

When the enabled queue contains energy missions, **Check Queue** first performs a resource inspection: it navigates through Select Mission → Co-op → Giant Boss Raid → Onslaught → horizontal bottom reward strip, reads energy and boost balances, and reads both daily GBR reward counters by icon, swiping the strip in either direction. It does not open detailed rewards. **Check Resources** runs the same inspection directly. **Cancel Resource Check** stops it. The check uses only these navigation controls, never creates a lobby or starts content, and stops rather than retrying an uncertain click. Start with the game home, status board, mission selector, or a recognized arena screen visible. The game may remain on GBR's reward screen afterward.

The queue log reports the actual blocker (for example, `GBR incomplete — Soul 63/165, Seed 121/300`) instead of the former resource-check placeholder. Fresh zero GBR counters only clear the GBR gate; individual mission costs still need validation before any future spending feature. Battle execution remains shelved.

Live verification, 2026-10-18 23:27 local: the normal desktop launcher completed the automatic mission-selector → Co-op → GBR → Rewards Available route. It read energy 45,838/120, boost 100, Soul 63/165 and Seed 121/300, then reported GBR incomplete for each enabled energy mission. No battle was started and no resources were spent. Launching the GUI inside Codex's command sandbox cannot activate the external game; use the desktop launcher for interactive navigation.

Battle controls are shelved at the user's request. No battle, upgrade, refill, purchase, restart, or legacy task is executed. Resource inspection navigates menus without spending resources. Unknown screens remain unknown; unsupported window sizes require the 1280x720 game viewport. Saved screenshot checks cannot unlock farming. World Boss and Alliance Battle remain manual.

The desktop entry point now uses `ModernMainWindow`, reusing the original designer layout without constructing the old emulator/game task controller. The old `lib/gui/widgets/main.py` is retained only as archived reference.

## Command-line tools

From this folder, using the isolated interpreter already installed on this workstation:

```powershell
& '../../work/mff-venv/Scripts/python.exe' farm.py --doctor
& '../../work/mff-venv/Scripts/python.exe' farm.py --demo
& '../../work/mff-venv/Scripts/python.exe' -m unittest discover -s tests -v
```

`farm.py --state observation.json` accepts `observations` and an optional `raid` object, using the dataclass fields in `lib/farming.py`. Timestamps must be timezone-aware ISO-8601 strings. It only prints decisions; it cannot click or spend resources. Omitted/unknown costs stop the decision.

For another machine: create a Python 3.12 virtual environment, install requirements.txt, and either install Tesseract 5 with English language data or provide settings/ocr-runtime.local.json with Node.js and the node_modules folder containing tesseract.js. The local JSON supplied here refers to this workstation's existing runtime.

## Not ready for unattended play

The current-game detector covers the screens listed above at a 1280x720 viewport (1312x753 BlueStacks window). The battle input driver, positive-entry start screens, energy costs and sweep confirmations still need implementation and validation. Unsupported layouts or unreadable fields stop. The old GUI still contains obsolete game modes, coordinates and upgrade routines. Do not use it for unattended account farming. The new controller deliberately does not call those legacy routines.

The 2026-10-18 manual battle tests in VERIFIED_RUNS.md were done with computer-control tools, not by this program. During detector development, navigation and read-only inspection were performed; no battles, refills, upgrades or resource spending were performed. All three free arenas were already complete, World Event had a score, and GBR was incomplete (63/165 and 121/300), so there was no eligible battle for a live run test.

## Next integration

1. Capture and validate positive-entry start screens and resource-cost confirmations when an eligible mode is available.
2. Implement the battle Driver protocol using verified observations, with bounded waits for loading and results.
3. Test a single no-energy action before enabling an unattended queue. Current completed entries cannot validate that step.

Read a saved screenshot without input:

```powershell
& '../../work/mff-venv/Scripts/python.exe' read_screen.py tests/fixtures/world_event.png
```

For a live read, import `SkyReader` from `scripts/sky_live_reader.mjs` in the Computer Use Node REPL, passing its initialized `sky`, the returned BlueStacks window, the isolated Python executable and this repository root. Call `observe()`. This bridge returns evidence and a conservative decision; input remains disabled. Saved fixtures have no capture timestamp and cannot authorize an action.

## Compact reward-strip correction

The resource inspector now uses icon-anchored positions in the horizontal Onslaught reward strip. It retains each observed counter while swiping to find the other, with bounded navigation. Real fixtures cover Soul 63/165, red Soul 0/165, and Seed 1/300. The Seed text crop excludes the glowing icon; a remaining Seed blocks energy missions. The boost-icon match allows its observed animation while rejecting dimmed screens.


