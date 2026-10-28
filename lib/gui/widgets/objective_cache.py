"""Daily Dimension/Dispatch requirements, persisted until the same reset boundary."""
from dataclasses import asdict,replace
from datetime import datetime,timezone
import json
from pathlib import Path
from lib.daily_queue import next_reset,reset_period
from lib.objectives import MissionPlan

CACHE=Path(__file__).resolve().parents[3]/'settings/gui/objective-checks.json'

def restore_plan(data,now):
    try:
        stamp=datetime.fromisoformat(data['checked_at']);expires=datetime.fromisoformat(data['expires_at'])
        if data['version']!=2 or stamp.tzinfo is None or expires.tzinfo is None:return None
        if not stamp<=now<expires or expires!=next_reset(stamp) or data['period']!=reset_period(now):return None
        p=data['plan']
        if type(p['dimension_clears']) is not int or not 0<=p['dimension_clears']<=100:return None
        if type(p['dispatch_clears']) is not int or p['dispatch_clears'] not in (0,1):return None
        if type(p['claim_contribution']) is not bool or (p['claim_contribution'] and p['dimension_clears']<5):return None
        if type(p['dispatch_sector']) is not int or p['dispatch_sector']!=7 or type(p['dispatch_mission']) is not int or p['dispatch_mission']!=1:return None
        return MissionPlan(**p),stamp
    except (ValueError,KeyError,TypeError,AttributeError):return None

class ObjectiveCache:
    def load_objective_cache(self):
        try:
            now=datetime.now(timezone.utc);restored=restore_plan(json.loads(CACHE.read_text(encoding='utf-8')),now)
            if restored:
                self.objective_plan,self.objective_checked_at=restored;self.objective_period=reset_period(now)
                self.log('Restored Dimension/Dispatch requirement checks until reset')
        except FileNotFoundError:pass
        except (OSError,ValueError) as error:self.log('Objective cache ignored: '+str(error),True)

    def persist_objective_cache(self,inflight=False):
        now=datetime.now(timezone.utc)
        data={'version':2,'plan':None}
        if not inflight and self.objective_plan is not None and self.objective_period==reset_period(now):
            stamp=self.objective_checked_at or now
            data.update(plan=asdict(self.objective_plan),checked_at=stamp.isoformat(),period=self.objective_period,
                expires_at=next_reset(stamp).isoformat())
        try:
            CACHE.parent.mkdir(parents=True,exist_ok=True);temporary=CACHE.with_suffix('.tmp')
            temporary.write_text(json.dumps(data,indent=2),encoding='utf-8');temporary.replace(CACHE)
            return True
        except OSError as error:
            self.log('Could not save objective state: '+str(error),True);return False

    def objective_completed(self,mode):
        if self.objective_plan is None:return
        if mode=='DIMENSION MISSION':self.objective_plan=replace(self.objective_plan,dimension_clears=0,claim_contribution=False)
        elif mode=='DISPATCH 7-1':self.objective_plan=replace(self.objective_plan,dispatch_clears=0)
        else:return
        self.persist_objective_cache()
