from datetime import datetime,timedelta,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from lib.world_event import WorldEventState,WorldEventReader,event_delay
from lib.daily_queue import next_reset

class WorldEventTests(unittest.TestCase):
 def test_done_cache_requires_valid_three_visit_page_proof(self):
  import json
  with TemporaryDirectory(dir=Path(__file__).resolve().parents[3]/'work') as d:
   path=Path(d)/'state.json';s=WorldEventState(self.now);verified=self.confirm_zero(s,self.now);s.save(path)
   valid=json.loads(path.read_text());self.assertTrue(WorldEventState.load(verified,path).done)
   for changed in ({'source':'content_board'}, {'observations':valid['completion_proof']['observations'][:1]},
                   {'observations':[valid['completion_proof']['observations'][0]]*3}):
    data=dict(valid,completion_proof=dict(valid['completion_proof'],**changed));path.write_text(json.dumps(data))
    loaded=WorldEventState.load(verified,path);self.assertFalse(loaded.done);self.assertTrue(loaded.cache_done_rejected);self.assertEqual(loaded.next_check,verified)
   data=dict(valid,pending=True,started=True);path.write_text(json.dumps(data))
   loaded=WorldEventState.load(verified,path);self.assertFalse(loaded.done);self.assertTrue(loaded.pending);self.assertTrue(loaded.started)

 def test_stale_future_or_unidentified_zero_visits_do_not_count(self):
  for observed,visit in ((self.now-timedelta(seconds=31),0),(self.now+timedelta(seconds=1),0),(self.now,None)):
   with self.subTest(observed=observed,visit=visit):
    s=WorldEventState(self.now);self.assertEqual(s.lobby(self.values(0),self.now,observed=observed,visit=visit),'recheck_zero')
    self.assertFalse(s.done);self.assertEqual(s.zero_observations,[])

 def test_zero_is_not_done_on_one_visit_or_duplicate_capture(self):
  s=WorldEventState(self.now)
  for i in range(4):
   now=self.now+timedelta(seconds=i*5)
   self.assertEqual(s.lobby(self.values(0),now,observed=now,visit=0),'recheck_zero')
  self.assertFalse(s.done);self.assertEqual(len(s.zero_observations),1)
  for visit in (1,2):s.lobby(self.values(0),self.now+timedelta(seconds=25),observed=self.now,visit=visit)
  self.assertFalse(s.done);self.assertEqual(len(s.zero_observations),1)

 def test_cached_zero_refreshing_to_two_entries_clears_candidate_and_enters(self):
  s=WorldEventState(self.now);s.lobby(self.values(0),self.now,observed=self.now,visit=0)
  later=self.now+timedelta(seconds=10)
  self.assertEqual(s.lobby(self.values(2),later,observed=later,visit=1),'enter')
  self.assertFalse(s.done);self.assertEqual(s.zero_observations,[])

 def test_zero_verification_preserves_pending_until_third_distinct_visit(self):
  s=WorldEventState(self.now);s.pending=True;s.before=1
  for visit in range(3):
   now=self.now+timedelta(seconds=visit*5);s.lobby(self.values(0),now,observed=now,visit=visit)
   self.assertEqual(s.pending,visit<2);self.assertEqual(s.done,visit==2)

 def test_zero_during_submitted_battle_cannot_clear_pending(self):
  s=WorldEventState(self.now);s.pending=True;s.started=True;s.before=1
  for visit in range(3):
   now=self.now+timedelta(seconds=visit*5);s.lobby(self.values(0),now,observed=now,visit=visit)
  self.assertTrue(s.pending);self.assertTrue(s.started);self.assertFalse(s.done)

 def test_old_board_done_cache_is_rejected_and_submission_latches_preserved(self):
  import json
  now=datetime(2026,10,24,22,10,tzinfo=timezone.utc)
  fixture=Path(__file__).parent/'fixtures/world_event_unverified_done_oct25.json'
  s=WorldEventState.load(now,fixture);self.assertFalse(s.done);self.assertTrue(s.cache_done_rejected);self.assertEqual(s.next_check,now)
  with TemporaryDirectory(dir=Path(__file__).resolve().parents[3]/'work') as d:
   data=json.loads(fixture.read_text());data.update(pending=True,started=True,before=2)
   path=Path(d)/'state.json';path.write_text(json.dumps(data))
   s=WorldEventState.load(now,path);self.assertFalse(s.done);self.assertTrue(s.pending);self.assertTrue(s.started);self.assertEqual(s.before,2)

 def test_unfinished_zero_proof_is_not_carried_across_restart(self):
  with TemporaryDirectory(dir=Path(__file__).resolve().parents[3]/'work') as d:
   path=Path(d)/'state.json';s=WorldEventState(self.now);s.lobby(self.values(0),self.now,observed=self.now,visit=0);s.save(path)
   loaded=WorldEventState.load(self.now,path);self.assertFalse(loaded.done);self.assertEqual(loaded.zero_observations,[])

 def test_live_refreshed_page_has_both_unused_entries_and_no_score(self):
  e=WorldEventReader().read(Path(__file__).parent/'fixtures/world_event_refresh_oct25.png')
  self.assertEqual(e.screen,'we_lobby');self.assertEqual(e.values['entries'],(2,2));self.assertEqual(e.values['best_score'],0)

 def test_current_world_event_battle_keeps_auto_enabled(self):
  e=WorldEventReader().read(Path(__file__).parent/'fixtures/world_event_battle_1080_current.png')
  self.assertEqual(e.screen,'we_battle');self.assertTrue(e.values['auto_on'])
 def test_trivia_challenges_can_return_home(self):
  e=WorldEventReader().read(Path(__file__).parent/'fixtures/trivia_start_current.png')
  self.assertEqual(e.screen,'challenge_navigation');self.assertTrue(e.values['home_available'])
 def setUp(self):self.now=datetime(2026,10,19,9,tzinfo=timezone.utc)
 def values(self,remaining=1,score=0,available=True):return dict(entries=(remaining,2),best_score=score,available=available,delay=3600)
 def confirm_zero(self,state,now):
  for visit in range(3):
   stamp=now+timedelta(seconds=visit*5)
   decision=state.lobby(self.values(0),stamp,observed=stamp,visit=visit)
   self.assertEqual(decision,'done' if visit==2 else 'recheck_zero')
  return now+timedelta(seconds=10)
 def test_score_only_skips_current_slot_and_next_slot_can_run(self):
  s=WorldEventState(self.now)
  self.assertEqual(s.lobby(self.values(score=123),self.now),'scored');self.assertFalse(s.done)
  self.assertEqual(s.lobby(self.values(),self.now+timedelta(hours=2)),'enter')
 def test_only_zero_entries_finishes_day(self):
  s=WorldEventState(self.now);self.confirm_zero(s,self.now)
  self.assertTrue(s.done);self.assertEqual(s.next_check,next_reset(self.now))
  s.rollover(next_reset(self.now));self.assertFalse(s.done)
 def test_closed_slot_rechecks_and_does_not_mark_done(self):
  s=WorldEventState(self.now);self.assertEqual(s.lobby(self.values(available=False),self.now),'closed')
  self.assertFalse(s.done);self.assertEqual(s.next_check,self.now+timedelta(minutes=5))
 def test_unknown_entry_does_not_repeat_within_slot(self):
  s=WorldEventState(self.now);s.lobby(self.values(),self.now);s.pending=True;s.started=True
  self.assertEqual(s.lobby(self.values(),self.now+timedelta(minutes=5)),'wait')
  self.assertTrue(s.pending)
 def test_counter_drop_allows_later_slot(self):
  s=WorldEventState(self.now);s.lobby(self.values(2),self.now);s.pending=True
  self.assertEqual(s.lobby(self.values(1,score=123),self.now),'scored');self.assertFalse(s.done)
 def test_cache_survives_restart_and_expires_at_reset(self):
  with TemporaryDirectory(dir=Path(__file__).resolve().parents[3]/'work') as d:
   path=Path(d)/'state.json';s=WorldEventState(self.now);verified=self.confirm_zero(s,self.now);s.save(path)
   self.assertTrue(WorldEventState.load(verified,path).done)
   self.assertFalse(WorldEventState.load(next_reset(self.now),path).done)
   s=WorldEventState(self.now);s.pending=True;s.started=True;s.before=1;s.save(path)
   self.assertTrue(WorldEventState.load(self.now,path).pending)
 def test_observed_current_screens(self):
  reader=WorldEventReader();root=Path(__file__).parent/'fixtures'
  for name,screen in [('ready_current','we_lobby'),('team_current','we_team'),('entry_confirm','we_confirm'),('start_current','we_start'),('battle_auto','we_battle'),('result_current','we_result')]:
   e=reader.read(root/f'world_event_{name}.png');self.assertFalse(e.errors,e);self.assertEqual(e.screen,screen)
   if screen=='we_lobby':self.assertEqual(e.values['entries'],(1,2));self.assertTrue(e.values['available'])
   if screen=='we_battle':self.assertTrue(e.values['auto_on'])
 def test_timer(self):
  self.assertEqual(event_delay('Event Ends in: 4h 45m'),17100);self.assertEqual(event_delay('30m'),1800)


 def test_actual_zero_counter_completes_day(self):
  e=WorldEventReader().read(Path(__file__).parent/'fixtures/world_event_zero_current.png')
  self.assertEqual(e.screen,'we_lobby');self.assertEqual(e.values['entries'],(0,2))
  s=WorldEventState(self.now);self.confirm_zero(s,self.now);self.assertTrue(s.done)
 def test_home_shortcut_is_found_after_board_removes_event(self):
  e=WorldEventReader().read(Path(__file__).parent/'fixtures/world_event_home_battle_list.png')
  self.assertEqual(e.screen,'we_home');self.assertTrue(e.values['battle_tab'])
  self.assertEqual(e.values['event_point'],(1040,575))

 def test_adb_lobby_label_ignores_background_lighting(self):
  e=WorldEventReader().read(Path(__file__).parent/'fixtures/world_event_zero_adb.png')
  self.assertEqual(e.screen,'we_lobby');self.assertEqual(e.values['entries'],(0,2))
  self.assertTrue(e.values['available']);self.assertEqual(e.values['best_score'],2867810)

 def test_new_reset_team_does_not_depend_on_character_background(self):
  e=WorldEventReader().read(Path(__file__).parent/'fixtures/world_event_team_reset.png')
  self.assertEqual(e.screen,'we_team');self.assertEqual(e.values['point'],(1034,674))

 def test_actual_two_entry_confirmation_reads_ok_without_pixel_background(self):
  e=WorldEventReader().read(Path(__file__).parent/'fixtures/world_event_confirm_reset.png')
  self.assertEqual(e.screen,'we_confirm');self.assertEqual(e.values['entries'],(2,2))
  self.assertEqual(e.values['point'],(748,512))
