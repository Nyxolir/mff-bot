import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from datetime import datetime,timedelta,timezone
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch,Mock
from PyQt5.QtWidgets import QApplication
from lib.gui.widgets import modern_main as gui
from lib.screen_reader import ScreenEvidence
from lib.objectives import MissionPlan


class QueueGuiTests(unittest.TestCase):
    def test_closing_during_update_idle_scan_cancels_and_closes_after_scan(self):
        from lib.gui.widgets import app_update_controls as updates
        w=self.window;w.queue_engine.start(datetime.now(timezone.utc));w.update_candidate={'version':'0.1.99'}
        with patch.object(updates,'saved_update_blocker',return_value=None):w.update_tick()
        w.busy=True
        with patch.object(updates.QtCore.QTimer,'singleShot') as retry:
            self.assertFalse(w.update_close_allowed());retry.assert_called_once()
        self.assertFalse(w.queue_engine.running);self.assertFalse(w.update_quiescing)
        w.busy=False;self.assertTrue(w.update_close_allowed())

    def test_closing_during_an_update_download_stops_queue_before_waiting_for_worker(self):
        from lib.gui.widgets import app_update_controls as updates
        w=self.window;w.queue_engine.start(datetime.now(timezone.utc));worker=Mock();worker.isRunning.return_value=True;w.update_worker=worker
        with patch.object(updates.QtCore.QTimer,'singleShot'):
            self.assertFalse(w.update_close_allowed())
        self.assertFalse(w.queue_engine.running);worker.requestInterruption.assert_called_once();self.assertTrue(w.update_closing)
        worker.isRunning.return_value=False

    def test_cancel_update_button_stops_previously_running_queue(self):
        from lib.gui.widgets import app_update_controls as updates
        w=self.window;w.queue_engine.start(datetime.now(timezone.utc));w.update_candidate={'version':'0.1.99'}
        with patch.object(updates,'saved_update_blocker',return_value=None):w.update_tick()
        self.assertIn('Stop Queue',w.run_queue_button.text());w.toggle_queue()
        self.assertFalse(w.update_quiescing);self.assertFalse(w.queue_engine.running)

    def test_app_update_waits_for_active_and_saved_submissions(self):
        from lib.gui.widgets import app_update_controls as updates
        w=self.window;w.update_candidate={'version':'0.1.99'}
        pending=(gui.reset_period(datetime.now(timezone.utc)),'DIMENSION MISSION',10)
        with patch.object(updates,'saved_update_blocker',return_value=None),patch.object(updates,'prepare_handoff') as prepare:
            w.queue_engine.pending=pending;w.update_tick();self.assertFalse(w.update_quiescing)
            w.queue_engine.pending=None;w.world_event_state.started=True;w.update_tick();self.assertFalse(w.update_quiescing)
            w.world_event_state.started=False;w.queue_target='STORY ULTIMATE';w.update_tick();self.assertFalse(w.update_quiescing)
            w.queue_target=None;w.queue_held={'TIMELINE BATTLE'};w.update_tick();self.assertFalse(w.update_quiescing)
            w.queue_held=set()
            with patch.object(updates,'saved_update_blocker',return_value='saved pending outcome'):
                w.update_tick();self.assertFalse(w.update_quiescing)
            prepare.assert_not_called()

    def test_app_update_quiesces_then_verifies_idle_without_game_input_and_preserves_queue(self):
        from lib.gui.widgets import app_update_controls as updates
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.queue_index=2;w.update_candidate={'version':'0.1.99'}
        w._save.return_value=True
        directory=Path(self.log_directory.name);path=directory/'handoff.json'
        plan={'token':'a'*32,'version':'0.1.99','resume':True}
        with patch.object(updates,'saved_update_blocker',return_value=None),patch.object(updates,'prepare_handoff',return_value=(path,directory/'helper.exe',plan)) as prepare,patch.object(updates.subprocess,'Popen'),patch.object(gui,'click_game_point') as click,patch.object(w,'close') as close:
            w.update_tick();self.assertTrue(w.update_quiescing);w.scan_live.assert_called_once()
            w.queue_tick();w.show_evidence(ScreenEvidence('game_home'),now,True);w.advance_queue();click.assert_not_called()
            w.update_tick()
            self.assertEqual(prepare.call_args.args[1:3],(True,True));self.assertEqual(prepare.call_args.kwargs['queue_index'],2)
            updates.atomic_json(directory/'ready.json',{'token':plan['token'],'stage':'waiting_for_app'})
            w.update_tick();close.assert_called_once();self.assertTrue(w.update_committing)
            self.assertEqual(__import__('json').loads((directory/'commit.json').read_text())['token'],plan['token'])
            click.assert_not_called()

    def test_app_update_save_failure_keeps_current_app_and_queue_running(self):
        from lib.gui.widgets import app_update_controls as updates
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.handle=None;w.update_candidate={'version':'0.1.99'};w._save.return_value=False
        w.update_config_path=Path(self.log_directory.name)/'updates.json'
        with patch.object(updates,'saved_update_blocker',return_value=None),patch.object(updates,'prepare_handoff') as prepare:
            w.update_tick();w.update_tick();prepare.assert_not_called()
        self.assertFalse(w.update_quiescing);self.assertTrue(w.queue_engine.running)
        self.assertEqual(w.update_config['failed_version'],'0.1.99')

    def test_app_update_user_stop_cancels_handoff_and_cannot_resume_queue(self):
        from lib.gui.widgets import app_update_controls as updates
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.update_candidate={'version':'0.1.99'}
        with patch.object(updates,'saved_update_blocker',return_value=None):w.update_tick()
        self.assertTrue(w.update_quiescing);w.stop_queue()
        self.assertFalse(w.update_quiescing);self.assertIsNone(w.update_candidate);self.assertFalse(w.queue_engine.running)

    def test_app_update_unknown_or_saved_screen_cannot_launch_helper(self):
        from lib.gui.widgets import app_update_controls as updates
        w=self.window;now=datetime.now(timezone.utc);w.update_candidate={'version':'0.1.99'}
        with patch.object(updates,'saved_update_blocker',return_value=None),patch.object(updates,'prepare_handoff') as prepare:
            w.update_tick();w.show_evidence(ScreenEvidence('unknown'),now,True);w.update_tick()
            prepare.assert_not_called();self.assertFalse(w.update_quiescing)

    def test_world_event_zero_recheck_finishes_before_startup_board_preflight(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.start_world_event(now)
        w.enable_board_preflight=True;w.board_check_due=True;w.board_check_active=False
        state=w.world_event_state;state.pending=True;state.started=False;state.before=1
        state.zero_observations=[(0,now-timedelta(seconds=5))]
        w.world_event_waiting=(('we_home','game_home'),now);w.queue_wake=None
        w.queue_tick()
        self.assertFalse(w.board_check_active);self.assertTrue(w.board_check_due)
        self.assertTrue(w.world_event_active);self.assertEqual(w.queue_phase,'world_event')
        self.assertEqual(w.world_event_waiting,(('we_home','game_home'),now))
        self.assertEqual(len(state.zero_observations),1);self.assertTrue(state.pending)
        w.scan_live.assert_called_once()

    def test_world_event_delayed_start_frame_never_repeats_or_recovers(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.start_world_event(now)
        state=w.world_event_state;state.pending=True;state.before=1
        with patch('lib.gui.widgets.world_event_controls.click_game_point') as click:
            e=ScreenEvidence('we_start',{'point':(1034,674)})
            w.queue_world_event(e,now);w.queue_world_event(e,now)
            self.assertEqual(click.call_count,1)
        self.assertTrue(state.pending);self.assertTrue(state.started);self.assertTrue(w.world_event_active)
        self.assertFalse(w.queue_recovering);self.assertTrue(w.queue_engine.running)

    def test_world_event_orphaned_start_reconciles_live_zero_then_schedules_next_task(self):
        from lib.gui.widgets import world_event_controls as controls
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.start_world_event(now)
        state=w.world_event_state;state.pending=True;state.started=True;state.before=1
        w.queues[0]=[{'mode':'WORLD EVENT','enabled':True},{'mode':'CUTTING CABLE','enabled':True}]
        e,_,_=self.scan_fixture('world_event_zero_latched_oct31.png',reader_kind='world_event')
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return cls.current
        Clock.current=now
        with patch.object(controls,'datetime',Clock),patch.object(gui,'datetime',Clock),patch('lib.gui.widgets.world_event_controls.click_game_point') as click:
            for second in range(0,61,5):
                stamp=now+timedelta(seconds=second);Clock.current=stamp
                w.show_evidence(e,stamp,True);w.advance_queue()
                if second<60:click.assert_not_called();self.assertTrue(state.started)
            self.assertFalse(state.started);self.assertTrue(state.pending);self.assertFalse(state.done)
            self.assertEqual(click.call_args.args,(11,1185,36))
            for second in (65,75):
                stamp=now+timedelta(seconds=second);Clock.current=stamp
                w.queue_world_event(ScreenEvidence('we_home',{'event_point':(1040,510),'battle_tab':True}),stamp)
                stamp+=timedelta(seconds=5);Clock.current=stamp;w.queue_world_event(e,stamp)
        self.assertFalse(w.world_event_active);self.assertFalse(state.pending);self.assertTrue(state.done)
        self.assertEqual(len(state.completion_proof['observations']),3)
        self.assertTrue(state.valid_completion_proof(state.completion_proof,now+timedelta(seconds=85)))
        self.clear_gbr(now);w.queue_wake=None;w.queue_tick()
        self.assertEqual(w.queue_target,'CUTTING CABLE')

    def test_world_event_reconciliation_save_failure_preserves_started_without_input(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.start_world_event(now)
        state=w.world_event_state;state.pending=True;state.started=True;state.before=1
        e,_,_=self.scan_fixture('world_event_zero_latched_oct31.png',reader_kind='world_event')
        state.lobby_reconciliation=((0,2,0,True),now-timedelta(seconds=60),now-timedelta(seconds=5),12)
        with patch.object(state,'save',side_effect=OSError('disk full')),patch('lib.gui.widgets.world_event_controls.click_game_point') as click:
            w.queue_world_event(e,now);click.assert_not_called()
        self.assertFalse(w.queue_engine.running);self.assertTrue(state.started);self.assertTrue(state.pending);self.assertFalse(state.done)

    def test_world_event_completion_save_failure_restores_submission_and_stops(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.start_world_event(now)
        state=w.world_event_state;state.pending=True;state.before=1
        state.zero_observations=[(0,now-timedelta(seconds=20)),(1,now-timedelta(seconds=10))];w.world_event_visit=2
        e,_,_=self.scan_fixture('world_event_zero_latched_oct31.png',reader_kind='world_event')
        with patch.object(state,'save',side_effect=OSError('disk full')),patch('lib.gui.widgets.world_event_controls.click_game_point') as click:
            w.queue_world_event(e,now);click.assert_not_called()
        self.assertFalse(w.queue_engine.running);self.assertTrue(state.pending);self.assertFalse(state.done)

    def test_world_event_battle_or_wrong_screen_discards_partial_lobby_reconciliation(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.start_world_event(now)
        state=w.world_event_state;state.pending=True;state.started=True;state.before=1
        for evidence in (ScreenEvidence('we_battle',{'auto_on':True}),ScreenEvidence('otherworld',{'entries':(0,2)})):
            state.lobby_reconciliation=((0,2,0,True),now-timedelta(seconds=55),now,12)
            with patch('lib.gui.widgets.world_event_controls.click_game_point') as click:
                w.queue_world_event(evidence,now);click.assert_not_called()
            self.assertIsNone(state.lobby_reconciliation);self.assertTrue(state.pending);self.assertTrue(state.started);self.assertFalse(state.done)
            if not w.queue_engine.running:w.queue_engine.start(now);w.start_world_event(now)

    def test_world_event_submission_blocks_generic_restart_and_recovery(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.world_event_state.pending=True;w.world_event_state.started=True;w.world_event_state.before=1
        w.adb_backend=Mock()
        w.restart_stuck_game();w.adb_backend.restart_game.assert_not_called()
        self.assertTrue(w.world_event_state.pending);self.assertFalse(w.queue_engine.running)
        w.queue_engine.start(now);w.recover_stuck_queue('unrecognised')
        self.assertTrue(w.world_event_state.started);self.assertFalse(w.queue_engine.running);self.assertFalse(w.queue_recovering)

    def test_live_max_level_pass_skips_to_next_source_and_keeps_dimension_plan(self):
        from lib.objectives import parse_objectives
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        i=gui.ObjectiveInspection(now);i.phase='benefits';i.daily=parse_objectives('Daily Challenges','[DIMENSION MISSION] Clear 1 Stage 0/1')
        i.quest_present=True;i.quest=parse_objectives('Event Quest','[DIMENSION MISSION] Clear 10 Stages 0/10')
        title='Emblem Upgrade Special Pass |';benefits=ScreenEvidence('benefit_list',{'events':[{'name':title,'point':(630,438)}]})
        i.observe(benefits,now);w.objective_inspection=i;w.objective_active=True
        e,observed,live=self.scan_fixture('special_pass_max_level_oct27.png',reader_kind='objectives')
        with patch.object(gui,'click_game_point') as click,patch.object(gui.QtCore.QTimer,'singleShot'):
            w.show_evidence(e,observed,live);w.advance_objectives()
            self.assertEqual(click.call_args.args,(11,1185,36));self.assertEqual(i.phase,'benefits')
            w.objective_waiting=None;w.show_evidence(benefits,datetime.now(timezone.utc),True);w.advance_objectives()
        self.assertFalse(w.objective_active);self.assertEqual(w.objective_plan.dimension_clears,10)
        self.assertEqual(i.max_level_passes,{title});self.assertFalse(w.queue_engine.completed)
        self.assertIsNone(w.queue_engine.pending);self.assertTrue(w.queue_engine.running)

    def test_network_ok_recovery_keeps_pending_and_does_not_repeat_same_frame(self):
        from lib.trivia_session import TriviaSession
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        pending=(gui.reset_period(now),'SINISTER SCHEMES',2);w.queue_engine.pending=pending
        w.trivia_active=True;w.trivia_session=TriviaSession(now);w.trivia_session.pending='unverified answer'
        e,observed,live=self.scan_fixture('network_retry_notice_oct27.png',reader_kind='trivia')
        self.assertEqual(e.screen,'network_retry_notice')
        with patch.object(gui,'click_game_point') as click,patch.object(gui.QtCore.QTimer,'singleShot'):
            w.show_evidence(e,observed,live)
            self.assertEqual(click.call_args.args,(11,741,538));self.assertTrue(click.call_args.kwargs['guard']())
            self.assertIsNone(w.trivia_observation);self.assertTrue(w.emulator_pending_interrupted)
            w.show_evidence(e,observed,live);self.assertEqual(click.call_count,1)
        self.assertEqual(w.queue_engine.pending,pending);self.assertEqual(w.trivia_session.pending,'unverified answer')
        self.assertFalse(w.queue_engine.completed);self.assertFalse(w.trivia_session.done)

    def test_network_retry_rejects_stale_saved_idle_and_unverified_notices(self):
        w=self.window;e,now,_=self.scan_fixture('network_retry_notice_oct27.png')
        with patch.object(gui,'click_game_point') as click:
            w.show_evidence(e,now,True);click.assert_not_called()
            w.trivia_active=True
            w.show_evidence(e,now-timedelta(seconds=31),True);click.assert_not_called()
            w.show_evidence(e,now,False);click.assert_not_called()
            w.show_evidence(ScreenEvidence('network_retry_notice'),now,True);click.assert_not_called()

    def test_network_retry_exhaustion_stops_without_clearing_submission(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        pending=(gui.reset_period(now),'SINISTER SCHEMES',2);w.queue_engine.pending=pending
        w.network_retry_attempts=[now-timedelta(seconds=n) for n in (90,60,30)]
        e,observed,live=self.scan_fixture('network_retry_notice_oct27.png')
        with patch.object(gui,'click_game_point') as click:
            w.show_evidence(e,observed,live);click.assert_not_called()
        self.assertFalse(w.queue_engine.running);self.assertEqual(w.queue_engine.pending,pending)
        self.assertFalse(w.queue_engine.completed)

    def test_notification_drawer_is_dismissed_before_all_specialized_readers(self):
        for kind in ('trivia','objectives','converging','arena','story','sweep','daily_board_check'):
            with self.subTest(kind=kind):
                e,_,_=self.scan_fixture('trivia_notification_panel_oct27.png',reader_kind=kind)
                self.assertEqual(e.screen,'quest_notification_panel');self.assertFalse(e.errors)

    def test_notification_dismissal_preserves_pending_answer_and_submitted_batch(self):
        from lib.trivia_session import TriviaSession
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        pending=(gui.reset_period(now),'SINISTER SCHEMES',2);w.queue_engine.pending=pending
        w.trivia_active=True;w.trivia_session=TriviaSession(now);w.trivia_session.pending='unverified answer'
        e,observed,live=self.scan_fixture('trivia_notification_panel_oct27.png',reader_kind='trivia')
        with patch.object(gui,'click_game_point') as click,patch.object(gui.QtCore.QTimer,'singleShot'):
            w.show_evidence(e,observed,live)
            self.assertEqual(click.call_args.args,(11,1066,36));self.assertTrue(click.call_args.kwargs['guard']())
            self.assertIsNone(w.trivia_observation);self.assertIsNone(w.queue_observation)
            w.show_evidence(e,observed,live);self.assertEqual(click.call_count,1)
        self.assertEqual(w.queue_engine.pending,pending);self.assertEqual(w.trivia_session.pending,'unverified answer')
        self.assertFalse(w.queue_engine.completed);self.assertFalse(w.trivia_session.done)

    def test_notification_dismissal_rejects_saved_stale_and_idle_frames(self):
        w=self.window;e,now,_=self.scan_fixture('trivia_notification_panel_oct27.png',reader_kind='trivia')
        with patch.object(gui,'click_game_point') as click:
            w.show_evidence(e,now,True);click.assert_not_called()
            w.trivia_active=True
            w.show_evidence(e,now-timedelta(seconds=31),True);click.assert_not_called()
            w.show_evidence(e,now,False);click.assert_not_called()

    def test_reported_ticket_crop_failure_can_clear_and_verify_result_using_boost_only(self):
        w=self.window;now=self.prepare_sweep();w.queue_target='SINISTER SCHEMES';w.queue_remaining=2
        w.queues[0]=[{'mode':m,'enabled':True} for m in ('SINISTER SCHEMES','RISE OF THE PHOENIX')]
        w.epic_preparation=(ScreenEvidence('epic_preparation',{'mode':w.queue_target,'remaining':2,
            'boost_unit':4,'preparation_verified':True}),now,w.queue_engine.generation)
        e,observed,_=self.scan_fixture('epic_ticket_recurrence_oct25.png',reader_kind='sweep')
        self.assertFalse(e.errors);self.assertNotIn('tickets_available',e.text)
        with patch('lib.queue_input.execute_sweep_control') as execute:
            w.queue_read_sweep(e,observed);self.assertEqual(execute.call_args.args[2],'clear_batch')
        self.assertEqual(w.queue_engine.pending,(gui.reset_period(now),'SINISTER SCHEMES',2))
        result,observed,_=self.scan_fixture('epic_sinister_result_boost_only_oct25.png',reader_kind='sweep')
        with patch('lib.queue_input.execute_sweep_control') as execute:
            w.queue_read_sweep(result,observed);self.assertEqual(execute.call_args.args[2],'close_result')
        self.assertIn('SINISTER SCHEMES',w.queue_engine.completed);self.assertIsNone(w.queue_engine.pending)
        w.queue_wake=None;w.queue_tick();self.assertEqual(w.queue_target,'RISE OF THE PHOENIX')

    def test_dimension_live_event_quest_count_is_derived_and_merged_with_contribution(self):
        from lib.objective_inspection import ObjectiveInspection
        from lib.objectives import parse_objectives
        e,now,live=self.scan_fixture('dimension_event_quest_ten_oct25.png',reader_kind='objectives')
        self.assertTrue(live);self.assertFalse(e.errors);self.assertEqual(e.screen,'event_quest_objectives')
        self.assertEqual([(r.kind,r.done,r.total) for r in e.values['objectives']],[('dimension',0,10)])
        i=ObjectiveInspection(now);i.daily=parse_objectives('Daily Challenges','[DIMENSION MISSION] Acquire Contribution Reward 0/1')
        i.phase='quest_home';i.observe(ScreenEvidence('game_home',{'event_quest_point':(1040,507)}),now)
        i.observe(e,now);i.observe(e,now);i.observe(ScreenEvidence('benefit_list',{'events':[]}),now)
        self.assertTrue(i.done);self.assertEqual(i.plan,MissionPlan(10,True,0))

    def test_dimension_adb_sweep_costs_scan_and_exact_ten_selection(self):
        w=self.window;now=self.prepare_sweep();w.queues[0].append({'mode':'DIMENSION MISSION','enabled':True})
        w.objective_plan=MissionPlan(10,True,0);w.queue_target='DIMENSION MISSION';w.queue_remaining=10
        e,observed,live=self.scan_fixture('dimension_sweep_adb_oct25.png',reader_kind='sweep')
        self.assertTrue(live);self.assertEqual(e.screen,'sweep');self.assertFalse(e.errors)
        self.assertEqual((e.values['selected'],e.values['boost_total']),(1,4))
        with patch('lib.queue_input.execute_sweep_control') as execute:
            w.queue_read_sweep(e,observed);self.assertEqual(execute.call_args.args[2],'increment')
        self.assertIsNone(w.queue_engine.pending)

    def test_dimension_ignores_ticket_icon_but_requires_boost_notice(self):
        from PIL import Image
        from lib.sweep_reader import SweepReader
        source=Image.open(Path(__file__).parent/'fixtures/dimension_sweep_adb_oct25.png').convert('RGB')
        for box in ((430,380,485,437),(440,311,845,352)):
            image=source.copy();image.paste((0,0,0),box)
            e=SweepReader().read(image)
            if box[0]==440:self.assertTrue(e.errors);self.assertNotIn('sweep_verified',e.values)
            else:self.assertFalse(e.errors);self.assertTrue(e.values['sweep_verified'])

    def test_dimension_multiple_clear_count_verifies_boost_total(self):
        e,_,_=self.scan_fixture('dimension_sweep_three_adb_oct25.png',reader_kind='sweep')
        self.assertFalse(e.errors);self.assertEqual(e.screen,'sweep')
        self.assertEqual((e.values['selected'],e.values['boost_total']),(3,12))

    def test_dimension_live_ten_result_routes_to_claim_and_surplus_progress_proves_one_claim(self):
        w=self.window;now=self.prepare_sweep();w.queue_target='DIMENSION MISSION'
        w.objective_plan=MissionPlan(10,True,0);w.queue_engine.pending=(gui.reset_period(now),'DIMENSION MISSION',10)
        e,observed,_=self.scan_fixture('dimension_result_ten_adb_oct25.png',reader_kind='sweep')
        self.assertFalse(e.errors);self.assertEqual((e.values['mode'],e.values['clears']),('DIMENSION MISSION',10))
        with patch('lib.queue_input.execute_sweep_control') as execute:
            w.queue_read_sweep(e,observed);self.assertEqual(execute.call_args.args[2],'close_result')
        self.assertEqual(w.queue_phase,'dimension_claim');self.assertTrue(w.contribution_followup)
        with patch.object(gui,'click_game_point') as click:
            w.queue_dimension_claim(ScreenEvidence('dimension_lobby',{'contribution':(120,60)}),now)
            w.queue_dimension_claim(ScreenEvidence('dimension_lobby',{'contribution':(120,60)}),now)
            self.assertEqual(click.call_count,1);self.assertIsNotNone(w.queue_engine.pending)
            w.queue_dimension_claim(ScreenEvidence('dimension_lobby',{'contribution':(60,60)}),now)
        self.assertIn('DIMENSION MISSION',w.queue_engine.completed);self.assertIsNone(w.queue_engine.pending)

    def test_dimension_claim_save_failure_leaves_ready_reward_without_input(self):
        w=self.window;now=self.prepare_sweep();w.queue_target='DIMENSION MISSION'
        pending=(gui.reset_period(now),'DIMENSION MISSION',10);w.queue_engine.pending=pending
        with patch.object(w,'persist_pending_clear',return_value=False),patch.object(gui,'click_game_point') as click:
            w.queue_dimension_claim(ScreenEvidence('dimension_lobby',{'contribution':(120,60)}),now);click.assert_not_called()
        self.assertFalse(w.queue_engine.running);self.assertEqual(w.queue_engine.pending,pending)

    def test_dimension_result_mismatched_count_or_mode_does_not_release_submission(self):
        w=self.window;now=self.prepare_sweep();w.queue_target='DIMENSION MISSION';w.objective_plan=MissionPlan(10,True,0)
        pending=(gui.reset_period(now),'DIMENSION MISSION',10);w.queue_engine.pending=pending
        with patch('lib.queue_input.execute_sweep_control') as execute:
            w.queue_read_sweep(ScreenEvidence('sweep_result',{'result_verified':True,'mode':'DIMENSION MISSION','clears':9}),now)
            w.queue_read_sweep(ScreenEvidence('sweep_result',{'result_verified':True,'mode':'CUTTING CABLE','clears':10}),now)
            execute.assert_not_called()
        self.assertEqual(w.queue_engine.pending,pending);self.assertNotIn('DIMENSION MISSION',w.queue_engine.completed)

    def test_dimension_claim_menu_overlay_is_read_before_the_underlying_board(self):
        w=self.window;now=self.prepare_sweep();w.queue_target='DIMENSION MISSION'
        pending=(gui.reset_period(now),'DIMENSION MISSION',10);w.queue_engine.pending=pending;w.contribution_followup=True
        e,observed,_=self.scan_fixture('dimension_claim_board_menu_oct25.png',reader_kind='sweep')
        self.assertEqual(e.screen,'navigation_menu');self.assertFalse(e.errors)
        with patch.object(w,'queue_send_point') as send:
            w.queue_dimension_claim(e,observed);self.assertEqual(send.call_args.args[0],(491,642))
        self.assertEqual(w.queue_engine.pending,pending);self.assertEqual(w.queue_phase,'dimension_claim')

    def test_dimension_actual_contribution_list_acquires_once_then_counter_drop_completes(self):
        w=self.window;now=self.prepare_sweep();w.queue_target='DIMENSION MISSION'
        w.objective_plan=MissionPlan(10,True,0);w.queue_engine.pending=(gui.reset_period(now),'DIMENSION MISSION',10)
        w.contribution_followup=True;w.contribution_submitted=True;w.contribution_before=(120,60)
        e,observed,_=self.scan_fixture('dimension_contribution_list_oct25.png',reader_kind='sweep')
        self.assertEqual(e.screen,'dimension_contribution');self.assertTrue(e.values['acquire_ready'])
        with patch.object(gui,'click_game_point') as click:
            w.queue_dimension_claim(e,observed);w.queue_dimension_claim(e,observed)
            self.assertEqual(click.call_count,1);self.assertEqual(click.call_args.args,(11,741,643))
        self.assertIsNotNone(w.queue_engine.pending);self.assertNotIn('DIMENSION MISSION',w.queue_engine.completed)
        w.queue_dimension_claim(ScreenEvidence('dimension_lobby',{'contribution':(0,60)}),now)
        self.assertIn('DIMENSION MISSION',w.queue_engine.completed);self.assertIsNone(w.queue_engine.pending)

    def test_dimension_contribution_acquire_save_failure_cannot_click(self):
        w=self.window;now=self.prepare_sweep();w.queue_engine.pending=(gui.reset_period(now),'DIMENSION MISSION',10)
        e,observed,_=self.scan_fixture('dimension_contribution_list_oct25.png',reader_kind='sweep')
        with patch.object(w,'persist_pending_clear',return_value=False),patch.object(gui,'click_game_point') as click:
            w.queue_dimension_claim(e,observed);click.assert_not_called()
        self.assertFalse(w.queue_engine.running);self.assertIsNotNone(w.queue_engine.pending)

    def test_dimension_actual_acquired_receipt_requires_submitted_claim_then_lobby_verification(self):
        w=self.window;now=self.prepare_sweep();w.queue_target='DIMENSION MISSION'
        pending=(gui.reset_period(now),'DIMENSION MISSION',10);w.queue_engine.pending=pending
        w.objective_plan=MissionPlan(10,True,0);w.contribution_followup=True;w.contribution_submitted=True;w.contribution_before=(120,60)
        e,observed,_=self.scan_fixture('dimension_contribution_receipt_oct25.png',reader_kind='sweep')
        self.assertFalse(e.errors);self.assertEqual(e.screen,'dimension_contribution_receipt')
        with patch.object(gui,'click_game_point') as click:
            w.queue_dimension_claim(e,observed);click.assert_not_called()
            w.contribution_acquire_submitted=True;w.queue_dimension_claim(e,observed)
            self.assertEqual(click.call_args.args,(11,640,537))
        self.assertEqual(w.queue_engine.pending,pending);self.assertNotIn('DIMENSION MISSION',w.queue_engine.completed)
        w.queue_dimension_claim(ScreenEvidence('dimension_lobby',{'contribution':(0,60)}),now)
        self.assertIsNone(w.queue_engine.pending);self.assertIn('DIMENSION MISSION',w.queue_engine.completed)

    def test_dimension_requirement_precedes_saved_epic_order_without_reordering_settings(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);self.clear_gbr(now)
        w.queues[0]=[{'mode':m,'enabled':True} for m in ('CUTTING CABLE','DIMENSION MISSION','ENDING THE STRYFE')]
        saved=[dict(row) for row in w.queues[0]];w.objective_plan=MissionPlan(10,True,1)
        self.assertEqual(w.eligible_modes(now),['DIMENSION MISSION'])
        w.queue_tick();self.assertEqual(w.queue_target,'DIMENSION MISSION');self.assertEqual(w.queue_phase,'dimension_nav')
        self.assertEqual(w.queues[0],saved)

    def test_dimension_deferral_and_held_outcome_keep_other_boosted_farming_blocked(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);self.clear_gbr(now)
        w.queues[0]=[{'mode':m,'enabled':True} for m in ('CUTTING CABLE','DIMENSION MISSION','STORY ULTIMATE','TIMELINE BATTLE')]
        w.objective_plan=MissionPlan(10,True,1);w.queue_deferred['DIMENSION MISSION']=now+timedelta(minutes=5)
        self.assertEqual(w.eligible_modes(now),['TIMELINE BATTLE'])
        w.queue_deferred.clear();w.queue_held={'DIMENSION MISSION'};w.queue_held_period=gui.reset_period(now)
        self.assertEqual(w.eligible_modes(now),['TIMELINE BATTLE'])
        w.queue_held.clear();w.queue_engine.completed.add('DIMENSION MISSION');w.objective_completed('DIMENSION MISSION')
        self.assertIn('CUTTING CABLE',w.eligible_modes(now));self.assertIn('STORY ULTIMATE',w.eligible_modes(now))

    def test_unread_or_stale_requirements_block_boosted_farming_and_refresh_before_free_work(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);self.clear_gbr(now)
        w.queues[0]=[{'mode':m,'enabled':True} for m in ('CUTTING CABLE','DIMENSION MISSION','TIMELINE BATTLE')]
        for plan,period,due in ((None,None,False),(MissionPlan(0,False,0),'old',False),(MissionPlan(5,True,0),gui.reset_period(now),True)):
            w.objective_plan=plan;w.objective_period=period;w.objective_refresh_due=due
            self.assertNotIn('CUTTING CABLE',w.eligible_modes(now))
            with patch.object(w,'check_objectives') as check:
                w.queue_tick();check.assert_called_once()
            self.assertIsNone(w.queue_target)

    def test_required_dimension_reselects_unsubmitted_epic_and_rejects_its_open_sweep(self):
        w=self.window;now=self.prepare_sweep();w.queues[0].append({'mode':'DIMENSION MISSION','enabled':True})
        w.objective_plan=MissionPlan(10,True,0);w.queue_phase='sweep'
        with patch('lib.queue_input.execute_sweep_control') as execute:
            w.queue_read_sweep(self.sweep_evidence(),now);execute.assert_not_called()
        self.assertIsNone(w.queue_engine.pending);self.assertIsNone(w.queue_target)
        w.queue_target='CUTTING CABLE';w.queue_wake=now+timedelta(minutes=5)
        w.queue_tick();self.assertEqual(w.queue_target,'DIMENSION MISSION')

    def test_dimension_priority_preserves_submitted_epic_then_selects_dimension(self):
        w=self.window;now=self.prepare_sweep();w.queues[0].append({'mode':'DIMENSION MISSION','enabled':True})
        w.objective_plan=MissionPlan(10,True,0);pending=(gui.reset_period(now),'CUTTING CABLE',3)
        w.queue_engine.pending=pending;w.queue_tick();self.assertEqual(w.queue_engine.pending,pending)
        with patch('lib.queue_input.execute_sweep_control'):
            w.queue_read_sweep(ScreenEvidence('sweep_result',{'mode':'CUTTING CABLE','clears':3,'result_verified':True}),now)
        self.assertIsNone(w.queue_engine.pending);w.queue_wake=None;w.queue_tick()
        self.assertEqual(w.queue_target,'DIMENSION MISSION')

    def test_dimension_ten_clear_batch_waits_for_full_forty_boost_and_reserves_priority(self):
        w=self.window;now=self.prepare_sweep();w.queues[0].append({'mode':'DIMENSION MISSION','enabled':True})
        w.objective_plan=MissionPlan(10,True,0);w.queue_target='DIMENSION MISSION';w.queue_remaining=10
        e=self.sweep_evidence(selected=10);e.values.update(mode='DIMENSION MISSION',energy_total=60,boost_total=40,ticket_total=10,boost_available=39)
        with patch('lib.queue_input.execute_sweep_control') as execute:
            w.queue_read_sweep(e,now)
            self.assertNotIn('clear_batch',[call.args[2] for call in execute.call_args_list])
        self.assertIsNone(w.queue_engine.pending);self.assertNotIn('CUTTING CABLE',w.eligible_modes(now))
        self.assertNotIn('STORY ULTIMATE',w.eligible_modes(now))

    def test_queue_start_requires_new_objective_inspection_despite_saved_same_day_plan(self):
        w=self.window;now=datetime.now(timezone.utc);self.clear_gbr(now)
        self.assertTrue(w.objective_plan_current(now))
        with patch.object(w,'queue_tick'):w.toggle_queue()
        self.assertTrue(w.objective_refresh_due);self.assertFalse(w.objective_plan_current(now))
        w.check_objectives();self.assertTrue(w.objective_active)

    def test_dimension_priority_status_explains_other_boosted_waits(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);self.clear_gbr(now)
        w.queues[0].append({'mode':'DIMENSION MISSION','enabled':True});w.objective_plan=MissionPlan(10,True,0)
        self.assertIn('10 clears',w.task_status('DIMENSION MISSION',now)[0])
        self.assertEqual(w.task_status('CUTTING CABLE',now)[0],'Waiting for required Dimension clears')

    def test_dimension_priority_blocks_dispatch_start_but_preserves_submitted_dispatch(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);self.clear_gbr(now)
        w.queues[0].append({'mode':'DIMENSION MISSION','enabled':True});w.objective_plan=MissionPlan(10,True,1)
        w.queue_target='DISPATCH 7-1'
        with patch.object(gui,'click_game_point') as click:
            w.queue_dispatch(ScreenEvidence('dispatch_7_1_setup'),now);click.assert_not_called()
        self.assertIsNone(w.queue_engine.pending);self.assertIsNone(w.queue_target)
        pending=(gui.reset_period(now),'DISPATCH 7-1',1);w.queue_engine.pending=pending
        with patch.object(gui,'click_game_point') as click:
            w.queue_dispatch(ScreenEvidence('dispatch_battle_auto',{'auto_on':True}),now);click.assert_not_called()
        self.assertEqual(w.queue_engine.pending,pending)

    def test_fresh_remaining_objectives_supersede_old_dimension_completion(self):
        from lib.objective_inspection import ObjectiveInspection
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.queue_engine.completed.add('DIMENSION MISSION');w.objective_inspection=ObjectiveInspection(now)
        w.objective_inspection.plan=MissionPlan(10,True,0);w.objective_active=True
        w.finish_objectives();self.assertNotIn('DIMENSION MISSION',w.queue_engine.completed)
        self.assertTrue(w.objective_plan_current(now));self.assertEqual(w.objective_plan.dimension_clears,10)

    def test_world_event_board_zero_and_missing_tail_never_clear_submitted_state(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        state=w.world_event_state;state.pending=True;state.started=False;state.before=2
        e=ScreenEvidence('content_board',{'tiles':[dict(mode='WORLD EVENT',remaining=0,completed=True)]})
        w.remember_board_completions(e,now)
        self.assertFalse(state.done);self.assertTrue(state.pending);self.assertEqual(state.before,2)
        w.start_daily_board_check(now);w.board_check_top=True
        with patch('lib.gui.widgets.daily_board_check.click_game_point'):
            w.queue_daily_board_check(ScreenEvidence('content_board',{'tiles':[],'completed_tail_verified':True,'incomplete_prefix_verified':True,'unfinished_modes':[]}),now)
        self.assertFalse(state.done);self.assertTrue(state.pending)

    def test_world_event_cached_zero_reopens_page_then_actual_two_entries_can_enter(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.start_world_event(now)
        zero,_,_=self.scan_fixture('world_event_zero_adb.png',reader_kind='world_event')
        actual,_,_=self.scan_fixture('world_event_refresh_oct25.png',reader_kind='world_event')
        with patch('lib.gui.widgets.world_event_controls.click_game_point') as click:
            w.queue_world_event(zero,now-timedelta(seconds=15))
            self.assertEqual(click.call_args.args,(11,1185,36));self.assertFalse(w.world_event_state.done)
            w.queue_world_event(ScreenEvidence('we_home',{'event_point':(1040,380),'battle_tab':True}),now-timedelta(seconds=10))
            self.assertEqual(click.call_args.args,(11,1040,380))
            w.queue_world_event(actual,now)
            self.assertEqual(click.call_args.args,(11,1040,674))
        self.assertFalse(w.world_event_state.done);self.assertEqual(w.world_event_state.zero_observations,[])
        self.assertEqual(w.world_event_waiting[0],('we_team',));self.assertFalse(w.world_event_state.pending)

    def test_world_event_requires_three_distinct_reopened_zero_visits_before_done(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.start_world_event(now)
        e,_,_=self.scan_fixture('world_event_zero_adb.png',reader_kind='world_event')
        state=w.world_event_state;state.pending=True;state.before=1
        with patch('lib.gui.widgets.world_event_controls.click_game_point') as click:
            for visit in range(3):
                stamp=now-timedelta(seconds=(2-visit)*10)
                w.queue_world_event(e,stamp)
                self.assertEqual(state.done,visit==2);self.assertEqual(state.pending,visit<2)
                if visit<2:
                    self.assertEqual(click.call_args.args,(11,1185,36))
                    w.queue_world_event(ScreenEvidence('we_home',{'event_point':(1040,380),'battle_tab':True}),stamp+timedelta(seconds=1))
            self.assertEqual(click.call_count,4)
        self.assertFalse(w.world_event_active);self.assertEqual(state.next_check,gui.next_reset(now))
        self.assertEqual(len(state.completion_proof['observations']),3)

    def test_world_event_started_battle_is_not_interrupted_by_zero_lobby_or_board(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.start_world_event(now)
        state=w.world_event_state;state.pending=True;state.started=True;state.before=2
        with patch('lib.gui.widgets.world_event_controls.click_game_point') as click:
            w.queue_world_event(ScreenEvidence('we_lobby',{'entries':(0,2),'best_score':0,'available':True}),now);click.assert_not_called()
        self.assertTrue(state.pending);self.assertTrue(state.started);self.assertFalse(state.done);self.assertEqual(state.zero_observations,[])

    def test_zombie_live_terminal_receipt_completed_board_and_next_task_through_scan_controller(self):
        w=self.window;now=datetime.now(timezone.utc);self.clear_gbr(now);w.queue_engine.start(now)
        w.queue_target='ZOMBIE SURVIVAL';w.queue_phase='navigate_board';w.queue_waiting=(('navigation_menu',),now)
        w.queue_engine.pending=(gui.reset_period(now),'ZOMBIE SURVIVAL',5);w.zombie_started=now-timedelta(minutes=20)
        w.queues[0]=[{'mode':'ZOMBIE SURVIVAL','enabled':True},{'mode':'CUTTING CABLE','enabled':True}]
        names=['zombie_repeat_ended_oct24.png','zombie_result_oct24.png','zombie_challenges_ready_oct24.png','zombie_rewards_oct24.png','zombie_challenges_claimed_oct24.png','zombie_board_completed_oct24.png']
        with patch('lib.gui.widgets.zombie_controls.click_game_point') as click:
            for name in names:
                e,observed,live=self.scan_fixture(name,reader_kind='zombie');w.show_evidence(e,observed,live);w.advance_queue()
            self.assertEqual([c.args for c in click.call_args_list],[(11,640,537),(11,867,660),(11,1135,121),(11,640,580),(11,1185,36)])
        self.assertIn('ZOMBIE SURVIVAL',w.queue_engine.completed);self.assertIsNone(w.queue_engine.pending);self.assertIsNone(w.queue_target)
        w.queue_wake=None;w.queue_tick();self.assertEqual(w.queue_target,'CUTTING CABLE')

    def test_zombie_post_repeat_receipt_wait_does_not_reuse_running_deadline(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='ZOMBIE SURVIVAL'
        pending=(gui.reset_period(now),'ZOMBIE SURVIVAL',5);w.queue_engine.pending=pending;w.zombie_started=now-timedelta(hours=2);w.zombie_repeat_finished=True
        with patch('lib.gui.widgets.zombie_controls.click_game_point') as click:w.queue_zombie(ScreenEvidence('unknown'),now);click.assert_not_called()
        self.assertTrue(w.queue_engine.running);self.assertEqual(w.queue_engine.pending,pending)
        w.zombie_collection_started=now-timedelta(minutes=4)
        w.queue_zombie(ScreenEvidence('unknown'),now);self.assertFalse(w.queue_engine.running);self.assertEqual(w.queue_engine.pending,pending)

    def test_zombie_unreadable_preparation_and_running_deadlines_stop_without_replay(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='ZOMBIE SURVIVAL'
        w.zombie_navigation_started=now-timedelta(minutes=4)
        with patch('lib.gui.widgets.zombie_controls.click_game_point') as click:w.queue_zombie(ScreenEvidence('unknown'),now);click.assert_not_called()
        self.assertFalse(w.queue_engine.running);self.assertIsNone(w.queue_engine.pending)
        w.queue_engine.start(now);pending=(gui.reset_period(now),'ZOMBIE SURVIVAL',5);w.queue_engine.pending=pending;w.zombie_started=now-timedelta(minutes=36)
        with patch('lib.gui.widgets.zombie_controls.click_game_point') as click:
            w.queue_zombie(ScreenEvidence('zombie_battle',{'mode':'ZOMBIE SURVIVAL','progress':(5,5)}),now);click.assert_not_called()
        self.assertFalse(w.queue_engine.running);self.assertEqual(w.queue_engine.pending,pending)

    def test_zombie_is_scheduled_without_gbr_and_board_open_accepts_weekly_notice(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.queues[0]=[{'mode':'ZOMBIE SURVIVAL','enabled':True},{'mode':'CUTTING CABLE','enabled':True}]
        w.gbr_retry_at=now+timedelta(minutes=1);w.queue_tick()
        self.assertEqual(w.queue_target,'ZOMBIE SURVIVAL');self.assertFalse(w.requires_gbr(w.queue_target))
        e,observed,_=self.scan_fixture('zombie_board_before_oct24.png',reader_kind='board')
        with patch.object(w,'queue_send_point') as send:
            w.queue_read_board(e,observed)
        self.assertEqual(send.call_args.args[:2],((1017,206),'zombie'))
        self.assertIn('zombie_season_notice',send.call_args.args[2])

    def test_zombie_wrong_level_returns_to_level_selector_and_never_opens_tickets(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='ZOMBIE SURVIVAL'
        with patch('lib.gui.widgets.zombie_controls.click_game_point') as click:
            w.queue_zombie(ScreenEvidence('zombie_lobby',{'mode':'ZOMBIE SURVIVAL','level':10,'minimum_point':(810,500),'prepare_point':(1030,658)}),now)
            self.assertEqual(click.call_args.args,(11,810,500))
            w.queue_zombie(ScreenEvidence('zombie_prepare',{'mode':'ZOMBIE SURVIVAL','level':2,'back_point':(35,36)}),now)
            self.assertEqual(click.call_args.args,(11,35,36));self.assertIsNone(w.zombie_prepare_verified)
        self.assertIsNone(w.queue_engine.pending)

    def test_zombie_character_tap_waits_for_slot_confirmation_instead_of_toggling_again(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='ZOMBIE SURVIVAL'
        w.zombie_roster_cleared=True;w.zombie_roster_top=True
        e,observed,_=self.scan_fixture('zombie_prepare_empty_oct24.png',reader_kind='zombie')
        with patch('lib.gui.widgets.zombie_controls.click_game_point') as click:
            w.queue_zombie(e,observed);self.assertEqual(click.call_count,1)
            w.queue_zombie(e,observed);self.assertEqual(click.call_count,1)
        self.assertEqual(w.zombie_pick,0);self.assertIsNone(w.queue_engine.pending)

    def test_zombie_pending_battle_never_sends_input_or_marks_complete_between_rounds(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='ZOMBIE SURVIVAL'
        pending=(gui.reset_period(now),'ZOMBIE SURVIVAL',5);w.queue_engine.pending=pending;w.zombie_started=now
        e,observed,_=self.scan_fixture('zombie_battle_1_oct24.png',reader_kind='zombie')
        with patch('lib.gui.widgets.zombie_controls.click_game_point') as click:
            w.queue_zombie(e,observed);w.queue_zombie(ScreenEvidence('unknown'),now);click.assert_not_called()
        self.assertEqual(w.zombie_progress,(1,5));self.assertEqual(w.queue_engine.pending,pending);self.assertNotIn('ZOMBIE SURVIVAL',w.queue_engine.completed)

    def test_zombie_stale_or_other_mode_evidence_and_partial_challenges_do_not_collect(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='ZOMBIE SURVIVAL'
        pending=(gui.reset_period(now),'ZOMBIE SURVIVAL',5);w.queue_engine.pending=pending;w.zombie_started=now
        e,observed,_=self.scan_fixture('zombie_challenges_before_oct24.png',reader_kind='zombie')
        with patch('lib.gui.widgets.zombie_controls.click_game_point') as click:
            w.queue_zombie(e,now-timedelta(seconds=31))
            w.queue_zombie(ScreenEvidence('zombie_challenges',dict(e.values,mode='OTHERWORLD BATTLE',acquire_ready=True,five_clears_verified=True)),now)
            click.assert_not_called();w.queue_zombie(e,observed);click.assert_not_called()
        self.assertFalse(w.queue_engine.running);self.assertEqual(w.queue_engine.pending,pending)

    def test_zombie_repeat_end_routed_before_stale_navigation_wait_and_retains_submission(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='ZOMBIE SURVIVAL';w.queue_phase='navigate_board'
        pending=(gui.reset_period(now),'ZOMBIE SURVIVAL',5);w.queue_engine.pending=pending;w.zombie_started=now
        w.queue_waiting=(('navigation_menu',),now)
        w.queue_observation=(ScreenEvidence('zombie_repeat_ended',{'mode':'ZOMBIE SURVIVAL','point':(640,603),'runs':5}),now)
        with patch('lib.gui.widgets.zombie_controls.click_game_point') as click:w.advance_queue();self.assertEqual(click.call_args.args,(11,640,603))
        self.assertTrue(w.zombie_repeat_finished);self.assertEqual(w.queue_engine.pending,pending);self.assertIsNone(w.queue_waiting)
        self.assertNotIn('ZOMBIE SURVIVAL',w.queue_engine.completed)

    def test_zombie_repeat_end_save_failure_or_mismatched_pending_never_acknowledges(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='ZOMBIE SURVIVAL'
        pending=(gui.reset_period(now),'ZOMBIE SURVIVAL',5);w.queue_engine.pending=pending;w.zombie_started=now
        e=ScreenEvidence('zombie_repeat_ended',{'mode':'ZOMBIE SURVIVAL','point':(640,603),'runs':5})
        with patch.object(w,'persist_pending_clear',return_value=False),patch('lib.gui.widgets.zombie_controls.click_game_point') as click:
            w.queue_zombie(e,now);click.assert_not_called()
        self.assertEqual(w.queue_engine.pending,pending);self.assertFalse(w.queue_engine.running)
        w.queue_engine.pending=None;w.queue_engine.start(now);other=(gui.reset_period(now),'OTHERWORLD BATTLE',5);w.queue_engine.pending=other
        w.queue_observation=(e,now)
        with patch('lib.gui.widgets.zombie_controls.click_game_point') as click:w.advance_queue();click.assert_not_called()
        self.assertEqual(w.queue_engine.pending,other)

    def test_zombie_completion_failure_preserves_pending_and_next_task_waits(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='ZOMBIE SURVIVAL'
        pending=(gui.reset_period(now),'ZOMBIE SURVIVAL',5);w.queue_engine.pending=pending;w.zombie_started=now
        e=ScreenEvidence('content_board',{'tiles':[dict(mode='ZOMBIE SURVIVAL',remaining=0,completed=True)]})
        with patch.object(w,'persist_completed_missions',return_value=False),patch('lib.gui.widgets.zombie_controls.click_game_point') as click:
            w.queue_zombie(e,now);click.assert_not_called()
        self.assertFalse(w.queue_engine.running);self.assertEqual(w.queue_engine.pending,pending);self.assertNotIn('ZOMBIE SURVIVAL',w.queue_engine.completed)

    def test_zombie_explicit_board_completion_caches_and_schedules_next_task(self):
        w=self.window;now=datetime.now(timezone.utc);self.clear_gbr(now);w.queue_engine.start(now);w.queue_target='ZOMBIE SURVIVAL';w.queue_phase='zombie'
        w.queues[0]=[{'mode':'ZOMBIE SURVIVAL','enabled':True},{'mode':'CUTTING CABLE','enabled':True}]
        e=ScreenEvidence('content_board',{'tiles':[dict(mode='ZOMBIE SURVIVAL',remaining=0,completed=True)]})
        with patch('lib.gui.widgets.zombie_controls.click_game_point') as click:w.queue_zombie(e,now);click.assert_not_called()
        self.assertIn('ZOMBIE SURVIVAL',w.queue_engine.completed);self.assertIsNone(w.queue_target)
        w.queue_wake=None;w.queue_tick();self.assertEqual(w.queue_target,'CUTTING CABLE')
        w.queue_engine.rollover(gui.next_reset(now));self.assertNotIn('ZOMBIE SURVIVAL',w.queue_engine.completed)

    def test_zombie_repeat_requires_fresh_level_one_roster_and_maximum_before_start(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='ZOMBIE SURVIVAL'
        e,observed,_=self.scan_fixture('zombie_repeat_max_oct24.png',reader_kind='zombie')
        with patch.object(gui,'click_game_point'),patch('lib.gui.widgets.zombie_controls.click_game_point') as click:
            w.queue_zombie(e,observed);self.assertEqual(click.call_args.args,(11,530,562));self.assertIsNone(w.queue_engine.pending)
            click.reset_mock();w.zombie_prepare_verified=observed;w.queue_zombie(e,observed)
            self.assertEqual(click.call_args.args,(11,748,562));self.assertEqual(w.queue_engine.pending,(gui.reset_period(now),'ZOMBIE SURVIVAL',5))
            self.assertTrue(w.zombie_protected());w.persist_pending_clear.assert_called()
            click.reset_mock();w.queue_zombie(e,observed);click.assert_not_called()

    def test_zombie_start_save_failure_and_mismatched_pending_never_start(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='ZOMBIE SURVIVAL'
        e,observed,_=self.scan_fixture('zombie_repeat_max_oct24.png',reader_kind='zombie');w.zombie_prepare_verified=observed
        with patch.object(w,'persist_pending_clear',return_value=False),patch('lib.gui.widgets.zombie_controls.click_game_point') as click:
            w.queue_zombie(e,observed);click.assert_not_called()
        self.assertIsNone(w.queue_engine.pending);self.assertFalse(w.queue_engine.running)
        w.queue_engine.start(now);pending=(gui.reset_period(now),'OTHERWORLD BATTLE',5);w.queue_engine.pending=pending
        with patch('lib.gui.widgets.zombie_controls.click_game_point') as click:w.queue_zombie(e,observed);click.assert_not_called()
        self.assertEqual(w.queue_engine.pending,pending)

    def test_zombie_selects_top_five_positions_without_roster_names(self):
        from lib.zombie_reader import TOP_FIVE
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='ZOMBIE SURVIVAL'
        w.zombie_roster_cleared=True;w.zombie_roster_top=True
        fixtures=['zombie_prepare_empty_oct24.png','zombie_prepare_one_oct24.png',*[f'zombie_prepare_{i}_oct24.png' for i in range(2,6)]]
        with patch('lib.gui.widgets.zombie_controls.click_game_point') as click:
            for i,name in enumerate(fixtures):
                e,observed,_=self.scan_fixture(name,reader_kind='zombie');w.queue_zombie(e,observed)
                self.assertEqual(click.call_args.args,(11,*(TOP_FIVE[i] if i<5 else (825,659))))
        self.assertEqual(w.zombie_pick,5);self.assertIsNotNone(w.zombie_prepare_verified)

    def test_zombie_pending_is_protected_from_restart_capture_failure_and_fresh_pass_release(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='ZOMBIE SURVIVAL'
        pending=(gui.reset_period(now),'ZOMBIE SURVIVAL',5);w.queue_engine.pending=pending;w.zombie_started=now
        w.queue_fresh_pass=True
        self.assertFalse(w.fresh_queue_home_check(ScreenEvidence('game_home',{'home_controls_verified':True}),now))
        with patch.object(w,'restart_stuck_game') as restart:w.recover_stuck_queue('Unrecognized battle frame');restart.assert_not_called()
        self.assertEqual(w.queue_engine.pending,pending);self.assertFalse(w.queue_engine.running)

    def test_running_queue_accepts_wheel_scrolling_and_refresh_preserves_position(self):
        from PyQt5 import QtGui
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.queues[0]=[{'mode':mode,'enabled':True} for mode in gui.MODES];w._populate();w.set_queue_editable(False)
        w.show();self.app.processEvents();view=w.queue_list_widget;bar=view.verticalScrollBar()
        self.assertGreater(bar.maximum(),0);self.assertTrue(view.isEnabled())
        def wheel(delta):
            point=view.viewport().rect().center()
            event=QtGui.QWheelEvent(gui.QtCore.QPointF(point),gui.QtCore.QPointF(view.viewport().mapToGlobal(point)),
                gui.QtCore.QPoint(),gui.QtCore.QPoint(0,delta),gui.QtCore.Qt.NoButton,gui.QtCore.Qt.NoModifier,gui.QtCore.Qt.NoScrollPhase,False)
            self.app.sendEvent(view.viewport(),event);self.app.processEvents()
        wheel(-120);down=bar.value();self.assertGreater(down,0)
        wheel(120);self.assertLess(bar.value(),down)
        bar.setValue(bar.maximum()//2);position=bar.value()
        for _ in range(3):w.refresh_task_statuses();self.assertEqual(bar.value(),position)
        view.setCurrentRow(3);selected=view.currentItem();bar.setValue(position)
        w.queue_engine.completed.add(gui.MODES[0]);w.refresh_task_statuses()
        self.assertEqual(bar.value(),position);self.assertIs(view.currentItem(),selected);self.assertTrue(selected.isSelected())
        self.assertEqual(view.item(view.count()-1).data(gui.QtCore.Qt.UserRole),gui.MODES[0])

    def test_done_items_sort_below_unfinished_without_changing_saved_priority_and_reset_restores_order(self):
        from lib.gui.widgets import appearance
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        modes=['TIMELINE BATTLE','CUTTING CABLE','ALLIANCE BATTLE','WORLD EVENT','STORY ULTIMATE']
        w.queues[0]=[{'mode':mode,'enabled':True} for mode in modes];w._populate()
        w.queue_engine.completed.update(('TIMELINE BATTLE','ALLIANCE BATTLE'));w.world_event_state.done=True
        w._save.reset_mock();w.refresh_task_statuses()
        shown=lambda:[w.queue_list_widget.item(i).data(gui.QtCore.Qt.UserRole) for i in range(w.queue_list_widget.count())]
        self.assertEqual(shown(),['CUTTING CABLE','STORY ULTIMATE','TIMELINE BATTLE','ALLIANCE BATTLE','WORLD EVENT'])
        self.assertEqual([i['mode'] for i in w.queues[0]],modes);w._save.assert_not_called()
        after=gui.next_reset(now)+timedelta(seconds=1)
        with patch.object(appearance,'datetime',wraps=datetime) as clock:
            clock.now.return_value=after;w.refresh_task_statuses()
        self.assertEqual(shown(),modes)
        self.assertNotIn('Done today',w.queue_list_widget.item(0).text())

    def test_checkbox_on_sorted_duplicate_updates_original_entry_only(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_engine.stop()
        w.queues[0]=[{'mode':'TIMELINE BATTLE','enabled':True},{'mode':'CUTTING CABLE','enabled':False},{'mode':'CUTTING CABLE','enabled':True}]
        w.queue_engine.completed.add('TIMELINE BATTLE');w._populate()
        first=w.queue_list_widget.item(0);self.assertEqual(first.data(gui.QtCore.Qt.UserRole+1),1)
        first.setCheckState(gui.QtCore.Qt.Checked)
        self.assertEqual(w.queues[0],[{'mode':'TIMELINE BATTLE','enabled':True},{'mode':'CUTTING CABLE','enabled':True},{'mode':'CUTTING CABLE','enabled':True}])
        w.queue_list_widget.item(1).setCheckState(gui.QtCore.Qt.Unchecked)
        self.assertTrue(w.queues[0][0]['enabled']);self.assertTrue(w.queues[0][1]['enabled']);self.assertFalse(w.queues[0][2]['enabled'])

    def test_edit_and_remove_sorted_rows_address_correct_saved_entry(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_engine.stop()
        w.queues[0]=[{'mode':'TIMELINE BATTLE','enabled':True},{'mode':'CUTTING CABLE','enabled':True},{'mode':'STORY ULTIMATE','enabled':True}]
        w.queue_engine.completed.add('TIMELINE BATTLE');w._populate();w.queue_list_widget.setCurrentRow(0)
        with patch.object(gui.QtWidgets.QInputDialog,'getItem',return_value=('MADNESS ENSUES',True)):w.edit_mode()
        self.assertEqual([i['mode'] for i in w.queues[0]],['TIMELINE BATTLE','MADNESS ENSUES','STORY ULTIMATE'])
        w.queue_list_widget.setCurrentRow(1);w.remove_modes()
        self.assertEqual([i['mode'] for i in w.queues[0]],['TIMELINE BATTLE','MADNESS ENSUES'])

    def test_running_list_is_browsable_but_all_edits_stay_locked_until_stop(self):
        from PyQt5.QtTest import QTest
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.set_queue_editable(False)
        view=w.queue_list_widget;original=[dict(i) for i in w.queues[0]]
        view.setCurrentRow(0);QTest.keyClick(view,gui.QtCore.Qt.Key_Space)
        self.assertEqual(view.item(0).checkState(),gui.QtCore.Qt.Checked)
        self.assertEqual(view.dragDropMode(),gui.QtWidgets.QAbstractItemView.NoDragDrop)
        with patch.object(gui.QtWidgets.QInputDialog,'getItem') as dialog:
            w.edit_mode();w.add_mode();dialog.assert_not_called()
        w.remove_modes();w.switch_queue(1);w.queue_reordered()
        self.assertEqual(w.queue_index,0);self.assertEqual(w.queues[0],original)
        w.stop_queue();self.assertTrue(view.item(0).flags()&gui.QtCore.Qt.ItemIsUserCheckable)
        self.assertEqual(view.dragDropMode(),gui.QtWidgets.QAbstractItemView.InternalMove)
        view.item(0).setCheckState(gui.QtCore.Qt.Unchecked);self.assertFalse(w.queues[0][0]['enabled'])

    def test_manual_drag_reorder_preserves_enablement_and_reindexes_sorted_entries(self):
        w=self.window
        w.queues[0]=[{'mode':'CUTTING CABLE','enabled':False},{'mode':'STORY ULTIMATE','enabled':True},{'mode':'TIMELINE BATTLE','enabled':False}];w._populate()
        model=w.queue_list_widget.model()
        self.assertTrue(model.moveRows(gui.QtCore.QModelIndex(),2,1,gui.QtCore.QModelIndex(),0))
        self.assertEqual(w.queues[0],[{'mode':'TIMELINE BATTLE','enabled':False},{'mode':'CUTTING CABLE','enabled':False},{'mode':'STORY ULTIMATE','enabled':True}])
        self.assertEqual([w.queue_list_widget.item(i).data(gui.QtCore.Qt.UserRole+1) for i in range(3)],[0,1,2])

    def test_live_weekly_alliance_scan_saves_skip_then_schedules_next_task_and_expires(self):
        import json
        from lib.gui.widgets import completion_cache as cache
        from lib.daily_queue import ContinuousQueue
        w=self.window;now=datetime.now(timezone.utc);self.clear_gbr(now);w.queue_engine.start(now)
        w.queue_target='ALLIANCE BATTLE';w.queue_phase='alliance'
        w.queue_waiting=(('alliance_weekly_skip',),now)
        e,observed,live=self.scan_fixture('alliance_infinite_challenge_oct24.png',reader_kind='alliance')
        cachefile=Path(self.log_directory.name)/'done.json'
        with patch.object(cache,'CACHE',cachefile),patch.object(w,'persist_completed_missions',side_effect=lambda:cache.CompletionCache.persist_completed_missions(w)),patch.object(gui,'click_game_point') as click:
            w.show_evidence(e,observed,live);w.advance_queue()
            self.assertEqual(click.call_args.args,(11,1185,36));self.assertEqual(click.call_count,1)
            self.assertIsNone(w.queue_target);self.assertIsNone(w.queue_engine.pending);self.assertIsNone(w.queue_waiting)
            self.assertEqual(w.queue_phase,'navigate_board')
            saved=json.loads(cachefile.read_text(encoding='utf-8'))
            self.assertIn('ALLIANCE BATTLE',saved['completed']);self.assertEqual(saved['expires_at'],gui.next_reset(now).isoformat())
            w.queue_engine=ContinuousQueue(w.raid_gate);cache.CompletionCache.load_completed_missions(w)
            w.queue_engine.start(now);w.queues[0]=[{'mode':m,'enabled':True} for m in ('ALLIANCE BATTLE','CUTTING CABLE')]
            w.queue_wake=None;w.queue_tick();self.assertEqual(w.queue_target,'CUTTING CABLE')
            self.assertEqual(cache.restore_completed(saved,gui.next_reset(now)),set())
            self.assertEqual(w.queue_engine.next_mode(['ALLIANCE BATTLE'],gui.next_reset(now)),'ALLIANCE BATTLE')

    def test_weekly_alliance_skip_preserves_any_pending_mission(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        e,observed,_=self.scan_fixture('alliance_infinite_challenge_oct24.png',reader_kind='alliance')
        for mode in ('ALLIANCE BATTLE','OTHERWORLD BATTLE'):
            pending=(gui.reset_period(now),mode,1);w.queue_engine.pending=pending
            with patch.object(gui,'click_game_point') as click:w.queue_read_alliance(e,observed);click.assert_not_called()
            self.assertEqual(w.queue_engine.pending,pending);self.assertNotIn('ALLIANCE BATTLE',w.queue_engine.completed)
        w.persist_completed_missions.assert_not_called()

    def test_weekly_alliance_skip_requires_fresh_matching_proof(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        e,_,_=self.scan_fixture('alliance_infinite_challenge_oct24.png',reader_kind='alliance')
        with patch.object(gui,'click_game_point') as click:
            w.queue_read_alliance(e,now-timedelta(seconds=31))
            w.queue_read_alliance(e,now+timedelta(seconds=5))
            for changed in ({'mode':'OTHERWORLD BATTLE'},{'weekly_skip_verified':False},{'weekly_variant':'NORMAL'}):
                w.queue_read_alliance(ScreenEvidence(e.screen,dict(e.values,**changed)),now)
            w.queue_read_alliance(ScreenEvidence(e.screen,e.values,errors=['unverified']),now)
            reset=gui.next_reset(now)
            with patch.object(gui,'datetime',wraps=datetime) as clock:
                clock.now.return_value=reset+timedelta(seconds=1)
                w.queue_read_alliance(e,reset-timedelta(seconds=1))
            click.assert_not_called()
        self.assertNotIn('ALLIANCE BATTLE',w.queue_engine.completed);w.persist_completed_missions.assert_not_called()

    def test_weekly_alliance_save_failure_stops_without_leaving_screen_or_remembering_skip(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        e,observed,_=self.scan_fixture('alliance_infinite_challenge_oct24.png',reader_kind='alliance')
        with patch.object(w,'persist_completed_missions',return_value=False),patch.object(gui,'click_game_point') as click:
            w.queue_read_alliance(e,observed);click.assert_not_called()
        self.assertFalse(w.queue_engine.running);self.assertNotIn('ALLIANCE BATTLE',w.queue_engine.completed)

    def test_failed_optional_trivia_recheck_preserves_today_done_and_next_reset(self):
        import json
        from lib.gui.widgets import trivia_controls
        w=self.window;now=datetime.now(timezone.utc);w.trivia_period=gui.reset_period(now)
        w.trivia_session=Mock(done=False)
        w.finish_trivia('Optional recheck unreadable')
        saved=json.loads(trivia_controls.TRIVIA_CACHE.read_text(encoding='utf-8'))
        self.assertTrue(saved['done']);self.assertEqual(saved['retry_at'],gui.next_reset(now).isoformat())
        w.init_trivia();self.assertFalse(w.trivia_due(now))

    def test_daily_queue_attempts_trivia_again_after_reset_even_with_old_done_record(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.trivia_period=gui.reset_period(now);w.trivia_retry_at=gui.next_reset(now)
        w.queue_target=None;w.queue_wake=gui.next_reset(now)
        after=gui.next_reset(now)+timedelta(seconds=1)
        with patch.object(gui,'datetime',wraps=datetime) as clock,patch.object(w,'check_trivia') as trivia:
            clock.now.return_value=after
            w.queue_tick();trivia.assert_called_once_with(automatic=True)

    def test_live_completed_trivia_is_saved_skipped_after_restart_and_due_next_reset(self):
        import json
        from lib.gui.widgets import trivia_controls
        from lib.trivia_session import TriviaSession
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.trivia_period=None;w.trivia_active=True;w.trivia_session=TriviaSession(now)
        with patch.object(gui.QtCore.QTimer,'singleShot'),patch('lib.gui.widgets.trivia_controls.click_game_point') as click:
            for name in ('trivia_completed_oct24_top.png',):
                e,observed,live=self.scan_fixture(name,reader_kind='trivia')
                w.show_evidence(e,observed,live);w.advance_trivia()
            click.assert_not_called()
        self.assertFalse(w.trivia_active);self.assertTrue(w.queue_engine.running)
        saved=json.loads(trivia_controls.TRIVIA_CACHE.read_text(encoding='utf-8'))
        self.assertTrue(saved['done']);self.assertEqual(saved['verified_questions'],5)
        self.assertEqual(saved['expires_at'],gui.next_reset(now).isoformat())
        w.init_trivia();self.assertFalse(w.trivia_due(datetime.now(timezone.utc)))
        w.scan_live.reset_mock();w.check_trivia(automatic=True);w.scan_live.assert_not_called()
        after=gui.next_reset(now)+timedelta(seconds=1)
        with patch.object(trivia_controls,'datetime',wraps=datetime) as clock:
            clock.now.return_value=after
            w.init_trivia();self.assertTrue(w.trivia_due(after))
            w.check_trivia(automatic=True);w.scan_live.assert_called_once()

    def test_incomplete_quiz_is_retried_and_never_saved_as_cleared(self):
        from lib.trivia_session import TriviaSession
        w=self.window;now=datetime.now(timezone.utc);w.trivia_period=None;w.trivia_active=True;w.trivia_session=TriviaSession(now)
        w.finish_trivia('Unknown answer - no submission');w.init_trivia()
        self.assertFalse(w.trivia_due(now));self.assertTrue(w.trivia_due(now+timedelta(minutes=3)))
        self.assertIsNone(w.trivia_period)

    def test_observed_nonzero_gbr_counts_finish_inspection_without_swipe_loop_or_clearance(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        for name,key,count in [('gbr_soul_full_clean_oct24.png','soul',165),('gbr_seed_full_clean_oct24.png','seed',300)]:
            with self.subTest(name=name):
                w.resource_active=True;w.resource_started=now;w.resource_waiting=None;w.latest_counters.clear()
                e,observed,live=self.scan_fixture(name,resource_check=True)
                with patch.object(gui,'perform_navigation') as navigation:
                    w.show_evidence(e,observed,live);w.advance_resource_check();navigation.assert_not_called()
                self.assertEqual(w.latest_counters[key][0],(count,count))
                self.assertFalse(w.resource_active);self.assertTrue(w.queue_engine.running)
                self.assertFalse(w.raid_gate.cleared(datetime.now(timezone.utc)))

    def test_interrupted_otherworld_reconciles_count_without_ticket_cost_gate(self):
        from lib.arena_reader import ArenaReader
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='OTHERWORLD BATTLE'
        w.queue_engine.pending=(gui.reset_period(now),w.queue_target,5);w.arena_started=now-timedelta(minutes=7);w.arena_resumed=True
        e=ArenaReader().read(Path(__file__).parent/'fixtures/otherworld_idle_four_oct24.png')
        self.assertTrue(e.values['lobby_idle_verified'])
        proof=('OTHERWORLD BATTLE',(4,5));w.arena_idle_seen=(proof,now-timedelta(seconds=61),now-timedelta(seconds=14),4)
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            w.queue_arena(e,now);click.assert_not_called()
            self.assertIsNone(w.queue_engine.pending);self.assertNotIn('OTHERWORLD BATTLE',w.queue_engine.completed)
            self.assertEqual(w.queue_phase,'navigate_board')
            w.queue_arena(e,now);self.assertEqual(w.arena_remaining,4)
            click.reset_mock()
            w.queue_arena(ScreenEvidence('otherworld_repeat',{'selected':5,'until_rewards':True}),now)
            click.assert_not_called();self.assertIsNone(w.queue_engine.pending)
            w.queue_arena(ScreenEvidence('otherworld_repeat',{'selected':4,'until_rewards':True}),now)
            self.assertEqual(click.call_args.args,(11,750,561));self.assertEqual(click.call_count,1)
            prepared=ArenaReader().read(Path(__file__).parent/'fixtures/otherworld_repeat_four_oct24.png')
            w.queue_arena(prepared,now);self.assertEqual(click.call_count,1)
        self.assertEqual(w.queue_engine.pending,(gui.reset_period(now),'OTHERWORLD BATTLE',4))

    def test_idle_reconciliation_requires_continuous_distinct_undimmed_captures(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='OTHERWORLD BATTLE'
        pending=(gui.reset_period(now),w.queue_target,5);w.queue_engine.pending=pending;w.arena_started=now;w.arena_resumed=True
        e=ScreenEvidence('otherworld_lobby',{'mode':w.queue_target,'entries':(4,5),'lobby_idle_verified':True})
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            w.queue_arena(e,now);w.queue_arena(e,now)
            self.assertEqual(w.arena_idle_seen[3],1);self.assertEqual(w.queue_engine.pending,pending)
            proof=(w.queue_target,(4,5))
            for invalid in (ScreenEvidence('unknown'),ScreenEvidence(errors=['OCR failed']),
                            ScreenEvidence('otherworld_lobby',{'mode':w.queue_target,'entries':(4,5)})):
                w.arena_idle_seen=(proof,now-timedelta(seconds=61),now-timedelta(seconds=14),4)
                w.queue_arena(invalid,now);self.assertIsNone(w.arena_idle_seen)
                self.assertEqual(w.queue_engine.pending,pending)
            w.arena_idle_seen=(proof,now-timedelta(seconds=61),now-timedelta(seconds=31),4)
            w.queue_arena(e,now);self.assertEqual(w.arena_idle_seen[3],1)
            click.assert_not_called()

    def test_weekly_information_can_close_without_releasing_or_replaying_pending_run(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='OTHERWORLD BATTLE';w.queue_phase='arena'
        pending=(gui.reset_period(now),w.queue_target,5);w.queue_engine.pending=pending;w.arena_started=now
        e,observed,live=self.scan_fixture('otherworld_weekly_oct24.png')
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click,patch.object(w,'recover_stuck_queue') as recover:
            w.show_evidence(e,observed,live);w.advance_queue()
            self.assertEqual(click.call_args.args,(11,640,615));self.assertEqual(click.call_count,1);recover.assert_not_called()
        self.assertEqual(w.queue_engine.pending,pending);self.assertFalse(w.arena_repeat_finished)
        self.assertNotIn('OTHERWORLD BATTLE',w.queue_engine.completed)
        w.persist_pending_clear.assert_not_called()

    def test_restart_inside_unsubmitted_repeat_can_close_modal_before_board_check(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.start_daily_board_check(now)
        e,observed,live=self.scan_fixture('otherworld_repeat_restart_oct24.png',reader_kind='daily_board_check')
        self.assertEqual(e.screen,'otherworld');self.assertFalse(e.values.get('menu_available'));self.assertFalse(e.values.get('home_available'))
        w.navigation_unsure_since=now-timedelta(seconds=7);w.navigation_unsure_backs=0
        with patch('lib.gui.widgets.stuck_recovery.click_game_point') as click,patch.object(gui.QtCore.QTimer,'singleShot'):
            w.show_evidence(e,observed,live)
        self.assertEqual(click.call_args.kwargs['key'],'back')
        self.assertTrue(w.board_check_active);self.assertTrue(w.queue_engine.running);self.assertIsNone(w.queue_engine.pending)
        self.assertEqual(w.queue_phase,'daily_board_check')

    def test_blocked_lobby_back_recovery_never_interrupts_a_submitted_repeat(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        pending=(gui.reset_period(now),'OTHERWORLD BATTLE',5);w.queue_engine.pending=pending
        w.navigation_unsure_since=now-timedelta(seconds=7)
        with patch('lib.gui.widgets.stuck_recovery.click_game_point') as click:
            for screen in ('otherworld','timeline','timeline_team'):
                w.navigation_back_recovery(ScreenEvidence(screen),now)
            click.assert_not_called()
        self.assertEqual(w.queue_engine.pending,pending)

    def scan_fixture(self,name,reader_kind='arena',resource_check=False):
        from PIL import Image
        observed=datetime.now(timezone.utc);results=[];errors=[]
        task=gui.ScanTask(Image.open(Path(__file__).parent/'fixtures'/name).convert('RGB'),observed,True,reader_kind=reader_kind,resource_check=resource_check)
        task.result.connect(lambda *result:results.append(result));task.failed.connect(errors.append)
        task.run()
        self.assertFalse(errors,errors);self.assertEqual(len(results),1)
        return results[0]

    def test_live_timeline_summary_through_scan_controller_result_and_next_task(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        pending=(gui.reset_period(now),'TIMELINE BATTLE',5)
        w.queue_engine.pending=pending;w.arena_started=now;w.arena_resumed=True
        w.queue_target='TIMELINE BATTLE';w.queue_phase='navigate_board'
        w.queue_waiting=(('timeline_setup',),now-timedelta(minutes=8))
        with patch.object(gui,'click_game_point') as generic,patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            e,observed,live=self.scan_fixture('timeline_exhausted_oct24.png',reader_kind='board')
            w.show_evidence(e,observed,live);w.advance_queue()
            self.assertTrue(w.arena_repeat_finished);self.assertIsNone(w.queue_waiting)
            self.assertEqual(w.queue_engine.pending,pending);self.assertNotIn('TIMELINE BATTLE',w.queue_engine.completed)
            self.assertEqual(click.call_args.args,(11,755,604))
            generic.assert_not_called()
            e,observed,live=self.scan_fixture('timeline_result_oct24.png')
            w.show_evidence(e,observed,live);w.advance_queue()
            self.assertEqual(click.call_args.args,(11,*e.values['point']))
        self.assertIn('TIMELINE BATTLE',w.queue_engine.completed);self.assertIsNone(w.queue_engine.pending)
        self.assertIsNone(w.queue_target);self.assertEqual(w.queue_phase,'navigate_board')
        w.queue_wake=None
        self.clear_gbr(datetime.now(timezone.utc))
        with patch.object(w,'check_resources'),patch.object(w,'start_dispatch_supplies'),patch.object(w,'start_world_event'):
            w.queue_tick()
        self.assertEqual(w.queue_target,'CUTTING CABLE');self.assertTrue(w.queue_engine.running)

    def test_real_team_summary_and_result_leave_completed_mode(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.queue_engine.pending=(gui.reset_period(now),'TEAM BATTLE ARENA',5);w.arena_started=now
        with patch.object(gui,'click_game_point') as click:
            e,observed,live=self.scan_fixture('team_arena_ended_one_win_oct24.png',reader_kind='board')
            w.show_evidence(e,observed,live);w.advance_queue();self.assertEqual(click.call_args.args,(11,640,603))
        self.assertIn('TEAM BATTLE ARENA',w.queue_engine.completed);self.assertIsNone(w.queue_engine.pending)
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            w.queue_observation=(ScreenEvidence('game_home',{'home_controls_verified':True}),datetime.now(timezone.utc))
            w.advance_queue();click.assert_not_called()
        self.assertIsNone(w.queue_target);self.assertEqual(w.queue_phase,'navigate_board')

    def test_terminal_popups_never_take_over_another_pending_task(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        pending=(gui.reset_period(now),'STORY ULTIMATE',1);w.queue_engine.pending=pending
        for screen in ('arena_exhausted','arena_repeat_ended'):
            w.queue_observation=(ScreenEvidence(screen,{'mode':'TIMELINE BATTLE','point':(755,604)}),now)
            with patch.object(gui,'click_game_point') as generic,patch('lib.gui.widgets.arena_controls.click_game_point') as click:
                w.advance_queue();generic.assert_not_called();click.assert_not_called()
            self.assertEqual(w.queue_engine.pending,pending);self.assertFalse(w.arena_repeat_finished)

    def test_terminal_notice_save_failure_keeps_popup_and_submission(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        pending=(gui.reset_period(now),'TIMELINE BATTLE',5);w.queue_engine.pending=pending;w.arena_started=now
        w.queue_observation=(ScreenEvidence('arena_exhausted',{'mode':'TIMELINE BATTLE','point':(755,604)}),now)
        with patch.object(w,'persist_pending_clear',return_value=False),patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            w.advance_queue();click.assert_not_called()
        self.assertFalse(w.queue_engine.running);self.assertEqual(w.queue_engine.pending,pending)

    def test_sorted_board_boundary_remembers_missing_modes_without_completing_unfinished_prefix(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.start_daily_board_check(now)
        w.board_check_top=True
        first=ScreenEvidence('content_board',{'incomplete_prefix_verified':True,'unfinished_modes':['MADNESS ENSUES','WORLD EVENT'],
            'tiles':[dict(mode='MADNESS ENSUES',remaining=4,completed=False)]})
        boundary=ScreenEvidence('content_board',{'incomplete_prefix_verified':True,'completed_tail_verified':True,
            'unfinished_modes':['SHOCK AND AWE'],'tiles':[dict(mode='SHOCK AND AWE',remaining=4,completed=False)]})
        with patch('lib.gui.widgets.daily_board_check.click_game_point'):
            w.queue_daily_board_check(first,now);w.queue_daily_board_check(boundary,now)
        self.assertIn('CUTTING CABLE',w.queue_engine.completed)
        self.assertNotIn('MADNESS ENSUES',w.queue_engine.completed);self.assertNotIn('SHOCK AND AWE',w.queue_engine.completed)
        self.assertNotIn('DIMENSION MISSION',w.queue_engine.completed);self.assertNotIn('DISPATCH 7-1',w.queue_engine.completed)
        self.assertFalse(w.world_event_state.done)

    def test_board_preflight_stops_at_completed_tail_without_marking_unseen_modes(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.start_daily_board_check(now)
        w.board_check_top=True
        e=ScreenEvidence('content_board',{'completed_tail_verified':True,'tiles':[]})
        before=set(w.queue_engine.completed)
        with patch('lib.gui.widgets.daily_board_check.click_game_point') as click:
            w.queue_daily_board_check(e,now)
        click.assert_not_called();self.assertFalse(w.board_check_active);self.assertFalse(w.board_check_due)
        self.assertEqual(w.queue_engine.completed,before)

    def test_board_preflight_can_leave_verified_gbr_strip_directly(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.start_daily_board_check(now)
        with patch('lib.gui.widgets.daily_board_check.click_game_point') as click:
            w.queue_daily_board_check(ScreenEvidence('gbr_main',{'reward_strip_verified':True,'seed':(0,300)}),now)
        self.assertEqual(click.call_args.args,(11,1249,36))

    def test_launcher_recovery_has_priority_over_interrupted_board_preflight(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.enable_board_preflight=True
        w.board_check_active=True;w.board_check_due=True;w.queue_recovering=True
        with patch.object(w,'scan_live') as scan:
            w.queue_tick();scan.assert_called_once();self.assertEqual(w.queue_phase,'recover_home')
        w.queue_recover_home(ScreenEvidence('game_home'),now)
        self.assertFalse(w.board_check_active);self.assertTrue(w.board_check_due)
        with patch.object(w,'scan_live'):
            w.queue_tick();self.assertEqual(w.queue_phase,'daily_board_check')

    def test_board_without_selected_target_returns_to_scheduler_without_input(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target=None
        with patch.object(w,'queue_send_point') as send:
            w.queue_read_board(ScreenEvidence('content_board',{'tiles':[]}),now)
        send.assert_not_called();self.assertEqual(w.queue_phase,'navigate_board');self.assertIsNone(w.queue_wake)

    def test_partial_story_board_opens_verified_unfinished_section_without_scrolling(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='STORY ULTIMATE'
        section=dict(mode='STORY: THE ALL-WAR',remaining=4,total=4,completed=False,point=(1017,342))
        e=ScreenEvidence('content_board',{'tiles':[dict(mode='STORY ULTIMATE',remaining=None,point=(1017,342))], 'story_themes':{'THE ALL-WAR':section}})
        with patch.object(w,'queue_send_point') as send,patch('lib.queue_input.scroll_board') as scroll:
            w.queue_read_board(e,now)
        send.assert_called_once_with((1017,342),'story',('story_select','story_ultimate'));scroll.assert_not_called()

    def test_verified_launcher_reopens_only_without_pending_submission(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        e=ScreenEvidence('android_home',{'launcher_verified':True,'launch_point':(539,204)})
        with patch.object(gui,'click_game_point') as click:
            w.show_evidence(e,now,True)
            self.assertEqual(click.call_args.args,(11,539,204))
            w.show_evidence(e,now,True);self.assertEqual(click.call_count,1)
        self.assertTrue(w.queue_engine.running);self.assertTrue(w.queue_recovering)
        self.assertEqual(w.queue_phase,'recover_home')

    def test_verified_launcher_keeps_pending_story_untouched(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.queue_engine.pending=(gui.reset_period(now),'STORY ULTIMATE',1)
        with patch.object(gui,'click_game_point') as click:
            w.show_evidence(ScreenEvidence('android_home',{'launcher_verified':True,'launch_point':(539,204)}),now,True)
        click.assert_not_called();self.assertFalse(w.queue_engine.running)
        self.assertIsNotNone(w.queue_engine.pending)

    def test_current_normal_setup_starts_once_and_commits_pending(self):
        from lib.alliance_reader import AllianceReader
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='ALLIANCE BATTLE'
        e=AllianceReader().read(Path(__file__).parent/'fixtures/alliance_normal_setup_current.png')
        with patch.object(gui,'click_game_point') as click:
            w.queue_read_alliance(e,now)
            self.assertEqual(click.call_args.args,(11,1030,674))
            w.queue_read_alliance(e,now)
            self.assertEqual(click.call_count,1)
        self.assertEqual(w.queue_engine.pending,(gui.reset_period(now),'ALLIANCE BATTLE',1))

    def test_reentering_lobby_does_not_reset_unknown_navigation_failure_budget(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='ALLIANCE BATTLE'
        with patch('lib.gui.widgets.stuck_recovery.click_game_point') as click,patch.object(gui.QtCore.QTimer,'singleShot'):
            for _ in range(4):
                w.navigation_back_recovery(ScreenEvidence('alliance_normal_ready'),now)
                w.navigation_unsure_since=now-timedelta(seconds=7)
                self.assertTrue(w.navigation_back_recovery(ScreenEvidence('unknown'),now))
        self.assertEqual(click.call_count,3)
        self.assertTrue(w.queue_recovering);self.assertIsNone(w.queue_target)
        self.assertIn('ALLIANCE BATTLE',w.queue_deferred)

    def test_board_preflight_prefers_menu_over_home_when_both_verified(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.start_daily_board_check(now)
        with patch('lib.gui.widgets.daily_board_check.click_game_point') as click:
            w.queue_daily_board_check(ScreenEvidence('mission_preparation',{'menu_available':True,'home_available':True}),now)
        self.assertEqual(click.call_args.args,(11,1249,36))

    def test_world_event_prefers_menu_from_other_content(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.start_world_event(now)
        with patch('lib.gui.widgets.world_event_controls.click_game_point') as click:
            w.queue_world_event(ScreenEvidence('challenge_navigation',{'menu_available':True,'home_available':True}),now)
        self.assertEqual(click.call_args.args,(11,1249,36))
        self.assertEqual(w.world_event_waiting[0],('navigation_menu',))

    def test_trivia_runs_before_board_world_event_and_gbr_after_reset(self):
        w=self.window;now=datetime.now(timezone.utc);w.enable_board_preflight=True;w.queue_engine.start(now)
        w.trivia_period=None
        with patch.object(w,'check_trivia') as trivia,patch.object(w,'check_resources') as gbr,patch.object(w,'start_world_event') as event:
            w.queue_tick();trivia.assert_called_once_with(automatic=True)
            self.assertFalse(w.board_check_active);gbr.assert_not_called();event.assert_not_called()

    def test_due_trivia_preempts_an_unsubmitted_boost_wait(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.queue_target='SINISTER SCHEMES';w.queue_phase='sweep';w.queue_wake=now+timedelta(minutes=20)
        w.trivia_period=None;w.trivia_retry_at=now
        with patch.object(w,'check_trivia') as trivia:
            w.queue_tick();trivia.assert_called_once_with(automatic=True)

    def test_due_trivia_waits_for_active_converging_preparation_and_direct_hidden_handoff(self):
        from lib.converging import NORMAL,HIDDEN
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.trivia_period=None;w.trivia_retry_at=now
        for mode in (NORMAL,HIDDEN):
            w.queue_target=mode;w.queue_phase='converging';w.queue_wake=now+timedelta(seconds=3)
            with patch.object(w,'check_trivia') as trivia:
                w.queue_tick();trivia.assert_not_called()
        w.queue_target=None;w.queue_waiting=None;w.queue_wake=None
        with patch.object(w,'check_trivia') as trivia:
            w.queue_tick();trivia.assert_called_once_with(automatic=True)

    def test_native_mission_navigation_reaches_trivia_menu_without_guessing_a_question(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.trivia_period=None;w.trivia_retry_at=now;w.check_trivia(automatic=True)
        for fixture in ('converging_ready_adb_oct26.png','trivia_navigation_event_quest_oct27.png'):
            e,observed,_=self.scan_fixture(fixture,reader_kind='trivia')
            self.assertEqual(e.screen,'challenge_navigation');self.assertTrue(e.values['menu_available'])
            w.trivia_observation=(e,observed);w.trivia_waiting=None
            with patch('lib.gui.widgets.trivia_controls.click_game_point') as click:
                w.advance_trivia();self.assertEqual(click.call_args.args,(11,1249,37))
            self.assertEqual(w.trivia_waiting[0],('trivia_menu',));self.assertIsNone(w.queue_engine.pending)

    def test_trivia_navigation_never_discards_pending_answer_or_uses_a_stale_frame(self):
        from lib.trivia_session import TriviaSession
        w=self.window;now=datetime.now(timezone.utc);w.trivia_period=None
        e,observed,_=self.scan_fixture('converging_ready_adb_oct26.png',reader_kind='trivia')
        for pending,stamp in (('unverified answer',observed),(None,now-timedelta(seconds=31))):
            w.trivia_active=True;w.trivia_waiting=None;w.trivia_session=TriviaSession(now);w.trivia_session.pending=pending
            w.trivia_observation=(e,stamp)
            with patch('lib.gui.widgets.trivia_controls.click_game_point') as click:
                w.advance_trivia();click.assert_not_called()
            self.assertFalse(w.trivia_active);self.assertNotEqual(w.trivia_period,gui.reset_period(now))

    def test_daily_reset_discards_previous_day_trivia_retry_delay(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        after=gui.next_reset(now)+timedelta(seconds=1);w.trivia_period=None;w.trivia_retry_at=after+timedelta(minutes=10)
        with patch.object(gui,'datetime',wraps=datetime) as clock,patch.object(w,'check_trivia') as trivia:
            clock.now.return_value=after;w.queue_tick();trivia.assert_called_once_with(automatic=True)
        self.assertEqual(w.trivia_retry_at,after)

    def test_board_completions_cache_story_free_modes_but_not_world_event(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        e=ScreenEvidence('content_board',{'tiles':[dict(mode=m,remaining=0,completed=True) for m in ('STORY ULTIMATE','TIMELINE BATTLE','WORLD EVENT')]})
        w.remember_board_completions(e,now)
        self.assertIn('STORY ULTIMATE',w.queue_engine.completed);self.assertIn('TIMELINE BATTLE',w.queue_engine.completed)
        self.assertFalse(w.world_event_state.done)
        self.assertLess(w.world_event_state.next_check,gui.next_reset(now))

    def test_story_reward_taken_does_not_open_auto_progress(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='STORY ULTIMATE'
        with patch('lib.gui.widgets.story_controls.click_game_point') as click:
            w.queue_story(ScreenEvidence('story_ultimate',{'daily_rewards':(0,1),'team_2':True,'energy':(100,120),'point':(930,668)}),now)
            self.assertEqual(click.call_args.args,(11,1249,36));self.assertIsNone(w.story_ultimate_verified)
        self.assertIsNone(w.queue_engine.pending)

    def test_completed_story_board_resolves_saved_submission_without_input(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='STORY ULTIMATE'
        w.queue_engine.pending=(gui.reset_period(now),w.queue_target,1);w.story_started=now
        e=ScreenEvidence('content_board',{'tiles':[dict(mode=m,remaining=0,completed=True) for m in ('MADNESS ENSUES','STORY ULTIMATE','WORLD EVENT')]})
        with patch('lib.gui.widgets.story_controls.click_game_point') as click,patch.object(w,'persist_story_run') as save:
            w.queue_story(e,now);click.assert_not_called();save.assert_called_with(False)
        self.assertIsNone(w.queue_engine.pending);self.assertIn('STORY ULTIMATE',w.queue_engine.completed)

    def test_pre_input_capture_is_discarded_before_any_controller_runs(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.adb_backend=Mock();w.adb_backend.last_input_at=now
        w.queue_observation=(ScreenEvidence('content_board'),now-timedelta(seconds=3))
        with patch.object(gui.QtCore.QTimer,'singleShot') as retry:
            w.show_evidence(ScreenEvidence('game_home'),now-timedelta(milliseconds=1),True)
        self.assertIsNone(w.queue_observation);retry.assert_called_once()

    def test_missing_world_event_board_tile_uses_home_shortcut_instead_of_looping(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.start_world_event(now)
        w.world_event_state.pending=True;w.world_event_state.started=False
        with patch('lib.gui.widgets.world_event_controls.click_game_point') as click:
            w.queue_world_event(ScreenEvidence('content_board',{'tiles':[]}),now)
            self.assertTrue(w.world_event_board_unavailable)
            self.assertEqual(w.world_event_waiting[0],('we_home','game_home'))
            w.queue_world_event(ScreenEvidence('we_home',{'event_point':None,'battle_tab':False}),now)
            self.assertEqual(click.call_args.args,(11,1020,335))

    def test_settings_popup_only_closes_without_changing_options(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        with patch('lib.gui.widgets.stuck_recovery.click_game_point') as click,patch.object(gui.QtCore.QTimer,'singleShot'):
            w.show_evidence(ScreenEvidence('game_settings',{'close_point':(640,645)}),now,True)
            self.assertEqual(click.call_args.kwargs['key'],'back')
            w.show_evidence(ScreenEvidence('game_settings',{'close_point':(640,645)}),now,True)
            self.assertEqual(click.call_args.args,(11,640,645))

    def test_android_back_never_interrupts_pending_auto_run(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        for mode in ('STORY ULTIMATE','TIMELINE BATTLE','OTHERWORLD BATTLE','TEAM BATTLE ARENA'):
            w.queue_engine.pending=(gui.reset_period(now),mode,1)
            with patch('lib.gui.widgets.stuck_recovery.click_game_point') as click:
                w.navigation_unsure_since=now-timedelta(seconds=20)
                w.navigation_back_recovery(ScreenEvidence('unknown'),now)
                w.navigation_back_recovery(ScreenEvidence('external_link_notice',{'cancel_point':(539,538)}),now)
                click.assert_not_called()

    def test_unknown_navigation_gets_two_bounded_android_backs(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.navigation_unsure_backs=0
        with patch('lib.gui.widgets.stuck_recovery.click_game_point') as click,patch.object(gui.QtCore.QTimer,'singleShot'):
            for _ in range(2):
                w.navigation_unsure_since=now-timedelta(seconds=7)
                self.assertTrue(w.navigation_back_recovery(ScreenEvidence('unknown'),now))
            self.assertFalse(w.navigation_back_recovery(ScreenEvidence('unknown'),now))
            self.assertEqual(click.call_count,2)
            self.assertEqual(click.call_args.kwargs['key'],'back')

    def test_dispatch_claim_loading_is_protected_from_android_back(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.start_dispatch_supplies(now);w.dispatch_supply_state.pending='all';w.dispatch_supply_state.claim_started=now
        w.navigation_unsure_since=now-timedelta(seconds=20)
        with patch('lib.gui.widgets.stuck_recovery.click_game_point') as click,patch('lib.gui.widgets.dispatch_supplies_controls.click_game_point') as dispatch_click:
            self.assertFalse(w.navigation_back_recovery(ScreenEvidence('unknown'),now))
            w.queue_dispatch_supplies(ScreenEvidence('unknown'),now)
            click.assert_not_called();dispatch_click.assert_not_called()
        self.assertTrue(w.dispatch_supply_active);self.assertEqual(w.dispatch_supply_state.pending,'all')

    def test_dispatch_claim_uses_session_deadline_and_accepts_empty_map(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.start_dispatch_supplies(now)
        ready=ScreenEvidence('dispatch_supplies_map',{'cards':[dict(key='MIDTOWN',pink_dot=True)],'signature':(),
            'claim_all_verified':True,'claim_all_point':(708,670)})
        with patch('lib.gui.widgets.dispatch_supplies_controls.click_game_point') as click:
            w.queue_dispatch_supplies(ready,now);click.assert_called_once()
            self.assertIsNone(w.dispatch_supply_waiting)
            w.dispatch_supply_state.claim_started=now-timedelta(seconds=30)
            w.queue_dispatch_supplies(ScreenEvidence('unknown'),now)
            self.assertTrue(w.dispatch_supply_active);self.assertEqual(click.call_count,1)
            with patch.object(w,'finish_dispatch_supplies') as finish:
                w.queue_dispatch_supplies(ScreenEvidence('dispatch_supply_empty_map',{'fill':0}),now)
                finish.assert_called_once_with()
            self.assertEqual(w.dispatch_supply_state.claimed,1)

    def test_stop_start_holds_previous_submission_on_verified_home(self):
        w=self.window;now=datetime.now(timezone.utc);self.clear_gbr(now);w.queue_engine.start(now)
        w.queue_engine.pending=(gui.reset_period(now),'TIMELINE BATTLE',2);w.queue_target='TIMELINE BATTLE';w.arena_started=now
        w.toggle_queue();self.assertFalse(w.queue_engine.running)
        w.toggle_queue();self.assertTrue(w.queue_engine.running);self.assertTrue(w.queue_fresh_pass)
        home=ScreenEvidence('game_home',{'home_controls_verified':True})
        self.assertTrue(w.fresh_queue_home_check(home,now))
        self.assertIsNotNone(w.queue_engine.pending)
        w.queue_fresh_home_seen=now-timedelta(seconds=4)
        self.assertTrue(w.fresh_queue_home_check(home,now))
        self.assertIsNone(w.queue_engine.pending);self.assertIsNone(w.queue_target)
        self.assertIn('TIMELINE BATTLE',w.queue_held);self.assertNotIn('TIMELINE BATTLE',w.queue_engine.completed)
        self.assertIn('CUTTING CABLE',w.planned_modes());self.assertEqual(w.queue_phase,'navigate_board')

    def test_fresh_pass_never_releases_submission_from_countdown_or_generic_home(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_fresh_pass=True
        pending=(gui.reset_period(now),'TIMELINE BATTLE',2);w.queue_engine.pending=pending
        for evidence in (ScreenEvidence('arena_result'),ScreenEvidence('game_home'),ScreenEvidence('unknown')):
            self.assertFalse(w.fresh_queue_home_check(evidence,now))
        self.assertEqual(w.queue_engine.pending,pending)

    def test_restored_repeat_full_home_reconciles_fresh_board(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='TIMELINE BATTLE'
        w.queue_engine.pending=(gui.reset_period(now),w.queue_target,2);w.arena_started=now-timedelta(minutes=20);w.arena_resumed=True
        home=ScreenEvidence('game_home',{'home_controls_verified':True})
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            w.queue_arena(home,now);click.assert_not_called()
            w.arena_home_seen=now-timedelta(seconds=4);w.queue_arena(home,now)
            self.assertEqual(click.call_args.args,(11,1249,36));self.assertFalse(w.arena_repeat_finished)
            click.reset_mock()
            w.queue_arena(ScreenEvidence('content_board',{'tiles':[{'mode':w.queue_target,'remaining':0,'total':5}]}),now)
            click.assert_not_called()
        self.assertIsNone(w.queue_engine.pending);self.assertIn('TIMELINE BATTLE',w.queue_engine.completed)

    def test_timeline_only_terminal_notice_unlocks_result_home(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='TIMELINE BATTLE'
        w.queue_engine.pending=(gui.reset_period(now),w.queue_target,2);w.arena_started=now
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            for _ in range(5):
                w.queue_arena(ScreenEvidence('arena_result',{'mode':w.queue_target,'point':(870,669)}),now)
            click.assert_not_called()
            w.queue_arena(ScreenEvidence('arena_exhausted',{'mode':w.queue_target,'point':(755,604)}),now)
            self.assertTrue(w.arena_repeat_finished);w.persist_pending_clear.assert_called()
            self.assertEqual(click.call_args.args,(11,755,604))
            w.queue_arena(ScreenEvidence('arena_result',{'mode':w.queue_target,'point':(870,669)}),now)
        self.assertIn('TIMELINE BATTLE',w.queue_engine.completed);self.assertIsNone(w.queue_engine.pending)
    def test_story_transitions_and_false_auto_checkbox_never_send_input(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='STORY ULTIMATE'
        w.story_started=now-timedelta(minutes=50);w.queue_engine.pending=(gui.reset_period(now),'STORY ULTIMATE',1)
        with patch('lib.gui.widgets.story_controls.click_game_point') as click,patch.object(w,'persist_story_run') as save:
            for e in (ScreenEvidence('story_result',{'point':(954,669)}),ScreenEvidence('story_battle',{'auto_on':False}),ScreenEvidence('arena_power',{'finished':True}),ScreenEvidence()):
                w.queue_story(e,now)
            click.assert_not_called();save.assert_not_called()
        self.assertIsNotNone(w.queue_engine.pending)
    def test_timeline_recovery_does_not_restart_or_navigate_during_repeat(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='TIMELINE BATTLE'
        pending=(gui.reset_period(now),w.queue_target,2);w.queue_engine.pending=pending
        with patch('lib.gui.widgets.stuck_recovery.RestartTask') as restart,patch('lib.gui.widgets.stuck_recovery.click_game_point') as click:
            w.recover_stuck_queue('OCR error between rounds');w.restart_stuck_game()
            restart.assert_not_called();click.assert_not_called()
        self.assertEqual(w.queue_engine.pending,pending)
    def test_unfinished_trivia_does_not_block_next_farm_navigation(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='SINISTER SCHEMES';self.clear_gbr(now)
        e=gui.ScreenReader().read(Path(__file__).parent/'fixtures/trivia_start_current.png',resource_check=True)
        self.assertEqual(e.screen,'challenge_navigation')
        with patch.object(w,'queue_send_point') as send:
            w.queue_navigate_board(e,now)
            send.assert_called_once_with((1249,36),'navigate_board',('navigation_menu',))
    def test_story_navigation_failure_defers_without_stopping_other_tasks(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='STORY ULTIMATE'
        self.assertFalse(w.story_restart_protected())
        w.recover_stuck_queue('Unrecognized Story preparation')
        self.assertTrue(w.queue_engine.running);self.assertIsNone(w.queue_target)
        self.assertIn('STORY ULTIMATE',w.queue_deferred);self.assertTrue(w.queue_recovering)
    def test_unrecognized_running_story_keeps_durable_launch_protection(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='STORY ULTIMATE'
        pending=(gui.reset_period(now),'STORY ULTIMATE',1);w.queue_engine.pending=pending
        w.story_started=now-timedelta(minutes=5);w.story_unknown_since=now-timedelta(seconds=91)
        with patch.object(w,'persist_story_run') as persist:
            w.queue_story(ScreenEvidence(),now);persist.assert_not_called()
        self.assertEqual(w.queue_engine.pending,pending);self.assertTrue(w.queue_engine.running)
    def test_world_event_finished_run_verifies_via_board_when_home_shortcut_disappears(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.start_world_event(now)
        w.world_event_state.pending=True;w.world_event_state.started=False
        with patch('lib.gui.widgets.world_event_controls.click_game_point') as click:
            w.queue_world_event(ScreenEvidence('we_home',{'event_point':None,'battle_tab':False}),now)
            self.assertEqual(click.call_args.args,(11,1249,36))
            w.queue_world_event(ScreenEvidence('navigation_menu'),now)
            self.assertEqual(click.call_args.args,(11,630,642))
    def test_unsupported_trivia_retry_survives_bot_reload_without_claiming_done(self):
        w=self.window;now=datetime.now(timezone.utc);w.trivia_period=None
        w.trivia_session=Mock(done=False,message='Unknown layout')
        w.finish_trivia('Unknown layout');w.init_trivia()
        self.assertGreater(w.trivia_retry_at,now);self.assertIsNone(w.trivia_period)
    def test_closed_epic_result_can_navigate_to_next_mission(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='CUTTING CABLE';self.clear_gbr(now)
        e=gui.ScreenReader().read(Path(__file__).parent/'fixtures/post_epic_navigation_current.png',resource_check=True)
        self.assertEqual(e.screen,'mission_preparation')
        with patch.object(w,'queue_send_point') as send:
            w.queue_navigate_board(e,now)
            send.assert_called_once_with((1249,36),'navigate_board',('navigation_menu',))
    def test_unsure_outcomes_wait_for_daily_queue_then_verify_without_replay(self):
        w=self.window;now=datetime.now(timezone.utc);self.clear_gbr(now);w.queue_engine.start(now)
        w.queues[0]=[{'mode':m,'enabled':True} for m in ('CUTTING CABLE','TIMELINE BATTLE')]
        w.queue_held={'TIMELINE BATTLE'};w.queue_held_period=gui.reset_period(now)
        w.queue_tick();self.assertEqual(w.queue_target,'CUTTING CABLE');self.assertIsNone(w.review_mode)
        w.queue_target=None;w.queue_engine.completed.add('CUTTING CABLE');w.queue_tick()
        self.assertEqual(w.review_mode,'TIMELINE BATTLE');self.assertEqual(w.queue_phase,'uncertain_review')
        with patch('lib.gui.widgets.uncertain_review.click_game_point') as click:
            w.queue_uncertain_review(ScreenEvidence('game_home'),now)
            self.assertEqual(click.call_args.args,(11,1249,36))
            w.queue_uncertain_review(ScreenEvidence('navigation_menu'),now)
            self.assertEqual(click.call_args.args,(11,630,642))
            w.queue_uncertain_review(ScreenEvidence('content_board',{'tiles':[{'mode':'TIMELINE BATTLE','remaining':0,'total':5}]}),now)
        self.assertIn('TIMELINE BATTLE',w.queue_engine.completed);self.assertNotIn('TIMELINE BATTLE',w.queue_held)
        self.assertIsNone(w.review_mode);self.assertIsNone(w.queue_engine.pending)
    def test_unsure_positive_count_returns_to_normal_cost_checks(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.queues[0]=[{'mode':'CUTTING CABLE','enabled':True}];w.queue_held={'CUTTING CABLE'}
        self.assertTrue(w.start_uncertain_review(now))
        with patch('lib.gui.widgets.uncertain_review.click_game_point') as click:
            w.queue_uncertain_review(ScreenEvidence('content_board',{'tiles':[{'mode':'CUTTING CABLE','remaining':2,'total':3}]}),now)
            click.assert_not_called()
        self.assertNotIn('CUTTING CABLE',w.queue_held);self.assertNotIn('CUTTING CABLE',w.queue_engine.completed)
        self.assertIsNone(w.queue_engine.pending);self.assertIsNone(w.review_mode)
    def test_unreadable_review_keeps_hold_and_does_not_loop(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.queues[0]=[{'mode':'CUTTING CABLE','enabled':True}];w.queue_held={'CUTTING CABLE'}
        w.start_uncertain_review(now)
        w.queue_uncertain_review(ScreenEvidence('content_board',{'tiles':[{'mode':'CUTTING CABLE','remaining':None}]}),now)
        self.assertIn('CUTTING CABLE',w.queue_held);self.assertFalse(w.start_uncertain_review(now))
    def test_review_cannot_interrupt_a_submitted_run(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_held={'CUTTING CABLE'}
        w.queue_engine.pending=(gui.reset_period(now),'OTHERWORLD BATTLE',5)
        self.assertFalse(w.start_uncertain_review(now))
    def test_alliance_already_scored_moves_on_without_record_challenge(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='ALLIANCE BATTLE'
        with patch.object(gui,'click_game_point') as click:
            w.queue_read_alliance(ScreenEvidence('alliance_normal_done',{'variant':'NORMAL','score':210500}),now)
            self.assertEqual(click.call_args.args,(11,1185,36))
        self.assertIn('ALLIANCE BATTLE',w.queue_engine.completed);self.assertIsNone(w.queue_engine.pending)
    def test_result_mode_cannot_control_a_different_arena(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        for mode in ('TIMELINE BATTLE','OTHERWORLD BATTLE','TEAM BATTLE ARENA'):
            w.queue_target=mode;w.queue_engine.pending=(gui.reset_period(now),mode,4);w.arena_repeat_finished=True
            with patch('lib.gui.widgets.arena_controls.click_game_point') as click:
                for detected in (None,*[m for m in ('TIMELINE BATTLE','OTHERWORLD BATTLE','TEAM BATTLE ARENA') if m!=mode]):
                    w.queue_arena(ScreenEvidence('arena_result',{'mode':detected,'point':(901,659)}),now)
                click.assert_not_called()
            self.assertEqual(w.queue_engine.pending[1],mode)
    def test_global_summary_cannot_release_another_submitted_mode(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        pending=(gui.reset_period(now),'OTHERWORLD BATTLE',5);w.queue_engine.pending=pending
        for screen in ('story_ended','team_arena_ended'):
            w.queue_observation=(ScreenEvidence(screen,{'runs':5,'point':(640,603)}),now)
            with patch.object(gui,'click_game_point') as click:w.advance_queue();click.assert_not_called()
            self.assertEqual(w.queue_engine.pending,pending)
    def test_alliance_board_without_numeric_counter_opens_normal_verification(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='ALLIANCE BATTLE'
        e=ScreenEvidence('content_board',{'tiles':[{'mode':'ALLIANCE BATTLE','remaining':None,'point':(252,431)}]})
        with patch.object(w,'queue_send_point') as click:
            w.queue_read_board(e,now)
            click.assert_called_once_with((252,431),'alliance',('alliance_select_normal','alliance_normal_ready','alliance_normal_setup','alliance_normal_done','alliance_weekly_skip'))
            expected=click.call_args.args[2]
        w.queue_phase='alliance';w.queue_waiting=(expected,now)
        w.queue_observation=(ScreenEvidence('alliance_normal_done',{'variant':'NORMAL','score':210500}),now)
        with patch.object(gui,'click_game_point'):w.advance_queue()
        self.assertIn('ALLIANCE BATTLE',w.queue_engine.completed);self.assertIsNone(w.queue_waiting)
    def test_team_arena_completes_all_remaining_four_not_only_five(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.queue_engine.pending=(gui.reset_period(now),'TEAM BATTLE ARENA',4)
        w.queue_observation=(ScreenEvidence('team_arena_ended',{'runs':4,'point':(640,603)}),now)
        with patch.object(gui,'click_game_point') as click:w.advance_queue();click.assert_called_once()
        self.assertIsNone(w.queue_engine.pending);self.assertIn('TEAM BATTLE ARENA',w.queue_engine.completed)
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            w.queue_arena(ScreenEvidence('arena_result',{'mode':'TEAM BATTLE ARENA','point':(901,659)}),now)
            self.assertEqual(click.call_args.args,(11,901,659))
        self.assertIsNone(w.queue_target);self.assertEqual(w.queue_phase,'navigate_board')
    def test_team_arena_partial_batch_only_authorizes_verification(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.queue_engine.pending=(gui.reset_period(now),'TEAM BATTLE ARENA',4)
        w.queue_observation=(ScreenEvidence('team_arena_ended',{'runs':3,'point':(640,603)}),now)
        with patch.object(gui,'click_game_point'):w.advance_queue()
        self.assertNotIn('TEAM BATTLE ARENA',w.queue_engine.completed)
        self.assertTrue(w.arena_repeat_finished);w.persist_pending_clear.assert_called()

    def test_completed_team_arena_releases_task_after_result_back_navigation(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='TEAM BATTLE ARENA';w.queue_phase='arena'
        w.queue_engine.completed.add('TEAM BATTLE ARENA')
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            w.queue_arena(ScreenEvidence('game_home',{'home_controls_verified':True}),now);click.assert_not_called()
        self.assertIsNone(w.queue_target);self.assertEqual(w.queue_phase,'navigate_board');self.assertIsNone(w.queue_wake)

    def test_completed_cache_never_releases_a_still_pending_arena(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='TEAM BATTLE ARENA'
        pending=(gui.reset_period(now),w.queue_target,5);w.queue_engine.pending=pending;w.queue_engine.completed.add(w.queue_target);w.arena_started=now
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            w.queue_arena(ScreenEvidence('game_home',{'home_controls_verified':True}),now);click.assert_not_called()
        self.assertEqual(w.queue_engine.pending,pending);self.assertEqual(w.queue_target,'TEAM BATTLE ARENA')
    def test_finished_otherworld_returns_from_home_verifies_zero_then_continues(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='OTHERWORLD BATTLE'
        w.queue_engine.pending=(gui.reset_period(now),w.queue_target,5);w.arena_started=now
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            w.queue_arena(ScreenEvidence('arena_repeat_ended',{'mode':w.queue_target,'point':(640,603)}),now)
            self.assertTrue(w.arena_repeat_finished);w.persist_pending_clear.assert_called()
            w.queue_arena(ScreenEvidence('arena_result',{'mode':w.queue_target,'point':(950,672)}),now)
            w.queue_arena(ScreenEvidence('game_home'),now)
            self.assertEqual(click.call_args.args,(11,1249,36))
            w.queue_arena(ScreenEvidence('navigation_menu'),now)
            self.assertEqual(click.call_args.args,(11,491,642))
            w.queue_arena(ScreenEvidence('arena_selector',{'cards':{'OTHERWORLD BATTLE':(491,376)}}),now)
            self.assertEqual(click.call_args.args,(11,491,376))
            w.queue_arena(ScreenEvidence('otherworld_lobby',{'mode':'OTHERWORLD BATTLE','entries':(0,5)}),now)
        self.assertIsNone(w.queue_engine.pending);self.assertIn('OTHERWORLD BATTLE',w.queue_engine.completed)
        self.assertIsNone(w.queue_target);self.assertEqual(w.queue_phase,'navigate_board')
    def test_running_repeat_does_not_navigate_from_home_or_board(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='OTHERWORLD BATTLE'
        w.queue_engine.pending=(gui.reset_period(now),w.queue_target,5);w.arena_started=now
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            w.queue_arena(ScreenEvidence('game_home'),now)
            w.queue_arena(ScreenEvidence('content_board',{'tiles':[{'mode':w.queue_target,'remaining':0,'total':5}]}),now)
            click.assert_not_called()
        self.assertIsNotNone(w.queue_engine.pending)
    def test_timeline_capacity_notice_requires_pending_and_is_not_repeated(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='TIMELINE BATTLE'
        e=ScreenEvidence('timeline_glory_cap',{'point':(742,536)})
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            w.queue_arena(e,now);click.assert_not_called()
            w.queue_engine.pending=(gui.reset_period(now),w.queue_target,5)
            w.queue_arena(e,now);click.assert_called_once()
            w.queue_arena(e,now);click.assert_called_once()
    def test_world_event_can_exit_to_other_tasks_without_pixel_perfect_menu_icon(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='TIMELINE BATTLE'
        with patch.object(w,'queue_send_point') as send:
            w.queue_navigate_board(ScreenEvidence('world_event',{'already_done':True}),now)
            send.assert_called_once_with((1249,36),'navigate_board',('navigation_menu',))

    def test_acquire_reward_popup_dismisses_only_before_repeat_submission(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='TEAM BATTLE ARENA'
        e=ScreenEvidence('arena_acquire',{'mode':w.queue_target,'point':(640,585)})
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            w.queue_arena(e,now);self.assertEqual(click.call_args.args,(11,640,585))
            click.reset_mock();w.queue_engine.pending=(gui.reset_period(now),w.queue_target,5);w.arena_started=now
            w.queue_arena(e,now);click.assert_not_called()

    def test_explicit_startup_request_waits_for_verified_background_frame(self):
        from PIL import Image
        from io import BytesIO
        w=self.window;now=datetime.now(timezone.utc);backend=Mock(connected=True)
        w.adb_backend=backend;w.start_queue_after_connect=True;w.toggle_queue=Mock()
        image=Image.new('RGB',(1280,720),'blue');raw=BytesIO();image.save(raw,format='PNG')
        w.adb_frame_ready(backend,image,raw.getvalue(),now)
        self.app.processEvents()
        w.toggle_queue.assert_called_once();self.assertFalse(w.start_queue_after_connect)

    def test_expired_restored_arena_cannot_navigate_without_repeat_end(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        pending=(gui.reset_period(now),'TEAM BATTLE ARENA',5);w.queue_target=pending[1];w.queue_engine.pending=pending
        w.arena_started=now-timedelta(hours=3);w.arena_resumed=True
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            w.queue_arena(ScreenEvidence('game_home'),now)
            click.assert_not_called();self.assertEqual(w.queue_engine.pending,pending)
            w.queue_arena(ScreenEvidence('navigation_menu'),now)
            click.assert_not_called();self.assertEqual(w.queue_engine.pending,pending)

    def test_expired_restored_arena_reconciles_fresh_board_without_starting(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.queue_target='TEAM BATTLE ARENA';w.queue_engine.pending=(gui.reset_period(now),w.queue_target,5)
        w.arena_started=now-timedelta(hours=3);w.arena_resumed=True
        w.arena_repeat_finished=True
        board=ScreenEvidence('content_board',{'tiles':[{'mode':'TEAM BATTLE ARENA','remaining':3,'total':5}]})
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            w.queue_arena(board,now);click.assert_not_called()
        self.assertIsNone(w.queue_engine.pending);self.assertNotIn('TEAM BATTLE ARENA',w.queue_engine.completed)
        self.assertTrue(w.queue_engine.running);self.assertEqual(w.queue_phase,'navigate_board')

    def test_restored_arena_cannot_reconcile_from_generic_or_other_mode_screen(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        pending=(gui.reset_period(now),'TEAM BATTLE ARENA',5);w.queue_target=pending[1];w.queue_engine.pending=pending
        w.arena_started=now-timedelta(hours=3);w.arena_resumed=True
        for evidence in (ScreenEvidence('unknown'),ScreenEvidence('content_board',{'tiles':[{'mode':'OTHERWORLD BATTLE','remaining':0,'total':5}]})):
            self.assertFalse(w.reconcile_restored_arena(evidence,now,now));self.assertEqual(w.queue_engine.pending,pending)

    def test_connection_failure_stops_queue_instead_of_logging_every_second(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        backend=Mock(connected=False);w.adb_backend=backend
        w.adb_frame_failed(backend,'Instance unavailable')
        self.assertFalse(w.queue_engine.running);self.assertIsNone(w.handle)

    def test_launcher_stops_polling_but_preserves_uncertain_arena(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        pending=(gui.reset_period(now),'TEAM BATTLE ARENA',5);w.queue_engine.pending=pending
        with patch.object(gui,'click_game_point') as click,patch.object(w,'restart_stuck_game') as restart:
            w.show_evidence(ScreenEvidence('android_home',{'launcher_verified':True}),now,True)
            click.assert_not_called();restart.assert_not_called()
        self.assertFalse(w.queue_engine.running);self.assertEqual(w.queue_engine.pending,pending)
        w.persist_pending_clear.assert_called();self.assertNotIn('TEAM BATTLE ARENA',w.queue_engine.completed)

    def test_stale_or_saved_launcher_does_not_stop_live_queue(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.show_evidence(ScreenEvidence('android_home'),now-timedelta(seconds=31),True)
        self.assertTrue(w.queue_engine.running)
        w.show_evidence(ScreenEvidence('android_home'),now,False)
        self.assertTrue(w.queue_engine.running)

    def test_gbr_lobby_can_navigate_to_board_for_free_modes(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='TIMELINE BATTLE'
        with patch.object(w,'queue_send_point') as send:
            w.queue_navigate_board(ScreenEvidence('gbr_main'),now)
            send.assert_called_once_with((1249,36),'navigate_board',('navigation_menu',))

    def test_nonzero_gbr_counter_returns_to_free_modes_without_strip_loop(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.resource_active=True;w.resource_started=now;w.resource_waiting=None
        w.resource_observation=(ScreenEvidence('gbr_main',{'soul':(165,165)}),now)
        w.latest_counters={'soul':((165,165),now)}
        with patch.object(gui,'perform_navigation') as nav:
            w.advance_resource_check();nav.assert_not_called()
        self.assertFalse(w.resource_active);self.assertTrue(w.queue_engine.running)
        self.assertFalse(w.raid_gate.cleared(now));self.assertEqual(w.queue_phase,'navigate_board')

    def test_arena_never_starts_when_submission_cannot_be_saved(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.queue_target='TEAM BATTLE ARENA';w.arena_remaining=5;w.arena_entry_verified=now
        with patch.object(w,'persist_pending_clear',return_value=False),patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            w.queue_arena(ScreenEvidence('team_arena_repeat',{'selected':5,'ticket_cost':12}),now)
            click.assert_not_called()
        self.assertFalse(w.queue_engine.running);self.assertIsNone(w.queue_engine.pending)

    def test_dark_theme_and_status_does_not_change_queue(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        self.assertIn('#111827',w.styleSheet())
        w.queue_engine.completed.add('CUTTING CABLE')
        w.refresh_task_statuses()
        self.assertIn('Done today',w.queue_list_widget.item(0).text())
        self.assertEqual(w.queues[0],[{'mode':'CUTTING CABLE','enabled':True}])

    def test_story_protected_from_restart_even_when_capture_fails(self):
        w=self.window;now=datetime.now(timezone.utc)
        w.queue_engine.start(now);w.queue_target='STORY ULTIMATE'
        w.queue_engine.pending=(gui.reset_period(now),'STORY ULTIMATE',1);w.story_started=now
        w.adb_backend=Mock();w.adb_backend.connected=True
        w.restart_stuck_game=Mock()
        for _ in range(5):w.adb_frame_failed(w.adb_backend,'blank')
        w.restart_stuck_game.assert_not_called()
        self.assertTrue(w.queue_engine.running)

    def test_home_recovery_escalates_to_game_restart(self):
        w=self.window;now=datetime.now(timezone.utc)
        w.queue_engine.start(now);w.queue_recovering=True;w.queue_recovery_steps=8
        w.restart_stuck_game=Mock()
        w.queue_recover_home(ScreenEvidence(),now)
        w.restart_stuck_game.assert_called_once()
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        log_root=Path(__file__).resolve().parents[3]/'work/gui-log-tests'
        log_root.mkdir(parents=True,exist_ok=True)
        self.log_directory=TemporaryDirectory(dir=log_root)
        self.patches=[patch.object(gui.ModernMainWindow,name) for name in ("_load","_save","load_gbr_clearance","persist_gbr_clearance","load_objective_cache","persist_objective_cache","load_completed_missions","persist_completed_missions","load_story_run","load_pending_clear","persist_pending_clear")]
        self.patches.append(patch.object(gui,'LOG_PATH',Path(self.log_directory.name)/'queue.log'))
        from lib.world_event import WorldEventState
        self.patches.append(patch.object(WorldEventState,'load',side_effect=lambda now:WorldEventState(now)))
        self.patches.append(patch.object(WorldEventState,'save'))
        from lib.gui.widgets import trivia_controls
        self.patches.append(patch.object(trivia_controls,'TRIVIA_CACHE',Path(self.log_directory.name)/'trivia.json'))
        for item in self.patches:item.start()
        self.window=gui.ModernMainWindow()
        self.window.enable_board_preflight=False
        self.window.dispatch_supply_next=datetime.max.replace(tzinfo=timezone.utc)
        self.window.timer.stop();self.window.queue_timer.stop()
        self.window.handle=11
        self.window.objective_plan=MissionPlan(0,False,0)
        self.window.objective_period=gui.reset_period(datetime.now(timezone.utc))
        self.window.objective_refresh_due=False
        self.window.trivia_period=gui.reset_period(datetime.now(timezone.utc))
        self.window.scan_live=Mock()
        self.window.queues[0]=[{"mode":"CUTTING CABLE","enabled":True}]
        self.window._populate()

    def tearDown(self):
        self.window.busy=False
        self.window.close()
        from lib.background_input import set_backend
        set_backend()
        for item in self.patches:item.stop()
        self.log_directory.cleanup()

    def clear_gbr(self,now):
        for key,value in (("soul",(0,165)),("seed",(0,300))):
            self.window.raid_gate.observe(key,value,now,now)

    def test_checked_gbr_is_reused_by_queue_and_resource_buttons(self):
        now=datetime.now(timezone.utc);w=self.window;self.clear_gbr(now)
        with patch.object(w,'check_resources') as check,patch.object(w,'render_queue_status') as status:
            w.check_queue();check.assert_not_called();status.assert_called_once()
        w.check_resources()
        self.assertFalse(w.resource_active);w.scan_live.assert_not_called()
        w.queue_engine.start(now);w.queue_target='CUTTING CABLE';w.queue_phase='board'
        with patch.object(w,'check_resources') as check:
            w.queue_tick();check.assert_not_called();w.scan_live.assert_called_once()
        w.stop_queue();w.scan_live.reset_mock();w.check_resources(force=True)
        self.assertTrue(w.resource_active);self.assertFalse(w.raid_gate.cleared(now))
        w.scan_live.assert_called_once()

    def test_objective_checks_reused_until_reset_and_can_be_forced(self):
        w=self.window
        w.check_objectives();self.assertFalse(w.objective_active);w.scan_live.assert_not_called()
        w.objective_period=None
        w.check_objectives();self.assertTrue(w.objective_active);w.scan_live.assert_called_once()
        w.objective_active=False

    def test_board_remembers_all_visible_done_quests_without_opening_them(self):
        now=self.prepare_sweep();w=self.window
        w.queue_target='CUTTING CABLE'
        board=ScreenEvidence('content_board',dict(tiles=[
            dict(mode='CUTTING CABLE',remaining=0),dict(mode='ENDING THE STRYFE',remaining=0)],accelerated_clear=True))
        with patch.object(gui,'click_game_point') as click:
            w.queue_read_board(board,now);click.assert_not_called()
        self.assertTrue({'CUTTING CABLE','ENDING THE STRYFE'}<=w.queue_engine.completed)
        self.assertIsNone(w.queue_target)

    def test_pending_clear_can_finish_from_verified_zero_entries(self):
        now=self.prepare_sweep();w=self.window
        w.queue_engine.pending=(gui.reset_period(now),'CUTTING CABLE',3)
        proof=ScreenEvidence('epic_preparation',dict(mode='CUTTING CABLE',remaining=0,preparation_verified=True))
        w.queue_read_sweep(proof,now)
        self.assertIsNone(w.queue_engine.pending)
        self.assertIn('CUTTING CABLE',w.queue_engine.completed)
        self.assertEqual(w.queue_phase,'navigate_board')

    def test_four_failures_hold_mission_and_recover_home_without_replay(self):
        now=self.prepare_sweep();w=self.window
        w.queue_engine.pending=(gui.reset_period(now),'CUTTING CABLE',3)
        for _ in range(4):w.queue_pause('Unrecognized result',10)
        self.assertTrue(w.queue_recovering)
        self.assertIsNone(w.queue_engine.pending)
        self.assertIn('CUTTING CABLE',w.queue_held)
        self.assertNotIn('CUTTING CABLE',w.planned_modes())
        self.assertNotIn('CUTTING CABLE',w.queue_engine.completed)
        with patch('lib.gui.widgets.stuck_recovery.click_game_point') as click:
            w.queue_recover_home(ScreenEvidence('unknown'),now)
            self.assertEqual(click.call_args.kwargs['key'],'back')
            w.queue_recover_home(ScreenEvidence('unknown',dict(menu_available=True)),now)
            self.assertEqual(click.call_args.args[1:3],(1249,36))
            w.queue_recover_home(ScreenEvidence('game_home'),now)
        self.assertFalse(w.queue_recovering)
        self.assertTrue(w.queue_engine.running)

    def test_resource_waits_do_not_skip_missions(self):
        self.prepare_sweep();w=self.window
        for _ in range(8):w.queue_pause('Need boost for full batch',60,stalled=False)
        self.assertFalse(w.queue_recovering);self.assertEqual(w.queue_held,set())

    def test_navigation_failure_defers_without_holding_until_reset(self):
        now=self.prepare_sweep();w=self.window
        for _ in range(4):w.queue_pause('Popup not recognized',10)
        self.assertTrue(w.queue_recovering);self.assertNotIn('CUTTING CABLE',w.queue_held)
        self.assertGreater(w.queue_deferred['CUTTING CABLE'],now)
        self.assertNotIn('CUTTING CABLE',w.eligible_modes(now))

    def test_background_scan_requests_worker_instead_of_blocking_capture(self):
        w=self.window
        del w.scan_live
        with patch.object(w,'request_adb_frame') as request,patch.object(w,'capture') as capture:
            w.scan_live()
            request.assert_called_once_with(for_scan=True)
            capture.assert_not_called()

    def test_stop_cancels_scan_waiting_for_background_frame(self):
        now=self.prepare_sweep();w=self.window
        w.frame_waiting_scan=True;w.adb_frame=(None,b'',now)
        w.stop_queue();w.adb_frame_finished()
        w.scan_live.assert_not_called()

    def test_waiting_queue_refreshes_preview_without_scanning_or_restarting_tasks(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.background_input=True;w.queue_target=None;w.queue_wake=gui.next_reset(now)
        with patch.object(w,'request_adb_frame') as request:
            w.refresh_preview();w.refresh_preview()
            request.assert_called_once_with()
        w.scan_live.assert_not_called();self.assertTrue(w.queue_engine.running)

    def test_queue_checks_trivia_before_waiting_and_remembers_same_reset(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.queue_target=None;w.queue_wake=gui.next_reset(now);w.trivia_period=None
        with patch.object(w,'check_trivia') as trivia:
            w.queue_tick();trivia.assert_called_once_with(automatic=True)
            w.trivia_period=gui.reset_period(now);w.queue_tick();self.assertEqual(trivia.call_count,1)

    def test_pending_battle_is_not_interrupted_by_due_trivia(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.trivia_period=None
        w.queue_engine.pending=(gui.reset_period(now),'TEAM BATTLE ARENA',5)
        with patch.object(w,'check_trivia') as trivia:w.queue_tick();trivia.assert_not_called()

    def test_idle_check_screen_resumes_after_frame_worker_finishes(self):
        w=self.window;now=datetime.now(timezone.utc)
        w.frame_waiting_scan=True;w.adb_frame=(None,b'',now)
        w.adb_frame_finished()
        w.scan_live.assert_called_once_with(frame=w.adb_frame)

    def test_passive_supplies_run_while_queue_waits_for_reset(self):
        now=datetime.now(timezone.utc);w=self.window
        w.queue_engine.start(now);w.queue_wake=gui.next_reset(now)
        w.dispatch_supply_next=now
        w.queue_tick()
        self.assertTrue(w.dispatch_supply_active);self.assertEqual(w.queue_phase,'dispatch_supplies')
        w.scan_live.assert_called_once()
        w.finish_dispatch_supplies()
        self.assertEqual(w.queue_wake,gui.next_reset(now))
        self.assertGreater(w.dispatch_supply_next,now)
        w.stop_queue();self.assertFalse(w.dispatch_supply_active)

    def test_epic_popup_inspects_preparation_then_submits_only_full_batch(self):
        now=self.prepare_sweep();w=self.window
        w.queue_target='BEGINNING OF THE CHAOS';w.queue_remaining=2
        modal=ScreenEvidence('sweep',dict(layout='epic',modal_verified=True,selected=2,ticket_unit=1,
            energy_available=100,boost_available=8,tickets_available=30,
            controls={'close_sweep':(872,555),'clear_batch':(640,555)}))
        prep=ScreenEvidence('epic_preparation',dict(mode=w.queue_target,remaining=2,
            energy_unit=4,boost_unit=4,preparation_verified=True,point=(560,684)))
        with patch('lib.queue_input.execute_sweep_control') as execute,patch.object(gui,'click_game_point') as click:
            w.queue_read_sweep(modal,now)
            self.assertEqual(execute.call_args.args[2],'close_sweep')
            self.assertIsNone(w.queue_engine.pending)
            w.queue_read_sweep(prep,now)
            self.assertEqual(click.call_args.args[1:3],(560,684))
            execute.reset_mock();w.queue_read_sweep(modal,now)
            self.assertEqual(execute.call_args.args[2],'clear_batch')
            self.assertEqual(w.queue_engine.pending[2],2)
            self.assertTrue(execute.call_args.kwargs['guard']())
            w.stop_queue();self.assertFalse(execute.call_args.kwargs['guard']())

    def test_epic_low_boost_closes_without_submitting_and_result_uses_close_only(self):
        now=self.prepare_sweep();w=self.window
        w.queue_target='BEGINNING OF THE CHAOS';w.queue_remaining=2
        prep=ScreenEvidence('epic_preparation',dict(mode=w.queue_target,remaining=2,
            energy_unit=4,boost_unit=4,preparation_verified=True))
        w.epic_preparation=(prep,now,w.queue_engine.generation)
        modal=ScreenEvidence('sweep',dict(layout='epic',modal_verified=True,selected=2,ticket_unit=1,
            energy_available=100,boost_available=7,tickets_available=30,
            controls={'close_sweep':(872,555),'clear_batch':(640,555)}))
        with patch('lib.queue_input.execute_sweep_control') as execute:
            w.queue_read_sweep(modal,now)
            self.assertEqual(execute.call_args.args[2],'close_sweep')
            self.assertIsNone(w.queue_engine.pending)
            w.queue_engine.pending=(gui.reset_period(now),w.queue_target,2)
            result=ScreenEvidence('sweep_result',dict(mode=w.queue_target,clears=2,result_verified=True,controls={'close_result':(880,676)}))
            w.queue_read_sweep(result,now)
            self.assertEqual(execute.call_args.args[2],'close_result')
            self.assertIsNone(w.queue_engine.pending)

    def test_epic_bad_modal_ocr_does_not_repeat_preparation_navigation(self):
        now=self.prepare_sweep();w=self.window
        w.epic_preparation=(ScreenEvidence('epic_preparation'),now,w.queue_engine.generation)
        modal=ScreenEvidence('sweep',{'layout':'epic','modal_verified':True},errors=['Quantity unreadable'])
        with patch('lib.queue_input.execute_sweep_control') as execute:
            w.queue_read_sweep(modal,now)
            execute.assert_not_called();self.assertIsNone(w.queue_engine.pending)
            self.assertGreater(w.queue_wake,now)

    def test_resource_swipes_stop_when_strip_position_does_not_change(self):
        now=datetime.now(timezone.utc);w=self.window
        w.resource_active=True;w.resource_started=now;w.resource_steps=0
        w.latest_counters={'soul':((0,165),now)}
        evidence=ScreenEvidence('gbr_main',{'reward_strip_verified':True,'strip_position':(None,111)})
        with patch.object(gui,'perform_navigation') as navigate,patch.object(gui.QtCore.QTimer,'singleShot'):
            for _ in range(3):
                w.resource_observation=(evidence,now);w.advance_resource_check()
            self.assertFalse(w.resource_active)
            self.assertEqual(navigate.call_count,2)
            self.assertIn('Reward strip stopped moving',w.logger_text.toPlainText())

    def test_start_stop_and_late_ocr_cannot_send_input(self):
        now=datetime.now(timezone.utc)
        self.clear_gbr(now)
        self.window.toggle_queue()
        self.assertTrue(self.window.queue_engine.running)
        self.assertEqual(self.window.run_queue_button.text(),"Stop Queue")
        self.assertTrue(self.window.queue_list_widget.isEnabled())
        self.assertFalse(self.window.queue_list_widget.item(0).flags()&gui.QtCore.Qt.ItemIsUserCheckable)
        self.window.stop_queue()
        self.assertFalse(self.window.queue_engine.running)
        with patch.object(gui,"click_game_point") as click:
            self.window.show_evidence(ScreenEvidence("content_board",{"tiles":[]}),now,True)
            self.window.advance_queue()
            self.window.queue_tick()
            click.assert_not_called()

    def test_cached_clearance_does_not_request_gbr_again(self):
        now=datetime.now(timezone.utc)
        self.clear_gbr(now)
        with patch.object(self.window,"check_resources") as check:
            self.window.toggle_queue()
            self.window.queue_tick()
            check.assert_not_called()

    def test_reset_requires_gbr_again_before_any_clear(self):
        now=datetime.now(timezone.utc)
        self.clear_gbr(now)
        self.window.toggle_queue()
        # Queue start now refreshes requirements before selecting boosted work.
        self.window.objective_active=False;self.window.objective_refresh_due=False
        after=gui.next_reset(now)
        self.window.trivia_period=gui.reset_period(after)
        with patch.object(gui,"datetime") as clock,patch.object(self.window,"check_resources") as check:
            clock.now.return_value=after
            self.window.queue_tick()
            check.assert_called_once()
            self.assertFalse(self.window.raid_gate.cleared(after))

    def test_no_enabled_energy_tasks_does_not_start(self):
        self.window.queues[0]=[{"mode":"WORLD BOSS","enabled":True}]
        self.window.toggle_queue()
        self.assertFalse(self.window.queue_engine.running)

    def sweep_evidence(self,boost=12,selected=3):
        return ScreenEvidence("sweep",{"mode":"CUTTING CABLE","selected":selected,
            "energy_total":12,"boost_total":12,"ticket_total":3,"crystal_total":0,
            "energy_available":100,"boost_available":boost,"tickets_available":30,
            "boosted":True,"sweep_verified":True})

    def prepare_sweep(self):
        now=datetime.now(timezone.utc)
        self.clear_gbr(now)
        self.window.queue_engine.start(now)
        self.window.queue_target="CUTTING CABLE"
        self.window.queue_remaining=3
        self.window.queue_phase="sweep"
        return now

    def test_full_batch_boost_shortage_waits_without_spending(self):
        now=self.prepare_sweep()
        with patch("lib.queue_input.execute_sweep_control") as execute:
            self.window.queue_read_sweep(self.sweep_evidence(boost=11),now)
            execute.assert_not_called()
        self.assertTrue(self.window.queue_engine.running)
        self.assertIsNone(self.window.queue_engine.pending)
        self.assertGreater(self.window.queue_wake,now)

    def test_full_batch_submission_has_live_stop_reset_guard(self):
        now=self.prepare_sweep()
        with patch("lib.queue_input.execute_sweep_control") as execute:
            self.window.queue_read_sweep(self.sweep_evidence(),now)
            self.assertEqual(execute.call_args.args[2],"clear_batch")
            guard=execute.call_args.kwargs["guard"]
            self.assertTrue(guard())
            self.window.stop_queue()
            self.assertFalse(guard())
        self.assertEqual(self.window.queue_engine.pending[2],3)

    def test_partial_batch_cannot_clear_and_max_does_not_spin(self):
        now=self.prepare_sweep()
        with patch("lib.queue_input.execute_sweep_control") as execute:
            self.window.queue_read_sweep(self.sweep_evidence(selected=2),now)
            self.assertEqual(execute.call_args.args[2],"select_max")
            execute.reset_mock()
            self.window.queue_read_sweep(self.sweep_evidence(selected=2),now)
            execute.assert_not_called()
        self.assertIsNone(self.window.queue_engine.pending)

    def test_result_verification_advances_once(self):
        now=self.prepare_sweep()
        self.window.queue_engine.authorize(__import__("lib.daily_queue",fromlist=["BatchEvidence"]).BatchEvidence(
            "CUTTING CABLE",3,3,12,12,3,100,12,30,now,0,True,True),now)
        result=ScreenEvidence("sweep_result",{"mode":"CUTTING CABLE","result_verified":True})
        with patch("lib.queue_input.execute_sweep_control") as execute:
            self.window.queue_read_sweep(result,now)
            self.assertEqual(execute.call_args.args[2],"close_result")
        self.assertIsNone(self.window.queue_engine.pending)
        self.assertIn("CUTTING CABLE",self.window.queue_engine.completed)

    def test_session_notice_clicks_once_and_invalidates_old_resources(self):
        now=self.prepare_sweep()
        self.window.latest_counters={"soul":((0,165),now),"seed":((0,300),now)}
        with patch.object(gui,"click_game_point") as click:
            notice=ScreenEvidence("session_replaced",{"ok_point":(640,538)})
            self.window.show_evidence(notice,now,True)
            self.window.show_evidence(notice,now,True)
            click.assert_called_once()
            self.assertEqual(click.call_args.args,(11,640,538))
        self.assertFalse(self.window.raid_gate.cleared(now))
        self.assertEqual(self.window.latest_counters,{})
        self.assertEqual(self.window.queue_phase,"navigate_board")

    def test_stopped_or_saved_session_notice_cannot_click(self):
        now=datetime.now(timezone.utc)
        with patch.object(gui,"click_game_point") as click:
            self.window.show_evidence(ScreenEvidence("session_replaced"),now,True)
            self.window.show_evidence(ScreenEvidence("session_replaced"),now,False)
            click.assert_not_called()

    def test_normal_alliance_result_never_selects_extreme_followup(self):
        now=datetime.now(timezone.utc)
        self.window.queue_engine.start(now)
        self.window.queue_engine.pending=(gui.reset_period(now),"ALLIANCE BATTLE",1)
        self.window.queue_target="ALLIANCE BATTLE"
        with patch.object(gui,"click_game_point") as click:
            self.window.queue_read_alliance(ScreenEvidence("alliance_result",{"score":166750,"result_verified":True}),now)
            self.assertEqual(click.call_args.args,(11,986,663))
        self.assertIn("ALLIANCE BATTLE",self.window.queue_engine.completed)
        self.assertIsNone(self.window.queue_engine.pending)

    def test_dimension_exact_quantity_uses_increment_not_max(self):
        now=self.prepare_sweep()
        self.window.queue_target="DIMENSION MISSION";self.window.queue_remaining=5
        evidence=self.sweep_evidence(selected=1)
        evidence.values["mode"]="DIMENSION MISSION"
        with patch("lib.queue_input.execute_sweep_control") as execute:
            self.window.queue_read_sweep(evidence,now)
            self.assertEqual(execute.call_args.args[2],"increment")
        self.assertIsNone(self.window.queue_engine.pending)

    def test_dimension_event_quest_quantity_above_five_uses_exact_selection(self):
        now=self.prepare_sweep();w=self.window;w.queue_target='DIMENSION MISSION';w.queue_remaining=7
        w.objective_plan=MissionPlan(7,False,0)
        evidence=self.sweep_evidence(selected=1);evidence.values['mode']='DIMENSION MISSION'
        with patch('lib.queue_input.execute_sweep_control') as execute:
            w.queue_read_sweep(evidence,now);self.assertEqual(execute.call_args.args[2],'increment')
        self.assertIsNone(w.queue_engine.pending)

    def test_objective_plan_controls_dimension_and_dispatch(self):
        self.window.queues[0]=[{"mode":"DIMENSION MISSION","enabled":True}]
        self.window.objective_plan=MissionPlan(0,False,0)
        self.assertNotIn("DIMENSION MISSION",self.window.planned_modes())
        self.window.objective_plan=MissionPlan(5,True,1)
        self.assertEqual(self.window.planned_modes(),["DIMENSION MISSION","DISPATCH 7-1"])

    def test_objective_navigation_waits_without_repeating_home_click(self):
        now=datetime.now(timezone.utc)
        self.window.objective_active=True
        self.window.objective_waiting=(("game_home",),now)
        self.window.objective_observation=(ScreenEvidence("daily_objectives"),now)
        with patch.object(gui,"click_game_point") as click:
            self.window.advance_objectives()
            click.assert_not_called()
        self.assertTrue(self.window.objective_active)
        self.window.objective_active=False

    def test_contribution_batch_does_not_complete_until_reward_claim(self):
        now=self.prepare_sweep()
        self.window.queue_target="DIMENSION MISSION"
        self.window.queue_engine.pending=(gui.reset_period(now),"DIMENSION MISSION",5)
        self.window.objective_plan=MissionPlan(5,True,0)
        e=ScreenEvidence("sweep_result",{"result_verified":True,"clears":5})
        with patch("lib.queue_input.execute_sweep_control"):
            self.window.queue_read_sweep(e,now)
        self.assertEqual(self.window.queue_phase,"dimension_claim")
        self.assertIsNotNone(self.window.queue_engine.pending)
        with patch.object(gui,"click_game_point") as click:
            self.window.queue_dimension_claim(ScreenEvidence("dimension_lobby",{"contribution":(60,60)}),now)
            self.assertEqual(click.call_args.args,(11,1215,665))
            self.window.queue_dimension_claim(ScreenEvidence("dimension_lobby",{"contribution":(60,60)}),now)
            self.assertEqual(click.call_count,1)
        self.window.queue_dimension_claim(ScreenEvidence("dimension_lobby",{"contribution":(0,60)}),now)
        self.assertIn("DIMENSION MISSION",self.window.queue_engine.completed)
        self.assertIsNone(self.window.queue_engine.pending)

    def test_world_event_checks_while_farming_waits_without_gbr(self):
        w=self.window;now=datetime.now(timezone.utc)
        w.queues[0].append({'mode':'WORLD EVENT','enabled':True})
        from lib.world_event import WorldEventState
        w.world_event_state=WorldEventState(now);w.queue_engine.start(now)
        w.queue_wake=now+timedelta(hours=1);w.queue_target='CUTTING CABLE'
        w.queue_tick()
        self.assertTrue(w.world_event_active);self.assertEqual(w.queue_phase,'world_event')
        self.assertEqual(w.world_event_resume,now+timedelta(hours=1));w.scan_live.assert_called_once()
        w.stop_queue();self.assertFalse(w.world_event_active)
    def test_world_event_zero_entries_cached_and_not_rechecked(self):
        w=self.window;now=datetime.now(timezone.utc)
        from lib.world_event import WorldEventState
        w.world_event_state=WorldEventState(now)
        for visit in range(3):
            stamp=now-timedelta(seconds=(2-visit)*5)
            w.world_event_state.lobby({'entries':(0,2)},now,observed=stamp,visit=visit)
        w.queues[0].append({'mode':'WORLD EVENT','enabled':True});w.queue_engine.start(now)
        w.queue_wake=now+timedelta(hours=1);w.queue_tick()
        self.assertFalse(w.world_event_active);w.scan_live.assert_not_called()
    def test_world_event_first_zero_reopens_page_without_claiming_completion(self):
        w=self.window;now=datetime.now(timezone.utc)
        from lib.world_event import WorldEventState
        w.world_event_state=WorldEventState(now);w.queue_engine.start(now);w.start_world_event(now)
        with patch('lib.world_event.WorldEventState.save'),patch('lib.gui.widgets.world_event_controls.click_game_point') as click:
            w.queue_world_event(ScreenEvidence('we_lobby',{'entries':(0,2),'best_score':123,'available':True}),now)
            self.assertEqual(click.call_args.args,(11,1185,36))
        self.assertFalse(w.world_event_state.done);self.assertTrue(w.world_event_active)
    def test_world_event_stopped_queue_never_inputs(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.start_world_event(now);w.stop_queue()
        with patch('lib.gui.widgets.world_event_controls.click_game_point') as click:
            w.queue_world_event(ScreenEvidence('we_confirm',{'entries':(1,2),'point':(748,512)}),now)
            click.assert_not_called()

    def test_world_event_loading_is_waited_for(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.start_world_event(now)
        with patch('lib.gui.widgets.world_event_controls.click_game_point') as click:
            w.queue_world_event(ScreenEvidence(),now)
            click.assert_not_called()
        self.assertTrue(w.world_event_active);self.assertGreater(w.queue_wake,now)
    def test_world_event_entry_is_latched_before_input_and_not_retried(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.start_world_event(now)
        from lib.world_event import WorldEventState
        w.world_event_state=WorldEventState(now)
        def sent(*args,**kwargs):self.assertTrue(w.world_event_state.pending)
        with patch('lib.world_event.WorldEventState.save'),patch('lib.gui.widgets.world_event_controls.click_game_point',side_effect=sent) as click:
            e=ScreenEvidence('we_confirm',{'entries':(1,2),'point':(748,512)})
            w.queue_world_event(e,now);w.queue_world_event(e,now)
            self.assertEqual(click.call_count,1)

    def test_world_event_visible_shortcut_wins_over_tab_recognition(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.start_world_event(now)
        with patch('lib.gui.widgets.world_event_controls.click_game_point') as click:
            w.queue_world_event(ScreenEvidence('we_home',{'battle_tab':False,'event_point':(1040,510)}),now)
            self.assertEqual(click.call_args.args,(11,1040,510))
        self.assertEqual(w.world_event_tab_attempts,0)
    def test_world_event_tab_selection_is_bounded(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.start_world_event(now)
        with patch('lib.world_event.WorldEventState.save'),patch('lib.gui.widgets.world_event_controls.click_game_point') as click:
            for _ in range(3):w.queue_world_event(ScreenEvidence('we_home',{'battle_tab':False,'event_point':None}),now)
            self.assertEqual(click.call_count,2)
        self.assertFalse(w.world_event_active)

    def test_world_event_navigation_failure_recovers_home_before_other_checks(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.start_world_event(now)
        w.world_event_waiting=(('we_confirm',),now-timedelta(seconds=61))
        with patch('lib.world_event.WorldEventState.save'):
            w.queue_world_event(ScreenEvidence('unknown'),now)
        self.assertFalse(w.world_event_active);self.assertTrue(w.queue_recovering)
        self.assertEqual(w.queue_phase,'recover_home')

    def test_gbr_blocks_only_boosted_modes(self):
        w=self.window;now=datetime.now(timezone.utc)
        w.queues[0]=[{'mode':m,'enabled':True} for m in ['CUTTING CABLE','TIMELINE BATTLE','OTHERWORLD BATTLE','ALLIANCE BATTLE','STORY ULTIMATE']]
        self.assertEqual(set(w.eligible_modes(now)),{'TIMELINE BATTLE','OTHERWORLD BATTLE','ALLIANCE BATTLE','STORY ULTIMATE'})
        self.clear_gbr(now);self.assertIn('CUTTING CABLE',w.eligible_modes(now))
    def test_incomplete_gbr_releases_target_and_keeps_queue_running(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='CUTTING CABLE'
        w.resource_active=True
        w.finish_resource_check('Remaining rewards')
        self.assertTrue(w.queue_engine.running);self.assertIsNone(w.queue_target)
        self.assertIsNone(w.queue_wake);self.assertGreater(w.gbr_retry_at,now)
    def test_gbr_is_rechecked_when_retry_becomes_due(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.gbr_retry_at=now-timedelta(seconds=1)
        with patch.object(w,'check_resources') as check:
            w.queue_tick();check.assert_called_once()
    def test_free_mode_navigation_does_not_require_gbr(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        for mode in ['TIMELINE BATTLE','OTHERWORLD BATTLE','TEAM BATTLE ARENA','ALLIANCE BATTLE','STORY ULTIMATE']:
            w.queue_target=mode
            with patch.object(gui,'click_game_point') as click:
                w.queue_send_point((1249,36),'navigate_board');click.assert_called_once()

    def test_failed_navigation_keeps_original_phase_for_fresh_observation(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.queue_target='TEAM BATTLE ARENA';w.queue_phase='board';w.queue_waiting=None
        with patch.object(gui,'click_game_point',side_effect=RuntimeError('Connection reset by peer')):
            with self.assertRaises(RuntimeError):w.queue_send_point((1017,206),'arena')
        self.assertEqual(w.queue_phase,'board');self.assertIsNone(w.queue_waiting)

    def test_team_repeat_summary_recovers_hold_and_then_returns_home(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.queue_held.add('TEAM BATTLE ARENA');w.queue_recovering=True
        w.queue_observation=(ScreenEvidence('team_arena_ended',{'runs':5,'point':(640,603)}),now)
        with patch.object(gui,'click_game_point') as click:w.advance_queue();click.assert_called_once()
        self.assertIn('TEAM BATTLE ARENA',w.queue_engine.completed);self.assertNotIn('TEAM BATTLE ARENA',w.queue_held)
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            w.queue_arena(ScreenEvidence('arena_result',{'mode':'TEAM BATTLE ARENA','point':(900,669)}),now)
            self.assertEqual(click.call_args.args,(11,900,669))
        self.assertIsNone(w.queue_target);self.assertFalse(w.queue_recovering)

    def test_team_arena_ticket_repeat_bypasses_gbr_and_starts_once(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.queues[0]=[{'mode':'TEAM BATTLE ARENA','enabled':True}];w.queue_target='TEAM BATTLE ARENA'
        self.assertIn('TEAM BATTLE ARENA',w.eligible_modes(now))
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            w.queue_arena(ScreenEvidence('team_arena_lobby',{'entries':(5,5)}),now)
            self.assertEqual(click.call_args.args,(11,770,678))
            w.queue_arena(ScreenEvidence('team_arena_repeat',{'selected':1,'ticket_cost':0}),now)
            self.assertEqual(click.call_args.args,(11,791,469))
            w.queue_arena(ScreenEvidence('team_arena_repeat',{'selected':5,'ticket_cost':12}),now)
            self.assertEqual(click.call_args.args,(11,750,561));self.assertEqual(w.queue_engine.pending[1],'TEAM BATTLE ARENA')
            before=click.call_count;w.queue_arena(ScreenEvidence('team_arena_repeat',{'selected':5,'ticket_cost':12}),now)
            self.assertEqual(click.call_count,before)

    def test_unread_objectives_do_not_prevent_due_gbr_retry(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.objective_plan=None;w.objective_period=None;w.gbr_retry_at=now-timedelta(seconds=1)
        with patch.object(w,'check_resources') as check,patch.object(w,'check_objectives') as objectives:
            w.queue_tick();check.assert_called_once();objectives.assert_not_called()

    def test_timeline_team_one_is_selected_before_start(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='TIMELINE BATTLE'
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            w.queue_arena(ScreenEvidence('timeline_setup',{'entries':(5,5),'team_1':False,'repeat':True}),now)
            self.assertEqual(click.call_args.args,(11,42,117));self.assertIsNone(w.queue_engine.pending)

    def test_timeline_start_is_latched_and_never_submitted_twice(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='TIMELINE BATTLE'
        e=ScreenEvidence('timeline_setup',{'entries':(5,5),'team_1':True,'repeat':True})
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            w.queue_arena(e,now);w.queue_arena(e,now);self.assertEqual(click.call_count,1)
        self.assertEqual(w.queue_engine.pending[1],'TIMELINE BATTLE')

    def test_story_requires_verified_ultimate_and_stage_one(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='STORY ULTIMATE'
        with patch('lib.gui.widgets.story_controls.click_game_point') as click,patch.object(w,'persist_story_run') as save:
            w.queue_story(ScreenEvidence('story_progress',{'from_stage_one':True}),now)
            self.assertEqual(click.call_args.args,(11,539,568));save.assert_not_called()
            w.story_ultimate_verified=(now,w.queue_engine.generation)
            w.queue_story(ScreenEvidence('story_progress',{'from_stage_one':False}),now)
            self.assertEqual(click.call_args.args,(11,551,447));save.assert_not_called()
            w.queue_story(ScreenEvidence('story_progress',{'from_stage_one':True}),now)
            save.assert_called_once_with(True);self.assertEqual(click.call_args.args,(11,741,568))
            self.assertEqual(w.queue_engine.pending[1],'STORY ULTIMATE')
            before=click.call_count;w.queue_story(ScreenEvidence('story_progress',{'from_stage_one':True}),now)
            self.assertEqual(click.call_count,before)

    def test_boost_shortage_releases_farm_for_story(self):
        now=self.prepare_sweep();w=self.window;w.queues[0].append({'mode':'STORY ULTIMATE','enabled':True})
        with patch('lib.queue_input.execute_sweep_control'):
            w.queue_read_sweep(self.sweep_evidence(boost=11),now)
        self.assertEqual(w.queue_target,'STORY ULTIMATE');self.assertEqual(w.queue_phase,'story');self.assertIn('CUTTING CABLE',w.queue_deferred)
        self.assertEqual(w.queue_engine.next_mode(w.eligible_modes(now),now),'STORY ULTIMATE')

    def test_story_inter_stage_result_does_not_complete_or_click(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.queue_target='STORY ULTIMATE';w.story_started=now;w.queue_engine.pending=(gui.reset_period(now),'STORY ULTIMATE',1)
        with patch('lib.gui.widgets.story_controls.click_game_point') as click:
            w.queue_story(ScreenEvidence('story_result',{'point':(954,669)}),now)
            w.queue_story(ScreenEvidence('story_battle',{'auto_on':True}),now)
            click.assert_not_called()
        self.assertIsNone(w.story_result_since);self.assertIsNotNone(w.queue_engine.pending)

    def test_story_long_result_still_waits_for_explicit_end(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.queue_target='STORY ULTIMATE';w.story_started=now-timedelta(hours=1)
        w.story_result_since=now-timedelta(seconds=46);w.queue_engine.pending=(gui.reset_period(now),'STORY ULTIMATE',1)
        with patch('lib.gui.widgets.story_controls.click_game_point') as click,patch.object(w,'persist_story_run') as save:
            w.queue_story(ScreenEvidence('story_result',{'point':(954,669)}),now)
            click.assert_not_called();save.assert_not_called()
        self.assertIsNotNone(w.queue_engine.pending);self.assertNotIn('STORY ULTIMATE',w.queue_engine.completed)

    def test_explicit_story_end_releases_previous_hold_from_any_queue_phase(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.story_started=now-timedelta(minutes=45);w.queue_held.add('STORY ULTIMATE')
        w.queue_phase='navigate_board';w.queue_recovering=True
        w.queue_observation=(ScreenEvidence('story_ended',{'point':(640,603)}),now)
        with patch('lib.gui.widgets.story_controls.click_game_point') as click,patch.object(w,'persist_story_run') as save:
            w.advance_queue()
            self.assertEqual(click.call_args.args,(11,640,603));save.assert_called_once_with(False)
        self.assertIn('STORY ULTIMATE',w.queue_engine.completed);self.assertNotIn('STORY ULTIMATE',w.queue_held)
        self.assertFalse(w.queue_recovering);self.assertTrue(w.queue_engine.running)
        self.assertEqual(w.queue_target,'STORY ULTIMATE');self.assertEqual(w.queue_phase,'story')
        with patch('lib.gui.widgets.story_controls.click_game_point') as click:
            w.queue_story(ScreenEvidence('story_result',{'point':(954,669)}),now)
            self.assertEqual(click.call_args.args,(11,954,669))
        self.assertIsNone(w.queue_target);self.assertEqual(w.queue_phase,'navigate_board')

    def test_otherworld_entry_decrease_does_not_interrupt_repeat(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='OTHERWORLD BATTLE'
        w.queue_engine.pending=(gui.reset_period(now),'OTHERWORLD BATTLE',5)
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click,patch.object(w,'recover_stuck_queue') as recover:
            w.queue_arena(ScreenEvidence('otherworld_lobby',{'mode':'OTHERWORLD BATTLE','entries':(5,5)}),now)
            click.assert_not_called();self.assertIsNotNone(w.queue_engine.pending)
            w.queue_arena(ScreenEvidence('otherworld_lobby',{'mode':'OTHERWORLD BATTLE','entries':(4,5)}),now)
            recover.assert_not_called();click.assert_not_called();self.assertIsNotNone(w.queue_engine.pending)

    def test_otherworld_uses_ticket_button_and_never_search_or_fight(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='OTHERWORLD BATTLE'
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            w.queue_arena(ScreenEvidence('otherworld_lobby',{'mode':'OTHERWORLD BATTLE','entries':(5,5),'ticket_icon_verified':True}),now)
            self.assertEqual(click.call_args.args,(11,750,678));self.assertIsNone(w.queue_engine.pending)
            w.queue_arena(ScreenEvidence('otherworld_repeat',{'selected':5,'ticket_cost':12,'until_rewards':False}),now)
            self.assertEqual(click.call_args.args,(11,491,479));self.assertIsNone(w.queue_engine.pending)
            w.queue_arena(ScreenEvidence('otherworld_repeat',{'selected':5,'ticket_cost':-12,'until_rewards':True}),now)
            self.assertEqual(click.call_args.args,(11,750,561));self.assertIsNotNone(w.queue_engine.pending)
            before=click.call_count
            w.queue_arena(ScreenEvidence('otherworld_repeat',{'selected':5,'ticket_cost':12,'until_rewards':True}),now)
            self.assertEqual(click.call_count,before)

    def test_story_team_two_is_verified_before_ticket_icon(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='STORY ULTIMATE'
        with patch('lib.gui.widgets.story_controls.click_game_point') as click:
            w.queue_story(ScreenEvidence('story_ultimate',{'team_2':False,'energy':(100,120),'point':(930,668)}),now)
            self.assertEqual(click.call_args.args,(11,925,264));self.assertIsNone(w.story_ultimate_verified)
            w.queue_story(ScreenEvidence('story_ultimate',{'team_2':True,'energy':(100,120),'point':(930,668)}),now)
            self.assertEqual(click.call_args.args,(11,930,668));self.assertIsNotNone(w.story_ultimate_verified)

    def test_story_quick_start_does_not_start_gbr_or_passive_checks(self):
        w=self.window;w.start_story_now()
        self.assertTrue(w.queue_engine.running);self.assertEqual(w.queue_target,'STORY ULTIMATE')
        self.assertEqual(w.queue_phase,'navigate_board');w.scan_live.assert_called_once()
        self.assertFalse(w.resource_active);self.assertFalse(w.dispatch_supply_active);self.assertFalse(w.world_event_active)

    def test_otherworld_verifies_zero_in_lobby_even_when_board_tile_disappears(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='OTHERWORLD BATTLE'
        w.queue_engine.pending=(gui.reset_period(now),'OTHERWORLD BATTLE',1)
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            w.queue_arena(ScreenEvidence('navigation_menu'),now)
            click.assert_not_called()
            w.queue_arena(ScreenEvidence('arena_repeat_ended',{'mode':'OTHERWORLD BATTLE','point':(755,604)}),now)
            w.queue_arena(ScreenEvidence('navigation_menu'),now)
            self.assertEqual(click.call_args.args,(11,491,642))
            w.queue_arena(ScreenEvidence('arena_selector',{'cards':{'OTHERWORLD BATTLE':(491,376)}}),now)
            self.assertEqual(click.call_args.args,(11,491,376))
            w.queue_arena(ScreenEvidence('otherworld_lobby',{'mode':'OTHERWORLD BATTLE','entries':(0,5)}),now)
        self.assertIsNone(w.queue_engine.pending);self.assertIn('OTHERWORLD BATTLE',w.queue_engine.completed)

    def test_selected_arena_tab_is_not_clicked_forever_when_cards_unreadable(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='OTHERWORLD BATTLE'
        w.queue_engine.pending=(gui.reset_period(now),w.queue_target,5);w.arena_repeat_finished=True
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click,patch.object(w,'recover_stuck_queue') as recover:
            for _ in range(4):w.queue_arena(ScreenEvidence('select_mission',{'first_mission':'TIMELINE BATTLE'}),now)
            click.assert_not_called();recover.assert_called_once()

    def test_ticket_repeats_send_no_inputs_on_intermediate_screens(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        for mode in ('TIMELINE BATTLE','OTHERWORLD BATTLE','TEAM BATTLE ARENA'):
            w.queue_target=mode;w.queue_engine.pending=(gui.reset_period(now),mode,5);w.arena_started=now
            with patch('lib.gui.widgets.arena_controls.click_game_point') as click,patch.object(w,'recover_stuck_queue') as recover:
                for screen,values in [('arena_battle',{'auto_on':False}),('arena_result',{'mode':mode,'point':(900,669)}),
                    ('navigation_menu',{}),('unknown',{'menu_available':True}),('timeline_setup',{'team_1':False,'repeat':False}),
                    ('content_board',{'tiles':[{'mode':mode,'remaining':4}]}),('game_home',{}),
                    ('arena_exhausted',{'mode':mode}),('otherworld_lobby',{'mode':mode,'entries':(0,5)})]:
                    w.queue_arena(ScreenEvidence(screen,values),now)
                click.assert_not_called();recover.assert_not_called()
                for _ in range(5):w.queue_arena(ScreenEvidence(errors=['OCR unreadable']),now)
                click.assert_not_called();recover.assert_not_called()

    def test_arena_capture_failure_cannot_restart_or_navigate_away(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='TEAM BATTLE ARENA'
        pending=(gui.reset_period(now),w.queue_target,5);w.queue_engine.pending=pending
        with patch('lib.gui.widgets.stuck_recovery.RestartTask') as restart,patch('lib.gui.widgets.stuck_recovery.click_game_point') as click:
            w.restart_stuck_game();restart.assert_not_called();click.assert_not_called()
        self.assertFalse(w.queue_engine.running);self.assertEqual(w.queue_engine.pending,pending)

    def test_transient_arena_capture_failures_keep_polling_without_restart(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='TEAM BATTLE ARENA'
        pending=(gui.reset_period(now),w.queue_target,5);w.queue_engine.pending=pending;w.arena_started=now
        backend=Mock(connected=True);w.adb_backend=backend
        with patch.object(w,'recover_stuck_queue') as recover,patch.object(w,'restart_stuck_game') as restart,patch.object(w,'queue_pause') as pause:
            for _ in range(8):w.adb_frame_failed(backend,'Incomplete capture')
            recover.assert_not_called();restart.assert_not_called()
            self.assertEqual(pause.call_args.args[1],15);self.assertFalse(pause.call_args.kwargs['stalled'])
        self.assertTrue(w.queue_engine.running);self.assertEqual(w.queue_engine.pending,pending)
        w.queue_observation=(ScreenEvidence('team_arena_ended',{'runs':5,'point':(640,603)}),now)
        with patch.object(gui,'click_game_point') as click:
            w.advance_queue();click.assert_called_once()
        self.assertIsNone(w.queue_engine.pending);self.assertIn('TEAM BATTLE ARENA',w.queue_engine.completed)

    def test_old_arena_submission_stays_saved_during_bounded_bridge_recovery(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='TEAM BATTLE ARENA'
        pending=(gui.reset_period(now),w.queue_target,5);w.queue_engine.pending=pending;w.arena_started=now-timedelta(minutes=36)
        backend=Mock(connected=True);w.adb_backend=backend;w.capture_failure_count=3
        with patch.object(w,'recover_stuck_queue') as recover,patch.object(w,'restart_stuck_game') as restart:
            w.adb_frame_failed(backend,'Incomplete capture');recover.assert_not_called();restart.assert_not_called()
        self.assertTrue(w.queue_engine.running);self.assertEqual(w.queue_engine.pending,pending)
        w.emulator_capture_failed_since=now-timedelta(seconds=61)
        with patch('lib.gui.widgets.emulator_recovery.EmulatorRecoveryTask') as recovery:
            w.adb_frame_failed(backend,'Background screenshot incomplete after three captures; reconnect')
            recovery.assert_called_once()
        w.emulator_task=None
        self.assertEqual(w.queue_engine.pending,pending)

    def test_otherworld_checks_until_rewards_before_adjusting_quantity(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now);w.queue_target='OTHERWORLD BATTLE'
        w.arena_remaining=5;w.arena_entry_verified=now
        with patch('lib.gui.widgets.arena_controls.click_game_point') as click:
            w.queue_arena(ScreenEvidence('otherworld_repeat',{'selected':1,'ticket_cost':0,'until_rewards':False}),now)
            self.assertEqual(click.call_args.args,(11,491,479));self.assertIsNone(w.queue_engine.pending)

    def test_epic_opens_preparation_without_first_opening_sweep(self):
        now=self.prepare_sweep();w=self.window
        board=ScreenEvidence('content_board',{'tiles':[{'mode':w.queue_target,'remaining':3,'point':(250,206)}],'accelerated_clear':True})
        with patch.object(gui,'click_game_point') as click:
            w.queue_read_board(board,now);self.assertEqual(click.call_args.args,(11,85,690))
            board.values['accelerated_clear']=False
            w.queue_read_board(board,now);self.assertEqual(click.call_args.args,(11,250,206))

    def test_dispatch_due_does_not_discard_active_mission_preparation(self):
        now=self.prepare_sweep();w=self.window;w.queue_phase='sweep';w.dispatch_supply_next=now-timedelta(seconds=1)
        w.epic_preparation=('verified',now,w.queue_engine.generation)
        with patch.object(w,'start_dispatch_supplies') as supplies:
            w.queue_tick();supplies.assert_not_called()
        self.assertEqual(w.epic_preparation[0],'verified')

    def test_due_world_event_does_not_interrupt_epic_preparation(self):
        now=self.prepare_sweep();w=self.window
        w.queues[0].append({'mode':'WORLD EVENT','enabled':True})
        w.world_event_state.done=False;w.world_event_state.next_check=now-timedelta(seconds=1)
        with patch.object(w,'start_world_event') as event:
            w.queue_tick();event.assert_not_called()

    def test_stale_terminal_summary_cannot_send_inputs(self):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.queue_observation=(ScreenEvidence('team_arena_ended',{'runs':5,'point':(640,603)}),now-timedelta(seconds=31))
        with patch.object(gui,'click_game_point') as click:
            w.advance_queue();click.assert_not_called()
        self.assertNotIn('TEAM BATTLE ARENA',w.queue_engine.completed)
