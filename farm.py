"""Read-only farming planner. Never attaches to an emulator or clicks a UI."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import sys

from lib.farming import Observation, RaidCheck, decide
from lib.ocr import js_runtime, native_executable


def load_state(path):
    state = json.loads(Path(path).read_text(encoding="utf-8"))
    observations = []
    for data in state["observations"]:
        data = dict(data)
        data["observed_at"] = datetime.fromisoformat(data["observed_at"])
        observations.append(Observation(**data))
    data = state.get("raid")
    raid = None
    if data:
        data = dict(data)
        data["observed_at"] = datetime.fromisoformat(data["observed_at"])
        raid = RaidCheck(**data)
    return observations, raid


def doctor():
    packages = {}
    for name in ("numpy", "opencv-python", "Pillow", "scikit-image", "pytesseract", "packaging", "PyQt5", "pywin32", "pyautoit"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    candidate = native_executable()
    portable = js_runtime()
    result = {"python": sys.version.split()[0], "packages": packages,
              "tesseract_executable": candidate,
              "portable_ocr_configured": bool(portable),
              "live_driver_validated": False,
              "mode": "offline planner; no game input"}
    print(json.dumps(result, indent=2))
    return 0 if all(packages.values()) and (candidate or portable) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--doctor", action="store_true")
    group.add_argument("--state", type=Path, help="JSON observations; prints decisions only")
    group.add_argument("--demo", action="store_true", help="Show user-rule examples without accessing the game")
    args = parser.parse_args()
    if args.doctor:
        return doctor()
    now = datetime.now(timezone.utc)
    if args.demo:
        base = dict(remaining=5, energy_cost=0, boost_cost=0, crystal_cost=0,
                    reset_id="demo-reset", observed_at=now)
        observations = [
            Observation(mode="TIMELINE BATTLE", **base),
            Observation(mode="OTHERWORLD BATTLE", ticket_icon_verified=True, **base),
            Observation(mode="WORLD EVENT", best_score=3862486, **base),
            Observation(mode="MAGNETO'S MIGHT", **{**base, "energy_cost":4, "boost_cost":4}),
            Observation(mode="WORLD BOSS", **base),
        ]
        raid = RaidCheck(63,165,121,300,"demo-reset",now)
    else:
        observations, raid = load_state(args.state)
    print(json.dumps([{"mode":o.mode, **asdict(decide(o, raid, now))} for o in observations], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
