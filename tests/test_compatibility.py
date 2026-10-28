import unittest
from unittest.mock import patch
import numpy as np

from lib.ocr import TesseractPool
from lib.structural_similarity.ssim import compare_ssim


class CompatibilityTests(unittest.TestCase):
    def test_similarity_preserves_upstream_return_contract(self):
        image=np.zeros((16,16),dtype=np.uint8)
        score,difference=compare_ssim(image,image,full=True)
        self.assertAlmostEqual(score,1.0)
        self.assertEqual(difference.shape,image.shape)
        self.assertLess(compare_ssim(image,np.full_like(image,255)),0.01)

    def test_multichannel_uses_current_public_api(self):
        image=np.zeros((16,16,3),dtype=np.uint8)
        self.assertAlmostEqual(compare_ssim(image,image,multichannel=True),1.0)

    def test_ocr_falls_back_without_legacy_dll_or_legacy_data(self):
        pool=TesseractPool(language="mff+eng")
        with patch("lib.ocr.native_executable",return_value=None), \
             patch("lib.ocr.recognize_with_js",return_value="0/165") as backend:
            self.assertEqual(pool.image_to_string(np.zeros((10,20),dtype=np.uint8),
                             whitelist="0123456789/",page_segmentation=7),"0/165")
            self.assertEqual(backend.call_args.args[1:],("0123456789/",7))

    def test_ocr_rejects_unsafe_whitelist_and_invalid_mode(self):
        pool=TesseractPool()
        for whitelist,psm in (("123 --x",7),("123\"",7),("123",99)):
            with self.assertRaises(ValueError):
                pool.image_to_string(np.zeros((10,20),dtype=np.uint8),
                                     whitelist=whitelist,page_segmentation=psm)

    def test_old_ui_modules_import_without_native_tesseract(self):
        from lib import functions
        import lib.game.ui
        self.assertTrue(hasattr(lib.game.ui,"DM_LABEL"))
        self.assertTrue(hasattr(functions,"get_text_from_image"))

    def test_local_gui_startup_never_checks_archived_upstream(self):
        import app_gui
        with patch("urllib.request.urlopen",side_effect=AssertionError("Network not allowed")):
            self.assertFalse(app_gui.check_updates()[1])


if __name__=="__main__": unittest.main()
