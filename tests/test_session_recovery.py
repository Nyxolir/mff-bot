import unittest
from pathlib import Path
from PIL import Image
from lib.session_recovery import session_notice

class SessionRecoveryTests(unittest.TestCase):
    def test_external_link_notice_exposes_cancel_only(self):
        e=session_notice(Path(__file__).parent/'fixtures/external_link_notice_current.png')
        self.assertEqual(e.screen,'external_link_notice');self.assertEqual(e.values,{'cancel_point':(539,538)})
    def test_settings_info_popup_closes_only_with_validated_controls(self):
        root=Path(__file__).parent/'fixtures'
        e=session_notice(root/'settings_info_current.png')
        self.assertEqual(e.screen,'game_settings');self.assertEqual(e.values['close_point'],(640,645))
        im=Image.open(root/'settings_info_current.png').convert('RGB')
        im.paste((0,0,0),(606,628,674,660));self.assertIsNone(session_notice(im))
    def test_exact_notice_and_other_screens(self):
        root=Path(__file__).parent/"fixtures"
        self.assertEqual(session_notice(root/"session_replaced.png").screen,"session_replaced")
        self.assertIsNone(session_notice(root/"status_board.png"))
        self.assertIsNone(session_notice(Image.new("RGB",(1280,720))))
        image=Image.open(root/"session_replaced.png").convert("RGB")
        image.paste((0,0,0),(348,374,932,408))
        self.assertIsNone(session_notice(image))
