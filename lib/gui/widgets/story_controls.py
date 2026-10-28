"""Start the game's Ultimate Auto Progress once per reset; never repeat a submission."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from lib.app_paths import data_path
import json
from lib.daily_queue import reset_period
from lib.resource_check import click_game_point,InputNotSent

STORY_STATE=data_path('settings/gui/story-run.json')

class StoryControls:
 def init_story(self):
  self.story_ultimate_verified=None;self.story_started=None;self.story_result_since=None
  self.story_navigation_started=None;self.story_team_verified=False
  self.story_unknown_since=None
 def start_story_now(self):
  if self.busy or self.resource_active or self.objective_active or self.trivia_active:
   self.log('Wait for the current screen check to finish before starting Story');return
  if self.queue_engine.running or self.queue_engine.pending:
   self.log('Stop the queue and verify any pending run before starting Story');return
  if not self.handle:self.connect_emulator();self.log('Connect BlueStacks, then press Start Story Ultimate');return
  now=datetime.now(timezone.utc);self.queue_engine.rollover(now)
  if 'STORY ULTIMATE' in self.queue_engine.completed:self.log('Story already completed for this reset');return
  self.queue_held.discard('STORY ULTIMATE');self.persist_completed_missions()
  self.queue_engine.start(now);self.queue_target='STORY ULTIMATE';self.queue_phase='navigate_board'
  self.queue_wake=None;self.queue_waiting=None;self.queue_observation=None
  self.story_ultimate_verified=None;self.story_navigation_started=now;self.story_team_verified=False
  self.run_queue_button.setText('Stop Queue');self.set_queue_editable(False)
  self.log('Starting Ultimate Story Auto Progress: Team 2, Stage 1-1, ticket button')
  self.queue_tick()
 def load_story_run(self):
  try:
   data=json.loads(STORY_STATE.read_text(encoding='utf-8'));stamp=datetime.fromisoformat(data['started_at'])
   if stamp.tzinfo:self.story_started=stamp
   if data.get('pending') and stamp.tzinfo and 'STORY ULTIMATE' not in self.queue_engine.completed and 'STORY ULTIMATE' not in self.queue_held and timedelta(0)<=datetime.now(timezone.utc)-stamp<timedelta(hours=2):
    self.story_started=stamp;self.queue_engine.pending=(reset_period(stamp),'STORY ULTIMATE',1)
    self.log('Restored active Story Auto Progress; will verify it without starting again')
   elif data.get('pending') and stamp.tzinfo and 'STORY ULTIMATE' not in self.queue_engine.completed and reset_period(stamp)==reset_period(datetime.now(timezone.utc)):
    self.queue_held.add('STORY ULTIMATE');self.log('Story was already launched this reset; no automatic relaunch')
  except FileNotFoundError:pass
  except (OSError,ValueError,KeyError,TypeError) as error:
   self.queue_held.add('STORY ULTIMATE');self.log('Story run state unreadable; held to prevent a duplicate launch: '+str(error),True)
 def persist_story_run(self,pending):
  data={'pending':pending,'started_at':self.story_started.isoformat()}
  STORY_STATE.parent.mkdir(exist_ok=True,parents=True);tmp=STORY_STATE.with_suffix('.tmp')
  tmp.write_text(json.dumps(data,indent=2),encoding='utf-8');tmp.replace(STORY_STATE)
 def queue_story(self,evidence,observed):
  now=datetime.now(timezone.utc);v=evidence.values;screen=evidence.screen
  def guard():return self.queue_engine.running and timedelta(0)<=datetime.now(timezone.utc)-observed<=timedelta(seconds=30)
  if not guard():return
  def click(point):click_game_point(self.handle,*point,guard=guard);self.queue_wake=now+timedelta(seconds=3)
  if screen=='content_board':
   self.remember_board_completions(evidence,observed)
   if 'STORY ULTIMATE' in self.queue_engine.completed:
    self.queue_target=None;self.queue_phase='navigate_board'
    self.log('All four Ultimate Story daily rewards verified complete on the board; no Start')
   elif not self.queue_engine.pending:
    self.queue_phase='board';self.queue_read_board(evidence,observed)
   return
  if screen=='story_ended':
   if self.story_started and reset_period(self.story_started)==reset_period(now):
    self.record_completed('STORY ULTIMATE',observed,now);self.persist_story_run(False)
   self.queue_target='STORY ULTIMATE';self.queue_phase='story'
   self.queue_recovering=False;self.queue_waiting=None
   click(v['point']);self.log('Story Auto Progress Ended verified; closing summary and continuing queue');return
  if screen=='story_result' and 'STORY ULTIMATE' in self.queue_engine.completed:
   click(v['point']);self.queue_target=None;self.queue_phase='navigate_board'
   self.log('Story completed summary closed; returning Home for the next queue task');return
  if self.queue_engine.pending:
   if screen=='unknown':
    if self.story_unknown_since is None:self.story_unknown_since=now
    if now-self.story_unknown_since>timedelta(seconds=90):
     self.log('Story Auto Progress is still protected: unfamiliar frame; waiting without inputs or relaunch')
     self.story_unknown_since=now
   else:self.story_unknown_since=None
   # Results/countdowns can remain visible between automatic stages. Neither
   # their duration nor a transient Auto checkbox authorizes any input.
   self.story_result_since=None
   # Auto Progress moves through every stage itself. Do not click ordinary
   # result/next buttons during the inter-stage countdown.
   if self.story_started and now-self.story_started>timedelta(minutes=95):
    self.recover_stuck_queue('Story Auto Progress exceeded 95 minutes; no relaunch');return
   self.queue_wake=now+timedelta(seconds=15);return
  if self.story_navigation_started is None:self.story_navigation_started=now
  if now-self.story_navigation_started>timedelta(minutes=3):
   self.recover_stuck_queue('Story navigation did not settle within three minutes');return
  if evidence.errors:self.queue_pause('Story: '+'; '.join(evidence.errors),10);return
  if screen=='story_select':click(v['point']);return
  if screen=='story_ultimate':
   if v.get('daily_rewards')==(0,1):
    self.story_ultimate_verified=None;self.queue_phase='navigate_board';self.queue_waiting=None
    self.log('This Ultimate Story section has no daily reward left; checking the board instead of starting')
    click((1249,36));return
   if not v.get('team_2'):
    click((925,264));return
   self.story_ultimate_verified=(now,self.queue_engine.generation);click(v['point']);return
  if screen=='story_progress':
   proof=self.story_ultimate_verified
   if not proof or proof[1]!=self.queue_engine.generation or now-proof[0]>timedelta(minutes=2):
    click(v.get('close_point',(539,568)));return
   if not v['from_stage_one']:click(v.get('stage_point',(551,447)));return
   self.story_started=now
   try:self.persist_story_run(True)
   except OSError as error:self.queue_pause('Could not save Story launch: '+str(error),60);return
   self.queue_engine.pending=(reset_period(now),'STORY ULTIMATE',1)
   try:click(v.get('start_point',(741,568)))
   except InputNotSent:self.queue_engine.pending=None;self.persist_story_run(False);return
   self.log('Started Ultimate Story Auto Progress from Stage 1-1. Energy only; no boost or GBR gate.');return
  if screen=='navigation_menu':click((491,642));return
  if screen in ('select_mission','select_mission_coop'):
   from lib.mission_reader import canonical
   if canonical(v.get('first_mission',''))=='DISPATCHMISSION':click((811,376))
   else:click((194,135))
   return
  if screen=='gbr_main' or v.get('menu_available'):click((1249,36));return
  self.queue_pause('Waiting for Story Ultimate navigation',10)
