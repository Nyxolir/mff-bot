"""Current Content Status Board recognition; consumes images, never clicks."""
import base64
import io
import json
from pathlib import Path
import re
import os
import subprocess
import numpy as np
from PIL import Image,ImageOps
from lib.farming import ENERGY_FARMS,UNBOOSTED_SWEEPS,MANUAL,FREE_ARENAS,parse_counter
from lib.ocr import ROOT,js_runtime,TesseractPool,native_executable,recognize_batch_with_js
from lib.screen_reader import ScreenEvidence


def viewport(source):
    image=Image.open(source) if isinstance(source,(str,Path)) else source
    image=image.convert("RGB")
    if image.size==(1312,753):return image.crop((0,32,1280,752))
    if image.size in ((1312,720),(1312,721)):return image.crop((0,0,1280,720))
    if image.size!=(1280,720):raise ValueError("Unsupported game viewport")
    return image


def read_fields(image,fields):
    requests=[]
    prepared={}
    for name,box,kind in fields:
        crop=image.crop(box)
        scale=6 if kind in ("dark_number","button_number","button_text","white_number","dim_white_number","dim_digit","dim_number","yellow_number") else 3
        crop=crop.resize((crop.width*scale,crop.height*scale))
        if kind=='light_blue_text':
            # Status messages are blue; exclude the orange mouse cursor in
            # desktop captures without depending on its position or shape.
            pixels=np.asarray(crop).astype('int16')
            mask=(pixels[:,:,2]>150)&(pixels[:,:,1]>110)&(pixels[:,:,2]-pixels[:,:,0]>20)&(pixels[:,:,1]-pixels[:,:,0]>10)
            crop=ImageOps.expand(Image.fromarray(np.where(mask,0,255).astype('uint8')),12,fill='white')
        elif kind in ('yellow_text','yellow_number','red_text'):
            pixels=np.asarray(crop).astype('int16')
            if kind=='red_text':mask=(pixels[:,:,0]>150)&(pixels[:,:,1]<130)&(pixels[:,:,2]<130)
            else:mask=(pixels[:,:,0]>140)&(pixels[:,:,1]>100)&(pixels[:,:,2]<130)&(pixels[:,:,0]-pixels[:,:,2]>45)
            crop=ImageOps.expand(Image.fromarray(np.where(mask,0,255).astype('uint8')),12,fill='white')
        elif kind=='dim_number':
            # Modal dimming affects colored balances too. Normalize brightness
            # at sixfold scale so thin final digits survive line recognition.
            gray=np.asarray(crop).max(axis=2).astype('float32')
            output=255-np.clip(gray*255/max(1,float(gray.max())),0,255).astype('uint8')
            crop=ImageOps.expand(Image.fromarray(output),12,fill='white')
        elif kind in ('white_number','white_text','white_block','dim_white_number','dim_digit'):
            pixels=np.asarray(crop).astype('int16')
            gray=pixels.max(axis=2)
            if kind in ('dim_white_number','dim_digit'):
                white=np.where((gray-pixels.min(axis=2))<max(5,float(gray.max())*.2),gray,0)
                output=255-np.clip(white*255/max(1,float(white.max())),0,255).astype('uint8')
            else:
                mask=(gray>max(25,float(gray.max())*.65))&((gray-pixels.min(axis=2))<40)
                output=np.where(mask,0,255).astype('uint8')
            crop=ImageOps.expand(Image.fromarray(output),12,fill='white')
        elif kind in ("button_number","button_text"):
            pixels=np.asarray(crop)
            mask=(pixels[:,:,0]<90)&(pixels[:,:,1]<110)&(pixels[:,:,2]<150)
            crop=ImageOps.expand(Image.fromarray(np.where(mask,0,255).astype("uint8")),12,fill="white")
        elif kind=="blue_number":
            pixels=np.asarray(crop)
            mask=(pixels[:,:,1]>115)&(pixels[:,:,2]>170)&(pixels[:,:,0]<130)
            crop=ImageOps.expand(Image.fromarray(np.where(mask,0,255).astype("uint8")),12,fill="white")
        elif kind=="dark_number":
            crop=ImageOps.expand(crop,12,fill="white")
        elif kind=="color_number":
            crop=ImageOps.expand(crop,12,fill="black")
        else:
            crop=Image.fromarray(np.asarray(crop).max(axis=2))
            crop=ImageOps.expand(ImageOps.invert(crop),12,fill="white")
        prepared[name]=np.asarray(crop)
        data=io.BytesIO();crop.save(data,format="PNG")
        requests.append({"name":name,"image":base64.b64encode(data.getvalue()).decode("ascii"),
            "whitelist":"0123456789/,-" if kind in ("number","dark_number","color_number","blue_number","button_number","white_number","dim_white_number","dim_digit","dim_number","yellow_number") else "",
            "psm":10 if kind=='dim_digit' else (13 if kind=="dark_number" else (6 if kind in ('block','white_block') else 7))})
    runtime=js_runtime()
    if runtime and not native_executable():
        return recognize_batch_with_js(requests,runtime)
    pool=TesseractPool()
    return {request["name"]:pool.image_to_string(prepared[request["name"]],
        whitelist=request["whitelist"] or None,page_segmentation=request["psm"]) for request in requests}


