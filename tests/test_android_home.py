from pathlib import Path
import unittest
from PIL import Image,ImageDraw
from lib.android_home import android_home,ANCHORS

FIXTURES=Path(__file__).parent/'fixtures'
class AndroidHomeTests(unittest.TestCase):
    def test_current_launcher_supplies_verified_game_icon(self):
        e=android_home(FIXTURES/'android_home_current.png')
        self.assertEqual(e.screen,'android_home');self.assertEqual(e.values['launch_point'],(539,204))
        from lib.android_home import CURRENT_ANCHORS
        for _,box in CURRENT_ANCHORS:
            im=Image.open(FIXTURES/'android_home_current.png').convert('RGB');ImageDraw.Draw(im).rectangle(box,fill='black')
            self.assertIsNone(android_home(im))
    def test_recorded_launcher_is_recognized_without_ocr(self):
        self.assertEqual(android_home(FIXTURES/'android_home_20261021.png').screen,'android_home')
    def test_each_launcher_anchor_is_required(self):
        for name,box in ANCHORS:
            with self.subTest(name=name):
                image=Image.open(FIXTURES/'android_home_20261021.png').convert('RGB')
                ImageDraw.Draw(image).rectangle(box,fill='black')
                self.assertIsNone(android_home(image))
    def test_game_screen_is_not_launcher(self):
        self.assertIsNone(android_home(FIXTURES/'story_ultimate_lobby.png'))
