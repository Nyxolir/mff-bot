import unittest
from datetime import datetime,timedelta,timezone
from lib.objective_inspection import ObjectiveInspection
from lib.screen_reader import ScreenEvidence
from lib.objectives import parse_objectives

class InspectionTests(unittest.TestCase):
 def test_weekly_completion_boundary_keeps_requirements_above_it_without_scroll(self):
  now=datetime.now(timezone.utc);i=ObjectiveInspection(now);i.phase='benefits'
  i.observe(ScreenEvidence('benefit_list',{'events':[{'name':'Weekly','point':(630,198)}]}),now)
  e=ScreenEvidence('event_objectives',{'signature':'incomplete then complete','completed_tail_verified':True,
   'objectives':parse_objectives('page','[DIMENSION MISSION] Clear 1 Stage 0/1')})
  self.assertEqual(i.observe(e,now),('home',1185,36));self.assertEqual(i.phase,'benefits')
  i.observe(ScreenEvidence('benefit_list',{'events':[{'name':'Weekly','point':(630,198)}]}),now)
  self.assertTrue(i.done);self.assertEqual(i.plan.dimension_clears,1)

 def test_quest_completion_boundary_stops_after_top_is_checked(self):
  now=datetime.now(timezone.utc);i=ObjectiveInspection(now);i.phase='quest';i.source='Event Quest'
  e=ScreenEvidence('event_quest_objectives',{'signature':'complete','completed_tail_verified':True,'objectives':[]})
  self.assertEqual(i.observe(e,now),('scroll_up',800,550))
  self.assertEqual(i.observe(e,now),('home',1185,36));self.assertEqual(i.phase,'benefits')

 def test_back_from_unknown_event_can_resume_through_current_benefits_slot(self):
  now=datetime.now(timezone.utc);i=ObjectiveInspection(now);i.phase='event'
  self.assertEqual(i.observe(ScreenEvidence('game_home',{'benefits_point':(845,126)}),now),('click',845,126))
  self.assertEqual(i.phase,'benefits')
 def test_benefits_uses_current_point_and_never_old_fixed_slot(self):
  now=datetime.now(timezone.utc);i=ObjectiveInspection(now);i.phase='benefits'
  for y in (126,225,310):
   self.assertEqual(i.observe(ScreenEvidence('game_home',{'benefits_point':(845,y)}),now),('click',845,y))
  with self.assertRaises(ValueError):i.observe(ScreenEvidence('game_home'),now)
 def test_trivia_tab_is_switched_before_reading_daily_challenges(self):
  now=datetime.now(timezone.utc);i=ObjectiveInspection(now)
  self.assertEqual(i.observe(ScreenEvidence('challenges_other_tab',{'daily_tab_point':(200,113)}),now),('click',200,113))
  self.assertFalse(i.daily)
 def test_daily_and_dynamic_event_are_both_required_and_exclusions_not_opened(self):
  now=datetime.now(timezone.utc);i=ObjectiveInspection(now)
  daily=ScreenEvidence('daily_objectives',{'signature':'daily','objectives':parse_objectives('page','[DIMENSION MISSION] Clear 1 Stage (0/1)')})
  for _ in range(3):i.observe(daily,now)
  self.assertEqual(i.phase,'quest_home')
  i.observe(ScreenEvidence('game_home',{'benefits_point':(845,126)}),now)
  i.observe(ScreenEvidence('game_home',{'benefits_point':(845,126)}),now+timedelta(seconds=3))
  i.observe(ScreenEvidence('game_home',{'benefits_point':(845,126)}),now+timedelta(seconds=6))
  e=ScreenEvidence('benefit_list',{'events':[{'name':'Rotated New Event','point':(630,198)},{'name':'OTHERWORLD BATTLE PASS','point':(630,278)},{'name':'FUTURE PASS','point':(630,358)}]})
  self.assertEqual(i.observe(e,now),('click',630,198))
  event=ScreenEvidence('event_objectives',{'signature':'event','objectives':parse_objectives('page','[DIMENSION MISSION] Acquire Contribution Reward 0/1')})
  for _ in range(3):i.observe(event,now)
  self.assertIsNone(i.observe(e,now));self.assertTrue(i.done)
  self.assertEqual(i.plan.dimension_clears,5)
  self.assertTrue(i.plan.claim_contribution)

 def test_optional_quest_required_before_finishing_and_merged_with_daily(self):
  now=datetime.now(timezone.utc);i=ObjectiveInspection(now);i.phase='quest_home'
  self.assertEqual(i.observe(ScreenEvidence('game_home',{'event_quest_point':(1040,518)}),now),('click',1040,518))
  quest=ScreenEvidence('event_quest_objectives',{'signature':'quest','objectives':parse_objectives('page','[DIMENSION MISSION] Clear 10 Stages 3/10')})
  self.assertEqual(i.observe(quest,now),('scroll_up',800,550))
  for _ in range(3):i.observe(quest,now)
  self.assertEqual(i.phase,'benefits')
  i.observe(ScreenEvidence('benefit_list',{'events':[]}),now)
  self.assertTrue(i.done);self.assertEqual(i.plan.dimension_clears,7)

 def test_menu_direct_for_daily_but_home_for_home_only_events(self):
  now=datetime.now(timezone.utc);i=ObjectiveInspection(now)
  e=ScreenEvidence('mission_preparation',{'menu_available':True,'home_available':True})
  self.assertEqual(i.observe(e,now),('menu',1249,37))
  for phase in ('benefits','quest_home'):
   i.phase=phase;self.assertEqual(i.observe(e,now),('home',1185,36))

 def test_missing_quest_shortcut_is_rechecked_and_reappearing_event_is_opened(self):
  now=datetime.now(timezone.utc);i=ObjectiveInspection(now);i.phase='quest_home'
  missing=ScreenEvidence('game_home',{'benefits_point':(845,126)})
  for offset in (0,0,1,3):
   self.assertEqual(i.observe(missing,now+timedelta(seconds=offset)),('wait',0,0))
   self.assertEqual(i.phase,'quest_home')
  self.assertEqual(i.observe(ScreenEvidence('game_home',{'event_quest_point':(1040,507)}),now+timedelta(seconds=6)),('click',1040,507))
  self.assertTrue(i.quest_present);self.assertEqual(i.phase,'quest')

 def test_genuinely_absent_quest_needs_three_spaced_home_observations(self):
  now=datetime.now(timezone.utc);i=ObjectiveInspection(now);i.phase='quest_home'
  missing=ScreenEvidence('game_home',{'benefits_point':(845,126)})
  self.assertEqual(i.observe(missing,now),('wait',0,0))
  self.assertEqual(i.observe(missing,now+timedelta(seconds=3)),('wait',0,0))
  self.assertEqual(i.observe(missing,now+timedelta(seconds=6)),('click',845,126))
  self.assertEqual(i.phase,'benefits');self.assertFalse(i.quest_present)
