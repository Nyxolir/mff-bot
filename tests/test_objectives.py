import unittest
from datetime import datetime,timedelta,timezone
from lib.objectives import Objective, ObjectiveLedger,parse_objectives,excluded_event,normal_alliance_allowed
from lib.daily_queue import next_reset

class ObjectiveTests(unittest.TestCase):
 def setUp(self):self.now=datetime.now(timezone.utc)
 def plan(self,texts):
  ledger=ObjectiveLedger();ledger.begin(self.now,['Rotating Event','OTHERWORLD BATTLE PASS','FUTURE PASS'])
  for source,text in zip(('Daily Challenges','Rotating Event'),texts):
   ledger.observe(source,parse_objectives(source,text));ledger.finish(source)
  return ledger.plan(self.now)
 def test_none_or_completed_dimension_is_skipped(self):
  self.assertEqual(self.plan(('[DIMENSION MISSION] Clear 1 Stage (1/1)','Upgrade gear 1 time (0/1)')).dimension_clears,0)
 def test_one_clear_serves_all_one_clear_requirements(self):
  self.assertEqual(self.plan(('[DIMENSION MISSION] Clear 1 Stage (0/1)','[DIMENSION MISSION] Clear 1 time 0/1')).dimension_clears,1)
 def test_contribution_requires_five_then_claim(self):
  p=self.plan(('[DIMENSION MISSION] Clear 1 Stage (0/1)','[DIMENSION MISSION] Acquire Contribution Reward 1 time 0/1'))
  self.assertEqual((p.dimension_clears,p.claim_contribution),(5,True))
 def test_dispatch_only_with_energy_requirement(self):
  p=self.plan(('', '[DISPATCH MISSION] Clear 1 time using Energy 0/1'))
  self.assertEqual((p.dispatch_clears,p.dispatch_sector,p.dispatch_mission),(1,7,1))
  self.assertEqual(self.plan(('', '[DISPATCH MISSION] Clear 1 time 0/1')).dispatch_clears,0)
 def test_unknown_progress_and_partial_inspection_block(self):
  with self.assertRaises(ValueError):parse_objectives('daily','[DIMENSION MISSION] Clear 1 Stage')
  l=ObjectiveLedger();l.begin(self.now,['New Title']);l.finish('Daily Challenges')
  with self.assertRaises(ValueError):l.plan(self.now)
 def test_reset_expires_plan(self):
  l=ObjectiveLedger();l.begin(self.now,[]);l.finish('Daily Challenges')
  with self.assertRaises(ValueError):l.plan(next_reset(self.now))
 def test_only_explicit_excluded_passes_and_normal_variant(self):
  self.assertTrue(excluded_event('Otherworld Battle Pass'));self.assertTrue(excluded_event('Future Pass'))
  self.assertTrue(excluded_event('Otherworld\nBattle   Pass'))
  self.assertTrue(excluded_event('  Future  Pass! '))
  self.assertFalse(excluded_event('New Weekly Event'))
  self.assertFalse(excluded_event('Weekly Tier-4 Material Pass'))
  for variant in ('EXTREME','LEGEND','NORMAL MODE EXTREME','INFINITE'):
   self.assertFalse(normal_alliance_allowed(variant,1,True))
  self.assertTrue(normal_alliance_allowed('NORMAL',1,True))

 def test_dispatch_waits_for_boost_and_reset(self):
  from lib.objectives import dispatch_start_reason,MissionPlan
  from lib.daily_queue import DailyRaidGate
  gate=DailyRaidGate()
  for k,v in [('soul',(0,165)),('seed',(0,300))]:gate.observe(k,v,self.now,self.now)
  v=dict(sector=7,mission=1,use_energy=True,start_verified=True,crystal_total=0,energy_cost=4,boost_cost=4,energy_available=100,boost_available=3)
  plan=MissionPlan(0,False,1)
  self.assertIn('boost',dispatch_start_reason(v,gate,self.now,self.now,plan))
  v['boost_available']=4
  self.assertIsNone(dispatch_start_reason(v,gate,self.now,self.now,plan))
  v['mission']=2
  self.assertIn('7-1',dispatch_start_reason(v,gate,self.now,self.now,plan))
