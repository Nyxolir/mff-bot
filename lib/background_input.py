"""Local emulator input/capture without Windows focus or physical mouse input."""
from io import BytesIO
from pathlib import Path
import re
import subprocess
import struct
import threading
import time
import json
from datetime import datetime,timezone
from PIL import Image

CONFIG=Path('C:/ProgramData/BlueStacks_nxt/bluestacks.conf')
ADB=Path('C:/Program Files/BlueStacks_nxt/HD-Adb.exe')
_backend=None
_required=False

def instance_record(text,instance_hint=None):
    records={}
    for name,key,value in re.findall(r'^bst\.instance\.([^.]+)\.(adb_port|status\.adb_port|display_name)="([^"\r\n]*)"\s*$',text,re.M):
        records.setdefault(name,{})[key]=value
    if instance_hint:
        records={name:fields for name,fields in records.items() if instance_hint in (name,fields.get('display_name'))}
        if len(records)!=1:raise RuntimeError('Could not uniquely match the open BlueStacks window to its instance')
    elif len(records)!=1:
        raise RuntimeError('Multiple BlueStacks instances configured; connect through the open instance window')
    if not records:raise RuntimeError('No configured BlueStacks ADB instance')
    return next(iter(records.items()))

def instance_port(text,instance_hint=None):
    _,fields=instance_record(text,instance_hint)
    # The runtime status port can differ from the original configured port.
    for key in ('status.adb_port','adb_port'):
        value=fields.get(key,'')
        if value.isdigit() and 1024<=int(value)<=65535:return int(value)
    raise RuntimeError('BlueStacks ADB installation/port unavailable')

def set_backend(backend=None,required=False):
    global _backend,_required
    _backend,_required=backend,required

def configured_backend():
    if _required and _backend is None:
        from lib.resource_check import InputNotSent
        raise InputNotSent('Background input is not connected. Enable BlueStacks Settings > Advanced > Android Debug Bridge, then Connect BlueStacks. No mouse fallback was used.')
    return _backend

