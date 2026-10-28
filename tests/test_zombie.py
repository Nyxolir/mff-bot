import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw
from lib.zombie_reader import ZombieReader,MODE
from lib.mission_reader import BoardReader

F=Path(__file__).parent/'fixtures'
class ZombieReaderTests(unittest.TestCase):
    def test_actual_repeat_end_result_and_reward_collection_renderings(self):
        reader=ZombieReader()
        for name,screen in [('zombie_repeat_ended_oct24.png','zombie_repeat_ended'),('zombie_result_oct24.png','zombie_result'),('zombie_rewards_oct24.png','zombie_rewards')]:
            with self.subTest(name=name):
                e=reader.read(F/name);self.assertEqual(e.screen,screen);self.assertEqual(e.values['mode'],MODE);self.assertFalse(e.errors,e)
        ended=reader.read(F/'zombie_repeat_ended_oct24.png');self.assertEqual(ended.values['point'],(640,537));self.assertEqual(ended.values['survivors'],(5,5))
        ready=reader.read(F/'zombie_challenges_ready_oct24.png');self.assertTrue(ready.values['five_clears_verified']);self.assertTrue(ready.values['acquire_ready'])
        claimed=reader.read(F/'zombie_challenges_claimed_oct24.png');self.assertTrue(claimed.values['five_clears_verified']);self.assertFalse(claimed.values['acquire_ready']);self.assertEqual(claimed.values['weekly_completed'],10)

    def test_terminal_and_receipt_require_the_specific_mode_labels_and_controls(self):
        for name,boxes in [('zombie_repeat_ended_oct24.png',[(804,42,1178,100),(515,306,765,344),(568,371,716,409),(605,517,675,556)]),
                ('zombie_rewards_oct24.png',[(455,202,846,241),(606,561,678,601)]),('zombie_result_oct24.png',[(843,639,892,682)])]:
            for box in boxes:
                with self.subTest(name=name,box=box):
                    im=Image.open(F/name).convert('RGB');ImageDraw.Draw(im).rectangle(box,fill='black')
                    e=ZombieReader().read(im)
                    self.assertNotIn(e.screen,('zombie_repeat_ended','zombie_result','zombie_rewards'))

    def test_explicit_completed_board_tile_requires_its_check(self):
        e=ZombieReader().read(F/'zombie_board_completed_oct24.png')
        self.assertEqual(e.screen,'content_board');row=next(r for r in e.values['tiles'] if r['mode']==MODE)
        self.assertEqual(row['remaining'],0);self.assertTrue(row['completed'])
        im=Image.open(F/'zombie_board_completed_oct24.png').convert('RGB');ImageDraw.Draw(im).rectangle((786,342,829,382),fill='black')
        e=BoardReader().read(im);row=next(r for r in e.values['tiles'] if r['mode']==MODE);self.assertFalse(row['completed'])

    def test_battle_repeat_progress_is_observation_only(self):
        e=ZombieReader().read(F/'zombie_battle_1_oct24.png')
        self.assertEqual(e.screen,'zombie_battle');self.assertEqual(e.values['progress'],(1,5));self.assertEqual(e.values['level'],1)
        self.assertNotIn('point',e.values)

    def test_current_lobby_notice_and_every_slot_count_without_character_names(self):
        reader=ZombieReader()
        for name,screen in [('zombie_lobby_oct24.png','zombie_lobby'),('zombie_past_season_oct24.png','zombie_season_notice')]:
            with self.subTest(name=name):
                e=reader.read(F/name);self.assertEqual(e.screen,screen);self.assertFalse(e.errors,e)
        for count,name in enumerate(['zombie_prepare_empty_oct24.png','zombie_prepare_one_oct24.png',*[f'zombie_prepare_{i}_oct24.png' for i in range(2,6)]]):
            with self.subTest(count=count):
                e=reader.read(F/name);self.assertEqual(e.screen,'zombie_prepare');self.assertFalse(e.errors,e)
                self.assertEqual(e.values['level'],1);self.assertEqual(e.values['slots'],tuple(i<count for i in range(5)))
                self.assertNotIn('characters',e.values)

    def test_max_repeat_verifies_count_without_ticket_amount(self):
        reader=ZombieReader()
        for name,count,cost,maximum in [('zombie_repeat_initial_oct24.png',1,0,False),('zombie_repeat_max_oct24.png',5,12,True)]:
            with self.subTest(name=name):
                e=reader.read(F/name);self.assertEqual(e.screen,'zombie_repeat');self.assertFalse(e.errors,e)
                self.assertEqual((e.values['selected'],e.values['max_selected']),(count,maximum))

    def test_mode_identity_and_slots_remain_required_without_ticket_amount(self):
        for box in ((92,317,302,348),(467,259,815,288)):
            with self.subTest(box=box):
                im=Image.open(F/'zombie_repeat_max_oct24.png').convert('RGB');ImageDraw.Draw(im).rectangle(box,fill='black')
                e=ZombieReader().read(im);self.assertNotEqual(e.screen,'zombie_repeat')
        im=Image.open(F/'zombie_prepare_5_oct24.png').convert('RGB');ImageDraw.Draw(im).rectangle((160,500,265,605),fill='black')
        e=ZombieReader().read(im);self.assertTrue(e.errors);self.assertNotIn('ticket_point',e.values)

    def test_unrelated_repeat_and_trivia_screens_do_not_identify_zombie(self):
        for name in ('otherworld_repeat_four_oct24.png','trivia_completed_oct24_top.png','alliance_normal_setup_current.png'):
            with self.subTest(name=name):self.assertFalse(ZombieReader().read(F/name).screen.startswith('zombie_'))

    def test_weekly_challenges_do_not_claim_before_five_clears(self):
        e=ZombieReader().read(F/'zombie_challenges_before_oct24.png')
        self.assertEqual(e.screen,'zombie_challenges');self.assertEqual(e.values['mode'],MODE)
        self.assertFalse(e.values['acquire_ready']);self.assertFalse(e.values['five_clears_verified']);self.assertEqual(e.values['weekly_completed'],0)

    def test_board_identifies_zombie_as_unfinished_instead_of_inferred_done(self):
        e=BoardReader().read(F/'zombie_board_before_oct24.png')
        routed=ZombieReader().read(F/'zombie_board_before_oct24.png')
        self.assertEqual(routed.screen,'content_board')
        row=next(r for r in e.values['tiles'] if r['mode']==MODE)
        self.assertEqual((row['remaining'],row['total'],row['completed']),(5,5,False))
        self.assertIn(MODE,e.values['unfinished_modes'])