def canonical(text):return re.sub(r"[^A-Z0-9]","",text.upper())

def board_rows(image):
    """Recover the scrolling grid phase from tile-bottom / next-top edge pairs."""
    import cv2
    edges=cv2.Canny(np.asarray(image)[155:650,70:1210],40,100)
    lines=cv2.HoughLinesP(edges,1,np.pi/180,100,minLineLength=330,maxLineGap=8)
    ys=sorted({int(line[0][1])+155 for line in ([] if lines is None else lines)
        if abs(int(line[0][1])-int(line[0][3]))<2})
    phases=[(bottom+1)%105 for top in ys for bottom in ys if 8<=bottom-top<=14]
    phase=66
    if len(phases)>=2:
        distance=lambda a,b:min((a-b)%105,(b-a)%105)
        phase=max(range(105),key=lambda candidate:(sum(distance(candidate,p)<=1 for p in phases),
            -sum(distance(candidate,p) for p in phases)))
    return [y for y in range(phase,660,105) if y>=168 and y+65<=660]


class BoardReader:
    def read(self,source):
        try:image=viewport(source)
        except ValueError as error:return ScreenEvidence(errors=[str(error)])
        fields=[("title",(67,18,335,52),"text")]
        cells=[]
        for row,y in enumerate(board_rows(image)):
            for column,x in enumerate((72,454,837)):
                name=f"{row}_{column}"
                fields.extend([(name+"_name",(x+9,y+13,x+293,y+49),"text"),
                               (name+"_count",(x+295,y+22,x+341,y+65),"blue_number")])
                cells.append((name,x,y))
        text=read_fields(image,fields)
        result=ScreenEvidence("unknown",text=text)
        if canonical(text["title"])!="CONTENTSTATUSBOARD":
            result.errors.append("Content Status Board not verified");return result
        result.screen="content_board"
        known={canonical(name):name for name in ENERGY_FARMS|UNBOOSTED_SWEEPS|MANUAL|FREE_ARENAS|{"TIMELINE BATTLE","WORLD EVENT","ZOMBIE SURVIVAL"}}
        known.update(QUEENOFUMBO='QUEEN OF LIMBO',TIMEUNEBATTLE='TIMELINE BATTLE')
        for label,theme in [('ULTIMATEDIMENSIONALCLASH','DIMENSIONAL CLASH'),('ULTIMATETHETRUESHIELD','THE TRUE S.H.I.E.L.D.'),
                ('ULTIMATETHETRUESHLELD','THE TRUE S.H.I.E.L.D.'),('ULTIMATETHEALLWAR','THE ALL-WAR'),('ULTIMATEENDOFTHEFUTURE','END OF THE FUTURE')]:
            known[label]='STORY: '+theme
        reference=Image.open(ROOT/"images/current/complete_check.png").convert("RGB")
        ref=np.asarray(reference)
        ref_mask=((ref[:,:,0]>180)&(ref[:,:,1]>130)&(ref[:,:,2]<110)).astype("uint8")
        current=np.asarray(Image.open(ROOT/'images/current/complete_check_1080.png').convert('RGB'))
        masks=[ref_mask,((current[:,:,0]>180)&(current[:,:,1]>130)&(current[:,:,2]<110)).astype('uint8')]
        middle=np.asarray(Image.open(ROOT/'images/current/complete_check_1080_middle.png').convert('RGB'))
        masks.append(((middle[:,:,0]>180)&(middle[:,:,1]>130)&(middle[:,:,2]<110)).astype('uint8'))
        import cv2
        tiles=[];completion_order=[];unfinished_modes=set();prefix_readable=True
        for name,x,y in cells:
            mode=known.get(canonical(text[name+"_name"]))
            pixels=np.asarray(image.crop((x+336,y-1,x+370,y+29)))
            mask=((pixels[:,:,0]>180)&(pixels[:,:,1]>130)&(pixels[:,:,2]<110)).astype("uint8")
            # A completed tile has both the check glyph and a gold outline.
            # The outline provides an independent anchor across minor raster
            # differences in scrolled glyphs.
            top=np.asarray(image.crop((x+5,max(0,y-3),x+355,y+4)))
            top=top.astype('int16')
            gold_top=((top[:,:,0]>120)&(top[:,:,1]>110)&
                (top[:,:,0]-top[:,:,2]>45)&(top[:,:,1]-top[:,:,2]>35)).mean(axis=1).max()>.8
            completed=bool(gold_top and max(cv2.matchTemplate(mask,r,cv2.TM_CCOEFF_NORMED).max() for r in masks)>=.90)
            label=text[name+'_name']
            # Unknown-but-readable content still participates in the visual
            # order. A synthetic 'done' for excluded Alliance variants does not.
            completion_order.append(completed if sum(c.isalpha() for c in label)>=3 else None)
            if not completed:
                if sum(c.isalpha() for c in label)<3:prefix_readable=False
                if not mode:
                    from difflib import get_close_matches
                    if get_close_matches(canonical(label),known.keys(),n=1,cutoff=.8):prefix_readable=False
            if not mode:continue
            remaining=total=None
            if completed:remaining=0
            else:
                try:remaining,total=parse_counter(text[name+"_count"])
                except ValueError:pass
            if mode=="ALLIANCE BATTLE":
                label=read_fields(image,[("entry_kind",(x+9,y+46,x+295,y+79),"text")])["entry_kind"]
                text[name+"_entry_kind"]=label
                if canonical(label) in {"EXTREMEPLAYCOUNT","LEGENDPLAYCOUNT","INFINITECHALLENGEPLAYCOUNT"}:
                    remaining=0;completed=True
                elif canonical(label)!="NORMALPLAYCOUNT":remaining=None
            tiles.append({"mode":mode,"remaining":remaining,"total":total,"point":(x+180,y+35),"completed":completed})
            if not completed:unfinished_modes.add('STORY ULTIMATE' if mode.startswith('STORY: ') else mode)
        themes={tile['mode'][7:]:tile for tile in tiles if tile['mode'].startswith('STORY: ')}
        result.values['story_themes']=themes
        if themes:
            all_seen=len(themes)==4;done=all_seen and all(t['completed'] for t in themes.values())
            target=next((t for t in themes.values() if not t['completed']),next(iter(themes.values())))
            tiles.append(dict(mode='STORY ULTIMATE',remaining=0 if done else sum(not t['completed'] for t in themes.values()) if all_seen else None,
                total=4 if all_seen else None,point=target['point'],completed=done))
        result.values["tiles"]=tiles
        first=next((i for i,done in enumerate(completion_order) if done is True),None)
        tab=np.asarray(image.crop((67,106,292,132))).astype('int16')
        all_selected=((tab[:,:,2]>tab[:,:,0]+40)&(tab[:,:,2]>70)).mean()>.55
        result.values['completed_tail_verified']=bool(all_selected and first is not None and
            None not in completion_order[:first] and all(done is True for done in completion_order[first:]))
        result.values['incomplete_prefix_verified']=bool(all_selected and prefix_readable and None not in completion_order)
        result.values['unfinished_modes']=sorted(unfinished_modes)
        checkbox=np.asarray(image.crop((69,674,101,706)))
        result.values["accelerated_clear"] = bool(((checkbox[:,:,2]>180)&(checkbox[:,:,1]>100)&(checkbox[:,:,0]<80)).sum()>300)
        result.values["signature"]=__import__("hashlib").sha256(image.crop((65,170,1210,660)).tobytes()).hexdigest()
        return result
