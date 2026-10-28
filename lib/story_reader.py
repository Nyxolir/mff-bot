"""Ultimate Story Auto Progress. Normal and ordinary pink Start are excluded."""
from pathlib import Path
from PIL import Image
from lib.mission_reader import viewport,read_fields,canonical
from lib.screen_reader import ScreenReader,ScreenEvidence
from lib.arena_reader import checked,ArenaReader
from lib.anchor_match import anchor_scores
import cv2,numpy as np
import re

ROOT=Path(__file__).resolve().parents[1]

class StoryReader:
 def read(self,source):
  from lib.story_completion import story_completion
  ended=story_completion(source)
  if ended:return ended
  image=viewport(source)
  def matches(name,box):
   ref=np.asarray(Image.open(ROOT/f'images/current/{name}.png').convert('RGB')).astype('int16')
   x1,y1,x2,y2=box;p=np.asarray(image.crop((x1-2,y1-2,x2+2,y2+2))).astype('int16')
   def glyph(a):
    if name in ('story_ultimate_button','story_progress_start'):return (a.max(2)<110).astype('uint8')
    if name in ('story_ultimate_caption','story_ultimate_caption_1080'):return ((a[:,:,0]>150)&(a[:,:,1]>110)&(a[:,:,2]<150)&(a[:,:,0]-a[:,:,2]>50)).astype('uint8')
    if name=='story_progress_tab':return ((a[:,:,1]>110)&(a[:,:,2]>170)&(a[:,:,0]<130)).astype('uint8')
    return ((a.min(2)>160)&(a.max(2)-a.min(2)<40)).astype('uint8')
   if name in ('story_ultimate_button','story_progress_start'):
    center=np.asarray(image.crop(box));cyan=(center[:,:,1]>130)&(center[:,:,2]>180)&(center[:,:,0]<80)
    if cyan.mean()<.6:return False
   mask=glyph(ref)
   return mask.sum()>20 and cv2.matchTemplate(glyph(p),mask,cv2.TM_CCOEFF_NORMED).max()>.93
  for offset in (62,0):
   def shifted(box):return (box[0],box[1]+offset,box[2],box[3]+offset)
   heading=read_fields(image,[('heading',shifted((520,115,766,155)),'text')])['heading']
   if canonical(heading)!='AUTOPROGRESS':continue
   labels=read_fields(image,[('tab',shifted((307,170,640,200)),'text'),('label',shifted((576,431,780,464)),'text'),('start',shifted((643,536,839,601)),'button_text')])
   tab=np.asarray(image.crop(shifted((310,171,635,196)))).astype('int16')
   selected=((tab[:,:,2]>tab[:,:,0]+45)&(tab[:,:,2]>65)).mean()>.8
   if canonical(labels['tab'])=='AUTOPROGRESS' and canonical(labels['label'])=='STARTFROMSTAGE11' and canonical(labels['start'])=='START' and selected:
    return ScreenEvidence('story_progress',{'from_stage_one':checked(image,shifted((535,431,566,464))),'start_point':(741,568+offset),'close_point':(539,568+offset),'stage_point':(551,447+offset)})
  progress=read_fields(image,[('heading',(520,115,766,155),'text')])
  if canonical(progress['heading'])=='AUTOPROGRESS':
   labels=read_fields(image,[('tab',(307,170,640,200),'text'),('label',(576,431,780,464),'text'),('start',(643,536,839,601),'button_text')])
   tab=np.asarray(image.crop((310,171,635,196))).astype('int16')
   selected=((tab[:,:,2]>tab[:,:,0]+45)&(tab[:,:,2]>65)).mean()>.8
   if canonical(labels['tab'])=='AUTOPROGRESS' and canonical(labels['label'])=='STARTFROMSTAGE11' and canonical(labels['start'])=='START' and selected:
    return ScreenEvidence('story_progress',{'from_stage_one':checked(image,(535,431,566,464))})
  if matches('story_progress_heading',(520,115,766,155)):
   if not matches('story_progress_tab',(307,170,640,200)) or not matches('story_stage_one_label',(576,431,780,464)) or not matches('story_progress_start',(643,536,839,601)):
    return ScreenEvidence(errors=['Story Auto Progress tab or controls not verified'])
   return ScreenEvidence('story_progress',{'from_stage_one':checked(image,(535,431,566,464))})
  if matches('story_select_title',(68,18,151,50)) and matches('story_ultimate_button',(234,553,417,607)):
   return ScreenEvidence('story_select',{'point':(325,578)})
  title=read_fields(image,[('story_title',(68,18,151,50),'text')])['story_title']
  if canonical(title)=='STORY':
   labels=read_fields(image,[('first_ultimate',(234,553,417,607),'button_text'),('second_ultimate',(660,553,843,607),'button_text')])
   if all(canonical(value)=='ULTIMATE' for value in labels.values()):return ScreenEvidence('story_select',{'point':(325,578)},dict(labels,story_title=title))
  caption=read_fields(image,[('caption',(834,553,1235,578),'text')])['caption']
  ultimate_caption=canonical(caption)=='TIER3ORPOTENTIALTRANSCENDEDCHARACTERSTHATHAVEREACHEDLEVEL70ORHIGHERCANPARTICIPATE'
  if matches('story_ultimate_caption',(834,553,1235,578)) or matches('story_ultimate_caption_1080',(834,553,1235,578)) or ultimate_caption:
   t=read_fields(image,[('team2',(906,249,943,282),'blue_number'),('daily_reward',(382,584,531,610),'text')])
   values={'team_2':t['team2'].strip()=='2','point':(930,668)}
   if not t['daily_reward'].strip():t['daily_reward']=read_fields(image,[('daily',(382,584,531,610),'red_text')])['daily']
   reward=re.fullmatch(r'DAILYREWARD([01])1',canonical(t['daily_reward']))
   if reward:values['daily_rewards']=(int(reward[1]),1)
   return ScreenEvidence('story_ultimate',values,t)
  battle=read_fields(image,[('progress',(423,613,565,645),'white_text'),('auto',(433,659,548,692),'white_text')])
  if canonical(battle['progress'])=='AUTOPROGRESS' and canonical(battle['auto'])=='AUTOPLAY':
   return ScreenEvidence('story_battle',{'auto_on':checked(image,(391,659,424,691)),'progress_on':checked(image,(391,613,424,646))})
  def letters(p):return ((p.min(2)>140)&(p.max(2).astype('int16')-p.min(2)<40)).astype('uint8')
  ref=np.asarray(Image.open(ROOT/'images/current/story_auto_label.png').convert('RGB'))
  actual=np.asarray(image.crop((433,657,548,692)))
  if cv2.matchTemplate(letters(actual),letters(ref),cv2.TM_CCOEFF_NORMED).max()>.93:
   return ScreenEvidence('story_battle',{'auto_on':checked(image,(391,659,424,691))})
  # The blue house icon is absent from battle and is only actionable after
  # the result has remained stable beyond Auto Progress's next-stage countdown.
  ref=np.asarray(Image.open(ROOT/'images/current/result_home_icon.png').convert('RGB'))
  search=np.asarray(image.crop((906,639,1000,703)))
  if cv2.matchTemplate(search,ref,cv2.TM_CCOEFF_NORMED).max()>.96:
   return ScreenEvidence('story_result',{'point':(954,669)})
  arena=ArenaReader().read(image)
  if arena.screen=='arena_selector':return ScreenReader().read(image,resource_check=True)
  if arena.screen=='arena_power':return arena
  if arena.screen=='arena_battle':return ScreenEvidence('story_battle',arena.values,arena.text)
  result=ScreenReader().read(image,resource_check=True)
  if result.screen=='status_board':
   from lib.mission_reader import BoardReader
   return BoardReader().read(image)
  return result
