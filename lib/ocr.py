"""Lazy Tesseract 5 adapter: importing game definitions never launches OCR."""
import os
import io
import json
from pathlib import Path
import shutil
import subprocess
from threading import Lock
from threading import Thread
from queue import Queue,Empty
import atexit
from lib.app_paths import data_path,resource_root

AUTOMATIC_PAGE_SEGMENTATION = 3
RAW_LINE_PAGE_SEGMENTATION = 13
ROOT = resource_root()


class _JsOcrSession:
    """Serialize calls to one local OCR process, with bounded waits and cleanup."""
    def __init__(self):self.lock=Lock();self.process=None;self.lines=None;self.runtime_key=None

    def close(self):
        process=self.process;self.process=None
        if process is not None:
            try:
                process.stdin.close()
                process.wait(timeout=2)
            except (OSError,subprocess.TimeoutExpired):
                process.kill();process.wait(timeout=2)
            finally:
                if process.stdout:process.stdout.close()

    def recognize(self,requests,runtime):
        with self.lock:
            key=(runtime['node'],runtime['node_modules'])
            if self.process is None or self.process.poll() is not None or self.runtime_key!=key:
                self.close();self.runtime_key=key;self.lines=Queue()
                environment=dict(os.environ,NODE_PATH=runtime['node_modules'],MFF_OCR_CACHE=str(data_path('.cache/ocr')))
                model=ROOT/'ocr/tessdata/eng.traineddata'
                if model.is_file():environment['MFF_OCR_LANG_PATH']=str(model.parent)
                self.process=subprocess.Popen([runtime['node'],str(ROOT/'scripts/ocr_server.cjs')],
                    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                    env=environment,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                def read_lines(stream,output):
                    try:
                        for line in stream:output.put(line)
                    finally:output.put(None)
                Thread(target=read_lines,args=(self.process.stdout,self.lines),daemon=True).start()
            try:
                self.process.stdin.write(json.dumps(requests).encode()+b'\n');self.process.stdin.flush()
                line=self.lines.get(timeout=90)
                if line is None:raise RuntimeError('OCR worker exited')
                response=json.loads(line)
                if 'error' in response:raise RuntimeError('OCR failed: '+response['error'])
                result=response['result']
                if set(result)!={r['name'] for r in requests} or any(not isinstance(v,str) for v in result.values()):raise ValueError('Invalid OCR response')
                return result
            except (OSError,Empty,ValueError,RuntimeError,KeyError):
                self.close();raise


_js_session=_JsOcrSession()
atexit.register(_js_session.close)

def recognize_batch_with_js(requests,runtime=None):
    runtime=runtime or js_runtime()
    if not runtime:raise RuntimeError('OCR runtime is not configured')
    return _js_session.recognize(requests,runtime)


def native_executable():
    configured = os.environ.get("MFF_TESSERACT_CMD")
    if configured:
        return configured
    if (ROOT/'ocr/node.exe').is_file():
        return None
    candidate = shutil.which("tesseract")
    installed = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Tesseract-OCR/tesseract.exe"
    return candidate or (str(installed) if installed.is_file() else None)


def js_runtime():
    bundled={'node':str(ROOT/'ocr/node.exe'),'node_modules':str(ROOT/'ocr/node_modules')}
    if Path(bundled['node']).is_file() and (Path(bundled['node_modules'])/'tesseract.js/package.json').is_file():
        return bundled
    settings = data_path('settings/ocr-runtime.local.json')
    if not settings.is_file():
        return None
    data = json.loads(settings.read_text(encoding="utf-8"))
    if not Path(data["node"]).is_file() or not Path(data["node_modules"]).is_dir():
        return None
    return data


def recognize_with_js(image, whitelist, psm):
    from PIL import Image
    runtime = js_runtime()
    if not runtime:
        raise RuntimeError("Install Tesseract 5 or configure settings/ocr-runtime.local.json")
    output = io.BytesIO()
    Image.fromarray(image).save(output, format="PNG")
    import base64
    return recognize_batch_with_js([{'name':'text','image':base64.b64encode(output.getvalue()).decode('ascii'),
        'whitelist':whitelist or '', 'psm':psm}],runtime)['text']


class TesseractPool:
    def __init__(self, processes=None, language="eng", data_folder=None):
        # Upstream mff.traineddata targets Tesseract 3. Use modern English
        # data and the caller's numeric whitelist instead.
        self.language = "eng" if language == "mff+eng" else language
        self._lock = Lock()

    def image_to_string(self, image, whitelist=None, page_segmentation=3):
        import pytesseract
        executable = native_executable()
        if not isinstance(page_segmentation, int) or not 0 <= page_segmentation <= 13:
            raise ValueError("Invalid OCR page segmentation mode")
        config = f"--psm {page_segmentation} --oem 3"
        if whitelist:
            if any(c.isspace() or c in '\"\x00' for c in whitelist):
                raise ValueError("Unsupported OCR whitelist characters")
            config += f" -c tessedit_char_whitelist={whitelist}"
        with self._lock:
            if not executable:
                if self.language != "eng":
                    raise RuntimeError("Portable OCR currently supports English only")
                return recognize_with_js(image, whitelist, page_segmentation)
            pytesseract.pytesseract.tesseract_cmd = executable
            return pytesseract.image_to_string(
                image, lang=self.language, config=config, timeout=10
            ).strip()
