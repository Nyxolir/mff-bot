from pathlib import Path
import unittest
from PIL import Image,ImageDraw
from lib.arena_reader import ArenaReader
from lib.story_reader import StoryReader

FIXTURES=Path(__file__).parent/'fixtures'

class ArenaStoryTests(unittest.TestCase):
 def test_repeat_counts_do_not_require_ticket_amounts(self):
  for name,selected,cost in [('otherworld_repeat_four_oct24.png',4,9),
      ('otherworld_repeat_current.png',1,0),('otherworld_repeat_zero.png',1,0)]:
   with self.subTest(name=name):
    e=ArenaReader().read(FIXTURES/name)
    self.assertEqual(e.screen,'otherworld_repeat');self.assertEqual(e.values['selected'],selected)
    self.assertNotIn('ticket_cost',e.values)

 def test_observed_weekly_information_notice_has_only_close_control(self):
  e=ArenaReader().read(FIXTURES/'otherworld_weekly_oct24.png')
  self.assertEqual(e.screen,'arena_information');self.assertEqual(e.values,{'mode':'OTHERWORLD BATTLE','point':(640,615)})
  for box in ((420,68,875,111),(300,132,978,158),(580,597,700,637)):
   with self.subTest(box=box):
    image=Image.open(FIXTURES/'otherworld_weekly_oct24.png').convert('RGB');ImageDraw.Draw(image).rectangle(box,fill='black')
    self.assertNotEqual(ArenaReader().read(image).screen,'arena_information')

 def test_timeline_result_with_different_character_and_scenery(self):
  e=ArenaReader().read(FIXTURES/'timeline_result_oct24.png')
  self.assertEqual(e.screen,'arena_result');self.assertEqual(e.values['mode'],'TIMELINE BATTLE')
  for actual,expected in zip(e.values['point'],(870,669)):self.assertLessEqual(abs(actual-expected),2)

 def test_result_requires_both_named_panel_and_home_control(self):
  for name,box in [('timeline_result_oct24.png',(746,407,1020,445)),
                   ('timeline_result_oct24.png',(759,639,977,701)),
                   ('otherworld_result_current.png',(565,418,716,451))]:
   with self.subTest(name=name,box=box):
    from lib.mission_reader import viewport
    image=viewport(FIXTURES/name)
    ImageDraw.Draw(image).rectangle(box,fill='black')
    self.assertNotEqual(ArenaReader().read(image).screen,'arena_result')

 def test_timeline_end_with_and_without_desktop_cursor_uses_same_contract(self):
  from lib.arena_completion import arena_completion
  for name in ('timeline_exhausted_current.png','timeline_exhausted_oct24.png'):
   with self.subTest(name=name):
    e=arena_completion(FIXTURES/name)
    self.assertEqual(e.screen,'arena_exhausted');self.assertEqual(e.values,{'mode':'TIMELINE BATTLE','point':(755,604)})
    self.assertEqual(ArenaReader().read(FIXTURES/name),e)

 def test_terminal_popup_requires_message_mode_heading_and_both_buttons(self):
  from lib.arena_completion import arena_completion
  boxes=((495,80,795,127),(300,200,982,240),(520,310,790,350),(470,581,585,625),(712,582,792,626))
  for box in boxes:
   with self.subTest(box=box):
    image=Image.open(FIXTURES/'timeline_exhausted_oct24.png').convert('RGB')
    ImageDraw.Draw(image).rectangle(box,fill='black')
    self.assertIsNone(arena_completion(image))
    self.assertNotIn(ArenaReader().read(image).screen,('arena_exhausted','arena_repeat_ended','team_arena_ended'))

 def test_all_arena_modes_share_strict_terminal_message_and_buttons(self):
  from unittest.mock import patch
  from lib.arena_completion import arena_completion
  values={'heading':'STOP AUTO REPEAT','message':'Auto-Repeat has ended because you have used up all of your entries.','mode':'','close':'CLOSE','ok':'OK','runs':'3 Win(s) 2 Defeat(s)'}
  def fields(image,requests):return {name:values[name] for name,_,_ in requests}
  with patch('lib.arena_completion.read_fields',side_effect=fields):
   for mode in ('TIMELINE BATTLE','OTHERWORLD BATTLE','TEAM BATTLE ARENA'):
    values['mode']=mode
    e=arena_completion(FIXTURES/'timeline_exhausted_oct24.png')
    self.assertEqual(e.screen,'arena_exhausted');self.assertEqual(e.values['mode'],mode)
    values['message']='Auto-Repeat is running'
    self.assertIsNone(arena_completion(FIXTURES/'timeline_exhausted_oct24.png'))
    values['message']='Auto-Repeat has ended because you have used up all of your entries.'

 def test_current_story_daily_reward_already_taken(self):
  e=StoryReader().read(FIXTURES/'story_daily_reward_taken_current.png')
  self.assertEqual(e.screen,'story_ultimate');self.assertEqual(e.values['daily_rewards'],(0,1))
 def test_observed_story_ultimate_does_not_read_energy(self):
  e=StoryReader().read(FIXTURES/'story_ultimate_1080_current.png')
  self.assertEqual(e.screen,'story_ultimate');self.assertFalse(e.errors,e)
  self.assertTrue(e.values['team_2']);self.assertNotIn('energy',e.values)
  self.assertEqual(e.values['point'],(930,668))
 def test_other_modes_rewards_never_become_generic_arena_results(self):
  reader=ArenaReader()
  for name in ('world_event_result_current.png','alliance_normal_result.png','story_final_result.png','epic_result_live.png','dimension_sweep_result_one.png'):
   with self.subTest(name=name):
    self.assertNotEqual(reader.read(FIXTURES/name).screen,'arena_result')
 def test_named_arena_rewards_keep_mode_identity(self):
  for name,mode in [('timeline_result_current.png','TIMELINE BATTLE'),('otherworld_result_current.png','OTHERWORLD BATTLE')]:
   e=ArenaReader().read(FIXTURES/name)
   self.assertEqual(e.screen,'arena_result');self.assertEqual(e.values['mode'],mode)
 def test_team_arena_refill_means_zero_entries_never_click_refill(self):
  e=ArenaReader().read(FIXTURES/'team_arena_refill_current.png')
  self.assertEqual(e.screen,'team_arena_lobby');self.assertEqual(e.values['entries'],(0,5))
  self.assertNotIn('point',e.values)
 def test_observed_1080_otherworld_ticket_icon(self):
  e=ArenaReader().read(FIXTURES/'otherworld_lobby_1080_current.png')
  self.assertEqual(e.screen,'otherworld_lobby');self.assertTrue(e.values['ticket_icon_verified'])
 def test_observed_glory_storage_notice(self):
  e=ArenaReader().read(FIXTURES/'timeline_glory_cap_current.png')
  self.assertEqual(e.screen,'timeline_glory_cap');self.assertEqual(e.values['point'],(742,536))
 def test_team_arena_acquire_popup_is_not_an_unknown_lobby(self):
  e=ArenaReader().read(FIXTURES/'team_arena_acquire_current.png')
  self.assertEqual(e.screen,'arena_acquire');self.assertEqual(e.values['point'],(640,585))

 def test_otherworld_close_summary_requires_explicit_ended_text(self):
  from unittest.mock import patch
  from lib.arena_completion import arena_completion
  values={'heading':'STOP AUTO REPEAT','message':'AUTO REPEAT HAS ENDED','mode':'OTHERWORLD BATTLE','close':'CLOSE','runs':''}
  def fields(image,requests):return {name:values[name] for name,_,_ in requests}
  with patch('lib.arena_completion.read_fields',side_effect=fields):
   e=arena_completion(FIXTURES/'team_arena_ended.png')
   self.assertEqual(e.screen,'arena_repeat_ended');self.assertEqual(e.values['mode'],'OTHERWORLD BATTLE')
   values['message']='AUTO REPEAT IS RUNNING'
   self.assertIsNone(arena_completion(FIXTURES/'team_arena_ended.png'))
 def test_otherworld_repeat_ignores_ticket_deduction(self):
  from unittest.mock import patch
  def fields(image,requests):
   values={'title':'','selected':'5','cost':'-12','start':'START'}
   return {name:values[name] for name,_,_ in requests}
  with patch('lib.arena_reader.read_fields',side_effect=fields):
   e=ArenaReader().read(FIXTURES/'otherworld_repeat_current.png')
  self.assertEqual(e.screen,'otherworld_repeat');self.assertNotIn('ticket_cost',e.values)
 def test_team_repeat_end_is_explicit_and_counts_all_five_runs(self):
  from lib.arena_completion import arena_completion
  evidence=arena_completion(FIXTURES/'team_arena_ended.png')
  self.assertEqual(evidence.screen,'team_arena_ended');self.assertEqual(evidence.values['runs'],5)

 def test_observed_one_win_four_defeats_counts_as_five_finished_runs(self):
  from lib.arena_completion import arena_completion
  evidence=arena_completion(FIXTURES/'team_arena_ended_one_win_oct24.png')
  self.assertEqual(evidence.screen,'team_arena_ended');self.assertEqual(evidence.values['runs'],5)
 def test_explicit_story_ended_summary(self):
  from lib.story_completion import story_completion
  image=Image.open(FIXTURES/'story_progress_ended.png').convert('RGB')
  evidence=story_completion(image)
  self.assertEqual(evidence.screen,'story_ended');self.assertEqual(evidence.values['point'],(640,603))
  ImageDraw.Draw(image).rectangle((495,112,790,159),fill='black')
  self.assertIsNone(story_completion(image))
 def test_current_arena_routes_and_terminal_screens(self):
  reader=ArenaReader()
  cases={'timeline_lobby_current.png':'timeline_lobby','timeline_team_current.png':'timeline_setup',
   'timeline_battle_current.png':'arena_battle','timeline_exhausted_current.png':'arena_exhausted',
   'timeline_result_current.png':'arena_result','otherworld_current.png':'otherworld_lobby','arena_selector_season23.png':'arena_selector',
   'otherworld_opponent_current.png':'otherworld_opponent','otherworld_deployment_current.png':'otherworld_setup',
   'otherworld_result_current.png':'arena_result','arena_power_done.png':'arena_power','arena_selector_current.png':'arena_selector'}
  cases.update({'otherworld_zero_current.png':'otherworld_lobby','otherworld_repeat_zero.png':'otherworld_repeat','otherworld_repeat_current.png':'otherworld_repeat','otherworld_repeat_opening.png':'arena_transition'})
  cases.update({'team_arena_lobby.png':'team_arena_lobby','team_arena_repeat.png':'team_arena_repeat','team_arena_repeat_two.png':'team_arena_repeat'})
  for name,screen in cases.items():
   with self.subTest(name=name):
    evidence=reader.read(FIXTURES/name);self.assertEqual(evidence.screen,screen,evidence);self.assertFalse(evidence.errors,evidence)
 def test_story_ultimate_and_auto_progress(self):
  reader=StoryReader()
  for name,screen in [('story_select_current.png','story_select'),('story_ultimate_lobby.png','story_ultimate'),
                       ('story_progress_current.png','story_progress'),('story_battle_current.png','story_battle'),
                       ('story_ultimate_live.png','story_ultimate'),('story_progress_live.png','story_progress'),
                       ('story_progress_settled.png','story_progress'),('story_auto_progress_battle.png','story_battle'),
                       ('story_final_result.png','story_result')]:
   with self.subTest(name=name):
    evidence=reader.read(FIXTURES/name);self.assertEqual(evidence.screen,screen,evidence);self.assertFalse(evidence.errors,evidence)
  evidence=reader.read(FIXTURES/'story_progress_current.png');self.assertTrue(evidence.values['from_stage_one'])
  evidence=reader.read(FIXTURES/'story_ultimate_lobby.png');self.assertTrue(evidence.values['team_2']);self.assertNotIn('energy',evidence.values)
 def test_story_without_ultimate_evidence_never_authorizes_start(self):
  image=Image.open(FIXTURES/'story_ultimate_lobby.png').convert('RGB')
  ImageDraw.Draw(image).rectangle((834,585,1235,610),fill='black')
  self.assertNotEqual(StoryReader().read(image).screen,'story_ultimate')
 def test_story_repeat_tab_is_not_auto_progress(self):
  image=Image.open(FIXTURES/'story_progress_current.png').convert('RGB')
  ImageDraw.Draw(image).rectangle((307,202,640,232),fill='black')
  evidence=StoryReader().read(image);self.assertTrue(evidence.errors)
 def test_missing_exhaustion_message_does_not_complete_timeline(self):
  image=Image.open(FIXTURES/'timeline_exhausted_current.png').convert('RGB')
  ImageDraw.Draw(image).rectangle((305,239,978,271),fill='black')
  self.assertNotEqual(ArenaReader().read(image).screen,'arena_exhausted')
