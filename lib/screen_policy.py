"""Connect recognized screens to conservative queue decisions.

Positive entries cannot authorize battle until start controls and costs have
been validated. This adapter currently handles observed completion and blocks.
"""
from datetime import timedelta
from lib.farming import Action, Decision


def evaluate(evidence, captured_at, now):
    if captured_at.tzinfo is None or now.tzinfo is None or not (
            timedelta(0) <= now-captured_at <= timedelta(seconds=30)):
        return Decision(Action.STOP, "Fresh screenshot evidence required")
    if evidence.errors or not evidence.values:
        return Decision(Action.STOP, "Screen recognition incomplete")
    values = evidence.values
    if values.get("refill_prompt"):
        return Decision(Action.STOP, "Entry refill is forbidden")
    if evidence.screen == "world_event" and values.get("already_done"):
        return Decision(Action.SKIP, "Existing World Event score; already done")
    if evidence.screen in {"timeline", "otherworld"}:
        entries = values.get("entries")
        if entries and entries[0] == 0:
            return Decision(Action.SKIP, "No reward entries remain")
    if evidence.screen in {"gbr_main", "gbr_rewards"}:
        return Decision(Action.STOP, "Collect both fresh GBR counters; raid remains manual")
    return Decision(Action.STOP, "Battle controls and costs require further validation")
