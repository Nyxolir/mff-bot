"""Zombie Survival labels and controls; no roster identities or game inputs."""
import re
from pathlib import Path
from PIL import Image
from lib.mission_reader import viewport,read_fields,canonical,BoardReader
from lib.screen_reader import ScreenEvidence,ScreenReader
from lib.anchor_match import anchor_scores

ROOT=Path(__file__).resolve().parents[1]
MODE='ZOMBIE SURVIVAL'
TOP_FIVE=((830,198),(940,198),(1050,198),(1160,198),(830,306))
SLOT_X=(160,270,409,519,633)

def zombie_completion(source):
    image=viewport(source)
    t=read_fields(image,[('heading',(580,145,700,190),'white_text')])
    if canonical(t['heading'])!='NOTICE':return None
    t.update(read_fields(image,[('success',(804,42,1178,100),'text'),('message',(515,306,765,344),'white_text'),
        ('survived',(568,371,716,409),'yellow_text'),('ok',(605,517,675,556),'light_blue_text')]))
    # Keep the slash as observed instead of reconstructing a numeric counter.
    survived=re.fullmatch(r'([0-5])\s*/\s*5\s+Survived',t['survived'].strip(),re.I)
    if (canonical(t['success'])=='SURVIVALSUCCESS' and canonical(t['message'])=='AUTOREPEATHASENDED'
            and survived and canonical(t['ok']) in ('OK','0K')):
        return ScreenEvidence('zombie_repeat_ended',{'mode':MODE,'survivors':(int(survived[1]),5),'point':(640,537)},t)
    return None

