"""Shared Arena repeat summaries, verified by text rather than cursor-bearing templates."""
import re
from lib.mission_reader import viewport,read_fields,canonical
from lib.screen_reader import ScreenEvidence

def arena_completion(source):
 image=viewport(source)
 t=read_fields(image,[('heading',(495,80,795,127),'text')])
 if canonical(t['heading'])!='STOPAUTOREPEAT':return None
 t.update(read_fields(image,[('message',(300,200,982,240),'text'),('mode',(520,310,790,350),'text'),('runs',(145,380,330,425),'text')]))
 mode={'TEAMBATTLEARENA':'TEAM BATTLE ARENA','OTHERWORLDBATTLE':'OTHERWORLD BATTLE','TIMELINEBATTLE':'TIMELINE BATTLE'}.get(canonical(t['mode']))
 if mode is None:return None
 message=canonical(t['message'])
 if message not in ('AUTOREPEATHASENDED','AUTOREPEATHASENDEDBECAUSEYOUHAVEUSEDUPALLOFYOURENTRIES'):
  t.update(read_fields(image,[('message',(300,200,982,240),'light_blue_text')]))
  message=canonical(t['message'])
 if message=='AUTOREPEATHASENDEDBECAUSEYOUHAVEUSEDUPALLOFYOURENTRIES':
  t.update(read_fields(image,[('close',(470,581,585,625),'text'),('ok',(712,582,792,626),'button_text')]))
  if canonical(t['close'])!='CLOSE' or canonical(t['ok'])!='OK':return None
  # OK closes the exhausted-entry notice. The controller still verifies the
  # underlying result or zero remaining entries before releasing the task.
  return ScreenEvidence('arena_exhausted',{'mode':mode,'point':(755,604)},t)
 if message!='AUTOREPEATHASENDED':return None
 t.update(read_fields(image,[('close',(590,581,693,625),'text')]))
 if canonical(t['close'])!='CLOSE':return None
 count=re.fullmatch(r'(\d+)WINS(\d+)DEFEATS',canonical(t['runs']))
 if mode!='TEAM BATTLE ARENA':return ScreenEvidence('arena_repeat_ended',{'mode':mode,'point':(640,603)},t)
 return ScreenEvidence('team_arena_ended',{'point':(640,603),'runs':sum(map(int,count.groups())) if count else None},t)
