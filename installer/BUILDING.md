# Windows installer builds

Installers are provided as Release assets. Keep direct installer-download links
out of the README. Verified local artifacts may also be uploaded manually with
their matching source archive, build manifest and checksums.

Every push to main builds the exact source revision,
checks offline OCR and GUI startup, and verifies installation, reinstall and
uninstall using isolated user data. Only a successful build publishes the
installer, corresponding source, validation manifest and checksums as Release
assets. A draft stages all assets before becoming the latest release; failed
builds retain the previous latest release. Manual runs are also available.
README.md contains no direct installer-download link, badge or workflow link.

The build also compiles the small native update helper. Isolated fake-app tests
verify parent-exit ordering, cancellation, missing authorization, modified
installers and installation failures. The installed-app test exercises the
actual GUI handoff, silent installer, offline verification and restarted-app
receipt, including selected-queue and running-state restoration. It records
resume intent without connecting to BlueStacks or starting a game queue.

## What is included

- Frozen Python 3.12 application and required libraries.
- Recognition templates and the verified default trivia bank.
- A pinned Node/Tesseract.js OCR runtime and the same English model used by
  the existing regression suite. OCR works without a first-run model download.
- Per-user Inno Setup installer, Start menu shortcut and optional desktop icon.
- Component licenses, dependency inventory, corresponding bot source archive,
  source revision, validation manifest and SHA-256 checksums.

Private configuration, pending runs, credentials, raw screenshot fixtures,
diagnostics and personal builder identity are excluded. Frozen bytecode paths
and payload contents are checked for builder identity before packaging.

## Local build

Use Windows x64, Python 3.12 and a clean build environment. In PowerShell:

```powershell
py -3.12 -m venv .venv-build
./installer/Build.ps1 -Version 0.1.0 -Python ./.venv-build/Scripts/python.exe
```

The script downloads hash-pinned build inputs from their published vendor
locations, verifies the Inno compiler's signature, installs locked Python/npm
dependencies and calls `build.py`. No system Python or OCR settings are changed.
Build tools and temporary files stay under `build/`; release artifacts appear
under `dist/release/`. Both directories are ignored by Git.

The installer build self-test creates an isolated profile, verifies GUI startup
and offline OCR without connecting to BlueStacks, then tests install,
reinstall and uninstall. It refuses to replace a pre-existing installed MFF Bot
for this test. Pending-state and custom-answer sentinels must survive reinstall
and uninstall. Locally, `MFF_SELFTEST_FIXTURES` can point to the private fixture
directory for additional packaged-reader checks; CI does not receive these
screenshots.

Run the full local bot suite for shared runtime changes before pushing. Private
screenshot fixtures are not in the repository. A local packaging check does not
replace the complete private regression suite.

## Dependency updates

Update `requirements-build.txt`, `ocr/package.json` and its lockfile, or
`runtime-inputs.json` deliberately, then run local checks and the installer
test again. The English model has both compressed and uncompressed hashes.
Keep licensing/source references current. Do not commit credentials, private
configuration or locally generated build artifacts.

Locally built installers are currently unsigned. No private signing key is
included in the source.
