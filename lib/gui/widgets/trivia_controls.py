"""Daily Trivia GUI action, separate from the energy-spending queue."""
from datetime import datetime,timedelta,timezone
from PyQt5 import QtCore
from lib.trivia_session import TriviaSession
from lib.resource_check import click_game_point
from lib.daily_queue import reset_period,next_reset
from pathlib import Path
from lib.app_paths import data_path
import json
TRIVIA_CACHE=data_path('settings/gui/trivia-daily.json')

class TriviaControls:
    def trivia_due(self,now):
        return self.trivia_period!=reset_period(now) and now>=self.trivia_retry_at

    def init_trivia(self):
        self.trivia_active=False;self.trivia_observation=None;self.trivia_session=None
        self.trivia_waiting=None
        self.trivia_period=None;self.trivia_retry_at=datetime.now(timezone.utc)
        try:
            saved=json.loads(TRIVIA_CACHE.read_text(encoding='utf-8'))
            if saved.get('period')==reset_period(datetime.now(timezone.utc)):
                if saved.get('done') is True:self.trivia_period=saved['period']
                elif saved.get('retry_at'):
                    retry=datetime.fromisoformat(saved['retry_at']);now=datetime.now(timezone.utc)
                    if retry.tzinfo and now<retry<=next_reset(now):self.trivia_retry_at=retry
        except (OSError,ValueError):pass

    def check_trivia(self,automatic=False):
        if automatic and not self.trivia_due(datetime.now(timezone.utc)):return
        if self.trivia_active:self.finish_trivia('Trivia check cancelled');return
        if self.busy or self.resource_active or self.objective_active or (self.queue_engine.running and not automatic):
            self.log('Stop the queue or wait for the active check before Daily Trivia');return
        if not self.handle:self.connect_emulator()
        if not self.handle:return
        if automatic:
            # Only called at an unsubmitted task boundary. Revisit the board
            # after trivia instead of retaining an obsolete mission screen.
            self.queue_target=None;self.queue_waiting=None;self.epic_preparation=None
            self.queue_observation=None;self.queue_wake=None;self.queue_phase='navigate_board'
            if self.board_check_active:self.board_check_active=False;self.board_check_due=True
        self.trivia_active=True;self.trivia_observation=None;self.trivia_waiting=None
        self.trivia_session=TriviaSession(datetime.now(timezone.utc))
        self.daily_trivia_button.setText('Cancel Trivia')
        self.log('Daily Trivia: local answer bank checked against the supplied Quizlet set. Unknown answers are never guessed.')
        self.scan_live()

    def finish_trivia(self,error=None):
        self.trivia_active=False;self.trivia_waiting=None
        self.daily_trivia_button.setText('Daily Trivia')
        now=datetime.now(timezone.utc)
        self.trivia_retry_at=next_reset(now) if self.trivia_period==reset_period(now) else now+timedelta(minutes=2)
        if error:self.log('Daily Trivia: '+error,True)
        else:
            self.log(self.trivia_session.message)
            if self.trivia_session.done:
                self.trivia_period=reset_period(now);self.trivia_retry_at=next_reset(now)
        try:
            temporary=TRIVIA_CACHE.with_suffix('.tmp')
            done=self.trivia_period==reset_period(now)
            temporary.write_text(json.dumps({'version':1,'period':reset_period(now),'done':done,
                'verified_questions':5 if done else 0,'checked_at':now.isoformat(),
                'expires_at':next_reset(now).isoformat(),'retry_at':self.trivia_retry_at.isoformat()}),encoding='utf-8')
            temporary.replace(TRIVIA_CACHE)
        except OSError as failure:self.log('Could not save trivia status: '+str(failure),True)
        if self.queue_engine.running:self.queue_wake=None

    def trivia_rescan(self):
        if self.trivia_active and not self.busy:self.scan_live()

    def advance_trivia(self):
        if not self.trivia_active or not self.trivia_observation:return
        evidence,captured=self.trivia_observation;now=datetime.now(timezone.utc)
        try:
            if not timedelta(0)<=now-captured<=timedelta(seconds=30):raise ValueError('Trivia screenshot expired')
            if self.trivia_waiting:
                expected,started=self.trivia_waiting
                if evidence.screen not in expected:
                    if now-started>timedelta(seconds=25):raise ValueError('Trivia navigation did not complete')
                    QtCore.QTimer.singleShot(2000,self.trivia_rescan);return
                self.trivia_waiting=None
            action=self.trivia_session.observe(evidence,now)
            for row in evidence.values.get('rows',[]):
                self.log('Trivia: '+row['question']+' → '+(row['answer'] or 'unknown')+(' (already answered)' if row['answered'] else ''))
            if action is None:self.finish_trivia();return
            kind,x,y=action
            if kind!='wait':
                if (x,y)==(844,126):self.trivia_waiting=(('daily_objectives',),now)
                elif (x,y)==(1249,37):self.trivia_waiting=(('trivia_menu',),now)
                elif (x,y)==(1195,390):self.trivia_waiting=(('daily_objectives',),now)
                elif (x,y)==(786,113):self.trivia_waiting=(('trivia_start','trivia_list','trivia_question'),now)
                elif evidence.screen=='trivia_start':self.trivia_waiting=(('trivia_list','trivia_question'),now)
                elif (x,y)==(1185,36):self.trivia_waiting=(('game_home',),now)
                click_game_point(self.handle,x,y,scroll=(kind,8 if kind=='up' else 4) if kind in ('up','down') else None,
                    guard=lambda:self.trivia_active and timedelta(0)<=datetime.now(timezone.utc)-captured<=timedelta(seconds=30))
            QtCore.QTimer.singleShot(2500,self.trivia_rescan)
        except Exception as error:self.finish_trivia(str(error))
