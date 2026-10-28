"""Periodic passive Dispatch collection within the continuous queue."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from lib.app_paths import data_path
import json
from lib.dispatch_supplies import DispatchSuppliesSession
from lib.dispatch_schedule import load_schedule,next_supply_check
from lib.resource_check import click_game_point
SUPPLY_NEXT=data_path('settings/gui/dispatch-supply-next.txt')
SUPPLY_STATE=SUPPLY_NEXT.with_name('dispatch-supply-state.json')

class DispatchSuppliesControls:
    def init_dispatch_supplies(self):
        self.dispatch_supply_active=False;self.dispatch_supply_state=None
        self.dispatch_supply_next=datetime.now(timezone.utc)
        self.dispatch_supply_last_claim=None
        self.dispatch_supply_waiting=None;self.dispatch_supply_resume=None
        try:
            if SUPPLY_STATE.exists():
                self.dispatch_supply_last_claim,self.dispatch_supply_next=load_schedule(json.loads(SUPPLY_STATE.read_text()),self.dispatch_supply_next)
                return
            saved=datetime.fromisoformat(SUPPLY_NEXT.read_text())
            if saved.tzinfo and timedelta(0)<saved-self.dispatch_supply_next<=timedelta(minutes=15):self.dispatch_supply_next=saved
        except (OSError,ValueError,TypeError):pass

    def start_dispatch_supplies(self,now):
        self.dispatch_supply_active=True;self.dispatch_supply_state=DispatchSuppliesSession(now)
        self.dispatch_supply_waiting=None;self.dispatch_supply_generation=self.queue_engine.generation
        self.dispatch_supply_resume=self.queue_wake
        self.queue_phase='dispatch_supplies';self.queue_waiting=None;self.queue_wake=None
        self.log('Checking passive Dispatch supplies; pink reward dots permit Claim All Rewards')

    def finish_dispatch_supplies(self,error=None):
        state=self.dispatch_supply_state;self.dispatch_supply_active=False;self.dispatch_supply_waiting=None
        now=datetime.now(timezone.utc)
        if not error and state and state.claimed:
            self.dispatch_supply_last_claim=state.claim_started
        self.dispatch_supply_next=(now+timedelta(minutes=15) if error else
            next_supply_check(now,self.dispatch_supply_last_claim,getattr(state,'fill',None)))
        self.queue_phase='dimension_nav' if self.queue_target=='DIMENSION MISSION' else 'dispatch' if self.queue_target=='DISPATCH 7-1' else 'navigate_board'
        self.queue_wake=self.dispatch_supply_resume
        if error:
            self.log('Dispatch supplies: '+error,True)
            if state and state.pending:self.stop_queue()
        else:
            try:
                SUPPLY_STATE.parent.mkdir(parents=True,exist_ok=True)
                temp=SUPPLY_STATE.with_suffix('.tmp')
                temp.write_text(json.dumps({'last_claimed_at':self.dispatch_supply_last_claim.isoformat() if self.dispatch_supply_last_claim else None,
                    'next_check_at':self.dispatch_supply_next.isoformat()},indent=2))
                temp.replace(SUPPLY_STATE)
            except OSError as failure:self.log('Could not save Dispatch check schedule: '+str(failure),True)
            self.log(f'Dispatch supplies: {state.claimed} Claim All collections verified; next check {self.dispatch_supply_next.astimezone().strftime("%H:%M")}.')

    def queue_dispatch_supplies(self,evidence,observed):
        now=datetime.now(timezone.utc)
        if not self.dispatch_supply_active:return
        if not timedelta(0)<=now-observed<=timedelta(seconds=30):
            self.queue_wake=now+timedelta(seconds=2);return
        try:
            if self.dispatch_supply_waiting:
                expected,started=self.dispatch_supply_waiting
                if evidence.screen not in expected:
                    if now-started>timedelta(seconds=25):raise ValueError('Dispatch supplies navigation did not complete')
                    self.queue_wake=now+timedelta(seconds=2);return
                self.dispatch_supply_waiting=None
            action=self.dispatch_supply_state.observe(evidence,now)
            if action is None:self.finish_dispatch_supplies();return
            kind,x,y=action
            if kind=='wait':self.queue_wake=now+timedelta(seconds=2);return
            def active():
                return self.queue_engine.running and self.dispatch_supply_active and self.queue_engine.generation==self.dispatch_supply_generation and timedelta(0)<=datetime.now(timezone.utc)-observed<=timedelta(seconds=30)
            if kind=='claim':
                stamp=self.dispatch_supply_state.reward_proof[1]
                def authorized():return active() and timedelta(0)<=datetime.now(timezone.utc)-stamp<=timedelta(seconds=30)
                click_game_point(self.handle,x,y,guard=authorized)
                # The session owns the pending transaction's 60-second
                # deadline and waits without input through loading frames.
                self.dispatch_supply_waiting=None
            elif kind=='ack':
                click_game_point(self.handle,x,y,guard=active)
                self.dispatch_supply_waiting=None
            elif kind in ('left','right'):
                click_game_point(self.handle,x,y,drag_to=(220,318) if kind=='left' else (1030,318),guard=active)
            elif kind=='back':
                click_game_point(self.handle,x,y,key='back',guard=active)
                self.dispatch_supply_waiting=(('dispatch_supplies_map',),now)
            else:
                click_game_point(self.handle,x,y,guard=active)
                expected=None
                if (x,y)==(1249,36):expected=('navigation_menu',)
                elif (x,y)==(491,642) or (x,y)==(194,135):expected=('select_mission','select_mission_coop')
                elif (x,y)==(174,376) or (x,y)==(1244,108):expected=('dispatch_supplies_map','dispatch_supply_empty_map')
                elif evidence.screen=='dispatch_supplies_map':expected=('dispatch_supply_panel',)
                if expected:self.dispatch_supply_waiting=(expected,now)
            self.queue_wake=now+timedelta(seconds=3)
        except Exception as error:self.finish_dispatch_supplies(str(error))
