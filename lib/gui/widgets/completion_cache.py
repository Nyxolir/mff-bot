"""Remember verified daily completions across queue and application restarts."""
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
from lib.app_paths import data_path
from lib.daily_queue import reset_period,next_reset
from lib.farming import ENERGY_FARMS,UNBOOSTED_SWEEPS
from dataclasses import asdict

CACHE=data_path('settings/gui/completed-missions.json')
ALLOWED=ENERGY_FARMS|UNBOOSTED_SWEEPS|{'ALLIANCE BATTLE','DISPATCH 7-1','TIMELINE BATTLE','OTHERWORLD BATTLE','TEAM BATTLE ARENA','STORY ULTIMATE','ZOMBIE SURVIVAL'}

def restore_completed(data,now):
    try:
        stamp=datetime.fromisoformat(data['recorded_at']);expires=datetime.fromisoformat(data['expires_at'])
        modes=data['completed']
        if data['version']!=1 or stamp.tzinfo is None or expires.tzinfo is None:return set()
        if not stamp<=now<expires or expires!=next_reset(stamp) or data['period']!=reset_period(now):return set()
        if not isinstance(modes,list) or any(not isinstance(mode,str) or mode not in ALLOWED for mode in modes):return set()
        return set(modes)
    except (KeyError,ValueError,TypeError,AttributeError):return set()

