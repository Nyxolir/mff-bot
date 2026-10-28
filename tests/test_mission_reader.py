from pathlib import Path
import unittest
from PIL import Image,ImageDraw
from lib.mission_reader import BoardReader
from lib.farming import ENERGY_FARMS

FIXTURES=Path(__file__).parent/"fixtures"


class BoardTests(unittest.TestCase):
    def test_completed_tail_includes_unautomated_tiles_but_not_synthetic_alliance_done(self):
        result=BoardReader().read(FIXTURES/'board_after_normal_alliance.png')
        self.assertTrue(result.values['completed_tail_verified'])
        from lib.mission_reader import viewport
        import numpy as np
        im=viewport(FIXTURES/'board_after_normal_alliance.png')
        pixels=np.asarray(im).copy().astype('int16')
        gold=(pixels[:,:,0]>120)&(pixels[:,:,1]>110)&(pixels[:,:,0]-pixels[:,:,2]>45)&(pixels[:,:,1]-pixels[:,:,2]>35)
        pixels[gold]=0
        result=BoardReader().read(Image.fromarray(pixels.astype('uint8')))
        self.assertFalse(result.values['completed_tail_verified'])

    def test_available_epic_missions_have_full_counts(self):
        result=BoardReader().read(FIXTURES/"status_board.png")
        self.assertFalse(result.errors,result)
        counts={tile["mode"]:tile["remaining"] for tile in result.values["tiles"]}
        expected={"MAGNETO'S MIGHT":2,"RISE OF THE PHOENIX":2,"MUTUAL ENEMY":2,
            "CUTTING CABLE":3,"ENDING THE STRYFE":3,"BEGINNING OF THE CHAOS":2,
            "MADNESS ENSUES":4,"SHOCK AND AWE":4,"READY FOR BATTLE":3,
            "QUEEN OF LIMBO":3,"SINISTER SCHEMES":2}
        for name,count in expected.items():self.assertEqual(counts[name],count,name)
        self.assertTrue(result.values["accelerated_clear"])

    def test_completed_arena_tiles_are_zero(self):
        result=BoardReader().read(FIXTURES/"arena_board.png")
        counts={tile["mode"]:tile["remaining"] for tile in result.values["tiles"]}
        for name in ("OTHERWORLD BATTLE","TIMELINE BATTLE","TEAM BATTLE ARENA"):
            self.assertEqual(counts[name],0)

    def test_blank_count_stays_unknown(self):
        image=Image.open(FIXTURES/"status_board.png").convert("RGB")
        ImageDraw.Draw(image).rectangle((1132,225,1178,280),fill="black")
        result=BoardReader().read(image)
        tile=next(tile for tile in result.values["tiles"] if tile["mode"]=="MAGNETO'S MIGHT")
        self.assertIsNone(tile["remaining"])
