"""Real screenshot OCR regressions plus conservative failure cases."""
from pathlib import Path
import unittest
from PIL import Image, ImageDraw
from lib.screen_reader import ScreenReader, number

FIXTURES = Path(__file__).parent / "fixtures"


class ReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader = ScreenReader()

    def read(self, name):
        result = self.reader.read(FIXTURES / (name + ".png"))
        self.assertFalse(result.errors, result)
        return result

    def test_world_event_existing_score(self):
        result = self.read("world_event")
        self.assertEqual(result.values["best_score"], 3862486)
        self.assertEqual(result.values["entries"], (1, 2))
        self.assertTrue(result.values["already_done"])

    def test_gbr_exact_nonzero_counters(self):
        self.assertEqual(self.read("gbr_main").values["soul"], (63, 165))
        self.assertEqual(self.read("gbr_rewards").values["seed"], (121, 300))

    def test_otherworld_done_and_ticket(self):
        result = self.read("otherworld")
        self.assertEqual(result.values["entries"], (0, 5))
        self.assertTrue(result.values["ticket_icon_verified"])

    def test_timeline_exhausted(self):
        self.assertEqual(self.read("timeline").values["entries"], (0, 5))

    def test_team_one_and_refill_block(self):
        result = self.read("timeline_refill")
        self.assertTrue(result.values["team_1_verified"])
        self.assertTrue(result.values["refill_prompt"])

    def test_arena_board_completed(self):
        result = self.read("arena_board")
        self.assertEqual(set(result.values["completed"]),
            {"OTHERWORLD BATTLE", "TIMELINE BATTLE", "TEAM BATTLE ARENA"})

    def test_missing_score_stays_unknown(self):
        im = Image.open(FIXTURES / "world_event.png").convert("RGB")
        ImageDraw.Draw(im).rectangle((1144,300,1238,327), fill="black")
        result = self.reader.read(im)
        self.assertTrue(result.errors)
        self.assertFalse(result.values)

    def test_team_two_does_not_match_team_one(self):
        im = Image.open(FIXTURES / "timeline_refill.png").convert("RGB")
        # Replace selected Team 1 with the visible unselected Team 2 button.
        im.paste(im.crop((15,186,70,241)), (15,122))
        result = self.reader.read(im)
        self.assertFalse(result.values["team_1_verified"])

    def test_unknown_layout(self):
        self.assertEqual(self.reader.read(Image.new("RGB", (640,360))).screen, "unknown")

    def test_missing_ticket_is_not_verified(self):
        im = Image.open(FIXTURES / "otherworld.png").convert("RGB")
        ImageDraw.Draw(im).rectangle((727,686,771,736), fill="black")
        self.assertFalse(self.reader.read(im).values["ticket_icon_verified"])

    def test_missing_completion_marks_are_not_done(self):
        im = Image.open(FIXTURES / "arena_board.png").convert("RGB")
        draw = ImageDraw.Draw(im)
        for x,y in ((454,171),(837,171),(72,276)):
            draw.rectangle((x+336,y+31,x+370,y+61),fill="black")
        self.assertEqual(self.reader.read(im).values["completed"], [])

    def test_number_rejects_guesses(self):
        for text in ("O", "", "1,23", "1 000", "3,862,48G"):
            with self.assertRaises(ValueError): number(text)


    def test_current_gbr_boss_list_and_selected_outline(self):
        selection=self.reader.read(FIXTURES/'gbr_master_current.png',resource_check=True)
        self.assertFalse(selection.errors,selection);self.assertEqual(selection.screen,'gbr_selection')
        selected=self.reader.read(FIXTURES/'gbr_onslaught_current.png',resource_check=True)
        self.assertFalse(selected.errors,selected);self.assertEqual(selected.screen,'gbr_main')
        self.assertEqual(selected.values['soul'],(0,165))

if __name__ == "__main__": unittest.main()

