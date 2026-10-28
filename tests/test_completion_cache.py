from datetime import datetime,timedelta,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from lib.gui.widgets import completion_cache as cache
from lib.daily_queue import ContinuousQueue,next_reset,reset_period

class Harness(cache.CompletionCache):
    def __init__(self):self.queue_engine=ContinuousQueue();self.log=lambda *args:None

class CompletionTests(unittest.TestCase):
    def test_dimension_objective_and_submitted_surplus_claim_survive_restart(self):
        from lib.objectives import MissionPlan
        now=datetime.now(timezone.utc)
        root=Path(__file__).resolve().parents[3]/'work/cache-tests';root.mkdir(parents=True,exist_ok=True)
        with TemporaryDirectory(dir=root) as directory,patch.object(cache,'CACHE',Path(directory)/'done.json'):
            first=Harness();first.queue_engine.start(now)
            first.objective_plan=MissionPlan(10,True,1);first.objective_period=reset_period(now);first.objective_checked_at=now
            first.queue_engine.pending=(reset_period(now),'DIMENSION MISSION',10)
            first.contribution_followup=True;first.contribution_submitted=True;first.contribution_before=(120,60)
            first.contribution_acquire_submitted=True
            self.assertTrue(first.persist_pending_clear())
            second=Harness();second.load_pending_clear()
            self.assertEqual(second.queue_engine.pending,first.queue_engine.pending)
            self.assertEqual(second.objective_plan,first.objective_plan);self.assertTrue(second.contribution_followup)
            self.assertTrue(second.contribution_submitted);self.assertEqual(second.contribution_before,(120,60))
            self.assertTrue(second.contribution_acquire_submitted)
            self.assertNotIn('DIMENSION MISSION',second.queue_engine.completed)

    def test_zombie_submission_and_repeat_end_survive_restart_without_replay(self):
        now=datetime.now(timezone.utc);started=now-timedelta(minutes=5)
        root=Path(__file__).resolve().parents[3]/'work/cache-tests';root.mkdir(parents=True,exist_ok=True)
        with TemporaryDirectory(dir=root) as directory,patch.object(cache,'CACHE',Path(directory)/'done.json'):
            first=Harness();first.queue_engine.start(now);first.zombie_started=started;first.zombie_repeat_finished=True
            first.queue_engine.pending=(reset_period(now),'ZOMBIE SURVIVAL',5);self.assertTrue(first.persist_pending_clear())
            restored=Harness();restored.load_pending_clear()
            self.assertEqual(restored.queue_engine.pending,first.queue_engine.pending);self.assertEqual(restored.zombie_started,started);self.assertTrue(restored.zombie_repeat_finished)
            self.assertNotIn('ZOMBIE SURVIVAL',restored.queue_engine.completed)

    def test_zombie_board_completion_survives_restart_then_daily_board_rechecks_weekly_state(self):
        now=datetime.now(timezone.utc)
        root=Path(__file__).resolve().parents[3]/'work/cache-tests';root.mkdir(parents=True,exist_ok=True)
        with TemporaryDirectory(dir=root) as directory,patch.object(cache,'CACHE',Path(directory)/'done.json'):
            first=Harness();first.queue_engine.start(now);first.record_completed('ZOMBIE SURVIVAL',now,now)
            restored=Harness();restored.load_completed_missions();restored.queue_engine.start(now)
            self.assertIsNone(restored.queue_engine.next_mode(['ZOMBIE SURVIVAL'],now))
            self.assertEqual(restored.queue_engine.next_mode(['ZOMBIE SURVIVAL'],next_reset(now)),'ZOMBIE SURVIVAL')

    def test_timeline_terminal_state_survives_reload(self):
        now=datetime.now(timezone.utc)
        root=Path(__file__).resolve().parents[3]/'work/cache-tests';root.mkdir(parents=True,exist_ok=True)
        with TemporaryDirectory(dir=root) as directory,patch.object(cache,'CACHE',Path(directory)/'done.json'):
            first=Harness();first.queue_engine.start(now);first.arena_started=now
            first.queue_engine.pending=(reset_period(now),'TIMELINE BATTLE',2);first.arena_repeat_finished=True
            first.persist_pending_clear();restored=Harness();restored.load_pending_clear()
            self.assertTrue(restored.arena_repeat_finished);self.assertEqual(restored.queue_engine.pending[1],'TIMELINE BATTLE')
    def test_explicit_repeat_end_survives_restart_without_marking_complete(self):
        now=datetime.now(timezone.utc)
        root=Path(__file__).resolve().parents[3]/'work/cache-tests';root.mkdir(parents=True,exist_ok=True)
        with TemporaryDirectory(dir=root) as directory,patch.object(cache,'CACHE',Path(directory)/'done.json'):
            first=Harness();first.queue_engine.start(now);first.arena_started=now
            first.queue_engine.pending=(reset_period(now),'OTHERWORLD BATTLE',5);first.arena_repeat_finished=True
            self.assertTrue(first.persist_pending_clear())
            restored=Harness();restored.load_pending_clear()
            self.assertTrue(restored.arena_repeat_finished);self.assertIsNotNone(restored.queue_engine.pending)
            self.assertNotIn('OTHERWORLD BATTLE',restored.queue_engine.completed)
    def test_arena_submission_and_original_clock_survive_restart(self):
        now=datetime.now(timezone.utc);started=now-timedelta(minutes=20)
        root=Path(__file__).resolve().parents[3]/'work/cache-tests';root.mkdir(parents=True,exist_ok=True)
        for mode in ('TIMELINE BATTLE','OTHERWORLD BATTLE','TEAM BATTLE ARENA'):
            with self.subTest(mode=mode),TemporaryDirectory(dir=root) as directory,patch.object(cache,'CACHE',Path(directory)/'done.json'):
                first=Harness();first.queue_engine.start(now);first.arena_started=started
                first.queue_engine.pending=(reset_period(now),mode,5);self.assertTrue(first.persist_pending_clear())
                restored=Harness();restored.load_pending_clear()
                self.assertEqual(restored.queue_engine.pending,first.queue_engine.pending)
                self.assertEqual(restored.arena_started,started)

    def test_held_outcome_is_not_restored_from_stale_pending_file(self):
        now=datetime.now(timezone.utc)
        root=Path(__file__).resolve().parents[3]/'work/cache-tests';root.mkdir(parents=True,exist_ok=True)
        with TemporaryDirectory(dir=root) as directory,patch.object(cache,'CACHE',Path(directory)/'done.json'):
            first=Harness();first.queue_engine.start(now);first.queue_engine.pending=(reset_period(now),'MUTUAL ENEMY',2)
            self.assertTrue(first.persist_pending_clear())
            first.queue_held={'MUTUAL ENEMY'};first.queue_held_period=reset_period(now);first.persist_completed_missions()
            restored=Harness();restored.load_completed_missions();restored.load_pending_clear()
            self.assertIsNone(restored.queue_engine.pending);self.assertIn('MUTUAL ENEMY',restored.queue_held)
    def test_completed_quests_survive_restart_and_expire_at_reset(self):
        now=datetime.now(timezone.utc)
        root=Path(__file__).resolve().parents[3]/'work/cache-tests';root.mkdir(parents=True,exist_ok=True)
        with TemporaryDirectory(dir=root) as directory,patch.object(cache,'CACHE',Path(directory)/'done.json'):
            first=Harness();first.queue_engine.start(now)
            first.record_completed('CUTTING CABLE',now,now)
            second=Harness();second.load_completed_missions();second.queue_engine.start(now)
            self.assertEqual(second.queue_engine.next_mode(['CUTTING CABLE','MUTUAL ENEMY'],now),'MUTUAL ENEMY')
            self.assertEqual(second.queue_engine.next_mode(['CUTTING CABLE'],next_reset(now)),'CUTTING CABLE')

    def test_future_old_or_invalid_records_do_not_skip_quests(self):
        now=datetime.now(timezone.utc)
        data=dict(version=1,period=reset_period(now),recorded_at=now.isoformat(),expires_at=next_reset(now).isoformat(),completed=['CUTTING CABLE'])
        self.assertEqual(cache.restore_completed(data,now),{'CUTTING CABLE'})
        self.assertEqual(cache.restore_completed(data,next_reset(now)),set())
        self.assertEqual(cache.restore_completed(data,now-timedelta(seconds=1)),set())
        data['completed']=['UNKNOWN'];self.assertEqual(cache.restore_completed(data,now),set())

    def test_held_quest_is_saved_separately_from_completed(self):
        now=datetime.now(timezone.utc)
        root=Path(__file__).resolve().parents[3]/'work/cache-tests'
        root.mkdir(parents=True,exist_ok=True)
        with TemporaryDirectory(dir=root) as directory,patch.object(cache,'CACHE',Path(directory)/'done.json'):
            first=Harness();first.queue_engine.start(now)
            first.queue_held={'CUTTING CABLE'};first.queue_held_period=reset_period(now)
            self.assertTrue(first.persist_completed_missions())
            second=Harness();second.load_completed_missions()
            self.assertEqual(second.queue_held,{'CUTTING CABLE'})
            self.assertEqual(second.queue_engine.completed,set())
