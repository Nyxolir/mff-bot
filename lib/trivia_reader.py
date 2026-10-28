"""Current Daily Trivia list reader. Unknown answer dialogs never get guessed clicks."""
import cv2
import re
import numpy as np
from lib.mission_reader import viewport,read_fields,canonical
from lib.screen_reader import ScreenEvidence
from lib.trivia import lookup_answer,normalize

class TriviaReader:
    def read(self,source):
        image=viewport(source)
        text=read_fields(image,[('title',(67,18,365,52),'text'),
            ('tab',(680,92,897,132),'text'),('heading',(58,161,180,187),'text')])
        if canonical(text['title'])!='CHALLENGES' or canonical(text['heading'])!='DAILYTRIVIA':
            from lib.objective_reader import ObjectiveReader
            result=ObjectiveReader().read(image)
            if result.screen=='objective_menu':return ScreenEvidence('trivia_menu',result.values,result.text)
            if result.screen=='unknown':
                nav=read_fields(image,[('menu',(465,18,560,58),'white_text'),
                    ('challenges',(1130,400,1260,436),'text')])
                if canonical(nav['menu'])=='MENU' and canonical(nav['challenges'])=='CHALLENGES':
                    return ScreenEvidence('trivia_menu',text=nav)
                if (canonical(result.text.get('home_daily','')) in {'SPECIALBENEFITS','PECIALBENEFITS'} and
                    canonical(result.text.get('home_benefits',''))=='TODAYSGIFT'):
                    return ScreenEvidence('game_home',{'daily_shortcut_missing':True},result.text)
                if not result.errors and (result.values.get('menu_available') is True or result.values.get('home_available') is True):
                    # A known navigation control on another mission page is
                    # usable even when its content is outside the quiz reader.
                    # Keep unrecognized quiz questions/results on their own
                    # guarded path; this authorizes navigation, never answers.
                    return ScreenEvidence('challenge_navigation',result.values,result.text)
            if (result.screen in ('daily_objectives','challenges_other_tab') and result.errors
                    and canonical(text['title'])=='CHALLENGES' and canonical(text['tab'])=='DAILYTRIVIA'):
                # Objective counters are unrelated to the independently
                # identified Trivia tab. Do not require their progress OCR.
                return ScreenEvidence(result.screen,result.values,result.text)
            if (result.screen not in ('game_home','daily_objectives','challenges_other_tab')
                    and (result.values.get('menu_available') is True or result.values.get('home_available') is True)):
                return ScreenEvidence('challenge_navigation',
                    {k:True for k in ('menu_available','home_available') if result.values.get(k) is True},result.text)
            return result
        from pathlib import Path
        from PIL import Image
        from lib.anchor_match import anchor_scores
        ring_box=(553,91,728,272)
        ring=Image.open(Path(__file__).resolve().parents[1]/'images/current/trivia_correct_ring.png').convert('RGB')
        score,error=anchor_scores(image,ring,ring_box)
        if score>.96 and error<15:
            modal=read_fields(image,[('answer',(440,296,842,333),'yellow_text'),
                ('energy',(560,438,820,478),'white_text'),('close',(590,553,692,593),'text')])
            match=re.fullmatch(r'Answer:\s*([1-4])\.\s*(.+)',modal['answer'].strip(),re.I)
            if match and canonical(modal['energy'])=='10ENERGYACQUIRED' and canonical(modal['close'])=='CLOSE':
                return ScreenEvidence('trivia_correct',dict(result_verified=True,answer=match[2],close_point=(640,575)),modal)
        score,error=anchor_scores(image,Image.open(Path(__file__).resolve().parents[1]/'images/current/trivia_start_button.png').convert('RGB'),(828,574,1172,637))
        if canonical(text['tab'])=='DAILYTRIVIA' and score>.97 and error<12:
            intro=read_fields(image,[('begin',(300,433,730,485),'text'),('start',(920,581,1080,628),'button_text')])
            text.update(intro)
            if canonical(intro['begin'])=='BEGINTODAYSTRIVIAQUIZ' and canonical(intro['start'])=='START':
                return ScreenEvidence('trivia_start',{'point':(1000,606)},text)
        if canonical(text['tab'])=='DAILYTRIVIA':
            ys=(294,385,475,566)
            fields=[('progress',(138,294,430,334),'yellow_text'),
                ('question',(145,349,750,481),'white_block'),('reward',(173,492,295,518),'text')]
            for i,y in enumerate(ys):
                fields.extend([(f'option{i}',(895,y+6,1167,y+59),'white_text'),
                    (f'number{i}',(843,y+7,877,y+56),'blue_number')])
            q=read_fields(image,fields);text.update(q)
            progress=re.fullmatch(r'TODAYSTRIVIA([1-5S])[5S]',canonical(q['progress']))
            if progress is None:
                parts=read_fields(image,[('caption',(138,294,310,334),'yellow_text'),('count',(312,294,375,334),'yellow_number')])
                text.update(parts)
                if canonical(parts['caption'])=='TODAYSTRIVIA':progress=re.fullmatch(r'([1-5])/5',parts['count'].strip())
            if (progress and canonical(q['reward'])=='BASICREWARD' and len(normalize(q['question']))>=18
                    and all(q[f'number{i}'].strip()==str(i+1) and q[f'option{i}'].strip() for i in range(4))):
                return ScreenEvidence('trivia_question',dict(layout_verified=True,question=' '.join(q['question'].split()),
                    options=[q[f'option{i}'].strip() for i in range(4)],points=[(1030,y+31) for y in ys],
                    question_number=int(progress[1].replace('S','5')),total=5),text)
        pixels=np.asarray(image)
        # Both disabled (answered) and enabled blue ANSWER buttons. Locate row
        # boundaries from their actual rectangles, including vertically scrolled rows.
        area=pixels[200:710,65:257]
        mask=((area[:,:,2].astype('int16')-area[:,:,0]>35)&(area[:,:,2]>60)&
            (area[:,:,1].astype('int16')-area[:,:,0]>10)).astype('uint8')*255
        contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        boxes=[]
        for contour in contours:
            x,y,w,h=cv2.boundingRect(contour)
            if 165<=w<=190 and 28<=h<=45 and 200+y>=250 and 200+y+h<=710:
                boxes.append((x+65,y+200,w,h))
        boxes.sort(key=lambda b:b[1])
        fields=[]
        for i,(x,y,w,h) in enumerate(boxes):
            fields.extend([(f'q{i}',(70,y-51,1210,y-6),'text'),
                (f'a{i}',(265,y,800,y+h),'text'),
                (f'label{i}',(x+w//2-48,y+4,x+w//2+50,y+h-4),'text')])
        rows_text=read_fields(image,fields) if fields else {}
        text.update(rows_text);rows=[]
        for i,(x,y,w,h) in enumerate(boxes):
            question=text[f'q{i}'].strip();displayed=text[f'a{i}'].strip()
            gold=pixels[y:y+h,265:1200]
            gold_count=((gold[:,:,0]>170)&(gold[:,:,1]>120)&(gold[:,:,2]<100)).sum()
            if len(question)<18:continue
            rows.append({'question':question,'answer':lookup_answer(question),
                'displayed_answer':displayed,'answered':bool(gold_count>15),
                'point':(x+w//2,y+h//2)})
        if not rows:return ScreenEvidence('trivia_unknown',text=text,errors=['Trivia question layout not verified'])
        # The question-and-answer summary appears only after the daily quiz is done.
        # One verified visible summary suffices; no need to expose all five rows.
        completed=(canonical(text['heading'])=='DAILYTRIVIA' and all(r['answered'] for r in rows)
            and any(canonical(rows_text.get(f'label{i}',''))=='ANSWER' and rows_text.get(f'a{i}','').strip()
                and len(rows_text.get(f'q{i}','').strip())>=18 for i in range(len(boxes))))
        return ScreenEvidence('trivia_list',{'rows':rows,'completed_summary_verified':completed,'signature':'|'.join(normalize(r['question']) for r in rows)},text)
