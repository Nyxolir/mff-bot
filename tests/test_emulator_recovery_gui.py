import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from datetime import datetime,timedelta,timezone
from io import BytesIO
from unittest.mock import Mock,patch
import unittest
from PIL import Image
from PyQt5.QtWidgets import QApplication
from tests import test_queue_gui
from lib.gui.widgets import modern_main as gui
from lib.gui.widgets import emulator_recovery
from lib.bluestacks_recovery import RecoveredEmulator
from lib.screen_reader import ScreenEvidence
from lib.objectives import MissionPlan

class EmulatorRecoveryGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        test_queue_gui.QueueGuiTests.setUp(self)
        p=patch.object(gui.QtCore.QTimer,'singleShot');p.start();self.patches.append(p)
        self.now=self.prepare_sweep();self.window.adb_backend=Mock(connected=True)
    def tearDown(self):
        self.window.emulator_task=None;self.window.frame_task=None
        test_queue_gui.QueueGuiTests.tearDown(self)
    prepare_sweep=test_queue_gui.QueueGuiTests.prepare_sweep
    clear_gbr=test_queue_gui.QueueGuiTests.clear_gbr
    scan_fixture=test_queue_gui.QueueGuiTests.scan_fixture

    def result(self,launched=True,game_opened=True):
        im=Image.new('RGB',(1280,720),(20,20,20));raw=BytesIO();im.save(raw,format='PNG')
        return RecoveredEmulator((im,raw.getvalue()),datetime.now(timezone.utc),44,launched,game_opened)

    def test_device_loss_saves_pending_and_starts_one_worker_without_generic_recovery(self):
        w=self.window;pending=(gui.reset_period(self.now),'DIMENSION MISSION',5);w.queue_engine.pending=pending
        w.contribution_followup=True;w.contribution_before=(60,60);w.contribution_acquire_submitted=True
        completed=set(w.queue_engine.completed)
        with patch.object(emulator_recovery,'EmulatorRecoveryTask') as task,patch.object(w,'recover_stuck_queue') as recover,patch.object(w,'restart_stuck_game') as restart:
            w.adb_frame_failed(w.adb_backend,"error: device 'emulator-5554' not found")
            w.adb_frame_failed(w.adb_backend,'device not found')
            task.assert_called_once();task.return_value.start.assert_called_once();recover.assert_not_called();restart.assert_not_called()
        w.persist_pending_clear.assert_called();self.assertEqual(w.queue_engine.pending,pending);self.assertEqual(w.queue_engine.completed,completed)
        self.assertTrue(w.contribution_followup);self.assertEqual(w.contribution_before,(60,60));self.assertTrue(w.contribution_acquire_submitted)
        self.assertTrue(w.queue_engine.running)

    def test_unsaved_submission_prevents_relaunch(self):
        w=self.window;w.queue_engine.pending=(gui.reset_period(self.now),'CUTTING CABLE',3)
        with patch.object(w,'persist_pending_clear',return_value=False),patch.object(emulator_recovery,'EmulatorRecoveryTask') as task:
            self.assertTrue(w.try_emulator_recovery('device not found'));task.assert_not_called()
        self.assertFalse(w.queue_engine.running);self.assertIsNotNone(w.queue_engine.pending)

    def test_running_recovery_blocks_stale_ocr_scans_and_queue_actions(self):
        w=self.window;w.emulator_task=Mock()
        with patch.object(gui,'click_game_point') as click,patch.object(gui,'BackgroundFrameTask') as frame:
            w.show_evidence(ScreenEvidence('android_home',{'launch_point':(539,204)}),self.now,True)
            gui.ModernMainWindow.scan_live(w);w.request_adb_frame();w.queue_tick()
            click.assert_not_called();frame.assert_not_called()

    def test_stopped_queue_and_unrelated_capture_failures_do_not_launch_emulator(self):
        w=self.window
        with patch.object(emulator_recovery,'EmulatorRecoveryTask') as task:
            self.assertTrue(w.try_emulator_recovery('Blank Android frame'))
            w.queue_engine.stop();self.assertFalse(w.try_emulator_recovery('device not found'));task.assert_not_called()

    def test_actual_decoder_hint_does_not_exhaust_budget_and_finished_batch_reconciles(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_target='TEAM BATTLE ARENA'
        pending=(gui.reset_period(now),w.queue_target,5);w.queue_engine.pending=pending;w.arena_started=now
        w.queues[0]=[{'mode':m,'enabled':True} for m in ('TEAM BATTLE ARENA','CUTTING CABLE')]
        w.emulator_attempts=[now-timedelta(minutes=2),now-timedelta(minutes=1)]
        with patch.object(emulator_recovery,'EmulatorRecoveryTask') as worker,patch.object(w,'restart_stuck_game') as restart:
            for _ in range(8):w.adb_frame_failed(w.adb_backend,'Background screenshot incomplete after three captures; reconnect')
            worker.assert_not_called();restart.assert_not_called()
        self.assertTrue(w.queue_engine.running);self.assertEqual(w.queue_engine.pending,pending);self.assertEqual(len(w.emulator_attempts),2)
        e,observed,_=self.scan_fixture('team_arena_capture_stall_oct26.png',reader_kind='arena')
        self.assertEqual(e.screen,'team_arena_ended');self.assertEqual(e.values['runs'],5)
        w.queue_observation=(e,observed)
        with patch.object(gui,'click_game_point') as click:w.advance_queue();click.assert_called_once_with(11,640,603,guard=unittest.mock.ANY)
        self.assertIsNone(w.queue_engine.pending);self.assertIn('TEAM BATTLE ARENA',w.queue_engine.completed)
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            w.queue_arena(ScreenEvidence('arena_result',{'mode':'TEAM BATTLE ARENA','point':(900,669)}),observed)
        self.assertIsNone(w.queue_target);w.queue_wake=None;w.queue_tick();self.assertEqual(w.queue_target,'CUTTING CABLE')

    def test_continuously_bad_frames_escalate_only_after_a_minute_and_save_pending(self):
        w=self.window;pending=(gui.reset_period(self.now),'TEAM BATTLE ARENA',5);w.queue_engine.pending=pending
        w.emulator_capture_failed_since=datetime.now(timezone.utc)-timedelta(seconds=61)
        with patch.object(emulator_recovery,'EmulatorRecoveryTask') as worker:
            self.assertTrue(w.try_emulator_recovery('Background screenshot incomplete after three captures; reconnect'))
            worker.assert_called_once();worker.return_value.start.assert_called_once()
        w.persist_pending_clear.assert_called();self.assertEqual(w.queue_engine.pending,pending)

    def test_fresh_frame_clears_continuous_capture_failure_clock(self):
        w=self.window;w.emulator_capture_failed_since=self.now-timedelta(seconds=59)
        result=self.result(False,False);w.adb_frame_ready(w.adb_backend,*result.frame,result.observed)
        self.assertIsNone(w.emulator_capture_failed_since)

    def test_recovery_is_limited_to_two_per_hour_without_losing_pending(self):
        w=self.window;w.queue_engine.pending=(gui.reset_period(self.now),'CUTTING CABLE',3)
        w.emulator_attempts=[self.now-timedelta(minutes=1),self.now]
        with patch.object(emulator_recovery,'EmulatorRecoveryTask') as task:
            self.assertTrue(w.try_emulator_recovery('device offline'));task.assert_not_called()
        self.assertFalse(w.queue_engine.running);self.assertIsNotNone(w.queue_engine.pending)

    def test_success_refreshes_frame_handle_and_requirements_without_erasing_completions(self):
        w=self.window;w.emulator_saved_phase='sweep';w.queue_engine.completed.add('ALLIANCE BATTLE')
        w.epic_preparation=object();w.emulator_recovered(w.adb_backend,self.result())
        self.assertEqual(w.handle,44);self.assertTrue(w.objective_refresh_due);self.assertIsNone(w.epic_preparation)
        self.assertEqual(w.queue_phase,'recover_home');self.assertTrue(w.queue_recovering)
        self.assertIn('ALLIANCE BATTLE',w.queue_engine.completed);self.assertIsNotNone(w.adb_frame)

    def test_stop_while_booting_prevents_automatic_queue_resume(self):
        w=self.window;w.queue_engine.stop();w.emulator_saved_phase='sweep'
        with patch.object(w,'adb_frame_ready') as ready:
            w.emulator_recovered(w.adb_backend,self.result());ready.assert_not_called()
        self.assertFalse(w.queue_engine.running)

    def test_interrupted_submission_home_is_neither_completion_nor_permission_to_replay(self):
        w=self.window;pending=(gui.reset_period(self.now),'TEAM BATTLE ARENA',5);w.queue_engine.pending=pending
        w.emulator_saved_phase='arena';w.emulator_recovered(w.adb_backend,self.result())
        now=datetime.now(timezone.utc)
        with patch.object(gui,'click_game_point') as click:
            w.show_evidence(ScreenEvidence('game_home',{'home_controls_verified':True}),now,True);click.assert_not_called()
        self.assertFalse(w.queue_engine.running);self.assertEqual(w.queue_engine.pending,pending)
        self.assertNotIn('TEAM BATTLE ARENA',w.queue_engine.completed);w.persist_pending_clear.assert_called()

    def test_precrash_image_is_rejected_even_if_within_the_normal_thirty_seconds(self):
        w=self.window;w.emulator_saved_phase='arena';w.queue_engine.pending=(gui.reset_period(self.now),'TEAM BATTLE ARENA',5)
        w.emulator_recovered(w.adb_backend,self.result())
        with patch.object(gui,'click_game_point') as click:
            w.show_evidence(ScreenEvidence('game_home',{'home_controls_verified':True}),self.now,True);click.assert_not_called()
        self.assertTrue(w.queue_engine.running);self.assertIsNotNone(w.queue_engine.pending)

    def test_launcher_during_game_startup_waits_without_second_launch_or_losing_submission(self):
        w=self.window;w.emulator_saved_phase='arena';pending=(gui.reset_period(self.now),'TEAM BATTLE ARENA',5)
        w.queue_engine.pending=pending;w.emulator_recovered(w.adb_backend,self.result())
        with patch.object(gui,'click_game_point') as click:
            w.show_evidence(ScreenEvidence('android_home',{'launcher_verified':True,'launch_point':(539,204)}),datetime.now(timezone.utc),True)
            click.assert_not_called()
        self.assertTrue(w.queue_engine.running);self.assertEqual(w.queue_engine.pending,pending)

    def test_verified_repeat_end_can_still_reconcile_its_lobby_after_relaunch(self):
        w=self.window;w.emulator_pending_interrupted=True;w.arena_repeat_finished=True
        w.queue_engine.pending=(gui.reset_period(self.now),'TEAM BATTLE ARENA',5)
        self.assertFalse(w.interrupted_emulator_home(ScreenEvidence('game_home',{'home_controls_verified':True}),self.now))
        self.assertTrue(w.queue_engine.running);self.assertIsNotNone(w.queue_engine.pending)

    def test_known_dimension_claim_survives_relaunch_and_actual_receipt_verification(self):
        w=self.window;w.queue_target='DIMENSION MISSION';w.objective_plan=MissionPlan(5,True,0)
        w.queue_engine.pending=(gui.reset_period(self.now),w.queue_target,5)
        w.contribution_followup=True;w.contribution_submitted=True;w.contribution_before=(60,60);w.contribution_acquire_submitted=True
        w.emulator_saved_phase='dimension_claim';w.emulator_recovered(w.adb_backend,self.result())
        self.assertFalse(w.emulator_pending_interrupted);self.assertEqual(w.queue_phase,'dimension_claim')
        e,stamp,_=self.scan_fixture('dimension_gold_receipt_oct25.png',reader_kind='sweep')
        with patch.object(gui,'click_game_point') as click:
            w.queue_observation=(e,stamp);w.advance_queue();self.assertEqual(click.call_args.args,(44,640,565))
        self.assertIsNotNone(w.queue_engine.pending)
        w.queue_observation=(ScreenEvidence('dimension_lobby',{'mode':'DIMENSION MISSION','contribution':(0,60)}),datetime.now(timezone.utc));w.advance_queue()
        self.assertIsNone(w.queue_engine.pending);self.assertIn('DIMENSION MISSION',w.queue_engine.completed)

    def test_verified_result_after_reconnection_releases_pending_then_selects_next_task(self):
        w=self.window;w.queues[0]=[{'mode':m,'enabled':True} for m in ('DIMENSION MISSION','CUTTING CABLE')]
        w.queue_target='DIMENSION MISSION';w.objective_plan=MissionPlan(5,False,0)
        w.queue_engine.pending=(gui.reset_period(self.now),w.queue_target,5)
        w.emulator_saved_phase='sweep_result';w.emulator_recovered(w.adb_backend,self.result())
        e,stamp,_=self.scan_fixture('dimension_five_sweep_result_oct25.png',reader_kind='sweep')
        with patch('lib.queue_input.execute_sweep_control') as execute:
            w.show_evidence(e,stamp,True);w.advance_queue();self.assertEqual(execute.call_args.args[2],'close_result')
        self.assertIsNone(w.queue_engine.pending);self.assertIn('DIMENSION MISSION',w.queue_engine.completed)
        w.objective_inspection=Mock(done=True,period=gui.reset_period(self.now),plan=MissionPlan(0,False,0),max_level_passes=set());w.finish_objectives()
        w.queue_wake=None;w.queue_tick();self.assertEqual(w.queue_target,'CUTTING CABLE')

if __name__=='__main__':unittest.main()
