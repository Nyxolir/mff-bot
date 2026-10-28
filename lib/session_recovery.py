"""Recognize only the validated account-session replacement notice."""
from pathlib import Path
import numpy as np
import cv2
from lib.mission_reader import viewport,read_fields,canonical
from lib.screen_reader import ScreenEvidence


def session_notice(source):
    try:image=viewport(source)
    except ValueError:return None
    # Match the retry message and both controls, not its variable NET code.
    # The blue OK rectangle gates OCR so ordinary pages remain inexpensive.
    button=np.asarray(image.crop((650,512,832,562))).astype('int16')
    if ((button[:,:,2]>170)&(button[:,:,1]>110)&(button[:,:,0]<80)).mean()>.7:
        retry=read_fields(image,[('title',(581,146,700,185),'text'),
            ('body',(433,313,857,346),'text'),('retry',(576,345,706,375),'text'),
            ('cancel',(486,518,592,554),'text'),('ok',(710,518,774,554),'text')])
        expected={'title':'NOTICE','body':'UNABLETOESTABLISHNETWORKCONNECTION',
            'retry':'TRYAGAIN','cancel':'CANCEL','ok':'OK'}
        if all(canonical(retry[k])==v for k,v in expected.items()):
            return ScreenEvidence('network_retry_notice',{'retry_verified':True,'ok_point':(741,538)},retry)
    from PIL import Image
    from lib.anchor_match import anchor_scores
    settings=[]
    for name,box in [('settings_heading',(568,42,712,82)),('settings_ok',(606,628,674,660))]:
        score,error=anchor_scores(image,Image.open(Path(__file__).resolve().parents[1]/f'images/current/{name}.png').convert('RGB'),box)
        settings.append(score>.97 and error<12)
    if all(settings):return ScreenEvidence('game_settings',{'close_point':(640,645)})
    link_notice=[]
    for name,box in [('external_link_message',(366,342,915,380)),('external_link_cancel',(486,520,590,551))]:
        score,error=anchor_scores(image,Image.open(Path(__file__).resolve().parents[1]/f'images/current/{name}.png').convert('RGB'),box)
        link_notice.append(score>.97 and error<12)
    if all(link_notice):return ScreenEvidence('external_link_notice',{'cancel_point':(539,538)})
    title_anchors=[]
    for name,box in [('game_title_logo',(507,439,772,588)),('game_title_play',(612,642,671,673))]:
        score,error=anchor_scores(image,Image.open(Path(__file__).resolve().parents[1]/f'images/current/{name}.png').convert('RGB'),box)
        title_anchors.append(score>.97 and error<12)
    if all(title_anchors):
        pixels=np.asarray(image.crop((592,316,688,396))).astype('int16')
        loading=((pixels[:,:,0]>150)&(pixels[:,:,1]>50)&(pixels[:,:,1]<190)&(pixels[:,:,2]<60)).sum()>150
        return ScreenEvidence('game_title',{'loading':bool(loading),'point':(640,657)})
    # Android's exit confirmation can cover a still-readable home screen.
    # Gate OCR on the observed white panel; cancellation never exits the game.
    panel=np.asarray(image.crop((369,310,910,410)))
    if (panel.min(axis=2)>240).mean()>.92:
        from PIL import Image
        from lib.anchor_match import anchor_scores
        reference=Image.open(Path(__file__).resolve().parents[1]/'images/current/exit_game_panel.png').convert('RGB')
        score,error=anchor_scores(image,reference,(369,310,910,410))
        if score>.97 and error<12:
            return ScreenEvidence('exit_game',{'cancel_point':(792,384)})
    root=Path(__file__).resolve().parents[1]/"images/current"
    from PIL import Image
    for name,box in (("message",(348,342,932,376)),("ok",(542,506,738,570))):
        reference=np.asarray(Image.open(root/f"session_replaced_{name}.png").convert("RGB"))
        x1,y1,x2,y2=box
        search=np.asarray(image.crop((x1-3,y1-3,x2+3,y2+3)))
        scores=cv2.matchTemplate(search,reference,cv2.TM_CCOEFF_NORMED)
        _,score,_,(x,y)=cv2.minMaxLoc(scores)
        actual=search[y:y+reference.shape[0],x:x+reference.shape[1]]
        if score<.95 or np.abs(actual.astype("int16")-reference.astype("int16")).mean()>15:
            text=read_fields(image,[("notice",box,"text")])["notice"]
            expected='YOUHAVELOGGEDINTOANOTHERDEVICEMOVINGTOMAINSCREEN' if name=='message' else 'OK'
            if canonical(text)!=expected:
                text=read_fields(image,[("notice",box,"white_text" if name=='message' else 'text')])["notice"]
                if canonical(text)!=expected:return None
    return ScreenEvidence("session_replaced",{"ok_point":(640,538)})
