"""Level-one positional roster selection and ticket-only Zombie repeat handling."""
from datetime import datetime,timedelta,timezone
from lib.daily_queue import reset_period
from lib.resource_check import click_game_point,InputNotSent
from lib.zombie_reader import MODE,TOP_FIVE,SLOT_X

class ZombieControls:
    def init_zombie(self):
        self.zombie_started=None;self.zombie_repeat_finished=False;self.zombie_progress=None
        self.zombie_roster_cleared=False;self.zombie_roster_top=False
        self.zombie_pick=0;self.zombie_pick_wait=None;self.zombie_prepare_verified=None
        self.zombie_max_clicked=False;self.zombie_home_seen=None
        self.zombie_claim_sent=None;self.zombie_claim_attempts=0
        self.zombie_verify_board=False;self.zombie_navigation_started=None;self.zombie_max_wait=None;self.zombie_collection_started=None;self.zombie_board_scrolls=0

    def zombie_protected(self):
        return bool(self.queue_engine.pending and self.queue_engine.pending[1]==MODE)

    def complete_zombie(self,observed,now):
        pending=self.queue_engine.pending;completed=set(self.queue_engine.completed)
        if pending and pending[1]!=MODE:return False
        self.queue_engine.verified_complete(MODE,observed,now)
        # The fresh weekly board/claimed screen proves completion even if the
        # submitted repeat crossed a daily reset.
        self.queue_engine.completed.add(MODE)
        if not self.persist_completed_missions():
            self.queue_engine.pending=pending;self.queue_engine.completed=completed
            self.stop_queue();self.log('Could not save Zombie completion; no exit or new start',True);return False
        if not self.persist_pending_clear():
            self.queue_engine.pending=pending;self.stop_queue();return False
        self.queue_held.discard(MODE)
        self.queue_target=None;self.queue_phase='navigate_board';self.queue_waiting=None
        self.log('Zombie Survival weekly rewards verified complete; continuing the rest of the queue')
        return True

    def queue_zombie(self,evidence,observed):
        now=datetime.now(timezone.utc);v=evidence.values;screen=evidence.screen
        pending=self.queue_engine.pending
        def guard():
            return (self.queue_engine.running and timedelta(0)<=datetime.now(timezone.utc)-observed<=timedelta(seconds=30)
                and reset_period(observed)==reset_period(datetime.now(timezone.utc)))
        def click(point,**kwargs):
            click_game_point(self.handle,*point,guard=guard,**kwargs);self.queue_wake=now+timedelta(seconds=2)
        if not guard() or (pending and pending[1]!=MODE):return
        if screen.startswith('zombie_') and v.get('mode')!=MODE:return
        if not pending:
            if self.zombie_navigation_started is None:self.zombie_navigation_started=now
            if now-self.zombie_navigation_started>timedelta(minutes=3):
                self.stop_queue();self.log('Zombie preparation could not be verified within three minutes; no Start sent',True);return
        elif not self.zombie_repeat_finished and self.zombie_started and now-self.zombie_started>timedelta(minutes=35) and screen in ('unknown','zombie_battle','zombie_prepare','zombie_repeat'):
            self.stop_queue();self.log('Zombie result deadline reached; submitted state retained without restart or replay',True);return
        if pending and self.zombie_repeat_finished:
            if self.zombie_collection_started is None:self.zombie_collection_started=now
            if now-self.zombie_collection_started>timedelta(minutes=3):
                self.stop_queue();self.log('Zombie post-run collection needs inspection; pending state retained without replay',True);return
        if evidence.errors:
            self.queue_wake=now+timedelta(seconds=5);return
        if screen=='zombie_battle':
            if pending and v.get('progress') and v['progress'][1]==pending[2]:
                if self.zombie_progress!=v['progress']:
                    self.zombie_progress=v['progress'];self.log('Zombie auto repeat '+str(v['progress'][0])+'/'+str(v['progress'][1]))
            self.queue_wake=now+timedelta(seconds=8);return
        if screen in ('zombie_repeat_ended','zombie_repeat_exhausted'):
            if not pending:return
            self.zombie_repeat_finished=True
            if not self.persist_pending_clear():
                self.stop_queue();self.log('Could not save Zombie repeat end; leaving summary open',True);return
            click(v['point']);self.log('Zombie repeat ended; verifying weekly clear count before Acquire All');return
        if screen=='zombie_result':
            if pending and self.zombie_repeat_finished:click(v['home_point'])
            else:self.queue_wake=now+timedelta(seconds=8)
            return
        if screen=='zombie_rewards':
            if pending and self.zombie_repeat_finished:
                self.zombie_claim_sent=None;click(v['point']);self.log('Zombie weekly reward receipt acknowledged; checking completed board tile')
            return
        if screen=='content_board':
            tile=next((r for r in v.get('tiles',[]) if r.get('mode')==MODE),None)
            if tile and type(tile.get('remaining')) is int and tile['remaining']==0 and tile.get('completed') is True:
                if self.complete_zombie(observed,now):self.queue_wake=now+timedelta(seconds=1)
            elif tile and pending:
                if self.zombie_verify_board:
                    self.stop_queue();self.log('Zombie board still has rewards after collection; no duplicate repeat submitted',True)
                else:click(tile['point'])
            elif pending:
                if self.zombie_board_scrolls>=8:
                    self.stop_queue();self.log('Zombie completion tile not found during bounded board inspection; no repeat submitted',True);return
                direction='up' if self.zombie_board_scrolls==0 else 'down'
                self.zombie_board_scrolls+=1
                click((1000,500),scroll=(direction,8 if direction=='up' else 4))
            elif not pending:self.queue_phase='board';self.queue_read_board(evidence,observed)
            return
        if screen=='game_home' and v.get('home_controls_verified') is True:
            if pending and not self.zombie_repeat_finished and not self.zombie_verify_board:
                if self.zombie_home_seen is None:self.zombie_home_seen=observed;self.queue_wake=now+timedelta(seconds=3);return
                if observed-self.zombie_home_seen<timedelta(seconds=3):return
            click((1249,36));return
        if screen=='navigation_menu':click((630,642));return
        if screen=='zombie_season_notice':
            click(v['point']);return
        if screen=='zombie_lobby':
            if pending:click(v['challenges_point']);return
            self.zombie_roster_cleared=False;self.zombie_roster_top=False;self.zombie_pick=0;self.zombie_pick_wait=None
            self.zombie_prepare_verified=None;self.zombie_max_clicked=False
            if v.get('level')!=1:click(v['minimum_point']);return
            click(v['prepare_point']);return
        if screen=='zombie_prepare' and not pending:
            if v.get('level')!=1:
                self.zombie_prepare_verified=None;click(v['back_point']);return
            slots=v.get('slots')
            if not isinstance(slots,(tuple,list)) or len(slots)!=5 or any(type(b) is not bool for b in slots):return
            if not self.zombie_roster_cleared:
                occupied=[i for i,b in enumerate(slots) if b]
                if occupied:click((SLOT_X[occupied[-1]]+50,548));return
                self.zombie_roster_cleared=True
            if not self.zombie_roster_top:
                self.zombie_roster_top=True;click((1000,400),scroll=('up',8));return
            if self.zombie_pick_wait:
                expected,sent=self.zombie_pick_wait
                if tuple(slots)==tuple(i<expected for i in range(5)):
                    self.zombie_pick=expected;self.zombie_pick_wait=None
                elif now-sent>timedelta(seconds=20):
                    self.stop_queue();self.log('Zombie character tap was not confirmed; no repeated toggle or Start',True);return
                else:self.queue_wake=now+timedelta(seconds=2);return
            if self.zombie_pick<5:
                if tuple(slots)!=tuple(i<self.zombie_pick for i in range(5)):
                    self.stop_queue();self.log('Zombie selection changed unexpectedly; no Start',True);return
                self.zombie_pick_wait=(self.zombie_pick+1,now);click(TOP_FIVE[self.zombie_pick]);return
            if not all(slots):return
            self.zombie_prepare_verified=observed
            click(v['ticket_point']);return
        if screen=='zombie_repeat' and not pending:
            # A generic Repeat dialog cannot prove Level 1 or roster selection.
            # On restart, close it and rebuild fresh preparation evidence.
            if self.zombie_prepare_verified is None or not timedelta(0)<=now-self.zombie_prepare_verified<=timedelta(minutes=2):
                self.zombie_max_clicked=False;click(v['close_point']);return
            if v.get('max_selected') is not True:
                if not self.zombie_max_clicked:
                    self.zombie_max_clicked=True;self.zombie_max_wait=now;click(v['max_point']);return
                if self.zombie_max_wait and now-self.zombie_max_wait>timedelta(seconds=20):
                    self.stop_queue();self.log('Zombie MAX selection not confirmed; no Start sent',True);return
                self.queue_wake=now+timedelta(seconds=2);return
            count=v.get('selected')
            if type(count) is not int or not 1<=count<=5:return
            self.zombie_started=now;self.zombie_repeat_finished=False
            submission=(reset_period(now),MODE,count);self.queue_engine.pending=submission
            if not self.persist_pending_clear():
                self.queue_engine.pending=None;self.stop_queue();self.log('Zombie repeat not started: submission could not be saved',True);return
            if self.adb_backend is not None:
                self.adb_backend.input_evidence=dict(getattr(self.adb_backend,'input_evidence',{}),pending=list(submission),
                    zombie_level=1,zombie_roster_slots=5,zombie_max_runs=count)
            try:click(v['start_point'])
            except InputNotSent:
                self.queue_engine.pending=None;self.persist_pending_clear();return
            self.log(f'Zombie Survival: Level 1, top five roster positions, MAX {count} runs; waiting for automatic exit')
            self.queue_waiting=None;self.queue_wake=now+timedelta(seconds=8);return
        if screen=='zombie_challenges':
            if not pending:click((35,36));return
            if v.get('five_clears_verified') is not True:
                self.stop_queue();self.log('Zombie five-clear challenge not verified; submitted batch retained without replay',True);return
            if v.get('acquire_ready') is True:
                if self.zombie_claim_sent and now-self.zombie_claim_sent<timedelta(seconds=15):
                    self.queue_wake=now+timedelta(seconds=3);return
                if self.zombie_claim_attempts>=3:
                    self.stop_queue();self.log('Zombie Acquire All did not settle; leaving submitted state intact',True);return
                self.zombie_claim_sent=now;self.zombie_claim_attempts+=1
                click(v['acquire_point']);self.log('Zombie Challenges: Acquire All after five verified clears');return
            if v.get('weekly_completed')==10:
                self.zombie_verify_board=True;click((1185,36));return
        if pending:
            if not self.zombie_repeat_finished and self.zombie_started and now-self.zombie_started>timedelta(minutes=35):
                self.stop_queue();self.log('Zombie result deadline reached; saved submission retained, no replay or restart',True);return
            self.queue_wake=now+timedelta(seconds=8);return
        self.queue_pause('Waiting for verified Zombie Survival controls',5,stalled=False)
