from datetime import datetime,timedelta,timezone
from pathlib import Path
from dataclasses import replace
from copy import deepcopy
import unittest
from lib.epic_sweep import bind_epic_batch,boost_balance
from lib.mission_reader import viewport
from lib.sweep_reader import SweepReader
from lib.daily_queue import DailyRaidGate,BatchEvidence,batch_decision,QueueAction,next_reset
from lib.screen_reader import ScreenEvidence

class EpicSweepTests(unittest.TestCase):
    def test_mutual_enemy_duplicate_heading_reconciles_exact_result(self):
        result=SweepReader().read(Path(__file__).parent/'fixtures/epic_mutual_enemy_result_oct24.png')
        self.assertEqual(result.screen,'sweep_result');self.assertFalse(result.errors,result)
        self.assertEqual((result.values['mode'],result.values['clears']),('MUTUAL ENEMY',2))
        self.assertTrue(result.values['result_verified'])
        from unittest.mock import patch
        from lib.epic_sweep import read_epic_result
        with patch('lib.epic_sweep.read_fields',return_value={
            'stage':'MUTUAL ENEMY Sinister Schemes','clears':'2 time(s)','clears_top':''}):
            invalid=read_epic_result(None,lambda *args:True)
        self.assertTrue(invalid.errors)
        self.assertNotIn('result_verified',invalid.values)

    def test_oct24_dimmed_ticket_stock_is_not_read(self):
        result=SweepReader().read(Path(__file__).parent/'fixtures/epic_ticket_final_one_oct24.png')
        self.assertEqual(result.screen,'sweep');self.assertFalse(result.errors,result)
        self.assertNotIn('tickets_available',result.values)
        self.assertNotIn('tickets_available',result.text)
        self.assertNotIn('tickets_normalized',result.text)
        self.assertEqual(result.values['selected'],3)
        self.assertFalse(result.values['sweep_verified'])

    def test_blank_ticket_balance_does_not_block_boosted_sweep(self):
        from PIL import ImageDraw
        image=viewport(Path(__file__).parent/'fixtures/epic_ticket_final_one_oct24.png')
        ImageDraw.Draw(image).rectangle((416,662,493,697),fill='black')
        result=SweepReader().read(image)
        self.assertFalse(result.errors,result)
        self.assertNotIn('tickets_available',result.values)

    def test_chaos_boost_is_verified_without_reading_energy_cost(self):
        e=SweepReader().read(Path(__file__).parent/'fixtures/epic_chaos_energy_oct24.png')
        self.assertFalse(e.errors,e);self.assertEqual(e.values['mode'],'BEGINNING OF THE CHAOS')
        self.assertEqual((e.values['remaining'],e.values['boost_unit']),(2,4))
        from PIL import Image,ImageDraw
        im=Image.open(Path(__file__).parent/'fixtures/epic_chaos_energy_oct24.png').convert('RGB')
        ImageDraw.Draw(im).rectangle((1001,649,1057,693),fill=(10,170,235))
        e=SweepReader().read(im);self.assertFalse(e.errors);self.assertTrue(e.values['preparation_verified'])

    def test_observed_1080_cutting_cable_keeps_full_batch_costs(self):
        e=SweepReader().read(Path(__file__).parent/'fixtures/epic_cutting_1080_current.png')
        self.assertEqual(e.screen,'epic_preparation');self.assertFalse(e.errors,e)
        self.assertEqual((e.values['mode'],e.values['remaining'],e.values['boost_unit']),('CUTTING CABLE',3,4))
    def test_dimmed_current_popup_does_not_depend_on_background_title_or_rgb(self):
        result=SweepReader().read(Path(__file__).parent/'fixtures/epic_sweep_live_dimmed.png')
        self.assertEqual(result.screen,'sweep');self.assertFalse(result.errors,result)
        self.assertEqual(result.values['selected'],3);self.assertEqual(result.values['boost_available'],100)
        self.assertFalse(result.values['sweep_verified'])
    def test_scaled_preparation_icons_keep_verified_costs(self):
        result=SweepReader().read(Path(__file__).parent/'fixtures/epic_preparation_live.png')
        self.assertEqual(result.screen,'epic_preparation');self.assertFalse(result.errors,result)
        self.assertEqual((result.values['boost_unit'],result.values['remaining']),(4,2))
    def test_live_result_has_exact_mission_count_and_safe_close(self):
        result=SweepReader().read(Path(__file__).parent/'fixtures/epic_result_live.png')
        self.assertEqual(result.screen,'sweep_result');self.assertFalse(result.errors,result)
        self.assertEqual((result.values['mode'],result.values['clears']),('BEGINNING OF THE CHAOS',2))
        self.assertEqual(result.values['controls'],{'close_result':(880,676)})
    @classmethod
    def setUpClass(cls):
        fixture=Path(__file__).parent/'fixtures';reader=SweepReader()
        cls.prep=reader.read(fixture/'epic_chaos_preparation.png')
        cls.modal=reader.read(fixture/'epic_chaos_sweep_two.png')

    def setUp(self):
        self.now=datetime.now(timezone.utc);self.target='BEGINNING OF THE CHAOS'
        self.proof=(self.prep,self.now,3)

    def test_real_controls_and_total_costs(self):
        self.assertEqual(self.prep.screen,'epic_preparation');self.assertFalse(self.prep.errors,self.prep)
        self.assertFalse(self.modal.errors,self.modal);self.assertFalse(self.modal.values['sweep_verified'])
        values,captured=bind_epic_batch(self.proof,self.modal,self.target,2,3,self.now,self.now)
        self.assertEqual(values['boost_total'],8);self.assertIsNone(values['energy_total']);self.assertIsNone(values['ticket_total'])
        self.assertEqual(values['controls']['clear_batch'],(640,555))
        gate=DailyRaidGate()
        for key,counter in [('soul',(0,165)),('seed',(0,300))]:gate.observe(key,counter,self.now,self.now)
        fields={key:values[key] for key in BatchEvidence.__dataclass_fields__ if key in values}
        batch=BatchEvidence(**fields,remaining=2,captured_at=captured)
        self.assertEqual(batch_decision(batch,gate,self.now).action,QueueAction.CLEAR)
        self.assertEqual(batch_decision(replace(batch,boost_available=7),gate,self.now).action,QueueAction.BOOST)
        self.assertEqual(batch_decision(replace(batch,energy_available=7),gate,self.now).action,QueueAction.CLEAR)
        self.assertEqual(batch_decision(replace(batch,tickets_available=1),gate,self.now).action,QueueAction.CLEAR)

    def test_no_stale_or_other_mission_preparation(self):
        args=(self.modal,self.target,2,3,self.now,self.now)
        for proof in (None,(self.prep,self.now-timedelta(seconds=121),3),(self.prep,self.now,2)):
            with self.assertRaises(ValueError):bind_epic_batch(proof,*args)
        with self.assertRaises(ValueError):bind_epic_batch(self.proof,self.modal,'CUTTING CABLE',2,3,self.now,self.now)
        with self.assertRaises(ValueError):bind_epic_batch(self.proof,self.modal,self.target,1,3,self.now,self.now)
        with self.assertRaises(ValueError):bind_epic_batch(self.proof,self.modal,self.target,2,3,self.now,next_reset(self.now))
        invalid=deepcopy(self.modal);invalid.values['selected']=1
        with self.assertRaises(ValueError):bind_epic_batch(self.proof,invalid,self.target,2,3,self.now,self.now)

    def test_fresh_popup_balance_not_aged_by_previous_preparation(self):
        proof=(self.prep,self.now-timedelta(seconds=60),3)
        values,captured=bind_epic_batch(proof,self.modal,self.target,2,3,self.now,self.now)
        self.assertEqual(captured,self.now);self.assertIsNone(values['energy_total'])
        with self.assertRaises(ValueError):bind_epic_batch(proof,self.modal,self.target,2,3,self.now-timedelta(seconds=31),self.now)

    def test_epic_result_has_its_own_close_and_exact_clear_count(self):
        result=SweepReader().read(Path(__file__).parent/'fixtures/epic_chaos_result_two.png')
        self.assertFalse(result.errors,result)
        self.assertEqual(result.values['mode'],self.target)
        self.assertEqual(result.values['clears'],2)
        self.assertEqual(result.values['controls'],{'close_result':(880,676)})

    def test_boost_ocr_cannot_drop_a_digit(self):
        image=viewport(Path(__file__).parent/'fixtures/epic_chaos_done_preparation.png')
        self.assertEqual(boost_balance(image,'9','92'),92)
        self.assertEqual(boost_balance(image,'9','2'),92)
        image=viewport(Path(__file__).parent/'fixtures/gbr_seed_zero_unreadable_boost.png')
        self.assertEqual(boost_balance(image,'','89'),89)

    def test_three_entry_popup_and_ticket_label_are_read_without_extra_digit(self):
        result=SweepReader().read(Path(__file__).parent/'fixtures/epic_cutting_sweep_three.png')
        self.assertFalse(result.errors,result)
        self.assertEqual(result.values['selected'],3)
        self.assertNotIn('tickets_available',result.values)
        self.assertNotIn('ticket_unit',result.values)

    def test_live_qt_popup_needs_boost_without_energy_balance(self):
        result=SweepReader().read(Path(__file__).parent/'fixtures/epic_cutting_sweep_qt.png')
        self.assertFalse(result.errors,result)
        self.assertNotIn('energy_available',result.values)
        self.assertEqual(result.values['boost_available'],100)
        self.assertEqual(result.values['selected'],3)

    def test_transient_result_never_falls_back_to_dimension_count(self):
        result=SweepReader().read(Path(__file__).parent/'fixtures/epic_result_transition_qt.png')
        self.assertNotEqual(result.values.get('controls'),{'close_result':(638,676)})
        if not result.errors:
            self.assertEqual(result.values['mode'],'ENDING THE STRYFE')
            self.assertLess(result.values['clears'],3)

    def test_faint_sevens_do_not_become_eleven(self):
        result=SweepReader().read(Path(__file__).parent/'fixtures/epic_madness_sweep_seventyseven.png')
        self.assertFalse(result.errors,result)
        self.assertEqual(result.values['boost_available'],77)
        self.assertEqual(result.values['selected'],4)

    def test_one_remaining_uses_one_even_when_other_button_says_ten(self):
        modal=SweepReader().read(Path(__file__).parent/'fixtures/epic_magneto_one_left.png')
        self.assertFalse(modal.errors,modal)
        self.assertEqual(modal.values['boost_available'],71)
        prep=ScreenEvidence('epic_preparation',dict(mode="MAGNETO'S MIGHT",remaining=1,
            preparation_verified=True,energy_unit=4,boost_unit=4))
        values,_=bind_epic_batch((prep,self.now,3),modal,"MAGNETO'S MIGHT",1,3,self.now,self.now)
        self.assertEqual(values['selected'],1)
        self.assertEqual(values['controls']['clear_batch'],(408,555))
        self.assertEqual(values['boost_total'],4)
        prep.values['remaining']=2
        with self.assertRaises(ValueError):bind_epic_batch((prep,self.now,3),modal,"MAGNETO'S MIGHT",2,3,self.now,self.now)

if __name__=='__main__':unittest.main()
