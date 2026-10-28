import unittest
from pathlib import Path
from lib.objective_reader import ObjectiveReader
from lib.alliance_reader import AllianceReader

F=Path(__file__).parent/'fixtures'
class CurrentObjectiveReaderTests(unittest.TestCase):
 def test_weekly_infinite_challenge_is_manual_skip_with_no_start_control(self):
  e=AllianceReader().read(F/'alliance_infinite_challenge_oct24.png')
  self.assertEqual(e.screen,'alliance_weekly_skip');self.assertFalse(e.errors,e)
  self.assertTrue(e.values['weekly_skip_verified']);self.assertEqual(e.values['mode'],'ALLIANCE BATTLE')
  self.assertNotIn('point',e.values)

 def test_weekly_skip_requires_each_label_and_never_matches_normal_or_trivia(self):
  from lib.mission_reader import viewport
  from PIL import ImageDraw
  for box in ((67,18,258,52),(14,88,280,125),(1010,226,1210,260),(1060,150,1190,181)):
   with self.subTest(box=box):
    im=viewport(F/'alliance_infinite_challenge_oct24.png');ImageDraw.Draw(im).rectangle(box,fill='black')
    self.assertNotEqual(AllianceReader().read(im).screen,'alliance_weekly_skip')
  for name in ('alliance_normal_ready.png','alliance_normal_setup_current.png','alliance_normal_scored_current.png','trivia_completed_oct24_top.png'):
   with self.subTest(name=name):self.assertNotEqual(AllianceReader().read(F/name).screen,'alliance_weekly_skip')

 def test_completion_boundary_requires_both_row_label_and_check(self):
  from PIL import Image,ImageDraw
  for name,kind in [('weekly_material_top','weekly'),('event_quest_completed_current','quest')]:
   with self.subTest(name=name):
    from lib.mission_reader import viewport
    im=viewport(F/(name+'.png'))
    self.assertTrue(ObjectiveReader().read(im).values['completed_tail_verified'])
    # Preserve text but erase every completion check in the action column.
    ImageDraw.Draw(im).rectangle((1176,190,1214,706),fill='black')
    self.assertFalse(ObjectiveReader().read(im).values.get('completed_tail_verified',False))

 def test_current_normal_alliance_setup_verifies_label_and_entry(self):
  e=AllianceReader().read(F/'alliance_normal_setup_current.png')
  self.assertEqual(e.screen,'alliance_normal_setup');self.assertFalse(e.errors,e)
  self.assertEqual(e.values['variant'],'NORMAL');self.assertEqual(e.values['entries'],(1,1))
  from PIL import Image
  im=Image.open(F/'alliance_normal_setup_current.png').convert('RGB')
  im.paste((0,0,0),(1130,657,1185,698))
  e=AllianceReader().read(im);self.assertTrue(e.errors);self.assertNotIn('point',e.values)

 def test_event_quest_home_label_is_optional_and_progress_is_separate(self):
  from PIL import Image
  from lib.objective_reader import home_shortcuts
  im=Image.open(F/'event_quest_home_current.png').convert('RGB')
  self.assertEqual(home_shortcuts(im)['event_quest_point'],(1040,518))
  im.paste((0,0,0),(925,485,1255,550))
  self.assertNotIn('event_quest_point',home_shortcuts(im))
  e=ObjectiveReader().read(F/'event_quest_completed_current.png')
  self.assertEqual(e.screen,'event_quest_objectives');self.assertFalse(e.errors,e)
  self.assertEqual([(r.kind,r.done,r.total) for r in e.values['objectives']],[('dimension',10,10)])

 def test_verified_menu_survives_challenges_tab_classification(self):
  self.assertTrue(ObjectiveReader().read(F/'trivia_completed_top.png').values.get('menu_available'))

 def test_shifted_special_benefits_label_sets_current_icon_point(self):
  from PIL import Image
  from lib.objective_reader import home_shortcuts
  im=Image.open(F/'home_without_daily_current.png').convert('RGB')
  self.assertEqual(home_shortcuts(im)['benefits_point'],(845,126))
  shortcut=im.crop((800,90,915,176));im.paste((0,0,0),(800,90,915,176));im.paste(shortcut,(800,189))
  self.assertEqual(home_shortcuts(im)['benefits_point'],(845,225))
 def test_completed_trivia_is_not_a_daily_objective_list(self):
  e=ObjectiveReader().read(F/'trivia_completed_top.png')
  self.assertEqual(e.screen,'challenges_other_tab');self.assertNotIn('objectives',e.values)
 def test_full_home_without_daily_task_has_strong_navigation_proof(self):
  e=ObjectiveReader().read(F/'home_without_daily_current.png')
  self.assertEqual(e.screen,'game_home');self.assertTrue(e.values['home_controls_verified'])
  self.assertTrue(e.values['daily_shortcut_missing'])
 def test_dimmed_home_is_not_strong_navigation_proof(self):
  from PIL import Image,ImageEnhance
  e=ObjectiveReader().read(ImageEnhance.Brightness(Image.open(F/'home_without_daily_current.png')).enhance(.45))
  self.assertFalse(e.values.get('home_controls_verified',False))
 def test_battle_results_never_supply_full_home_proof(self):
  for name in ('timeline_result_current.png','otherworld_result_current.png','story_final_result.png'):
   with self.subTest(name=name):
    e=ObjectiveReader().read(F/name)
    self.assertFalse(e.values.get('home_controls_verified',False))
 def test_normal_scored_state_is_done_without_record_challenge(self):
  e=AllianceReader().read(F/'alliance_normal_scored_current.png')
  self.assertEqual(e.screen,'alliance_normal_done');self.assertFalse(e.errors,e)
  self.assertEqual(e.values['score'],210500);self.assertEqual(e.values['variant'],'NORMAL')
  self.assertNotIn('point',e.values)
 def test_live_daily_requirement(self):
  e=ObjectiveReader().read(F/'daily_challenges_top.png')
  self.assertEqual(e.screen,'daily_objectives');self.assertFalse(e.errors,e)
  self.assertEqual([(r.kind,r.done,r.total) for r in e.values['objectives']],[('dimension',0,1)])
 def test_excluded_event_names_are_discovered_dynamically(self):
  e=ObjectiveReader().read(F/'special_benefits.png')
  self.assertEqual(e.screen,'benefit_list')
  self.assertEqual([r['name'] for r in e.values['events'] if not r['excluded']],['WEEKLY TIER-4 MATERIAL PASS'])
 def test_normal_controls_auto_and_result(self):
  r=AllianceReader()
  for f,s in [('alliance_normal_ready','alliance_normal_ready'),('alliance_normal_setup','alliance_normal_setup'),('alliance_auto_battle','alliance_battle_auto'),('alliance_normal_result','alliance_result')]:
   e=r.read(F/(f+'.png'));self.assertEqual(e.screen,s);self.assertFalse(e.errors,e)
  self.assertTrue(r.read(F/'alliance_auto_battle.png').values['auto_on'])
  self.assertEqual(r.read(F/'alliance_normal_result.png').values['score'],166750)

 def test_dimension_exact_costs_result_and_dispatch_setup(self):
  from lib.sweep_reader import SweepReader
  from lib.dispatch_reader import DispatchReader
  e=SweepReader().read(F/'dimension_sweep_one.png')
  self.assertFalse(e.errors,e)
  self.assertEqual((e.values['selected'],e.values['boost_total']),(1,4))
  e=SweepReader().read(F/'dimension_sweep_result_one.png')
  self.assertEqual(e.values['clears'],1)
  r=DispatchReader()
  self.assertEqual(r.read(F/'dispatch_sector_seven.png').screen,'dispatch_sector_seven')
  e=r.read(F/'dispatch_7_1_preparation.png')
  self.assertFalse(e.errors,e)
  self.assertEqual((e.values['sector'],e.values['mission'],e.values['boost_cost']),(7,1,4))
  self.assertTrue(e.values['use_energy'])
