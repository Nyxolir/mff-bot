from pathlib import Path
import unittest
from lib.mission_reader import BoardReader

class ScrolledBoardTests(unittest.TestCase):
    def test_all_four_ultimate_story_themes_and_current_gold_checks(self):
        e=BoardReader().read(Path(__file__).parent/'fixtures/board_story_completed_current.png')
        themes=e.values['story_themes'];self.assertEqual(len(themes),4)
        self.assertTrue(all(t['completed'] for t in themes.values()))
        for name in ('MADNESS ENSUES','SINISTER SCHEMES','WORLD EVENT','STORY ULTIMATE'):
            tile=next(t for t in e.values['tiles'] if t['mode']==name)
            self.assertTrue(tile['completed'],name);self.assertEqual(tile['remaining'],0)

    def test_one_unconfirmed_story_theme_cannot_mark_entire_story_done(self):
        from PIL import Image
        im=Image.open(Path(__file__).parent/'fixtures/board_story_completed_current.png').convert('RGB')
        im.paste((10,20,40),(1173,345,1207,375))
        e=BoardReader().read(im);tile=next(t for t in e.values['tiles'] if t['mode']=='STORY ULTIMATE')
        self.assertFalse(tile['completed']);self.assertEqual(tile['remaining'],1)

    def test_scrolled_live_rows_and_completed_tile(self):
        fixtures=Path(__file__).parent/'fixtures';reader=BoardReader()
        partial=reader.read(fixtures/'board_scrolled_offset.png')
        tiles={tile['mode']:tile for tile in partial.values['tiles']}
        self.assertEqual(tiles['ENDING THE STRYFE']['remaining'],3)
        self.assertEqual(tiles['MADNESS ENSUES']['remaining'],4)
        self.assertTrue(tiles['OTHERWORLD BATTLE']['completed'])
        bottom=reader.read(fixtures/'board_completed_chaos_offset.png')
        tile=next(t for t in bottom.values['tiles'] if t['mode']=='BEGINNING OF THE CHAOS')
        self.assertTrue(tile['completed']);self.assertEqual(tile['remaining'],0)
