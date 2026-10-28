"""Read a saved screenshot; never clicks or marks saved evidence fresh."""
import argparse
from dataclasses import asdict
import json
from datetime import datetime, timezone
from lib.screen_reader import ScreenReader
from lib.screen_policy import evaluate

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("--captured-at", help="Timezone-aware timestamp from the live capture bridge")
    args = parser.parse_args()
    result = ScreenReader().read(args.image)
    output = asdict(result)
    if args.captured_at:
        output["decision"] = asdict(evaluate(result, datetime.fromisoformat(args.captured_at), datetime.now(timezone.utc)))
    print(json.dumps(output, indent=2))
    raise SystemExit(0 if result.values and not result.errors else 2)
