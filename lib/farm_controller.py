"""Bounded farming queue orchestration for a separately validated UI driver.

Drivers must implement the named actions using fresh screen observations. The
archived coordinate driver is deliberately not wired to this controller.
"""
from datetime import datetime, timezone
from typing import Protocol

from lib.farming import Action, Decision, Observation, RaidCheck, decide


class Driver(Protocol):
    def observe(self) -> Observation: ...
    def inspect_gbr(self) -> RaidCheck: ...
    def select_team_1(self) -> None: ...
    def run(self, action: Action, runs: int) -> None: ...


class FarmingSession:
    def __init__(self, driver: Driver, clock=None):
        self.driver = driver
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.raid = None
        self.halted = False
        self.pending = None
        self.completed = set()
        self.events = []

    def step(self):
        if self.halted:
            return Decision(Action.STOP,"Session halted; inspect the cause before restarting")
        try:
            o = self.driver.observe()
            key = (o.reset_id,o.mode.strip().upper())
            if self.pending:
                return Decision(Action.STOP,"Wait for verified completion of the active run")
            if key in self.completed:
                return Decision(Action.SKIP,"This mode is already complete for this reset")
            result = decide(o,self.raid,self.clock())
            if result.action == Action.CHECK_GBR:
                self.raid = self.driver.inspect_gbr()
                # Raid inspection changes the screen. Return without spending;
                # the next step must observe the intended mission again.
                self.events.append((key,"raid_checked"))
                return result
            if result.action == Action.SELECT_TEAM_1:
                self.driver.select_team_1()
                # Selecting a team is not proof it was selected successfully.
                # A new observation must verify it before the next step.
                return result
            if result.action in (Action.SKIP,Action.STOP):
                return result
            # Set pending BEFORE touching UI: a timeout has an unknown outcome,
            # so no automatic retry may spend another entry.
            self.pending = (key,result)
            self.driver.run(result.action,result.runs)
            self.events.append((key,result.action.value))
            return result
        except Exception:
            self.halted = True
            raise

    def verify_completion(self, observation):
        if not self.pending:
            raise RuntimeError("No active run to verify")
        key, decision = self.pending
        if (observation.reset_id,observation.mode.strip().upper()) != key:
            raise ValueError("Completion belongs to a different mode or reset")
        now = self.clock()
        check = decide(observation,self.raid,now)
        if check.action != Action.SKIP:
            raise ValueError("Fresh screen does not verify completed rewards or World Event score")
        # For approved automatic modes, SKIP can only come from zero remaining
        # entries or an existing World Event score (validated by decide).
        self.completed.add(key)
        self.pending = None
        self.events.append((key,"completed"))