class AdbBackend:
    def __init__(self,executable=ADB,config=CONFIG,instance_hint=None,server_port=5042):
        self.executable=Path(executable);self.config=Path(config)
        self.instance_hint=instance_hint;self.server_port=server_port
        self.instance_name=None
        self.serial=None;self.connected=False;self.lock=threading.RLock()
        self.device_size=None

    def _run(self,args,timeout=10):
        result=subprocess.run([str(self.executable),'-P',str(self.server_port),*args],capture_output=True,timeout=timeout,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:
            raise RuntimeError('BlueStacks background connection failed: '+result.stderr.decode(errors='replace').strip()[-200:])
        return result.stdout

    def selected_instance(self):
        # Read only: enabling debugging is a user-operated emulator setting.
        text=self.config.read_text(encoding='utf-8')
        if not re.search(r'^bst\.enable_adb_access="1"\s*$',text,re.M):
            raise RuntimeError('Enable BlueStacks Settings > Advanced > Android Debug Bridge, then Connect BlueStacks. Background mode never uses your mouse.')
        return instance_record(text,self.instance_name or self.instance_hint)

    def connect(self):
        name,_=self.selected_instance()
        self.instance_name=name
        port=instance_port(self.config.read_text(encoding='utf-8'),name)
        if not 1024<=port<=65535 or not self.executable.is_file():raise RuntimeError('BlueStacks ADB installation/port unavailable')
        self.serial=f'127.0.0.1:{port}'
        with self.lock:
            devices=self._run(['devices']).decode(errors='replace')
            native=f'emulator-{port-1}'
            if re.search(r'^'+re.escape(native)+r'\s+device\s*$',devices,re.M):
                self.serial=native
            last_error='BlueStacks ADB is not ready'
            for attempt in range(3):
                if self.serial.startswith('127.0.0.1:'):
                    reply=self._run(['connect',self.serial]).decode(errors='replace').strip()
                    if any(word in reply.lower() for word in ('unable','failed','refused')):
                        last_error=reply;time.sleep(.3);continue
                try:
                    if self._run(['-s',self.serial,'get-state']).strip()==b'device':break
                except RuntimeError as error:last_error=str(error)
                time.sleep(.3)
            else:raise RuntimeError('BlueStacks ADB is not ready: '+last_error)
        self.connected=True
        self.device_size=None
        try:self.initial_frame=self.capture()
        except Exception:
            self.connected=False;raise

    def capture(self):
        if not self.connected:raise RuntimeError('Connect BlueStacks background mode first')
        # BlueStacks occasionally returns a partial frame, especially at 4K.
        # Retry only capture; never reuse a truncated frame for recognition.
        with self.lock:
            for attempt in range(3):
                try:data=self._run(['-s',self.serial,'exec-out','screencap']+(['-p'] if attempt else []))
                except subprocess.TimeoutExpired:
                    if attempt==2:raise
                    continue
                except RuntimeError as error:
                    if attempt==2 or not any(word in str(error).lower() for word in ('device','offline','closed')):raise
                    # Reconnect for a new read only. Spending inputs are never
                    # retried after an uncertain transport failure.
                    if self.serial.startswith('127.0.0.1:'):self._run(['connect',self.serial])
                    time.sleep(.3);continue
                try:
                    if data.startswith(b'\x89PNG\r\n\x1a\n'):
                        image=Image.open(BytesIO(data));image.load()
                    else:
                        # Raw Android frames avoid costly 4K PNG compression.
                        if len(data)<12:raise ValueError('Incomplete raw header')
                        w,h,fmt=struct.unpack('<III',data[:12])
                        if not 0<w<=8192 or not 0<h<=8192:raise ValueError('Invalid raw dimensions')
                        modes={1:('RGBA',4),2:('RGBX',4),3:('RGB',3),5:('BGRA',4)}
                        if fmt not in modes:raise ValueError('Unsupported raw pixel format')
                        mode,channels=modes[fmt];offset=len(data)-w*h*channels
                        if offset not in (12,16):raise ValueError('Incomplete raw frame')
                        image=Image.frombytes('RGBA' if mode=='BGRA' else mode,(w,h),data[offset:],'raw',mode)
                    if max(high for low,high in image.convert('RGB').getextrema())<5:raise ValueError('Blank Android frame')
                    break
                except (OSError,ValueError):continue
            else:raise RuntimeError('Background screenshot incomplete after three captures; reconnect')
        width,height=image.size
        if width<640 or height<360 or width*9!=height*16:
            raise RuntimeError('Background mode needs the game in landscape 16:9; received '+str(image.size))
        if self.device_size is not None and image.size!=self.device_size:
            raise RuntimeError('Android resolution changed during the session; reconnect to refresh tap scaling')
        self.device_size=image.size
        image=image.convert('RGB')
        if image.size!=(1280,720):image=image.resize((1280,720),Image.Resampling.LANCZOS)
        # These bytes feed only the local GUI preview; favor encoding speed.
        normalized=BytesIO();image.save(normalized,format='PNG',compress_level=1);data=normalized.getvalue()
        return image,data

    def send(self,x,y,scroll=None,drag_to=None,key=None,guard=None):
        from lib.resource_check import InputNotSent
        if not self.connected:raise InputNotSent('Background input disconnected; no mouse fallback')
        if self.device_size is None:raise InputNotSent('Capture the Android screen before sending input')
        if not (type(x) is int and type(y) is int and 0<=x<1280 and 0<=y<720):raise ValueError('Invalid game point')
        width,height=self.device_size
        def point(px,py):return str(min(width-1,round(px*width/1280))),str(min(height-1,round(py*height/720)))
        if key is not None:
            if key!='back':raise ValueError('Unsupported Android key')
            action=['keyevent','4']
        elif drag_to is not None:
            if (x,y,drag_to) not in ((500,658,(80,658)),(80,658,(500,658)),(1030,318,(220,318)),(220,318,(1030,318)),(640,518,(640,228))):
                raise ValueError('Unsupported Android swipe')
            action=['swipe',*point(x,y),*point(*drag_to),'650']
        elif scroll:
            direction,clicks=scroll
            if direction not in ('up','down') or type(clicks) is not int or not 1<=clicks<=8:raise ValueError('Invalid board scroll')
            start=600 if direction=='down' else 170
            end=start+(-1 if direction=='down' else 1)*min(480,clicks*100)
            if direction=='up' and getattr(self,'input_evidence',{}).get('screen') in ('content_board','trivia_list'):
                # The old start lay on the fixed board header, outside its list.
                start=250;end=min(680,start+clicks*100)
            action=['swipe',*point(x,start),*point(x,end),'450']
        else:action=['tap',*point(x,y)]
        with self.lock:
            if guard is not None and not guard():raise InputNotSent('Queue stopped or evidence expired before Android input')
            evidence=getattr(self,'input_evidence',{})
            stamp=evidence.get('captured_at')
            if stamp and getattr(self,'last_input_at',None):
                try:observed=datetime.fromisoformat(stamp)
                except (TypeError,ValueError):raise InputNotSent('Input evidence timestamp unreadable')
                if observed<=self.last_input_at:raise InputNotSent('Fresh screenshot required after previous Android input')
            if key is None and scroll is None and drag_to is None and (x,y)==(1185,36) and evidence.get('screen') in ('game_home','we_home'):
                raise InputNotSent('Home control is the Settings gear on the home screen; no tap sent')
            audit=getattr(self,'input_audit_path',None)
            if audit:
                try:
                    audit=Path(audit);audit.parent.mkdir(parents=True,exist_ok=True)
                    with audit.open('a',encoding='utf-8') as stream:
                        stream.write(json.dumps({'time':datetime.now(timezone.utc).isoformat(),'event':'input_attempt','action':action,'evidence':getattr(self,'input_evidence',{})})+'\n')
                except OSError:pass
            try:self._run(['-s',self.serial,'shell','input',*action],timeout=10)
            finally:self.last_input_at=datetime.now(timezone.utc)

    def restart_game(self,guard=None):
        """Restart only the installed Future Fight package; leave BlueStacks running."""
        with self.lock:
            if not self.connected or (guard and not guard()):raise RuntimeError('Recovery cancelled')
            packages=self._run(['-s',self.serial,'shell','pm','list','packages']).decode(errors='replace').splitlines()
            matches=[p.removeprefix('package:').strip() for p in packages if p.strip()=='package:com.netmarble.mherosgb']
            if len(matches)!=1:raise RuntimeError('Installed Future Fight package could not be verified')
            package=matches[0]
            if guard and not guard():raise RuntimeError('Recovery cancelled')
            self._run(['-s',self.serial,'shell','input','keyevent','3'])
            if guard and not guard():raise RuntimeError('Recovery cancelled')
            self._run(['-s',self.serial,'shell','am','force-stop',package])
            self._run(['-s',self.serial,'shell','monkey','-p',package,'-c','android.intent.category.LAUNCHER','1'])

    def launch_game(self,guard=None):
        """Open the verified installed game without stopping it or replaying input."""
        with self.lock:
            if not self.connected or (guard and not guard()):raise RuntimeError('Recovery cancelled')
            package='com.netmarble.mherosgb'
            packages=self._run(['-s',self.serial,'shell','pm','list','packages']).decode(errors='replace').splitlines()
            if sum(line.strip()=='package:'+package for line in packages)!=1:
                raise RuntimeError('Installed Future Fight package could not be verified')
            if guard and not guard():raise RuntimeError('Recovery cancelled')
            self._run(['-s',self.serial,'shell','monkey','-p',package,'-c','android.intent.category.LAUNCHER','1'])

