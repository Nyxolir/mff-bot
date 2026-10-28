"""Inspect fresh board pages using verified navigation; never start a mission."""
from datetime import datetime,timezone
from pathlib import Path
import json,time
from dataclasses import asdict
from lib.background_input import AdbBackend
from lib.story_reader import StoryReader
from lib.objective_reader import ObjectiveReader
from lib.screen_reader import ScreenReader
from lib.mission_reader import BoardReader

def main():
    backend=AdbBackend(instance_hint='Pie64');backend.connect()
    backend.input_audit_path=Path('diagnostics/input-actions.jsonl')
    folder=Path('diagnostics/content-board-inspection');folder.mkdir(exist_ok=True)
    def capture():
        stamp=datetime.now(timezone.utc);im,_=backend.capture();return im,stamp
    def act(e,stamp,x,y,scroll=None):
        backend.input_evidence=dict(screen=e.screen,phase='board_inspection',captured_at=stamp.isoformat())
        backend.send(x,y,scroll=scroll,guard=lambda:(datetime.now(timezone.utc)-stamp).total_seconds()<30)
        time.sleep(2)
    image,stamp=capture();e=StoryReader().read(image)
    if e.screen=='story_ultimate':act(e,stamp,1185,36)
    image,stamp=capture();e=ObjectiveReader().read(image)
    if e.screen=='game_home':act(e,stamp,1249,36)
    image,stamp=capture();e=ScreenReader().read(image,resource_check=True)
    if e.screen=='navigation_menu':act(e,stamp,630,642)
    for page in range(4):
        image,stamp=capture();e=BoardReader().read(image)
        if e.screen!='content_board' or e.errors:raise RuntimeError('Board not verified; no further input')
        image.save(folder/f'page-{page}.png')
        (folder/f'page-{page}.json').write_text(json.dumps(asdict(e),indent=2),encoding='utf-8')
        print(json.dumps(dict(page=page,tiles=e.values['tiles']),ensure_ascii=True),flush=True)
        if page<3:act(e,stamp,1000,500,scroll=('down',4))
if __name__=='__main__':main()
