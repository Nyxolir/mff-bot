"""One bounded board pass before daily mode-specific navigation."""
from datetime import datetime,timedelta,timezone
from lib.daily_queue import reset_period,next_reset
from lib.resource_check import click_game_point
from lib.gui.widgets.completion_cache import ALLOWED

class DailyBoardCheck:
    def remember_board_completions(self,evidence,observed):
        now=datetime.now(timezone.utc)
        if evidence.screen!='content_board' or evidence.errors or not timedelta(0)<=now-observed<=timedelta(seconds=30):return
        pending=self.queue_engine.pending
        rows=sorted(evidence.values.get('tiles',[]),key=lambda row:bool(pending and row.get('mode')!=pending[1]))
        for row in rows:
            mode=row.get('mode')
            if row.get('remaining')!=0 or not row.get('completed'):continue
            if self.queue_engine.pending and mode!=self.queue_engine.pending[1]:continue
            if mode in ALLOWED and mode not in self.queue_engine.completed:self.record_completed(mode,observed,now)
            if mode=='STORY ULTIMATE' and self.story_started:
                self.persist_story_run(False);self.story_started=None
            # World Event board values can stay cached until its page opens.
            # Neither a completed tile nor an absent tile proves daily exhaustion.

    def start_daily_board_check(self,now):
        self.board_check_active=True;self.board_check_started=now;self.board_check_steps=0
        self.board_check_signatures=set();self.board_check_top=False
        self.board_check_top_signature=None;self.board_check_unfinished=set();self.board_check_prefix_verified=True
        self.queue_phase='daily_board_check';self.queue_target=None;self.queue_waiting=None;self.queue_wake=None
        self.log('Checking Content Status Board first; completed daily content will be cached until reset')

    def finish_daily_board_check(self,message):
        self.board_check_active=False;self.board_check_due=False
        self.queue_phase='navigate_board';self.queue_waiting=None;self.queue_wake=None
        self.log('Content Status Board: '+message)

    def queue_daily_board_check(self,evidence,observed):
        now=datetime.now(timezone.utc)
        if not self.queue_engine.running or self.queue_engine.pending or not self.board_check_active:return
        if not timedelta(0)<=now-observed<=timedelta(seconds=30):return
        if now-self.board_check_started>timedelta(seconds=100) or self.board_check_steps>=12:
            self.finish_daily_board_check('inspection bounded; unreadable tasks remain unconfirmed');return
        if evidence.errors:self.queue_wake=now+timedelta(seconds=3);return
        guard=lambda:self.queue_engine.running and self.board_check_active and timedelta(0)<=datetime.now(timezone.utc)-observed<=timedelta(seconds=30)
        def click(point):
            click_game_point(self.handle,*point,guard=guard)
            self.queue_wake=now+timedelta(seconds=3)
        self.board_check_steps+=1
        if evidence.screen=='content_board':
            self.remember_board_completions(evidence,observed)
            signature=tuple((row.get('mode'),row.get('remaining'),row.get('completed')) for row in evidence.values.get('tiles',[]))
            if not self.board_check_top:
                if self.board_check_top_signature==signature:self.board_check_top=True
                else:
                    self.board_check_top_signature=signature
                    click_game_point(self.handle,1000,500,scroll=('up',8),guard=guard);self.queue_wake=now+timedelta(seconds=3);return
            self.board_check_prefix_verified &= evidence.values.get('incomplete_prefix_verified') is True
            self.board_check_unfinished.update(evidence.values.get('unfinished_modes',[]))
            if evidence.values.get('completed_tail_verified') is True:
                if self.board_check_prefix_verified:
                    # User confirmed this board sorts every unfinished item
                    # before the completed section. Keep those items pending.
                    completed=ALLOWED-{'DIMENSION MISSION','DISPATCH 7-1','ZOMBIE SURVIVAL'}-self.board_check_unfinished
                    for mode in sorted(completed-self.queue_engine.completed):self.record_completed(mode,observed,now)
                    self.log('Remembered completed board content from the verified unfinished-first list until reset')
                self.finish_daily_board_check('completed section reached; skipping the remaining completed pages');return
            if signature in self.board_check_signatures:
                self.finish_daily_board_check('all visible pages checked; continuing unfinished tasks');return
            self.board_check_signatures.add(signature)
            click_game_point(self.handle,1000,500,scroll=('down',4),guard=guard);self.queue_wake=now+timedelta(seconds=3);return
        if evidence.screen in ('game_home','we_home','gbr_main'):click((1249,36));return
        if evidence.screen=='navigation_menu':click((630,642));return
        if evidence.screen=='status_board':self.queue_wake=now+timedelta(seconds=2);return
        if evidence.values.get('menu_available'):click((1249,36));return
        if evidence.values.get('home_available'):click((1185,36));return
        self.queue_wake=now+timedelta(seconds=3)
