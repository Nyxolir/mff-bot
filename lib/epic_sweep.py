"""Epic Quest preparation and immediate full-batch sweep popup. No input API."""
from datetime import timedelta
import re
import numpy as np
import cv2
from PIL import Image
from pathlib import Path
from lib.daily_queue import reset_period
from lib.farming import ENERGY_FARMS,parse_counter
from lib.mission_reader import read_fields,canonical
from lib.screen_reader import ScreenEvidence,number

PREP_ASSETS={
    'epic_sweep_button':(502,669,620,700),
    'epic_boost_cost_icon':(928,620,963,655),
    'epic_ticket_icon':(647,652,689,691),
}
MODAL_ASSETS={
    'epic_sweep_heading':(590,137,700,175),
    'epic_sweep_prompt':(500,313,782,350),
    'epic_sweep_ticket_label':(453,370,797,405),
    'epic_sweep_close':(760,524,984,588),
}

def boost_balance(image,primary,fallback,normalized=None):
    # OCR sometimes reads 89 as blank or 90 as 9. Verify the digit count from
    # the separated white glyphs before accepting either rendering.
    pixels=np.asarray(image.crop((950,19,995,49)).resize((270,180))).astype('int16')
    gray=pixels.max(axis=2)
    ink=(gray>max(25,float(gray.max())*.65))&((gray-pixels.min(axis=2))<40)
    changes=np.diff(np.r_[0,(ink.sum(axis=0)>2).astype('int8'),0])
    count=sum(end-start>=8 for start,end in zip(np.where(changes==1)[0],np.where(changes==-1)[0]))
    if not 1<=count<=3:raise ValueError('Boost digit layout unreadable')
    for candidate in (primary,normalized or '',fallback):
        if re.fullmatch(r'\d{'+str(count)+r'}',candidate.strip()):return number(candidate)
    # Tight neighboring glyphs such as 71 can fail line OCR. Read each
    # separately, retaining the independently verified number of glyphs.
    runs=[(int(start),int(end)) for start,end in zip(np.where(changes==1)[0],np.where(changes==-1)[0]) if end-start>=8]
    fields=[(str(i),(950+max(start//6-2,(runs[i-1][1]+5)//6 if i else 0),19,
        950+(end+5)//6+2,49),'dim_digit') for i,(start,end) in enumerate(runs)]
    digits=read_fields(image,fields)
    if all(re.fullmatch(r'\d',digits[str(i)].strip()) for i in range(count)):
        return int(''.join(digits[str(i)].strip() for i in range(count)))
    raise ValueError('Boost balance digit count not verified')

def read_epic_result(image,matches):
    close=any(matches(name,(763,644,996,708)) for name in ('epic_result_close','epic_result_close_qt'))
    repeat=any(matches(name,(285,644,518,708)) for name in ('epic_result_repeat','epic_result_repeat_qt'))
    if not (close and repeat):
        controls=read_fields(image,[('close',(800,650,955,700),'text'),('single',(310,650,490,700),'text'),('batch',(540,650,735,700),'text')])
        if not (canonical(controls['close'])=='CLOSE' and canonical(controls['batch'])=='USEUPTO10'):return None
    text=read_fields(image,[('stage',(310,331,982,376),'text'),('clears',(192,451,305,501),'text'),
        ('clears_top',(193,410,317,452),'text')])
    stage=re.sub(r'^CHAPTER\s+\d+\s*-\s*\d+\s*','',text['stage'],flags=re.I)
    stage=re.sub(r'^\[?VEILED SECRET\]?\s*','',stage,flags=re.I)
    # Some Epic chapters print the category and mission with the same name.
    # Accept only that exact duplication, never an arbitrary title substring.
    mode=next((mode for mode in ENERGY_FARMS-{'DIMENSION MISSION'}
        if canonical(stage) in (canonical(mode),canonical(mode)*2)),None)
    counts=[int(match[1]) for key in ('clears','clears_top')
        if (match:=re.fullmatch(r'(\d+)\s*time\(s\)',text[key].strip(),re.I))]
    if mode is None or not counts:return ScreenEvidence(errors=['Epic clear result mission/count unreadable'],text=text)
    return ScreenEvidence('sweep_result',{'layout':'epic','mode':mode,'clears':max(counts),
        'result_verified':True,'controls':{'close_result':(880,676)}},text)

def read_epic(image,title,matches):
    if canonical(title)!='MISSIONPREPARATION':return ScreenEvidence()
    labels=read_fields(image,[('heading',(590,137,700,175),'text'),('prompt',(500,313,782,350),'text'),('close',(810,530,935,577),'text')])
    modal_text=(canonical(labels['heading'])=='SWEEP' and canonical(labels['prompt'])=='SETTHENUMBEROFSWEEPS' and canonical(labels['close'])=='CLOSE')
    if modal_text or all(matches(name,box) for name,box in MODAL_ASSETS.items()):
        text=read_fields(image,[('selected',(680,536,708,574),'button_number'),
            ('quantity_label',(545,537,730,573),'text'),
            ('ticket_line',(454,369,835,405),'text'),
            ('boost_available',(950,19,995,49),'color_number'),
            ('boost_fallback',(950,19,995,49),'white_number'),
            ('boost_normalized',(950,19,995,49),'dim_white_number')])
        values={'layout':'epic','modal_verified':True,'sweep_verified':False,
            'controls':{'close_sweep':(872,555),'clear_batch':(640,555)}}
        single_text=read_fields(image,[('single',(350,535,465,578),'button_text')])['single']
        values['single_verified']=bool(matches('epic_sweep_single',(295,524,520,588)) or canonical(single_text)=='USEX1')
        result=ScreenEvidence('sweep',values,text)
        try:
            quantity=re.fullmatch(r'USEUPTO(\d+)',canonical(text['quantity_label']))
            if not quantity:raise ValueError('Epic full-batch button quantity unreadable: '+text['quantity_label'])
            selected=int(quantity[1])
            if text['selected'].strip().isdigit() and int(text['selected'])!=selected:
                raise ValueError('Epic button quantity readings disagree')
            if not canonical(text['ticket_line']).startswith('SWEEPTICKETSCONSUMEDPERPLAY'):
                raise ValueError('Epic sweep confirmation label unreadable')
            values.update(selected=selected,
                boost_available=boost_balance(image,text['boost_available'],text['boost_fallback'],text['boost_normalized']))
        except ValueError as error:result.errors.append(str(error))
        return result
    def prep_match(name,box):
        if matches(name,box) or matches(name+'_1080',box):return True
        if name not in ('epic_boost_cost_icon','epic_energy_cost_icon'):return False
        # Small cost icons shift slightly when a high-resolution Android frame
        # is normalized. Match luminance shape locally, independently of RGB.
        x1,y1,x2,y2=box
        actual=np.asarray(image.crop((x1-2,y1-2,x2+2,y2+2)).convert('L'))
        ref=np.asarray(Image.open(Path(__file__).resolve().parents[1]/f'images/current/{name}.png').convert('L'))
        return ref.std()>15 and cv2.matchTemplate(actual,ref,cv2.TM_CCOEFF_NORMED).max()>.92
    if not all(prep_match(name,box) for name,box in PREP_ASSETS.items()):return ScreenEvidence()
    text=read_fields(image,[('stage',(173,105,630,137),'text'),
        ('remaining',(180,668,222,699),'number'),
        ('boost_unit',(978,620,1009,646),'number')])
    result=ScreenEvidence('epic_preparation',text=text)
    mode_text=re.sub(r'^\[[^\]]+\]\s*','',text['stage'])
    mode=next((mode for mode in ENERGY_FARMS-{'DIMENSION MISSION'} if canonical(mode)==canonical(mode_text)),None)
    try:
        if mode is None:raise ValueError('Epic mission name unreadable or not authorized')
        remaining,total=parse_counter(text['remaining'])
        def unit(name):
            raw=text[name].strip()
            if not re.fullmatch(r'-?\d+',raw):raise ValueError('Epic unit cost unreadable: '+name)
            value=abs(int(raw))
            if value<=0:raise ValueError('Epic positive boost and energy costs required')
            return value
        result.values.update(mode=mode,remaining=remaining,total=total,
            boost_unit=unit('boost_unit'),
            preparation_verified=True,point=(560,684))
    except ValueError as error:result.errors.append(str(error))
    return result

def bind_epic_batch(preparation,modal,target,remaining,generation,observed,now):
    """Bind obscured modal costs to the immediately preceding verified preparation."""
    if preparation is None:raise ValueError('Inspect Epic preparation before clearing')
    evidence,captured,prepared_generation=preparation
    for stamp,limit in ((captured,120),(observed,30)):
        if not timedelta(0)<=now-stamp<=timedelta(seconds=limit) or reset_period(stamp)!=reset_period(now):
            raise ValueError('Epic preparation expired; inspect costs again')
    p=evidence.values;v=modal.values
    if evidence.screen!='epic_preparation' or evidence.errors or not p.get('preparation_verified') or prepared_generation!=generation:
        raise ValueError('Epic preparation authorization changed')
    single=remaining==1 and v.get('single_verified') is True
    if p.get('mode')!=target or p.get('remaining')!=remaining or (v.get('selected')!=remaining and not single) or remaining<=0:
        raise ValueError('Epic mission or full remaining batch does not match preparation')
    if modal.errors or v.get('layout')!='epic' or not v.get('modal_verified'):raise ValueError('Epic sweep popup not verified')
    for key in ('boost_unit',):
        if type(p.get(key)) is not int or p[key]<=0:raise ValueError('Epic cost is not verified')
    values=dict(v,mode=target,energy_total=None,ticket_total=None,energy_available=None,tickets_available=None,
        boost_total=p['boost_unit']*remaining,
        crystal_total=0,boosted=True,sweep_verified=True)
    if single:
        values['selected']=1;values['controls']=dict(v['controls'],clear_batch=(408,555))
    return values,observed
