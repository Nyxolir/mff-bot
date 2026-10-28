"""Separate normal/hidden daily ticket sweeps; preserve submitted outcomes."""
from datetime import datetime,timedelta,timezone
from lib.converging import NORMAL,HIDDEN
from lib.farming import UNBOOSTED_SWEEPS
from lib.daily_queue import BatchEvidence,QueueAction,reset_period
from lib.resource_check import click_game_point,InputNotSent

class ConvergingControls:
    def finish_converging(self,mode,observed,now):
        previous=set(self.queue_engine.completed);pending=self.queue_engine.pending;held=set(self.queue_held)
        self.queue_engine.verified_complete(mode,observed,now)
        self.queue_held.discard(mode)
        if not self.persist_completed_missions() or not self.persist_pending_clear():
            self.queue_engine.completed=previous;self.queue_engine.pending=pending;self.queue_held=held
            self.stop_queue();self.log('Could not persist Converging completion; leaving the verified zero-entry screen',True);return
        self.queue_fresh_pass=False
        if not self.queue_engine.running or mode not in self.queue_engine.completed:return
        self.converging_preparation=None
        other=HIDDEN if mode==NORMAL else NORMAL
        enabled=any(r['mode']==other and r['enabled'] for r in self.queues[self.queue_index])
        if enabled and other not in self.queue_engine.completed:
            self.queue_target=other
            self.log(mode+': zero entries verified; opening '+other+' directly from this chapter')
            self.queue_send_point((35,36),'converging',('converging_chapter',));return
        self.queue_target=None
        self.queue_send_point((1185,36),'navigate_board',('game_home',))

    def queue_converging(self,evidence,observed):
        now=datetime.now(timezone.utc);mode=self.queue_target;v=evidence.values;pending=self.queue_engine.pending
        if mode not in UNBOOSTED_SWEEPS or evidence.errors:return self.queue_pause('Converging Fates screen needs verification',15,stalled=False)
        if not timedelta(0)<=now-observed<=timedelta(seconds=30) or reset_period(now)!=reset_period(observed):return
        if pending:
            if pending[1]!=mode:return
            if evidence.screen=='converging_ready' and v.get('mode')==mode and v.get('remaining')==0 and v.get('preparation_verified') is True and v.get('total')==5:
                self.finish_converging(mode,observed,now);return
            if evidence.screen=='converging_result' and v.get('mode')==mode and v.get('result_verified') and v.get('clears')==pending[2]:
                self.queue_send_point(v['point'],'converging',('converging_ready',));return
            self.queue_pause('Waiting for the submitted Converging ticket sweep and zero daily entries; no repeat',5,stalled=False);return
        if evidence.screen=='converging_chapter':
            self.converging_preparation=None
            self.queue_send_point(v['points'][mode],'converging',('converging_difficulty',));return
        if evidence.screen=='converging_difficulty':
            self.queue_send_point(v['point'],'converging',('converging_ready',));return
        if evidence.screen=='converging_ready':
            if v.get('preparation_verified') is not True or type(v.get('remaining')) is not int or not 0<=v['remaining']<=5 or v.get('total')!=5:
                self.queue_pause('Converging preparation/counter incomplete',10,stalled=False);return
            if v.get('mode')!=mode:
                self.converging_preparation=None
                self.queue_send_point((35,36),'converging',('converging_chapter',));return
            if v.get('remaining')==0:self.finish_converging(mode,observed,now);return
            self.converging_preparation=(evidence,observed,self.queue_engine.generation)
            self.queue_send_point(v['point'],'converging',('converging_vault_notice','converging_sweep'));return
        prepared=getattr(self,'converging_preparation',None)
        valid=bool(prepared and prepared[0].values.get('mode')==mode and prepared[2]==self.queue_engine.generation
            and reset_period(prepared[1])==reset_period(now) and timedelta(0)<=now-prepared[1]<=timedelta(seconds=120))
        if evidence.screen=='converging_vault_notice':
            # The user explicitly approved this identical full-vault notice.
            self.queue_send_point(v['point'] if valid else (539,536),'converging',('converging_sweep',) if valid else ('converging_ready',));return
        if evidence.screen=='converging_sweep':
            if v.get('sweep_verified') is not True or v.get('boost_total')!=0 or v.get('crystal_total')!=0:
                self.queue_pause('Converging ticket sweep is not verified',10,stalled=False);return
            if not valid:
                self.queue_send_point(v['close_point'],'converging',('converging_ready',));return
            remaining=prepared[0].values['remaining']
            single=remaining==1 and v.get('single_verified') is True
            if v.get('selected')!=remaining and not single:
                self.queue_send_point(v['close_point'],'converging',('converging_ready',));return
            batch=BatchEvidence(mode,remaining,remaining,None,0,None,None,None,None,observed,0,False,True)
            decision=self.queue_engine.authorize(batch,now)
            if decision.action!=QueueAction.CLEAR:self.queue_pause(decision.reason,10,stalled=False);return
            if not self.persist_pending_clear():
                self.queue_engine.pending=None;self.stop_queue();return
            generation=self.queue_engine.generation;period=reset_period(now)
            try:
                click_game_point(self.handle,*((408,555) if single else v['point']),guard=lambda:self.queue_engine.running and self.queue_engine.generation==generation
                    and self.queue_engine.pending==(period,mode,remaining) and reset_period(datetime.now(timezone.utc))==period
                    and timedelta(0)<=datetime.now(timezone.utc)-observed<=timedelta(seconds=30))
            except InputNotSent:
                self.queue_engine.pending=None;self.persist_pending_clear()
            self.queue_waiting=None;self.queue_wake=now+timedelta(seconds=3);return
        if evidence.screen=='converging_result' and v.get('mode')==mode:
            self.queue_send_point(v['point'],'converging',('converging_ready',));return
        if evidence.screen=='game_home' or v.get('menu_available'):
            self.queue_target=None;self.queue_phase='navigate_board';self.queue_waiting=None
            self.queue_wake=now+timedelta(seconds=1);return
        self.queue_pause('Waiting for Converging Fates controls',5,stalled=False)