class ZombieReader:
    def read(self,source):
        image=viewport(source)
        ended=zombie_completion(image)
        if ended:return ended
        t=read_fields(image,[('title',(67,18,280,52),'text'),('season_heading',(398,116,881,155),'white_text'),
            ('repeat',(580,122,711,166),'white_text')])
        title=canonical(t['title'])
        reward=read_fields(image,[('reward_heading',(489,104,799,145),'white_text')])
        if title=='CHALLENGES' and canonical(reward['reward_heading'])=='CHALLENGEREWARD':
            reward.update(read_fields(image,[('token',(455,202,846,241),'white_text'),('reward_ok',(606,561,678,601),'light_blue_text')]))
            if re.fullmatch(r'ZOMBIESURVIVALTOKENX[0-9]+ACQUIRED',canonical(reward['token'])) and canonical(reward['reward_ok']) in ('OK','0K'):
                return ScreenEvidence('zombie_rewards',{'mode':MODE,'point':(640,580)},dict(t,**reward))
        result_text=read_fields(image,[('success',(804,42,1178,100),'text')])
        if canonical(result_text['success'])=='SURVIVALSUCCESS':
            result_text.update(read_fields(image,[('challenge_level',(724,183,925,221),'text'),
                ('kill_score',(727,266,904,298),'text'),('level_number',(1204,184,1239,222),'dim_number')]))
            score,error=anchor_scores(image,Image.open(ROOT/'images/current/zombie_result_home.png').convert('RGB'),(843,639,892,682))
            if (canonical(result_text['challenge_level'])=='CHALLENGELEVEL' and canonical(result_text['kill_score'])=='ZOMBIEKILLSCORE'
                and result_text['level_number'].strip()=='1' and score>.96 and error<15):
                return ScreenEvidence('zombie_result',{'mode':MODE,'level':1,'home_point':(867,660)},dict(t,**result_text))
        battle=read_fields(image,[('battle_caption',(8,9,67,42),'white_text'),('battle_level',(68,10,90,40),'white_number'),
            ('gas',(1080,153,1232,184),'white_text')])
        if canonical(battle['battle_caption'])=='LEVEL' and battle['battle_level'].strip()=='1' and canonical(battle['gas'])=='ZOMBIEGAS':
            battle.update(read_fields(image,[('progress',(399,531,543,559),'white_text'),('auto',(425,615,554,645),'white_text')]))
            progress=re.fullmatch(r'Auto\s*Repeat\s*([1-5])\s*/\s*([1-5])',battle['progress'].strip(),re.I)
            if progress and int(progress[1])<=int(progress[2]) and canonical(battle['auto'])=='AUTOPLAY':
                return ScreenEvidence('zombie_battle',{'mode':MODE,'level':1,'progress':tuple(map(int,progress.groups()))},dict(t,**battle))
        if canonical(t['season_heading'])=='PASTSEASONRESULTS':
            t.update(read_fields(image,[('notice',(482,495,804,522),'yellow_text'),('ok',(610,548,673,586),'light_blue_text')]))
            if title==MODE.replace(' ','') and canonical(t['notice'])=='REWARDSWILLBEDELIVEREDTOYOURINBOX' and canonical(t['ok']) in ('OK','0K'):
                return ScreenEvidence('zombie_season_notice',{'mode':MODE,'point':(640,566)},t)
        if title=='CONTENTSTATUSBOARD':return BoardReader().read(image)
        if title=='SELECTCHARACTERS':
            t.update(read_fields(image,[('zombie',(92,317,302,348),'text')]))
            if canonical(t['zombie'])!='ZOMBIEENHANCEMENT':return ScreenEvidence(text=t)
            if canonical(t['repeat'])=='REPEAT':
                t.update(read_fields(image,[('perplay',(467,259,815,288),'text'),('selected',(548,445,606,494),'white_number'),
                    ('max',(741,445,841,489),'light_blue_text'),
                    ('cancel',(739,445,845,488),'red_text'),('start',(674,539,810,585),'button_text'),('close',(483,540,582,582),'light_blue_text')]))
                if (not canonical(t['perplay']).startswith('REQUIREDSWEEPTICKETSPERPLAY') or canonical(t['start'])!='START' or canonical(t['close'])!='CLOSE'):
                    return ScreenEvidence(errors=['Zombie ticket repeat controls unreadable'],text=t)
                count=re.fullmatch(r'[1-5]',t['selected'].strip())
                if not count:return ScreenEvidence(errors=['Zombie repeat count unreadable'],text=t)
                count=int(count[0])
                maximum=canonical(t['cancel'])=='CANCEL'
                if not maximum and canonical(t['max'])!='MAX':return ScreenEvidence(errors=['Zombie MAX control unreadable'],text=t)
                return ScreenEvidence('zombie_repeat',{'mode':MODE,'selected':count,'max_selected':maximum,
                    'max_point':(791,469),'close_point':(530,562),'start_point':(748,562)},t)
            t.update(read_fields(image,[('level',(500,351,700,387),'red_text'),('sort',(1000,98,1187,133),'text'),
                ('starting',(185,464,370,492),'text'),('reserve',(500,464,690,492),'text'),
                ('challenge',(984,641,1144,682),'button_text')]
                +[(f'slot_{i}',(x+10,559,x+98,585),'white_text') for i,x in enumerate(SLOT_X,1)]))
            level=re.fullmatch(r'SURVIVALLEVEL(\d+)',canonical(t['level']))
            if not level or canonical(t['sort'])!='DESCENDING' or canonical(t['starting'])!='STARTINGCHARACTER' or canonical(t['reserve'])!='RESERVECHARACTER' or canonical(t['challenge'])!='CHALLENGE':
                return ScreenEvidence(errors=['Zombie character selection controls unreadable'],text=t)
            slots=[]
            for i,x in enumerate(SLOT_X,1):
                if re.search(r'LV\d',canonical(t[f'slot_{i}'])):slots.append(True);continue
                ref=Image.open(ROOT/f'images/current/zombie_empty_slot_{i}.png').convert('RGB')
                score,error=anchor_scores(image,ref,(x+18,514,x+83,578))
                if score>.96 and error<15:slots.append(False)
                else:return ScreenEvidence(errors=[f'Zombie character slot {i} unreadable'],text=t)
            return ScreenEvidence('zombie_prepare',{'mode':MODE,'level':int(level[1]),'slots':tuple(slots),
                'ticket_point':(825,659),'back_point':(35,36)},t)
        if title=='ZOMBIESURVIVAL':
            t.update(read_fields(image,[('level',(70,85,343,130),'red_text'),('prepare',(908,642,1168,680),'button_text'),
                ('challenges',(106,641,263,681),'light_blue_text')]))
            level=re.fullmatch(r'SURVIVALLEVEL(\d+)',canonical(t['level']))
            if level and 1<=int(level[1])<=10 and canonical(t['prepare'])=='PREPAREFORCHALLENGE' and canonical(t['challenges'])=='CHALLENGES':
                return ScreenEvidence('zombie_lobby',{'mode':MODE,'level':int(level[1]),'minimum_point':(810,500),
                    'prepare_point':(1030,658),'challenges_point':(185,658)},t)
        if title=='CHALLENGES':
            t.update(read_fields(image,[('weekly_heading',(566,159,910,190),'text'),
                ('weekly_complete',(180,413,423,441),'white_text'),('acquire_all',(1064,103,1204,140),'text'),
                ('weekly_count',(244,452,342,494),'yellow_number'),('fifth',(566,552,912,582),'text'),
                ('five_clears',(711,603,761,623),'white_number')]))
            if canonical(t['weekly_heading'])=='WEEKLYMASTER0FSURVIVAL1':t['weekly_heading']='[Weekly] Master of Survival #1'
            if canonical(t['weekly_heading'])=='WEEKLYMASTEROFSURVIVAL1' and canonical(t['weekly_complete'])=='WEEKLYCHALLENGECOMPLETE' and canonical(t['acquire_all'])=='ACQUIREALL':
                import numpy as np
                pixels=np.asarray(image.crop((1063,105,1204,139)))
                # A usable cyan button is brighter than its disabled rendering.
                ready=float(pixels[:,:,2].mean())>140
                count=re.fullmatch(r'(\d+)/10',t['weekly_count'].strip())
                completed_labels=read_fields(image,[('complete',(208,450,380,496),'yellow_text')]
                    +[(f'claimed_{i}',(1072,180+i*98,1178,219+i*98),'text') for i in range(5)])
                t.update(completed_labels)
                all_claimed=(canonical(t['complete'])=='COMPLETE' and all(canonical(t[f'claimed_{i}'])=='COMPLETE' for i in range(5)))
                return ScreenEvidence('zombie_challenges',{'mode':MODE,'acquire_ready':ready,'acquire_point':(1135,121),
                    'weekly_completed':10 if all_claimed else int(count[1]) if count else None,'five_clears_verified':canonical(t['fifth'])=='WEEKLYMASTEROFSURVIVAL5' and t['five_clears'].strip()=='5/5'},t)
        result=ScreenReader().read(image,resource_check=True)
        if result.screen=='status_board':return BoardReader().read(image)
        if result.screen=='unknown' and not result.errors:
            from lib.objective_reader import ObjectiveReader
            home=ObjectiveReader().read(image)
            if home.screen=='game_home':return home
        return result
