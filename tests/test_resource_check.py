from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from PIL import Image, ImageEnhance
from lib.resource_check import next_navigation, resource_status, Navigation, perform_navigation
from lib.screen_reader import ScreenReader, ScreenEvidence

FIXTURES=Path(__file__).parent/"fixtures"


class ResourceTests(unittest.TestCase):
    def test_clean_full_remaining_counts_do_not_lose_slash_or_first_digit(self):
        for name,key,expected in [('gbr_soul_full_clean_oct24.png','soul',(165,165)),
                                  ('gbr_seed_full_clean_oct24.png','seed',(300,300))]:
            with self.subTest(name=name):
                e=ScreenReader().read(FIXTURES/name,resource_check=True)
                self.assertFalse(e.errors,e);self.assertEqual(e.values[key],expected)
                counters={'soul':((0,165),self.now),'seed':((0,300),self.now)}
                counters[key]=(expected,self.now)
                self.assertIn('GBR incomplete',resource_status(counters,None,self.now))

    def test_missing_counter_parts_never_become_zero_or_a_complete_counter(self):
        from PIL import ImageDraw
        for name,key,box in [('gbr_soul_full_clean_oct24.png','soul',(60,679,97,705)),
                             ('gbr_soul_full_clean_oct24.png','soul',(96,679,134,705)),
                             ('gbr_seed_full_clean_oct24.png','seed',(133,679,174,705)),
                             ('gbr_seed_full_clean_oct24.png','seed',(173,679,215,705))]:
            with self.subTest(name=name,box=box):
                im=Image.open(FIXTURES/name).convert('RGB');ImageDraw.Draw(im).rectangle(box,fill='black')
                self.assertNotIn(key,ScreenReader().read(im,resource_check=True).values)

    def test_oct24_soul_zero_rendering_is_verified_without_guessing_ocr(self):
        reader=ScreenReader()
        e=reader.read(FIXTURES/'gbr_soul_zero_oct24.png',resource_check=True)
        self.assertFalse(e.errors,e);self.assertEqual(e.values['soul'],(0,165))
        self.assertEqual(next_navigation(e,True).name,'Scroll rewards right')
        # Removing the numerator must not turn the visible cap into clearance.
        from PIL import ImageDraw
        im=Image.open(FIXTURES/'gbr_soul_zero_oct24.png').convert('RGB')
        ImageDraw.Draw(im).rectangle((78,680,94,705),fill='black')
        e=reader.read(im,resource_check=True)
        self.assertNotIn('soul',e.values)

    def test_oct24_seed_counter_and_complete_resource_status(self):
        e=ScreenReader().read(FIXTURES/'gbr_seed_zero_oct24.png',resource_check=True)
        self.assertFalse(e.errors,e);self.assertEqual(e.values['seed'],(0,300))
        counters={'soul':((0,165),self.now),'seed':(e.values['seed'],self.now)}
        self.assertTrue(resource_status(counters,(e.values,self.now),self.now).startswith('GBR complete'))

    def test_current_1080_seed_zero_rendering(self):
        evidence=ScreenReader().read(FIXTURES/'gbr_seed_zero_1080_current.png',resource_check=True)
        self.assertFalse(evidence.errors,evidence)
        self.assertEqual(evidence.values['seed'],(0,300))
    def setUp(self):self.now=datetime.now(timezone.utc)

    def test_fresh_both_zero_required(self):
        balances=({"energy":(45838,120),"boost":100},self.now)
        for soul,seed in ((63,121),(0,121),(63,0)):
            counters={"soul":((soul,165),self.now),"seed":((seed,300),self.now)}
            self.assertIn("GBR incomplete",resource_status(counters,balances,self.now))
        counters={"soul":((0,165),self.now),"seed":((0,300),self.now)}
        self.assertIn("boost 100",resource_status(counters,balances,self.now))

    def test_compact_strip_red_zero_and_seed_one(self):
        reader=ScreenReader()
        soul=reader.read(FIXTURES/"gbr_zero_main.png",resource_check=True)
        self.assertFalse(soul.errors,soul)
        self.assertEqual(soul.values["soul"],(0,165))
        seed=reader.read(FIXTURES/"gbr_strip_seed_one.png",resource_check=True)
        self.assertFalse(seed.errors,seed)
        self.assertEqual(seed.values["seed"],(1,300))
        self.assertNotIn("soul",seed.values)
        counters={"soul":((0,165),self.now),"seed":((1,300),self.now)}
        self.assertIn("GBR incomplete",resource_status(counters,({"energy":(100,120),"boost":100},self.now),self.now))

    def test_seed_zero_in_actual_gui_capture_and_strip_endpoint(self):
        reader=ScreenReader()
        for name in ("gbr_seed_zero_qt.png","gbr_seed_zero_stuck.png"):
            result=reader.read(FIXTURES/name,resource_check=True)
            self.assertFalse(result.errors,result)
            self.assertEqual(result.values.get("seed"),(0,300),result)
        # The existing nonzero regression above must still read 1/300;
        # neither an unreadable counter nor a cap alone establishes zero.

    def test_unreadable_boost_does_not_block_verified_raid_rewards(self):
        result=ScreenReader().read(FIXTURES/"gbr_seed_zero_unreadable_boost.png",resource_check=True)
        self.assertFalse(result.errors,result)
        self.assertEqual(result.values.get("seed"),(0,300))
        self.assertNotIn("boost",result.values)
        self.assertIn("balance_error",result.values)
        self.assertIsNotNone(next_navigation(result))

    def test_compact_strip_scans_both_directions_without_details(self):
        evidence=ScreenEvidence("gbr_main",{"reward_strip_verified":True})
        for have_soul,expected in ((False,(80,658,(500,658))),(True,(500,658,(80,658)))):
            action=next_navigation(evidence,have_soul)
            with patch("lib.resource_check.click_game_point") as click:
                perform_navigation(11,action)
                click.assert_called_once_with(11,*expected[:2],drag_to=expected[2])

    def test_resource_readiness_is_separate_from_confirmed_raid_completion(self):
        counters={"soul":((0,165),self.now),"seed":((0,300),self.now)}
        for balances in (None,({"energy":(1,120)},self.now),
                         ({"energy":(100,120),"boost":100},self.now-timedelta(minutes=11))):
            status=resource_status(counters,balances,self.now)
            self.assertTrue(status.startswith("GBR complete"))
            self.assertTrue(any(word in status for word in ("fresh","unreadable","waiting")))
        self.assertIn("boost 100",resource_status(counters,({"energy":(0,120),"boost":100},self.now),self.now))
        counters["soul"]=((0,165),self.now-timedelta(minutes=11))
        self.assertIn("missing fresh",resource_status(counters,None,self.now))

    def test_navigation_has_no_battle_routes(self):
        route=[next_navigation(ScreenEvidence(name,{"menu_available":True})) for name in
               ("timeline","navigation_menu","select_mission","select_mission_coop","gbr_selection","gbr_main")]
        self.assertEqual([item.name for item in route],
            ["Open Menu","Select Mission","Co-op tab","Giant Boss Raid","Select Onslaught","Rewards Available"])
        self.assertIsNone(next_navigation(ScreenEvidence("unknown")))
        self.assertIsNone(next_navigation(ScreenEvidence("gbr_rewards",{"seed":(0,300)}),True))
        with self.assertRaises(ValueError):perform_navigation(0,Navigation("Start Battle",1100,670,()))

    def test_current_bluestacks_render_surface(self):
        import win32gui,autoit
        route=next_navigation(ScreenEvidence("select_mission_coop",{"navigation_only":True}))
        with patch.object(win32gui,"EnumChildWindows",side_effect=lambda parent,callback,unused:callback(22,None)), \
             patch.object(win32gui,"GetWindowText",return_value="HD renderer"), \
             patch.object(win32gui,"GetClassName",return_value="BlueStacksApp"), \
             patch.object(win32gui,"GetClientRect",return_value=(0,0,1278,719)), \
             patch.object(win32gui,"GetForegroundWindow",return_value=11), \
             patch.object(autoit,"win_activate_by_handle",return_value=1), \
             patch.object(autoit,"win_wait_active_by_handle",return_value=1), \
             patch.object(win32gui,"ClientToScreen",side_effect=lambda handle,point:point), \
             patch.object(win32gui,"WindowFromPoint",return_value=22), \
             patch.object(win32gui,"GetAncestor",return_value=11), \
             patch.object(win32gui,"IsWindow",return_value=False), \
             patch.object(autoit,"mouse_click",return_value=1) as click:
            perform_navigation(11,route)
            click.assert_called_once_with("left",x=174,y=375,clicks=1,speed=0)

    def test_real_energy_boost_and_gbr(self):
        result=ScreenReader().read(FIXTURES/"gbr_main.png",resource_check=True)
        self.assertFalse(result.errors,result)
        self.assertNotIn("energy",result.values)
        self.assertEqual(result.values["boost"],100)
        self.assertEqual(result.values["soul"],(63,165))

    def test_menu_and_selector_anchors(self):
        reader=ScreenReader()
        for name in ("navigation_menu","select_mission","select_mission_coop"):
            self.assertEqual(reader.read(FIXTURES/(name+".png"),resource_check=True).screen,name)

    def test_timeline_currency_is_not_boost(self):
        result=ScreenReader().read(FIXTURES/"timeline.png",resource_check=True)
        self.assertTrue(result.values.get("menu_available"),result)
        self.assertNotIn("boost",result.values)

    def test_dimmed_popup_cannot_verify_onslaught(self):
        image=Image.open(FIXTURES/"gbr_main.png").convert("RGB")
        image=ImageEnhance.Brightness(image).enhance(.35)
        result=ScreenReader().read(image,resource_check=True)
        self.assertNotIn("soul",result.values)
        self.assertIsNone(next_navigation(result))
