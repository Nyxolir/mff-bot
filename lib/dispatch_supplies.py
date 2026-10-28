"""Inspect passive Dispatch supplies; pink reward dots authorize Claim All Rewards."""
from datetime import timedelta
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from lib.mission_reader import viewport,read_fields,canonical
from lib.screen_reader import ScreenEvidence,ScreenReader

ROOT=Path(__file__).resolve().parents[1]
CITY_SECTORS={'MIDTOWN':1,'HARLEM':2,'TIMESSQUARE':3,'OROLLAN':4,'PARIS':5,
    'LATVERIA':6,'WAKANDA':7,'KAMARTAJMONASTERY':8,'SHANGHAI':9,'ALASKA':10,
    'ILIADAIRCRAFTCARRIER':11,'TRISKELION':12,'ASGARD':13}

def reward_dot(pixels,box):
    """Only inspect the pink notification at a verified Acquire button corner."""
    x,y,w,h=box
    patch=pixels[max(0,y-7):min(pixels.shape[0],y+9),max(0,x+w-8):min(pixels.shape[1],x+w+8)].astype('int16')
    mask=((patch[:,:,0]>180)&(patch[:,:,2]>100)&(patch[:,:,1]<110)&
          (patch[:,:,0]-patch[:,:,1]>90)&(patch[:,:,2]-patch[:,:,1]>50)).astype('uint8')
    count,_,stats,_=cv2.connectedComponentsWithStats(mask)
    return any(8<=area<=150 and 3<=width<=14 and 3<=height<=14
               for _,_,width,height,area in stats[1:count])

