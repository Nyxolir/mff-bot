from pathlib import Path
import unittest
import numpy as np
from PIL import Image
from lib.anchor_match import anchor_scores
from lib.screen_reader import ScreenReader

class AnchorTests(unittest.TestCase):
    def test_actual_adb_render_retains_strict_menu_match(self):
        root=Path(__file__).resolve().parents[1]
        image=Image.open(root/'tests/fixtures/adb_home_4k_normalized.png').convert('RGB')
        ref=Image.open(root/'images/current/menu_icon.png').convert('RGB')
        score,error=anchor_scores(image,ref,(1234,24,1265,50))
        self.assertGreaterEqual(score,.97);self.assertLessEqual(error,12)
        self.assertTrue(ScreenReader().read(image,resource_check=True).values.get('menu_available'))

    def test_search_cannot_follow_an_anchor_outside_two_pixels(self):
        ref=Image.fromarray(np.random.default_rng(2).integers(0,256,(15,20,3),dtype=np.uint8))
        image=Image.new('RGB',(100,100));image.paste(ref,(42,39))
        self.assertGreater(anchor_scores(image,ref,(40,40,60,55))[0],.99)
        image=Image.new('RGB',(100,100));image.paste(ref,(50,40))
        self.assertLess(anchor_scores(image,ref,(40,40,60,55))[0],.97)
