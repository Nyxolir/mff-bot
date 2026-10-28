import unittest
from pathlib import Path
from PIL import Image,ImageDraw
from lib.notification_panel import notification_panel

class NotificationPanelTests(unittest.TestCase):
    def test_observed_panel_requires_heading_objective_footer_and_arrow(self):
        original=Image.open(Path(__file__).parent/'fixtures/trivia_notification_panel_oct27.png').convert('RGB')
        e=notification_panel(original)
        self.assertEqual(e.screen,'quest_notification_panel');self.assertEqual(e.values['close_point'],(1066,36))
        for box in ((920,77,1168,105),(920,109,1218,139),(837,380,1279,417),(1053,394,1060,405)):
            with self.subTest(box=box):
                image=original.copy();ImageDraw.Draw(image).rectangle(box,fill='white')
                self.assertIsNone(notification_panel(image))

    def test_open_quiz_and_daily_pages_do_not_authorize_notification_click(self):
        for name in ('trivia_moon_knight_oct27.png','trivia_start_oct24.png','trivia_navigation_event_quest_oct27.png'):
            with self.subTest(name=name):self.assertIsNone(notification_panel(Path(__file__).parent/'fixtures'/name))

    def test_actual_daily_challenges_page_has_same_drawer(self):
        e=notification_panel(Path(__file__).parent/'fixtures/trivia_navigation_daily_oct27.png')
        self.assertEqual(e.screen,'quest_notification_panel')

    def test_observed_single_row_has_different_footer_height_and_quest_name(self):
        e=notification_panel(Path(__file__).parent/'fixtures/notification_single_row_oct27.png')
        self.assertEqual(e.screen,'quest_notification_panel');self.assertEqual(e.values['footer_y'],156)
