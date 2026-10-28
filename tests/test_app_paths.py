import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from lib import app_paths,trivia


class AppPathTests(unittest.TestCase):
    def test_source_state_stays_with_existing_checkout(self):
        with patch.dict(os.environ,{},clear=True),patch.object(sys,'frozen',False,create=True):
            self.assertEqual(app_paths.data_root(),Path(app_paths.__file__).resolve().parents[1])

    def test_installed_state_is_separate_and_preparation_preserves_pending_files(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);bundle=base/'bundle';local=base/'user'
            with patch.dict(os.environ,{'LOCALAPPDATA':str(local)},clear=True),patch.object(sys,'frozen',True,create=True),patch.object(sys,'_MEIPASS',str(bundle),create=True):
                self.assertEqual(app_paths.resource_root(),bundle)
                self.assertEqual(app_paths.data_root(),local/'Nyxolir/MFFBot')
                app_paths.prepare_runtime();pending=app_paths.data_path('settings/gui/pending-clear.json')
                pending.write_text('{"pending":["saved submission"]}',encoding='utf-8')
                app_paths.prepare_runtime()
                self.assertEqual(json.loads(pending.read_text())['pending'],['saved submission'])
                self.assertFalse(bundle.exists())

    def test_override_supports_isolated_smoke_testing_and_paths_cannot_escape(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'MFF_DATA_DIR':folder}):
            self.assertEqual(app_paths.data_root(),Path(folder).resolve())
            for value in ('../account.json',str(Path(folder)/'absolute.json')):
                with self.assertRaises(ValueError):app_paths.data_path(value)

    def test_release_answers_and_user_additions_merge_without_overwriting_known_answers(self):
        with tempfile.TemporaryDirectory() as folder:
            default=Path(folder)/'default.json';user=Path(folder)/'user.json'
            default.write_text(json.dumps({'version':1,'answers':{'A sufficiently long bundled quiz question?':'Bundled'}}))
            user.write_text(json.dumps({'version':1,'answers':{'A sufficiently long personal quiz addition?':'Custom','A sufficiently long bundled quiz question?':'Wrong'}}))
            with patch.object(trivia,'DEFAULT_ANSWERS',default),patch.object(trivia,'EXTRA_ANSWERS',user):
                self.assertEqual(trivia.lookup_answer('A sufficiently long bundled quiz question?'),'Bundled')
                self.assertEqual(trivia.lookup_answer('A sufficiently long personal quiz addition?'),'Custom')
                default.write_text(json.dumps({'version':1,'answers':{'A sufficiently long new release quiz question?':'New'}}))
                self.assertEqual(trivia.lookup_answer('A sufficiently long new release quiz question?'),'New')
                self.assertEqual(trivia.lookup_answer('A sufficiently long personal quiz addition?'),'Custom')


if __name__=='__main__':unittest.main()
