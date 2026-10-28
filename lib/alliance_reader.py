"""Normal-only Alliance Battle evidence; no Extreme/Legend start is defined."""
from pathlib import Path
import re
import cv2
import numpy as np
from PIL import Image
from lib.mission_reader import viewport,read_fields,canonical
from lib.screen_reader import ScreenEvidence,number
from lib.farming import parse_counter

ROOT=Path(__file__).resolve().parents[1]


class AllianceReader:
    def read(self,source):
        try:image=viewport(source)
        except ValueError as error:return ScreenEvidence(errors=[str(error)])
        def matches(name,box):
            from lib.anchor_match import anchor_scores
            ref=Image.open(ROOT/f"images/current/{name}.png").convert("RGB")
            score,error=anchor_scores(image,ref,box)
            return score>.96 and error<15
        if matches("alliance_result_heading",(442,62,840,112)):
            text=read_fields(image,[("score",(798,203,982,257),"number")])
            try:score=number(text["score"])
            except ValueError:return ScreenEvidence(errors=["Alliance result score unreadable"])
            return ScreenEvidence("alliance_result",{"score":score,"result_verified":True,"home_point":(986,663)},text)
        def white_letters(p):
            return ((p.min(axis=2)>160)&((p.max(axis=2).astype('int16')-p.min(axis=2))<30)).astype('uint8')
        auto_ref=np.asarray(Image.open(ROOT/"images/current/alliance_auto_label.png").convert("RGB"))
        auto_actual=np.asarray(image.crop((424,659,535,687)))
        if cv2.matchTemplate(white_letters(auto_actual),white_letters(auto_ref),cv2.TM_CCOEFF_NORMED)[0,0]>.93:
            box=np.asarray(image.crop((384,658,413,688)))
            checked=((box[:,:,2]>150)&(box[:,:,1]>100)&(box[:,:,0]<80)).sum()>200
            return ScreenEvidence("alliance_battle_auto",{"auto_on":bool(checked)})
        text=read_fields(image,[("title",(67,18,335,52),"text"),
            ("ready_variant",(17,128,130,155),"text"),
            ("setup_variant",(180,189,300,222),"text"),
            ("normal_card",(1040,225,1168,263),"text"),
            ("extreme_card",(1040,360,1170,398),"text"),
            ("legend_card",(1040,497,1170,535),"text"),
            ("auto_label",(424,656,567,690),"text")])
        # The weekly Relay/Infinite Challenge screen replaces Normal Battle.
        # Four independent labels identify it without using the animated boss.
        weekly=read_fields(image,[('weekly_title',(67,18,258,52),'text'),
            ('relay_heading',(14,88,280,125),'yellow_text'),
            ('infinite_card',(1010,226,1210,260),'text'),
            ('relay_tab',(1060,150,1190,181),'text')])
        if all(canonical(weekly[key])==expected for key,expected in (
            ('weekly_title','ALLIANCEBATTLE'),('relay_heading','RELAYBOSSBATTLE'),
            ('infinite_card','INFINITECHALLENGE'),('relay_tab','RELAYBATTLE'))):
            return ScreenEvidence('alliance_weekly_skip',
                {'mode':'ALLIANCE BATTLE','weekly_variant':'INFINITE CHALLENGE',
                 'weekly_skip_verified':True,'home_point':(1185,36)},dict(text,**weekly))
        result=ScreenEvidence(text=text)
        if canonical(text["title"])=="ALLIANCEBATTLE":
            setup_verified=False
            if canonical(text['setup_variant'])=='NORMAL':
                setup_verified=matches('alliance_normal_start_button',(850,653,1106,698))
                if not setup_verified:
                    current=read_fields(image,[('start_label',(850,653,1106,698),'button_text'),
                        ('select_characters',(620,106,1040,149),'white_text')])
                    text.update(current)
                    setup_verified=(canonical(current['start_label'])=='NORMALMODESTART' and
                        canonical(current['select_characters'])=='SELECTCHARACTERS')
            if canonical(text["ready_variant"])=="NORMAL" and matches("alliance_normal_ready_button",(900,653,1169,698)):
                raw=read_fields(image,[("entries",(1180,657,1245,698),"button_number")])["entries"]
                result.screen="alliance_normal_ready"
                box=(1080,672)
            elif canonical(text["setup_variant"])=="NORMAL" and setup_verified:
                raw=read_fields(image,[("entries",(1130,657,1185,698),"button_number")])["entries"]
                try:parse_counter(raw)
                except ValueError:
                    # Current rasterization can make OCR drop the slash.
                    # Only this exact observed 1/1 glyph permits a fallback.
                    from lib.anchor_match import anchor_scores
                    score,error=anchor_scores(image,Image.open(ROOT/'images/current/alliance_normal_setup_one_entry_current.png').convert('RGB'),(1130,657,1185,698))
                    if score>.99 and error<8:raw='1/1'
                result.screen="alliance_normal_setup"
                box=(1030,674)
            else:
                if canonical(text["normal_card"])=="NORMAL" and canonical(text["extreme_card"])=="EXTREME" and canonical(text["legend_card"])=="LEGEND":
                    scored=read_fields(image,[('normal_score',(1030,266,1186,302),'yellow_text'),('record',(925,650,1235,696),'button_text')])
                    score=re.fullmatch(r'([\d,]+)\s*PTS',scored['normal_score'].strip(),re.I)
                    if score and number(score[1])>0 and (canonical(scored['record'])=='NORMALRECORDCHALLENGE' or matches('alliance_normal_record_button_1080',(925,650,1235,696))):
                        return ScreenEvidence('alliance_normal_done',{'variant':'NORMAL','score':number(score[1])},dict(text,**scored))
                    result.screen="alliance_select_normal";result.values["point"]=(1090,262);return result
                if canonical(text["setup_variant"]) in {"EXTREME","LEGEND"}:
                    result.screen="alliance_wrong_variant";result.values["point"]=(35,36);return result
                result.errors.append("Normal Alliance Battle controls not verified; Extreme/Legend excluded")
                return result
            try:entries=parse_counter(raw)
            except ValueError:result.errors.append("Normal entry count unreadable");return result
            result.values.update(variant="NORMAL",entries=entries,point=box)
        elif canonical(text["auto_label"])=="AUTOPLAY":
            box=np.asarray(image.crop((384,658,413,688)))
            checked=((box[:,:,2]>150)&(box[:,:,1]>100)&(box[:,:,0]<80)).sum()>200
            result.screen="alliance_battle_auto"
            result.values["auto_on"]=bool(checked)
        return result