class DispatchSuppliesReader:
    def read(self,source):
        image=viewport(source)
        def matches(name,box,inset=None):
            from lib.anchor_match import anchor_scores
            ref=Image.open(ROOT/f'images/current/{name}.png').convert('RGB')
            if inset:
                ref=ref.crop(inset)
                x,y=box[:2];left,top,right,bottom=inset
                box=(x+left,y+top,x+right,y+bottom)
            score,error=anchor_scores(image,ref,box)
            return score>.96 and error<15
        if matches('dispatch_claim_result_title',(570,20,710,58)) and matches('dispatch_claim_result_ok',(524,635,756,699)):
            return ScreenEvidence('dispatch_supply_result',{'ok_point':(640,667)})
        # The help icon after the title can OCR as ©/C and invalidate an
        # otherwise exact heading. Keep it outside the text crop; reward
        # actions still require the independent button and card anchors.
        text=read_fields(image,[('title',(67,18,268,52),'text')])
        if canonical(text['title'])=='DISPATCHMISSION':
            if matches('dispatch_reward_panel_close',(1230,94,1259,121)):
                return ScreenEvidence('dispatch_supply_panel',{'close_point':(1244,108)},text)
            # Immediately after Claim All the game disables its button and
            # hides Acquire controls. Verify both empty supply bars as well;
            # absence of reward dots on an unreadable map is not proof.
            if (matches('dispatch_claim_all_disabled',(618,641,799,696)) and
                    matches('dispatch_empty_midtown',(84,350,258,409)) and
                    matches('dispatch_empty_times_square',(537,306,711,365))):
                return ScreenEvidence('dispatch_supply_empty_map',{'fill':0},text)
            # Match the complete label inside the cyan button. Its outside
            # glow animates and must not invalidate the fixed text anchor.
            if matches('dispatch_claim_all_anchor',(618,641,799,696),(7,14,175,42)):
                pixels=np.asarray(image)
                blue=((pixels[:,:,2]>160)&(pixels[:,:,1]>110)&(pixels[:,:,0]<80)&
                    (pixels[:,:,2].astype('int16')-pixels[:,:,1]>20)).astype('uint8')*255
                blue=cv2.morphologyEx(blue,cv2.MORPH_OPEN,np.ones((3,149),np.uint8))
                contours,_=cv2.findContours(blue,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
                # Pair each button's top/bottom cyan bands. Closing the whole map
                # also joins nearby paths and the Claim All button to some cards.
                bands=[cv2.boundingRect(c) for c in contours]
                boxes=[]
                for x,y,w,h in bands:
                    if not (160<=w<=230 and 8<=h<=15 and 240<=y<=610):continue
                    bottom=next((b for b in bands if 23<=b[1]-y<=29 and 8<=b[3]<=15
                        and min(x+w,b[0]+b[2])-max(x,b[0])>=160),None)
                    if bottom:
                        left=max(x,bottom[0]);right=min(x+w,bottom[0]+bottom[2])
                        boxes.append((left,y,right-left,bottom[1]+bottom[3]-y))
                boxes.sort()
                fields=[]
                for i,(x,y,w,h) in enumerate(boxes):
                    fields.extend([(f'label{i}',(x,y-241,x+w,y-212),'text'),
                        (f'city{i}',(max(0,x-15),y-219,min(1280,x+w+15),y-192),'yellow_text')])
                text.update(read_fields(image,fields) if fields else {})
                cards=[]
                ref=np.asarray(Image.open(ROOT/'images/current/dispatch_acquire_label.png').convert('RGB'))
                dark=lambda p:((p[:,:,0]<100)&(p[:,:,1]<100)&(p[:,:,2]<130)).astype('uint8')
                for i,(x,y,w,h) in enumerate(boxes):
                    label=canonical(text[f'label{i}']);city=canonical(text[f'city{i}'])
                    button=pixels[y+1:y+h-1,x+20:x+w-20]
                    if button.shape[0]<ref.shape[0] or button.shape[1]<ref.shape[1]:continue
                    score=cv2.matchTemplate(dark(button),dark(ref),cv2.TM_CCOEFF_NORMED).max()
                    if score<.82 or len(city)<3:continue
                    bar=pixels[y-16:y-7,x:x+w].astype('int16')
                    orange=(bar[:,:,0]>160)&(bar[:,:,1]>95)&(bar[:,:,2]<85)&(bar[:,:,0]-bar[:,:,2]>90)
                    fill=float((orange.sum(axis=0)>=3).mean())
                    # The small sector label can lose a leading digit (13 → 3).
                    # Exact city names identify the observed map sectors reliably.
                    sector_id=CITY_SECTORS.get(city)
                    cards.append(dict(key=city,sector=sector_id,fill=fill,
                        acquire=(x+w//2,y+h//2),open=(x+w//2,y-135),
                        pink_dot=reward_dot(pixels,(x,y,w,h))))
                if not cards:return ScreenEvidence(errors=['Dispatch supply cards unreadable'],text=text)
                signature=tuple(c['acquire'] for c in cards)
                return ScreenEvidence('dispatch_supplies_map',{'cards':cards,'signature':signature,'claim_all_point':(708,670),'claim_all_verified':True},text)
        return ScreenReader().read(image,resource_check=True)

class DispatchSuppliesSession:
    def __init__(self,now):
        self.started=now;self.actions=0;self.phase='left';self.seen=set()
        self.previous=None;self.same=0;self.reward_proof=None
        self.pending=None;self.claim_started=None;self.result_closed=False;self.claimed=0
        self.done=False
        self.fill=None

    def observe(self,evidence,now):
        if now-self.started>timedelta(minutes=6) or self.actions>=80:raise ValueError('Dispatch supplies inspection timed out')
        if evidence.errors:raise ValueError('; '.join(evidence.errors))
        screen=evidence.screen;v=evidence.values
        if self.pending:
            if screen=='dispatch_supplies_map':self.seen.update(c['key'] for c in v['cards'])
            if screen=='dispatch_supply_result' and not self.result_closed:
                self.result_closed=True;return self.action(('ack',*v.get('ok_point',(640,667))))
            if screen=='dispatch_supplies_map' and not any(c.get('pink_dot') for c in v['cards']):
                self.claimed=1;self.pending=None;self.done=True;return None
            if screen=='dispatch_supply_empty_map':
                self.fill=0;self.claimed=1;self.pending=None;self.done=True;return None
            if now-self.claim_started>timedelta(seconds=60):
                raise ValueError('Dispatch Claim All outcome unknown; no retry')
            return self.action(('wait',0,0))
        if screen=='dispatch_supply_result':
            self.pending='all';self.claim_started=now;self.result_closed=True
            return self.action(('ack',*v.get('ok_point',(640,667))))
        if screen=='dispatch_supply_panel':
            return self.action(('click',*v['close_point']))
        if screen=='dispatch_supply_empty_map':
            self.fill=0;self.done=True;return None
        if screen=='dispatch_supplies_map':
            cards=v['cards'];signature=v['signature']
            if not cards:raise ValueError('No Dispatch reward cards verified')
            self.fill=max((c.get('fill',0) for c in cards),default=0)
            self.seen.update(c['key'] for c in cards)
            if any(c.get('pink_dot') for c in cards):
                if not v.get('claim_all_verified'):raise ValueError('Dispatch Claim All button not verified')
                self.reward_proof=('all',now)
                self.pending='all';self.claim_started=now;self.result_closed=False
                return self.action(('claim',*v['claim_all_point']))
            # Sectors share their accumulation clock; one visible set is
            # sufficient. Do not pan the map or open individual timers.
            self.done=True;return None
        if screen=='navigation_menu':return self.action(('click',491,642))
        if screen in ('select_mission','select_mission_coop'):
            if canonical(v.get('first_mission',''))=='DISPATCHMISSION':return self.action(('click',174,376))
            return self.action(('click',194,135))
        if v.get('menu_available'):return self.action(('click',1249,36))
        raise ValueError('Dispatch supplies navigation screen unrecognized')

    def action(self,value):self.actions+=1;return value
