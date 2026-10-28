from datetime import datetime,timedelta,timezone
from pathlib import Path
import unittest
import numpy as np
from PIL import Image
from lib.dispatch_supplies import DispatchSuppliesReader,DispatchSuppliesSession,reward_dot
from lib.screen_reader import ScreenEvidence

class SuppliesTests(unittest.TestCase):
    def setUp(self):self.now=datetime.now(timezone.utc)
    def map(self,pink=True,verified=True):
        return ScreenEvidence('dispatch_supplies_map',{'cards':[dict(key='MIDTOWN',sector=1,fill=1,pink_dot=pink)],'signature':((171,389),),'claim_all_verified':verified,'claim_all_point':(708,670)})
    def test_pink_dot_claims_all_once(self):
        s=DispatchSuppliesSession(self.now)
        self.assertEqual(s.observe(self.map(),self.now),('claim',708,670))
        self.assertEqual(s.observe(self.map(),self.now),('wait',0,0))
        self.assertEqual(s.observe(ScreenEvidence('dispatch_supply_result'),self.now),('ack',640,667))
        self.assertIsNone(s.observe(self.map(False),self.now));self.assertEqual(s.claimed,1)
    def test_full_bar_without_dot_never_claims(self):
        s=DispatchSuppliesSession(self.now)
        self.assertIsNone(s.observe(self.map(False),self.now));self.assertIsNone(s.pending)
        self.assertEqual(s.actions,0);self.assertTrue(s.done)

    def test_right_side_visible_dots_are_enough_without_panning(self):
        evidence=self.map();evidence.values['cards'][0].update(key='ASGARD',sector=13)
        s=DispatchSuppliesSession(self.now)
        self.assertEqual(s.observe(evidence,self.now),('claim',708,670))

    def test_schedule_persists_claim_across_daily_reset(self):
        from lib.dispatch_schedule import next_supply_check,load_schedule
        claimed=self.now.replace(hour=14,minute=0,second=0,microsecond=0)
        due=next_supply_check(claimed,claimed)
        self.assertEqual(due,claimed+timedelta(hours=11,minutes=50))
        last,restored=load_schedule({'last_claimed_at':claimed.isoformat(),'next_check_at':due.isoformat()},claimed+timedelta(hours=1))
        self.assertEqual(last,claimed);self.assertEqual(restored,due)
        self.assertEqual(next_supply_check(due,last),due+timedelta(minutes=10))

    def test_unknown_claim_time_uses_observed_fill_and_rejects_bad_cache(self):
        from lib.dispatch_schedule import next_supply_check,load_schedule
        self.assertEqual(next_supply_check(self.now,fill=.5),self.now+timedelta(hours=5,minutes=50))
        self.assertEqual(load_schedule({'next_check_at':(self.now+timedelta(days=5)).isoformat()},self.now),(None,self.now))
        self.assertEqual(load_schedule({'last_claimed_at':self.now.replace(tzinfo=None).isoformat(),'next_check_at':self.now.isoformat()},self.now),(None,self.now))

    def test_verified_claim_schedule_survives_controller_restart(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch,Mock
        from lib.gui.widgets import dispatch_supplies_controls as controls
        work=Path(__file__).resolve().parents[3]/'work'
        with TemporaryDirectory(dir=work) as folder,patch.object(controls,'SUPPLY_STATE',Path(folder)/'state.json'),patch.object(controls,'SUPPLY_NEXT',Path(folder)/'old.txt'):
            host=controls.DispatchSuppliesControls();host.init_dispatch_supplies()
            host.queue_target=None;host.dispatch_supply_resume=None;host.log=Mock()
            state=DispatchSuppliesSession(self.now);state.observe(self.map(),self.now);state.observe(self.map(False),self.now)
            host.dispatch_supply_state=state;host.finish_dispatch_supplies()
            restored=controls.DispatchSuppliesControls();restored.init_dispatch_supplies()
            self.assertEqual(restored.dispatch_supply_last_claim,self.now)
            self.assertEqual(restored.dispatch_supply_next,self.now+timedelta(hours=11,minutes=50))
    def test_claim_requires_verified_button(self):
        with self.assertRaises(ValueError):DispatchSuppliesSession(self.now).observe(self.map(verified=False),self.now)
    def test_uncertain_claim_never_retries(self):
        s=DispatchSuppliesSession(self.now);s.observe(self.map(),self.now)
        with self.assertRaises(ValueError):s.observe(self.map(),self.now+timedelta(seconds=61))
        self.assertEqual(s.actions,1)
    def test_panels_close_without_timer_ocr(self):
        reader=DispatchSuppliesReader()
        for name in ['dispatch_rewards_sector8_partial.png','dispatch_rewards_qt_partial.png','dispatch_rewards_full_panel.png']:
            evidence=reader.read(Path(__file__).parent/'fixtures'/name)
            self.assertEqual(evidence.screen,'dispatch_supply_panel');self.assertFalse(evidence.errors)
            self.assertEqual(DispatchSuppliesSession(self.now).observe(evidence,self.now),('click',1244,108))
    def test_real_dots_at_reward_corners(self):
        pixels=np.asarray(Image.open(Path(__file__).parent/'fixtures/dispatch_rewards_full_panel.png').convert('RGB'))
        for box in [(85,371,172,37),(538,327,173,37),(312,584,172,37)]:self.assertTrue(reward_dot(pixels,box))
    def test_partial_map_header_notifications_do_not_authorize_claim(self):
        reader=DispatchSuppliesReader()
        for name in ['dispatch_rewards_partial.png','dispatch_rewards_left_end.png','dispatch_rewards_right_map.png']:
            evidence=reader.read(Path(__file__).parent/'fixtures'/name)
            self.assertEqual(evidence.screen,'dispatch_supplies_map');self.assertFalse(evidence.errors)
            self.assertFalse(any(c['pink_dot'] for c in evidence.values['cards']))

    def test_actual_full_map_has_reward_dots_and_claim_all(self):
        e=DispatchSuppliesReader().read(Path(__file__).parent/'fixtures/dispatch_rewards_full_map.png')
        self.assertEqual(e.screen,'dispatch_supplies_map');self.assertFalse(e.errors)
        self.assertTrue(all(c['pink_dot'] for c in e.values['cards']))
        self.assertEqual(DispatchSuppliesSession(self.now).observe(e,self.now),('claim',708,670))

    def test_help_icon_does_not_pollute_dispatch_title(self):
        e=DispatchSuppliesReader().read(Path(__file__).parent/'fixtures/dispatch_rewards_title_icon_oct24.png')
        self.assertEqual(e.screen,'dispatch_supplies_map');self.assertFalse(e.errors)
        self.assertTrue(e.values['claim_all_verified'])
        self.assertTrue(any(c['pink_dot'] for c in e.values['cards']))
        self.assertEqual(DispatchSuppliesSession(self.now).observe(e,self.now),('claim',708,670))

    def test_ready_cards_without_claim_all_label_do_not_authorize_claim(self):
        from PIL import ImageDraw
        image=Image.open(Path(__file__).parent/'fixtures/dispatch_rewards_title_icon_oct24.png').convert('RGB')
        ImageDraw.Draw(image).rectangle((618,641,799,696),fill=(0,173,235))
        e=DispatchSuppliesReader().read(image)
        self.assertNotEqual(e.screen,'dispatch_supplies_map')
        self.assertFalse(e.values.get('claim_all_verified'))

    def test_real_immediate_post_claim_map_confirms_pending_collection(self):
        reader=DispatchSuppliesReader()
        ready=reader.read(Path(__file__).parent/'fixtures/dispatch_rewards_title_icon_oct24.png')
        empty=reader.read(Path(__file__).parent/'fixtures/dispatch_rewards_empty_map_oct24.png')
        self.assertEqual(empty.screen,'dispatch_supply_empty_map')
        s=DispatchSuppliesSession(self.now)
        self.assertEqual(s.observe(ready,self.now),('claim',708,670))
        self.assertEqual(s.observe(ScreenEvidence('unknown'),self.now+timedelta(seconds=30)),('wait',0,0))
        self.assertIsNone(s.observe(empty,self.now+timedelta(seconds=35)))
        self.assertEqual(s.claimed,1);self.assertTrue(s.done);self.assertIsNone(s.pending)
        fresh=DispatchSuppliesSession(self.now)
        self.assertIsNone(fresh.observe(empty,self.now));self.assertEqual(fresh.claimed,0);self.assertEqual(fresh.fill,0)

    def test_empty_map_requires_both_empty_supply_cards(self):
        from PIL import ImageDraw
        image=Image.open(Path(__file__).parent/'fixtures/dispatch_rewards_empty_map_oct24.png').convert('RGB')
        ImageDraw.Draw(image).rectangle((84,350,258,409),fill=(0,173,235))
        self.assertNotEqual(DispatchSuppliesReader().read(image).screen,'dispatch_supply_empty_map')

    def test_real_claim_result_can_be_recovered_after_restart(self):
        evidence=DispatchSuppliesReader().read(Path(__file__).parent/'fixtures/dispatch_claim_all_result.png')
        self.assertEqual(evidence.screen,'dispatch_supply_result')
        s=DispatchSuppliesSession(self.now)
        self.assertEqual(s.observe(evidence,self.now),('ack',640,667))
        self.assertIsNone(s.observe(self.map(False),self.now));self.assertEqual(s.claimed,1)

    def test_actual_claimed_map_has_no_reward_dots(self):
        e=DispatchSuppliesReader().read(Path(__file__).parent/'fixtures/dispatch_rewards_claimed_map.png')
        self.assertEqual(e.screen,'dispatch_supplies_map');self.assertFalse(e.errors)
        self.assertTrue(all(not c['pink_dot'] and c['fill']==0 for c in e.values['cards']))
