"""Revisit held outcomes only after the ordinary daily queue has drained."""
from datetime import datetime,timedelta,timezone
from lib.daily_queue import reset_period
from lib.farming import ENERGY_FARMS,UNBOOSTED_SWEEPS
from lib.resource_check import click_game_point

REVIEWABLE=ENERGY_FARMS|UNBOOSTED_SWEEPS|{'TIMELINE BATTLE','OTHERWORLD BATTLE','TEAM BATTLE ARENA','ALLIANCE BATTLE','DISPATCH 7-1'}

class UncertainReview:
    def init_uncertain_review(self):
        self.review_mode=None;self.review_due={};self.review_period=reset_period(datetime.now(timezone.utc))

    def uncertain_review_candidates(self,now):
        if self.review_period!=reset_period(now):
            self.review_due={};self.review_mode=None;self.review_period=reset_period(now)
        enabled={row['mode'] for row in self.queues[self.queue_index] if row['enabled']}
        held=self.queue_held if self.queue_held_period==reset_period(now) else set()
        return sorted((held&enabled&REVIEWABLE)-self.queue_engine.completed)

    def start_uncertain_review(self,now):
        if self.queue_engine.pending or self.story_restart_protected():return False
        mode=next((m for m in self.uncertain_review_candidates(now) if now>=self.review_due.get(m,now)),None)
        if mode is None:return False
        self.review_mode=mode;self.review_started=now;self.review_scrolls=0
        self.queue_phase='uncertain_review';self.queue_waiting=None;self.queue_wake=None
        if mode=='DIMENSION MISSION':
            self.log('Reviewing Dimension Mission through fresh challenge/event requirements; its contribution outcome is not checked on the content board')
            self.check_objectives(force=True)
            return True
        self.log('Daily queue finished: reviewing unsure outcome for '+mode+'; no replay without fresh remaining entries')
        return True

    def finish_uncertain_review(self,message):
        mode=self.review_mode;self.review_mode=None
        self.review_due[mode]=datetime.now(timezone.utc)+timedelta(minutes=5)
        self.queue_phase='navigate_board';self.queue_target=None;self.queue_waiting=None;self.queue_wake=None
        self.log('Unsure review '+str(mode)+': '+message)

    def reconcile_held_dimension_objectives(self):
        now=datetime.now(timezone.utc);inspection=self.objective_inspection;plan=self.objective_plan
        if ('DIMENSION MISSION' not in self.queue_held or self.queue_engine.pending
                or getattr(inspection,'done',False) is not True or inspection.period!=reset_period(now)
                or not self.objective_plan_current(now) or plan.claim_contribution):return False
        previous=set(self.queue_engine.completed);held=set(self.queue_held)
        if plan.dimension_clears:self.queue_engine.completed.discard('DIMENSION MISSION')
        else:self.queue_engine.completed.add('DIMENSION MISSION')
        self.queue_held.discard('DIMENSION MISSION')
        if not self.persist_completed_missions():
            self.queue_engine.completed=previous;self.queue_held=held;self.stop_queue()
            self.log('Could not save verified Dimension objective reconciliation',True);return False
        self.contribution_followup=False;self.contribution_submitted=False;self.contribution_before=None;self.contribution_acquire_submitted=False
        message=(str(plan.dimension_clears)+' additional clears required; contribution already complete; hold released for the remaining objective batch'
            if plan.dimension_clears else 'fresh objectives confirm clears and contribution reward complete; unsure hold resolved')
        if self.review_mode=='DIMENSION MISSION':self.finish_uncertain_review(message)
        self.log('Dimension Mission: '+message)
        return True

    def queue_uncertain_review(self,evidence,observed):
        now=datetime.now(timezone.utc);mode=self.review_mode
        if not mode or not self.queue_engine.running or self.queue_engine.pending:return
        if not timedelta(0)<=now-observed<=timedelta(seconds=30):return
        if reset_period(now)!=self.review_period:
            self.finish_uncertain_review('daily reset crossed; old outcome not used');return
        if now-self.review_started>timedelta(seconds=90):
            self.finish_uncertain_review('not verified; keep unsure and revisit in five minutes');return
        guard=lambda:self.queue_engine.running and self.review_mode==mode and self.queue_engine.pending is None and timedelta(0)<=datetime.now(timezone.utc)-observed<=timedelta(seconds=30)
        def click(point):
            click_game_point(self.handle,*point,guard=guard);self.queue_wake=now+timedelta(seconds=3)
        if mode=='DIMENSION MISSION':
            self.check_objectives(force=True);return
        if evidence.errors:self.queue_wake=now+timedelta(seconds=5);return
        if evidence.screen=='game_home':click((1249,36));return
        if evidence.screen=='navigation_menu':click((630,642));return
        if evidence.screen=='status_board':self.queue_wake=now+timedelta(seconds=2);return
        if evidence.screen=='content_board':
            row=next((r for r in evidence.values.get('tiles',[]) if r.get('mode')==mode),None)
            if row:
                remaining=row.get('remaining');total=row.get('total')
                done=remaining==0 or (remaining is None and row.get('completed') is True)
                positive=(type(remaining) is int and type(total) is int and 0<remaining<=total)
                if not done and not positive:
                    self.finish_uncertain_review('counter unreadable; keep unsure');return
                self.queue_held.discard(mode)
                if not self.persist_completed_missions():
                    self.queue_held.add(mode);self.stop_queue();return
                if done:
                    self.record_completed(mode,observed,now)
                    self.finish_uncertain_review('confirmed complete; skipped until reset');return
                # Release only a fresh, named remaining count. Normal prep
                # must re-verify costs, daily GBR clearance and current balance.
                self.queue_deferred.pop(mode,None)
                self.finish_uncertain_review(str(remaining)+' remaining verified; returned to normal queue for fresh preparation')
                return
            if self.review_scrolls>=8:
                self.finish_uncertain_review('named tile not found; keep unsure');return
            from lib.queue_input import scroll_board
            scroll_board(self.handle,'up' if self.review_scrolls==0 else 'down',8 if self.review_scrolls==0 else 4)
            self.review_scrolls+=1;self.queue_wake=now+timedelta(seconds=3);return
        if evidence.values.get('menu_available'):click((1249,36));return
        if evidence.values.get('home_available'):click((1185,36));return
        self.queue_wake=now+timedelta(seconds=5)
