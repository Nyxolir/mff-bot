from dataclasses import replace
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
import unittest
from PIL import Image,ImageDraw
from lib.daily_queue import DailyRaidGate,BatchEvidence,QueueAction,batch_decision
from lib.sweep_reader import SweepReader
from lib.dispatch_reader import DispatchReader
from lib.story_reader import StoryReader
from lib.zombie_reader import ZombieReader
from lib.arena_reader import ArenaReader
from lib.objectives import MissionPlan,dispatch_start_reason

F=Path(__file__).parent/'fixtures'

class BoostOnlyTests(unittest.TestCase):
    def test_missing_or_zero_energy_and_tickets_never_block_but_boost_still_does(self):
        now=datetime.now(timezone.utc);gate=DailyRaidGate()
        for k,v in [('soul',(0,165)),('seed',(0,300))]:gate.observe(k,v,now,now)
        batch=BatchEvidence('DIMENSION MISSION',10,10,None,40,None,None,40,None,now,0,True,True)
        for value in (None,0,'unreadable',False):
            e=replace(batch,energy_total=value,ticket_total=value,energy_available=value,tickets_available=value)
            self.assertEqual(batch_decision(e,gate,now).action,QueueAction.CLEAR)
        self.assertEqual(batch_decision(replace(batch,boost_available=39),gate,now).action,QueueAction.BOOST)
        self.assertEqual(batch_decision(replace(batch,crystal_total=1),gate,now).action,QueueAction.ERROR)

    def test_reported_ticket_counter_screen_no_longer_reads_or_requires_ticket_balance(self):
        e=SweepReader().read(F/'epic_ticket_recurrence_oct25.png')
        self.assertFalse(e.errors,e);self.assertEqual(e.screen,'sweep')
        self.assertEqual((e.values['selected'],e.values['boost_available']),(2,13))
        self.assertNotIn('tickets_available',e.text);self.assertNotIn('energy_available',e.text)

    def test_dimension_energy_and_ticket_regions_can_be_blank(self):
        im=Image.open(F/'dimension_sweep_ten_adb_oct25.png').convert('RGB')
        for box in ((519,19,606,49),(447,656,518,687),(532,389,574,424),(710,382,810,432)):
            ImageDraw.Draw(im).rectangle(box,fill='black')
        e=SweepReader().read(im);self.assertFalse(e.errors,e)
        self.assertEqual((e.values['selected'],e.values['boost_total']),(10,40))

    def test_story_and_repeat_modes_ignore_resource_amount_regions(self):
        cases=[(StoryReader(),'story_ultimate_lobby.png',(519,19,606,49),'story_ultimate'),
            (ArenaReader(),'otherworld_repeat_four_oct24.png',(610,340,703,379),'otherworld_repeat'),
            (ZombieReader(),'zombie_repeat_max_oct24.png',(615,354,677,395),'zombie_repeat')]
        for reader,name,box,screen in cases:
            with self.subTest(name=name):
                im=Image.open(F/name).convert('RGB');ImageDraw.Draw(im).rectangle(box,fill='black')
                e=reader.read(im);self.assertFalse(e.errors,e);self.assertEqual(e.screen,screen)

    def test_dispatch_boost_is_sufficient_without_energy_fields(self):
        now=datetime.now(timezone.utc);gate=DailyRaidGate()
        for k,v in [('soul',(0,165)),('seed',(0,300))]:gate.observe(k,v,now,now)
        v=dict(sector=7,mission=1,use_energy=True,start_verified=True,crystal_total=0,boost_cost=4,boost_available=4)
        self.assertIsNone(dispatch_start_reason(v,gate,now,now,MissionPlan(0,False,1)))
        v['boost_available']=3;self.assertIn('boost',dispatch_start_reason(v,gate,now,now,MissionPlan(0,False,1)))
