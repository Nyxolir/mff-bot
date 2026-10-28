import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from lib.farm_controller import FarmingSession
from lib.farming import Action,Observation,RaidCheck


class FakeDriver:
    def __init__(self,o):
        self.o=o
        self.calls=[]
        self.fail=False

    def observe(self): return self.o
    def inspect_gbr(self):
        self.calls.append("gbr")
        return RaidCheck(63,165,121,300,self.o.reset_id,self.o.observed_at)
    def select_team_1(self): self.calls.append("team1")
    def run(self,action,runs):
        self.calls.append((action,runs))
        if self.fail: raise TimeoutError("Unknown click outcome")


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,18,21,tzinfo=timezone.utc)
        self.o=Observation("TIMELINE BATTLE",5,0,0,self.now,"reset-a",crystal_cost=0)
        self.driver=FakeDriver(self.o)
        self.session=FarmingSession(self.driver,lambda:self.now)

    def test_selection_must_be_observed_before_battle(self):
        self.assertEqual(self.session.step().action,Action.SELECT_TEAM_1)
        self.assertEqual(self.driver.calls,["team1"])
        self.assertEqual(self.session.step().action,Action.SELECT_TEAM_1)
        self.driver.o=replace(self.o,team_1_verified=True)
        self.assertEqual(self.session.step().action,Action.TIMELINE_AUTO)

    def test_incomplete_gbr_never_spends(self):
        self.driver.o=replace(self.o,mode="MAGNETO'S MIGHT",energy_cost=4,sweep_verified=True)
        self.assertEqual(self.session.step().action,Action.CHECK_GBR)
        self.assertEqual(self.driver.calls,["gbr"])
        self.session.step()
        self.assertFalse(any(isinstance(c,tuple) for c in self.driver.calls))

    def test_unknown_outcome_halts_and_cannot_retry(self):
        self.driver.o=replace(self.o,team_1_verified=True)
        self.driver.fail=True
        with self.assertRaises(TimeoutError): self.session.step()
        self.assertEqual(self.session.step().action,Action.STOP)
        self.assertEqual(len(self.driver.calls),1)

    def test_pending_run_cannot_be_started_twice(self):
        self.driver.o=replace(self.o,team_1_verified=True)
        self.session.step()
        self.assertEqual(self.session.step().action,Action.STOP)
        self.assertEqual(len(self.driver.calls),1)

    def test_completion_requires_fresh_matching_evidence(self):
        self.driver.o=replace(self.o,team_1_verified=True)
        self.session.step()
        for o in (replace(self.driver.o,remaining=1),
                  replace(self.driver.o,remaining=0,reset_id="other"),
                  replace(self.driver.o,remaining=0,observed_at=self.now-timedelta(minutes=1))):
            with self.assertRaises(ValueError): self.session.verify_completion(o)
        self.session.verify_completion(replace(self.driver.o,remaining=0))
        self.assertEqual(self.session.step().action,Action.SKIP)

    def test_world_event_completed_once_per_reset(self):
        self.driver.o=replace(self.o,mode="WORLD EVENT",best_score=0,remaining=2)
        self.session.step()
        self.assertEqual(self.driver.calls,[(Action.WORLD_EVENT,1)])
        self.session.verify_completion(replace(self.driver.o,best_score=3862486,remaining=1))
        self.assertEqual(self.session.step().action,Action.SKIP)


if __name__=="__main__": unittest.main()
