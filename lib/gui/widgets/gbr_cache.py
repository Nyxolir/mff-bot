"""Persist only verified daily raid clearance, never resource balances."""
import json
from datetime import datetime,timezone
from pathlib import Path
from lib.daily_queue import DailyRaidGate

CACHE=Path(__file__).resolve().parents[3]/'settings/gui/gbr-clearance.json'

class GbrCache:
    def load_gbr_clearance(self):
        try:
            data=json.loads(CACHE.read_text(encoding='utf-8'))
            if data.get('version')!=1:return
            now=datetime.now(timezone.utc)
            gate=DailyRaidGate.from_cache(data.get('clearance'),now)
            if gate.cleared(now):
                self.raid_gate=gate;self.queue_engine.gate=gate
                self.latest_counters=dict(gate.counters)
                self.log('Restored GBR clearance until reset '+gate.expires_at.strftime('%H:%M UTC'))
        except FileNotFoundError:pass
        except (OSError,ValueError,TypeError,AttributeError) as error:
            self.log('GBR cache ignored; fresh check required: '+str(error),True)

    def persist_gbr_clearance(self):
        try:
            CACHE.parent.mkdir(parents=True,exist_ok=True)
            data={'version':1,'clearance':self.raid_gate.cache_record(datetime.now(timezone.utc))}
            temporary=CACHE.with_suffix('.tmp')
            temporary.write_text(json.dumps(data,indent=2),encoding='utf-8');temporary.replace(CACHE)
        except OSError as error:self.log('Could not save GBR clearance: '+str(error),True)
