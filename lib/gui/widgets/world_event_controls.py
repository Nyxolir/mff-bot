"""Periodic World Event auto participation; daily completion requires 0/2."""
from datetime import datetime,timedelta,timezone
from lib.world_event import WorldEventState
from lib.resource_check import click_game_point

class WorldEventControls:
    def init_world_event(self):
        self.world_event_state=WorldEventState.load(datetime.now(timezone.utc))
        self.world_event_active=False;self.world_event_waiting=None
    def world_event_enabled(self):
        return any(i['enabled'] and i['mode']=='WORLD EVENT' for i in self.queues[self.queue_index])
    def start_world_event(self,now):
        self.world_event_active=True;self.world_event_started=now;self.world_event_steps=0
        self.world_event_generation=self.queue_engine.generation;self.world_event_resume=self.queue_wake
        self.world_event_waiting=None;self.queue_phase='world_event';self.queue_wake=None;self.queue_waiting=None
        self.world_event_visit=0;self.world_event_state.reset_zero_verification()
        self.world_event_state.lobby_reconciliation=None
        self.world_event_board_unavailable=False
        self.epic_preparation=None;self.world_event_auto_clicked=False;self.world_event_unknown_since=None;self.world_event_home_scrolls=0;self.world_event_tab_attempts=0
        self.log('Checking World Event: auto participation until daily entries show 0/2')
    def finish_world_event(self,message):
        self.world_event_active=False;self.world_event_waiting=None
        try:self.world_event_state.save()
        except OSError as error:
            self.stop_queue();self.log("Could not save World Event state: "+str(error),True);return
        self.queue_phase='dimension_nav' if self.queue_target=='DIMENSION MISSION' else 'dispatch' if self.queue_target=='DISPATCH 7-1' else 'navigate_board'
        self.queue_wake=self.world_event_resume
        self.log('World Event: '+message)
    def queue_world_event(self,evidence,observed):
        now=datetime.now(timezone.utc);state=self.world_event_state
        if not self.world_event_active or not timedelta(0)<=now-observed<=timedelta(seconds=30):return
        def guard():return self.queue_engine.running and self.world_event_active and self.queue_engine.generation==self.world_event_generation and timedelta(0)<=datetime.now(timezone.utc)-observed<=timedelta(seconds=30)
        def click(point,expected=None):
            click_game_point(self.handle,*point,guard=guard)
            if expected:self.world_event_waiting=(expected,now)
            self.queue_wake=now+timedelta(seconds=3)
        def open_event(point):
            self.world_event_visit+=1
            click(point,('we_lobby','we_closed'))
        try:
            if now-self.world_event_started>timedelta(minutes=12) or self.world_event_steps>=150:
                raise ValueError('check timed out; deferred without repeating an entry')
            self.world_event_steps+=1
            screen=evidence.screen;v=evidence.values
            if screen!='we_lobby':state.lobby_reconciliation=None
            if self.world_event_waiting:
                expected,stamp=self.world_event_waiting
                if screen not in expected:
                    if now-stamp>timedelta(seconds=60):raise ValueError('navigation timed out')
                    self.queue_wake=now+timedelta(seconds=3);return
                self.world_event_waiting=None
            if evidence.errors:raise ValueError('; '.join(evidence.errors))
            if screen in ('we_lobby','we_closed'):
                if state.started:
                    if screen!='we_lobby' or not state.reconcile_started_lobby(v,now,observed):
                        self.queue_wake=now+timedelta(seconds=5);return
                    # Persist the end of gameplay before allowing page refreshes.
                    state.started=False
                    try:state.save()
                    except OSError:
                        state.started=True
                        raise
                    self.log('World Event: consumed-entry lobby stable for 60 seconds; submitted run reconciled, checking daily completion')
                # A failed completion save must retain the submission in memory
                # as well as on disk. No navigation is permitted before saving.
                previous=(state.pending,state.started,state.done,state.completion_proof,state.next_check)
                decision=state.lobby(v,now,observed=observed,visit=self.world_event_visit)
                try:state.save()
                except OSError:
                    state.pending,state.started,state.done,state.completion_proof,state.next_check=previous
                    raise
                if decision=='recheck_zero':
                    self.log('World Event: 0/2 candidate '+str(len(state.zero_observations))+'/3; reopening the event page to refresh cached entries')
                    self.world_event_board_unavailable=True
                    click((1185,36),('we_home','game_home'));return
                if decision=='done':self.finish_world_event('0/2 verified on three reopened event-page visits; finished until reset');return
                if decision!='enter':self.finish_world_event(decision+'; will check a later slot');return
                click(v['point'],('we_team',));return
            if screen=='we_team':
                if state.pending:raise ValueError('entry already submitted; will verify later')
                click(v['point'],('we_confirm',));return
            if screen=='we_confirm':
                if state.pending:raise ValueError('entry confirmation already submitted; no retry')
                if v['entries'][1]!=2 or v['entries'][0]<=0:raise ValueError('No verified reward entry')
                state.before=v['entries'][0];state.pending=True;state.started=False
                # Durable latch before confirmation; no transport retry.
                if state.slot_until is None:state.slot_until=now+timedelta(hours=6)
                state.save();click(v['point'],('we_start',));return
            if screen=='we_start':
                if state.pending and state.started:
                    self.queue_wake=now+timedelta(seconds=5);return
                if not state.pending:raise ValueError('Start lacks a fresh, unsubmitted entry confirmation')
                state.started=True;state.save();click(v['point']);return
            if screen=='we_battle':
                if not v['auto_on'] and not self.world_event_auto_clicked:
                    self.world_event_auto_clicked=True;click((398,672));return
                self.queue_wake=now+timedelta(seconds=5);return
            if v.get('home_available') and not state.started:
                if v.get('menu_available') and not self.world_event_board_unavailable:
                    click((1249,36),('navigation_menu',));return
                click((1185,36),('we_home','game_home'));return
            if screen=='unknown' and not v.get('menu_available'):
                if self.world_event_unknown_since is None:self.world_event_unknown_since=now
                if now-self.world_event_unknown_since<timedelta(seconds=60):
                    self.queue_wake=now+timedelta(seconds=5);return
            else:self.world_event_unknown_since=None
            if screen=='we_result':
                state.started=False;state.save();click(v['point']);return
            if screen=='we_result_summary':
                click(v['point'],('we_lobby','we_closed'));return
            if state.started and screen=='unknown' and not v.get('menu_available'):
                # Loading/results animations never authorize another entry.
                self.queue_wake=now+timedelta(seconds=5);return
            if screen=='navigation_menu':click((630,642),('status_board','content_board'));return
            if screen=='status_board':self.queue_wake=now+timedelta(seconds=2);return
            if screen=='content_board':
                self.remember_board_completions(evidence,observed)
                tile=next((c for c in v['tiles'] if c['mode']=='WORLD EVENT'),None)
                if tile:open_event(tile['point']);return
                self.world_event_board_unavailable=True
                click((1185,36),('we_home','game_home'));return
            if screen=='we_home':
                # A verified event shortcut is sufficient, regardless of tab artwork.
                if v['event_point']:open_event(v['event_point']);return
                if state.pending and not state.started and not self.world_event_board_unavailable:
                    click((1249,36),('navigation_menu',));return
                if not v['battle_tab']:
                    if self.world_event_tab_attempts>=2:raise ValueError('Battle tab did not settle; deferring World Event')
                    self.world_event_tab_attempts+=1;click((1020,335));return
                if self.world_event_home_scrolls>=6:raise ValueError('World Event home shortcut unavailable; checking a later slot')
                self.world_event_home_scrolls+=1
                click_game_point(self.handle,1080,500,scroll=('down',2),guard=guard)
                self.queue_wake=now+timedelta(seconds=3);return
            if v.get('menu_available'):click((1249,36),('navigation_menu',));return
            raise ValueError('screen not recognized')
        except Exception as error:
            if state.pending or state.started:
                self.stop_queue();self.log('World Event: '+str(error)+'; submitted outcome preserved without restart or replay',True);return
            state.next_check=now+timedelta(minutes=5)
            self.finish_world_event(str(error))
            if self.queue_engine.running:
                self.queue_recovering=True;self.queue_recovery_steps=0
                self.queue_phase="recover_home";self.queue_wake=now+timedelta(seconds=1)
