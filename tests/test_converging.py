import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from datetime import datetime,timedelta,timezone
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import unittest
from PyQt5.QtWidgets import QApplication
from tests import test_queue_gui
from lib.gui.widgets import modern_main as gui
from lib.converging import ConvergingReader,NORMAL,HIDDEN
from lib.daily_queue import BatchEvidence,DailyRaidGate,batch_decision,QueueAction,reset_period,next_reset
from lib.screen_reader import ScreenEvidence

class ConvergingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    setUp=test_queue_gui.QueueGuiTests.setUp
    tearDown=test_queue_gui.QueueGuiTests.tearDown
    scan_fixture=test_queue_gui.QueueGuiTests.scan_fixture

    def start(self,mode=NORMAL):
        w=self.window;now=datetime.now(timezone.utc);w.queue_engine.start(now)
        w.queues[0]=[{'mode':m,'enabled':True} for m in (NORMAL,HIDDEN,'CUTTING CABLE')]
        w.queue_target=mode;w.queue_phase='converging';return w,now

    def frame(self,name):return self.scan_fixture('converging_'+name+'_oct25.png',reader_kind='converging')[:2]

    def test_all_observed_converging_screens_pass_scan_task(self):
        for name,screen in [('chapter','chapter'),('normal_difficulty','difficulty'),('hidden_difficulty','difficulty'),
                ('normal_ready','ready'),('hidden_ready','ready'),('normal_sweep','sweep'),('hidden_sweep','sweep'),
                ('vault_notice','vault_notice'),('hidden_vault','vault_notice'),('normal_claim','result'),('hidden_claim','result'),
                ('normal_zero','ready'),('hidden_zero','ready')]:
            e,_=self.frame(name);self.assertEqual(e.screen,'converging_'+screen,(name,e));self.assertFalse(e.errors)
            self.assertFalse(any('energy' in k or 'tickets_available' in k or 'boost_available' in k for k in e.text))

    def test_queue_preflight_can_navigate_from_the_converging_ready_screen(self):
        w,now=self.start();w.enable_board_preflight=True;w.start_daily_board_check(now)
        e,observed,_=self.scan_fixture('converging_hidden_zero_oct25.png',reader_kind='daily_board_check')
        self.assertTrue(e.values.get('menu_available'),e)
        with patch('lib.gui.widgets.daily_board_check.click_game_point') as click:
            w.queue_daily_board_check(e,observed);self.assertEqual(click.call_args.args,(11,1249,36))

    def test_only_explicit_converging_modes_bypass_boost_and_gbr(self):
        now=datetime.now(timezone.utc);b=BatchEvidence(NORMAL,5,5,None,0,None,None,None,None,now,0,False,True)
        for mode in (NORMAL,HIDDEN):self.assertEqual(batch_decision(replace(b,mode=mode),DailyRaidGate(),now).action,QueueAction.CLEAR)
        for change in ({'remaining':6,'selected':6},{'boost_total':4},{'crystal_total':1},{'selected':1},{'sweep_verified':False}):
            self.assertNotEqual(batch_decision(replace(b,**change),DailyRaidGate(),now).action,QueueAction.CLEAR)
        self.assertEqual(batch_decision(replace(b,mode='CUTTING CABLE'),DailyRaidGate(),now).action,QueueAction.GBR)
        self.assertNotEqual(batch_decision(replace(b,captured_at=now-timedelta(seconds=31)),DailyRaidGate(),now).action,QueueAction.CLEAR)

    def test_both_variants_schedule_before_gbr_and_objective_waits(self):
        w,now=self.start();w.queue_target=None;w.objective_refresh_due=True
        with patch.object(w,'check_resources') as gbr,patch.object(w,'check_objectives') as objectives:
            w.queue_tick();self.assertEqual(w.queue_target,NORMAL);gbr.assert_not_called();objectives.assert_not_called()
        self.assertIn(HIDDEN,w.eligible_modes(now));self.assertFalse(w.requires_gbr(NORMAL));self.assertFalse(w.requires_gbr(HIDDEN))

    def test_full_ticket_flow_keeps_pending_until_zero_then_opens_hidden_directly(self):
        w,now=self.start()
        with patch('lib.gui.widgets.modern_main.click_game_point') as nav,patch('lib.gui.widgets.converging_controls.click_game_point') as spend:
            for name in ('normal_difficulty','normal_ready','vault_notice','normal_sweep'):
                e,observed=self.frame(name);w.queue_converging(e,observed)
            self.assertEqual(w.queue_engine.pending,(reset_period(now),NORMAL,5));self.assertEqual(spend.call_count,1)
            e,observed=self.frame('normal_claim');w.queue_converging(e,observed)
            self.assertIsNotNone(w.queue_engine.pending);self.assertNotIn(NORMAL,w.queue_engine.completed)
            e,observed=self.frame('normal_zero');w.queue_converging(e,observed)
            self.assertIsNone(w.queue_engine.pending);self.assertIn(NORMAL,w.queue_engine.completed);self.assertEqual(w.queue_target,HIDDEN)
            self.assertEqual(nav.call_args.args,(11,35,36))
            e,observed=self.frame('chapter');w.queue_converging(e,observed)
            self.assertEqual(nav.call_args.args,(11,216,676));self.assertEqual(w.queue_phase,'converging')

    def test_native_adb_five_entries_and_vault_notice_complete_the_ticket_flow(self):
        w,now=self.start()
        with patch('lib.gui.widgets.modern_main.click_game_point') as nav,patch('lib.gui.widgets.converging_controls.click_game_point') as spend:
            ready,stamp,_=self.scan_fixture('converging_ready_adb_oct26.png',reader_kind='converging')
            self.assertEqual(ready.screen,'converging_ready');self.assertEqual(ready.values['remaining'],5)
            w.queue_converging(ready,stamp)
            notice,stamp,_=self.scan_fixture('converging_vault_adb_oct26.png',reader_kind='converging')
            self.assertEqual(notice.screen,'converging_vault_notice');w.queue_converging(notice,stamp)
            self.assertEqual(nav.call_args.args,(11,740,536))
            sweep,stamp,_=self.scan_fixture('converging_sweep_adb_oct26.png',reader_kind='converging')
            self.assertEqual(sweep.screen,'converging_sweep');self.assertEqual(sweep.values['selected'],5)
            w.queue_converging(sweep,stamp)
            self.assertEqual(w.queue_engine.pending,(reset_period(now),NORMAL,5));self.assertEqual(spend.call_count,1)
            claim,stamp=self.frame('normal_claim');w.queue_converging(claim,stamp)
            self.assertNotIn(NORMAL,w.queue_engine.completed)
            zero,stamp=self.frame('normal_zero');w.queue_converging(zero,stamp)
            self.assertIsNone(w.queue_engine.pending);self.assertIn(NORMAL,w.queue_engine.completed)
            self.assertEqual(w.queue_target,HIDDEN)
            chapter,stamp=self.frame('chapter');w.queue_converging(chapter,stamp)
            self.assertEqual(nav.call_args.args,(11,216,676))

    def test_native_notice_requires_exact_text_and_ok_control(self):
        from PIL import Image,ImageDraw
        source=Image.open(Path(__file__).parent/'fixtures/converging_vault_adb_oct26.png').convert('RGB')
        for box in ((345,279,940,345),(690,510,790,565)):
            image=source.copy();ImageDraw.Draw(image).rectangle(box,fill='black')
            self.assertNotEqual(ConvergingReader().read(image).screen,'converging_vault_notice')

    def test_native_sweep_requires_prompt_ticket_label_and_batch_control(self):
        from PIL import Image,ImageDraw
        source=Image.open(Path(__file__).parent/'fixtures/converging_sweep_adb_oct26.png').convert('RGB')
        for box in ((490,310,800,345),(450,368,800,405),(550,536,733,577)):
            image=source.copy();ImageDraw.Draw(image).rectangle(box,fill='black')
            self.assertNotEqual(ConvergingReader().read(image).screen,'converging_sweep')

    def test_only_unfinished_variant_is_opened_from_the_board(self):
        for unfinished,done in ((NORMAL,HIDDEN),(HIDDEN,NORMAL)):
            w,now=self.start(unfinished);w.queue_engine.completed.clear();w.queue_phase='board'
            board=ScreenEvidence('content_board',dict(tiles=[dict(mode=done,remaining=0,completed=True,point=(10,10)),
                dict(mode=unfinished,remaining=5,total=5,completed=False,point=(252,206))],accelerated_clear=False))
            with patch.object(gui,'click_game_point') as click:
                w.queue_read_board(board,now)
                self.assertIn(done,w.queue_engine.completed);self.assertNotIn(unfinished,w.queue_engine.completed)
                self.assertEqual(w.queue_target,unfinished);self.assertEqual(w.queue_phase,'converging')
                self.assertEqual(click.call_args.args,(11,252,206))

    def test_result_mismatch_unknown_or_positive_ready_never_repeats(self):
        w,now=self.start();pending=(reset_period(now),NORMAL,5);w.queue_engine.pending=pending
        for name in ('hidden_claim','normal_ready','normal_sweep'):
            e,observed=self.frame(name)
            with patch('lib.gui.widgets.converging_controls.click_game_point') as spend,patch.object(gui,'click_game_point') as nav:
                w.queue_converging(e,observed);spend.assert_not_called();nav.assert_not_called()
            self.assertEqual(w.queue_engine.pending,pending);self.assertNotIn(NORMAL,w.queue_engine.completed)

    def test_missing_expired_or_different_variant_preparation_closes_popup(self):
        w,now=self.start();modal,stamp=self.frame('normal_sweep');prep,_=self.frame('hidden_ready')
        for record in (None,(prep,now,w.queue_engine.generation)):
            w.converging_preparation=record
            with patch.object(gui,'click_game_point') as nav,patch('lib.gui.widgets.converging_controls.click_game_point') as spend:
                w.queue_converging(modal,stamp);spend.assert_not_called();self.assertEqual(nav.call_args.args,(11,872,555))
            self.assertIsNone(w.queue_engine.pending)

    def test_submission_and_completion_persistence_failures_send_no_input(self):
        w,now=self.start();prep,stamp=self.frame('normal_ready');w.converging_preparation=(prep,stamp,w.queue_engine.generation)
        modal,stamp=self.frame('normal_sweep')
        with patch.object(w,'persist_pending_clear',return_value=False),patch('lib.gui.widgets.converging_controls.click_game_point') as spend:
            w.queue_converging(modal,stamp);spend.assert_not_called();self.assertIsNone(w.queue_engine.pending)
        w.queue_engine.start(now);w.queue_target=NORMAL;pending=(reset_period(now),NORMAL,5);w.queue_engine.pending=pending
        zero,stamp=self.frame('normal_zero')
        with patch.object(w,'persist_completed_missions',return_value=False),patch.object(gui,'click_game_point') as nav:
            w.queue_converging(zero,stamp);nav.assert_not_called();self.assertEqual(w.queue_engine.pending,pending)
            self.assertNotIn(NORMAL,w.queue_engine.completed);self.assertFalse(w.queue_engine.running)

    def test_one_remaining_entry_uses_verified_single_ticket_control(self):
        w,now=self.start();prep,stamp=self.frame('normal_ready')
        prep=ScreenEvidence(prep.screen,dict(prep.values,remaining=1),prep.text)
        w.converging_preparation=(prep,stamp,w.queue_engine.generation)
        modal,stamp=self.frame('normal_sweep');self.assertTrue(modal.values['single_verified'])
        with patch('lib.gui.widgets.converging_controls.click_game_point') as spend:
            w.queue_converging(modal,stamp);self.assertEqual(spend.call_args.args,(11,408,555))
        self.assertEqual(w.queue_engine.pending,(reset_period(now),NORMAL,1))

    def test_saved_pending_variants_restore_without_losing_submission(self):
        import json
        from tempfile import TemporaryDirectory
        from lib.gui.widgets import completion_cache
        w,now=self.start()
        with TemporaryDirectory() as folder,patch.object(completion_cache,'CACHE',Path(folder)/'completed.json'):
            for mode in (NORMAL,HIDDEN):
                saved=(reset_period(now),mode,5)
                (Path(folder)/'pending-clear.json').write_text(json.dumps({'pending':list(saved)}))
                w.queue_engine.pending=None
                completion_cache.CompletionCache.load_pending_clear(w)
                self.assertEqual(w.queue_engine.pending,saved)

    def test_restart_routes_pending_converging_to_its_own_controller(self):
        w,now=self.start(HIDDEN);w.queue_engine.pending=(reset_period(now),HIDDEN,5);w.queue_target=None;w.queue_wake=None
        w.queue_tick();self.assertEqual(w.queue_target,HIDDEN);self.assertEqual(w.queue_phase,'converging')

    def test_masked_identity_or_controls_do_not_authorize_preparation(self):
        from PIL import Image,ImageDraw
        source=Image.open(Path(__file__).parent/'fixtures/converging_hidden_ready_oct25.png').convert('RGB')
        for box in ((175,359,614,397),(177,697,222,733),(520,697,604,734)):
            image=source.copy();ImageDraw.Draw(image).rectangle(box,fill='black')
            self.assertNotEqual(ConvergingReader().read(image).screen,'converging_ready')

if __name__=='__main__':unittest.main()
