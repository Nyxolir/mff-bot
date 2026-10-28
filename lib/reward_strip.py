"""Read icon-anchored counters in Onslaught's horizontal reward strip."""
from pathlib import Path
import re
import cv2
import numpy as np
from PIL import Image
from lib.farming import parse_counter

ROOT=Path(__file__).resolve().parents[1]


def read_strip(image,read):
    values={"reward_strip_verified":True}
    positions={"soul":None,"seed":None}
    search=np.asarray(image.crop((40,620,562,682)))
    for key in ("soul","seed"):
        ref=np.asarray(Image.open(ROOT/f"images/current/{key}_strip_icon.png").convert("RGB"))
        scoremap=cv2.matchTemplate(search,ref,cv2.TM_CCOEFF_NORMED)
        _,score,_,(x,y)=cv2.minMaxLoc(scoremap)
        if score<.85:continue
        x+=40
        positions[key]=x
        # An item can be clipped at either end; only complete counters count.
        box=(x+4,679,x+72,705) if key=="soul" else (x-12,679,x+67,705)
        left,right=box[0],box[2]
        if left<42 or right>560:continue
        zero_verified=False
        references=[f"{key}_zero_counter"]+(["seed_zero_counter_qt","seed_zero_counter_current"] if key=="seed" else ['soul_zero_counter_current'])
        for name in references:
            zero=np.asarray(Image.open(ROOT/f"images/current/{name}.png").convert("RGB"))
            zero_left=x+(16 if key=="soul" else 9)
            region=np.asarray(image.crop((zero_left-4,679,zero_left+zero.shape[1]+4,706)))
            _,zscore,_,(zx,zy)=cv2.minMaxLoc(cv2.matchTemplate(region,zero,cv2.TM_CCOEFF_NORMED))
            counter=region[zy:zy+zero.shape[0],zx:zx+zero.shape[1]]
            if zscore>.95 and np.abs(counter.astype('int16')-zero.astype('int16')).mean()<15:
                values[key]=(0,165 if key=="soul" else 300);zero_verified=True;break
        if zero_verified:continue
        try:
            counter=parse_counter(read(key,box,True))
            if counter[1]==(165 if key=="soul" else 300):values[key]=counter
        except ValueError:
            # The slash between white remaining digits and a yellow cap can
            # become a 7 in mixed-color OCR. Verify both rendered parts;
            # never repair a numeric string by inserting a guessed slash.
            from lib.mission_reader import read_fields
            parts=read_fields(image,[('remaining',box,'white_number'),('cap',box,'yellow_number')])
            cap=165 if key=='soul' else 300
            try:
                counter=parse_counter(parts['remaining'])
                if counter[1]==cap and 0<=counter[0]<=cap:
                    values[key]=counter;continue
            except ValueError:pass
            prefix=re.fullmatch(r'(\d+)/',parts['remaining'].strip())
            if prefix and parts['cap'].strip()==str(cap):
                remaining=int(prefix[1])
                if 0<=remaining<=cap:values[key]=(remaining,cap)
    values["strip_position"]=(positions["soul"],positions["seed"])
    return values
