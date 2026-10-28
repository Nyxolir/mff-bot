"""Background emulator recovery with saved submissions and bounded retries."""
from datetime import datetime,timedelta,timezone
from PyQt5 import QtCore
from lib.bluestacks_recovery import recover_connection,transport_failure,capture_failure

class EmulatorRecoveryTask(QtCore.QThread):
    result=QtCore.pyqtSignal(object,object)
    failed=QtCore.pyqtSignal(object,str)
    progress=QtCore.pyqtSignal(str)
    def __init__(self,backend,probe,guard,parent):
        super().__init__(parent);self.backend=backend;self.probe=probe;self.guard=guard
    def run(self):
        try:self.result.emit(self.backend,recover_connection(self.backend,self.probe,self.guard,self.progress.emit))
        except Exception as error:self.failed.emit(self.backend,str(error))

class EmulatorRecovery:
    def init_emulator_recovery(self):
        self.emulator_task=None;self.emulator_attempts=[];self.emulator_pending_interrupted=False
        self.emulator_frame_floor=None
        self.emulator_game_loading_until=None
        self.emulator_capture_failed_since=None

    def emulator_recovering(self):return self.emulator_task is not None

    def try_emulator_recovery(self,error):
        if not self.background_input or self.adb_backend is None or not self.queue_engine.running:return False
        if self.emulator_recovering():return True
        now=datetime.now(timezone.utc)
        if capture_failure(error):
            # A partial/blank frame is not a disconnected device. Give capture
            # a continuous minute to recover, without burning reconnect slots
            # or interrupting an already submitted automatic run.
            since=getattr(self,'emulator_capture_failed_since',None)
            if since is None:self.emulator_capture_failed_since=since=now
            self.adb_frame=None
            self.queue_observation=None;self.objective_observation=None;self.trivia_observation=None;self.resource_observation=None
            if now-since<timedelta(seconds=60):
                self.queue_pause('ADB screenshot unavailable; retrying fresh capture before player recovery',15,stalled=False)
                return True
        elif not transport_failure(error):return False
        self.emulator_attempts=[stamp for stamp in self.emulator_attempts if now-stamp<timedelta(hours=1)]
        if len(self.emulator_attempts)>=2:
            self.stop_queue();self.log('BlueStacks recovery limit reached (two per hour); submitted state retained',True);return True
        if not self.persist_pending_clear():
            self.stop_queue();self.log('Could not save submissions; emulator recovery cancelled',True);return True
        from lib.background_input import set_backend
        from lib.gui.widgets.modern_main import find_bluestacks
        def probe(title):
            try:return find_bluestacks(allow_minimized=True,title_hint=title)
            except RuntimeError:return None
        self.emulator_attempts.append(now)
        self.emulator_saved_phase=self.queue_phase
        self.adb_frame=None;self.frame_waiting_scan=False
        self.queue_observation=None;self.objective_observation=None;self.trivia_observation=None;self.resource_observation=None
        self.queue_waiting=None;self.objective_waiting=None;self.trivia_waiting=None;self.resource_waiting=None
        self.queue_stall_key=None;self.queue_stall_count=0;self.queue_stall_since=None
        set_backend(None,required=True)
        task=EmulatorRecoveryTask(self.adb_backend,probe,lambda:self.queue_engine.running,self)
        self.emulator_task=task
        task.result.connect(self.emulator_recovered)
        task.failed.connect(self.emulator_recovery_failed)
        task.progress.connect(self.log)
        task.finished.connect(self.emulator_recovery_finished)
        self.log('BlueStacks connection lost: preserving submissions, checking the player process and reconnecting the selected instance')
        self.statusBar().showMessage('Recovering BlueStacks; submitted runs preserved')
        task.start();return True

    def emulator_recovered(self,backend,result):
        if backend is not self.adb_backend or not self.queue_engine.running:return
        now=datetime.now(timezone.utc)
        if self.objective_active:self.finish_objectives('BlueStacks recovered; fresh inspection required')
        if self.trivia_active:self.finish_trivia('BlueStacks recovered; retrying unfinished trivia')
        if self.resource_active:self.finish_resource_check('BlueStacks recovered; restarting unfinished check',True)
        self.handle=result.handle;self.capture_failure_count=0
        self.emulator_frame_floor=result.observed
        self.emulator_capture_failed_since=None
        self.objective_refresh_due=True;self.epic_preparation=None;self.converging_preparation=None
        self.queue_fresh_pass=False
        pending=self.queue_engine.pending
        self.emulator_pending_interrupted=bool(result.game_opened and
            (pending or self.world_event_state.pending or self.world_event_state.started) and not self.dimension_claim_protected())
        if pending:
            self.queue_target=pending[1];self.queue_phase=self.emulator_saved_phase
        elif self.world_event_active or self.dispatch_supply_active:self.queue_phase=self.emulator_saved_phase
        else:
            self.queue_target=None;self.queue_recovering=True;self.queue_recovery_steps=0;self.queue_phase='recover_home'
            self.board_check_active=False;self.board_check_due=True
        self.queue_waiting=None;self.queue_wake=now+timedelta(seconds=5)
        self.session_reload_deadline=now+timedelta(minutes=3)
        self.emulator_game_loading_until=self.session_reload_deadline if result.game_opened else None
        self.adb_frame_ready(backend,*result.frame,result.observed)
        self.log('BlueStacks '+('restarted' if result.launched else 'reconnected')+'; MFF loading/verification resumes without replaying a submitted run')
        QtCore.QTimer.singleShot(1500,self.scan_live)

    def emulator_recovery_failed(self,backend,error):
        if backend is not self.adb_backend:return
        backend.connected=False;self.handle=None;self.label_username.setText('BlueStacks: disconnected')
        if self.queue_engine.running:self.stop_queue()
        self.log('BlueStacks recovery stopped: '+error+'. Saved submissions retained.',True)

    def emulator_recovery_finished(self):
        task=self.emulator_task;self.emulator_task=None
        if task:task.deleteLater()
        if self.close_after_capture:self.close()

    def interrupted_emulator_home(self,evidence,observed):
        if not self.emulator_pending_interrupted or not self.queue_engine.running:return False
        if not (self.queue_engine.pending or self.world_event_state.pending or self.world_event_state.started):
            self.emulator_pending_interrupted=False;return False
        pending=self.queue_engine.pending
        if (self.dimension_claim_protected() or (pending and
                ((pending[1] in ('TIMELINE BATTLE','OTHERWORLD BATTLE','TEAM BATTLE ARENA') and self.arena_repeat_finished)
                 or (pending[1]=='ZOMBIE SURVIVAL' and self.zombie_repeat_finished)))):
            self.emulator_pending_interrupted=False;return False
        if (evidence.screen=='game_home' and evidence.values.get('home_controls_verified') is True and not evidence.errors
                and timedelta(0)<=datetime.now(timezone.utc)-observed<=timedelta(seconds=30)):
            self.stop_queue()
            self.log('MFF reopened after BlueStacks loss, but the submitted run has no verified result. Saved submission retained; no automatic replay.',True)
            return True
        return False
