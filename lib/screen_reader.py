"""Read current 1280x720 game screens from supplied screenshots only.

No capture or input API is used here. Evidence stays unknown on a mismatched
layout, missing anchor, or unreadable counter. Saved fixtures are never fresh
authorization to spend resources.
"""
from dataclasses import dataclass, field
from pathlib import Path
import re

import numpy as np
import cv2
from PIL import Image, ImageOps

from lib.ocr import TesseractPool
from lib.farming import parse_counter


@dataclass
class ScreenEvidence:
    screen: str = "unknown"
    values: dict = field(default_factory=dict)
    text: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)


def number(text):
    text = text.strip()
    if not re.fullmatch(r"(?:\d{1,3}(?:,\d{3})+|\d+)", text):
        raise ValueError("Unreadable number")
    return int(text.replace(",", ""))


class ScreenReader:
    def __init__(self, ocr=None):
        self.ocr = ocr or TesseractPool()

    def read(self, source, resource_check=False):
        image = Image.open(source) if isinstance(source, (str, Path)) else source
        image = image.convert("RGB")
        # Explicitly supported native screenshot dimensions. Never stretch an
        # unknown layout onto old click coordinates.
        if image.size == (1312, 753):
            image = image.crop((0, 32, 1280, 752))
        elif image.size in ((1312,720),(1312,721)):
            # QScreen's client-area capture excludes the native title bar.
            image = image.crop((0,0,1280,720))
        elif image.size != (1280, 720):
            return ScreenEvidence(errors=["Unsupported viewport dimensions"])
        result = ScreenEvidence()

        def template(name, box):
            reference = Image.open(Path(__file__).resolve().parents[1] / "images/current" / name).convert("RGB")
            crop = image.crop(box)
            if crop.size != reference.size:
                return False
            if name == "complete_check.png":
                def gold(im):
                    p = np.asarray(im)
                    return (p[:,:,0]>180) & (p[:,:,1]>130) & (p[:,:,2]<110)
                x1,y1,x2,y2 = box
                search = image.crop((x1-3,y1-3,x2+3,y2+3))
                score = cv2.matchTemplate(gold(search).astype("uint8"),
                    gold(reference).astype("uint8"), cv2.TM_CCOEFF_NORMED).max()
                return bool(score >= .93)
            from lib.anchor_match import anchor_scores
            score,brightness_error=anchor_scores(image,reference,box)
            if name=="boost_icon.png":return bool(score>=.90 and brightness_error<=20)
            return bool(score >= .97 and brightness_error <= 12)

        def read(name, box, numeric=False):
            crop = image.crop(box)
            scale = 6 if name == "soul" else 3
            crop = crop.resize((crop.width * scale, crop.height * scale))
            # Bright game text on dark backgrounds; color maximum retains
            # yellow entry counters as well as white numbers.
            pixels = np.asarray(crop)
            gray = Image.fromarray(pixels.max(axis=2))
            prepared = ImageOps.expand(ImageOps.invert(gray), border=12, fill="white")
            if name in ("soul","energy","boost"):
                prepared = ImageOps.expand(crop, border=12, fill="black")
            if name == "timeline_entries":
                crop = image.crop(box).resize(((box[2]-box[0])*6,(box[3]-box[1])*6))
                prepared = ImageOps.expand(crop, border=12, fill="white")
            text = self.ocr.image_to_string(np.asarray(prepared),
                whitelist="0123456789/," if numeric else None,
                page_segmentation=13 if name == "timeline_entries" else 7).strip()
            result.text[name] = text
            return text

        if resource_check and template("menu_heading.png",(431,19,539,59)) and template("select_mission_tile.png",(429,598,559,692)):
            return ScreenEvidence("navigation_menu", {"select_mission":True})
        title = read("title", (67, 18, 335, 52)).upper()
        # Modal has its own title, with main screen dimmed behind it.
        modal = read("modal", (476, 45, 815, 89)).upper()
        try:
            if resource_check and title.startswith("SELECT MISSION"):
                label=read("first_mission",(13,199,287,236)).upper()
                result.screen="select_mission_coop" if re.sub(r"\s","",label)=="GIANTBOSSRAID" else "select_mission"
                result.values["navigation_only"]=True
                result.values["first_mission"]=label
            elif re.fullmatch(r"ONSLAUGHT ROUND [12]", modal):
                result.screen = "gbr_rewards"
                result.values["seed"] = parse_counter(read("seed", (986, 345, 1061, 373), True))
                if result.values["seed"][1] != 300:
                    raise ValueError("Unexpected Celestial Seed daily cap")
            elif re.sub(r"\s", "", title).startswith("GIANTBOSSRAID"):
                # OCR can still read a dimmed lobby behind a popup. Require
                # undimmed boss-card text before authorizing any navigation.
                label_pixels=np.asarray(image.crop((1017,150,1140,510))).astype('int16')
                bright=(label_pixels.min(axis=2)>175)&(label_pixels.max(axis=2)-label_pixels.min(axis=2)<40)
                if bright.sum()<30:raise ValueError('GBR lobby is dimmed or obscured')
                rewards = read("rewards", (76, 575, 261, 607)).upper()
                def boss_text(name,box):
                    from lib.mission_reader import read_fields
                    value=read_fields(image,[(name,box,'white_text')])[name]
                    result.text[name]=value
                    return re.sub(r'[^A-Z]','',value.upper())
                # Verify text and the selected card outline independently of character lighting.
                onslaught=boss_text('boss_onslaught',(1017,473,1140,510))=='ONSLAUGHT'
                pixels=np.asarray(image.crop((880,445,1236,452))).astype('int16')
                selected=((pixels[:,:,0]>160)&(pixels[:,:,1]>100)&(pixels[:,:,2]<120)&(pixels[:,:,0]-pixels[:,:,2]>60)).mean(axis=1).max()>.65
                names=[boss_text('boss_master',(1017,150,1140,186)),boss_text('boss_galactus',(1017,259,1122,295)),boss_text('boss_dormammu',(1017,365,1140,401))]
                list_verified=sum(n==expected for n,expected in zip(names,('MASTERMOLD','GALACTUS','DORMAMMU')))>=2
                anchored=template("onslaught_selected.png",(1017,473,1140,510)) or ((onslaught or list_verified) and selected)
                if not anchored or rewards != "REWARDS AVAILABLE":
                    if resource_check:
                        if not list_verified:
                            raise ValueError("GBR boss selection controls not verified")
                        result.screen="gbr_selection";result.values["onslaught_selected"]=False
                        return result
                    raise ValueError("Onslaught reward anchors not verified")
                result.screen = "gbr_main"
                if resource_check:
                    from lib.reward_strip import read_strip
                    result.values.update(read_strip(image,read))
                else:
                # Exhausted rewards use a red zero beside a yellow slash/cap.
                # OCR merges that slash into a 7 or drops it. Verify the whole
                # observed 0/165 rendering; never infer zero from failed OCR.
                    if template("soul_zero_counter.png",(78,683,132,702)):
                        result.values["soul"]=(0,165)
                        result.text["soul"]="0/165 (verified rendering)"
                    else:
                        result.values["soul"] = parse_counter(read("soul", (66, 679, 134, 705), True))
                if "soul" in result.values and result.values["soul"][1] != 165:
                    raise ValueError("Unexpected Soul of Faltine daily cap")
            elif title.startswith("WORLD EVENT"):
                label = read("score_label", (865, 266, 1016, 294)).upper()
                if label != "BEST SCORE":
                    raise ValueError("World Event score anchor not verified")
                result.screen = "world_event"
                result.values["best_score"] = number(read("best_score", (1144, 268, 1238, 295), True))
                result.values["entries"] = parse_counter(read("entries", (728, 671, 782, 706), True))
                result.values["already_done"] = result.values["best_score"] > 0
            elif title.startswith("OTHERWORLD BATTLE"):
                result.screen = "otherworld"
                label = read("entry_label", (907, 608, 1142, 637))
                match = re.fullmatch(r"Available Reward Counts\s+(\d+)/(\d+)", label)
                if not match:
                    raise ValueError("Otherworld reward count not verified")
                result.values["entries"] = parse_counter("/".join(match.groups()))
                result.values["ticket_icon_verified"] = template("repeat_ticket.png", (727, 654, 771, 704))
            elif title.startswith("TIMELINE BATTLE"):
                result.screen = "timeline"
                label = read("ready", (961, 658, 1100, 697)).upper()
                if label == "GET READY":
                    result.values["entries"] = parse_counter(read("timeline_entries", (1142, 660, 1196, 698), True))
                else:
                    label = read("battle_control", (980, 641, 1239, 698)).upper()
                    result.screen = "timeline_team"
                    result.values["team_1_verified"] = template("team_1_selected.png", (15, 90, 70, 145))
                    result.values["refill_prompt"] = label == "REFILL ENTRY"
                    if label != "REFILL ENTRY":
                        raise ValueError("Timeline start control not yet validated")
            elif title == "CONTENT STATUS BOARD":
                result.screen = "status_board"
                # Fixed arena grid needs named anchors. A completed check is
                # matched only alongside that tile's mode.
                completed = []
                for name, x, y in (("OTHERWORLD BATTLE",454,171),
                                   ("TIMELINE BATTLE",837,171),
                                   ("TEAM BATTLE ARENA",72,276)):
                    label = read(name, (x+9,y+13,x+289,y+49)).upper()
                    checked = template("complete_check.png", (x+339,y+2,x+367,y+26))
                    if label == name and checked:
                        completed.append(name)
                result.values["completed"] = completed
        except ValueError as error:
            result.errors.append(str(error))
            # Partial OCR is useful diagnostics, never complete evidence.
            result.values.clear()
        navigation_titles={'MISSIONPREPARATION':'mission_preparation','CHALLENGES':'challenge_navigation'}
        navigation_title=re.sub(r'[^A-Z]','',title)
        if resource_check and result.screen=='unknown' and navigation_title in navigation_titles:
            # Navigation only, after closing an Epic result. A dimmed header
            # behind a sweep popup cannot authorize leaving preparation.
            header=np.asarray(image.crop((67,18,335,52)))
            if (header.min(axis=2)>170).sum()>100:
                result.screen=navigation_titles[navigation_title];result.values.update(menu_available=True,home_available=True)
        if resource_check and result.screen=="gbr_main" and not result.errors:
            try:
                if not template("boost_icon.png",(910,15,945,53)):
                    raise ValueError("Boost icon not verified")
                result.values["boost"]=number(read("boost",(950,19,995,49),True))
            except ValueError as error:
                # Balance OCR must not discard or block independently verified
                # raid rewards. Full-batch spending still needs fresh balances
                # from its own verified preparation screen.
                result.values["balance_error"]=str(error)
        if resource_check and result.screen in {"unknown","timeline","timeline_team","otherworld","world_event","status_board"}:
            if template("menu_icon.png",(1234,24,1265,50)):
                result.values["menu_available"]=True
        if resource_check and result.screen=='unknown' and not result.errors:
            from lib.objective_reader import ObjectiveReader
            navigation=ObjectiveReader().read(image)
            if navigation.screen=='game_home':
                navigation.values.update(result.values);return navigation
        return result
