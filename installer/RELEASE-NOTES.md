Windows x64 installer for MFF Bot, maintained by Nyxolir and based on
tmarenko/mff_auto data, recognition templates and code.

Download **MFF-Bot-Setup.exe**, install, then open **MFF Bot** from the Start menu.
Python and English OCR are bundled; no Python, Node.js or Tesseract installation
is required. BlueStacks and the game are installed separately. Enable ADB in
BlueStacks Settings > Advanced, use a landscape 16:9 display, and click Connect
BlueStacks in the bot. The app starts idle until you start the queue.

Settings and pending outcomes are kept separately under
`%LOCALAPPDATA%\Nyxolir\MFFBot` and preserved during updates and uninstall.
Stop the queue and finish any active game run before updating.

This version adds automatic in-app updates. Install this release once; later
stable releases download automatically and install only at a verified idle
boundary. The Updates menu includes an opt-out and manual check. Settings,
answers, completion state and queue selection are preserved. A stopped queue
stays stopped; a previously running queue resumes after offline verification.
Downloads or updates that fail never authorize replaying a submitted game action.

Priorities: early trivia at safe boundaries; fresh objective checks; GBR reward
clearance before boosted farming; required Dimension clears/contribution ahead
of other boosted content. Missing trivia answers are not guessed.

The executable is currently unsigned. This release does not include BlueStacks,
game files, credentials, raw screenshot fixtures or any saved account state.

Also included: corresponding source/build scripts, build and validation
manifest, and SHA-256 checksums. The installer includes component license
notices, including GPL-3.0 PyQt5 and LGPL Qt. See README and SETUP in the source
archive for the full configuration guide and current supported behavior.
