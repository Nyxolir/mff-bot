"""Verified public-release downloads and durable installer handoff data."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sys
import time
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

from lib.app_paths import data_root, resource_root

REPOSITORY='Nyxolir/mff-bot'
LATEST='https://api.github.com/repos/'+REPOSITORY+'/releases/latest'
INSTALLER='MFF-Bot-Setup.exe'
MANIFEST='BUILD-MANIFEST.json'
MAX_INSTALLER=512*1024*1024
CHECK_INTERVAL=timedelta(hours=4)


def version_tuple(value):
    if not isinstance(value,str) or not re.fullmatch(r'(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)',value):
        raise ValueError('Invalid update version')
    parts=tuple(map(int,value.split('.')))
    if max(parts)>65535:raise ValueError('Update version exceeds Windows limits')
    return parts


def installed_version():
    if not getattr(sys,'frozen',False):return None
    try:
        value=json.loads((resource_root()/'build-info.json').read_text(encoding='utf-8'))['version']
        version_tuple(value);return value
    except (OSError,ValueError,KeyError,TypeError):return None


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    with temporary.open('w',encoding='utf-8') as stream:
        json.dump(value,stream,indent=2);stream.flush();os.fsync(stream.fileno())
    temporary.replace(path)


def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def trusted_url(url):
    parsed=urlsplit(url)
    if (parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in (None,443)
            or parsed.fragment or parsed.hostname not in {'api.github.com','github.com','release-assets.githubusercontent.com','objects.githubusercontent.com'}):
        raise ValueError('Update URL is outside GitHub release hosting')
    return url


class ReleaseRedirects(HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        trusted_url(newurl)
        return super().redirect_request(request,fp,code,msg,headers,newurl)


def open_release_url(url):
    request=Request(trusted_url(url),headers={'User-Agent':'Nyxolir-MFFBot-Updater','Accept':'application/vnd.github+json'})
    return build_opener(ReleaseRedirects()).open(request,timeout=20)


def read_asset(url,limit,opener=open_release_url,cancelled=lambda:False):
    chunks=[];received=0;deadline=time.monotonic()+30
    with opener(url) as response:
        while True:
            if cancelled():raise InterruptedError('Update metadata check cancelled')
            if time.monotonic()>deadline:raise TimeoutError('Update metadata timed out')
            content=getattr(response,'read1',response.read)(min(65536,limit+1-received))
            if not content:break
            chunks.append(content);received+=len(content)
            if received>limit:raise ValueError('Update metadata exceeds its size limit')
    return b''.join(chunks)


def parse_release(release,current):
    if release.get('draft') is not False or release.get('prerelease') is not False:
        raise ValueError('Only published stable releases can update this app')
    tag=release.get('tag_name','');version=tag.removeprefix('v')
    if tag!='v'+version:raise ValueError('Invalid update release tag')
    if version_tuple(version)<=version_tuple(current):return None
    commit=release.get('target_commitish','')
    if not re.fullmatch(r'[0-9a-f]{40}',commit):raise ValueError('Update release must identify its exact source revision')
    assets={}
    for name in (INSTALLER,MANIFEST):
        matches=[a for a in release.get('assets',[]) if a.get('name')==name]
        if len(matches)!=1:raise ValueError('Release asset missing or duplicated: '+name)
        asset=matches[0];digest=asset.get('digest','')
        expected='https://github.com/'+REPOSITORY+'/releases/download/'+tag+'/'+name
        if asset.get('browser_download_url')!=expected or not re.fullmatch(r'sha256:[0-9a-f]{64}',digest):
            raise ValueError('Release asset identity/digest is invalid')
        size=asset.get('size')
        if type(size) is not int or not 0<size<=(MAX_INSTALLER if name==INSTALLER else 256*1024):
            raise ValueError('Release asset size is invalid')
        assets[name]={'url':expected,'sha256':digest[7:],'size':size}
    return {'version':version,'source_commit':commit,'assets':assets}


def fetch_update(current,cache,failed_version=None,opener=open_release_url,cancelled=lambda:False,progress=lambda value:None):
    """No install or game actions. A partial/unverified file is never returned."""
    release=json.loads(read_asset(LATEST,1024*1024,opener,cancelled))
    candidate=parse_release(release,current)
    if candidate is None or candidate['version']==failed_version:return None
    if cancelled():raise InterruptedError('Update check cancelled')
    metadata=candidate['assets'][MANIFEST]
    raw=read_asset(metadata['url'],256*1024,opener,cancelled)
    if len(raw)!=metadata['size'] or hashlib.sha256(raw).hexdigest()!=metadata['sha256']:
        raise ValueError('Release manifest checksum mismatch')
    manifest=json.loads(raw)
    if (manifest.get('version')!=candidate['version'] or manifest.get('source_commit')!=candidate['source_commit']
            or manifest.get('self_test',{}).get('passed') is not True
            or manifest.get('installation_test',{}).get('passed') is not True
            or manifest.get('artifacts',{}).get(INSTALLER)!=candidate['assets'][INSTALLER]['sha256']):
        raise ValueError('Installer does not match a verified source build')
    directory=Path(cache)/candidate['version'];directory.mkdir(parents=True,exist_ok=True)
    target=directory/INSTALLER;asset=candidate['assets'][INSTALLER]
    if not (target.is_file() and target.stat().st_size==asset['size'] and sha256(target)==asset['sha256']):
        temporary=directory/(INSTALLER+'.part');digest=hashlib.sha256();received=0
        deadline=time.monotonic()+15*60
        try:
            with opener(asset['url']) as response,temporary.open('wb') as stream:
                while True:
                    if cancelled():raise InterruptedError('Update download cancelled')
                    if time.monotonic()>deadline:raise TimeoutError('Update download exceeded 15 minutes')
                    chunk=getattr(response,'read1',response.read)(1024*1024)
                    if not chunk:break
                    received+=len(chunk)
                    if received>asset['size']:raise ValueError('Installer exceeds its declared size')
                    stream.write(chunk);digest.update(chunk);progress(received*100//asset['size'])
                stream.flush();os.fsync(stream.fileno())
            if received!=asset['size'] or digest.hexdigest()!=asset['sha256']:
                raise ValueError('Installer download incomplete or checksum mismatch')
            temporary.replace(target)
        finally:
            if temporary.exists():temporary.unlink()
    if cancelled():raise InterruptedError('Update download cancelled')
    candidate.update(installer=str(target.resolve()),sha256=asset['sha256'])
    return candidate


def update_blocker(window):
    """Every gate must be quiet before the updater requests its final idle scan."""
    if window.queue_engine.pending or window.world_event_state.pending or window.world_event_state.started:return 'a submitted outcome is pending'
    if getattr(window,'queue_held',set()):return 'a held outcome needs verification'
    if getattr(getattr(window,'dispatch_supply_state',None),'pending',None):return 'a Dispatch claim is pending'
    if window.story_restart_protected():return 'Story is active'
    if window.emulator_recovering():return 'emulator recovery is active'
    if getattr(window,'restart_task',None) is not None and window.restart_task.isRunning():return 'game recovery is active'
    if window.busy or window.frame_task is not None:return 'a screen capture/check is active'
    for field in ('trivia_active','objective_active','resource_active','world_event_active','dispatch_supply_active',
                  'board_check_active','queue_recovering','session_reload_deadline','review_mode','queue_target',
                  'epic_preparation','converging_preparation'):
        if getattr(window,field,None):return 'a content task is active'
    if window.trivia_session and window.trivia_session.pending and not window.trivia_session.done:
        return 'a trivia answer is pending'
    return None


def saved_update_blocker(root=None):
    """Unreadable or still-submitted disk state cannot authorize a restart."""
    root=Path(root or data_root())/'settings/gui'
    for name,fields in (('pending-clear.json',('pending','contribution_followup','contribution_submitted','contribution_acquire_submitted')),
                        ('world-event.json',('pending','started'))):
        try:
            value=json.loads((root/name).read_text(encoding='utf-8'))
            if not isinstance(value,dict):return 'saved submission state is unreadable'
            if 'pending' not in value:return 'saved submission state is unreadable'
            if name=='world-event.json' and any(type(value.get(field)) is not bool for field in fields):return 'saved submission state is unreadable'
            if name=='pending-clear.json' and value['pending'] is not None and not isinstance(value['pending'],list):return 'saved submission state is unreadable'
            if any(value.get(field) for field in fields):return 'a saved submission needs verification'
        except FileNotFoundError:pass
        except (OSError,ValueError,TypeError):return 'saved submission state is unreadable'
    return None


def idle_update_evidence(evidence,observed,now,live):
    if not live or evidence.errors or not timedelta(0)<=now-observed<=timedelta(seconds=30):return False
    if evidence.screen in {'game_home','we_home','navigation_menu','content_board','status_board','dispatch_supplies_map','gbr_main'}:return True
    # An incomplete quiz can need an answer-bank update. Its undimmed,
    # independently navigable Challenges page is idle once the trivia session
    # has ended without a pending answer; update_blocker enforces that latch.
    if evidence.screen in {'challenge_navigation','daily_objectives','challenges_other_tab'}:
        return evidence.values.get('home_available') is True and evidence.values.get('menu_available') is True
    return evidence.screen=='trivia_list' and evidence.values.get('completed_summary_verified') is True


def prepare_handoff(candidate,resume,connected,minimized,executable=None,root=None,helper=None,queue_index=0):
    root=Path(root or data_root()).resolve();exe=Path(executable or sys.executable).resolve()
    version_tuple(candidate['version'])
    directory=root/'.cache/updates'/candidate['version'];directory=directory.resolve()
    installer=Path(candidate['installer']).resolve()
    if installer!=directory/INSTALLER or sha256(installer)!=candidate['sha256']:
        raise ValueError('Cached installer changed before handoff')
    if exe.name!='MFF Bot.exe' or not exe.is_file():raise ValueError('Updater requires an installed MFF Bot')
    source=Path(helper or resource_root()/'updater/MFF Bot Update Helper.exe')
    copied=directory/'MFF Bot Update Helper.exe';shutil.copyfile(source,copied)
    if sha256(copied)!=sha256(source):raise ValueError('Updater helper copy did not verify')
    plan={'protocol':1,'token':secrets.token_hex(16),'version':candidate['version'],'created_at':datetime.now(timezone.utc).isoformat(),
          'installer':str(installer),'sha256':candidate['sha256'],'executable':str(exe),'profile':str(root),
          'parent_pid':os.getpid(),'resume':bool(resume),'connected':bool(connected),'minimized':bool(minimized),'queue_index':queue_index}
    path=directory/'handoff.json';atomic_json(path,plan)
    # Each version has a fresh handshake; a previous attempt cannot authorize it.
    for name in ('ready.json','commit.json','cancel.json','result.json','consumed.json'):
        old=directory/name
        if old.exists():old.unlink()
    return path,copied,plan


def consume_update_result(plan_path,root=None,executable=None,current=None):
    """Only a matching, fresh, once-consumed helper receipt can resume a queue."""
    root=Path(root or data_root()).resolve();path=Path(plan_path).resolve()
    if not path.is_relative_to(root/'.cache/updates') or path.name!='handoff.json':raise ValueError('Update receipt outside the update cache')
    plan=json.loads(path.read_text(encoding='utf-8-sig'));result=json.loads((path.parent/'result.json').read_text(encoding='utf-8-sig'))
    stamp=datetime.fromisoformat(plan['created_at']);now=datetime.now(timezone.utc)
    if (plan.get('protocol')!=1 or not stamp.tzinfo or not timedelta(0)<=now-stamp<=timedelta(hours=1)
            or plan.get('token')!=result.get('token') or Path(plan['profile']).resolve()!=root
            or Path(plan['executable']).resolve()!=Path(executable or sys.executable).resolve()
            or result.get('stage') not in ('success','failed')):raise ValueError('Update receipt identity is invalid')
    success=result['stage']=='success'
    if type(plan.get('queue_index')) is not int or not 0<=plan['queue_index']<4:raise ValueError('Saved update queue selection is invalid')
    if success and plan['version']!=(current or installed_version()):raise ValueError('Installed version does not match the update receipt')
    blocker=saved_update_blocker(root) if success else None
    with (path.parent/'consumed.json').open('x',encoding='utf-8') as stream:json.dump({'token':plan['token']},stream)
    return {'success':success,'version':plan['version'],'resume':success and not blocker and plan.get('resume') is True,
            'connected':success and not blocker and (plan.get('connected') is True or plan.get('resume') is True),
            'minimized':plan.get('minimized') is True,'queue_index':plan['queue_index'],'error':blocker or result.get('error','')}
