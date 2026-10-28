import unittest
from datetime import datetime,timezone
from pathlib import Path
from PIL import ImageDraw
from lib.mission_reader import viewport
from lib.objective_reader import ObjectiveReader
from lib.objective_inspection import ObjectiveInspection
from lib.objectives import parse_objectives,ObjectiveLedger
from lib.screen_reader import ScreenEvidence

F=Path(__file__).parent/'fixtures'
class MaxLevelPassTests(unittest.TestCase):
    def test_actual_max_level_pass_does_not_parse_unclaimed_challenge_rows(self):
        e=ObjectiveReader().read(F/'special_pass_max_level_oct27.png')
        self.assertEqual(e.screen,'event_rewards');self.assertFalse(e.errors)
        self.assertTrue(e.values['pass_max_level_verified']);self.assertEqual(e.values['pass_title'],'Emblem Upgrade Special Pass')
        self.assertEqual(e.values['objectives'],[])

    def test_max_level_requires_label_full_bar_and_pass_identity(self):
        for box in ((435,168,548,192),(562,172,678,187),(67,18,260,52),(227,99,765,145)):
            with self.subTest(box=box):
                image=viewport(F/'special_pass_max_level_oct27.png');ImageDraw.Draw(image).rectangle(box,fill='black')
                self.assertFalse(ObjectiveReader().read(image).values.get('pass_max_level_verified',False))
        for name in ('weekly_elite_complete_oct27.png','weekly_material_top.png','daily_challenges_top.png','event_quest_completed_current.png'):
            with self.subTest(name=name):self.assertFalse(ObjectiveReader().read(F/name).values.get('pass_max_level_verified',False))

    def test_weekly_layout_accepts_verified_max_indicator_without_assuming_a_level_number(self):
        image=viewport(F/'special_pass_max_level_oct27.png');weekly=viewport(F/'weekly_elite_complete_oct27.png')
        for box in ((67,18,260,52),(227,99,765,145)):image.paste(weekly.crop(box),box)
        e=ObjectiveReader().read(image)
        self.assertTrue(e.values.get('pass_max_level_verified'));self.assertEqual(e.values['pass_title'],'WEEKLY ELITE GEAR PASS')

    def test_skipping_maxed_pass_keeps_daily_and_event_quest_dimension_requirements(self):
        now=datetime.now(timezone.utc);i=ObjectiveInspection(now);i.phase='benefits'
        i.daily=parse_objectives('Daily Challenges','[DIMENSION MISSION] Clear 1 Stage 0/1')
        i.quest_present=True;i.quest=parse_objectives('Event Quest','[DIMENSION MISSION] Clear 10 Stages 0/10')
        name='Emblem Upgrade Special Pass |';benefits=ScreenEvidence('benefit_list',{'events':[{'name':name,'point':(630,438)}]})
        self.assertEqual(i.observe(benefits,now),('click',630,438))
        i.ledger.observe(name,parse_objectives(name,'[DIMENSION MISSION] Acquire Contribution Reward 0/1'))
        e=ObjectiveReader().read(F/'special_pass_max_level_oct27.png')
        self.assertEqual(i.observe(e,now),('home',1185,36));self.assertEqual(i.phase,'benefits')
        self.assertEqual(i.max_level_passes,{name});self.assertIn(name,i.visited)
        self.assertIsNone(i.observe(benefits,now));self.assertTrue(i.done)
        self.assertEqual(i.plan.dimension_clears,10);self.assertFalse(i.plan.claim_contribution)
        self.assertEqual({row.source for row in i.ledger.rows.values()},{'Daily Challenges','Event Quest'})

    def test_wrong_pass_or_missing_max_proof_does_not_skip(self):
        now=datetime.now(timezone.utc);i=ObjectiveInspection(now);i.phase='benefits'
        i.observe(ScreenEvidence('benefit_list',{'events':[{'name':'Different Weekly Pass','point':(630,198)}]}),now)
        e=ObjectiveReader().read(F/'special_pass_max_level_oct27.png')
        with self.assertRaises(ValueError):i.observe(e,now)
        self.assertFalse(i.visited);self.assertFalse(i.max_level_passes)
        e.values.pop('pass_max_level_verified')
        self.assertEqual(i.observe(e,now),('click',1110,181));self.assertFalse(i.visited)
        for source in ('Daily Challenges','Event Quest','Unknown'):
            ledger=ObjectiveLedger();ledger.begin(now,{'Event Quest'})
            with self.assertRaises(ValueError):ledger.finish_max_level_pass(source)
