"""Read challenge pages and active benefit names, with no account actions."""
from lib.mission_reader import viewport,read_fields,canonical
from lib.screen_reader import ScreenEvidence
from lib.objectives import parse_objectives,excluded_event

def completed_challenge_tail(image,kind):
    """Known unfinished-first lists: require both the check and COMPLETE label."""
    import cv2,numpy as np
    from PIL import Image
    from pathlib import Path
    top,bottom=(190,622) if kind=='quest' else (274,706)
    ref=np.asarray(Image.open(Path(__file__).resolve().parents[1]/f'images/current/{kind}_complete_check.png').convert('RGB'))
    search=np.asarray(image.crop((1170,top,1215,bottom)))
    scores=cv2.matchTemplate(search,ref,cv2.TM_CCOEFF_NORMED)
    for y,x in zip(*np.where(scores>.96)):
        actual=search[y:y+ref.shape[0],x:x+ref.shape[1]]
        if np.abs(actual.astype('int16')-ref.astype('int16')).mean()>=12:continue
        y=int(y)+top
        label=read_fields(image,[('complete',(1030 if kind=='quest' else 1065,y+(8 if kind=='quest' else 5),1175 if kind=='quest' else 1182,min(bottom,y+(40 if kind=='quest' else 32))),'text')])['complete']
        if canonical(label)=='COMPLETE':return True
    return False

