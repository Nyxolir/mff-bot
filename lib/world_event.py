"""World Event visual evidence and daily/slot state, independent of energy farming."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from lib.app_paths import data_path
import json,re
import cv2
import numpy as np
from PIL import Image
from lib.anchor_match import anchor_scores
from lib.mission_reader import viewport,read_fields,canonical,BoardReader
from lib.screen_reader import ScreenEvidence,ScreenReader,number
from lib.farming import parse_counter
from lib.daily_queue import reset_period,next_reset
ROOT=Path(__file__).resolve().parents[1]
CACHE=data_path('settings/gui/world-event.json')

def event_delay(text):
    match=re.search(r'(\d+)\s*h(?:\s*(\d+)\s*m)?|(\d+)\s*m',text,re.I)
    if not match:return 300
    return max(60,int(match[1] or 0)*3600+int(match[2] or match[3] or 0)*60)

class WorldEventReader:
    def read(self,source):
        image=viewport(source)
        def matches(name,box):
            ref=Image.open(ROOT/f'images/current/{name}.png').convert('RGB')
            if name in ('we_score_label','we_ready_title','we_battle_auto','we_battle_auto_1080'):
                # Label glyphs are identical in ADB captures; background lighting varies.
                def letters(p):return ((p.min(2)>140)&(p.max(2).astype('int16')-p.min(2)<40)).astype('uint8')
                x1,y1,x2,y2=box
                actual=np.asarray(image.crop((x1-2,y1-2,x2+2,y2+2)))
                return cv2.matchTemplate(letters(actual),letters(np.asarray(ref)),cv2.TM_CCOEFF_NORMED).max()>.96
            score,error=anchor_scores(image,ref,box)
            return score>.96 and error<15
        if matches('we_confirm_title',(480,172,805,213)):
            text=read_fields(image,[('entries',(695,363,744,400),'white_number'),('ok',(680,489,817,533),'button_text')])
            if canonical(text['ok'])!='OK':return ScreenEvidence(errors=['World Event confirmation OK unreadable'],text=text)
            try:entries=parse_counter(text['entries']);assert entries[1]==2
            except (ValueError,AssertionError):return ScreenEvidence(errors=['World Event confirmation entries unreadable'])
            return ScreenEvidence('we_confirm',{'entries':entries,'point':(748,512)},text)
        if matches('we_battle_auto',(438,660,540,689)) or matches('we_battle_auto_1080',(438,660,540,689)):
            box=np.asarray(image.crop((384,658,413,688)))
            checked=((box[:,:,2]>150)&(box[:,:,1]>100)&(box[:,:,0]<80)).sum()>200
            return ScreenEvidence('we_battle',{'auto_on':bool(checked)})
        if matches('we_result_home',(531,620,568,658)):
            heading=read_fields(image,[('heading',(528,53,763,112),'text')])
            if canonical(heading['heading'])=='ENDBATTLE':
                return ScreenEvidence('we_result',{'point':(550,638)},heading)
        text=read_fields(image,[('title',(67,18,335,52),'text')])
        title=canonical(text['title'])
        if title=='CONTENTSTATUSBOARD':return BoardReader().read(image)
        if title.startswith('WORLDEVENT') and matches('we_score_label',(865,270,970,295)):
            text.update(read_fields(image,[('score',(1144,268,1238,295),'white_number'),
                ('entries',(728,671,782,706),'color_number'),('timer',(31,654,335,687),'text')]))
            try:entries=parse_counter(text['entries']);score=number(text['score']);assert entries[1]==2
            except (ValueError,AssertionError):return ScreenEvidence(errors=['World Event daily entries/score unreadable'],text=text)
            ready=matches('we_lobby_ready',(970,650,1135,690))
            return ScreenEvidence('we_lobby',{'entries':entries,'best_score':score,'available':ready,'delay':event_delay(text['timer']),'point':(1040,674)},text)
        if title.startswith('READY') or matches('we_ready_title',(69,19,145,50)):
            setup=read_fields(image,[('caption',(18,653,600,676),'yellow_text'),('button',(970,650,1110,690),'button_text')])
            if canonical(setup['caption'])=='SELECTEDTEAMANDCHARACTERSCANBEUSEDINTHEWORLDEVENT':
                if canonical(setup['button'])=='READY':return ScreenEvidence('we_team',{'point':(1034,674)},setup)
                if canonical(setup['button'])=='START':return ScreenEvidence('we_start',{'point':(1034,674)},setup)
        if title.startswith('READY') and matches('we_team_footer',(19,654,560,697)):
            if matches('we_team_start',(970,650,1110,690)):
                return ScreenEvidence('we_start',{'point':(1034,674)})
            if matches('we_team_ready',(970,650,1110,690)):
                return ScreenEvidence('we_team',{'point':(1034,674)})
        # Closed slots are read without authorizing an entry. Unknown layouts
        # are deferred and revisited, never treated as daily completion.
        if title.startswith('WORLDEVENT'):
            text.update(read_fields(image,[('entries',(728,671,782,706),'color_number')]))
            try:
                entries=parse_counter(text['entries'])
                if entries[1]==2:return ScreenEvidence('we_closed',{'entries':entries},text)
            except ValueError:pass
        result=ScreenReader().read(image,resource_check=True)
        if result.screen in ('unknown','game_home'):
            from lib.objective_reader import ObjectiveReader
            home=ObjectiveReader().read(image)
            if canonical(home.text.get('title',''))=='CHALLENGES' and not home.errors:
                return ScreenEvidence('challenge_navigation',{'home_available':True,'menu_available':home.values.get('menu_available',False) or result.values.get('menu_available',False)},home.text)
            if home.values.get('home_available') and not home.errors:return home
            if home.screen=='game_home':
                rows=read_fields(image,[(str(i),(927,365+i*65,1165,395+i*65),'text') for i in range(4)])
                point=next(((1040,380+i*65) for i in range(4) if canonical(rows[str(i)])=='WORLDEVENT'),None)
                return ScreenEvidence('we_home',{'event_point':point,'battle_tab':matches('we_home_battle_tab',(1003,318,1040,354))},rows)
        return result

class WorldEventState:
    def __init__(self,now):
        self.period=reset_period(now);self.done=False;self.next_check=now
        self.pending=False;self.started=False;self.slot_until=None;self.before=None
        self.zero_observations=[];self.completion_proof=None;self.cache_done_rejected=False

    def rollover(self,now):
        if self.period!=reset_period(now):self.__init__(now)

    def reset_zero_verification(self):
        self.zero_observations=[];self.completion_proof=None;self.done=False

    def lobby(self,values,now,observed=None,visit=None):
        self.rollover(now)
        remaining,total=values['entries']
        if type(total) is not int or type(remaining) is not int or total!=2 or not 0<=remaining<=2:
            raise ValueError('Invalid World Event reward counter')
        if remaining==0:
            self.done=False;self.next_check=now+timedelta(seconds=3)
            # Repeated frames from one page visit cannot confirm a cached zero.
            # The controller must leave and reopen the dedicated event page.
            valid=(observed is not None and observed.tzinfo is not None and type(visit) is int and visit>=0
                and timedelta(0)<=now-observed<=timedelta(seconds=30) and reset_period(observed)==self.period)
            if valid and not self.started:
                previous=self.zero_observations
                if (visit not in [row[0] for row in previous]
                    and (not previous or observed-previous[-1][1]>=timedelta(seconds=3))):
                    previous.append((visit,observed))
                if len(previous)>=3:
                    self.completion_proof={'source':'world_event_page',
                        'observations':[{'visit':v,'observed_at':stamp.isoformat()} for v,stamp in previous[-3:]]}
                    self.done=True;self.pending=False;self.started=False;self.next_check=next_reset(now)
                    return 'done'
            return 'recheck_zero'
        self.reset_zero_verification()
        if self.pending:
            if (self.before is not None and remaining<self.before) or values.get('best_score',0)>0:
                self.pending=False;self.started=False
            elif self.slot_until is None or now<self.slot_until:
                self.next_check=now+timedelta(minutes=5);return 'wait'
            else:self.pending=False;self.started=False
        if values.get('best_score',0)>0:
            self.next_check=min(next_reset(now),now+timedelta(seconds=values.get('delay',300)+60));return 'scored'
        if not values.get('available'):
            self.next_check=now+timedelta(minutes=5);return 'closed'
        self.before=remaining;self.slot_until=now+timedelta(seconds=values.get('delay',300)+60)
        return 'enter'

    def save(self,path=CACHE):
        data=dict(version=2,period=self.period,done=self.done,pending=self.pending,started=self.started,before=self.before,
            next_check=self.next_check.isoformat(),slot_until=self.slot_until.isoformat() if self.slot_until else None,
            completion_proof=self.completion_proof if self.done else None)
        path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.tmp')
        temp.write_text(json.dumps(data,indent=2),encoding='utf-8');temp.replace(path)

    @staticmethod
    def valid_completion_proof(proof,now):
        try:
            if proof['source']!='world_event_page':return False
            rows=proof['observations']
            if not isinstance(rows,list) or len(rows)!=3:return False
            visits=[row['visit'] for row in rows];stamps=[datetime.fromisoformat(row['observed_at']) for row in rows]
            return (all(type(v) is int and v>=0 for v in visits) and len(set(visits))==3
                and all(stamp.tzinfo is not None and stamp<=now and reset_period(stamp)==reset_period(now) for stamp in stamps)
                and all(b-a>=timedelta(seconds=3) for a,b in zip(stamps,stamps[1:])))
        except (KeyError,TypeError,ValueError,AttributeError):return False

    @classmethod
    def load(cls,now,path=CACHE):
        state=cls(now)
        try:
            d=json.loads(path.read_text(encoding='utf-8'))
            if d['version'] not in (1,2) or d['period']!=state.period:return state
            if any(type(d[k]) is not bool for k in ('done','pending','started')):return state
            due=datetime.fromisoformat(d['next_check']);slot=datetime.fromisoformat(d['slot_until']) if d['slot_until'] else None
            if due.tzinfo is None or due>next_reset(now) or (slot and slot.tzinfo is None):return state
            if d['before'] not in (None,1,2):return state
            # Preserve submission latches when invalidating an old done flag.
            state.pending=d['pending'];state.started=d['started'];state.before=d['before']
            state.next_check=due;state.slot_until=slot
            proof=d.get('completion_proof')
            if d['done'] and not d['pending'] and not d['started'] and d['version']==2 and cls.valid_completion_proof(proof,now):
                state.done=True;state.completion_proof=proof
            elif d['done']:
                state.cache_done_rejected=True;state.next_check=now
        except (OSError,ValueError,KeyError,TypeError):pass
        return state
