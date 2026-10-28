"""Current desktop shell using the upstream GUI design, without legacy tasks."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from pathlib import Path
import sys

from PIL import Image
from PyQt5 import QtCore, QtGui, QtWidgets

from lib.gui.designes.main_window import Ui_MainWindow
from lib.farming import ENERGY_FARMS,UNBOOSTED_SWEEPS, MANUAL
from lib.screen_reader import ScreenReader
from lib.screen_policy import evaluate
from lib.resource_check import Navigation,next_navigation,perform_navigation,resource_status,click_game_point,InputNotSent
from lib.daily_queue import DailyRaidGate,ContinuousQueue,BatchEvidence,QueueAction,next_reset,reset_period
from lib.objective_inspection import ObjectiveInspection
from lib.gui.widgets.trivia_controls import TriviaControls
from lib.gui.widgets.gbr_cache import GbrCache
from lib.gui.widgets.objective_cache import ObjectiveCache
from lib.gui.widgets.dispatch_supplies_controls import DispatchSuppliesControls
from lib.gui.widgets.completion_cache import CompletionCache
from lib.gui.widgets.stuck_recovery import StuckRecovery
from lib.gui.widgets.world_event_controls import WorldEventControls
from lib.gui.widgets.arena_controls import ArenaControls
from lib.gui.widgets.uncertain_review import UncertainReview
from lib.gui.widgets.story_controls import StoryControls
from lib.gui.widgets.appearance import Appearance
from lib.gui.widgets.daily_board_check import DailyBoardCheck
from lib.gui.widgets.zombie_controls import ZombieControls
from lib.gui.widgets.converging_controls import ConvergingControls
from lib.gui.widgets.emulator_recovery import EmulatorRecovery

from lib.app_paths import data_root
ROOT = data_root()
LOG_PATH = ROOT/'diagnostics/queue.log'
STATE = ROOT / "settings/gui/modern-desktop.json"
MODES = ["TIMELINE BATTLE", "OTHERWORLD BATTLE", "TEAM BATTLE ARENA", "WORLD EVENT", "ZOMBIE SURVIVAL", *sorted(UNBOOSTED_SWEEPS), *sorted(ENERGY_FARMS), "DISPATCH 7-1", "WORLD BOSS", "ALLIANCE BATTLE", "STORY ULTIMATE"]


def bluestacks_title(handle):
    import ctypes
    from ctypes import wintypes
    user32=ctypes.WinDLL('user32',use_last_error=True)
    user32.GetWindowTextLengthW.argtypes=[wintypes.HWND]
    user32.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    value=ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(handle)+1)
    user32.GetWindowTextW(handle,value,len(value))
    return value.value

def find_bluestacks(allow_minimized=False,title_hint=None):
    """Discover the visible window for the app's user-operated preview."""
    if sys.platform != "win32":
        raise RuntimeError("BlueStacks preview requires Windows")
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    matches = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    def visit(handle, unused):
        size = user32.GetWindowTextLengthW(handle)
        title = ctypes.create_unicode_buffer(size+1)
        user32.GetWindowTextW(handle,title,size+1)
        if title.value.startswith("BlueStacks App Player") and (title_hint is None or title.value==title_hint) and user32.IsWindowVisible(handle):
            matches.append((int(handle),bool(user32.IsIconic(handle))))
        return True
    callback = callback_type(visit)
    user32.EnumWindows.argtypes = [callback_type,wintypes.LPARAM]
    user32.EnumWindows(callback,0)
    if len(matches) != 1:
        raise RuntimeError(f"Open exactly one BlueStacks App Player window (found {len(matches)})")
    if matches[0][1] and not allow_minimized:
        raise RuntimeError("Restore BlueStacks from the taskbar before connecting")
    return matches[0][0]


class BackgroundFrameTask(QtCore.QThread):
    result=QtCore.pyqtSignal(object,object,object,object)
    failed=QtCore.pyqtSignal(object,str)
    def __init__(self,backend,connect=False,parent=None):
        super().__init__(parent);self.backend=backend;self.connect_first=connect
    def run(self):
        try:
            observed=datetime.now(timezone.utc)
            if self.connect_first:
                self.backend.connect();image,data=self.backend.initial_frame
            else:image,data=self.backend.capture()
            self.result.emit(self.backend,image,data,observed)
        except Exception as error:self.failed.emit(self.backend,str(error))

class ScanTask(QtCore.QThread):
    result = QtCore.pyqtSignal(object,object,bool)
    failed = QtCore.pyqtSignal(str)
    def __init__(self,image,captured_at,live,resource_check=False,reader_kind="screen",home_probe=False):
        super().__init__()
        self.image,self.captured_at,self.live = image,captured_at,live
        self.resource_check=resource_check
        self.reader_kind=reader_kind
        self.home_probe=home_probe
    def run(self):
        try:
            from lib.android_home import android_home
            launcher=android_home(self.image)
            if launcher:
                self.result.emit(launcher,self.captured_at,self.live);return
            from lib.session_recovery import session_notice
            notice=session_notice(self.image)
            if notice:
                self.result.emit(notice,self.captured_at,self.live)
                return
            from lib.notification_panel import notification_panel
            panel=notification_panel(self.image)
            if panel:
                self.result.emit(panel,self.captured_at,self.live);return
            from lib.story_completion import story_completion
            ended=story_completion(self.image)
            if ended:
                self.result.emit(ended,self.captured_at,self.live);return
            if self.home_probe:
                from lib.objective_reader import ObjectiveReader
                home=ObjectiveReader().read(self.image)
                if home.values.get('home_controls_verified') is True:
                    self.result.emit(home,self.captured_at,self.live);return
            from lib.zombie_reader import zombie_completion
            ended=zombie_completion(self.image)
            if ended:
                self.result.emit(ended,self.captured_at,self.live);return
            from lib.arena_completion import arena_completion
            ended=arena_completion(self.image)
            if ended:
                self.result.emit(ended,self.captured_at,self.live);return
            if self.reader_kind in ('uncertain_review','daily_board_check'):
                evidence=ScreenReader().read(self.image,resource_check=True)
                if evidence.screen=='status_board':
                    from lib.mission_reader import BoardReader
                    evidence=BoardReader().read(self.image)
                if evidence.screen=='unknown':
                    from lib.objective_reader import ObjectiveReader
                    evidence=ObjectiveReader().read(self.image)
                self.result.emit(evidence,self.captured_at,self.live);return
            if self.reader_kind in ("objectives","recover_home"):
                from lib.objective_reader import ObjectiveReader
                evidence=ObjectiveReader().read(self.image)
                if self.reader_kind=='objectives':
                    diagnostic=ROOT/'diagnostics/last-objectives.png';diagnostic.parent.mkdir(exist_ok=True)
                    self.image.save(diagnostic)
                    diagnostic.with_suffix('.json').write_text(json.dumps(asdict(evidence),indent=2),encoding='utf-8')
                self.result.emit(evidence,self.captured_at,self.live);return
            if self.reader_kind=='converging':
                from lib.converging import ConvergingReader
                evidence=ConvergingReader().read(self.image)
                if evidence.screen=='unknown' and not evidence.errors:
                    from lib.objective_reader import ObjectiveReader
                    evidence=ObjectiveReader().read(self.image)
                self.result.emit(evidence,self.captured_at,self.live);return
            if self.reader_kind=="trivia":
                from lib.trivia_reader import TriviaReader
                evidence=TriviaReader().read(self.image)
                diagnostic=ROOT/'diagnostics/last-trivia.png';diagnostic.parent.mkdir(exist_ok=True);self.image.save(diagnostic)
                diagnostic.with_suffix('.json').write_text(json.dumps(asdict(evidence),indent=2),encoding='utf-8')
                self.result.emit(evidence,self.captured_at,self.live);return
            if self.reader_kind=='world_event':
                from lib.world_event import WorldEventReader
                evidence=WorldEventReader().read(self.image)
                diagnostic=ROOT/'diagnostics/last-world-event.png'
                diagnostic.parent.mkdir(exist_ok=True);self.image.save(diagnostic)
                diagnostic.with_suffix('.json').write_text(json.dumps(asdict(evidence),indent=2),encoding='utf-8')
                self.result.emit(evidence,self.captured_at,self.live);return
            if self.reader_kind=='dispatch_supplies':
                from lib.dispatch_supplies import DispatchSuppliesReader
                evidence=DispatchSuppliesReader().read(self.image)
                diagnostic=ROOT/'diagnostics/last-dispatch-supplies.png'
                diagnostic.parent.mkdir(exist_ok=True);self.image.save(diagnostic)
                diagnostic.with_suffix('.json').write_text(json.dumps(asdict(evidence),indent=2),encoding='utf-8')
                self.result.emit(evidence,self.captured_at,self.live);return
            if self.reader_kind in ('arena','arena_resume'):
                from lib.arena_reader import ArenaReader
                evidence=ArenaReader().read(self.image,resume=self.reader_kind=='arena_resume')
                diagnostic=ROOT/'diagnostics/last-arena.png';diagnostic.parent.mkdir(exist_ok=True);self.image.save(diagnostic)
                diagnostic.with_suffix('.json').write_text(json.dumps(asdict(evidence),indent=2),encoding='utf-8')
                self.result.emit(evidence,self.captured_at,self.live);return
            if self.reader_kind=='story':
                from lib.story_reader import StoryReader
                evidence=StoryReader().read(self.image)
                diagnostic=ROOT/'diagnostics/last-story.png';diagnostic.parent.mkdir(exist_ok=True);self.image.save(diagnostic)
                diagnostic.with_suffix('.json').write_text(json.dumps(asdict(evidence),indent=2),encoding='utf-8')
                if evidence.screen=='unknown':
                    trace=ROOT/'diagnostics/story-frames';trace.mkdir(exist_ok=True)
                    self.image.save(trace/(self.captured_at.strftime('%Y%m%d-%H%M%S-%f')+'.png'))
                    for old in sorted(trace.glob('*.png'))[:-12]:old.unlink()
                self.result.emit(evidence,self.captured_at,self.live);return
            if self.reader_kind=='zombie':
                from lib.zombie_reader import ZombieReader
                evidence=ZombieReader().read(self.image)
                self.result.emit(evidence,self.captured_at,self.live);return
            if self.reader_kind=="alliance":
                from lib.alliance_reader import AllianceReader
                evidence=AllianceReader().read(self.image)
                self.result.emit(evidence,self.captured_at,self.live);return
            if self.reader_kind=="dispatch":
                from lib.dispatch_reader import DispatchReader
                evidence=DispatchReader().read(self.image)
                if evidence.screen=="unknown" and not evidence.errors:
                    evidence=ScreenReader().read(self.image,resource_check=True)
                self.result.emit(evidence,self.captured_at,self.live);return
            if self.reader_kind=="board":
                from lib.mission_reader import BoardReader
                evidence=BoardReader().read(self.image)
            elif self.reader_kind in ("sweep","sweep_result"):
                from lib.sweep_reader import SweepReader
                evidence=SweepReader().read(self.image)
            else:evidence=ScreenReader().read(self.image,resource_check=self.resource_check)
            if self.resource_check and evidence.screen=="gbr_main":
                diagnostic=ROOT/"diagnostics/last-gbr-check.png"
                diagnostic.parent.mkdir(exist_ok=True)
                self.image.save(diagnostic)
            if self.reader_kind in ("sweep","sweep_result"):
                diagnostic=ROOT/"diagnostics/last-sweep-check.png"
                diagnostic.parent.mkdir(exist_ok=True)
                self.image.save(diagnostic)
                diagnostic.with_suffix('.json').write_text(json.dumps(asdict(evidence),indent=2),encoding='utf-8')
            self.result.emit(evidence,self.captured_at,self.live)
        except Exception as error:
            self.failed.emit(str(error))


