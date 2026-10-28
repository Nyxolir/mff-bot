"""Observed Multiverse Saga ticket-sweep screens; no resource-stock OCR."""
import re
from lib.mission_reader import viewport,read_fields,canonical
from lib.screen_reader import ScreenEvidence
from lib.farming import parse_counter,UNBOOSTED_SWEEPS

NORMAL='[NORMAL] CONVERGING FATES'
HIDDEN='[HIDDEN] CONVERGING FATES'

def stage_mode(text,seven_alias=False):
    s=canonical(text)
    if re.fullmatch(r'[17][1-5]FUTUREFIGHTLEVEL[1-5]' if seven_alias else r'7[1-5]FUTUREFIGHTLEVEL[1-5]',s):return NORMAL
    if re.fullmatch(r'8[1-5]DOOM3099LEVEL[1-5]',s):return HIDDEN
    return None

class ConvergingReader:
    def read(self,source):
        image=viewport(source)
        t=read_fields(image,[('title',(67,18,267,52),'text'),('stage',(222,105,520,137),'white_text'),
            ('modal',(470,140,810,180),'text'),('claim',(550,15,737,58),'white_text'),
            ('difficulty',(470,45,820,94),'text')])
        title=canonical(t['title']);mode=stage_mode(t['stage'],seven_alias=True)
        if canonical(t['claim'])=='CLAIMALL':
            t.update(read_fields(image,[('result_stage',(480,78,850,113),'text'),
                ('close',(800,644,960,706),'text'),('runs',(190,114,313,465),'white_block')]))
            mode=stage_mode(t['result_stage']);counts=re.findall(r'(\d+)\s*time\(s\)',t['runs'],re.I)
            if mode and canonical(t['close'])=='CLOSE' and counts:
                return ScreenEvidence('converging_result',dict(mode=mode,clears=max(map(int,counts)),result_verified=True,point=(880,666)),t)
            return ScreenEvidence(errors=['Converging claim identity/count not verified'],text=t)
        if title=='MULTIVERSESAGA' and canonical(t['difficulty'])=='SELECTDIFFICULTY':
            t.update(read_fields(image,[('ready',(680,604,826,654),'button_text'),('entries',(648,580,855,611),'text')]))
            m=re.fullmatch(r'REMAININGENTRYCOUNT(\d+)(\d+)',canonical(t['entries']))
            if canonical(t['ready'])=='READY' and m and 0<=int(m[1])<=int(m[2])==5:
                return ScreenEvidence('converging_difficulty',dict(entries=(int(m[1]),5),point=(750,633)),t)
        if title=='MULTIVERSESAGA':
            t.update(read_fields(image,[('chapter',(27,91,236,136),'text'),('theme',(25,140,235,171),'text'),
                ('normal',(45,660,122,690),'text'),('hidden',(165,665,287,690),'text')]))
            if canonical(t['chapter'])=='CHAPTER7' and canonical(t['theme'])=='MERGINGFATE' and canonical(t['normal'])=='BOSS' and canonical(t['hidden'])=='HIDDENBOSS':
                return ScreenEvidence('converging_chapter',dict(points={NORMAL:(80,676),HIDDEN:(216,676)}),t)
        if title!='READY':return ScreenEvidence(text=t)
        # Native ADB frames can lose the blue-backed heading in generic OCR.
        # Keep the exact notice body and its independent OK control as proof.
        t.update(read_fields(image,[('modal_white',(470,140,810,180),'white_text')]))
        if 'NOTICE' in (canonical(t['modal']),canonical(t['modal_white'])):
            t.update(read_fields(image,[('notice',(345,279,940,345),'white_block'),('ok',(690,510,790,565),'button_text')]))
            if (canonical(t['notice'])=='THECRYSTALVAULTISFULLANDYOUWILLNOTBEABLETOSTOREMOREINTHECRYSTALVAULTEVENAFTERCOMPLETINGANEPISODE' and canonical(t['ok'])=='OK'):
                return ScreenEvidence('converging_vault_notice',dict(mode=mode,point=(740,536)),t)
        if 'SWEEP' in (canonical(t['modal']),canonical(t['modal_white'])):
            t.update(read_fields(image,[('prompt',(490,310,800,345),'text'),('ticket_label',(450,368,800,405),'text'),
                ('batch',(550,536,733,577),'text'),('close',(800,536,951,574),'text'),('single',(350,536,465,577),'button_text')]))
            m=re.fullmatch(r'USEUPTO([1-5S])',canonical(t['batch']))
            if (canonical(t['prompt'])=='SETTHENUMBEROFSWEEPS' and canonical(t['ticket_label']).startswith('SWEEPTICKETSCONSUMEDPERPLAY') and m and canonical(t['close'])=='CLOSE'):
                return ScreenEvidence('converging_sweep',dict(mode=mode,selected=int(m[1].replace('S','5')),boost_total=0,crystal_total=0,sweep_verified=True,single_verified=canonical(t['single'])=='USEX1',point=(640,555),close_point=(872,555)),t)
        if not mode:return ScreenEvidence(text=t)
        t.update(read_fields(image,[('designated',(642,106,1195,143),'white_text'),('reward',(175,327,614,365),'yellow_text'),
            ('daily',(57,666,135,700),'text'),('entries',(170,662,230,703),'text'),('sweep',(520,665,604,702),'button_text')]))
        reward='BIOMETRICSVALERIARICHARDS' if mode==NORMAL else 'BIOMETRICSFRANKLINRICHARDS'
        try:remaining,total=parse_counter(t['entries'])
        except ValueError:return ScreenEvidence(errors=['Converging daily entries unreadable'],text=t)
        if (canonical(t['reward'])==reward
                and canonical(t['daily'])=='DAILY' and total==5 and canonical(t['sweep'])=='SWEEP'):
            return ScreenEvidence('converging_ready',dict(mode=mode,remaining=remaining,total=total,preparation_verified=True,point=(560,684)),t)
        return ScreenEvidence(errors=['Converging preparation identity/control incomplete'],text=t)
