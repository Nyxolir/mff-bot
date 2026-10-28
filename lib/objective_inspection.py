"""Bounded, reset-aware challenge inspection state machine. No input API."""
from dataclasses import replace
from datetime import timedelta
from lib.objectives import ObjectiveLedger,excluded_event
from lib.daily_queue import reset_period


class ObjectiveInspection:
    def __init__(self,now):
        self.started=now;self.period=reset_period(now)
        self.phase="daily";self.source="Daily Challenges"
        self.daily=[];self.ledger=ObjectiveLedger()
        self.events=None;self.visited=set();self.previous=None;self.scrolls=0
        self.same_count=0
        self.max_level_passes=set()
        self.quest=[];self.quest_present=False;self.quest_top=False
        self.quest_missing_last=None;self.quest_missing_count=0
        self.done=False;self.plan=None;self.actions=0

    def observe(self,evidence,now):
        if reset_period(now)!=self.period:raise ValueError("Reset crossed; inspect objectives again")
        if now-self.started>timedelta(minutes=5) or self.actions>45:raise ValueError("Objective inspection timed out")
        if evidence.errors:raise ValueError("; ".join(evidence.errors))
        screen=evidence.screen
        action=None
        if (self.phase=='event' and screen in ('event_rewards','event_objectives')
                and evidence.values.get('pass_max_level_verified') is True):
            from lib.mission_reader import canonical
            if canonical(evidence.values.get('pass_title',''))!=canonical(self.source):
                raise ValueError('Maximum-level pass title does not match the selected event')
            self.ledger.finish_max_level_pass(self.source);self.visited.add(self.source)
            self.max_level_passes.add(self.source)
            self.phase='benefits';self.previous=None;self.scrolls=0;self.same_count=0
            self.actions+=1;return ('home',1185,36)
        if screen=="benefit_list" and self.phase!="benefits":return ("click",640,593)
        if self.phase=='quest' and screen=='event_quest_objectives' and not self.quest_top:
            self.quest_top=True;self.actions+=1;return ('scroll_up',800,550)
        if self.phase in ("daily","event","quest") and screen in ("daily_objectives","event_objectives","event_quest_objectives"):
            expected={'daily':'daily_objectives','event':'event_objectives','quest':'event_quest_objectives'}[self.phase]
            if screen!=expected:return ("home",1185,36)
            rows=[replace(row,source=self.source) for row in evidence.values.get("objectives",[])]
            if self.phase=="daily":self.daily.extend(rows)
            elif self.phase=='quest':self.quest.extend(rows)
            else:self.ledger.observe(self.source,rows)
            signature=evidence.values.get("signature")
            if not signature:raise ValueError("Objective list unreadable")
            self.same_count=self.same_count+1 if signature==self.previous and self.scrolls else 0
            if self.same_count>=2 or (self.phase in ('quest','event') and evidence.values.get('completed_tail_verified') is True):
                if self.phase=="event":
                    self.ledger.finish(self.source);self.visited.add(self.source)
                self.phase='quest_home' if self.phase=='daily' else 'benefits';self.previous=None;self.scrolls=0;self.same_count=0
                action=("home",1185,36)
            else:
                self.previous=signature;self.scrolls+=1
                if self.scrolls>8:raise ValueError("Could not verify the end of the objective list")
                action=("scroll",800,550)
        elif self.phase=='daily' and screen=='challenges_other_tab':action=('click',*evidence.values['daily_tab_point'])
        elif self.phase=='daily' and screen=='objective_menu':action=('click',*evidence.values['challenges_point'])
        elif self.phase=='quest_home' and screen=='game_home':
            point=evidence.values.get('event_quest_point')
            if point:
                self.quest_present=True;self.phase='quest';self.source='Event Quest';action=('click',*point)
            else:
                # Home shortcuts can be missing on a transition frame. Require
                # three spaced reads before treating this optional event absent.
                if self.quest_missing_last is None or now-self.quest_missing_last>=timedelta(seconds=3):
                    self.quest_missing_last=now;self.quest_missing_count+=1
                if self.quest_missing_count<3:return ('wait',0,0)
                self.phase='benefits';return self.observe(evidence,now)
        elif self.phase=="daily" and screen=="game_home":
            point=evidence.values.get('daily_point')
            action=('click',*point) if point else ('click',1249,37)
        elif self.phase in ('benefits','event') and screen=="game_home":
            if self.phase=='event':
                self.phase='benefits';self.previous=None;self.scrolls=0;self.same_count=0
            point=evidence.values.get('benefits_point')
            if not point:raise ValueError('Special Benefits shortcut not located on current home screen; no guessed tap')
            action=('click',*point)
        elif self.phase=="benefits" and screen=="benefit_list":
            entries=[entry for entry in evidence.values["events"] if not excluded_event(entry["name"])]
            if self.events is None:
                self.events={entry["name"] for entry in entries}
                self.ledger.begin(now,self.events|({'Event Quest'} if self.quest_present else set()))
                self.ledger.observe("Daily Challenges",self.daily);self.ledger.finish("Daily Challenges")
                if self.quest_present:self.ledger.observe('Event Quest',self.quest);self.ledger.finish('Event Quest')
            elif self.events!={entry["name"] for entry in entries}:
                raise ValueError("Active event list changed; inspect again")
            pending=next((entry for entry in entries if entry["name"] not in self.visited),None)
            if pending:
                self.source=pending["name"];self.phase="event"
                action=("click",*pending["point"])
            else:
                self.plan=self.ledger.plan(now);self.done=True
                return None
        elif self.phase=="event" and screen=="event_rewards":action=("click",1110,181)
        elif self.phase=='daily' and evidence.values.get('menu_available'):action=('menu',1249,37)
        elif evidence.values.get("home_available") or screen in ("daily_objectives","event_objectives","event_rewards"):
            action=("home",1185,36)
        elif screen=="game_home":action=('click',*(evidence.values.get('daily_point') or (1249,37)))
        else:raise ValueError("Objective navigation screen not recognized")
        self.actions+=1
        return action
