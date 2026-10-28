"""Bounded Daily Trivia navigation and answer decisions, without an input API."""
from datetime import timedelta
from lib.trivia import normalize,choose_option,answer_key
from lib.daily_queue import reset_period

class TriviaSession:
    def __init__(self,now):
        self.started=now;self.period=reset_period(now);self.actions=0
        self.rows={}
        self.done=False;self.message='';self.pending=None;self.pending_answer=None;self.closed=False;self.start_clicked=False
        self.unrecognized_since=None
        self.pending_number=None

    def observe(self,evidence,now):
        if reset_period(now)!=self.period:raise ValueError('Daily reset crossed; restart Daily Trivia')
        if now-self.started>timedelta(minutes=3) or self.actions>=24:raise ValueError('Trivia inspection timed out')
        screen=evidence.screen;values=evidence.values
        if screen in ('trivia_unknown','unknown'):
            if self.unrecognized_since is None:self.unrecognized_since=now
            if now-self.unrecognized_since<=timedelta(seconds=20):return self.action(('wait',0,0))
            raise ValueError('Trivia screen did not settle within 20 seconds; no answer retried')
        self.unrecognized_since=None
        if evidence.errors:raise ValueError('; '.join(evidence.errors))
        if screen=='trivia_start':
            if self.start_clicked:return self.action(('wait',0,0))
            self.start_clicked=True;return self.action(('click',*values['point']))
        if screen=='trivia_list':
            rows=values.get('rows',[])
            if (values.get('completed_summary_verified') is not True or not rows
                    or not all(r.get('answered') for r in rows)
                    or not any(r.get('displayed_answer') for r in rows)):
                raise ValueError('Daily Trivia completed summary not verified')
            self.rows={normalize(row['question']):row for row in rows}
            self.pending=None;self.pending_answer=None;self.pending_number=None
            self.done=True;self.message='Daily Trivia completed question-and-answer summary verified'
            return None
        if screen=='trivia_question':
            if not values.get('layout_verified'):raise ValueError('Trivia answer controls need live validation')
            token=normalize(values['question'])
            if self.pending and not self.closed:return self.action(('wait',0,0))
            if self.pending_number is not None and values.get('question_number')==self.pending_number:
                return self.action(('wait',0,0))
            if self.pending==token:return self.action(('wait',0,0))
            index=choose_option(values['question'],values['options'])
            if index is None:raise ValueError('Unknown or ambiguous trivia question/options; no answer submitted')
            self.pending=token;self.closed=False
            self.pending_number=values.get('question_number')
            self.pending_answer=values['options'][index]
            return self.action(('answer',*values['points'][index]))
        if screen=='trivia_correct' and (self.pending or values.get('result_verified') is True):
            if (self.pending_answer and values.get('result_verified') is True and
                    answer_key(values.get('answer',''))!=answer_key(self.pending_answer)):
                raise ValueError('Trivia result does not match the submitted answer; stopped')
            if self.closed:return self.action(('wait',0,0))
            self.closed=True;return self.action(('click',*values['close_point']))
        if screen=='trivia_incorrect':raise ValueError('Trivia result was incorrect; stopped')
        if self.pending:raise ValueError('Answer outcome not verified; no retry')
        if screen=='game_home':
            return self.action(('click',*values['daily_point']) if values.get('daily_point') else ('click',1249,37) if values.get('daily_shortcut_missing') else ('click',844,126))
        if screen=='trivia_menu':return self.action(('click',1195,390))
        if screen in ('daily_objectives','challenges_other_tab'):return self.action(('click',786,113))
        if values.get('menu_available'):return self.action(('click',1249,37))
        if values.get('home_available'):return self.action(('click',1185,36))
        raise ValueError('Daily Trivia screen not recognized; open Challenges → Daily Trivia')

    def action(self,value):
        if value[0]!='wait':self.actions+=1
        return value
