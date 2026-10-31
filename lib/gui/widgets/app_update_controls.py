"""Background downloads and a bounded, read-only idle check before updating."""
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from PyQt5 import QtCore

from lib.app_paths import data_root
from lib.app_updates import (CHECK_INTERVAL,atomic_json,fetch_update,installed_version,
                            update_blocker,saved_update_blocker,idle_update_evidence,prepare_handoff)


class UpdateDownload(QtCore.QThread):
    result=QtCore.pyqtSignal(object)
    failed=QtCore.pyqtSignal(str)
    def __init__(self,version,cache,failed_version,parent):
        super().__init__(parent);self.version=version;self.cache=cache;self.failed_version=failed_version
    def run(self):
        try:
            value=fetch_update(self.version,self.cache,self.failed_version,cancelled=self.isInterruptionRequested)
            if not self.isInterruptionRequested():self.result.emit(value)
        except Exception as error:
            if not self.isInterruptionRequested():self.failed.emit(str(error))


class AppUpdateControls:
    def init_app_updates(self):
        self.update_version=installed_version();self.update_worker=None;self.update_candidate=None
        self.update_quiescing=False;self.update_committing=False;self.update_closing=False
        self.update_observation=None;self.update_handoff=None;self.update_process=None
        self.update_config_path=data_root()/'settings/gui/updates.json'
        self.update_config={'enabled':True}
        try:self.update_config.update(json.loads(self.update_config_path.read_text(encoding='utf-8')))
        except (OSError,ValueError,TypeError):pass
        self.update_check_at=datetime.now(timezone.utc)+timedelta(seconds=30)
        self.update_timer=QtCore.QTimer(self);self.update_timer.timeout.connect(self.update_tick)
        # No network/downloads in a source run or an isolated installer test.
        self.update_supported=bool(self.update_version and not any(a in sys.argv for a in ('--self-test','--update-self-test','--update-probe')))
        menu=self.menuBar.addMenu('Updates')
        menu.addAction('Installed version '+self.update_version if self.update_version else 'Source checkout').setEnabled(False)
        self.auto_update_action=menu.addAction('Automatic updates')
        self.auto_update_action.setCheckable(True);self.auto_update_action.setChecked(bool(self.update_version) and self.update_config.get('enabled') is True)
        self.auto_update_action.setEnabled(self.update_supported)
        self.auto_update_action.toggled.connect(self.set_auto_updates)
        self.check_update_action=menu.addAction('Check for updates now',lambda:self.check_app_updates(force=True))
        self.check_update_action.setEnabled(self.update_supported)
        if not self.update_supported:menu.setToolTip('Automatic installer updates are available in the installed app. Source checkouts use Git.')
        if self.update_supported:self.update_timer.start(1000)

    def save_update_config(self):
        try:atomic_json(self.update_config_path,self.update_config);return True
        except OSError as error:self.log('Could not save update preferences: '+str(error),True);return False

    def set_auto_updates(self,enabled):
        self.update_config['enabled']=bool(enabled);self.save_update_config()
        if not enabled:
            if self.update_worker and self.update_worker.isRunning():self.update_worker.requestInterruption()
            if self.update_quiescing:self.cancel_update_handoff('Automatic updates disabled')
            self.update_candidate=None
        else:self.update_check_at=datetime.now(timezone.utc)

    def check_app_updates(self,force=False):
        if not self.update_supported or self.update_closing or self.update_quiescing:return
        if self.update_worker and self.update_worker.isRunning():return
        if not force and self.update_config.get('enabled') is not True:return
        self.update_check_at=datetime.now(timezone.utc)+CHECK_INTERVAL
        self.update_worker=UpdateDownload(self.update_version,data_root()/'.cache/updates',
            None if force else self.update_config.get('failed_version'),self)
        self.update_worker.result.connect(self.update_downloaded);self.update_worker.failed.connect(self.update_download_failed)
        self.log('Updates: checking the latest verified release'+(' (manual check)' if force else ''))
        self.update_worker.start()

    def update_downloaded(self,candidate):
        if self.update_closing:return
        self.update_candidate=candidate
        self.log('Updates: version '+candidate['version']+' downloaded and verified; waiting for an idle boundary' if candidate else 'Updates: no newer eligible release')

    def update_download_failed(self,error):
        self.update_check_at=datetime.now(timezone.utc)+timedelta(hours=1)
        self.log('Update check/download failed; current app continues running: '+error,True)

    def cancel_update_handoff(self,message,failed=False):
        if self.update_handoff:
            path,plan=self.update_handoff
            try:atomic_json(path.parent/'cancel.json',{'token':plan['token']})
            except OSError:pass
        if failed and self.update_candidate:
            self.update_config['failed_version']=self.update_candidate['version'];self.save_update_config()
        self.update_quiescing=False;self.update_handoff=None;self.update_candidate=None;self.update_observation=None
        self.update_check_at=datetime.now(timezone.utc)+timedelta(hours=1)
        if not self.update_closing:
            if getattr(self,'update_queue_timer_running',True):self.queue_timer.start(1000)
            if getattr(self,'update_preview_running',True):self.timer.start(2000)
            self.set_queue_editable(not self.queue_engine.running)
            self.run_queue_button.setText('Stop Queue' if self.queue_engine.running else 'Start Queue')
        self.log('Updates: '+message,failed)

    def update_tick(self):
        if self.update_closing or self.update_committing:return
        now=datetime.now(timezone.utc)
        if not self.update_quiescing:
            if self.update_candidate:
                if update_blocker(self) or saved_update_blocker() or (self.update_worker and self.update_worker.isRunning()):return
                self.update_quiescing=True;self.update_deadline=now+timedelta(seconds=60)
                self.update_queue_timer_running=self.queue_timer.isActive();self.update_preview_running=self.timer.isActive()
                self.update_observation=None;self.queue_timer.stop();self.timer.stop();self.set_queue_editable(False)
                self.run_queue_button.setText('Cancel update / Stop Queue' if self.queue_engine.running else 'Cancel update')
                self.log('Updates: verifying the idle screen before installing '+self.update_candidate['version'])
                if self.handle:self.scan_live()
            elif now>=self.update_check_at:self.check_app_updates()
            return
        if now>self.update_deadline:
            self.cancel_update_handoff('Idle/installer handoff timed out; app left running',failed=True);return
        if self.update_handoff:
            path,plan=self.update_handoff
            try:
                result_path=path.parent/'result.json'
                if result_path.exists():
                    result=json.loads(result_path.read_text(encoding='utf-8-sig'))
                    if result.get('token')==plan['token'] and result.get('stage')=='failed':
                        self.cancel_update_handoff(result.get('error','Installer helper failed'),failed=True);return
                ready=json.loads((path.parent/'ready.json').read_text(encoding='utf-8-sig'))
                if ready.get('token')!=plan['token'] or ready.get('stage')!='waiting_for_app':return
                if update_blocker(self) or saved_update_blocker():self.cancel_update_handoff('New activity postponed installation');return
                atomic_json(path.parent/'commit.json',{'token':plan['token']})
                self.update_committing=True;self.timer.stop();self.queue_timer.stop();self.update_timer.stop()
                self.log('Updates: installing '+plan['version']+'; saved queue will '+('resume' if plan['resume'] else 'remain stopped'))
                self.close()
            except FileNotFoundError:pass
            except (OSError,ValueError) as error:self.cancel_update_handoff(str(error),failed=True)
            return
        if update_blocker(self):return
        if self.handle:
            if not self.update_observation:return
            evidence,observed,live=self.update_observation
            if not idle_update_evidence(evidence,observed,now,live):
                self.cancel_update_handoff('Screen is not a verified idle page; installation deferred');return
        try:
            if not self._save():raise OSError('Settings could not be saved; installation deferred')
            path,helper,plan=prepare_handoff(self.update_candidate,self.queue_engine.running,bool(self.handle),self.isMinimized(),queue_index=self.queue_index)
            self.update_handoff=(path,plan)
            self.update_process=subprocess.Popen([str(helper),str(path)],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except Exception as error:self.cancel_update_handoff(str(error),failed=True)

    def update_close_allowed(self):
        worker_running=bool(self.update_worker and self.update_worker.isRunning())
        if not self.update_committing and not self.update_closing:
            self.update_closing=True
            self.update_waiting_for_work=bool(self.update_quiescing or worker_running)
            if self.update_quiescing:self.cancel_update_handoff('App closed; installation cancelled')
            if self.update_waiting_for_work:self.stop_queue();self.timer.stop();self.queue_timer.stop()
        self.update_timer.stop()
        if worker_running:
            self.update_worker.requestInterruption();QtCore.QTimer.singleShot(250,self.close);return False
        if getattr(self,'update_waiting_for_work',False) and self.busy:
            QtCore.QTimer.singleShot(250,self.close);return False
        return True

    def handle_update_receipt(self,receipt):
        if receipt['success']:
            self.update_config.pop('failed_version',None)
            self.log('Updates: installed version '+receipt['version']+' verified; saved settings and outcomes preserved')
            if receipt.get('error'):self.log('Updates: queue remains stopped because '+receipt['error'],True)
        else:
            self.update_config['failed_version']=receipt['version']
            self.log('Update failed; queue remains stopped: '+receipt.get('error','Unknown installer error'),True)
        self.save_update_config()
