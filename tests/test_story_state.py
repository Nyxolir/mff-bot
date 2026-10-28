from datetime import datetime,timedelta,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch,Mock
import unittest,json
from lib.daily_queue import ContinuousQueue,reset_period
from lib.gui.widgets import story_controls as story

class Harness(story.StoryControls):
 def __init__(self):
  self.init_story();self.queue_engine=ContinuousQueue();self.queue_held=set();self.log=Mock()

class StoryStateTests(unittest.TestCase):
 def test_pending_launch_survives_app_restart_without_resubmission(self):
  root=Path(__file__).resolve().parents[3]/'work/story-state-tests';root.mkdir(parents=True,exist_ok=True)
  with TemporaryDirectory(dir=root) as directory,patch.object(story,'STORY_STATE',Path(directory)/'run.json'):
   first=Harness();first.story_started=datetime.now(timezone.utc)-timedelta(minutes=5);first.persist_story_run(True)
   restored=Harness();restored.load_story_run()
   self.assertEqual(restored.queue_engine.pending,(reset_period(first.story_started),'STORY ULTIMATE',1))
   self.assertEqual(restored.story_started,first.story_started)
   first.persist_story_run(False);finished=Harness();finished.load_story_run();self.assertIsNone(finished.queue_engine.pending)
 def test_malformed_existing_state_holds_story_instead_of_relaunching(self):
  with patch.object(Path,'read_text',return_value='{broken'):
   h=Harness();h.load_story_run();self.assertIn('STORY ULTIMATE',h.queue_held)
 def test_missing_state_allows_first_launch(self):
  with patch.object(Path,'read_text',side_effect=FileNotFoundError):
   h=Harness();h.load_story_run();self.assertFalse(h.queue_held);self.assertIsNone(h.queue_engine.pending)
