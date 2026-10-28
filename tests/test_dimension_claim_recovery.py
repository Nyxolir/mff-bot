import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import Mock,patch
import unittest
from PyQt5.QtWidgets import QApplication
from tests import test_queue_gui
from lib.gui.widgets import modern_main as gui
from lib.objectives import MissionPlan
from lib.screen_reader import ScreenEvidence
from lib.sweep_reader import SweepReader

class DimensionClaimRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    setUp=test_queue_gui.QueueGuiTests.setUp
    tearDown=test_queue_gui.QueueGuiTests.tearDown
    scan_fixture=test_queue_gui.QueueGuiTests.scan_fixture
    prepare_sweep=test_queue_gui.QueueGuiTests.prepare_sweep
    clear_gbr=test_queue_gui.QueueGuiTests.clear_gbr

    def prepare_claim(self):
        w=self.window;now=self.prepare_sweep();w.queue_target='DIMENSION MISSION';w.queue_phase='dimension_claim'
        w.objective_plan=MissionPlan(5,True,0);w.queue_engine.pending=(gui.reset_period(now),'DIMENSION MISSION',5)
        w.contribution_followup=True;w.contribution_submitted=True;w.contribution_before=(60,60);w.contribution_acquire_submitted=True
        return w,now

    def test_observed_gold_receipt_ack_then_counter_drop_releases_batch_and_next_task(self):
        w,now=self.prepare_claim();w.queues[0]=[{'mode':m,'enabled':True} for m in ('DIMENSION MISSION','CUTTING CABLE')]
        pending=w.queue_engine.pending
        e,stamp,_=self.scan_fixture('dimension_gold_receipt_oct25.png',reader_kind='sweep')
        self.assertEqual(e.screen,'dimension_contribution_receipt');self.assertEqual(e.values['receipt_kind'],'gold')
        with patch.object(gui,'click_game_point') as click:
            w.queue_observation=(e,stamp);w.advance_queue();self.assertEqual(click.call_args.args,(11,640,565))
        self.assertEqual(w.queue_engine.pending,pending);self.assertNotIn('DIMENSION MISSION',w.queue_engine.completed)
        w.queue_observation=(ScreenEvidence('dimension_lobby',{'mode':'DIMENSION MISSION','contribution':(0,60)}),datetime.now(timezone.utc));w.advance_queue()
        self.assertIsNone(w.queue_engine.pending);self.assertIn('DIMENSION MISSION',w.queue_engine.completed)
        self.assertEqual(w.objective_plan,MissionPlan(0,False,0));w.queue_wake=None;w.queue_tick()
        self.assertEqual(w.queue_target,'CUTTING CABLE')

    def test_receipt_requires_claim_submission_and_never_marks_completion_by_itself(self):
        w,now=self.prepare_claim();w.contribution_acquire_submitted=False
        e,stamp,_=self.scan_fixture('dimension_gold_receipt_oct25.png',reader_kind='sweep')
        with patch.object(gui,'click_game_point') as click:
            w.queue_dimension_claim(e,stamp);click.assert_not_called()
        self.assertIsNotNone(w.queue_engine.pending);self.assertNotIn('DIMENSION MISSION',w.queue_engine.completed)

    def test_masked_gold_receipt_identity_body_and_ok_are_rejected(self):
        from PIL import Image,ImageDraw
        original=Image.open(Path(__file__).parent/'fixtures/dimension_gold_receipt_oct25.png').convert('RGB')
        for box in ((67,18,282,52),(520,125,760,163),(450,395,835,438),(555,536,725,593)):
            im=original.copy();ImageDraw.Draw(im).rectangle(box,fill='black')
            self.assertNotEqual(SweepReader().read(im).screen,'dimension_contribution_receipt')

    def test_claim_recovery_preserves_confirmed_batch_and_snapshot_instead_of_holding(self):
        w,now=self.prepare_claim();pending=w.queue_engine.pending
        with patch.object(w,'restart_stuck_game') as restart:
            w.recover_stuck_queue('Gold receipt unreadable');restart.assert_not_called()
        self.assertEqual(w.queue_engine.pending,pending);self.assertTrue(w.contribution_followup)
        self.assertEqual(w.contribution_before,(60,60));self.assertTrue(w.contribution_acquire_submitted)
        self.assertNotIn('DIMENSION MISSION',w.queue_held);self.assertFalse(w.queue_engine.running)

    def test_direct_restart_also_preserves_unverified_contribution(self):
        w,now=self.prepare_claim()
        with patch('lib.gui.widgets.stuck_recovery.RestartTask') as restart:
            w.restart_stuck_game();restart.assert_not_called()
        self.assertIsNotNone(w.queue_engine.pending);self.assertFalse(w.queue_engine.running)

    def test_gold_receipt_stale_or_wrong_mode_cannot_send_acknowledgement(self):
        w,now=self.prepare_claim()
        e,stamp,_=self.scan_fixture('dimension_gold_receipt_oct25.png',reader_kind='sweep')
        with patch.object(gui,'click_game_point') as click:
            w.queue_observation=(e,now-timedelta(seconds=31));w.advance_queue();click.assert_not_called()
            e.values['mode']='CUTTING CABLE';w.queue_observation=(e,stamp);w.advance_queue();click.assert_not_called()
        self.assertIsNotNone(w.queue_engine.pending);self.assertNotIn('DIMENSION MISSION',w.queue_engine.completed)

    def test_recovery_snapshot_restores_claim_after_gui_restart(self):
        from tempfile import TemporaryDirectory
        from lib.gui.widgets import completion_cache
        from tests.test_completion_cache import Harness
        w,now=self.prepare_claim()
        with TemporaryDirectory(dir=self.log_directory.name) as directory,patch.object(completion_cache,'CACHE',Path(directory)/'done.json'):
            with patch.object(w,'persist_pending_clear',side_effect=lambda:completion_cache.CompletionCache.persist_pending_clear(w)):
                w.recover_stuck_queue('unreadable reward')
            restored=Harness();restored.load_pending_clear()
        self.assertEqual(restored.queue_engine.pending,w.queue_engine.pending)
        self.assertTrue(restored.contribution_followup);self.assertTrue(restored.contribution_acquire_submitted)
        self.assertTrue(restored.contribution_submitted);self.assertEqual(restored.contribution_before,(60,60))
        self.assertEqual(restored.objective_plan,MissionPlan(5,True,0))

    def test_legacy_dimension_hold_requests_fresh_objectives_instead_of_board(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.queues[0]=[{'mode':'DIMENSION MISSION','enabled':True}];w.queue_held={'DIMENSION MISSION'}
        with patch.object(w,'check_objectives') as check:
            self.assertTrue(w.start_uncertain_review(now));check.assert_called_once_with(force=True)

    def test_only_complete_current_objective_inspection_can_resolve_legacy_hold(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_held={'DIMENSION MISSION'}
        w.objective_inspection=Mock(done=True,period=gui.reset_period(now));w.objective_plan=MissionPlan(0,False,0)
        self.assertTrue(w.reconcile_held_dimension_objectives());self.assertNotIn('DIMENSION MISSION',w.queue_held)
        self.assertIn('DIMENSION MISSION',w.queue_engine.completed)

    def test_incomplete_stale_outstanding_or_pending_proof_cannot_resolve_hold(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        for kind in ('incomplete','old_reset','claim','pending'):
            w.queue_held={'DIMENSION MISSION'};w.queue_engine.completed.discard('DIMENSION MISSION');w.queue_engine.pending=None
            w.objective_inspection=Mock(done=kind!='incomplete',period=gui.reset_period(now-timedelta(days=1)) if kind=='old_reset' else gui.reset_period(now))
            w.objective_plan=MissionPlan(0,kind=='claim',0)
            if kind=='pending':w.queue_engine.pending=(gui.reset_period(now),'DIMENSION MISSION',5)
            self.assertFalse(w.reconcile_held_dimension_objectives());self.assertIn('DIMENSION MISSION',w.queue_held)
            self.assertNotIn('DIMENSION MISSION',w.queue_engine.completed)

    def test_partial_event_counter_reconciles_hold_to_only_remaining_clears(self):
        from lib.objective_inspection import ObjectiveInspection
        from lib.objectives import parse_objectives
        w,now=self.prepare_claim();w.queue_engine.pending=None;w.queue_held={'DIMENSION MISSION'}
        w.queues[0]=[{'mode':m,'enabled':True} for m in ('CUTTING CABLE','DIMENSION MISSION')]
        e,stamp,_=self.scan_fixture('dimension_event_quest_partial_oct25.png',reader_kind='objectives')
        self.assertFalse(e.errors);self.assertEqual([(r.kind,r.done,r.total) for r in e.values['objectives']],[('dimension',5,10)])
        inspection=ObjectiveInspection(stamp);inspection.daily=parse_objectives('Daily Challenges','[DIMENSION MISSION] Acquire Contribution Reward 1/1')
        inspection.phase='quest_home';inspection.observe(ScreenEvidence('game_home',{'event_quest_point':(1040,507)}),stamp)
        inspection.observe(e,stamp);inspection.observe(e,stamp);inspection.observe(ScreenEvidence('benefit_list',{'events':[]}),stamp)
        self.assertTrue(inspection.done);self.assertEqual(inspection.plan,MissionPlan(5,False,0))
        w.objective_inspection=inspection;w.finish_objectives()
        self.assertNotIn('DIMENSION MISSION',w.queue_held);self.assertNotIn('DIMENSION MISSION',w.queue_engine.completed)
        self.assertEqual(w.eligible_modes(now),['DIMENSION MISSION']);w.queue_wake=None;w.queue_tick()
        self.assertEqual(w.queue_target,'DIMENSION MISSION');self.assertIsNone(w.queue_engine.pending)
        w.queue_remaining=5
        sweep,stamp,_=self.scan_fixture('dimension_five_sweep_oct25.png',reader_kind='sweep')
        with patch('lib.queue_input.execute_sweep_control') as execute:
            w.queue_read_sweep(sweep,stamp);self.assertEqual(execute.call_args.args[2],'clear_batch')
        self.assertEqual(w.queue_engine.pending,(gui.reset_period(now),'DIMENSION MISSION',5))
        result,stamp,_=self.scan_fixture('dimension_five_sweep_result_oct25.png',reader_kind='sweep')
        with patch('lib.queue_input.execute_sweep_control') as execute:
            w.queue_read_sweep(result,stamp);self.assertEqual(execute.call_args.args[2],'close_result')
        self.assertIsNone(w.queue_engine.pending);self.assertIn('DIMENSION MISSION',w.queue_engine.completed)
        self.assertEqual(w.objective_plan,MissionPlan(0,False,0));w.queue_wake=None;w.queue_tick()
        self.assertEqual(w.queue_target,'CUTTING CABLE')

    def test_partial_counter_mask_does_not_become_no_requirement(self):
        from PIL import Image,ImageDraw
        from lib.objective_reader import ObjectiveReader
        im=Image.open(Path(__file__).parent/'fixtures/dimension_event_quest_partial_oct25.png').convert('RGB')
        ImageDraw.Draw(im).rectangle((1040,267,1185,301),fill='black')
        e=ObjectiveReader().read(im);self.assertTrue(e.errors);self.assertNotIn('objectives',e.values)

    def test_hold_reconciliation_persistence_failure_rolls_back(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_held={'DIMENSION MISSION'}
        w.objective_inspection=Mock(done=True,period=gui.reset_period(now));w.objective_plan=MissionPlan(0,False,0)
        with patch.object(w,'persist_completed_missions',return_value=False):self.assertFalse(w.reconcile_held_dimension_objectives())
        self.assertIn('DIMENSION MISSION',w.queue_held);self.assertNotIn('DIMENSION MISSION',w.queue_engine.completed);self.assertFalse(w.queue_engine.running)

if __name__=='__main__':unittest.main()
