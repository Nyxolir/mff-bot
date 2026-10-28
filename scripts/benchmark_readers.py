"""Compare fresh vs persistent OCR on identical saved game screens. No game input."""
import base64,json,os,subprocess,sys,time
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from lib.ocr import js_runtime,recognize_batch_with_js
from lib.arena_reader import ArenaReader
from lib.sweep_reader import SweepReader
from lib.mission_reader import BoardReader

def fresh(requests,runtime):
    p=subprocess.run([runtime['node'],str(ROOT/'scripts/ocr_batch.cjs')],input=json.dumps(requests).encode(),capture_output=True,
        env=dict(os.environ,NODE_PATH=runtime['node_modules']),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=90)
    if p.returncode:raise RuntimeError(p.stderr.decode(errors='replace'))
    return json.loads(p.stdout)

def main():
    cases=[(ArenaReader,'otherworld_repeat_current.png'),(SweepReader,'epic_preparation_live.png'),(BoardReader,'arena_board.png')]
    outputs={};rows=[]
    for label,recognize in [('fresh',fresh),('persistent',recognize_batch_with_js)]:
        with patch('lib.mission_reader.recognize_batch_with_js',recognize):
            for reader,name in cases:
                start=time.perf_counter();evidence=reader().read(ROOT/'tests/fixtures'/name);seconds=time.perf_counter()-start
                if label=='fresh':outputs[name]=asdict(evidence)
                elif outputs[name]!=asdict(evidence):raise AssertionError('OCR behavior changed: '+name)
                rows.append({'engine':label,'fixture':name,'screen':evidence.screen,'seconds':round(seconds,4)})
    before=sum(r['seconds'] for r in rows if r['engine']=='fresh');after=sum(r['seconds'] for r in rows if r['engine']=='persistent')
    report={'passed':True,'readings':rows,'fresh_total_seconds':before,'persistent_total_seconds':after,'speedup':before/after,
        'scope':'Saved-screen reader timings on this PC. Same evidence including OCR text required. Includes cold start on first persistent read; excludes screenshot capture, game loading, waits and inputs.'}
    (ROOT/'diagnostics/reader-performance.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
