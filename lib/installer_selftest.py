"""Offline installed-build validation. Never connects to a player or starts a queue."""
import json
from pathlib import Path
from lib.app_paths import data_root,resource_root


def run_self_test(window,report_path):
    from PIL import Image,ImageDraw,ImageFont
    import numpy as np
    import os
    from lib.ocr import recognize_with_js,_js_session,js_runtime
    from lib.trivia import lookup_answer
    root=resource_root()
    assert not window.queue_engine.running and window.handle is None
    assert (root/'images/current/trivia_start_button.png').is_file()
    assert (root/'ocr/tessdata/eng.traineddata').is_file()
    assert js_runtime() is not None
    sample=Image.new('RGB',(600,90),'white')
    font=ImageFont.truetype(str(Path(os.environ['WINDIR'])/'Fonts/arial.ttf'),40)
    ImageDraw.Draw(sample).text((20,12),'DAILY TRIVIA',font=font,fill='black')
    text=recognize_with_js(np.asarray(sample),'ABCDEFGHIJKLMNOPQRSTUVWXYZ ',7)
    assert text.strip()=='DAILY TRIVIA',repr(text)
    assert lookup_answer('Which of the following characters is not a god of Olympus?')=='Loki'
    assert lookup_answer('What is the name of the sword wielded by Silver Samurai?')=='Muramasa Blade'
    fixtures=os.environ.get('MFF_SELFTEST_FIXTURES')
    fixture_checks=0
    if fixtures:
        from lib.trivia_reader import TriviaReader
        from lib.trivia import choose_option
        for name,answer in [('trivia_olympus_oct28.png','Loki'),('trivia_silver_samurai_oct28.png','Muramasa Blade')]:
            evidence=TriviaReader().read(Path(fixtures)/name)
            assert evidence.screen=='trivia_question' and not evidence.errors
            index=choose_option(evidence.values['question'],evidence.values['options'])
            assert index is not None and evidence.values['options'][index]==answer
            fixture_checks+=1
    from lib.gui.widgets import completion_cache,story_controls,gbr_cache,objective_cache,trivia_controls,dispatch_supplies_controls
    from lib.world_event import CACHE
    paths=[completion_cache.CACHE,story_controls.STORY_STATE,gbr_cache.CACHE,objective_cache.CACHE,trivia_controls.TRIVIA_CACHE,dispatch_supplies_controls.SUPPLY_STATE,CACHE]
    assert all(p.is_relative_to(data_root()) for p in paths)
    window._save()
    assert (data_root()/'settings/gui/modern-desktop.json').is_file()
    window.queue_timer.stop();window.timer.stop()
    _js_session.close()
    report={'passed':True,'gui_constructed':True,'offline_ocr':text.strip(),'bundled_answers':True,'per_user_state':True,'private_fixture_checks':fixture_checks,'queue_started':False,'game_connected':False}
    Path(report_path).write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0
