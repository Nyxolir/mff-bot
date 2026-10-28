"""Desktop appearance and task state presentation, without game input."""
from datetime import datetime,timezone
from PyQt5 import QtCore,QtGui,QtWidgets
from lib.daily_queue import reset_period

DARK='''
QWidget { background:#111827; color:#e5e7eb; font-family:"Segoe UI"; font-size:12px; }
QMainWindow,QDialog { background:#111827; }
QGroupBox { border:1px solid #334155; border-radius:10px; margin-top:14px; padding-top:10px; font-weight:600; }
QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 6px; color:#93c5fd; }
QPushButton { background:#243247; border:1px solid #42516a; border-radius:7px; padding:8px; }
QPushButton:hover { background:#334968; border-color:#60a5fa; }
QPushButton:pressed,QPushButton:checked { background:#1d4ed8; color:white; }
QPushButton:disabled { color:#7c8ba1; background:#1b2535; border-color:#29374c; }
QListWidget,QPlainTextEdit,QTextEdit,QSpinBox,QComboBox { background:#0b1220; border:1px solid #334155; border-radius:6px; selection-background-color:#254b80; }
QListWidget::item { padding:5px 3px; border-bottom:1px solid #1c293b; }
QTabWidget::pane { border:1px solid #334155; }
QTabBar::tab { background:#1e293b; padding:7px 13px; }
QTabBar::tab:selected { background:#254b80; color:white; }
QMenuBar,QMenu,QStatusBar { background:#172235; }
QMenu::item:selected { background:#254b80; }
QToolTip { background:#243247; color:white; border:1px solid #64748b; padding:5px; }
QCheckBox { spacing:6px; }
QCheckBox::indicator { width:14px; height:14px; background:#0b1220; border:1px solid #64748b; border-radius:3px; }
QCheckBox::indicator:checked { background:#3b82f6; border:2px solid #93c5fd; }
QScrollBar:vertical { background:#111827; width:10px; }
QScrollBar::handle:vertical { background:#475569; min-height:25px; border-radius:5px; }
'''

class Appearance:
    def init_appearance(self):
        self.setStyleSheet(DARK)
        self.queue_list_widget.setViewMode(QtWidgets.QListView.ListMode)
        self.queue_list_widget.setFlow(QtWidgets.QListView.TopToBottom)
        self.queue_list_widget.setWrapping(False)
        self.queue_list_widget.setWordWrap(True)
        self.queue_list_widget.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.queue_list_widget.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.queue_list_widget.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.run_queue_button.setStyleSheet('QPushButton {background:#2563eb;color:white;font-weight:600;} QPushButton:disabled {background:#1e3a5f;}')
        self.task_status_timer=QtCore.QTimer(self)
        self.task_status_timer.timeout.connect(self.refresh_task_statuses)
        self.task_status_timer.start(1000)
        self.refresh_task_statuses()

    def task_done_today(self,mode,now):
        period=reset_period(now)
        return ((self.queue_engine.period==period and mode in self.queue_engine.completed)
            or (mode=='WORLD EVENT' and self.world_event_state.period==period and self.world_event_state.done))

    def task_status(self,mode,now):
        if self.task_done_today(mode,now):
            if mode=='ZOMBIE SURVIVAL':return 'Done · weekly rewards verified','#6ee7b7'
            return ('Done today · 0/2 remaining' if mode=='WORLD EVENT' else 'Done today'),'#6ee7b7'
        if mode=='WORLD EVENT' and self.world_event_active:
            count=len(self.world_event_state.zero_observations)
            return (f'Verifying 0/2 · {count}/3 page visits' if count else 'Running World Event' if self.world_event_state.started else 'Checking World Event page'),'#93c5fd'
        if getattr(self,'review_mode',None)==mode:return 'Reviewing unsure outcome','#93c5fd'
        if mode in self.queue_held:return 'Unsure · review after daily tasks','#fbbf24'
        pending=self.queue_engine.pending
        if mode==self.queue_target or (pending and pending[1]==mode):
            if mode=='ZOMBIE SURVIVAL' and pending and self.zombie_progress:
                return f'Auto repeat {self.zombie_progress[0]}/{self.zombie_progress[1]} · Level 1','#93c5fd'
            if self.queue_recovering:return 'Recovering','#fbbf24'
            if mode=='STORY ULTIMATE' and self.story_started:return 'Auto Progress · restart protected','#93c5fd'
            if self.queue_wake and self.queue_wake>now:
                return 'Waiting · '+getattr(self,'task_wait_reason','next screen'), '#fbbf24'
            return 'Running · '+self.queue_phase.replace('_',' '),'#93c5fd'
        retry=self.queue_deferred.get(mode)
        if retry and retry>now:return 'Retry in '+str(max(1,int((retry-now).total_seconds()/60)))+' min','#fbbf24'
        if mode=='WORLD BOSS':return 'Manual','#94a3b8'
        plan=self.objective_plan
        if self.objective_plan_current(now) and mode in ('DIMENSION MISSION','DISPATCH 7-1'):
            clears=plan.dimension_clears if mode=='DIMENSION MISSION' else plan.dispatch_clears
            if clears==0:return 'Skipped · no challenge requires it','#94a3b8'
        if not self.queue_engine.running:return 'Queued','#94a3b8'
        if self.requires_gbr(mode) and not self.raid_gate.cleared(now):return 'Waiting for GBR','#fbbf24'
        if self.requires_gbr(mode) and not self.objective_plan_current(now):return 'Waiting for requirement check','#fbbf24'
        if mode=='DIMENSION MISSION' and self.dimension_priority_required(now):
            return f'Priority · {plan.dimension_clears} clears'+(' + contribution claim' if plan.claim_contribution else ''),'#93c5fd'
        if self.dimension_priority_blocks(mode,now):return 'Waiting for required Dimension clears','#fbbf24'
        return 'Queued','#94a3b8'

    def refresh_task_statuses(self):
        now=datetime.now(timezone.utc)
        widget=self.queue_list_widget
        scroll=widget.verticalScrollBar();position=scroll.value()
        current=widget.currentItem();selected=widget.selectedItems()
        previous=widget.blockSignals(True);loading=self.loading;self.loading=True
        try:
            items=[widget.item(i) for i in range(widget.count())]
            for item in items:
                mode=item.data(QtCore.Qt.UserRole)
                state,color=self.task_status(mode,now)
                if item.checkState()!=QtCore.Qt.Checked:state,color='Disabled','#64748b'
                title=mode+(' · Normal only' if mode=='ALLIANCE BATTLE' else ' · Level 1 / MAX tickets' if mode=='ZOMBIE SURVIVAL' else '')
                text=title+'\n'+state
                if item.text()!=text:item.setText(text)
                item.setForeground(QtGui.QColor(color));item.setToolTip(text)
            # Stable display grouping never rewrites the saved mission order.
            # Retain original entry indices so editing sorted rows stays precise.
            ordered=sorted(items,key=lambda item:(self.task_done_today(item.data(QtCore.Qt.UserRole),now),item.data(QtCore.Qt.UserRole+1)))
            if not scroll.isSliderDown():
                for row,item in enumerate(ordered):
                    old=widget.row(item)
                    if old!=row:widget.insertItem(row,widget.takeItem(old))
            if current is not None:widget.setCurrentItem(current,QtCore.QItemSelectionModel.NoUpdate)
            widget.clearSelection()
            for item in selected:item.setSelected(True)
            widget.doItemsLayout()
            scroll.setValue(position)
        finally:
            self.loading=loading;widget.blockSignals(previous)
