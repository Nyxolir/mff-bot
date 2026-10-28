from datetime import datetime,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import json
import unittest
from lib.daily_queue import DailyRaidGate
from lib.gui.widgets import gbr_cache

TEMP_ROOT=Path(__file__).resolve().parents[3]/'work/cache-tests'
TEMP_ROOT.mkdir(parents=True,exist_ok=True)

class CacheHarness(gbr_cache.GbrCache):
    def __init__(self):
        self.raid_gate=DailyRaidGate();self.queue_engine=SimpleNamespace(gate=self.raid_gate)
        self.latest_counters={};self.log=lambda *args:None

class CacheTests(unittest.TestCase):
    def test_actual_file_roundtrip_and_revocation(self):
        with TemporaryDirectory(dir=TEMP_ROOT) as folder,patch.object(gbr_cache,'CACHE',Path(folder)/'gbr.json'):
            now=datetime.now(timezone.utc);first=CacheHarness()
            for key,counter in [('soul',(0,165)),('seed',(0,300))]:first.raid_gate.observe(key,counter,now,now)
            first.persist_gbr_clearance()
            second=CacheHarness();second.load_gbr_clearance()
            self.assertTrue(second.raid_gate.cleared(datetime.now(timezone.utc)))
            self.assertIs(second.queue_engine.gate,second.raid_gate)
            self.assertEqual(second.latest_counters,first.raid_gate.counters)
            second.raid_gate.observe('seed',(1,300),now,now);second.persist_gbr_clearance()
            third=CacheHarness();third.load_gbr_clearance()
            self.assertFalse(third.raid_gate.cleared(now))
            self.assertIsNone(json.loads(gbr_cache.CACHE.read_text())['clearance'])

    def test_malformed_file_does_not_load_clearance(self):
        with TemporaryDirectory(dir=TEMP_ROOT) as folder,patch.object(gbr_cache,'CACHE',Path(folder)/'gbr.json'):
            gbr_cache.CACHE.write_text('{broken')
            app=CacheHarness();app.load_gbr_clearance()
            self.assertFalse(app.raid_gate.cleared(datetime.now(timezone.utc)))