class CompletionCache:
    def fresh_queue_home_check(self,evidence,observed):
        pending=self.queue_engine.pending;now=datetime.now(timezone.utc)
        if not (self.queue_engine.running and pending and getattr(self,'queue_fresh_pass',False)):return False
        if pending[1]=='ZOMBIE SURVIVAL':return False
        if evidence.errors or not timedelta(0)<=now-observed<=timedelta(seconds=30):return False
        if evidence.screen!='game_home' or evidence.values.get('home_controls_verified') is not True:
            self.queue_fresh_home_seen=None;return False
        seen=getattr(self,'queue_fresh_home_seen',None)
        if seen is None:
            self.queue_fresh_home_seen=observed;self.queue_wake=now+timedelta(seconds=3);return True
        if observed-seen<timedelta(seconds=3):return True
        mode=pending[1];self.queue_held.add(mode);self.queue_held_period=reset_period(now)
        if not self.persist_completed_missions():self.stop_queue();return True
        self.queue_engine.pending=None
        if not self.persist_pending_clear():
            self.queue_engine.pending=pending;self.stop_queue();return True
        self.queue_fresh_pass=False;self.queue_target=None;self.queue_phase='navigate_board'
        self.queue_waiting=None;self.queue_observation=None;self.queue_wake=now+timedelta(seconds=1)
        self.queue_deferred.clear();self.review_mode=None;self.review_due={}
        self.epic_preparation=None;self.contribution_followup=False;self.contribution_submitted=False
        self.init_arenas()
        if mode=='STORY ULTIMATE':self.story_started=None
        self.log('Fresh queue pass: '+mode+' held for end-of-day review; selecting the next unfinished task')
        return True

    def persist_pending_clear(self):
        pending_path=CACHE.with_name('pending-clear.json')
        data={'pending':list(self.queue_engine.pending) if self.queue_engine.pending else None}
        if self.queue_engine.pending and self.queue_engine.pending[1]=='DIMENSION MISSION':
            now=datetime.now(timezone.utc);stamp=self.objective_checked_at or now
            if self.objective_plan is not None:
                data['dimension_objective']=dict(version=2,plan=asdict(self.objective_plan),
                    checked_at=stamp.isoformat(),period=self.objective_period,expires_at=next_reset(stamp).isoformat())
            data['contribution_followup']=self.contribution_followup
            data['contribution_submitted']=self.contribution_submitted
            data['contribution_before']=getattr(self,'contribution_before',None)
            data['contribution_acquire_submitted']=getattr(self,'contribution_acquire_submitted',False)
        started=getattr(self,'arena_started',None)
        if started is not None and self.queue_engine.pending:data['submitted_at']=started.isoformat()
        if self.queue_engine.pending and self.queue_engine.pending[1] in ('TIMELINE BATTLE','OTHERWORLD BATTLE','TEAM BATTLE ARENA'):
            data['repeat_ended']=getattr(self,'arena_repeat_finished',False) is True
        if self.queue_engine.pending and self.queue_engine.pending[1]=='ZOMBIE SURVIVAL':
            data['submitted_at']=self.zombie_started.isoformat() if self.zombie_started else None
            data['repeat_ended']=self.zombie_repeat_finished
        try:
            temporary=pending_path.with_suffix('.tmp');temporary.write_text(json.dumps(data),encoding='utf-8');temporary.replace(pending_path);return True
        except OSError as error:self.log('Could not save pending clear: '+str(error),True);return False

    def load_pending_clear(self):
        try:
            data=json.loads(CACHE.with_name('pending-clear.json').read_text(encoding='utf-8'));pending=data['pending']
            if not pending:return
            period,mode,count=pending
            arenas={'TIMELINE BATTLE','OTHERWORLD BATTLE','TEAM BATTLE ARENA'}
            if mode not in ENERGY_FARMS|UNBOOSTED_SWEEPS|arenas|{'STORY ULTIMATE','ZOMBIE SURVIVAL'} or type(count) is not int or not 1<=count<=10:raise ValueError('Invalid pending clear')
            if mode in UNBOOSTED_SWEEPS and count>5:raise ValueError('Invalid Converging batch')
            if mode=='ZOMBIE SURVIVAL' and count>5:raise ValueError('Invalid Zombie batch')
            if (period==reset_period(datetime.now(timezone.utc)) or mode=='ZOMBIE SURVIVAL') and mode not in self.queue_engine.completed and mode not in getattr(self,'queue_held',set()):
                self.queue_engine.pending=(period,mode,count)
                if mode=='DIMENSION MISSION':
                    from lib.gui.widgets.objective_cache import restore_plan
                    restored=restore_plan(data.get('dimension_objective',{}),datetime.now(timezone.utc))
                    if restored and restored[0].dimension_clears==count:
                        self.objective_plan,self.objective_checked_at=restored;self.objective_period=period
                    self.contribution_followup=data.get('contribution_followup') is True
                    self.contribution_submitted=data.get('contribution_submitted') is True
                    self.contribution_acquire_submitted=data.get('contribution_acquire_submitted') is True
                    before=data.get('contribution_before')
                    self.contribution_before=(tuple(before) if isinstance(before,list) and len(before)==2
                        and all(type(n) is int and n>=0 for n in before) and before[1]>0 else None)
                if mode=='ZOMBIE SURVIVAL':
                    self.zombie_repeat_finished=data.get('repeat_ended') is True
                    try:
                        stamp=datetime.fromisoformat(data['submitted_at'])
                        if stamp.tzinfo is None or stamp>datetime.now(timezone.utc):raise ValueError('Invalid Zombie timestamp')
                        self.zombie_started=stamp
                    except (ValueError,KeyError,TypeError):self.zombie_started=datetime.now(timezone.utc)
                if mode in arenas:
                    self.arena_resumed=True
                    self.arena_repeat_finished=data.get('repeat_ended') is True
                    try:
                        started=datetime.fromisoformat(data['submitted_at'])
                        now=datetime.now(timezone.utc)
                        if started.tzinfo is None or started>now or reset_period(started)!=period:raise ValueError('Invalid arena timestamp')
                    except (KeyError,ValueError,TypeError):started=datetime.now(timezone.utc)
                    self.arena_started=started
                self.log('Restored submitted '+mode+' batch; verifying without another clear')
        except FileNotFoundError:pass
        except (OSError,ValueError,KeyError,TypeError):self.log('Pending clear state unreadable; verify submitted farming before resuming',True)
    def load_completed_missions(self):
        now=datetime.now(timezone.utc);self.queue_engine.rollover(now)
        try:
            data=json.loads(CACHE.read_text(encoding='utf-8'))
            modes=restore_completed(data,now)
            self.queue_held=restore_completed(dict(data,completed=data.get('held',[])),now)
            self.queue_held_period=reset_period(now)
            self.queue_engine.completed.update(modes)
            if modes:self.log('Remembered completed quests until reset: '+', '.join(sorted(modes)))
            if self.queue_held:self.log('Unsure outcomes held for review after daily tasks: '+', '.join(sorted(self.queue_held)))
        except FileNotFoundError:pass
        except (OSError,ValueError) as error:self.log('Completion cache ignored: '+str(error),True)

    def persist_completed_missions(self):
        now=datetime.now(timezone.utc)
        if self.queue_engine.period!=reset_period(now):return False
        data=dict(version=1,period=self.queue_engine.period,recorded_at=now.isoformat(),
            expires_at=next_reset(now).isoformat(),completed=sorted(self.queue_engine.completed&ALLOWED),
            held=sorted(getattr(self,'queue_held',set())&ALLOWED) if getattr(self,'queue_held_period',None)==reset_period(now) else [])
        try:
            CACHE.parent.mkdir(parents=True,exist_ok=True);temporary=CACHE.with_suffix('.tmp')
            temporary.write_text(json.dumps(data,indent=2),encoding='utf-8');temporary.replace(CACHE)
            return True
        except OSError as error:self.log('Could not save completed quests: '+str(error),True);return False

    def record_completed(self,mode,captured_at,now):
        pending=self.queue_engine.pending
        self.queue_engine.verified_complete(mode,captured_at,now)
        if pending and pending[1]==mode:self.queue_fresh_pass=False
        self.persist_pending_clear()
        if hasattr(self,'queue_held'):self.queue_held.discard(mode)
        if hasattr(self,'queue_stall_count'):
            self.queue_stall_key=None;self.queue_stall_count=0;self.queue_stall_since=None
        self.persist_completed_missions()
