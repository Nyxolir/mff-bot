import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from lib.trivia import lookup_answer,choose_option
from lib.trivia_reader import TriviaReader
from lib.trivia_session import TriviaSession
from lib.screen_reader import ScreenEvidence
from lib.daily_queue import next_reset

class TriviaTests(unittest.TestCase):
    def test_oct27_moon_knight_question_uses_named_answer(self):
        for name,number in (('trivia_moon_knight_oct27.png',1),('trivia_surtur_oct27.png',2)):
            with self.subTest(name=name):
                e=TriviaReader().read(Path(__file__).parent/'fixtures'/name)
                self.assertEqual(e.screen,'trivia_question');self.assertEqual(e.values['question_number'],number)
                self.assertEqual(choose_option(e.values['question'],e.values['options']),1)

    def test_unreadable_unrelated_event_counters_do_not_block_verified_trivia_navigation(self):
        now=datetime.now(timezone.utc);session=TriviaSession(now)
        evidence=TriviaReader().read(Path(__file__).parent/'fixtures/trivia_navigation_event_quest_oct27.png')
        self.assertEqual(evidence.screen,'challenge_navigation');self.assertFalse(evidence.errors)
        self.assertEqual(session.observe(evidence,now),('click',1249,37));self.assertFalse(session.done)
        session.pending='unverified answer'
        with self.assertRaises(ValueError):session.observe(evidence,now)

    def test_observed_daily_objectives_page_navigates_to_trivia_without_claiming_completion(self):
        now=datetime.now(timezone.utc);session=TriviaSession(now)
        evidence=TriviaReader().read(Path(__file__).parent/'fixtures/trivia_navigation_daily_oct27.png')
        self.assertEqual(evidence.screen,'daily_objectives');self.assertFalse(evidence.errors)
        self.assertEqual(session.observe(evidence,now),('click',786,113));self.assertFalse(session.done)

    def test_live_additions_reload_without_overriding_existing_answers(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        import json
        from lib import trivia
        with TemporaryDirectory() as folder:
            path=Path(folder)/'answers.json'
            with patch.object(trivia,'EXTRA_ANSWERS',path):
                q='What is the status effect that provokes enemies and forces them to attack?'
                path.write_text(json.dumps({'version':1,'answers':{q:'Mockery',"What is Iron Man's real name?":'Thor'}}))
                self.assertEqual(lookup_answer(q),'Mockery')
                self.assertEqual(lookup_answer("What is Iron Man's real name?"),'Tony Stark')
                path.write_text('{broken')
                self.assertEqual(lookup_answer("What is Iron Man's real name?"),'Tony Stark')
    def test_oct25_mockery_question_matches_observed_option(self):
        e=TriviaReader().read(Path(__file__).parent/'fixtures/trivia_mockery_oct25.png')
        self.assertEqual(e.screen,'trivia_question',e)
        self.assertEqual(choose_option(e.values['question'],e.values['options']),0)

    def test_oct25_elektra_question_matches_observed_option(self):
        e=TriviaReader().read(Path(__file__).parent/'fixtures/trivia_elektra_oct25.png')
        self.assertEqual(e.screen,'trivia_question',e)
        self.assertEqual(e.values['question_number'],2)
        self.assertEqual(lookup_answer(e.values['question']),'Elektra')
        self.assertEqual(choose_option(e.values['question'],e.values['options']),3)

    def test_oct24_questions_and_game_confirmed_missing_answers(self):
        expected=['Jubilee','Thermokinesis','Black Panther','Rescue','Marvel Boy']
        for number,answer in enumerate(expected,1):
            with self.subTest(number=number):
                e=TriviaReader().read(Path(__file__).parent/f'fixtures/trivia_question_{number}_oct24.png')
                self.assertEqual(e.screen,'trivia_question',e);self.assertEqual(e.values['question_number'],number)
                self.assertEqual(lookup_answer(e.values['question']),answer)
                self.assertEqual(e.values['options'][choose_option(e.values['question'],e.values['options'])],answer)

    def test_completed_summary_finishes_from_either_scroll_position_without_input(self):
        now=datetime.now(timezone.utc);root=Path(__file__).parent/'fixtures'
        for name in ('trivia_completed_oct24_top.png','trivia_completed_oct24_bottom.png',
                     'trivia_completed_top.png','trivia_completed_bottom.png','trivia_completed_oct28_bottom.png'):
            with self.subTest(name=name):
                session=TriviaSession(now);session.pending='interrupted final answer'
                e=TriviaReader().read(root/name)
                self.assertTrue(e.values['completed_summary_verified'])
                self.assertIsNone(session.observe(e,now));self.assertTrue(session.done)
                self.assertEqual(session.actions,0);self.assertIsNone(session.pending)

    def test_summary_requires_its_own_visual_proof_and_answered_rows(self):
        now=datetime.now(timezone.utc)
        row=dict(question='A verified long question?',displayed_answer='TVA',answered=True)
        for values in ({'rows':[row]}, {'rows':[],'completed_summary_verified':True},
                       {'rows':[dict(row,answered=False)],'completed_summary_verified':True},
                       {'rows':[dict(row,displayed_answer='')],'completed_summary_verified':True}):
            session=TriviaSession(now)
            with self.assertRaises(ValueError):session.observe(ScreenEvidence('trivia_list',values),now)
            self.assertFalse(session.done);self.assertEqual(session.actions,0)

    def test_summary_does_not_complete_if_answer_labels_or_gold_answers_are_missing(self):
        from PIL import Image,ImageDraw
        source=Path(__file__).parent/'fixtures/trivia_completed_oct24_top.png'
        for box in ((65,200,257,710),(265,200,1200,710)):
            im=Image.open(source).convert('RGB');ImageDraw.Draw(im).rectangle(box,fill='black')
            e=TriviaReader().read(im)
            self.assertFalse(e.values.get('completed_summary_verified',False))

    def test_animation_wait_is_bounded_and_does_not_use_input_budget(self):
        now=datetime.now(timezone.utc);session=TriviaSession(now)
        e=ScreenEvidence('trivia_unknown',errors=['options still animating'])
        for seconds in (0,3,6,9,12,15,18):self.assertEqual(session.observe(e,now+timedelta(seconds=seconds)),('wait',0,0))
        self.assertEqual(session.actions,0)
        with self.assertRaises(ValueError):session.observe(e,now+timedelta(seconds=21))

    def test_question_number_prevents_resubmission_when_ocr_changes_during_answer_animation(self):
        now=datetime.now(timezone.utc);session=TriviaSession(now)
        e=TriviaReader().read(Path(__file__).parent/'fixtures/trivia_question_4_oct24.png')
        self.assertEqual(session.observe(e,now)[0],'answer')
        changed=ScreenEvidence('trivia_question',dict(e.values,question=e.values['question'].replace('Tony Stark', 'Tony St rk')))
        self.assertEqual(session.observe(changed,now),('wait',0,0))
        session.observe(ScreenEvidence('trivia_correct',{'result_verified':True,'answer':'Rescue','close_point':(640,575)}),now)
        self.assertEqual(session.observe(changed,now),('wait',0,0))

    def test_oct24_start_is_semantically_verified_and_clicked_once(self):
        from PIL import Image,ImageDraw
        root=Path(__file__).parent/'fixtures'
        e=TriviaReader().read(root/'trivia_start_oct24.png')
        self.assertEqual(e.screen,'trivia_start')
        now=datetime.now(timezone.utc);session=TriviaSession(now)
        self.assertEqual(session.observe(e,now),('click',1000,606))
        self.assertEqual(session.observe(e,now),('wait',0,0))
        for box in ((300,433,730,485),(920,581,1080,628)):
            im=Image.open(root/'trivia_start_oct24.png').convert('RGB');ImageDraw.Draw(im).rectangle(box,fill='black')
            self.assertNotEqual(TriviaReader().read(im).screen,'trivia_start')

    def test_all_current_questions_match_the_correct_option(self):
        expected=[1,2,3,0,0]
        for number,index in enumerate(expected,1):
            with self.subTest(number=number):
                e=TriviaReader().read(Path(__file__).parent/f'fixtures/trivia_question_{number}_current.png')
                self.assertEqual(e.screen,'trivia_question',e)
                self.assertEqual(e.values['question_number'],number)
                self.assertEqual(choose_option(e.values['question'],e.values['options']),index)
    def test_current_correct_modal_is_verified_and_can_resume_after_reload(self):
        e=TriviaReader().read(Path(__file__).parent/'fixtures/trivia_correct_current.png')
        self.assertEqual(e.screen,'trivia_correct',e);self.assertTrue(e.values['result_verified'])
        self.assertEqual(e.values['answer'],'Baxter Building')
        now=datetime.now(timezone.utc);session=TriviaSession(now)
        self.assertEqual(session.observe(e,now),('click',640,575))
        self.assertEqual(session.observe(e,now),('wait',0,0))
    def test_mismatched_correct_result_does_not_advance(self):
        now=datetime.now(timezone.utc);session=TriviaSession(now)
        q=ScreenEvidence('trivia_question',dict(layout_verified=True,question="What is Iron Man's real name?",
            options=['Thor','Tony Stark','Steve Rogers','Peter Parker'],points=[(1,1),(2,2),(3,3),(4,4)]))
        session.observe(q,now)
        with self.assertRaises(ValueError):
            session.observe(ScreenEvidence('trivia_correct',dict(result_verified=True,answer='Thor',close_point=(640,575))),now)
    def test_current_four_option_question_and_verified_answer(self):
        e=TriviaReader().read(Path(__file__).parent/'fixtures/trivia_question_1_current.png')
        self.assertEqual(e.screen,'trivia_question',e);self.assertTrue(e.values['layout_verified'])
        self.assertEqual(e.values['question_number'],1)
        self.assertEqual(choose_option(e.values['question'],e.values['options']),1)
        now=datetime.now(timezone.utc);session=TriviaSession(now)
        self.assertEqual(session.observe(e,now),('answer',1030,416))
        self.assertEqual(session.observe(e,now),('wait',0,0))
    def test_verified_title_play_screen(self):
        from lib.session_recovery import session_notice
        e=session_notice(Path(__file__).parent/'fixtures/game_title_play_current.png')
        self.assertEqual(e.screen,'game_title');self.assertEqual(e.values['point'],(640,657))
    def test_home_with_animated_benefits_is_still_recognized(self):
        from lib.objective_reader import ObjectiveReader
        e=ObjectiveReader().read(Path(__file__).parent/'fixtures/home_animated_benefits_current.png')
        self.assertEqual(e.screen,'game_home')
    def test_current_start_is_clicked_once(self):
        evidence=TriviaReader().read(Path(__file__).parent/'fixtures/trivia_start_current.png')
        self.assertEqual(evidence.screen,'trivia_start',evidence)
        now=datetime.now(timezone.utc);session=TriviaSession(now)
        self.assertEqual(session.observe(evidence,now),('click',1000,606))
        self.assertEqual(session.observe(evidence,now),('wait',0,0))
    def test_exit_dialog_is_cancelled_and_home_is_not_dialog(self):
        from lib.session_recovery import session_notice
        root=Path(__file__).parent/'fixtures'
        evidence=session_notice(root/'exit_game_current.png')
        self.assertIsNotNone(evidence);self.assertEqual(evidence.screen,'exit_game')
        self.assertEqual(evidence.values['cancel_point'],(792,384))
        self.assertIsNone(session_notice(root/'trivia_home_completed_tasks.png'))
    def test_completed_task_home_uses_menu_fallback(self):
        root=Path(__file__).parent/'fixtures';now=datetime.now(timezone.utc)
        home=TriviaReader().read(root/'trivia_home_completed_tasks.png')
        menu=TriviaReader().read(root/'trivia_menu.png')
        self.assertEqual(home.screen,'game_home')
        self.assertEqual(menu.screen,'trivia_menu')
        self.assertEqual(TriviaReader().read(root/'trivia_menu_adb.png').screen,'trivia_menu')
        session=TriviaSession(now)
        self.assertEqual(session.observe(home,now),('click',1249,37))
        self.assertEqual(session.observe(menu,now),('click',1195,390))
    def test_source_aliases_and_conflicting_old_answer(self):
        self.assertEqual(lookup_answer("Which is the name of the bridge connects Yggdrasil's nine realms?"),'Bifrost')
        self.assertEqual(lookup_answer('What materials are NOT required to upgrade a character to Tier-3?'),'Norn Stones of Chaos')
        self.assertEqual(lookup_answer('What Character Type is typically strong against Combat Type Characters?'),'Blast')
        self.assertEqual(lookup_answer('What Character Type is typically strong against Blast Type Characters?'),'Speed')
    def test_unknown_ambiguity_and_negation_never_guess(self):
        self.assertIsNone(lookup_answer('What is the name of an unknown new artifact?'))
        bank={'Which hero is the king of the golden realm?':'A','Which hero is the king of the silver realm?':'B'}
        self.assertIsNone(lookup_answer('Which hero is the king of the hidden realm?',bank))
        self.assertIsNone(lookup_answer('What material is NOT Captain America shield made of?'))
    def test_options_are_unique_and_order_independent(self):
        q="What is Iron Man's real name?"
        self.assertEqual(choose_option(q,['Bruce Banner','Steve Rogers','Tony Stark','Thor']),2)
        self.assertIsNone(choose_option(q,['Tony Stark','Tony Stark','Steve Rogers','Thor']))
        self.assertIsNone(choose_option(q,['Bruce Banner','Steve Rogers','Peter Parker','Thor']))
        self.assertIsNone(choose_option(q,['Tony Stark']))
    def test_completed_live_fixtures_and_session(self):
        root=Path(__file__).parent/'fixtures';now=datetime.now(timezone.utc)
        top=TriviaReader().read(root/'trivia_completed_top.png')
        bottom=TriviaReader().read(root/'trivia_completed_bottom.png')
        self.assertEqual(top.screen,'trivia_list');self.assertFalse(top.errors)
        self.assertEqual(bottom.screen,'trivia_list');self.assertFalse(bottom.errors)
        self.assertTrue(all(r['answered'] for r in top.values['rows']+bottom.values['rows']))
        self.assertTrue(all(r['answer'] for r in top.values['rows']+bottom.values['rows']))
        session=TriviaSession(now)
        self.assertIsNone(session.observe(bottom,now));self.assertTrue(session.done)
        self.assertEqual(session.actions,0)
    def test_no_duplicate_answer_or_unknown_result_retry(self):
        now=datetime.now(timezone.utc);session=TriviaSession(now)
        q=ScreenEvidence('trivia_question',dict(layout_verified=True,question="What is Iron Man's real name?",
            options=['Steve Rogers','Tony Stark','Thor','Peter Parker'],points=[(1,1),(2,2),(3,3),(4,4)]))
        self.assertEqual(session.observe(q,now),('answer',2,2))
        self.assertEqual(session.observe(q,now),('wait',0,0))
        self.assertEqual(session.observe(ScreenEvidence(),now),('wait',0,0))
        with self.assertRaises(ValueError):session.observe(ScreenEvidence(),now+timedelta(seconds=21))
    def test_unvalidated_dialog_and_reset_stop(self):
        now=datetime.now(timezone.utc);session=TriviaSession(now)
        with self.assertRaises(ValueError):session.observe(ScreenEvidence('trivia_question'),now)
        with self.assertRaises(ValueError):session.observe(ScreenEvidence(),next_reset(now))

if __name__=='__main__':unittest.main()