class ModernMainWindow(QtWidgets.QMainWindow,Ui_MainWindow,TriviaControls,GbrCache,ObjectiveCache,CompletionCache,StuckRecovery,DispatchSuppliesControls,WorldEventControls,ArenaControls,StoryControls,Appearance,UncertainReview,DailyBoardCheck,ZombieControls,ConvergingControls,EmulatorRecovery):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.init_trivia()
        self.init_dispatch_supplies()
        self.init_world_event()
        self.init_arenas()
        self.init_story()
        self.init_zombie()
        self.converging_preparation=None
        self.gbr_retry_at=datetime.now(timezone.utc)
        self.queue_deferred={}
        self.init_stuck_recovery()
        self.init_emulator_recovery()
        self.init_uncertain_review()
        self.setWindowTitle("MFF Auto — Farming")
        self.resize(1250,760)
        self.setMinimumSize(1080,650)
        self.queues = [[{"mode":name,"enabled":True} for name in MODES[:5]],[],[],[]]
        self.queue_index = 0
        self.handle = None
        self.background_input=True
        self.adb_backend=None
        self.adb_frame=None;self.frame_task=None;self.frame_waiting_scan=False;self.close_after_capture=False
        self.last_image = None
        self.last_evidence = None
        self.latest_counters = {}
        self.objective_active=False
        self.objective_observation=None
        self.objective_waiting=None
        self.objective_inspection=None
        self.objective_plan=None
        self.objective_period=None
        self.objective_checked_at=None
        self.objective_refresh_due=True
        self.alliance_started=None
        self.alliance_auto_clicked=False
        self.contribution_followup=False
        self.contribution_submitted=False
        self.contribution_before=None
        self.contribution_acquire_submitted=False
        self.dispatch_started=None
        self.dispatch_swipes=0
        self.dispatch_auto_clicked=False
        self.session_notice_acknowledged = False
        self.session_reload_deadline = None
        self.resource_balances = None
        self.resource_active = False
        self.resource_pending_queue = False
        self.resource_waiting = None
        self.resource_steps = 0
        self.resource_strip_last=None
        self.resource_strip_stalls=0
        self.resource_observation = None
        self.raid_gate=DailyRaidGate()
        self.queue_engine=ContinuousQueue(self.raid_gate)
        self.queue_phase="idle"
        self.queue_target=None
        self.queue_wake=None
        self.queue_waiting=None
        self.queue_scrolls=0
        self.queue_last_board=None
        self.queue_observation=None
        self.queue_started_period=None
        self.board_check_active=False;self.board_check_due=True;self.enable_board_preflight=True
        self.queue_batch_generation=None
        self.queue_max_attempted=False
        self.epic_preparation=None
        self.task = None
        self.busy = False
        self.loading = False
        self._setup_controls()
        self._load()
        from lib.background_input import set_backend
        set_backend(None,required=self.background_input)
        self.load_gbr_clearance()
        self.load_objective_cache()
        self.load_completed_missions()
        self.load_story_run()
        self.load_pending_clear()
        self._populate()
        self.init_appearance()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.refresh_preview)
        self.timer.start(2000)
        self.queue_timer=QtCore.QTimer(self)
        self.queue_timer.timeout.connect(self.queue_tick)
        self.queue_timer.start(1000)
        self.log("Ready. Connect BlueStacks to preview the game, then Check Screen.")
        self.log('Build 2026-10-21: isolated ADB, active-instance ports, restored Arena recovery, reward-popup handling')
        self.log("Start Queue uses full boosted ticket batches. Combat skill controls remain shelved.")
        if self.world_event_state.cache_done_rejected:self.log('World Event: old unverified done flag ignored; fresh event-page checks are due')

    def _setup_controls(self):
        self.info_group.setTitle("Connection & farming status")
        self.label_username.setText("BlueStacks: disconnected")
        self.label_energy.setText("Soul of Faltine: unknown")
        self.label_gold.setText("Celestial Seed: unknown")
        self.label_boosts.setText("Energy / boost farming: blocked")
        self.autoplay_button.setText("Connect BlueStacks")
        self.autoplay_button.setToolTip("Connect a read-only game preview")
        self.autoplay_button.clicked.connect(self.connect_emulator)
        self.restart_game_button.setText("Check Screen")
        self.restart_game_button.setToolTip("Read the current screen without clicking the game")
        self.restart_game_button.clicked.connect(self.scan_live)
        self.run_queue_button.setText("Start Queue")
        self.run_queue_button.setToolTip("Run enabled energy missions with full boosted ticket batches; keep waiting until stopped")
        self.run_queue_button.clicked.connect(self.toggle_queue)
        self.add_queue_button.clicked.connect(self.add_mode)
        self.edit_queue_button.clicked.connect(self.edit_mode)
        self.remove_queue_button.clicked.connect(self.remove_modes)
        self.queue_list_widget.itemChanged.connect(self.queue_changed)
        self.queue_list_widget.model().rowsMoved.connect(self.queue_reordered)
        self.queue_list_widget.itemDoubleClicked.connect(lambda item:self.edit_mode())
        self.queue_buttons = [self.queue_button_1,self.queue_button_2,self.queue_button_3,self.queue_button_4]
        for index,button in enumerate(self.queue_buttons):
            button.clicked.connect(lambda checked,index=index:self.switch_queue(index))
        self.acquire_heroic_quest_rewards_label.setText("Allow sweep tickets + energy")
        self.acquire_heroic_quest_rewards_label.setToolTip("Preference only; energy and boost use require both GBR counters at zero")
        self.acquire_heroic_quest_rewards_checkbox.setToolTip("Saved preference; does not spend anything")
        self.acquire_heroic_quest_rewards_checkbox.stateChanged.connect(self._save)
        self.mission_team_spin_box.valueChanged.connect(self._save)
        self.timeline_team_spin_box.setValue(1)
        self.timeline_team_spin_box.setEnabled(False)
        self.timeline_team_spin_box.setToolTip("Timeline Team 1, as requested")
        self.handle_network_errors_label.setText("Combat skills: shelved")
        self.handle_network_errors_checkbox.setChecked(False)
        self.handle_network_errors_checkbox.setEnabled(False)
        self.quick_start_group.setTitle("Quick Checks")
        replacements = [
            (self.daily_trivia_button,"Daily Trivia",self.check_trivia),
            (self.comic_cards_button,"Check Objectives",self.check_objectives),
            (self.custom_gear_button,"Open Screenshot…",self.open_image),
            (self.dispatch_mission_rewards,"Check Resources",self.check_resources),
            (self.squad_battle_button,"Start Story Ultimate",self.start_story_now),
            (self.world_boss_invasion_button,"Clear Logs",self.clear_logs),
        ]
        for button,label,callback in replacements:
            button.setText(label)
            button.clicked.connect(callback)
        for button in (self.danger_room_button,self.enhance_potential_button,self.shadowland_button):
            button.hide()
        self.game_screen_group.setTitle("Game Preview")
        self.screen_label.setMinimumSize(400,225)
        self.screen_label.setStyleSheet("background:#111827;color:#aab7cb;border:1px solid #334155;")
        self.screen_label.setText("Connect BlueStacks\n\nGame input is disabled")
        self.log_tab_widget.setLayoutDirection(QtCore.Qt.LeftToRight)
        menu=self.menuBar.addMenu("File")
        menu.addAction("Connect BlueStacks",self.connect_emulator)
        self.background_action=menu.addAction('Background control (ADB, no mouse)')
        self.background_action.setCheckable(True)
        self.background_action.setChecked(True)
        self.background_action.toggled.connect(self.set_background_input)
        menu.addAction("Recheck GBR now",lambda:self.check_resources(force=True))
        menu.addAction("Recheck Dimension/Dispatch requirements",lambda:self.check_objectives(force=True))
        menu.addAction("Open screenshot…",self.open_image)
        menu.addAction("Load example…",self.open_example)
        menu.addSeparator()
        menu.addAction("Exit",self.close)
        help_menu=self.menuBar.addMenu("Help")
        help_menu.addAction("Farming rules",self.show_rules)
        self.statusBar().showMessage("Ready • Battle controls shelved • No crystals or upgrades")
        self.reset_label=QtWidgets.QLabel("Reset: 15:00 UTC · 17:00 Albania summer / 16:00 winter",self)
        self.statusBar().addPermanentWidget(self.reset_label)

    def log(self,text,error=False):
        line=f"[{datetime.now():%H:%M:%S}] {text}"
        self.logger_text.appendPlainText(line)
        (self.logger_text_error if error else self.logger_text_info).appendPlainText(line)
        try:
            path=LOG_PATH;path.parent.mkdir(exist_ok=True)
            if path.exists() and path.stat().st_size>5000000:path.replace(path.with_suffix('.previous.log'))
            with path.open('a',encoding='utf-8') as output:output.write(line+'\n')
        except OSError:pass

    def clear_logs(self):
        for widget in (self.logger_text,self.logger_text_info,self.logger_text_error): widget.clear()

    def _load(self):
        if not STATE.exists(): return
        try:
            data=json.loads(STATE.read_text(encoding="utf-8"))
            queues=data["queues"]
            if len(queues)!=4 or any(not isinstance(q,list) for q in queues): raise ValueError("Invalid queues")
            for queue in queues:
                for item in queue:
                    if item["mode"] not in MODES or type(item["enabled"]) is not bool: raise ValueError("Invalid queue item")
            self.queues=queues
            if data.get('converging_queue_version',0)<1:
                for mode in sorted(UNBOOSTED_SWEEPS):
                    if not any(row['mode']==mode for row in self.queues[0]):self.queues[0].insert(0,{'mode':mode,'enabled':True})
            if data.get('zombie_queue_version',0)<1 and not any(row['mode']=='ZOMBIE SURVIVAL' for row in self.queues[0]):
                self.queues[0].append({'mode':'ZOMBIE SURVIVAL','enabled':True})
            if data.get("objective_rules_version",0)<1:
                for item in self.queues[0]:
                    if item["mode"]=="ALLIANCE BATTLE":item["enabled"]=True
            self.mission_team_spin_box.setValue(int(data.get("mission_team",1)))
            self.acquire_heroic_quest_rewards_checkbox.setChecked(data.get("allow_sweep",True))
            self.background_input=bool(data.get('background_input',True))
            self.background_action.blockSignals(True)
            self.background_action.setChecked(self.background_input)
            self.background_action.blockSignals(False)
        except Exception as error: self.log(f"Could not load saved queues: {error}",True)

    def _save(self,*unused):
        if self.loading: return
        try:
            STATE.parent.mkdir(parents=True,exist_ok=True)
            data={"queues":self.queues,"mission_team":self.mission_team_spin_box.value(),
                  "timeline_team":1,"allow_sweep":self.acquire_heroic_quest_rewards_checkbox.isChecked(),"objective_rules_version":1,
                  'background_input':self.background_input,'zombie_queue_version':1,'converging_queue_version':1}
            temporary=STATE.with_suffix(".tmp")
            temporary.write_text(json.dumps(data,indent=2),encoding="utf-8")
            temporary.replace(STATE)
        except OSError as error:self.log(f"Could not save settings: {error}",True)

    def _populate(self):
        self.loading=True
        self.queue_list_widget.clear()
        for index,data in enumerate(self.queues[self.queue_index]):
            mode=data["mode"]
            item=QtWidgets.QListWidgetItem(mode + ("  · Normal only" if mode=="ALLIANCE BATTLE" else "  · manual" if mode in MANUAL else ""))
            item.setData(QtCore.Qt.UserRole,mode)
            item.setData(QtCore.Qt.UserRole+1,index)
            item.setFlags(item.flags()|QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked if data["enabled"] else QtCore.Qt.Unchecked)
            self.queue_list_widget.addItem(item)
        for index,button in enumerate(self.queue_buttons): button.setChecked(index==self.queue_index)
        self.loading=False
        self.refresh_task_statuses()

    def queue_changed(self,*unused):
        if self.loading or self.queue_engine.running:return
        # Display order groups completed tasks at the bottom. Checkbox edits
        # still address the original entry, including duplicate mode entries.
        for i in range(self.queue_list_widget.count()):
            item=self.queue_list_widget.item(i);index=item.data(QtCore.Qt.UserRole+1)
            self.queues[self.queue_index][index]['enabled']=item.checkState()==QtCore.Qt.Checked
        self._save()

    def queue_reordered(self,*unused):
        if self.loading or self.queue_engine.running:return
        self.queues[self.queue_index]=[{"mode":self.queue_list_widget.item(i).data(QtCore.Qt.UserRole),
            "enabled":self.queue_list_widget.item(i).checkState()==QtCore.Qt.Checked}
            for i in range(self.queue_list_widget.count())]
        self.loading=True
        try:
            for i in range(self.queue_list_widget.count()):
                self.queue_list_widget.item(i).setData(QtCore.Qt.UserRole+1,i)
        finally:self.loading=False
        self._save();self.refresh_task_statuses()

    def switch_queue(self,index):
        if self.queue_engine.running:return
        self.queue_index=index
        self._populate()

    def add_mode(self):
        if self.queue_engine.running:return
        name,ok=QtWidgets.QInputDialog.getItem(self,"Add farming task","Content:",MODES,0,False)
        if ok:
            self.queues[self.queue_index].append({"mode":name,"enabled":True})
            self._populate();self._save()

    def edit_mode(self):
        if self.queue_engine.running:return
        item=self.queue_list_widget.currentItem()
        if item is None:return
        old=self.queues[self.queue_index][item.data(QtCore.Qt.UserRole+1)]
        name,ok=QtWidgets.QInputDialog.getItem(self,"Edit farming task","Content:",MODES,MODES.index(old["mode"]),False)
        if ok:
            old["mode"]=name
            self._populate();self._save()

    def remove_modes(self):
        if self.queue_engine.running:return
        rows=sorted((item.data(QtCore.Qt.UserRole+1) for item in self.queue_list_widget.selectedItems()),reverse=True)
        for row in rows: del self.queues[self.queue_index][row]
        self._populate();self._save()

    def connect_emulator(self):
        if self.emulator_recovering():return
        if self.frame_task is not None:
            self.log('Background connection/capture is already in progress');return
        try:
            from lib.background_input import AdbBackend,set_backend
            set_backend(None,required=self.background_input)
            self.adb_backend=None
            if self.background_input:
                self.handle=find_bluestacks(allow_minimized=True)
                backend=AdbBackend(instance_hint=bluestacks_title(self.handle))
                backend.input_audit_path=ROOT/'diagnostics/input-actions.jsonl'
                self.adb_backend=backend;self.adb_frame=None
                self.label_username.setText('BlueStacks: connecting in background')
                self.request_adb_frame(connect=True)
                return
            else:self.handle=find_bluestacks()
            self.label_username.setText('BlueStacks: background ADB' if self.background_input else 'BlueStacks: foreground mouse')
            self.refresh_preview()
            self.log('Background ADB connected: mouse/focus untouched.' if self.background_input else 'Foreground input connected: game actions use the mouse.')
        except Exception as error:
            self.handle=None
            self.label_username.setText("BlueStacks: disconnected")
            self.log(str(error),True)

    def set_background_input(self,enabled):
        if self.queue_engine.running or self.busy:return
        from lib.background_input import set_backend
        self.background_input=bool(enabled);self.adb_backend=None;self.handle=None
        set_backend(None,required=self.background_input)
        self.label_username.setText('BlueStacks: disconnected')
        self.log('Input mode changed. Connect BlueStacks again.');self._save()

    def capture(self):
        if not self.handle:raise RuntimeError("Click Connect BlueStacks first")
        if self.background_input:
            if self.adb_frame is None:raise RuntimeError('Waiting for a background screenshot')
            image,data,observed=self.adb_frame
            if not timedelta(0)<=datetime.now(timezone.utc)-observed<=timedelta(seconds=30):raise RuntimeError('Waiting for a fresh background screenshot')
            pixmap=QtGui.QPixmap();pixmap.loadFromData(data,'PNG')
            return image,pixmap
        screen=QtWidgets.QApplication.primaryScreen()
        pixmap=screen.grabWindow(self.handle)
        if pixmap.isNull():raise RuntimeError("Could not capture BlueStacks. Keep its window restored and visible.")
        data=QtCore.QByteArray()
        buffer=QtCore.QBuffer(data)
        buffer.open(QtCore.QIODevice.WriteOnly)
        pixmap.save(buffer,"PNG")
        return Image.open(BytesIO(bytes(data))).convert("RGB"),pixmap

    def refresh_preview(self):
        self.update_gbr()
        if not self.handle:return
        if self.background_input:
            now=datetime.now(timezone.utc)
            idle_queue=(self.queue_engine.running and self.queue_target is None and not self.queue_engine.pending
                and self.queue_wake is not None and self.queue_wake>now+timedelta(seconds=10))
            if not (self.resource_active or self.objective_active or self.trivia_active or self.busy) and (not self.queue_engine.running or idle_queue):
                if now>=getattr(self,'preview_next',now):
                    self.preview_next=now+timedelta(seconds=5)
                    self.request_adb_frame()
            return
        try:
            image,pixmap=self.capture()
            self.last_image=image
            self.screen_label.setPixmap(pixmap.scaled(self.screen_label.size(),QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation))
        except Exception as error:
            self.handle=None
            self.label_username.setText("BlueStacks: disconnected")
            self.log(str(error),True)

    def request_adb_frame(self,connect=False,for_scan=False):
        if self.emulator_recovering():return
        if self.adb_backend is None:return
        self.frame_waiting_scan=self.frame_waiting_scan or for_scan
        if self.frame_task is not None:return
        task=BackgroundFrameTask(self.adb_backend,connect,self)
        self.frame_task=task
        task.result.connect(self.adb_frame_ready)
        task.failed.connect(self.adb_frame_failed)
        task.finished.connect(self.adb_frame_finished)
        task.start()

    def adb_frame_ready(self,backend,image,data,observed):
        if backend is not self.adb_backend or not self.background_input:return
        self.capture_failure_count=0
        self.emulator_capture_failed_since=None
        from lib.background_input import set_backend
        first=self.adb_frame is None
        self.adb_frame=(image,data,observed);set_backend(backend,required=True)
        self.label_username.setText('Background ADB • frame '+observed.astimezone().strftime('%H:%M:%S'))
        pixmap=QtGui.QPixmap();pixmap.loadFromData(data,'PNG')
        self.screen_label.setPixmap(pixmap.scaled(self.screen_label.size(),QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation))
        if first:self.log('Background ADB connected: mouse/focus untouched.')
        if first and getattr(self,'start_queue_after_connect',False):
            self.start_queue_after_connect=False
            QtCore.QTimer.singleShot(0,self.toggle_queue)

    def adb_frame_failed(self,backend,error):
        if backend is not self.adb_backend:return
        self.log('Background capture: '+error,True)
        if self.try_emulator_recovery(error):return
        self.frame_waiting_scan=False
        if not backend.connected:
            self.handle=None;self.label_username.setText('BlueStacks: disconnected')
        if self.queue_engine.running:
            if not backend.connected:
                self.stop_queue();self.log('Connection failed. Reconnect BlueStacks before starting the queue; submitted state preserved.',True);return
            self.capture_failure_count=getattr(self,'capture_failure_count',0)+1
            if self.capture_failure_count>=4:
                self.capture_failure_count=0
                if self.zombie_protected():
                    if self.zombie_started and datetime.now(timezone.utc)-self.zombie_started<=timedelta(minutes=35):
                        self.queue_pause('Zombie capture unavailable; submitted repeat left running',15,stalled=False)
                    else:self.stop_queue();self.log('Zombie capture deadline reached; saved submission retained, game left running',True)
                    return
                if self.story_restart_protected():
                    self.queue_pause('Story capture unavailable; automatic restart suppressed',15,stalled=False);return
                if self.arena_repeat_protected():
                    started=getattr(self,'arena_started',None)
                    now=datetime.now(timezone.utc)
                    if started is not None and timedelta(0)<=now-started<=timedelta(minutes=35):
                        self.queue_pause('Arena capture unavailable; waiting for a fresh result without interrupting the submitted repeat',15,stalled=False)
                    else:
                        self.stop_queue();self.log('Arena capture outcome timed out; submitted state preserved and game left untouched.',True)
                    return
                if self.queue_target or self.queue_engine.pending:self.recover_stuck_queue('Four consecutive capture failures')
                if self.queue_engine.running:self.restart_stuck_game()
                return
            self.queue_pause('Waiting for background capture',10,stalled=False)

    def adb_frame_finished(self):
        task=self.frame_task;self.frame_task=None
        if task:task.deleteLater()
        if self.close_after_capture:self.close();return
        if self.frame_waiting_scan:
            self.frame_waiting_scan=False
            if self.adb_frame is not None:
                self.scan_live(frame=self.adb_frame)

    def scan_live(self,frame=None):
        if self.emulator_recovering():return
        if self.busy:return
        if self.background_input and frame is None:
            if not self.handle:
                self.log('Click Connect BlueStacks first');return
            self.request_adb_frame(for_scan=True);return
        try:
            if frame is not None:
                image,data,captured_at=frame
                if not timedelta(0)<=datetime.now(timezone.utc)-captured_at<=timedelta(seconds=30):return
                pixmap=QtGui.QPixmap();pixmap.loadFromData(data,'PNG')
            else:
                captured_at=datetime.now(timezone.utc)
                image,pixmap=self.capture()
            self.screen_label.setPixmap(pixmap.scaled(self.screen_label.size(),QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation))
            kind="screen"
            if self.trivia_active:kind="trivia"
            elif self.objective_active:kind="objectives"
            elif self.queue_engine.running and not self.resource_active:
                kind="board" if self.queue_phase=="board" else "sweep" if self.queue_phase in ("sweep","sweep_result") else "screen"
                if self.queue_phase=="arena":kind="arena"
                elif self.queue_phase=="converging":kind="converging"
                elif self.queue_phase=='story':kind='story'
                elif self.queue_phase=="world_event":kind="world_event"
                elif self.queue_phase=='zombie':kind='zombie'
                elif self.queue_phase=="alliance":kind="alliance"
                elif self.queue_phase=='recover_home':kind='recover_home'
                elif self.queue_phase=='uncertain_review':kind='uncertain_review'
                elif self.queue_phase=='daily_board_check':kind='daily_board_check'
                elif self.queue_phase=='dispatch_supplies':kind='dispatch_supplies'
                elif self.queue_phase=="dimension_claim":kind="sweep"
                elif self.queue_phase=="dispatch":kind="dispatch"
            elif self.queue_engine.pending and not self.resource_active:
                kind="alliance" if self.queue_engine.pending[1]=="ALLIANCE BATTLE" else "dispatch" if self.queue_engine.pending[1]=="DISPATCH 7-1" else "sweep_result"
                if self.queue_engine.pending[1]=='ZOMBIE SURVIVAL':kind='zombie'
                elif self.queue_engine.pending[1]=='STORY ULTIMATE':kind='story'
                elif self.queue_engine.pending[1] in ('TIMELINE BATTLE','OTHERWORLD BATTLE','TEAM BATTLE ARENA'):kind='arena'
            if kind=='arena' and getattr(self,'arena_resumed',False):
                kind='arena_resume'
            self.scan(image,captured_at,True,kind)
        except Exception as error:
            self.log(str(error),True)
            if self.trivia_active:self.finish_trivia("Capture failed; restore BlueStacks")
            elif self.objective_active:self.finish_objectives("Capture failed; restore BlueStacks")
            elif self.resource_active:self.finish_resource_check("Capture failed; check stopped",True)
            elif self.queue_engine.running:self.queue_pause("Capture failed; restore BlueStacks",60)

    def open_image(self,directory=""):
        if self.busy:return
        path,_=QtWidgets.QFileDialog.getOpenFileName(self,"Open game screenshot",directory if isinstance(directory,str) else "","Images (*.png *.jpg *.jpeg)")
        if not path:return
        try:
            image=Image.open(path).convert("RGB")
            pixmap=QtGui.QPixmap(path)
            self.screen_label.setPixmap(pixmap.scaled(self.screen_label.size(),QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation))
            self.scan(image,datetime.now(timezone.utc),False)
        except Exception as error:self.log(str(error),True)

    def open_example(self):self.open_image(str(ROOT/"tests/fixtures"))

    def scan(self,image,captured_at,live,reader_kind="screen"):
        if self.busy:return
        self.busy=True
        self.restart_game_button.setEnabled(False)
        self.statusBar().showMessage("Reading game screen…")
        self.task=ScanTask(image,captured_at,live,resource_check=self.resource_active or self.queue_engine.running,reader_kind=reader_kind,home_probe=bool(getattr(self,'queue_fresh_pass',False) and self.queue_engine.pending))
        self.task.result.connect(self.show_evidence)
        self.task.failed.connect(self.scan_failed)
        self.task.finished.connect(self.scan_finished)
        self.task.start()

    def scan_finished(self):
        self.busy=False
        self.restart_game_button.setEnabled(not self.queue_engine.running)
        if self.queue_engine.running:
            task='GBR reward check' if self.resource_active else 'World Event' if self.world_event_active else 'Dispatch supplies' if self.dispatch_supply_active else self.queue_target or 'selecting next task'
            self.statusBar().showMessage("Queue running — "+task)
        else:self.statusBar().showMessage("Ready • No crystals, refills or upgrades")
        if self.session_reload_deadline and not self.resource_observation and not self.queue_observation:return
        if self.trivia_active:QtCore.QTimer.singleShot(0,self.advance_trivia)
        elif self.objective_active:QtCore.QTimer.singleShot(0,self.advance_objectives)
        elif self.resource_active:QtCore.QTimer.singleShot(0,self.advance_resource_check)
        elif self.queue_engine.running:QtCore.QTimer.singleShot(0,self.advance_queue)

    def scan_failed(self,text):
        if self.emulator_recovering():return
        self.log(f"Screen check failed: {text}",True)
        if self.trivia_active:self.finish_trivia("OCR failed: "+text)
        elif self.objective_active:self.finish_objectives("OCR failed: "+text)
        elif self.resource_active:self.finish_resource_check("OCR failed; resource check stopped",True)
        elif self.queue_engine.running:self.queue_pause("Screen read failed: "+text,60)

    def show_evidence(self,evidence,captured_at,live):
        if live and self.emulator_recovering():return
        if live and self.emulator_frame_floor and captured_at<self.emulator_frame_floor:
            QtCore.QTimer.singleShot(1500,self.scan_live);return
        if (live and self.queue_engine.running and evidence.screen=='android_home' and self.emulator_game_loading_until
                and datetime.now(timezone.utc)<self.emulator_game_loading_until):
            self.queue_wake=datetime.now(timezone.utc)+timedelta(seconds=5);return
        if live and self.interrupted_emulator_home(evidence,captured_at):return
        last_input=getattr(self.adb_backend,'last_input_at',None) if self.adb_backend is not None else None
        if live and isinstance(last_input,datetime) and captured_at<=last_input:
            self.queue_observation=None;self.trivia_observation=None;self.objective_observation=None;self.resource_observation=None
            self.log('Discarded screenshot captured before the previous input finished; requesting a fresh frame')
            if self.queue_engine.running or self.trivia_active or self.objective_active or self.resource_active:
                QtCore.QTimer.singleShot(1500,self.scan_live)
            return
        self.last_evidence=(evidence,captured_at,live)
        if live and self.adb_backend is not None:
            self.adb_backend.input_evidence=dict(screen=evidence.screen,mode=self.queue_target,phase=self.queue_phase,captured_at=captured_at.isoformat(),pending=list(self.queue_engine.pending) if self.queue_engine.pending else None,repeat_ended=self.zombie_repeat_finished if self.zombie_protected() else self.arena_repeat_finished)
        # Preserve separate live evidence for each mode and screen. These are
        # diagnostics, never templates or authorization for a later input.
        if live and self.task is not None and isinstance(getattr(self.task,'image',None),Image.Image):
            pending=self.queue_engine.pending
            expected=self.queue_target or (pending[1] if pending else None)
            mode=evidence.values.get('mode') or ('WORLD EVENT' if self.world_event_active else 'DAILY TRIVIA' if self.trivia_active else expected)
            if mode:
                folder=''.join(c.lower() if c.isalnum() else '_' for c in mode)
                screen=''.join(c if c.isalnum() else '_' for c in evidence.screen)
                target=ROOT/'diagnostics/modes'/folder
                try:
                    target.mkdir(parents=True,exist_ok=True)
                    self.task.image.save(target/(screen+'.png'),compress_level=1)
                    (target/(screen+'.json')).write_text(json.dumps(dict(captured_at=captured_at.isoformat(),expected_mode=expected,evidence=asdict(evidence)),indent=2),encoding='utf-8')
                except OSError as error:self.log('Could not retain mode diagnostic: '+str(error),True)
        source="Live" if live else "Saved image"
        self.log(f"{source}: {evidence.screen}")
        for key,value in evidence.values.items(): self.log(f"  {key}: {value}")
        for error in evidence.errors:self.log(error,True)
        if live:
            if evidence.screen=='network_retry_notice':
                active=lambda:self.queue_engine.running or self.trivia_active or self.objective_active or self.resource_active
                now=datetime.now(timezone.utc)
                if not active() or not evidence.values.get('retry_verified') or not timedelta(0)<=now-captured_at<=timedelta(seconds=30):return
                attempts=[t for t in getattr(self,'network_retry_attempts',[]) if now-t<timedelta(minutes=5)]
                if len(attempts)>=3:
                    if self.trivia_active:self.finish_trivia('Network retry limit reached; answer outcome remains unverified')
                    if self.objective_active:self.finish_objectives('Network retry limit reached')
                    if self.resource_active:self.finish_resource_check('Network retry limit reached',True)
                    if self.queue_engine.running:self.stop_queue()
                    self.log('Persistent network error: stopped with submitted outcomes preserved',True);return
                self.queue_observation=None;self.trivia_observation=None;self.objective_observation=None;self.resource_observation=None
                if not attempts or now-attempts[-1]>=timedelta(seconds=20):
                    # Latch before input; an uncertain transport never causes
                    # an immediate repeated acknowledgement or mission replay.
                    self.network_retry_attempts=attempts+[now]
                    if self.queue_engine.pending or self.world_event_state.pending or self.world_event_state.started:
                        self.emulator_pending_interrupted=True
                    click_game_point(self.handle,*evidence.values['ok_point'],
                        guard=lambda:active() and timedelta(0)<=datetime.now(timezone.utc)-captured_at<=timedelta(seconds=30))
                    if self.trivia_active and self.trivia_session:self.trivia_session.started=now
                    self.log('Accepted verified network retry notice; waiting for the result or game reload')
                self.queue_wake=now+timedelta(seconds=5)
                QtCore.QTimer.singleShot(5000,self.scan_live);return
            if evidence.screen=='quest_notification_panel':
                active=lambda:self.queue_engine.running or self.trivia_active or self.objective_active or self.resource_active
                now=datetime.now(timezone.utc)
                if not active() or not evidence.values.get('panel_verified') or not timedelta(0)<=now-captured_at<=timedelta(seconds=30):return
                attempts=[t for t in getattr(self,'notification_dismissals',[]) if now-t<timedelta(minutes=1)]
                if len(attempts)>=3:
                    if self.trivia_active:self.finish_trivia('Quest notification panel did not close')
                    if self.objective_active:self.finish_objectives('Quest notification panel did not close')
                    if self.resource_active:self.finish_resource_check('Quest notification panel did not close',True)
                    if self.queue_engine.running:self.stop_queue()
                    self.log('Repeated notification panel: stopped with pending outcomes preserved',True);return
                self.queue_observation=None;self.trivia_observation=None;self.objective_observation=None;self.resource_observation=None
                if not attempts or now-attempts[-1]>=timedelta(seconds=3):
                    click_game_point(self.handle,*evidence.values['close_point'],
                        guard=lambda:active() and timedelta(0)<=datetime.now(timezone.utc)-captured_at<=timedelta(seconds=30))
                    self.notification_dismissals=attempts+[now]
                    self.log('Closed verified quest notification panel using the exclamation circle; requesting fresh evidence')
                QtCore.QTimer.singleShot(3000,self.scan_live);return
            if self.fresh_queue_home_check(evidence,captured_at):return
            if self.navigation_back_recovery(evidence,captured_at):return
            if evidence.screen=='game_title':
                now=datetime.now(timezone.utc)
                if self.queue_engine.running and timedelta(0)<=now-captured_at<=timedelta(seconds=30):
                    previous=getattr(self,'title_play_at',None)
                    if not evidence.values['loading'] and (previous is None or now-previous>timedelta(seconds=60)):
                        self.title_play_at=now
                        click_game_point(self.handle,*evidence.values['point'],guard=lambda:self.queue_engine.running)
                        self.log('Verified MFF title screen: Play; waiting for login')
                    if self.trivia_active:self.finish_trivia('Game is loading; retry after login')
                    self.queue_wake=now+timedelta(seconds=5)
                return
            if evidence.screen=='exit_game':
                if (self.queue_engine.running or self.resource_active or self.trivia_active or self.objective_active):
                    click_game_point(self.handle,*evidence.values['cancel_point'],
                        guard=lambda:timedelta(0)<=datetime.now(timezone.utc)-captured_at<=timedelta(seconds=30))
                    self.log('Cancelled Exit Game confirmation; resuming the active check')
                    self.queue_wake=datetime.now(timezone.utc)+timedelta(seconds=3)
                    if self.trivia_active:QtCore.QTimer.singleShot(3000,self.trivia_rescan)
                    elif self.resource_active:QtCore.QTimer.singleShot(3000,self.resource_rescan)
                    elif self.objective_active:QtCore.QTimer.singleShot(3000,self.objective_rescan)
                return
            if evidence.screen=='android_home':
                now=datetime.now(timezone.utc)
                if not timedelta(0)<=now-captured_at<=timedelta(seconds=30):return
                if (self.queue_engine.running and not self.queue_engine.pending and not self.story_restart_protected()
                        and not self.world_event_state.pending and not self.world_event_state.started and evidence.values.get('launch_point')):
                    attempts=[stamp for stamp in getattr(self,'launcher_attempts',[]) if now-stamp<timedelta(hours=1)]
                    if len(attempts)<2:
                        if attempts and now-attempts[-1]<timedelta(seconds=60):
                            self.queue_wake=now+timedelta(seconds=5);return
                        if self.objective_active:self.finish_objectives('Game left foreground; reopening and restarting inspection')
                        if self.trivia_active:self.finish_trivia('Game left foreground; reopening before retry')
                        if self.resource_active:self.finish_resource_check('Game left foreground; reopening before retry',True)
                        click_game_point(self.handle,*evidence.values['launch_point'],guard=lambda:self.queue_engine.running and not self.queue_engine.pending)
                        self.launcher_attempts=attempts+[now]
                        self.queue_target=None;self.queue_waiting=None;self.queue_observation=None
                        self.queue_recovering=True;self.queue_recovery_steps=0;self.queue_phase='recover_home'
                        self.queue_wake=now+timedelta(seconds=15);self.session_reload_deadline=now+timedelta(minutes=3)
                        self.log('Verified Android launcher: reopening MFF once, then restarting unfinished checks; no battle was submitted')
                        return
                if self.queue_engine.running:
                    self.persist_pending_clear()
                    self.stop_queue()
                    self.log('Android home detected: MFF is no longer on screen. Queue stopped; submitted outcome preserved, no completion inferred or battle replayed.',True)
                elif self.resource_active:self.finish_resource_check('Android home detected; reopen MFF before checking GBR',True)
                return
            if evidence.screen=="session_replaced":
                if self.trivia_active:
                    self.finish_trivia("Session replaced; reload the game before Daily Trivia")
                    self.trivia_retry_at=datetime.now(timezone.utc)+timedelta(seconds=20)
                self.recover_session(captured_at)
                return
            self.session_notice_acknowledged=False
            if self.session_reload_deadline:
                now=datetime.now(timezone.utc)
                if evidence.screen=="unknown" and now<self.session_reload_deadline:
                    self.queue_wake=now+timedelta(seconds=5)
                    if self.resource_active:QtCore.QTimer.singleShot(5000,self.resource_rescan)
                    elif self.objective_active:QtCore.QTimer.singleShot(5000,self.objective_rescan)
                    return
                self.session_reload_deadline=None
            if self.trivia_active:self.trivia_observation=(evidence,captured_at)
            elif self.objective_active:self.objective_observation=(evidence,captured_at)
            elif self.resource_active:self.resource_observation=(evidence,captured_at)
            elif self.queue_engine.running:self.queue_observation=(evidence,captured_at)
            else:
                decision=evaluate(evidence,captured_at,datetime.now(timezone.utc))
                self.log(f"{decision.action.value.upper()}: {decision.reason}")
                if self.queue_engine.pending and evidence.screen=="sweep_result" and evidence.values.get("result_verified"):
                    self.record_completed(self.queue_engine.pending[1],captured_at,datetime.now(timezone.utc))
                    self.log("Previous clear verified; queue can be started again")
            for key in ("soul","seed"):
                if key in evidence.values:
                    self.latest_counters[key]=(evidence.values[key],captured_at)
                    self.raid_gate.observe(key,evidence.values[key],captured_at,datetime.now(timezone.utc))
            if any(key in evidence.values for key in ("soul","seed")):self.persist_gbr_clearance()
            if "boost" in evidence.values:
                self.resource_balances=({'boost':evidence.values['boost']},captured_at)
            self.update_gbr()
        else:self.log("Example/image evidence does not unlock energy or boost farming.")

    def recover_session(self,captured_at):
        now=datetime.now(timezone.utc)
        if not (self.queue_engine.running or self.resource_active or self.objective_active):
            self.log("Session replaced. Start Queue or Check Resources to reload the game.")
            return
        if not timedelta(0)<=now-captured_at<=timedelta(seconds=30):return
        if self.session_notice_acknowledged:
            if self.session_reload_deadline and now>=self.session_reload_deadline:
                if self.queue_engine.running:self.stop_queue()
                elif self.resource_active:self.finish_resource_check("Session notice did not close; inspect the game",True)
                self.session_reload_deadline=None
            else:
                self.queue_wake=now+timedelta(seconds=5)
                if self.resource_active:QtCore.QTimer.singleShot(5000,self.resource_rescan)
            return
        # Latch before input: an uncertain click must never be repeated blindly.
        self.session_notice_acknowledged=True
        self.session_reload_deadline=now+timedelta(seconds=90)
        self.raid_gate=DailyRaidGate()
        self.queue_engine.gate=self.raid_gate
        self.persist_gbr_clearance()
        self.dispatch_supply_active=False;self.dispatch_supply_waiting=None
        self.objective_plan=None;self.objective_period=None
        self.persist_objective_cache()
        if self.objective_active:self.objective_inspection=ObjectiveInspection(now)
        self.latest_counters.clear()
        self.resource_balances=None
        self.queue_observation=None
        self.resource_observation=None
        self.queue_waiting=None
        self.resource_waiting=None
        self.queue_phase="dimension_nav" if self.queue_target=="DIMENSION MISSION" else "navigate_board"
        self.queue_wake=now+timedelta(seconds=10)
        self.update_gbr()
        try:
            click_game_point(self.handle,640,538,
                guard=lambda:self.queue_engine.running or self.resource_active or self.objective_active)
        except Exception as error:
            self.log("Session OK outcome uncertain: "+str(error),True)
            if self.queue_engine.running:self.stop_queue()
            elif self.resource_active:self.finish_resource_check("Session recovery needs attention",True)
            return
        self.log("Session notice acknowledged. Waiting for reload; fresh GBR check required.")
        if self.resource_active:
            self.resource_started=now
            self.resource_steps=0
            QtCore.QTimer.singleShot(10000,self.resource_rescan)
        elif self.objective_active:QtCore.QTimer.singleShot(10000,self.objective_rescan)

    def check_objectives(self,force=False):
        if self.trivia_active:return
        if self.objective_active:
            self.finish_objectives("Objective inspection cancelled");return
        if self.busy or self.resource_active:return
        if not force and self.objective_plan_current(datetime.now(timezone.utc)):
            self.log('Using cached Dimension/Dispatch requirements until reset');return
        if force:
            self.objective_plan=None;self.objective_period=None;self.persist_objective_cache()
        if not self.handle:self.connect_emulator()
        if not self.handle:return
        self.objective_active=True
        self.objective_observation=None
        self.objective_inspection=ObjectiveInspection(datetime.now(timezone.utc))
        self.objective_waiting=None
        self.comic_cards_button.setText("Cancel Objectives")
        self.log("Inspecting Daily Challenges and active events; Otherworld/Future Pass excluded")
        self.scan_live()

    def objective_rescan(self):
        if self.objective_active and not self.busy:self.scan_live()

    def finish_objectives(self,error=None):
        self.objective_active=False
        self.objective_waiting=None
        self.comic_cards_button.setText("Check Objectives")
        if error:
            self.objective_plan=None;self.objective_period=None
            self.persist_objective_cache()
            self.log("Objective inspection stopped: "+error,True)
            if self.queue_engine.running:self.queue_pause("Objective inspection: "+error,60)
        else:
            self.objective_plan=self.objective_inspection.plan
            self.objective_period=self.objective_inspection.period
            self.objective_checked_at=datetime.now(timezone.utc)
            self.objective_refresh_due=False
            self.persist_objective_cache()
            plan=self.objective_plan
            if plan.dimension_clears and 'DIMENSION MISSION' in self.queue_engine.completed:
                # A fresh objective can ask for additional clears after an
                # earlier batch; its remaining counter supersedes that cache.
                self.queue_engine.completed.remove('DIMENSION MISSION')
                if not self.persist_completed_missions():
                    self.stop_queue();self.log('Could not save refreshed Dimension requirements',True);return
            self.log(f"Objectives: Dimension clears {plan.dimension_clears}; contribution claim {plan.claim_contribution}; Dispatch 7-1 energy clears {plan.dispatch_clears}")
            for title in sorted(self.objective_inspection.max_level_passes):
                self.log('Ignored remaining challenges for verified MAX LEVEL pass: '+title)
            self.reconcile_held_dimension_objectives()
            self.queue_wake=datetime.now(timezone.utc)+timedelta(seconds=3)
        if self.review_mode=='DIMENSION MISSION':
            self.finish_uncertain_review('objective verification incomplete; Dimension remains held without replay' if error else 'objectives still require Dimension work; submitted outcome remains held')

    def advance_objectives(self):
        if not self.objective_active or not self.objective_observation:return
        evidence,observed=self.objective_observation;self.objective_observation=None
        now=datetime.now(timezone.utc)
        if not timedelta(0)<=now-observed<=timedelta(seconds=30):
            QtCore.QTimer.singleShot(1000,self.objective_rescan);return
        if self.objective_waiting:
            expected,started=self.objective_waiting
            if evidence.screen not in expected:
                if now-started>timedelta(seconds=30):
                    self.finish_objectives("Navigation did not reach "+" / ".join(expected));return
                QtCore.QTimer.singleShot(2000,self.objective_rescan);return
            self.objective_waiting=None
        try:
            action=self.objective_inspection.observe(evidence,now)
            if self.objective_inspection.done:
                if evidence.screen=="benefit_list":
                    click_game_point(self.handle,640,593,guard=lambda:self.objective_active)
                self.finish_objectives();return
            kind,x,y=action
            if kind=='wait':
                self.log('Objective inspection: rechecking home for the Event Quest shortcut before treating it absent')
                QtCore.QTimer.singleShot(3000,self.objective_rescan);return
            expected=None
            if kind=="home":expected=("game_home",)
            elif kind=='menu':expected=('objective_menu',)
            elif kind in ('scroll','scroll_up'):expected=(evidence.screen,)
            elif evidence.screen=='game_home':
                expected=('event_quest_objectives',) if self.objective_inspection.phase=='quest' else ('benefit_list',) if self.objective_inspection.phase=='benefits' else ('objective_menu',) if (x,y)==(1249,37) else ('daily_objectives','challenges_other_tab')
            elif evidence.screen=='objective_menu' or evidence.screen=='challenges_other_tab':expected=('daily_objectives','challenges_other_tab')
            elif (x,y)==(1110,181):expected=("event_objectives",)
            elif evidence.screen=="benefit_list":expected=("event_rewards","event_objectives")
            if expected:self.objective_waiting=(expected,now)
            self.log("Objective navigation: "+kind+f" ({x},{y})")
            click_game_point(self.handle,x,y,scroll=("down",4) if kind=="scroll" else ('up',8) if kind=='scroll_up' else None,
                guard=lambda:self.objective_active)
            QtCore.QTimer.singleShot(2500,self.objective_rescan)
        except Exception as error:self.finish_objectives(str(error))

    def update_gbr(self):
        now=datetime.now(timezone.utc)
        valid={key:value for key,value in self.latest_counters.items() if reset_period(value[1])==reset_period(now) and
            (self.raid_gate.cleared(now) or timedelta(0)<=now-value[1]<=timedelta(minutes=10))}
        def counter(key):return "/".join(map(str,valid[key][0])) if key in valid else "unknown"
        balances=self.resource_balances[0] if self.resource_balances and timedelta(0)<=now-self.resource_balances[1]<=timedelta(minutes=10) else {}
        energy="/".join(f"{n:,}" for n in balances["energy"]) if "energy" in balances else "unknown"
        boost=str(balances.get("boost","unknown"))
        self.label_energy.setText("Soul of Faltine: "+counter("soul"))
        self.label_gold.setText("Boost points: "+boost+"\nCelestial Seed: "+counter("seed"))
        done=self.raid_gate.cleared(now)
        self.label_boosts.setText("GBR cleared until reset" if done else "Energy / boost farming: blocked")
        self.label_boosts.setToolTip(resource_status(self.latest_counters,self.resource_balances,now,self.raid_gate))

    def check_resources(self,force=False):
        if self.trivia_active:return
        if self.resource_active:
            self.finish_resource_check("Resource check cancelled",True)
            return
        if self.busy:
            self.log("Wait for the current screen check to finish.")
            return
        if not force and self.raid_gate.cleared(datetime.now(timezone.utc)):
            self.log('Using cached GBR clearance until reset; no repeat raid check')
            self.update_gbr()
            if self.resource_pending_queue:
                self.resource_pending_queue=False;self.render_queue_status()
            return
        if not self.handle:self.connect_emulator()
        if not self.handle:return
        if force:
            self.raid_gate=DailyRaidGate();self.queue_engine.gate=self.raid_gate
            self.persist_gbr_clearance()
        self.latest_counters.clear()
        self.resource_balances=None
        self.resource_active=True
        self.resource_waiting=None
        self.resource_steps=0
        self.resource_observation=None
        self.resource_strip_last=None
        self.resource_strip_stalls=0
        self.resource_started=datetime.now(timezone.utc)
        self.dispatch_mission_rewards.setText("Cancel Resource Check")
        self.log("Checking resources: opening GBR rewards. No battle or resource spending.")
        self.scan_live()

    def advance_resource_check(self):
        if not self.resource_active:return
        if not self.resource_observation:
            self.finish_resource_check("No resource observation returned",True);return
        evidence,observed=self.resource_observation
        now=datetime.now(timezone.utc)
        if now-self.resource_started>timedelta(minutes=3) or now-observed>timedelta(seconds=30):
            self.finish_resource_check("Resource check timed out; no action retried",True);return
        if self.resource_waiting:
            expected,started=self.resource_waiting
            if evidence.screen not in expected:
                if now-started>timedelta(seconds=25):
                    self.finish_resource_check("Navigation did not reach "+" / ".join(expected)+"; stopped without retrying the click",True)
                else:QtCore.QTimer.singleShot(1000,self.resource_rescan)
                return
            self.resource_waiting=None
        if all(key in self.latest_counters for key in ("soul","seed")):
            self.finish_resource_check(resource_status(self.latest_counters,self.resource_balances,now));return
        for key,(counter,captured) in self.latest_counters.items():
            if (key in ('soul','seed') and counter[0]>0 and reset_period(captured)==reset_period(now)
                    and timedelta(0)<=now-captured<=timedelta(seconds=30)):
                self.finish_resource_check(key+' rewards remain ('+str(counter[0])+'/'+str(counter[1])+'); boosted missions stay blocked; continuing free modes')
                return
        navigation=next_navigation(evidence,"soul" in self.latest_counters)
        if not navigation:
            detail="; ".join(evidence.errors) or "Unrecognized navigation screen; open the game home or status board"
            self.finish_resource_check(detail,True);return
        if evidence.screen=="gbr_main" and "strip_position" in evidence.values:
            position=(navigation.name,evidence.values["strip_position"])
            self.resource_strip_stalls=self.resource_strip_stalls+1 if position==self.resource_strip_last else 0
            self.resource_strip_last=position
            if self.resource_strip_stalls>=2:
                missing=", ".join(key for key in ("soul","seed") if key not in self.latest_counters)
                self.finish_resource_check("Reward strip stopped moving; unreadable "+missing+" counter. See diagnostics/last-gbr-check.png",True);return
        if self.resource_steps>=14:
            self.finish_resource_check("Navigation limit reached; stopped",True);return
        try:
            self.log("Resource check: "+navigation.name)
            self.resource_steps+=1
            self.resource_waiting=(navigation.expected,now)
            perform_navigation(self.handle,navigation)
            QtCore.QTimer.singleShot(1200,self.resource_rescan)
        except Exception as error:self.finish_resource_check(str(error),True)

    def resource_rescan(self):
        if self.resource_active and not self.busy:self.scan_live()

    def finish_resource_check(self,message,error=False):
        self.gbr_retry_at=datetime.now(timezone.utc)+timedelta(seconds=60)
        self.resource_active=False
        self.resource_waiting=None
        self.dispatch_mission_rewards.setText("Check Resources")
        self.update_gbr()
        self.log("Resource check: "+message,error)
        if self.resource_pending_queue:
            self.resource_pending_queue=False
            self.render_queue_status()
        if self.queue_engine.running:
            if self.raid_gate.cleared(datetime.now(timezone.utc)):
                self.queue_phase="dimension_nav" if self.queue_target=="DIMENSION MISSION" else "navigate_board"
                if self.queue_target=="DISPATCH 7-1":self.queue_phase="dispatch"
                self.queue_wake=None
                self.queue_observation=None
                self.queue_waiting=None
            else:
                self.gbr_retry_at=datetime.now(timezone.utc)+timedelta(seconds=60)
                self.queue_target=None;self.queue_waiting=None;self.queue_wake=None;self.queue_phase='navigate_board'
                self.log('GBR not cleared: boosted missions paused; free modes and Story remain eligible. Recheck in 60 seconds.')

    def check_queue(self):
        if self.resource_active:
            self.resource_pending_queue=True
            self.log("Queue will be checked after the active resource check.")
            return
        if self.busy:
            self.log("Wait for the current screen check to finish.")
            return
        if any(item["enabled"] and item["mode"] in ENERGY_FARMS for item in self.queues[self.queue_index]):
            if self.raid_gate.cleared(datetime.now(timezone.utc)):
                self.log('Check Queue: GBR clearance already verified for this reset')
                self.render_queue_status();return
            self.resource_pending_queue=True
            self.check_resources()
            return
        self.render_queue_status()

    def toggle_queue(self):
        if self.queue_engine.running:
            self.stop_queue();return
        if self.busy or self.resource_active or self.objective_active or self.trivia_active:
            self.log("Wait for the current screen/resource check to finish.");return
        if self.enabled_energy_modes() and not self.acquire_heroic_quest_rewards_checkbox.isChecked():
            self.log("Enable sweep tickets + energy before starting energy farming.");return
        if not self.handle:self.connect_emulator()
        if not self.handle:return
        modes=self.enabled_energy_modes()+self.free_enabled_modes()+(["WORLD EVENT"] if self.world_event_enabled() else [])
        if not modes:
            self.log("Enable a farming mission, Normal Alliance Battle, or World Event.");return
        try:
            self.queue_fresh_pass=bool(self.queue_engine.pending);self.queue_fresh_home_seen=None
            if self.queue_engine.pending:
                self.queue_engine.resume_verification(datetime.now(timezone.utc))
                if self.queue_engine.pending[1] in ('TIMELINE BATTLE','OTHERWORLD BATTLE','TEAM BATTLE ARENA'):
                    self.arena_resumed=True;self.arena_home_seen=None;self.arena_home_verified=False
                self.log('Starting a fresh queue pass. The previous submission will be held for later review once the game is safely outside its automatic run.')
            else:self.queue_engine.start(datetime.now(timezone.utc))
        except RuntimeError as error:self.log(str(error),True);return
        self.world_event_state.rollover(datetime.now(timezone.utc))
        self.objective_refresh_due=True
        if not self.world_event_state.done:self.world_event_state.next_check=datetime.now(timezone.utc)
        self.queue_phase="navigate_board"
        self.queue_target=None
        self.queue_deferred.clear();self.epic_preparation=None
        self.queue_stall_key=None;self.queue_stall_count=0;self.queue_stall_since=None
        self.queue_waiting=None
        self.queue_wake=None
        self.queue_observation=None
        self.queue_scrolls=0
        self.queue_started_period=reset_period(datetime.now(timezone.utc))
        self.board_check_active=False;self.board_check_due=True
        self.run_queue_button.setText("Stop Queue")
        self.set_queue_editable(False)
        self.log("Queue started. Full boosted batches only; GBR clearance expires at 15:00 UTC.")
        for item in self.queues[self.queue_index]:
            if item["enabled"] and item["mode"] not in ENERGY_FARMS|UNBOOSTED_SWEEPS|{"ALLIANCE BATTLE","DISPATCH 7-1","WORLD EVENT","TIMELINE BATTLE","OTHERWORLD BATTLE","TEAM BATTLE ARENA","ZOMBIE SURVIVAL","STORY ULTIMATE"}:
                self.log(item["mode"]+": combat/manual task skipped; combat controls remain shelved")
        self.queue_tick()

    def enabled_energy_modes(self):
        return list(dict.fromkeys(item["mode"] for item in self.queues[self.queue_index]
            if item["enabled"] and item["mode"] in ENERGY_FARMS))

    def alliance_enabled(self):
        return any(item["mode"]=="ALLIANCE BATTLE" and item["enabled"] for item in self.queues[self.queue_index])

    @staticmethod
    def requires_gbr(mode):return mode in ENERGY_FARMS|{'DISPATCH 7-1'}

    def free_enabled_modes(self):
        return [mode for mode in (*sorted(UNBOOSTED_SWEEPS,reverse=True),'TIMELINE BATTLE','OTHERWORLD BATTLE','TEAM BATTLE ARENA','ALLIANCE BATTLE','ZOMBIE SURVIVAL','STORY ULTIMATE')
                if any(i['enabled'] and i['mode']==mode for i in self.queues[self.queue_index])]

    def eligible_modes(self,now):
        modes=[mode for mode in self.planned_modes() if (not self.requires_gbr(mode) or self.raid_gate.cleared(now))
                and now>=self.queue_deferred.get(mode,now) and not self.dimension_priority_blocks(mode,now)]
        if self.dimension_priority_required(now) and self.raid_gate.cleared(now):
            # Keep the requirement first even when the saved queue has Epic
            # farming ahead of it. Deferral must not free its boost for others.
            modes=[mode for mode in modes if mode!='STORY ULTIMATE']
            modes.sort(key=lambda mode:mode!='DIMENSION MISSION')
        return modes

    def objective_plan_current(self,now):
        return (self.objective_plan is not None and self.objective_period==reset_period(now)
            and not self.objective_refresh_due)

    def dimension_priority_required(self,now):
        return (self.objective_plan_current(now)
            and bool(self.objective_plan.dimension_clears or self.objective_plan.claim_contribution)
            and 'DIMENSION MISSION' in self.enabled_energy_modes()
            and not (self.queue_engine.period==reset_period(now) and 'DIMENSION MISSION' in self.queue_engine.completed))

    def dimension_priority_blocks(self,mode,now):
        return (self.requires_gbr(mode) and (not self.objective_plan_current(now)
            or (mode!='DIMENSION MISSION' and self.dimension_priority_required(now))))

    def planned_modes(self):
        modes=[m for m in self.free_enabled_modes() if m!='STORY ULTIMATE']+self.enabled_energy_modes()
        if self.objective_plan:
            if not self.objective_plan.dimension_clears:modes=[mode for mode in modes if mode!="DIMENSION MISSION"]
            if self.objective_plan.dispatch_clears:modes.append("DISPATCH 7-1")
        else:modes=[m for m in modes if m!='DIMENSION MISSION']
        if 'STORY ULTIMATE' in self.free_enabled_modes():modes.append('STORY ULTIMATE')
        held=self.queue_held if self.queue_held_period==reset_period(datetime.now(timezone.utc)) else set()
        return [mode for mode in modes if mode not in held]

    def set_queue_editable(self,enabled):
        for widget in [*self.queue_buttons,self.add_queue_button,self.edit_queue_button,self.remove_queue_button,
                       self.mission_team_spin_box,self.acquire_heroic_quest_rewards_checkbox]:widget.setEnabled(enabled)
        # Keep the view and scrollbar usable while execution is locked.
        self.queue_list_widget.setEnabled(True)
        self.queue_list_widget.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove if enabled else QtWidgets.QAbstractItemView.NoDragDrop)
        editable_flags=QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled
        previous=self.queue_list_widget.blockSignals(True)
        try:
            for i in range(self.queue_list_widget.count()):
                item=self.queue_list_widget.item(i)
                item.setFlags(item.flags()|editable_flags if enabled else item.flags()&~editable_flags)
        finally:self.queue_list_widget.blockSignals(previous)
        for widget in (self.autoplay_button,self.restart_game_button,self.daily_trivia_button,
                       self.comic_cards_button,self.custom_gear_button,self.dispatch_mission_rewards):widget.setEnabled(enabled)
        self.menuBar.setEnabled(enabled)

    def stop_queue(self):
        self.board_check_active=False
        self.emulator_capture_failed_since=None
        self.review_mode=None
        self.start_queue_after_connect=False
        if self.queue_engine.pending:self.persist_pending_clear()
        self.frame_waiting_scan=False
        self.queue_recovering=False
        self.dispatch_supply_active=False
        self.world_event_active=False;self.world_event_waiting=None
        self.epic_preparation=None
        if self.trivia_active:self.finish_trivia('Stopped')
        self.objective_active=False
        self.comic_cards_button.setText("Check Objectives")
        self.queue_engine.stop()
        self.queue_phase="idle"
        self.queue_wake=None
        self.queue_waiting=None
        self.resource_pending_queue=False
        if self.resource_active:self.finish_resource_check("Stopped by Stop Queue")
        self.run_queue_button.setText("Start Queue")
        self.set_queue_editable(True)
        self.statusBar().showMessage("Queue stopped • No further game inputs will be sent")
        self.log("Queue stopped. Any clear already submitted must finish; no new clear will start.")

    def queue_pause(self,reason,seconds=60,phase=None,stalled=True):
        self.task_wait_reason=reason
        if stalled and self.queue_engine.running and self.note_queue_stall(reason):return
        if phase:self.queue_phase=phase
        self.queue_waiting=None
        self.queue_wake=datetime.now(timezone.utc)+timedelta(seconds=seconds)
        self.log("Queue waiting: "+reason)
        self.statusBar().showMessage("Running — "+reason)

    def queue_tick(self):
        if self.emulator_recovering():return
        if getattr(self,'restart_task',None) and self.restart_task.isRunning():return
        if not self.queue_engine.running or self.busy or self.resource_active or self.objective_active or self.trivia_active:return
        now=datetime.now(timezone.utc)
        changed=self.queue_engine.rollover(now)
        if changed:
            self.trivia_retry_at=now
            self.board_check_due=True;self.board_check_active=False
            self.queue_deferred.clear()
            self.log("Daily reset reached. Previous GBR clearance expired; GBR must be checked again.")
            self.queue_wake=None
            self.queue_waiting=None
            if not self.queue_engine.pending:
                self.queue_target=None
                self.queue_phase='recover_home' if self.queue_recovering else 'dispatch_supplies' if self.dispatch_supply_active else 'navigate_board'
        # Trivia is free and time-sensitive. Check before the board/GBR and
        # boost waits, while preserving every submitted or protected run.
        trivia_boundary=(self.queue_target is None or (self.requires_gbr(self.queue_target)
            and self.queue_wake is not None and self.queue_wake>now+timedelta(seconds=30) and self.queue_waiting is None))
        if (not self.queue_engine.pending and not self.queue_recovering and not self.session_reload_deadline
                and not self.review_mode and not self.dispatch_supply_active and not self.world_event_active
                and not self.story_restart_protected() and trivia_boundary and self.trivia_due(now)):
            self.log('Queue: checking Daily Trivia early for this reset')
            self.check_trivia(automatic=True);return
        if (getattr(self,'enable_board_preflight',True) and not self.queue_engine.pending
                and not self.queue_recovering and not self.session_reload_deadline
                and not self.story_restart_protected() and not self.world_event_state.started
                and (self.board_check_active or (self.board_check_due and self.queue_target is None))):
            if not self.board_check_active:self.start_daily_board_check(now)
            self.queue_phase='daily_board_check'
            if not self.queue_wake or now>=self.queue_wake:self.scan_live()
            return
        if self.review_mode:
            if not self.queue_wake or now>=self.queue_wake:self.scan_live()
            return
        if self.queue_recovering:
            self.queue_phase='recover_home'
            if not self.queue_wake or now>=self.queue_wake:self.scan_live()
            return
        if self.session_reload_deadline:
            if not self.queue_wake or now>=self.queue_wake:self.scan_live()
            return
        if self.queue_target=='STORY ULTIMATE' and not self.queue_engine.pending and self.queue_phase=='story':
            self.queue_phase='story'
            if not self.queue_wake or now>=self.queue_wake:self.scan_live()
            return
        if self.queue_target and not self.queue_engine.pending and self.requires_gbr(self.queue_target) and not self.raid_gate.cleared(now):
            self.queue_target=None;self.queue_waiting=None;self.epic_preparation=None
        if not self.queue_engine.pending and self.dimension_priority_blocks(self.queue_target,now):
            self.log('Reselecting mission: verify requirements and finish required Dimension clears before other boosted farming')
            self.queue_target=None;self.queue_waiting=None;self.queue_wake=None;self.epic_preparation=None
            self.queue_phase='navigate_board'
        self.world_event_state.rollover(now)
        if self.world_event_active:
            self.queue_phase='world_event'
            if not self.queue_wake or now>=self.queue_wake:self.scan_live()
            return
        if (not self.queue_engine.pending and self.queue_target is None and not self.dispatch_supply_active and not self.session_reload_deadline
                and self.world_event_enabled() and not self.world_event_state.done and now>=self.world_event_state.next_check):
            self.start_world_event(now);self.scan_live();return
        if not self.queue_engine.pending and not self.session_reload_deadline and (self.dispatch_supply_active or self.queue_target is None):
            if not self.dispatch_supply_active and now>=self.dispatch_supply_next:self.start_dispatch_supplies(now)
            if self.dispatch_supply_active:
                if not self.queue_wake or now>=self.queue_wake:self.scan_live()
                return
        if self.queue_wake and now<self.queue_wake:return
        self.queue_wake=None
        if self.queue_engine.pending:
            self.queue_target=self.queue_engine.pending[1]
            self.queue_phase="alliance" if self.queue_engine.pending[1]=="ALLIANCE BATTLE" else "sweep_result"
            if self.queue_engine.pending[1]=="DISPATCH 7-1":self.queue_phase="dispatch"
            if self.queue_engine.pending[1] in ("TIMELINE BATTLE","OTHERWORLD BATTLE","TEAM BATTLE ARENA"):self.queue_phase="arena"
            if self.queue_engine.pending[1]=='ZOMBIE SURVIVAL':self.queue_phase='zombie'
            elif self.queue_engine.pending[1]=='STORY ULTIMATE':self.queue_phase='story'
            if self.queue_engine.pending[1] in UNBOOSTED_SWEEPS:self.queue_phase='converging'
            if self.contribution_followup:self.queue_phase="dimension_claim"
            self.scan_live();return
        if self.queue_target and self.requires_gbr(self.queue_target) and not self.raid_gate.cleared(now):
            self.queue_target=None;self.queue_waiting=None;self.epic_preparation=None
        available=self.eligible_modes(now)
        free_remaining=any(mode in self.free_enabled_modes() and mode not in self.queue_engine.completed for mode in available)
        blocked=any(self.requires_gbr(mode) and mode not in self.queue_engine.completed for mode in self.planned_modes()) and not self.raid_gate.cleared(now)
        unboosted_remaining=any(mode in UNBOOSTED_SWEEPS and mode not in self.queue_engine.completed for mode in available)
        if blocked and not unboosted_remaining and not self.queue_target and now>=self.gbr_retry_at:
            self.check_resources();return
        if not unboosted_remaining and not self.objective_plan_current(now) and (not free_remaining or self.raid_gate.cleared(now)):
            self.check_objectives();return
        if not self.queue_target:
            self.queue_target=self.queue_engine.next_mode(self.eligible_modes(now),now)
            if not self.queue_target:
                blocked=any(self.requires_gbr(mode) and mode not in self.queue_engine.completed for mode in self.planned_modes()) and not self.raid_gate.cleared(now)
                if blocked:
                    if now>=self.gbr_retry_at:self.check_resources();return
                    self.queue_wake=self.gbr_retry_at
                    self.statusBar().showMessage('Boosted missions waiting for GBR; next check within one minute')
                    return
                deferred=[stamp for mode,stamp in self.queue_deferred.items() if stamp>now and mode in self.planned_modes() and mode not in self.queue_engine.completed]
                if deferred:
                    self.queue_wake=min(deferred);return
                if self.start_uncertain_review(now):self.scan_live();return
                reviews=self.uncertain_review_candidates(now)
                if reviews:
                    self.queue_wake=min(self.review_due.get(mode,now+timedelta(minutes=5)) for mode in reviews)
                    self.statusBar().showMessage('Running — unsure outcomes will be reviewed again');return
                if self.dimension_priority_required(now):
                    self.queue_wake=now+timedelta(seconds=60)
                    self.statusBar().showMessage('Required Dimension clears pending; other boosted farming waits')
                    return
                self.queue_wake=next_reset(now)
                self.queue_phase="navigate_board"
                self.statusBar().showMessage("Running — all enabled energy missions done; waiting for reset")
                self.log("Daily farming finished. Queue monitors World Event and Dispatch rewards until stopped; next reset 15:00 UTC.")
                return
            self.queue_phase="dimension_nav" if self.queue_target=="DIMENSION MISSION" else "navigate_board"
            if self.queue_target=="DISPATCH 7-1":self.queue_phase="dispatch"
            if self.queue_target=='STORY ULTIMATE':self.story_ultimate_verified=None;self.story_navigation_started=now
            self.queue_scrolls=0
            self.queue_last_board=None
            self.queue_max_attempted=False
            self.epic_preparation=None
            self.queue_stall_key=None;self.queue_stall_count=0;self.queue_stall_since=None
            self.log("Queue mission: "+self.queue_target)
        if self.requires_gbr(self.queue_target) and not self.raid_gate.cleared(now):
            self.queue_target=None;self.queue_waiting=None;self.queue_wake=None;return
        self.scan_live()

    def queue_send_point(self,point,phase,expected=()):
        now=datetime.now(timezone.utc)
        if not self.queue_engine.running:return
        if self.requires_gbr(self.queue_target) and not self.raid_gate.cleared(now):
            self.queue_target=None;self.queue_phase="navigate_board";self.queue_waiting=None;self.queue_wake=None;return
        click_game_point(self.handle,int(point[0]),int(point[1]))
        self.queue_phase=phase
        self.queue_waiting=(tuple(expected),datetime.now(timezone.utc)) if expected else None
        self.queue_wake=now+timedelta(seconds=2)
        self.queue_observation=None

    def advance_queue(self):
        if not self.queue_engine.running or self.resource_active or not self.queue_observation:return
        evidence,observed=self.queue_observation
        self.queue_observation=None
        now=datetime.now(timezone.utc)
        if not timedelta(0)<=now-observed<=timedelta(seconds=30):
            self.queue_pause("Refreshing stale screen",2,stalled=False);return
        if evidence.screen in ('zombie_repeat_ended','zombie_repeat_exhausted'):
            pending=self.queue_engine.pending
            if not pending or pending[1]!='ZOMBIE SURVIVAL' or evidence.values.get('mode')!='ZOMBIE SURVIVAL':
                self.queue_wake=now+timedelta(seconds=5);return
            self.queue_target='ZOMBIE SURVIVAL';self.queue_phase='zombie'
            self.queue_recovering=False;self.queue_waiting=None
            self.queue_zombie(evidence,observed);return
        if evidence.screen=='story_ended':
            if self.queue_engine.pending and self.queue_engine.pending[1]!='STORY ULTIMATE':
                self.queue_wake=now+timedelta(seconds=5);self.log('Story summary does not match submitted task; no input',True);return
            self.queue_story(evidence,observed);return
        if evidence.screen in ('arena_exhausted','arena_repeat_ended') and evidence.values.get('point'):
            mode=evidence.values.get('mode')
            if mode not in ('TIMELINE BATTLE','OTHERWORLD BATTLE','TEAM BATTLE ARENA'):return
            pending=self.queue_engine.pending
            if pending and pending[1]!=mode:
                self.queue_wake=now+timedelta(seconds=5);self.log('Arena summary does not match submitted task; no input',True);return
            # A verified terminal popup must reach its controller even if a
            # stale navigation expectation or recovery phase owns the queue.
            self.queue_target=mode;self.queue_phase='arena'
            self.queue_recovering=False;self.queue_waiting=None
            self.queue_arena(evidence,observed);return
        if evidence.screen=='team_arena_ended':
            pending=self.queue_engine.pending
            if pending and pending[1]!='TEAM BATTLE ARENA':
                self.queue_wake=now+timedelta(seconds=5);self.log('Team Arena summary does not match submitted task; no input',True);return
            runs=evidence.values.get('runs')
            expected=pending[2] if pending and pending[1]=='TEAM BATTLE ARENA' else 5
            if type(runs) is int and runs==expected:
                self.record_completed('TEAM BATTLE ARENA',observed,now)
            elif pending and pending[1]=='TEAM BATTLE ARENA':
                self.arena_repeat_finished=True
                if not self.persist_pending_clear():
                    self.stop_queue();self.log('Could not save Team Arena repeat end; leaving summary open',True);return
            self.queue_target='TEAM BATTLE ARENA';self.queue_phase='arena'
            self.queue_recovering=False;self.queue_waiting=None
            click_game_point(self.handle,*evidence.values['point'],guard=lambda:self.queue_engine.running)
            self.queue_wake=now+timedelta(seconds=3);return
        if self.queue_engine.rollover(now):
            self.log("Reset crossed during inspection; GBR check required before any clear")
            if not self.queue_engine.pending:
                self.queue_phase='recover_home' if self.queue_recovering else 'dispatch_supplies' if self.dispatch_supply_active else 'navigate_board'
                self.queue_waiting=None
                if not self.dispatch_supply_active and not self.queue_recovering:return
        if self.queue_recovering:
            self.queue_recover_home(evidence,observed);return
        if self.queue_phase=='uncertain_review':
            self.queue_uncertain_review(evidence,observed);return
        if self.queue_phase=='daily_board_check':
            self.queue_daily_board_check(evidence,observed);return
        if self.queue_phase=='world_event':
            self.queue_world_event(evidence,observed);return
        if self.queue_phase=='dispatch_supplies':
            self.queue_dispatch_supplies(evidence,observed);return
        if self.requires_gbr(self.queue_target) and not self.raid_gate.cleared(now) and not self.queue_engine.pending:
            self.queue_target=None;self.queue_phase="navigate_board";self.queue_waiting=None;self.queue_wake=None;return
        if not self.queue_engine.pending and self.dimension_priority_blocks(self.queue_target,now):
            self.queue_target=None;self.queue_phase='navigate_board';self.queue_waiting=None;self.queue_wake=None
            self.epic_preparation=None;return
        if self.queue_waiting:
            expected,started=self.queue_waiting
            if evidence.screen not in expected:
                if now-started>timedelta(seconds=25):
                    self.queue_pause("Navigation did not reach "+" / ".join(expected)+"; inspect the game",60)
                else:self.queue_wake=now+timedelta(seconds=2)
                return
            self.queue_waiting=None
        try:
            if self.queue_phase=="navigate_board":self.queue_navigate_board(evidence,observed)
            elif self.queue_phase=="board":self.queue_read_board(evidence,observed)
            elif self.queue_phase in ("sweep","sweep_result"):self.queue_read_sweep(evidence,observed)
            elif self.queue_phase=='zombie':self.queue_zombie(evidence,observed)
            elif self.queue_phase=='converging':self.queue_converging(evidence,observed)
            elif self.queue_phase=="alliance":self.queue_read_alliance(evidence,observed)
            elif self.queue_phase=="arena":self.queue_arena(evidence,observed)
            elif self.queue_phase=='story':self.queue_story(evidence,observed)
            elif self.queue_phase=="dimension_nav":self.queue_dimension_nav(evidence)
            elif self.queue_phase=="dimension_claim":self.queue_dimension_claim(evidence,observed)
            elif self.queue_phase=="dispatch":self.queue_dispatch(evidence,observed)
        except Exception as error:
            self.queue_pause("Needs attention: "+str(error),60)

    def queue_navigate_board(self,evidence,observed=None):
        if evidence.screen in ("status_board","content_board"):
            self.queue_phase="board"
            if evidence.screen=='content_board' and observed is not None:self.queue_read_board(evidence,observed)
            return
        if evidence.screen=="navigation_menu":
            self.queue_send_point((630,642),"navigate_board",("status_board","content_board"));return
        if evidence.screen=="gbr_rewards":
            self.queue_send_point((640,648),"navigate_board",("gbr_main",));return
        if evidence.screen in ('gbr_main','world_event','timeline','otherworld','game_home'):
            self.queue_send_point((1249,36),'navigate_board',('navigation_menu',));return
        if evidence.values.get("menu_available"):
            self.queue_send_point((1249,36),"navigate_board",("navigation_menu",));return
        self.queue_pause("Open the game home or Content Status Board; screen is not recognized",60)

    def queue_read_board(self,evidence,observed):
        if evidence.screen!="content_board" or evidence.errors:
            self.queue_pause("Content Status Board not readable",60);return
        # Remember every verified completed tile seen on the way, so selecting
        # another target does not cause a separate trip for each finished quest.
        from lib.gui.widgets.completion_cache import ALLOWED
        now=datetime.now(timezone.utc)
        self.remember_board_completions(evidence,observed)
        for row in evidence.values.get('tiles',[]):
            mode=row.get('mode')
            if mode in ALLOWED and row.get('remaining')==0 and mode not in self.queue_engine.completed:
                self.record_completed(mode,observed,now)
        if self.queue_target is None:
            self.queue_phase='navigate_board';self.queue_wake=None;return
        if self.queue_target in self.queue_engine.completed:
            self.log(self.queue_target+': remembered complete; skipping until reset')
            self.queue_target=None;self.queue_phase='navigate_board';return
        tile=next((tile for tile in evidence.values.get("tiles",[]) if tile["mode"]==self.queue_target),None)
        if tile:
            if tile["remaining"]==0:
                self.record_completed(self.queue_target,observed,datetime.now(timezone.utc))
                self.log(self.queue_target+": done for this reset")
                self.queue_target=None;self.queue_phase="navigate_board";return
            # Alliance's board tile has no entry counter. Its Normal lobby
            if self.queue_target=='STORY ULTIMATE':
                if tile.get('remaining') is None:
                    # A positive named section is enough to start the game's
                    # own Auto Progress. All four marks are required only to
                    # conclude that every section is already complete.
                    section=next((row for row in evidence.values.get('story_themes',{}).values()
                        if type(row.get('remaining')) is int and row['remaining']>0 and not row.get('completed')),None)
                    if section:
                        self.queue_send_point(section['point'],'story',('story_select','story_ultimate'));return
                    if self.queue_scrolls>=8:
                        self.queue_deferred['STORY ULTIMATE']=now+timedelta(minutes=5)
                        self.queue_target=None;self.queue_phase='navigate_board';return
                    from lib.queue_input import scroll_board
                    direction='down' if 'DIMENSIONAL CLASH' in evidence.values.get('story_themes',{}) else 'up'
                    scroll_board(self.handle,direction,3);self.queue_scrolls+=1
                    self.queue_wake=now+timedelta(seconds=3);return
                self.queue_send_point(tile['point'],'story',('story_select','story_ultimate'));return
            # verifies availability and the variant before any battle Start.
            if self.queue_target in UNBOOSTED_SWEEPS:
                self.converging_preparation=None
                self.queue_send_point(tile['point'],'converging',('converging_difficulty','converging_ready','converging_chapter'));return
            if self.queue_target=='ZOMBIE SURVIVAL':
                self.init_zombie()
                self.queue_send_point(tile['point'],'zombie',('zombie_lobby','zombie_season_notice','zombie_prepare','zombie_repeat'));return
            if self.queue_target=="ALLIANCE BATTLE":
                self.queue_send_point(tile["point"],"alliance",("alliance_select_normal","alliance_normal_ready","alliance_normal_setup","alliance_normal_done","alliance_weekly_skip"));return
            if type(tile["remaining"]) is not int:
                self.queue_pause("Remaining entries unreadable for "+self.queue_target,60);return
            if self.queue_target in ("TIMELINE BATTLE","OTHERWORLD BATTLE","TEAM BATTLE ARENA"):
                self.arena_started=None;self.arena_claim_at=None;self.arena_exhausted=False
                self.arena_repeat_finished=False
                self.queue_send_point(tile["point"],"arena");return
            epic=self.queue_target in ENERGY_FARMS-{'DIMENSION MISSION'}
            if epic and evidence.values.get('accelerated_clear'):
                self.queue_send_point((85,690),'board',('content_board',));return
            if not epic and not evidence.values.get("accelerated_clear"):
                self.queue_pause("Enable Accelerated Clear on the Content Status Board",60);return
            self.queue_remaining=tile["remaining"]
            if self.queue_target=="DIMENSION MISSION":
                if self.objective_plan is None or self.objective_period!=reset_period(datetime.now(timezone.utc)):
                    self.queue_pause("Fresh objective inspection required",60);return
                self.queue_remaining=self.objective_plan.dimension_clears
                if self.queue_remaining==0:
                    self.queue_target=None;self.queue_phase="navigate_board";return
            self.queue_send_point(tile["point"],"sweep",("sweep","epic_preparation"));return
        if self.queue_scrolls>=8 or self.queue_last_board==evidence.values.get("signature"):
            self.queue_pause(self.queue_target+" not found on the board",60,phase="navigate_board")
            self.queue_scrolls=0;self.queue_last_board=None;return
        from lib.queue_input import scroll_board
        if self.queue_scrolls==0:
            self.queue_scrolls=1
            scroll_board(self.handle,"up",8)
            self.queue_wake=datetime.now(timezone.utc)+timedelta(seconds=2)
            return
        self.queue_scrolls+=1
        self.queue_last_board=evidence.values.get("signature")
        scroll_board(self.handle)
        self.queue_wake=datetime.now(timezone.utc)+timedelta(seconds=2)

    def queue_dimension_nav(self,evidence):
        screen=evidence.screen
        if screen=="navigation_menu":
            self.queue_send_point((491,642),"dimension_nav",("select_mission","select_mission_coop"));return
        if screen in ("select_mission","select_mission_coop"):
            from lib.mission_reader import canonical
            if canonical(evidence.values.get("first_mission",""))=="DISPATCHMISSION":
                self.queue_remaining=self.objective_plan.dimension_clears
                self.queue_send_point((490,376),"sweep",("dimension_lobby","sweep_preparation","sweep_hidden","sweep"));return
            self.queue_send_point((194,135),"dimension_nav",("select_mission",));return
        if screen=="gbr_main" or evidence.values.get("menu_available"):
            self.queue_send_point((1249,36),"dimension_nav",("navigation_menu",));return
        self.queue_pause("Open game home or mission selector for Dimension Mission",60)

    def queue_dispatch(self,evidence,observed):
        from lib.objectives import dispatch_start_reason
        from lib.mission_reader import canonical
        now=datetime.now(timezone.utc)
        pending=self.queue_engine.pending
        if pending:
            if evidence.screen=="dispatch_result" and evidence.values.get("result_verified"):
                self.record_completed("DISPATCH 7-1",observed,now)
                self.objective_completed('DISPATCH 7-1')
                self.queue_target=None;self.queue_phase="navigate_board"
                click_game_point(self.handle,35,36,key="back",guard=lambda:self.queue_engine.running)
                self.queue_wake=now+timedelta(seconds=3)
                self.log("Dispatch 7-1 energy clear completed");return
            if evidence.screen=="dispatch_battle_auto" and not evidence.values.get("auto_on") and not self.dispatch_auto_clicked:
                self.dispatch_auto_clicked=True
                click_game_point(self.handle,398,672,guard=lambda:self.queue_engine.running)
            if self.dispatch_started and now-self.dispatch_started>timedelta(minutes=10):
                self.stop_queue();self.log("Dispatch outcome not verified; no repeat",True);return
            self.queue_wake=now+timedelta(seconds=5);return
        if self.dimension_priority_blocks('DISPATCH 7-1',now):
            self.queue_target=None;self.queue_phase='navigate_board';self.queue_waiting=None;self.queue_wake=None;return
        if evidence.errors:self.queue_pause("Dispatch: "+"; ".join(evidence.errors),60);return
        screen=evidence.screen
        if screen=="navigation_menu":
            self.queue_send_point((491,642),"dispatch",("select_mission","select_mission_coop"));return
        if screen in ("select_mission","select_mission_coop"):
            if canonical(evidence.values.get("first_mission",""))=="DISPATCHMISSION":
                self.queue_send_point((174,376),"dispatch",("dispatch_map","dispatch_sector_seven"));return
            self.queue_send_point((194,135),"dispatch",("select_mission",));return
        if screen=="dispatch_map":
            point=evidence.values.get("sector_seven_point")
            if point:self.queue_send_point(point,"dispatch",("dispatch_sector_seven",));return
            if self.dispatch_swipes>=4:
                self.queue_pause("Sector 7 not found; inspect Dispatch map",60);return
            self.dispatch_swipes+=1
            click_game_point(self.handle,1030,318,drag_to=(220,318),guard=lambda:self.queue_engine.running)
            self.queue_wake=now+timedelta(seconds=3);return
        if screen=="dispatch_sector_seven":
            self.queue_send_point((1080,334),"dispatch",("dispatch_7_1_setup",));return
        if screen=="dispatch_other_sector":
            self.queue_send_point((1244,108),"dispatch",("dispatch_map",));return
        if screen=="dispatch_wrong_stage":
            click_game_point(self.handle,35,36,key="back",guard=lambda:self.queue_engine.running)
            self.queue_wake=now+timedelta(seconds=3);return
        if screen=="dispatch_7_1_setup":
            if not evidence.values.get("use_energy"):
                self.queue_send_point((440,684),"dispatch",("dispatch_7_1_setup",));return
            reason=dispatch_start_reason(evidence.values,self.raid_gate,observed,now,self.objective_plan)
            if reason:
                self.queue_pause(reason,60,phase="dispatch",stalled=not reason.startswith(('Need ','Wait for enough ')))
                if reason.startswith(('Need ','Wait for enough ')):self.yield_farm_to_story(now)
                return
            if not self.persist_objective_cache(inflight=True):
                self.queue_pause('Could not persist Dispatch in-flight state',60);return
            self.queue_engine.pending=(reset_period(now),"DISPATCH 7-1",1)
            self.dispatch_started=now;self.dispatch_auto_clicked=False
            generation=self.queue_engine.generation
            def authorized():
                current=datetime.now(timezone.utc)
                return self.queue_engine.running and self.queue_engine.generation==generation and self.objective_period==reset_period(current) and dispatch_start_reason(evidence.values,self.raid_gate,observed,current,self.objective_plan) is None
            try:click_game_point(self.handle,1130,672,guard=authorized)
            except InputNotSent:self.queue_engine.pending=None;return
            self.queue_wake=now+timedelta(seconds=5);return
        if screen=="gbr_main" or evidence.values.get("menu_available"):
            self.queue_send_point((1249,36),"dispatch",("navigation_menu",));return
        self.queue_pause("Dispatch navigation screen not recognized",60)

    def queue_dimension_claim(self,evidence,observed):
        now=datetime.now(timezone.utc)
        if not self.queue_engine.pending or self.queue_engine.pending[1]!="DIMENSION MISSION":
            self.queue_pause("No verified Dimension batch awaiting contribution claim",60);return
        if evidence.screen=='dimension_contribution_receipt' and not evidence.errors and evidence.values.get('mode')=='DIMENSION MISSION':
            if self.contribution_acquire_submitted:
                click_game_point(self.handle,*evidence.values['point'],guard=lambda:self.queue_engine.running)
            self.queue_wake=now+timedelta(seconds=3);return
        if evidence.screen=='dimension_contribution' and not evidence.errors and evidence.values.get('mode')=='DIMENSION MISSION':
            if evidence.values['acquire_ready']:
                if self.contribution_acquire_submitted:
                    self.queue_wake=now+timedelta(seconds=5);return
                self.contribution_acquire_submitted=True
                if not self.persist_pending_clear():
                    self.contribution_acquire_submitted=False;self.stop_queue();return
                click_game_point(self.handle,*evidence.values['acquire_point'],guard=lambda:self.queue_engine.running)
                self.queue_wake=now+timedelta(seconds=3);return
            click_game_point(self.handle,*evidence.values['close_point'],guard=lambda:self.queue_engine.running)
            self.queue_wake=now+timedelta(seconds=3);return
        if evidence.screen=="sweep_preparation":
            self.queue_send_point((35,36),"dimension_claim",("dimension_lobby",));return
        if evidence.screen=="dimension_lobby":
            counter=evidence.values.get("contribution")
            before=getattr(self,'contribution_before',None)
            claimed=(counter and self.contribution_submitted and
                ((before and counter[1]==before[1] and counter[0]<before[0]) or (before is None and counter[0]<counter[1])))
            if claimed:
                self.record_completed("DIMENSION MISSION",observed,now)
                self.objective_completed('DIMENSION MISSION')
                self.contribution_followup=False;self.contribution_submitted=False;self.contribution_before=None;self.contribution_acquire_submitted=False
                self.queue_target=None;self.queue_phase="navigate_board"
                self.log("Dimension contribution reward acquired")
                return
            if counter and counter[1]>0 and counter[0]>=counter[1] and not self.contribution_submitted:
                self.contribution_submitted=True;self.contribution_before=counter;self.contribution_acquire_submitted=False
                if not self.persist_pending_clear():
                    self.contribution_submitted=False;self.contribution_before=None
                    self.stop_queue();self.log('Could not save Dimension contribution submission',True);return
                click_game_point(self.handle,1215,665,guard=lambda:self.queue_engine.running)
                self.queue_wake=now+timedelta(seconds=3);return
        if evidence.screen=='content_board':
            self.queue_send_point((1249,36),'dimension_claim',('navigation_menu',));return
        if evidence.screen in ('navigation_menu','select_mission','select_mission_coop','game_home','gbr_main') or evidence.values.get('menu_available'):
            self.queue_dimension_nav(evidence);self.queue_phase='dimension_claim';return
        self.queue_pause("Waiting for verified contribution reward; no extra clears or repeated claim",10,phase="dimension_claim")

    def queue_read_alliance(self,evidence,observed):
        now=datetime.now(timezone.utc)
        pending=self.queue_engine.pending
        if evidence.screen=='alliance_weekly_skip':
            # This is a manual weekly event, not proof of a submitted battle.
            # Never release a pending mission or save stale/reset-crossing evidence.
            if (pending or evidence.errors or evidence.values.get('mode')!='ALLIANCE BATTLE'
                or evidence.values.get('weekly_skip_verified') is not True
                or evidence.values.get('weekly_variant')!='INFINITE CHALLENGE'
                or not timedelta(0)<=now-observed<=timedelta(seconds=30)
                or reset_period(observed)!=reset_period(now)):
                self.queue_wake=now+timedelta(seconds=5);return
            previous=set(self.queue_engine.completed)
            self.queue_engine.verified_complete('ALLIANCE BATTLE',observed,now)
            if not self.persist_completed_missions():
                self.queue_engine.completed=previous
                self.stop_queue();self.log('Could not save weekly Alliance skip; leaving event open',True);return
            self.queue_held.discard('ALLIANCE BATTLE')
            self.log('Alliance Battle: weekly Infinite Challenge left for manual clear; skipped until daily reset')
            self.queue_target=None;self.queue_phase='navigate_board';self.queue_waiting=None
            click_game_point(self.handle,1185,36,guard=lambda:self.queue_engine.running)
            self.queue_wake=now+timedelta(seconds=3);return
        if evidence.screen=='alliance_normal_done' and not pending and not evidence.errors and evidence.values.get('variant')=='NORMAL':
            self.record_completed('ALLIANCE BATTLE',observed,now)
            self.log('Normal Alliance Battle already scored; skipping record challenges')
            self.queue_target=None;self.queue_phase='navigate_board'
            click_game_point(self.handle,1185,36,guard=lambda:self.queue_engine.running)
            self.queue_wake=now+timedelta(seconds=3);return
        if evidence.errors:
            self.queue_pause("Normal Alliance Battle: "+"; ".join(evidence.errors),60);return
        if evidence.screen=="alliance_result" and pending and pending[1]=="ALLIANCE BATTLE":
            self.record_completed("ALLIANCE BATTLE",observed,now)
            self.log("Normal Alliance Battle completed; score "+str(evidence.values["score"]))
            self.queue_target=None;self.queue_phase="navigate_board"
            click_game_point(self.handle,986,663,guard=lambda:self.queue_engine.running)
            self.queue_wake=now+timedelta(seconds=3)
            return
        if pending:
            if not self.alliance_started:self.alliance_started=now
            if now-self.alliance_started>timedelta(minutes=10):
                self.stop_queue();self.log("Alliance result not verified; no retry",True);return
            if evidence.screen=="alliance_battle_auto" and not evidence.values.get("auto_on"):
                if not self.alliance_auto_clicked:
                    self.alliance_auto_clicked=True
                    click_game_point(self.handle,398,672,guard=lambda:self.queue_engine.running)
            self.queue_wake=now+timedelta(seconds=5);return
        if evidence.screen in ("alliance_select_normal","alliance_wrong_variant"):
            self.queue_send_point(evidence.values["point"],"alliance",("alliance_normal_ready","alliance_select_normal","alliance_normal_done","alliance_weekly_skip"));return
        if evidence.screen not in ("alliance_normal_ready","alliance_normal_setup") or evidence.values.get("variant")!="NORMAL":
            self.queue_pause("Only verified Normal Alliance Battle is allowed",60);return
        remaining=evidence.values.get("entries",(None,))[0]
        if remaining==0:
            self.record_completed("ALLIANCE BATTLE",observed,now)
            self.queue_target=None;self.queue_phase="navigate_board";return
        if remaining!=1:
            self.queue_pause("Normal Alliance Battle entry count unreadable",60);return
        if evidence.screen=="alliance_normal_setup":
            self.queue_engine.pending=(reset_period(now),"ALLIANCE BATTLE",1)
            self.alliance_started=now;self.alliance_auto_clicked=False
        try:
            click_game_point(self.handle,*evidence.values["point"],guard=lambda:
                self.queue_engine.running and reset_period(datetime.now(timezone.utc))==reset_period(observed)
                and datetime.now(timezone.utc)-observed<=timedelta(seconds=30))
        except InputNotSent:
            self.queue_engine.pending=None;return
        self.queue_wake=now+timedelta(seconds=5)

    def queue_read_sweep(self,evidence,observed):
        from lib.queue_input import execute_sweep_control
        from lib.epic_sweep import bind_epic_batch
        from lib.screen_reader import ScreenEvidence
        now=datetime.now(timezone.utc)
        values=evidence.values
        if not self.queue_engine.pending and self.dimension_priority_blocks(self.queue_target,now):
            self.queue_target=None;self.queue_phase='navigate_board';self.queue_waiting=None;self.queue_wake=None
            self.epic_preparation=None;return
        if self.queue_engine.pending and not evidence.errors:
            pending_mode=self.queue_engine.pending[1]
            zero_prep=evidence.screen=='epic_preparation' and values.get('preparation_verified') and values.get('mode')==pending_mode and values.get('remaining')==0
            zero_board=evidence.screen=='content_board' and any(row.get('mode')==pending_mode and row.get('remaining')==0 for row in values.get('tiles',[]))
            if zero_prep or zero_board:
                self.record_completed(pending_mode,observed,now)
                self.log(pending_mode+': zero entries verified; completed and continuing')
                self.queue_target=None;self.queue_phase='navigate_board';self.queue_wake=now+timedelta(seconds=2)
                return
        if not self.queue_engine.pending and evidence.screen=="epic_preparation":
            if evidence.errors or not values.get("preparation_verified") or values.get("mode")!=self.queue_target:
                self.queue_pause("Epic preparation costs or mission not verified",60);return
            if values.get("remaining")==0:
                self.record_completed(self.queue_target,observed,now)
                self.queue_target=None;self.queue_phase="navigate_board";return
            if values.get("remaining")!=self.queue_remaining:
                self.queue_pause("Epic preparation entry count differs from the board",60);return
            self.epic_preparation=(evidence,observed,self.queue_engine.generation)
            self.log(self.queue_target+": verified per-clear boost "+str(values["boost_unit"]))
            self.queue_send_point(values["point"],"sweep",("sweep",));return
        if not self.queue_engine.pending and evidence.screen=="sweep" and values.get("layout")=="epic" and values.get("modal_verified"):
            if self.epic_preparation is not None and evidence.errors:
                self.queue_pause("Epic popup unreadable: "+"; ".join(evidence.errors),60);return
            try:
                values,observed=bind_epic_batch(self.epic_preparation,evidence,self.queue_target,
                    self.queue_remaining,self.queue_engine.generation,observed,now)
                evidence=ScreenEvidence("sweep",values,evidence.text)
            except ValueError as error:
                if self.epic_preparation is not None and 'expired' not in str(error):
                    self.recover_stuck_queue('Epic batch could not be authorized: '+str(error))
                    return
                self.epic_preparation=None
                self.log(str(error)+"; opening preparation without spending")
                close=ScreenEvidence("sweep",{"controls":{"close_sweep":(872,555)}})
                execute_sweep_control(self.handle,close,"close_sweep",guard=lambda:self.queue_engine.running)
                self.queue_phase="sweep";self.queue_waiting=(("epic_preparation",),now)
                self.queue_wake=now+timedelta(seconds=2);return
        if evidence.screen in ("dimension_lobby","sweep_preparation","sweep_hidden") and self.queue_target=="DIMENSION MISSION" and not self.queue_engine.pending:
            self.queue_send_point(values["point"],"sweep",("dimension_lobby","sweep_preparation","sweep_hidden","sweep"));return
        if self.queue_engine.pending:
            if evidence.screen=="sweep_result" and values.get("result_verified") and values.get("clears",self.queue_engine.pending[2])==self.queue_engine.pending[2]:
                mode=self.queue_engine.pending[1]
                if values.get("mode") and values["mode"]!=mode:
                    self.queue_pause("Clear result belongs to a different mission",60);return
                if mode=="DIMENSION MISSION" and self.objective_plan and self.objective_plan.claim_contribution:
                    self.contribution_followup=True;self.contribution_submitted=False;self.contribution_before=None;self.contribution_acquire_submitted=False
                    if not self.persist_pending_clear():
                        self.stop_queue();self.log('Could not save Dimension result follow-up',True);return
                    execute_sweep_control(self.handle,evidence,"close_result")
                    self.queue_phase="dimension_claim";self.queue_wake=now+timedelta(seconds=3)
                    return
                self.record_completed(mode,observed,now)
                self.objective_completed(mode)
                self.log(mode+": full batch completed")
                self.queue_target=None
                execute_sweep_control(self.handle,evidence,"close_result")
                self.queue_phase="navigate_board"
                self.queue_wake=now+timedelta(seconds=2)
            else:self.queue_pause("Waiting for verified clear results; no clear will be retried",10,phase="sweep_result")
            return
        if evidence.screen!="sweep" or evidence.errors:
            self.queue_pause("Sweep screen unreadable",60);return
        if values.get("mode")!=self.queue_target:
            self.queue_pause("Verify that Sweep belongs to "+self.queue_target,60);return
        if values.get("selected")!=self.queue_remaining:
            if type(values.get("selected")) is not int:
                self.queue_pause("Sweep batch count unreadable",60,phase="sweep");return
            if self.queue_target=="DIMENSION MISSION":
                if not 1<=self.queue_remaining<=100:
                    self.queue_pause("Dimension quantity must match a daily objective batch",60);return
                execute_sweep_control(self.handle,evidence,"increment" if values["selected"]<self.queue_remaining else "decrement")
                self.queue_wake=now+timedelta(seconds=2);return
            if self.queue_max_attempted:
                self.queue_max_attempted=False
                self.queue_pause(f"Waiting to select all {self.queue_remaining} entries; current selection is {values.get('selected')}",60,phase="sweep")
                return
            self.queue_max_attempted=True
            execute_sweep_control(self.handle,evidence,"select_max")
            self.queue_wake=now+timedelta(seconds=2);return
        self.queue_max_attempted=False
        batch=BatchEvidence(mode=self.queue_target,remaining=self.queue_remaining,
            selected=values.get("selected"),energy_total=values.get("energy_total"),
            boost_total=values.get("boost_total"),ticket_total=values.get("ticket_total"),
            energy_available=values.get("energy_available"),boost_available=values.get("boost_available"),
            tickets_available=values.get("tickets_available"),captured_at=observed,
            crystal_total=values.get("crystal_total"),boosted=values.get("boosted",False),
            sweep_verified=values.get("sweep_verified",False))
        decision=self.queue_engine.authorize(batch,now)
        self.log(self.queue_target+": "+decision.reason)
        if decision.action==QueueAction.CLEAR:
            if self.queue_target=='DIMENSION MISSION' and not self.persist_objective_cache(inflight=True):
                self.queue_engine.pending=None;self.queue_pause('Could not persist Dimension in-flight state',60);return
            if not self.queue_engine.running or not self.raid_gate.cleared(datetime.now(timezone.utc)):
                self.queue_engine.pending=None;return
            generation=self.queue_engine.generation
            period=reset_period(observed)
            def still_authorized():
                current=datetime.now(timezone.utc)
                return (self.queue_engine.running and self.queue_engine.generation==generation
                    and self.raid_gate.cleared(current) and reset_period(current)==period
                    and not self.dimension_priority_blocks(batch.mode,current)
                    and timedelta(0)<=current-observed<=timedelta(seconds=30))
            if not self.persist_pending_clear():
                self.queue_engine.pending=None;self.queue_pause('Could not save submitted batch state',60);return
            try:execute_sweep_control(self.handle,evidence,"clear_batch",guard=still_authorized)
            except InputNotSent as error:
                self.queue_engine.pending=None
                self.persist_pending_clear()
                self.log('Clear was not sent: '+str(error)+'; refreshing preparation and popup')
                self.epic_preparation=None;self.queue_waiting=None
                self.queue_phase="sweep"
                self.queue_wake=now+timedelta(seconds=2)
                return
            self.queue_phase="sweep_result"
            self.queue_wake=now+timedelta(seconds=3)
        elif decision.action==QueueAction.GBR:self.queue_phase="navigate_board"
        elif decision.action==QueueAction.SKIP:
            self.record_completed(self.queue_target,observed,now)
            self.queue_target=None;self.queue_phase="navigate_board"
        else:
            phase="sweep"
            if values.get("controls",{}).get("close_sweep"):
                execute_sweep_control(self.handle,evidence,"close_sweep")
                phase="navigate_board"
            self.queue_pause(decision.reason,60,phase=phase,stalled=decision.action not in (QueueAction.BOOST,QueueAction.ENERGY,QueueAction.TICKETS))
            if decision.action in (QueueAction.BOOST,QueueAction.ENERGY,QueueAction.TICKETS):self.yield_farm_to_story(now)

    def yield_farm_to_story(self,now):
        if 'STORY ULTIMATE' not in self.eligible_modes(now) or 'STORY ULTIMATE' in self.queue_engine.completed:return
        self.queue_deferred[self.queue_target]=now+timedelta(seconds=60)
        self.queue_target='STORY ULTIMATE';self.queue_phase='story';self.story_ultimate_verified=None
        self.story_navigation_started=now
        self.queue_waiting=None;self.queue_wake=now+timedelta(seconds=2)

    def render_queue_status(self):
        self.update_gbr()
        self.log(f"Checking Queue #{self.queue_index+1} — Normal Alliance Battle auto; combat skills shelved")
        self.log('DAILY TRIVIA: '+('cleared for this reset - remembered across restarts' if self.trivia_period==reset_period(datetime.now(timezone.utc)) else
            'in progress' if self.trivia_active else 'automatic daily check pending; retries incomplete checks'))
        completed=set(self.queue_engine.completed) if self.queue_engine.period==reset_period(datetime.now(timezone.utc)) else set()
        if self.last_evidence:
            evidence,observed,live=self.last_evidence
            fresh=live and timedelta(0)<=datetime.now(timezone.utc)-observed<=timedelta(seconds=30)
            if fresh and not evidence.errors:
                completed.update(evidence.values.get("completed",[]))
                mode={"timeline":"TIMELINE BATTLE","otherworld":"OTHERWORLD BATTLE","world_event":"WORLD EVENT"}.get(evidence.screen)
                if mode and evaluate(evidence,observed,datetime.now(timezone.utc)).action.value=="skip":completed.add(mode)
        for item in self.queues[self.queue_index]:
            mode=item["mode"]
            if not item["enabled"]:status="disabled"
            elif mode=="WORLD EVENT":status="0/2 verified - done until reset" if self.world_event_state.done else "Auto participation; checks slots until 0/2 daily entries"
            elif mode=='ZOMBIE SURVIVAL':status='weekly rewards verified - skip' if mode in completed else 'Level 1; top five roster positions; MAX ticket repeat; Acquire All after five clears'
            elif mode=="ALLIANCE BATTLE":status="Normal only — built-in auto, once per reset; Extreme/Legend excluded"
            elif mode=='TIMELINE BATTLE':status='Auto, Team 1; runs without GBR clearance'
            elif mode=='OTHERWORLD BATTLE':status='Auto reward battles; runs without GBR clearance'
            elif mode=='TEAM BATTLE ARENA':status='Automatic ticket repeat; no energy, boost or GBR gate'
            elif mode in UNBOOSTED_SWEEPS:status='All remaining entries with Sweep tickets; no boost or GBR gate'
            elif mode=='STORY ULTIMATE':status='Ultimate Auto Progress from 1-1; energy only, no GBR or boost requirement'
            elif mode in MANUAL:status="manual — reserved for you"
            elif mode in completed:status="done — skip"
            elif mode in ENERGY_FARMS:
                status=resource_status(self.latest_counters,self.resource_balances,datetime.now(timezone.utc),self.raid_gate)
                if not self.acquire_heroic_quest_rewards_checkbox.isChecked():status="disabled: sweep/energy preference off"
            else:status="fresh mode check required; execution shelved"
            self.log(f"{mode}: {status}")

    def show_rules(self):
        QtWidgets.QMessageBox.information(self,"Farming rules",
            "• No crystals, purchases, refills or upgrades.\n"
            "• Boosted farming needs GBR 0/165 AND 0/300 once per reset.\n"
            "• Incomplete GBR pauses boosted farming only; rechecks every minute between tasks.\n"
            "• Timeline, Otherworld, Normal Alliance and Story continue without GBR clearance.\n"
            "• Daily Trivia is automatic once per reset; five verified answers are remembered across restarts.\n"
            "• Zombie Survival uses Level 1, the top five list positions, and MAX ticket repeats; collects weekly Challenges.\n"
            "• Story uses Ultimate Auto Progress from Stage 1-1, energy only.\n"
            "• Clearance lasts until 15:00 UTC (17:00 Albania summer / 16:00 winter).\n"
            "• Check enough boost for the whole remaining batch; energy and ticket amounts are not checked.\n"
            "• Never run a partial batch or an unboosted clear.\n"
            "• Sweep tickets and existing energy are allowed after that check.\n"
            "• Timeline uses Team 1.\n"
            "• World Event checks later slots until 0/2; a score only finishes that slot.\n"
              "• Normal Alliance Battle uses built-in auto once; Extreme/Legend excluded.\n"
              "• Inspect Daily Challenges and active Special Benefits events; skip Otherworld/Future Pass.\n"
              "• Refresh requirements at queue start. Dimension clears take priority over other boosted farming.\n"
              "• Dimension: use the largest remaining challenge count; contribution reward needs at least 5 then claim.\n"
              "• Dispatch: only an event energy-clear requirement, only 7-1, with enough boost.\n"
              "• World Boss stays manual.\n\n"
            "Start Queue keeps energy farming active until Stop Queue. Combat skill controls remain shelved.")

    def closeEvent(self,event):
        if self.emulator_recovering():
            self.stop_queue();self.close_after_capture=True
            self.timer.stop();self.queue_timer.stop();event.ignore();return
        if getattr(self,'restart_task',None) and self.restart_task.isRunning():
            self.queue_engine.stop();self.log('Waiting for game recovery to finish before closing');event.ignore();return
        if self.frame_task is not None:
            self.close_after_capture=True;self.timer.stop();self.queue_timer.stop();self.queue_engine.stop()
            self.frame_waiting_scan=False;event.ignore();return
        if self.busy:
            self.log("Wait for the current screen check to finish before closing.")
            event.ignore();return
        self.resource_active=False
        self.trivia_active=False
        self.objective_active=False
        self.queue_engine.stop()
        self._save()
        event.accept()
