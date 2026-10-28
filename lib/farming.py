"""Current-game decisions. No clicks or resource spending occur in this module.

The UI driver must supply fresh observations before every action. Unknown or
unreadable observations stop rather than fall back to legacy game routines.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import re


class Action(str, Enum):
    STOP = "stop"
    SKIP = "skip"
    CHECK_GBR = "check_gbr"
    SELECT_TEAM_1 = "select_team_1"
    TICKET_REPEAT = "ticket_repeat"
    TIMELINE_AUTO = "timeline_auto"
    WORLD_EVENT = "world_event_once"
    SWEEP = "sweep"


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str
    runs: int = 0


@dataclass(frozen=True)
class RaidCheck:
    soul_remaining: int
    soul_total: int
    seed_remaining: int
    seed_total: int
    reset_id: str
    observed_at: datetime

    def permits_farming(self, reset_id, now):
        if any(type(value) is not int for value in (
            self.soul_remaining,self.soul_total,self.seed_remaining,self.seed_total
        )):
            return False
        return (
            bool(reset_id) and self.reset_id == reset_id
            and timedelta(0) <= now - self.observed_at <= timedelta(minutes=10)
            and (self.soul_remaining, self.soul_total) == (0, 165)
            and (self.seed_remaining, self.seed_total) == (0, 300)
        )


@dataclass(frozen=True)
class Observation:
    mode: str
    remaining: int | None
    energy_cost: int | None
    boost_cost: int | None
    observed_at: datetime
    reset_id: str
    ticket_icon_verified: bool = False
    team_1_verified: bool = False
    best_score: int | None = None
    crystal_cost: int | None = None
    upgrade_prompt: bool = False
    refill_prompt: bool = False
    sweep_verified: bool = False


ENERGY_FARMS = frozenset({
    "MAGNETO'S MIGHT", "RISE OF THE PHOENIX", "MUTUAL ENEMY",
    "CUTTING CABLE", "ENDING THE STRYFE", "BEGINNING OF THE CHAOS",
    "MADNESS ENSUES", "SHOCK AND AWE", "READY FOR BATTLE",
    "QUEEN OF LIMBO", "SINISTER SCHEMES", "DIMENSION MISSION",
})
# Explicit user exception: energy-only ticket sweeps, no boost or GBR gate.
UNBOOSTED_SWEEPS = frozenset({'[NORMAL] CONVERGING FATES','[HIDDEN] CONVERGING FATES'})
MANUAL = frozenset({"WORLD BOSS", "ALLIANCE BATTLE", "GIANT BOSS RAID"})
FREE_ARENAS = frozenset({"OTHERWORLD BATTLE", "TEAM BATTLE ARENA"})


def parse_counter(text):
    """Never turn an OCR letter O, missing value, or guess into zero."""
    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", text)
    if not match:
        raise ValueError("Unreadable daily reward counter")
    remaining, total = map(int, match.groups())
    if total == 0 or remaining > total:
        raise ValueError("Invalid daily reward counter")
    return remaining, total


def decide(o, raid=None, now=None):
    now = now or datetime.now(timezone.utc)
    if o.observed_at.tzinfo is None or now.tzinfo is None:
        return Decision(Action.STOP, "Timezone-aware evidence is required")
    if not timedelta(0) <= now - o.observed_at <= timedelta(seconds=30):
        return Decision(Action.STOP, "Refresh the screen before acting")
    if any(type(value) is not bool for value in (
        o.upgrade_prompt,o.refill_prompt,o.ticket_icon_verified,
        o.team_1_verified,o.sweep_verified
    )):
        return Decision(Action.STOP, "Unverified screen flags")
    if type(o.crystal_cost) is not int:
        return Decision(Action.STOP, "Crystal cost is unreadable")
    if o.upgrade_prompt or o.refill_prompt or o.crystal_cost != 0:
        return Decision(Action.STOP, "No upgrades, refills, or unverified crystal costs")
    mode = o.mode.strip().upper()
    if mode in MANUAL:
        return Decision(Action.SKIP, "Reserved for the user")
    if mode not in ENERGY_FARMS | UNBOOSTED_SWEEPS | FREE_ARENAS | {"TIMELINE BATTLE", "WORLD EVENT"}:
        return Decision(Action.SKIP, "Mode is not validated for farming")
    if mode == "WORLD EVENT":
        if type(o.best_score) is not int or o.best_score < 0:
            return Decision(Action.STOP, "Read the existing World Event score first")
        if o.best_score > 0:
            return Decision(Action.SKIP, "An existing score means World Event is done")
    if type(o.remaining) is not int or not 0 <= o.remaining <= 100:
        return Decision(Action.STOP, "Read the available entry count first")
    if o.remaining == 0:
        return Decision(Action.SKIP, "No reward entries remain")
    if type(o.boost_cost) is not int or o.boost_cost<0:
        return Decision(Action.STOP, "Verify boost cost")
    spends_resources = mode in ENERGY_FARMS or bool(o.boost_cost)
    if spends_resources:
        if not raid or raid.observed_at.tzinfo is None or not raid.permits_farming(o.reset_id, now):
            return Decision(Action.CHECK_GBR, "Require fresh 0/165 AND 0/300 GBR counters")
    if mode == "TIMELINE BATTLE":
        if spends_resources:
            return Decision(Action.STOP, "Unexpected Timeline resource cost")
        if not o.team_1_verified:
            return Decision(Action.SELECT_TEAM_1, "Verify selected Team 1 before battle")
        return Decision(Action.TIMELINE_AUTO, "Use existing entries with Auto Play+", o.remaining)
    if mode in FREE_ARENAS:
        if spends_resources or not o.ticket_icon_verified:
            return Decision(Action.STOP, "Verify gray/blue ticket icon and zero energy/boost cost")
        return Decision(Action.TICKET_REPEAT, "Repeat only until available rewards run out", o.remaining)
    if mode == "WORLD EVENT":
        if spends_resources:
            return Decision(Action.STOP, "Unexpected World Event resource cost")
        return Decision(Action.WORLD_EVENT, "One run only; recheck score after results", 1)
    if not o.sweep_verified:
        return Decision(Action.STOP, "Verify Sweep control and resource confirmation")
    return Decision(Action.SWEEP, "Sweep existing entries; never buy refills", o.remaining)
