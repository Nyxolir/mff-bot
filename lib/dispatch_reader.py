"""Dispatch 7-1 navigation and energy/boost evidence; never selects another stage."""
from pathlib import Path
import re
import cv2
import numpy as np
from PIL import Image
from lib.mission_reader import viewport,read_fields,canonical
from lib.screen_reader import ScreenEvidence,number
from lib.alliance_reader import AllianceReader

ROOT=Path(__file__).resolve().parents[1]


class DispatchReader:
    def read(self,source):
        try:image=viewport(source)
        except ValueError as error:return ScreenEvidence(errors=[str(error)])
        text=read_fields(image,[("title",(67,18,335,52),"text"),
            ("stage",(231,105,510,139),"text"),
            ("sector",(896,91,1044,120),"text"),
            ("first_stage",(907,296,969,334),"text"),
            ("result",(300,5,1000,175),"block")])
        result=ScreenEvidence(text=text)
        if canonical(text["title"])=="MISSIONPREPARATION":
            if not re.match(r"\[7-1\]\s*Panther Protection",text["stage"],re.I):
                result.screen="dispatch_wrong_stage";return result
            fields=[("boost_cost",(978,620,1009,646),"number"),
                ("boost_available",(950,19,995,49),"color_number")]
            text.update(read_fields(image,fields))
            result.screen="dispatch_7_1_setup"
            try:
                ref=np.asarray(Image.open(ROOT/"images/current/dispatch_start_label.png").convert("RGB"))
                from lib.anchor_match import anchor_scores
                score,error=anchor_scores(image,Image.fromarray(ref),(1091,650,1178,693))
                if score<.96 or error>15:
                    raise ValueError("Dispatch start control not verified")
                box=np.asarray(image.crop((425,668,455,699)))
                energy_on=((box[:,:,2]>150)&(box[:,:,1]>100)&(box[:,:,0]<80)).sum()>200
                result.values.update(sector=7,mission=1,use_energy=bool(energy_on),
                    boost_cost=number(text["boost_cost"].lstrip('-')),
                    boost_available=number(text["boost_available"]),
                    crystal_total=0,start_verified=True,point=(1130,672))
            except ValueError as error:result.errors.append(str(error))
            return result
        if canonical(text["title"])=="DISPATCHMISSION":
            if canonical(text["first_stage"])=="71":
                result.screen="dispatch_sector_seven";result.values["point"]=(1080,334);return result
            if canonical(text["sector"]).startswith("SECTOR") or re.fullmatch(r"\d+-1",text["first_stage"].strip()):
                result.screen="dispatch_other_sector";return result
            result.screen="dispatch_map"
            ref=np.asarray(Image.open(ROOT/"images/current/dispatch_sector7_label.png").convert("RGB"))
            search=np.asarray(image.crop((0,72,1280,600)))
            _,score,_,(x,y)=cv2.minMaxLoc(cv2.matchTemplate(search,ref,cv2.TM_CCOEFF_NORMED))
            if score>.97:result.values["sector_seven_point"]=(x+40,y+72+130)
            return result
        auto=AllianceReader().read(image)
        if auto.screen=="alliance_battle_auto":
            auto.screen="dispatch_battle_auto";return auto
        if ("VICTORY" in canonical(text["result"]) or "MISSIONCLEAR" in canonical(text["result"])):
            result.screen="dispatch_result";result.values["result_verified"]=True
        return result
