"""Validated Dimension and Epic ticket-sweep screens. Unknown layouts block."""
from pathlib import Path
import re
import cv2
import numpy as np
from PIL import Image
from lib.screen_reader import ScreenEvidence,ScreenReader,number
from lib.mission_reader import viewport,read_fields,canonical
from lib.farming import parse_counter

ROOT=Path(__file__).resolve().parents[1]
DIMENSION_CONTROLS={"select_max":(835,477),"clear_batch":(748,561),
    "close_sweep":(532,561),"increment":(695,477),"decrement":(450,477)}
CONTROL_POINTS={"select_max":{(835,477)},"clear_batch":{(748,561),(640,555),(408,555)},
    "close_result":{(638,676),(880,676)},"close_sweep":{(532,561),(872,555)},
    "increment":{(695,477)},"decrement":{(450,477)}}

def contribution_counter(raw):
    match=re.fullmatch(r'(\d+)\s*/\s*(\d+)',raw.strip())
    if not match or int(match[2])<=0:raise ValueError('Contribution counter unreadable')
    # Ten clears can produce 120/60: surplus progress is valid here.
    return int(match[1]),int(match[2])


class SweepReader:
    def read(self,source):
        try:image=viewport(source)
        except ValueError as error:return ScreenEvidence(errors=[str(error)])
        def matches(name,box):
            from lib.anchor_match import anchor_scores
            ref=Image.open(ROOT/f"images/current/{name}.png").convert("RGB")
            score,error=anchor_scores(image,ref,box)
            return score>.96 and error<15
        if matches('menu_heading',(431,19,539,59)) and matches('select_mission_tile',(429,598,559,692)):
            return ScreenEvidence('navigation_menu',{'select_mission':True})
        if matches("sweep_result_heading",(590,15,700,58)):
            # Dimension shares the heading/star artwork with Epic results.
            # Its centered Close, clipped mode title and contribution bar
            # identify it before the more permissive Epic control fallback.
            if matches('dimension_result_close',(521,644,756,708)):
                text=read_fields(image,[('mode_prefix',(67,18,160,52),'text'),
                    ('mode_white',(67,18,160,52),'white_text'),
                    ('contribution',(590,285,690,320),'color_number'),
                    ('clears',(193,410,317,452),'text'),('clears_bottom',(192,451,317,501),'text')])
                try:
                    contribution=contribution_counter(text['contribution'])
                    assert contribution[1]>0 and any(canonical(text[k])=='DIMENSI' for k in ('mode_prefix','mode_white'))
                    counts=[int(m[1]) for k in ('clears','clears_bottom')
                        if (m:=re.fullmatch(r'(\d+)\s*time\(s\)',text[k].strip(),re.I))]
                    assert counts and 1<=max(counts)<=100
                except (ValueError,AssertionError):return ScreenEvidence(errors=['Dimension result identity/count unreadable'],text=text)
                return ScreenEvidence('sweep_result',{'mode':'DIMENSION MISSION','result_verified':True,
                    'clears':max(counts),'contribution':contribution,'controls':{'close_result':(638,676)}},text)
            from lib.epic_sweep import read_epic_result
            epic=read_epic_result(image,matches)
            if epic is not None:return epic
            if not matches('dimension_result_close',(521,644,756,708)):
                return ScreenEvidence(errors=['Sweep result layout not verified'])
            text=read_fields(image,[("clears",(193,410,317,452),"text")])
            match=re.fullmatch(r"(\d+)\s*time\(s\)",text["clears"].strip(),re.I)
            if not match:return ScreenEvidence(errors=["Sweep result count unreadable"],text=text)
            return ScreenEvidence("sweep_result",{"result_verified":True,"clears":int(match[1]),"controls":{"close_result":(638,676)}},text)
        text=read_fields(image,[("title",(67,18,335,52),"text")])
        if canonical(text['title']) not in ('MISSIONPREPARATION','DIMENSIONMISSION','CONTENTSTATUSBOARD'):
            text['title']=read_fields(image,[("title",(67,18,335,52),"white_text")])['title']
        if canonical(text['title']) not in ('MISSIONPREPARATION','DIMENSIONMISSION','CONTENTSTATUSBOARD'):
            narrow=read_fields(image,[('title',(67,18,282,52),'text')])['title']
            if canonical(narrow)=='DIMENSIONMISSION':text['title']=narrow
        result=ScreenEvidence(text=text)
        if canonical(text['title'])=='CONTENTSTATUSBOARD':
            from lib.mission_reader import BoardReader
            return BoardReader().read(image)
        if canonical(text["title"])=="MISSIONPREPARATION":
            from lib.epic_sweep import read_epic
            return read_epic(image,text["title"],matches)
        if canonical(text["title"])!="DIMENSIONMISSION":return ScreenReader().read(image,resource_check=True)
        result.values["mode"]="DIMENSION MISSION"
        receipt=read_fields(image,[('heading',(520,125,760,163),'text'),('body',(449,199,901,334),'block'),
            ('ok',(555,510,725,563),'text')])
        if canonical(receipt['heading'])=='ACQUIRED' and canonical(receipt['ok'])=='OK' and 'ACQUIRED' in canonical(receipt['body']):
            return ScreenEvidence('dimension_contribution_receipt',{'mode':'DIMENSION MISSION','point':(640,537)},dict(text,**receipt))
        # Gold rewards use a taller Acquired popup than item rewards.
        # Its body and OK are lower; keep the old item layout above intact.
        gold=read_fields(image,[('gold_body',(450,395,835,438),'white_text'),('gold_ok',(555,536,725,593),'text')])
        if (canonical(receipt['heading'])=='ACQUIRED' and canonical(gold['gold_ok'])=='OK'
                and re.fullmatch(r'[0-9,]+\s+Gold\s+acquired!',gold['gold_body'].strip(),re.I)):
            return ScreenEvidence('dimension_contribution_receipt',{'mode':'DIMENSION MISSION','point':(640,565),'receipt_kind':'gold'},dict(text,**receipt,**gold))
        modal=read_fields(image,[('modal',(476,45,815,89),'text')])['modal']
        if canonical(modal)=='CONTRIBUTIONREWARD':
            labels=read_fields(image,[('close',(442,612,636,673),'button_text'),('acquire',(644,612,838,673),'button_text')])
            if canonical(labels['close'])=='CLOSE' and canonical(labels['acquire'])=='ACQUIREALL':
                pixels=np.asarray(image.crop((650,615,832,667))).astype('int16')
                ready=((pixels[:,:,2]>150)&(pixels[:,:,1]>90)&(pixels[:,:,0]<80)).mean()>.35
                return ScreenEvidence('dimension_contribution',{'mode':'DIMENSION MISSION','acquire_ready':bool(ready),
                    'acquire_point':(741,643),'close_point':(538,643)},dict(text,modal=modal,**labels))
            return ScreenEvidence(errors=['Dimension contribution controls unreadable'])
        if matches("dimension_hidden_question",(428,288,850,354)):
            result.screen="sweep_hidden";result.values["point"]=(538,538);return result
        if matches("dimension_sweep_button",(523,654,634,691)):
            result.screen="sweep_preparation";result.values["point"]=(579,673);return result
        if matches("dimension_ready_button",(490,642,790,706)):
            result.screen="dimension_lobby";result.values["point"]=(640,673)
            raw=read_fields(image,[("contribution",(1076,665,1145,696),"color_number")])["contribution"]
            try:result.values["contribution"]=contribution_counter(raw)
            except ValueError:pass
            return result
        if not matches("sweep_heading",(590,121,700,166)):return result
        result.screen="sweep"
        fields=[("selected",(540,459,610,496),"number"),
            ("boost_unit",(1040,610,1080,639),"number"),
            ("boost_available",(950,19,995,49),"color_number")]
        text.update(read_fields(image,fields))
        try:
            if not matches("sweep_boost_notice",(444,315,838,349)):
                raise ValueError("Sweep boost notice not verified")
            def cost(key):
                raw=text[key].strip()
                if not re.fullmatch(r"-?\d+",raw):raise ValueError("Sweep cost unreadable: "+key)
                return abs(int(raw))
            selected=number(text["selected"])
            result.values.update(selected=selected,
                boost_total=cost("boost_unit")*selected,boost_available=number(text["boost_available"]),
                crystal_total=0,boosted=True,sweep_verified=True,
                controls=dict(DIMENSION_CONTROLS))
        except ValueError as error:result.errors.append(str(error))
        return result
