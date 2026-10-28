"""Recognize the observed BlueStacks launcher; never tap or infer completion."""
from functools import lru_cache
from pathlib import Path
from PIL import Image
from lib.anchor_match import anchor_scores
from lib.screen_reader import ScreenEvidence

ROOT=Path(__file__).resolve().parents[1]
ANCHORS=(('search',(400,64,879,107)),('system_apps',(284,222,380,249)),('future_fight',(486,222,592,249)))
CURRENT_ANCHORS=(('current_search',(400,64,879,107)),('current_system_apps',(284,245,390,276)),('current_future_fight',(486,245,600,276)))

@lru_cache(maxsize=6)
def reference(name):return Image.open(ROOT/('images/current/android_launcher_'+name+'.png')).convert('RGB')

def android_home(source):
    from lib.mission_reader import viewport
    image=viewport(source)
    for anchors,point in ((ANCHORS,None),(CURRENT_ANCHORS,(539,204))):
        if all((lambda pair:pair[0]>.96 and pair[1]<15)(anchor_scores(image,reference(name),box)) for name,box in anchors):
            return ScreenEvidence('android_home',{'launcher_verified':True,**({'launch_point':point} if point else {})})
    return None
