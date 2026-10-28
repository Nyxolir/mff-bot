import unittest
from pathlib import Path
from PIL import Image,ImageDraw
from lib.session_recovery import session_notice

class NetworkRetryTests(unittest.TestCase):
    def test_live_notice_allows_variable_error_codes_but_requires_message_and_controls(self):
        original=Image.open(Path(__file__).parent/'fixtures/network_retry_notice_oct27.png').convert('RGB')
        for code in ('NET_00000003','NET_00000007','NET_10000012',''):
            image=original.copy();draw=ImageDraw.Draw(image)
            draw.rectangle((500,378,785,410),fill=(8,23,43));draw.text((510,385),code,fill='white')
            e=session_notice(image)
            self.assertEqual(e.screen,'network_retry_notice');self.assertEqual(e.values['ok_point'],(741,538))
        for box in ((581,146,700,185),(433,313,857,346),(576,345,706,375),(486,518,592,554),(710,518,774,554)):
            image=original.copy();ImageDraw.Draw(image).rectangle(box,fill='black')
            e=session_notice(image)
            self.assertTrue(e is None or e.screen!='network_retry_notice')

