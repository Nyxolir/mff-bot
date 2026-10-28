from dataclasses import asdict
from datetime import datetime,timedelta,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from lib.gui.widgets import objective_cache
from lib.objectives import MissionPlan
from lib.daily_queue import reset_period,next_reset

class Harness(objective_cache.ObjectiveCache):
    def __init__(self):
        self.objective_plan=None;self.objective_period=None;self.objective_checked_at=None
        self.log=lambda *args:None

class ObjectiveCacheTests(unittest.TestCase):
    def test_plan_remembers_checks_and_expires_at_reset(self):
        now=datetime.now(timezone.utc);plan=MissionPlan(5,True,1)
        data=dict(version=2,checked_at=now.isoformat(),expires_at=next_reset(now).isoformat(),period=reset_period(now),plan=asdict(plan))
        self.assertEqual(objective_cache.restore_plan(data,now),(plan,now))
        self.assertIsNone(objective_cache.restore_plan(data,next_reset(now)))
        data['plan']['dispatch_mission']=2
        self.assertIsNone(objective_cache.restore_plan(data,now))

    def test_quest_counts_persist_and_old_incomplete_check_version_is_discarded(self):
        now=datetime.now(timezone.utc);plan=MissionPlan(7,True,0)
        data=dict(version=2,checked_at=now.isoformat(),expires_at=next_reset(now).isoformat(),period=reset_period(now),plan=asdict(plan))
        self.assertEqual(objective_cache.restore_plan(data,now),(plan,now))
        data['version']=1;self.assertIsNone(objective_cache.restore_plan(data,now))

    def test_completed_modes_update_cache_and_inflight_forces_reinspection(self):
        root=Path(__file__).resolve().parents[3]/'work/cache-tests';root.mkdir(parents=True,exist_ok=True)
        with TemporaryDirectory(dir=root) as directory,patch.object(objective_cache,'CACHE',Path(directory)/'objectives.json'):
            now=datetime.now(timezone.utc);first=Harness()
            first.objective_plan=MissionPlan(1,False,1);first.objective_period=reset_period(now);first.objective_checked_at=now
            self.assertTrue(first.persist_objective_cache())
            second=Harness();second.load_objective_cache();self.assertEqual(second.objective_plan,first.objective_plan)
            first.objective_completed('DIMENSION MISSION');first.objective_completed('DISPATCH 7-1')
            second.load_objective_cache();self.assertEqual(second.objective_plan,MissionPlan(0,False,0))
            first.persist_objective_cache(inflight=True)
            third=Harness();third.load_objective_cache();self.assertIsNone(third.objective_plan)
