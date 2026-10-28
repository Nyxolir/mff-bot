from datetime import datetime, timedelta, timezone
import unittest
from lib.farming import Action
from lib.screen_reader import ScreenEvidence
from lib.screen_policy import evaluate


class ScreenPolicyTests(unittest.TestCase):
    def setUp(self): self.now = datetime.now(timezone.utc)

    def check(self, screen, values, action):
        self.assertEqual(evaluate(ScreenEvidence(screen, values), self.now, self.now).action, action)

    def test_completed_modes_skip(self):
        self.check("world_event", {"already_done":True}, Action.SKIP)
        self.check("otherworld", {"entries":(0,5)}, Action.SKIP)
        self.check("timeline", {"entries":(0,5)}, Action.SKIP)

    def test_unvalidated_positive_entries_stop(self):
        self.check("otherworld", {"entries":(5,5),"ticket_icon_verified":True}, Action.STOP)

    def test_refill_never_runs(self):
        self.check("timeline_team", {"team_1_verified":True,"refill_prompt":True}, Action.STOP)

    def test_stale_or_naive_evidence_stops(self):
        evidence=ScreenEvidence("world_event", {"already_done":True})
        for captured in (self.now-timedelta(seconds=31),self.now+timedelta(seconds=1),self.now.replace(tzinfo=None)):
            self.assertEqual(evaluate(evidence,captured,self.now).action,Action.STOP)

    def test_partial_gbr_never_unlocks(self):
        self.check("gbr_main", {"soul":(0,165)}, Action.STOP)
        self.check("gbr_rewards", {"seed":(0,300)}, Action.STOP)