def home_shortcuts(image):
    """Locate shortcut captions in their current vertical slots, not old points."""
    import numpy as np
    pixels=np.asarray(image.crop((780,72,925,355))).astype('int16')
    white=(pixels.min(2)>150)&(pixels.max(2)-pixels.min(2)<45)
    rows=np.flatnonzero(white.sum(1)>10);bands=[]
    for y in rows:
        if not bands or y-bands[-1][-1]>2:bands.append([int(y)])
        else:bands[-1].append(int(y))
    boxes=[(780,72+b[0]-2,925,72+b[-1]+3) for b in bands if 5<=b[-1]-b[0]+1<=23]
    words=read_fields(image,[(str(i),box,'white_text') for i,box in enumerate(boxes)]) if boxes else {}
    found={}
    for i,box in enumerate(boxes):
        caption=canonical(words[str(i)]).lstrip('0123456789')
        key='benefits_point' if caption in {'SPECIALBENEFITS','PECIALBENEFITS'} else 'daily_point' if caption=='DAILYTASK' else None
        if key:found[key]=(845,(box[1]+box[3])//2-34)
    pixels=np.asarray(image.crop((930,350,1135,620))).astype('int16')
    white=(pixels.min(2)>150)&(pixels.max(2)-pixels.min(2)<45)
    bands=[]
    for y in np.flatnonzero(white.sum(1)>8):
        if not bands or y-bands[-1][-1]>2:bands.append([int(y)])
        else:bands[-1].append(int(y))
    boxes=[(930,350+b[0]-2,1135,350+b[-1]+3) for b in bands if 7<=b[-1]-b[0]+1<=24]
    words=read_fields(image,[(str(i),box,'white_text') for i,box in enumerate(boxes)]) if boxes else {}
    for i,box in enumerate(boxes):
        if canonical(words[str(i)])=='EVENTQUEST':found['event_quest_point']=(1040,(box[1]+box[3])//2)
    return found


class ObjectiveReader:
    def read(self,source):
        try:image=viewport(source)
        except ValueError as error:return ScreenEvidence(errors=[str(error)])
        fields=[("title",(67,18,365,52),"text"),
                ("benefits",(479,94,800,137),"text"),
                ("home_daily",(806,149,897,174),"text"),
                ("home_benefits",(796,245,908,269),"text"),
                ("daily_tab",(153,92,255,132),"text"),
                ("event_tab",(1020,161,1205,199),"text"),
                ("list_heading",(393,228,588,264),"text"),
                ("event_heading",(227,99,765,145),"text")]
        text=read_fields(image,fields)
        result=ScreenEvidence(text=text)
        from PIL import Image
        from pathlib import Path
        from lib.anchor_match import anchor_scores
        score,error=anchor_scores(image,Image.open(Path(__file__).resolve().parents[1]/'images/current/menu_icon.png').convert('RGB'),(1234,24,1265,50))
        if score>.97 and error<12:result.values['menu_available']=True
        if canonical(text['title'])=='EVENTQUEST':
            result.screen='event_quest_objectives';result.values['home_available']=True
            body=read_fields(image,[('body',(185,190,790,622),'white_block')])['body']
            result.text['body']=body;result.values['signature']=' '.join(body.upper().split())
            try:result.values['objectives']=read_quest_rows(image,body)
            except ValueError as error:result.errors.append(str(error))
            if not body.strip():result.errors.append('Event Quest list unreadable')
            result.values['completed_tail_verified']=completed_challenge_tail(image,'quest')
            return result
        if canonical(text['title']) not in {'CHALLENGES','SPECIALBENEFITS'}:
            # Benefits artwork can animate away while the static home menu is
            # visible. Require all three labels and undimmed white lettering.
            import numpy as np
            labels=read_fields(image,[('store',(18,239,185,280),'white_text'),
                ('team',(18,329,185,373),'white_text'),('inventory',(18,419,230,465),'white_text'),
                ('enter',(1000,630,1253,700),'button_text')])
            result.text.update({'home_'+k:v for k,v in labels.items()})
            pixels=np.asarray(image.crop((18,239,185,280)))
            if (all(canonical(labels[k])==k.upper() for k in labels)
                    and (pixels.min(axis=2)>170).sum()>100):
                result.screen='game_home';result.values['home_controls_verified']=True
                result.values['daily_shortcut_missing']=canonical(text['home_daily'])!='DAILYTASK'
                result.values.update(home_shortcuts(image))
                result.values['daily_shortcut_missing']='daily_point' not in result.values
                return result
        if (canonical(text['home_daily']) in {'SPECIALBENEFITS','PECIALBENEFITS'} and
            canonical(text['home_benefits'])=='TODAYSGIFT'):
            result.screen='game_home';result.values.update(home_shortcuts(image));result.values['daily_shortcut_missing']='daily_point' not in result.values;return result
        def home_label(name,box):
            import cv2,numpy as np
            from PIL import Image
            from pathlib import Path
            ref=np.asarray(Image.open(Path(__file__).resolve().parents[1]/f"images/current/{name}.png").convert("RGB"))
            def letters(p):return ((p.min(axis=2)>160)&((p.max(axis=2).astype('int16')-p.min(axis=2))<35)).astype('uint8')
            x1,y1,x2,y2=box
            actual=np.asarray(image.crop((x1-2,y1-2,x2+2,y2+2)))
            return cv2.matchTemplate(letters(actual),letters(ref),cv2.TM_CCOEFF_NORMED).max()>.92
        if canonical(text["benefits"])=="SPECIALBENEFITS":
            result.screen="benefit_list"
            # Settled modal cards; animation frames fail the heading check.
            names=read_fields(image,[(f"entry{i}",(436,175+i*80,780,203+i*80),"text") for i in range(4)])
            entries=[]
            for i in range(4):
                title=names[f"entry{i}"].strip()
                if len(title)>=4 and sum(c.isalpha() for c in title)>=4:
                    entries.append({"name":title,"excluded":excluded_event(title),"point":(630,198+i*80)})
            result.values["events"]=entries
            return result
        if ((canonical(text["home_daily"])=="DAILYTASK" and canonical(text["home_benefits"])=="SPECIALBENEFITS") or
            (home_label("home_daily_label",(806,149,897,174)) and home_label("home_benefits_label",(796,245,908,269)))):
            result.screen="game_home";result.values.update(home_shortcuts(image));result.values['daily_shortcut_missing']='daily_point' not in result.values;return result
        if canonical(text["title"])=="CHALLENGES" and canonical(text["daily_tab"])=="DAILY":
            import numpy as np
            tab=np.asarray(image.crop((67,95,337,132))).astype('int16')
            selected=((tab[:,:,2]>tab[:,:,0]+40)&(tab[:,:,2]>70)).mean()>.55
            if not selected:return ScreenEvidence('challenges_other_tab',{**result.values,'daily_tab_point':(200,113),'home_available':True},text)
            result.screen="daily_objectives"
            box=(632,294,934,706)
        elif canonical(text["event_tab"]) in {"CHALLENGES","CHALLSNGES"}:
            import numpy as np
            # Maxed passes retain unclaimed/repeatable daily rows. Those rows
            # no longer create farming requirements for this pass.
            pass_header=read_fields(image,[('pass_header',(67,18,260,52),'white_text')]) if 'PASS' in canonical(text['event_heading']) else {}
            if (canonical(pass_header.get('pass_header','')) in {'WEEKLYPASS','SPECIALPASS'}
                    and 'PASS' in canonical(text['event_heading'])):
                progress=read_fields(image,[('pass_progress',(435,168,548,192),'white_text')])
                full=True
                for box in ((294,172,420,187),(562,172,678,187)):
                    bar=np.asarray(image.crop(box)).astype('int16')
                    full=full and ((bar[:,:,2]>150)&(bar[:,:,1]>100)&(bar[:,:,2]-bar[:,:,0]>60)).mean()>.9
                if canonical(progress['pass_progress'])=='MAXLEVEL' and full:
                    result.screen='event_rewards';result.text.update(progress)
                    result.values.update(pass_max_level_verified=True,pass_title=text['event_heading'],objectives=[])
                    return result
            selected=np.asarray(image.crop((1020,159,1204,164))).mean()>100
            if not selected or canonical(text["list_heading"])!="CHALLENGES":
                result.screen="event_rewards";return result
            result.screen="event_objectives"
            box=(483,274,910,706)
        else:
            nav=read_fields(image,[('menu',(465,18,560,58),'white_text'),('challenges',(1130,400,1260,436),'text')])
            if canonical(nav['menu'])=='MENU' and canonical(nav['challenges'])=='CHALLENGES':
                return ScreenEvidence('objective_menu',{'challenges_point':(1195,390)},nav)
            import cv2,numpy as np
            from PIL import Image
            from pathlib import Path
            root=Path(__file__).resolve().parents[1]
            ref=np.asarray(Image.open(root/"images/current/home_nav_icon.png").convert("RGB"))
            from lib.anchor_match import anchor_scores
            score,error=anchor_scores(image,Image.fromarray(ref),(1168,19,1201,51))
            if score>.97 and error<12:
                result.values["home_available"]=True
            if canonical(text["title"]) in {"GIANTBOSSRAID","DIMENSIONMISSION","ALLIANCEBATTLE","CONTENTSTATUSBOARD","SELECTMISSION","WEEKLYPASS","CHALLENGES"}:
                result.values["home_available"]=True
            return result
        body=read_fields(image,[("body",box,"block")])["body"]
        result.text["body"]=body
        result.values["signature"]=" ".join(body.upper().split())
        try:
            if result.screen=="event_objectives":
                result.values["objectives"]=read_event_rows(image,body)
                result.values['completed_tail_verified']=completed_challenge_tail(image,'weekly')
            else:result.values["objectives"]=parse_objectives("page",body)
        except ValueError as error:result.errors.append(str(error))
        if not body.strip():result.errors.append("Challenge list unreadable")
        return result


def read_quest_rows(image,body):
    """Event Quest has separate description and progress columns, unlike passes."""
    import cv2,numpy as np,re
    edges=cv2.Canny(np.asarray(image)[180:623,65:1209],40,100)
    lines=cv2.HoughLinesP(edges,1,np.pi/180,300,minLineLength=1000,maxLineGap=8)
    ys=sorted({int(line[0][1])+180 for line in ([] if lines is None else lines) if abs(int(line[0][1])-int(line[0][3]))<2})
    bounds=[]
    for y in ys:
        if not bounds or y-bounds[-1]>6:bounds.append(y)
    pairs=[(a,b) for a,b in zip(bounds,bounds[1:]) if 90<=b-a<=130]
    fields=[]
    for i,(a,b) in enumerate(pairs):
        fields.extend([(f'task{i}',(185,a+47,790,b-12),'white_block'),(f'count{i}',(1040,b-40,1185,b-14),'white_number')])
    text=read_fields(image,fields) if fields else {};rows=[]
    # A partially filled cyan bar splits the counter background. Isolate its
    # white digits first; retain the older color treatment for other layouts.
    fallback=[(f'count{i}',(1040,b-40,1185,b-14),'color_number') for i,(_,b) in enumerate(pairs)
        if not re.fullmatch(r'\s*\d+\s*/\s*\d+\s*',text[f'count{i}'])]
    if fallback:text.update(read_fields(image,fallback))
    for i,_ in enumerate(pairs):rows.extend(parse_objectives('Event Quest',text[f'task{i}']+' '+text[f'count{i}']))
    for keyword,kinds in (('DIMENSIONMISSION',{'dimension','contribution'}),('DISPATCHMISSION',{'dispatch_energy'})):
        if keyword in canonical(body) and not any(row.kind in kinds for row in rows):raise ValueError('Relevant Event Quest progress unreadable')
    return rows


def read_event_rows(image,body):
    """Event progress sits on a separate bar; OCR it independently of the task."""
    import cv2
    import numpy as np
    pixels=np.asarray(image)
    edges=cv2.Canny(pixels[274:706,485:910],50,100)
    lines=cv2.HoughLinesP(edges,1,np.pi/180,150,minLineLength=390,maxLineGap=4)
    ys=sorted({int(line[0][1])+274 for line in ([] if lines is None else lines) if abs(int(line[0][1])-int(line[0][3]))<2})
    bars=[]
    for y in ys:
        if any(16<=end-y<=20 for end in ys) and not any(abs(y-old)<5 for old,_ in bars):bars.append((y,False))
    crop=pixels[274:706,485:910]
    cyan=((crop[:,:,1]>100)&(crop[:,:,2]>130)&(crop[:,:,0]<80)).mean(axis=1)>.9
    starts=np.flatnonzero(cyan & ~np.r_[False,cyan[:-1]])
    for start in starts:
        end=start
        while end<len(cyan) and cyan[end]:end+=1
        if end-start>=8 and not any(abs(start+274-y)<6 for y,_ in bars):bars.append((int(start)+274,True))
    fields=[]
    for i,(y,full) in enumerate(bars):
        if y-59<274:continue
        fields.extend([(f"row{i}",(483,y-59,910,y-3),"block"),(f"count{i}",(663,y,733,y+19),"color_number")])
    text=read_fields(image,fields) if fields else {}
    rows=[]
    for i,(y,full) in enumerate(bars):
        if f"row{i}" not in text:continue
        description=text[f"row{i}"]
        progress="1/1" if full else text[f"count{i}"]
        rows.extend(parse_objectives("page",description+" "+progress))
    # A relevant sentence without a usable row is unknown, never 'no task'.
    for keyword,kind in (("DIMENSIONMISSION",{"dimension","contribution"}),("DISPATCHMISSION",{"dispatch_energy"})):
        if keyword in canonical(body) and not any(row.kind in kind for row in rows):
            fallback=parse_objectives("page",body)
            relevant=[row for row in fallback if row.kind in kind]
            if not relevant:raise ValueError("Relevant event objective row unreadable")
            rows.extend(relevant)
    return rows
