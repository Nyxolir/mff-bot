"""Local trivia answers with conservative, option-aware matching. No random fallback."""
from pathlib import Path
import json
from difflib import SequenceMatcher
import re
import unicodedata
from lib.game.data.daily_trivia import trivia_qa

SOURCE_URL='https://quizlet.com/hk/699399827/future-fight-daily-trivia-flash-cards/'

# Wording aliases checked against the supplied set. Retain the existing upstream
# bank rather than duplicating the flashcard collection. Correct spelling in UI
# answers matters: the source's "Dimension Derbis" is a typo.
EXTRA_ANSWERS=Path(__file__).resolve().parents[1]/'settings/gui/trivia-answers.json'

QUIZLET_ALIASES={
    "Which is the name of the bridge connects Yggdrasil's nine realms?":'Bifrost',
    "What is the name of the character-based quests that can be cleared in order for rewards?":'Heroic Quest',
    "Where you can battle other users using a set team of 3 and get Glory Tokens as rewards?":'Timeline Battle',
    "What Character Type is typically strong against Combat Type Characters?":'Blast',
    "What Character Type is typically strong against Blast Type Characters?":'Speed',
    "What is the name of the skill effect that reduces all Basic Defenses and removes all buffs from the enemy?":'Incapacitation',
    "What is the name of the skill effect that reduces all enemies Basic Attacks?":'Fracture',
}
# Confirmed displayed answers on the live account, 2026-10-19, 2026-10-22 and 2026-10-24. These newer
# questions are absent from the supplied 58-card set.
GAME_ANSWERS={
    # Live question Oct 25; https://www.marvel.com/comics/discover/2258/elektras-
    "What's the name of Daredevil's lover who becomes the second Daredevil?":'Elektra',
    # Correct results verified in the live quiz on 2026-10-24.
    # https://www.marvel.com/comics/discover/740/jubilee
    'Which of the following characters does not have the ability to transform?':'Jubilee',
    # https://www.marvel.com/characters/iron-man-tony-stark/in-comics
    "What's the name of the character who works as Tony Stark's secretary and specializes in rescue operations?":'Rescue',
    # https://www.marvel.com/comics/collection/22093/marvel_boy_hardcover
    'Which character is from Earth-200080 and a super soldier of the Kree Empire?':'Marvel Boy',
    # https://forum.netmarble.com/futurefight_en/view/75/792053
    'Which game mode lets you compete with other alliances to capture regions?':'Alliance Conquest',
    # https://www.marvel.com/comics/discover/1956/knull
    "What's the name of the character who created the Symbiote and is nicknamed King in Black?":'Knull',
    'What is the skill that attacks an enemy by triggering a counterattack when attacked by an enemy?':'Counterattack',
    # Marvel's Future Foundation profile identifies its Baxter Building HQ:
    # https://www.marvel.com/teams-and-groups/future-foundation
    "What is the name of the location of the Fantastic Four's famous base of operations?":'Baxter Building',
    'What is the name of the magical armor Odin forged to oppose the Celestials?':'Destroyer',
    'Which game mode lets you form a team of 5 characters to face against other users?':'Otherworld Battle',
    'What is the name of the half-moon bear spirit that Crescent travels with?':'Io',
    "What's the name of the material used for Uru Awakening that makes Odin's Blessing even stronger?":'Eternal Flame',
}

def normalize(text):
    text=unicodedata.normalize('NFKD',text).upper().replace('’',"'")
    text=text.replace("ISN'T",'IS NOT').replace("AREN'T",'ARE NOT')
    return ' '.join(re.sub(r'[^A-Z0-9 ]',' ',text).split())

def negative(text):
    return bool(set(normalize(text).split()) & {'NOT','NEVER','EXCEPT'})

def answer_key(text):
    value=normalize(text)
    return {'ISO 8 BONUS':'ISO 8 SET BONUS','NORN STONE OF CHAOS':'NORN STONES OF CHAOS'}.get(value,value)

def answer_bank():
    bank=dict(trivia_qa)
    # The archived file has case-only duplicates with contradictory answers.
    # The supplied Quizlet set identifies Norn Stones of Chaos for this question.
    for question in bank:
        if normalize(question)=='WHAT MATERIALS ARE NOT REQUIRED TO UPGRADE A CHARACTER TO TIER 3':
            bank[question]='Norn Stones of Chaos'
    bank.update(QUIZLET_ALIASES);bank.update(GAME_ANSWERS)
    # Read verified additions for each question so fixes need no GUI restart.
    try:
        extra=json.loads(EXTRA_ANSWERS.read_text(encoding='utf-8'))
        if extra.get('version')==1 and isinstance(extra.get('answers'),dict):
            known={normalize(q):answer_key(a) for q,a in bank.items()}
            for question,answer in extra['answers'].items():
                if not isinstance(question,str) or not isinstance(answer,str):continue
                if len(normalize(question))<18 or not 1<=len(answer.strip())<=120:continue
                if normalize(question) in known and known[normalize(question)]!=answer_key(answer):continue
                bank[question]=answer
    except (OSError,ValueError,TypeError,AttributeError):pass
    return bank

def lookup_answer(question,bank=None):
    query=normalize(question)
    if len(query)<18:return None
    bank=answer_bank() if bank is None else bank
    exact={answer_key(answer):answer for known,answer in bank.items() if normalize(known)==query}
    if exact:return next(iter(exact.values())) if len(exact)==1 else None
    scores={}
    for known,answer in bank.items():
        if negative(question)!=negative(known):continue
        target_type=re.search(r'AGAINST (COMBAT|SPEED|BLAST)',query)
        known_type=re.search(r'AGAINST (COMBAT|SPEED|BLAST)',normalize(known))
        if (target_type or known_type) and (not target_type or not known_type or target_type[1]!=known_type[1]):continue
        score=SequenceMatcher(None,query,normalize(known)).ratio()
        key=answer_key(answer)
        if score>scores.get(key,(0,None))[0]:scores[key]=(score,answer)
    ranked=sorted(scores.values(),reverse=True)
    if not ranked or ranked[0][0]<.91:return None
    if len(ranked)>1 and ranked[0][0]-ranked[1][0]<.045:return None
    return ranked[0][1]

def choose_option(question,options,bank=None):
    """Return the unique answer index, or None; order is never assumed."""
    expected=lookup_answer(question,bank)
    if expected is None or len(options)!=4 or any(not normalize(o) for o in options):return None
    target=answer_key(expected)
    exact=[i for i,o in enumerate(options) if answer_key(o)==target]
    if exact:return exact[0] if len(exact)==1 else None
    if len(target)<5:return None
    scores=sorted(((SequenceMatcher(None,target,answer_key(o)).ratio(),i) for i,o in enumerate(options)),reverse=True)
    if scores[0][0]>=.94 and scores[0][0]-scores[1][0]>=.08:return scores[0][1]
    return None
