"""Recover a vanished emulator or its read transport without retrying game inputs."""
import csv
from dataclasses import dataclass
from datetime import datetime,timezone
import io
import os
from pathlib import Path
import re
import subprocess
import time

def capture_failure(message):
    text=message.lower()
    return (any(word in text for word in ('incomplete capture','screenshot incomplete','blank android frame','incomplete raw frame'))
            or ('screencap' in text and 'timed out' in text))

def transport_failure(message):
    # A decoder's old "reconnect" hint is not evidence of a lost device.
    return not capture_failure(message) and any(word in message.lower() for word in ('device','offline','closed','connect','transport'))

def selected_player_pid(handle):
    import ctypes
    from ctypes import wintypes
    pid=wintypes.DWORD()
    user32=ctypes.WinDLL('user32',use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    if not user32.GetWindowThreadProcessId(handle,ctypes.byref(pid)) or not pid.value:
        raise RuntimeError('Could not identify the selected BlueStacks process')
    executable=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/tasklist.exe'
    result=subprocess.run([str(executable),'/FI','PID eq '+str(pid.value),'/FO','CSV','/NH'],capture_output=True,timeout=10,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    rows=list(csv.reader(io.StringIO(result.stdout.decode(errors='replace'))))
    if result.returncode or len(rows)!=1 or len(rows[0])<2 or rows[0][0].casefold()!='hd-player.exe' or rows[0][1]!=str(pid.value):
        raise RuntimeError('Selected window is not a verified BlueStacks player; no process stopped')
    return pid.value

def stop_selected_player(backend,title,handle,window_probe,guard):
    if not guard() or window_probe(title)!=handle:raise RuntimeError('BlueStacks restart cancelled or selected window changed')
    pid=selected_player_pid(handle)
    if not guard() or window_probe(title)!=handle or selected_player_pid(handle)!=pid:
        raise RuntimeError('Selected BlueStacks identity changed; no process stopped')
    executable=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/taskkill.exe'
    result=subprocess.run([str(executable),'/PID',str(pid),'/T','/F'],capture_output=True,timeout=20,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise RuntimeError('Could not stop the verified BlueStacks player; no duplicate launched')
    backend.connected=False
    # Reset only this bot's private bridge, never another app's ADB server.
    if guard() and getattr(backend,'server_port',None)==5042:
        try:backend._run(['kill-server'],timeout=10)
        except Exception:pass

def players_running():
    executable=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/tasklist.exe'
    result=subprocess.run([str(executable),'/FO','CSV','/NH'],capture_output=True,timeout=10,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise RuntimeError('Could not verify whether BlueStacks is still running')
    rows=list(csv.reader(io.StringIO(result.stdout.decode(errors='replace'))))
    if not rows or any(len(row)<2 or not row[1].isdigit() for row in rows):
        raise RuntimeError('Process list unreadable; emulator launch suppressed')
    return any(row[0].casefold()=='hd-player.exe' for row in rows)

@dataclass
class RecoveredEmulator:
    frame:tuple
    observed:datetime
    handle:int
    launched:bool
    game_opened:bool

def recover_connection(backend,window_probe,guard,progress=lambda message:None,timeout=150,restart_after=30,restart_first=False):
    name,fields=backend.selected_instance()
    if not re.fullmatch(r'[A-Za-z0-9_-]+',name):raise RuntimeError('Invalid remembered BlueStacks instance')
    title=fields.get('display_name') or backend.instance_hint
    if not title:raise RuntimeError('Remembered BlueStacks instance has no window identity')
    executable=backend.executable.with_name('HD-Player.exe')
    if not executable.is_file():raise RuntimeError('Installed BlueStacks player executable unavailable')
    started=time.monotonic();deadline=started+timeout;launched=False;stopped=False;last_error='Waiting for the selected instance to boot'
    while time.monotonic()<deadline:
        if not guard():raise RuntimeError('BlueStacks recovery cancelled')
        running=players_running()
        if not running and not launched:
            # A lost ADB device alone is insufficient evidence to launch another
            # emulator. Require a readable process list with no player present.
            if not guard():raise RuntimeError('BlueStacks recovery cancelled')
            subprocess.Popen([str(executable),'--instance',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            launched=True;progress('BlueStacks exited; starting remembered instance '+name)
        handle=window_probe(title) if running else None
        if handle:
            if restart_first and not stopped:
                stop_selected_player(backend,title,handle,window_probe,guard);stopped=True
                progress('Restarting verified BlueStacks instance '+name+'; saved submissions will not be replayed')
                time.sleep(2);continue
            try:
                if not guard():raise RuntimeError('BlueStacks recovery cancelled')
                backend.connect()
                if not guard():raise RuntimeError('BlueStacks recovery cancelled')
                if window_probe(title)!=handle:raise RuntimeError('Selected instance window changed during reconnect')
                from lib.android_home import android_home
                game_opened=bool(launched or android_home(backend.initial_frame[0]))
                if game_opened:backend.launch_game(guard)
                frame=backend.capture()
                if not guard():raise RuntimeError('BlueStacks recovery cancelled')
                if window_probe(title)!=handle:raise RuntimeError('Selected instance window changed during capture')
                return RecoveredEmulator(frame,datetime.now(timezone.utc),handle,launched,game_opened)
            except Exception as error:
                backend.connected=False;last_error=str(error)
                if not stopped and not launched and time.monotonic()-started>=restart_after:
                    stop_selected_player(backend,title,handle,window_probe,guard);stopped=True
                    progress('Persistent ADB failure: restarting verified BlueStacks instance '+name+' once; saved submissions retained')
        elif running:
            last_error='A player is running but the remembered instance window is absent; no duplicate launch'
        time.sleep(2)
    raise RuntimeError('BlueStacks recovery timed out: '+last_error)
