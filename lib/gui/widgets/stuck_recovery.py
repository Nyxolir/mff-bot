"""Bounded navigation recovery; uncertain missions are held, never replayed."""
from datetime import datetime,timedelta,timezone
from lib.daily_queue import reset_period
from lib.resource_check import click_game_point
from PyQt5 import QtCore

class RestartTask(QtCore.QThread):
    result=QtCore.pyqtSignal(str)
    def __init__(self,backend,guard,parent):
        super().__init__(parent);self.backend=backend;self.guard=guard
    def run(self):
        try:self.backend.restart_game(self.guard);self.result.emit('')
        except Exception as error:self.result.emit(str(error))

class StuckRecovery:
    def navigation_back_recovery(self,evidence,observed):
        now=datetime.now(timezone.utc);screen=evidence.screen
        popup=screen in ('external_link_notice','game_settings')
        active=lambda:self.queue_engine.running or self.objective_active or self.trivia_active or self.resource_active
        protected=lambda:bool(self.queue_engine.pending or self.story_restart_protected() or self.world_event_state.started or self.world_event_state.pending or
            (getattr(self,'dispatch_supply_active',False) and getattr(getattr(self,'dispatch_supply_state',None),'pending',None)))
        if not active() or protected() or not timedelta(0)<=now-observed<=timedelta(seconds=30):return popup
        if popup:
            if getattr(self,'back_popup',None)==screen:
                point=evidence.values['cancel_point' if screen=='external_link_notice' else 'close_point']
                click_game_point(self.handle,*point,guard=lambda:active() and not protected())
                self.log('Popup remained after Android Back; used its verified Cancel/Close control')
            else:
                self.back_popup=screen
                click_game_point(self.handle,35,36,key='back',guard=lambda:active() and not protected())
                self.log('Android Back: dismissing '+screen+' and rereading the screen')
        elif screen in ('unknown','otherworld','timeline','timeline_team') and not evidence.values.get('home_available') and not evidence.values.get('menu_available'):
            # A restart may leave an unsubmitted Repeat form over a readable
            # lobby title. Treat its unavailable navigation controls like any
            # other blocked screen; pending runs remain protected above.
            started=getattr(self,'navigation_unsure_since',None)
            if started is None:self.navigation_unsure_since=now;self.navigation_unsure_backs=0
            if getattr(self,'navigation_unsure_backs',0)>=2:return False
            if started is not None and now-started>=timedelta(seconds=6):
                # A recognized lobby between failures must not reset the
                # per-mission budget and create an endless enter/back loop.
                if self.queue_engine.running and self.queue_target and self.note_queue_stall('Unrecognized navigation screen after entering content'):
                    self.navigation_unsure_since=None
                    self.queue_observation=None
                    return True
                click_game_point(self.handle,35,36,key='back',guard=lambda:active() and not protected())
                self.navigation_unsure_backs+=1;self.navigation_unsure_since=now
                self.log('Android Back: recovering an unrecognized navigation screen ('+str(self.navigation_unsure_backs)+'/2)')
        else:
            self.back_popup=None;self.navigation_unsure_since=None;self.navigation_unsure_backs=0;return False
        self.objective_waiting=None;self.trivia_waiting=None;self.queue_waiting=None;self.resource_waiting=None;self.world_event_waiting=None
        self.queue_observation=None;self.objective_observation=None;self.trivia_observation=None;self.resource_observation=None
        self.queue_wake=now+timedelta(seconds=3)
        QtCore.QTimer.singleShot(3000,self.scan_live)
        return True

    def init_stuck_recovery(self):
        self.queue_held=set();self.queue_held_period=reset_period(datetime.now(timezone.utc))
        self.queue_stall_key=None;self.queue_stall_count=0;self.queue_stall_since=None
        self.queue_recovering=False;self.queue_recovery_steps=0
        self.restart_task=None;self.restart_attempts=[]

    def story_restart_protected(self):
        pending=self.queue_engine.pending
        return (bool(pending and pending[1]=='STORY ULTIMATE') or
            (self.story_started is not None and 'STORY ULTIMATE' not in self.queue_engine.completed and
             timedelta(0)<=datetime.now(timezone.utc)-self.story_started<timedelta(minutes=95)))

    def restart_stuck_game(self):
        if self.dimension_claim_protected():
            self.stop_queue();self.log('Dimension clears are confirmed; contribution claim needs verification. Submission and claim state preserved without replay.',True);return
        if self.zombie_protected():
            self.stop_queue();self.log('Zombie repeat is protected; game left running without restart',True);return
        now=datetime.now(timezone.utc)
        if self.arena_repeat_protected():
            self.stop_queue();self.log('Arena repeat is active; game left untouched rather than restarted.',True);return
        if self.story_restart_protected():
            self.stop_queue();self.log('Story is restart protected; game left running.',True);return
        self.restart_attempts=[t for t in self.restart_attempts if now-t<timedelta(hours=1)]
        if len(self.restart_attempts)>=2 or not self.adb_backend:
            self.stop_queue();self.log('Automatic restart limit reached or background connection unavailable; game left running.',True);return
        self.restart_attempts.append(now)
        if self.trivia_active:self.finish_trivia('Game recovery interrupted inspection; retry later')
        if self.objective_active:self.finish_objectives('Game recovery interrupted inspection')
        if self.resource_active:self.finish_resource_check('Game recovery interrupted inspection',True)
        self.queue_recovering=False;self.queue_wake=now+timedelta(seconds=45)
        self.log('Recovery: Android Home → close MFF → relaunch. Maximum two restarts per hour.',True)
        self.restart_task=RestartTask(self.adb_backend,
            lambda:self.queue_engine.running and not self.story_restart_protected(),self)
        self.restart_task.result.connect(self.restart_finished)
        self.restart_task.start()

    def restart_finished(self,error):
        if error:
            self.stop_queue();self.log('Game restart failed: '+error,True);return
        if not self.queue_engine.running:return
        now=datetime.now(timezone.utc)
        self.session_reload_deadline=now+timedelta(minutes=3)
        self.queue_wake=now+timedelta(seconds=30)
        self.queue_recovering=True;self.queue_recovery_steps=0;self.queue_phase='recover_home'
        self.log('MFF restarted; waiting for loading before resuming the queue')

    def note_queue_stall(self,reason):
        now=datetime.now(timezone.utc)
        mode=self.queue_engine.pending[1] if self.queue_engine.pending else self.queue_target
        if not mode:return False
        if self.queue_stall_key!=mode:
            self.queue_stall_key=mode;self.queue_stall_since=now;self.queue_stall_count=0
        self.queue_stall_count+=1
        if self.queue_stall_count>=4 or now-self.queue_stall_since>=timedelta(seconds=90):
            self.recover_stuck_queue(reason);return True
        return False

    def recover_stuck_queue(self,reason):
        if self.dimension_claim_protected():
            self.stop_queue();self.log('Dimension contribution needs inspection; confirmed clears and claim state preserved: '+reason,True);return
        if self.zombie_protected():
            self.stop_queue();self.log('Zombie repeat needs inspection; submitted state preserved without restart or replay: '+reason,True);return
        if self.arena_repeat_protected():
            self.stop_queue();self.log('Arena repeat needs inspection: '+reason+'. Game left untouched; submitted state preserved.',True);return
        if self.story_restart_protected():
            self.stop_queue();self.log('Story needs attention: '+reason+'. Automatic restart suppressed; game left running.',True);return
        now=datetime.now(timezone.utc)
        mode=self.queue_engine.pending[1] if self.queue_engine.pending else self.queue_target
        if not mode:return
        if self.queue_held_period!=reset_period(now):self.queue_held=set();self.queue_held_period=reset_period(now)
        uncertain=self.queue_engine.pending is not None
        if uncertain:self.queue_held.add(mode)
        else:self.queue_deferred[mode]=now+timedelta(minutes=5)
        # Save the no-retry hold before clearing pending, including unknown
        # spending outcomes. Held is distinct from verified completion.
        if not self.persist_completed_missions():
            self.stop_queue();self.log('Could not save stuck-mission hold; stopped to avoid replay',True);return
        self.queue_engine.pending=None;self.queue_engine.generation+=1
        if not self.persist_pending_clear():
            self.stop_queue();self.log('Could not clear the saved pending state; stopped to preserve the hold',True);return
        self.contribution_followup=False;self.contribution_submitted=False
        self.epic_preparation=None;self.queue_target=None;self.queue_waiting=None
        self.queue_stall_key=None;self.queue_stall_count=0
        self.queue_recovering=True;self.queue_recovery_steps=0
        self.queue_phase='recover_home';self.queue_wake=now+timedelta(seconds=1)
        disposition='held for end-of-day verification because a submitted outcome is uncertain' if uncertain else 'navigation deferred for five minutes; no clear was submitted'
        self.log(mode+': stuck ('+reason+'). '+disposition+'; returning home and continuing.',True)

    def dimension_claim_protected(self):
        pending=self.queue_engine.pending
        return bool(pending and pending[1]=='DIMENSION MISSION' and getattr(self,'contribution_followup',False))

    def arena_repeat_protected(self):
        pending=self.queue_engine.pending
        return bool(pending and pending[1] in ('TIMELINE BATTLE','OTHERWORLD BATTLE','TEAM BATTLE ARENA') and not getattr(self,'arena_repeat_finished',False))

    def queue_recover_home(self,evidence,observed):
        now=datetime.now(timezone.utc)
        if not self.queue_engine.running or not timedelta(0)<=now-observed<=timedelta(seconds=30):return
        if evidence.screen in ('game_home','navigation_menu','content_board','status_board'):
            self.session_reload_deadline=None
            self.queue_recovering=False;self.queue_phase='navigate_board';self.queue_wake=None
            if self.board_check_active:self.board_check_active=False;self.board_check_due=True
            self.log('Navigation recovered; continuing with the next unfinished quest');return
        if self.session_reload_deadline and now<self.session_reload_deadline and evidence.screen=='unknown':
            self.queue_wake=now+timedelta(seconds=5);return
        if self.queue_recovery_steps>=8:
            self.restart_stuck_game();return
        self.queue_recovery_steps+=1
        guard=lambda:self.queue_engine.running and self.queue_recovering
        if evidence.values.get('menu_available'):
            click_game_point(self.handle,1249,36,guard=guard)
            self.queue_recovering=False;self.queue_phase='navigate_board';self.queue_observation=None
            self.queue_waiting=(('navigation_menu',),now)
        elif evidence.values.get('home_available'):
            click_game_point(self.handle,1185,36,guard=guard)
        else:click_game_point(self.handle,35,36,key='back',guard=guard)
        self.queue_wake=now+timedelta(seconds=3)
