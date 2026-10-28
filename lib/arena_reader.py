"""Current free-arena screens, never authorizing refills."""
from pathlib import Path
import re
import cv2,numpy as np
from PIL import Image
from lib.mission_reader import viewport,read_fields,canonical
from lib.screen_reader import ScreenReader,ScreenEvidence
from lib.farming import parse_counter
ROOT=Path(__file__).resolve().parents[1]

def checked(image,box):
 p=np.asarray(image.crop(box));return bool(((p[:,:,0]<90)&(p[:,:,1]>120)&(p[:,:,2]>175)).sum()>150)

def read_ticket_cost(image,box,raw):
 raw=raw.strip()
 if not re.fullmatch(r'-?\d+',raw):
  raw=read_fields(image,[('cost',box,'yellow_text')])['cost'].strip()
 return raw

class ArenaReader:
 def read(self,source,resume=False):
  image=viewport(source)
  from lib.arena_completion import arena_completion
  ended=arena_completion(image)
  if ended:return ended
  def matches(name,box):
   from lib.anchor_match import anchor_scores
   score,error=anchor_scores(image,Image.open(ROOT/f'images/current/{name}.png').convert('RGB'),box)
   return score>.96 and error<15
  team_title=read_fields(image,[('title',(67,18,335,52),'white_text')])['title']
  if canonical(team_title)=='OTHERWORLDBATTLE':
   info=read_fields(image,[('heading',(420,68,875,111),'text'),('detail',(300,132,978,158),'text'),('close',(580,597,700,637),'text')])
   if (canonical(info['heading'])=='THISWEEKSDEBUFFEDCHARACTERS' and
       canonical(info['detail'])=='UPTO8NEWCHARACTERSWILLBEDEBUFFEDEVERYWEEKUPTOAMAXIMUMOF16CHARACTERS' and
       canonical(info['close'])=='CLOSE'):
    return ScreenEvidence('arena_information',{'mode':'OTHERWORLD BATTLE','point':(640,615)},info)
  if canonical(team_title)=='TEAMBATTLEARENA':
   if (matches('arena_acquire_heading',(582,102,700,134)) and matches('arena_acquire_mode',(548,163,733,188))
       and matches('arena_acquire_ok',(535,554,745,616))):
    reward=read_fields(image,[('reward',(452,216,809,255),'text')])
    if re.fullmatch(r'ARENATOKENX\d+ACQUIRED',canonical(reward['reward'])):
     return ScreenEvidence('arena_acquire',{'mode':'TEAM BATTLE ARENA','point':(640,585)},reward)
   t=read_fields(image,[('heading',(570,120,720,165),'text'),('search',(850,648,1220,705),'button_text')])
   if canonical(t['search'])=='REFILLENTRY':
    return ScreenEvidence('team_arena_lobby',{'mode':'TEAM BATTLE ARENA','entries':(0,5)},t)
   if canonical(t['heading'])=='REPEAT':
    t.update(read_fields(image,[('count',(540,446,610,491),'white_number'),('start',(660,539,835,590),'button_text'),('rule',(465,257,820,293),'text')]))
    if canonical(t['start'])=='START' and canonical(t['rule']).startswith('REQUIREDSWEEPTICKETSPERPLAY') and t['count'].isdigit():
     return ScreenEvidence('team_arena_repeat',{'selected':int(t['count'])},t)
   m=re.fullmatch(r'SEARCHFOROPPONENT(\d+)5',canonical(t['search']))
   if m:return ScreenEvidence('team_arena_lobby',{'mode':'TEAM BATTLE ARENA','entries':(int(m[1]),5)},t)
  if matches('otherworld_repeat_title',(586,122,710,164)) and matches('otherworld_repeat_rules',(470,249,816,284)) and matches('otherworld_repeat_until',(516,463,842,496)):
   t=read_fields(image,[('selected',(540,408,610,445),'white_number'),('start',(645,531,852,594),'button_text')])
   if canonical(t['start'])!='START':return ScreenEvidence(errors=['Otherworld ticket-repeat Start not verified'],text=t)
   try:selected=int(t['selected'])
   except ValueError:return ScreenEvidence(errors=['Otherworld repeat quantity or ticket cost unreadable'],text=t)
   return ScreenEvidence('otherworld_repeat',{'selected':selected,'until_rewards':checked(image,(478,465,505,493))},t)
  # A captured opening tween has the Repeat heading/rules displaced and its
  # Start buttons not drawn yet. Recognize only as a wait state, never a lobby
  # or a repeat form that can authorize input.
  def displaced(name,box):
   ref=np.asarray(Image.open(ROOT/f'images/current/{name}.png').convert('RGB'))
   x1,y1,x2,y2=box;search=np.asarray(image.crop((x1-3,max(0,y1-40),x2+3,y2+40)))
   _,score,_,(x,y)=cv2.minMaxLoc(cv2.matchTemplate(search,ref,cv2.TM_CCOEFF_NORMED))
   actual=search[y:y+ref.shape[0],x:x+ref.shape[1]]
   return score>.96 and np.abs(actual.astype('int16')-ref.astype('int16')).mean()<15
  if displaced('otherworld_repeat_title',(586,122,710,164)) and displaced('otherworld_repeat_rules',(470,249,816,284)):
   return ScreenEvidence('arena_transition')
  if matches('timeline_glory_cap_notice',(315,132,965,587)):
   return ScreenEvidence('timeline_glory_cap',{'point':(742,536)})
  home=np.asarray(Image.open(ROOT/'images/current/result_home_icon.png').convert('RGB'))
  region=np.asarray(image.crop((800,639,1040,703)))
  score=cv2.matchTemplate(region,home,cv2.TM_CCOEFF_NORMED)
  _,best,_,point=cv2.minMaxLoc(score)
  if best>.96:
   # A home button is a control, never sufficient to identify a mode.
   # Text templates include translucent scenery and vary with the opponent.
   # Require exact semantic labels plus the independently verified home icon.
   labels=read_fields(image,[('timeline_reward',(746,407,1020,445),'text'),
       ('points',(746,120,883,155),'text'),('otherworld_reward',(565,418,716,451),'text'),
       ('arena_info',(90,650,240,691),'text')])
   home_point=(800+point[0]+home.shape[1]//2,639+point[1]+home.shape[0]//2)
   if canonical(labels['timeline_reward'])=='TIMELINEBATTLEREWARD' and canonical(labels['points'])=='POINTS':
    return ScreenEvidence('arena_result',{'mode':'TIMELINE BATTLE','point':home_point},labels)
   if canonical(labels['otherworld_reward'])=='ARENAREWARD' and canonical(labels['arena_info'])=='ARENAINFO':
    return ScreenEvidence('arena_result',{'mode':'OTHERWORLD BATTLE','point':home_point},labels)
   # Team Arena has its own Results / Win Reward / Domination Bonus panel.
   labels=read_fields(image,[('results',(790,157,913,192),'white_text'),
       ('reward',(790,439,968,478),'white_text'),('bonus',(790,365,1026,404),'white_text')])
   if (canonical(labels['results'])=='RESULTS' and canonical(labels['reward'])=='WINREWARD'
       and canonical(labels['bonus'])=='DOMINATIONBONUS'):
    return ScreenEvidence('arena_result',{'mode':'TEAM BATTLE ARENA','point':(800+point[0]+home.shape[1]//2,639+point[1]+home.shape[0]//2)},labels)
  if matches('arena_power_label',(1048,19,1264,64)):
   return ScreenEvidence('arena_power',{'finished':matches('arena_power_end',(550,536,735,571))})
  if matches('arena_selector_tab',(640,117,934,155)) or canonical(team_title)=='SELECTMISSION':
   fields=[(str(i),(x+13,199,min(x+287,1275),236),'white_text') for i,x in enumerate((0,327,654,981))]
   labels=read_fields(image,fields);cards={}
   for i,x in enumerate((0,327,654,981)):
    for mode in ('TIMELINE BATTLE','OTHERWORLD BATTLE','TEAM BATTLE ARENA','ALLIANCE BATTLE'):
     if canonical(labels[str(i)])==canonical(mode):cards[mode]=(x+164,376)
   if len(cards)>=2:return ScreenEvidence('arena_selector',{'cards':cards},labels)
  t=read_fields(image,[('title',(13,15,335,54),'white_text'),('power',(1048,19,1264,64),'text'),('end',(530,530,794,576),'yellow_text')])
  if 'CONTENTSTATUSBOARD' in canonical(t['title']):
   from lib.mission_reader import BoardReader
   return BoardReader().read(image)
  if canonical(t['title']).startswith('OTHERWORLDBATTLE'):
   t.update(read_fields(image,[('reward_count',(908,607,1142,635),'yellow_text'),('enter',(895,655,1170,698),'button_text'),('opponent',(885,656,1181,697),'button_text')]))
   if canonical(t['enter']) in ('ENTERBATTLEFIELD','ENTERBATTLEFELD'):return ScreenEvidence('otherworld_opponent',{},t)
   ticket=matches('otherworld_ticket_current',(727,654,771,704)) or matches('otherworld_ticket_legacy',(727,654,771,704))
   idle=(canonical(t['opponent'])=='SEARCHFOROPPONENT' and ticket and
         ScreenReader().read(image,resource_check=True).values.get('menu_available') is True)
   match=re.search(r'Available Reward Counts\s*(\d+)\s*/\s*(\d+)',t['reward_count'],re.I)
   if match and tuple(map(int,match.groups()))==(0,5):return ScreenEvidence('otherworld_lobby',{'mode':'OTHERWORLD BATTLE','entries':(0,5),'lobby_idle_verified':idle},t)
   if canonical(t['opponent'])=='SEARCHFOROPPONENT':
    match=re.search(r'Available Reward Counts\s*(\d+)\s*/\s*(\d+)',t['reward_count'],re.I)
    if match and int(match[2])==5:
     return ScreenEvidence('otherworld_lobby',{'mode':'OTHERWORLD BATTLE','entries':(int(match[1]),5),'ticket_icon_verified':ticket,'lobby_idle_verified':idle},t)
  if canonical(t['title'])=='HERODEPLOYMENT':
   fight=read_fields(image,[('fight',(609,634,811,678),'button_text')])
   if canonical(fight['fight'])=='FIGHT':return ScreenEvidence('otherworld_setup',{},fight)
  if 'POWERSAVINGMODE' in canonical(t['power']):
   return ScreenEvidence('arena_power',{'finished':'ENDBATTLE' in canonical(t['end'])},t)
  if canonical(t['title']).startswith('TIMELINEBATTLE'):
   t.update(read_fields(image,[('ready',(961,657,1107,699),'button_text'),('search',(959,650,1173,700),'button_text'),
       ('entries',(1185,658,1238,691),'dark_number'),('team1',(23,94,62,133),'blue_number'),('refill',(962,650,1245,700),'button_text')]))
   if 'REFILL' in canonical(t['refill']):return ScreenEvidence('arena_exhausted',{'mode':'TIMELINE BATTLE'},t)
   if canonical(t['ready'])=='GETREADY':return ScreenEvidence('timeline_lobby',{'point':(1050,677)},t)
   if canonical(t['search']).startswith('SEARCHFOR'):
    try:entries=parse_counter(t['entries'])
    except ValueError:return ScreenEvidence(errors=['Timeline entry count unreadable'],text=t)
    return ScreenEvidence('timeline_setup',{'entries':entries,'team_1':t['team1'].strip()=='1','repeat':checked(image,(692,594,728,629))},t)
  # Auto checkbox location is shared by the observed current battle layouts.
  ref=Image.open(ROOT/'images/current/arena_auto_label.png').convert('RGB')
  def letters(p):return ((p.min(2)>140)&(p.max(2).astype('int16')-p.min(2)<40)).astype('uint8')
  actual=np.asarray(image.crop((436,658,551,692)))
  if cv2.matchTemplate(letters(actual),letters(np.asarray(ref)),cv2.TM_CCOEFF_NORMED).max()>.93:
   return ScreenEvidence('arena_battle',{'auto_on':checked(image,(391,659,424,691))})
  result=ScreenReader().read(image,resource_check=True)
  if resume and result.screen=='unknown' and not result.errors:
   from lib.objective_reader import ObjectiveReader
   home=ObjectiveReader().read(image)
   if home.screen=='game_home':return home
  return result
