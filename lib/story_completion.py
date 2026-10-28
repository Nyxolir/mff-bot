"""Recognize the explicit Story Auto Progress terminal summary."""
from lib.mission_reader import viewport,read_fields,canonical
from lib.screen_reader import ScreenEvidence

def story_completion(source):
 image=viewport(source)
 text=read_fields(image,[('heading',(495,80,790,127),'text')])
 if canonical(text['heading'])!='AUTOPROGRESSENDED':return None
 text.update(read_fields(image,[('message',(500,200,785,240),'text'),('close',(590,581,693,625),'text')]))
 if canonical(text['message'])!='AUTOPROGRESSHASENDED' or canonical(text['close'])!='CLOSE':return None
 return ScreenEvidence('story_ended',{'point':(640,603)},text)
