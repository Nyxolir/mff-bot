"""The expanded quest drawer obscures controls across game pages."""
import numpy as np
import re
from lib.mission_reader import viewport,read_fields,canonical
from lib.screen_reader import ScreenEvidence


def notification_panel(source):
    image=viewport(source)
    # The number of quest rows changes. Locate the footer instead of pinning
    # its height or requiring a particular quest name / collection category.
    pixels=np.asarray(image)
    area=pixels[110:680,845:1265].astype('int16')
    cyan=(area[:,:,2]>160)&(area[:,:,1]>110)&(area[:,:,0]<90)
    rows=np.flatnonzero(cyan.mean(axis=1)>.9)
    groups=np.split(rows,np.flatnonzero(np.diff(rows)>1)+1)
    footer=None
    for group in groups:
        if not 24<=len(group)<=40:continue
        y=110+int(group[0]);arrow=pixels[y+15:y+20,1054:1059]
        if (arrow.max(axis=2)<90).mean()>.8:footer=y;break
    if footer is None:return None
    text=read_fields(image,[('heading',(920,77,1168,105),'text'),
        ('objective',(920,109,1218,139),'text')])
    if not (re.match(r'^\[?DAILY\]?\s+\S{3,}',text['heading'],re.I)
            or canonical(text['heading'])=='PROGRESSIVEMISSIONS'):return None
    if not re.match(r'^[\[(][A-Z][A-Z ]{2,35}\]\s*.{4,100}',text['objective'],re.I):return None
    return ScreenEvidence('quest_notification_panel',
        {'panel_verified':True,'close_point':(1066,36),'footer_y':footer},text)
