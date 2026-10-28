"""Free Timeline and Otherworld handling independent of GBR/boost clearance."""
from datetime import datetime,timedelta,timezone
from lib.resource_check import click_game_point
from lib.daily_queue import reset_period

class ArenaControls:
 def init_arenas(self):self.arena_started=None;self.arena_auto_clicked=False;self.arena_claim_at=None;self.arena_exhausted=False;self.arena_unknown_since=None;self.arena_repeat_finished=False;self.arena_resumed=False
 def reconcile_restored_arena(self,evidence,observed,now):
  pending=self.queue_engine.pending
  if (not pending or not getattr(self,'arena_resumed',False) or
      not self.arena_started):return False
  if evidence.errors:self.arena_idle_seen=None;return False
  if not self.arena_repeat_finished and not getattr(self,'arena_home_verified',False):
   entries=evidence.values.get('entries')
   if (evidence.screen=='otherworld_lobby' and pending[1]=='OTHERWORLD BATTLE' and
       evidence.values.get('mode')==pending[1] and evidence.values.get('lobby_idle_verified') is True and
       entries and entries[1]==5 and type(entries[0]) is int and 0<=entries[0]<=5):
    # An interrupted repeat can return to its undimmed, interactive lobby.
    # Require a continuous minute of distinct captures with unchanged count;
    # a single lobby frame can occur between rounds and must do nothing.
    proof=(pending[1],tuple(entries));seen=getattr(self,'arena_idle_seen',None)
    if not seen or seen[0]!=proof or not timedelta(0)<observed-seen[2]<=timedelta(seconds=30):
     self.arena_idle_seen=(proof,observed,observed,1);return False
    self.arena_idle_seen=(proof,seen[1],observed,seen[3]+1)
    if observed-seen[1]<timedelta(seconds=60) or seen[3]+1<3:return False
    self.arena_home_verified=True
    self.log('Restored Otherworld repeat remained on a verified idle lobby for one minute; reconciling fresh remaining entries')
   else:
    self.arena_idle_seen=None
    # A whole undimmed home menu cannot be a battle countdown. Require two
    # distinct fresh captures before inspecting the board after a restart.
    if evidence.screen!='game_home' or evidence.values.get('home_controls_verified') is not True:
     self.arena_home_seen=None;return False
    seen=getattr(self,'arena_home_seen',None)
    if seen is None:self.arena_home_seen=observed;return False
    if observed-seen<timedelta(seconds=3):return False
    self.arena_home_verified=True
    self.log('Restored Arena is on verified game home; checking daily count without starting a battle')
  if not getattr(self,'arena_home_verified',False) and now-self.arena_started<=timedelta(minutes=35):return False
  mode=pending[1];remaining=None
  if evidence.screen in ('game_home','navigation_menu'):
   point=(1249,36) if evidence.screen=='game_home' else (630,642)
   guard=lambda:self.queue_engine.running and self.queue_engine.pending==pending and timedelta(0)<=datetime.now(timezone.utc)-observed<=timedelta(seconds=30)
   click_game_point(self.handle,*point,guard=guard)
   self.queue_wake=now+timedelta(seconds=3)
   self.log('Restored Arena attempt: opening daily board to verify remaining entries; no battle Start')
   return True
  if evidence.screen=='content_board':
   row=next((r for r in evidence.values.get('tiles',[]) if r.get('mode')==mode),None)
   if row and row.get('total')==5:remaining=row.get('remaining')
  elif evidence.screen in ('team_arena_lobby','otherworld_lobby') and evidence.values.get('mode')==mode:
   entries=evidence.values.get('entries')
   if entries and entries[1]==5:remaining=entries[0]
  if type(remaining) is not int or not 0<=remaining<=5:return False
  if remaining==0:
   self.record_completed(mode,observed,now);self.queue_target=None;self.queue_phase='navigate_board'
  else:
   # A fresh named board/lobby after verified restoration proves this repeat
   # no longer owns the screen. Reopen prep and reread remaining entries and
   # ticket costs; never reuse the original batch quantity as permission.
   self.queue_engine.pending=None
   if not self.persist_pending_clear():
    self.queue_engine.pending=pending;self.stop_queue();self.log('Could not save Arena reconciliation; no new Start sent',True);return True
   self.queue_target=mode;self.queue_phase='navigate_board';self.queue_waiting=None
  self.arena_resumed=False;self.arena_started=None;self.arena_repeat_finished=False
  self.arena_idle_seen=None
  self.arena_home_verified=False;self.arena_home_seen=None
  self.queue_observation=None;self.queue_wake=now+timedelta(seconds=1)
  self.log(mode+': restored submission reconciled against fresh daily count '+str(remaining)+'/5; '+('done' if remaining==0 else 'preparation and costs will be checked again'))
  return True
 def queue_arena(self,evidence,observed):
  now=datetime.now(timezone.utc);v=evidence.values;mode=self.queue_target
  def guard():return self.queue_engine.running and timedelta(0)<=datetime.now(timezone.utc)-observed<=timedelta(seconds=30)
  def click(point):click_game_point(self.handle,*point,guard=guard);self.queue_wake=now+timedelta(seconds=3)
  if not guard():return
  if self.reconcile_restored_arena(evidence,observed,now):return
  ticket_running=bool(self.queue_engine.pending and mode in ('TIMELINE BATTLE','OTHERWORLD BATTLE','TEAM BATTLE ARENA') and not self.arena_repeat_finished)
  if ticket_running and evidence.errors:
   self.queue_wake=now+timedelta(seconds=10);return
  if evidence.screen=='arena_transition':
   if self.arena_unknown_since is None:self.arena_unknown_since=now
   if now-self.arena_unknown_since>timedelta(seconds=90) and not ticket_running:
    self.recover_stuck_queue('Arena repeat controls did not finish appearing');return
   self.queue_wake=now+timedelta(seconds=2);return
  if evidence.screen!='unknown':self.arena_unknown_since=None
  if evidence.errors:self.queue_pause('Free arena: '+'; '.join(evidence.errors),10);return
  if evidence.screen=='arena_result' and v.get('mode')!=mode:
   # Never act on another mode's result, or an unidentified home icon.
   self.queue_wake=now+timedelta(seconds=5)
   self.log('Arena result mode does not match active task; no result input',True);return
  if evidence.screen=='arena_information' and v.get('mode')==mode:
   # This explicit information-only Close is safe even during a submitted
   # repeat. It does not authorize Back, result exit, completion, or Start.
   click(v['point'])
   if self.queue_engine.pending:self.arena_resumed=True;self.arena_idle_seen=None
   self.log('Closed verified Otherworld weekly character notice; submitted repeat unchanged');return
  if evidence.screen=='timeline_glory_cap':
   if mode=='TIMELINE BATTLE' and self.queue_engine.pending and not getattr(self,'timeline_cap_acknowledged',False):
    self.timeline_cap_acknowledged=True;click(v['point'])
    self.log('Timeline: acknowledged full Glory Token storage; continuing the already submitted free repeat')
   else:self.queue_wake=now+timedelta(seconds=10)
   return
  if mode=='TEAM BATTLE ARENA' and mode in self.queue_engine.completed and not self.queue_engine.pending:
   if evidence.screen=='arena_result':
    click(v['point']);self.queue_target=None;self.queue_phase='navigate_board';return
   if (evidence.screen in ('navigation_menu','content_board','status_board') or
       (evidence.screen=='game_home' and v.get('home_controls_verified') is True)):
    self.queue_target=None;self.queue_phase='navigate_board';self.queue_waiting=None;self.queue_wake=None
    self.log('Team Arena completion saved; result already left, continuing with the next task');return
  if evidence.screen=='arena_power':
   if ticket_running:self.queue_wake=now+timedelta(seconds=10);return
   if v['finished']:click_game_point(self.handle,640,518,drag_to=(640,228),guard=guard)
   self.queue_wake=now+timedelta(seconds=5);return
  if evidence.screen=='arena_repeat_ended' and v.get('mode')==mode and self.queue_engine.pending:
   self.arena_repeat_finished=True
   if not self.persist_pending_clear():
    self.stop_queue();self.log('Could not save Arena repeat end; leaving the summary open',True);return
   click(v['point']);return
  if ticket_running:
   if evidence.screen=='arena_exhausted' and v.get('point') and v.get('mode')==mode:
    # A named terminal notice is distinct from a lobby showing zero entries
    # while the last submitted fight is still loading.
    self.arena_exhausted=True;self.arena_repeat_finished=True
    if not self.persist_pending_clear():self.stop_queue();return
    click(v['point']);return
   if self.arena_started and now-self.arena_started>timedelta(minutes=35):
    self.stop_queue();self.log('Automatic Arena repeat outcome timed out; game left untouched',True);return
   self.queue_wake=now+timedelta(seconds=10);return
  if evidence.screen=='arena_exhausted' or (v.get('entries') and v['entries'][0]==0):
   if v.get('mode',mode)!=mode:return
   if evidence.screen=='arena_exhausted' and v.get('point'):
    self.arena_exhausted=True;click(v['point']);return
   self.record_completed(mode,observed,now);self.queue_target=None;self.queue_phase='navigate_board'
   if v.get('point'):click(v['point'])
   else:click_game_point(self.handle,35,36,key='back',guard=guard)
   self.queue_wake=now+timedelta(seconds=3);return
  if self.queue_engine.pending and self.arena_repeat_finished and mode in ('TIMELINE BATTLE','OTHERWORLD BATTLE','TEAM BATTLE ARENA'):
   if evidence.screen=='game_home':
    click((1249,36));self.log('Arena repeat ended: reopening its lobby to verify remaining rewards');return
   if evidence.screen=='navigation_menu':click((491,642));return
   if evidence.screen=='status_board':self.queue_wake=now+timedelta(seconds=2);return
   if evidence.screen=='content_board':
    row=next((r for r in v.get('tiles',[]) if r.get('mode')==mode),None)
    if row and row.get('total')==5 and type(row.get('remaining')) is int:
     if row['remaining']==0:
      self.record_completed(mode,observed,now);self.queue_target=None;self.queue_phase='navigate_board'
      self.arena_repeat_finished=False;self.arena_resumed=False;self.queue_wake=None
      self.log(mode+': zero remaining rewards verified after repeat; continuing queue');return
     self.recover_stuck_queue('Repeat ended with daily rewards still remaining; no repeat replay');return
  if evidence.screen=='arena_acquire' and v.get('mode')==mode and not self.queue_engine.pending:
   click(v['point']);return
  if evidence.screen=='timeline_lobby':click(v['point']);return
  if mode=='TEAM BATTLE ARENA':
   if evidence.screen=='team_arena_lobby':
    if self.queue_engine.pending:
     if v['entries'][0]<self.queue_engine.pending[2]:self.recover_stuck_queue('Team Arena repeat stopped with entries remaining');return
     self.queue_wake=now+timedelta(seconds=10);return
    self.arena_remaining=v['entries'][0];self.arena_entry_verified=now;click((770,678));return
   if evidence.screen=='team_arena_repeat':
    if self.queue_engine.pending:self.queue_wake=now+timedelta(seconds=10);return
    remaining=getattr(self,'arena_remaining',None)
    if not remaining or now-getattr(self,'arena_entry_verified',now)>timedelta(minutes=3):click((532,561));return
    if v['selected']!=remaining:
     if v['selected']>remaining:self.queue_pause('Arena MAX exceeds remaining daily entries; no Start',10);return
     click((791,469));return
    self.queue_engine.pending=(reset_period(now),mode,remaining);self.arena_started=now
    if not self.persist_pending_clear():
     self.queue_engine.pending=None;self.stop_queue();self.log('Arena submission not saved; no Start sent',True);return
    click((750,561));self.log('Team Battle Arena: automatic ticket repeat for all daily entries; no energy or boost');return
  if evidence.screen=='timeline_setup':
   if self.queue_engine.pending:
    self.queue_wake=now+timedelta(seconds=10);return
   if not v['team_1']:click((42,117));return
   if not v['repeat']:click((710,612));return
   self.queue_engine.pending=(reset_period(now),mode,v['entries'][0]);self.arena_started=now;self.arena_auto_clicked=False;self.timeline_cap_acknowledged=False
   if not self.persist_pending_clear():
    self.queue_engine.pending=None;self.stop_queue();self.log('Timeline submission not saved; no Start sent',True);return
   click((1080,669));return
  if mode=='OTHERWORLD BATTLE':
   if evidence.screen=='otherworld_lobby':
    if self.queue_engine.pending:
     if v['entries'][0]<self.queue_engine.pending[2]:self.recover_stuck_queue('Otherworld ticket repeat stopped before zero rewards; no individual-fight fallback');return
     else:self.queue_pause('Otherworld result not yet verified',10);return
    if not v.get('ticket_icon_verified'):self.queue_pause('Otherworld clear-ticket icon not verified',10);return
    self.arena_remaining=v['entries'][0];self.arena_entry_verified=now;click((750,678));return
   if evidence.screen=='otherworld_repeat':
    if self.queue_engine.pending:self.queue_pause('Otherworld ticket repeat already submitted; no second Start',10,stalled=False);return
    remaining=getattr(self,'arena_remaining',None)
    if not remaining or not getattr(self,'arena_entry_verified',None) or now-self.arena_entry_verified>timedelta(minutes=3):click((532,561));return
    if not v['until_rewards']:click((491,479));return
    if v['selected']!=remaining:
     if v['selected']>remaining:self.queue_pause('Otherworld quantity exceeds remaining rewards; no Start',10);return
     click((791,422));return
    self.queue_engine.pending=(reset_period(now),mode,remaining);self.arena_started=now
    if not self.persist_pending_clear():
     self.queue_engine.pending=None;self.stop_queue();self.log('Otherworld submission not saved; no Start sent',True);return
    click((750,561));self.log('Otherworld: clear-ticket Auto Repeat until reward count runs out');return
   if evidence.screen in ('otherworld_opponent','otherworld_setup') and not self.queue_engine.pending:
    click_game_point(self.handle,35,36,key='back',guard=guard);self.queue_wake=now+timedelta(seconds=3);return
  if evidence.screen=='arena_battle':
   if self.queue_engine.pending and not v['auto_on'] and not self.arena_auto_clicked:
    self.arena_auto_clicked=True;click((407,675));return
  if evidence.screen=='arena_result':
   if self.arena_exhausted and v.get('mode')==mode:
    self.record_completed(mode,observed,now);self.queue_target=None;self.queue_phase='navigate_board';self.arena_exhausted=False
   click(v['point']);return
  if self.queue_engine.pending:
   if evidence.screen=='unknown':
    if self.arena_unknown_since is None:self.arena_unknown_since=now
    if now-self.arena_unknown_since>timedelta(seconds=90):self.recover_stuck_queue('Arena screen remained unrecognized for 90 seconds');return
   if mode in ('OTHERWORLD BATTLE','TEAM BATTLE ARENA'):
    if evidence.screen=='content_board':
     row=next((r for r in v.get('tiles',[]) if r['mode']==mode),None)
     if row and type(row.get('remaining')) is int and row['remaining']<self.queue_engine.pending[2]:
      self.queue_engine.pending=None;self.queue_phase='board';return
    if evidence.screen=='navigation_menu':click((491,642));return
    if evidence.screen in ('select_mission','select_mission_coop'):
     if v.get('first_mission')=='TIMELINE BATTLE':
      self.queue_pause('Arena tab is selected but mission cards are unreadable',8);return
     click((785,135));return
    if evidence.screen=='arena_selector' and mode in v.get('cards',{}):click(v['cards'][mode]);return
    if v.get('menu_available'):click((1249,36));return
   if self.arena_started and now-self.arena_started>timedelta(minutes=35):self.recover_stuck_queue('Free arena outcome timed out');return
   self.queue_wake=now+timedelta(seconds=5);return
  self.queue_pause('Waiting for free arena controls',10)
