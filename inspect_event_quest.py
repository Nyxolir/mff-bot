"""Capture an already-open Event Quest list. No claims or mission starts."""
from datetime import datetime,timezone
from dataclasses import asdict
from pathlib import Path
import json,time
from lib.background_input import AdbBackend
from lib.objective_reader import ObjectiveReader

def main():
    b=AdbBackend(instance_hint='Pie64');b.connect()
    folder=Path('diagnostics/event-quest-inspection');folder.mkdir(exist_ok=True)
    previous=None;same=0
    for page in range(9):
        stamp=datetime.now(timezone.utc);im,_=b.capture();e=ObjectiveReader().read(im)
        im.save(folder/f'page-{page}.png')
        (folder/f'page-{page}.json').write_text(json.dumps(asdict(e),indent=2),encoding='utf-8')
        if e.screen!='event_quest_objectives' or e.errors:raise RuntimeError(str(e))
        print(page,e.values,flush=True)
        signature=e.values['signature'];same=same+1 if signature==previous else 0;previous=signature
        if same>=2:return
        b.input_evidence=dict(screen=e.screen,phase='event_quest_inspection',captured_at=stamp.isoformat())
        b.send(800,550,scroll=('down',4),guard=lambda:(datetime.now(timezone.utc)-stamp).total_seconds()<30)
        time.sleep(2)
    raise RuntimeError('Quest inspection exceeded bound')

if __name__=='__main__':main()
