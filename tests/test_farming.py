import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from lib.farming import Action, Observation, RaidCheck, decide, parse_counter


class FarmingRules(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026,10,18,21,0,tzinfo=timezone.utc)
        self.o = Observation("OTHERWORLD BATTLE",5,0,0,self.now,"reset-a",
                             ticket_icon_verified=True,crystal_cost=0)
        self.raid = RaidCheck(0,165,0,300,"reset-a",self.now)

    def action(self, **changes):
        return decide(replace(self.o, **changes), self.raid, self.now).action

    def test_ticket_repeat_works_without_completed_gbr(self):
        raid = replace(self.raid,soul_remaining=63,seed_remaining=121)
        result=decide(self.o,raid,self.now)
        self.assertEqual((result.action,result.runs),(Action.TICKET_REPEAT,5))

    def test_icon_is_required_independently_of_ticket_cost(self):
        self.assertEqual(self.action(ticket_icon_verified=False),Action.STOP)

    def test_unknown_or_negative_costs_stop(self):
        for field in ("boost_cost","crystal_cost"):
            for value in (None,-1):
                with self.subTest(field=field,value=value):
                    self.assertEqual(self.action(**{field:value}),Action.STOP)

    def test_upgrades_refills_crystals_stop(self):
        for changes in ({"upgrade_prompt":True},{"refill_prompt":True},{"crystal_cost":1}):
            self.assertEqual(self.action(**changes),Action.STOP)

    def test_manual_and_unknown_modes_are_not_started(self):
        for mode in ("WORLD BOSS","ALLIANCE BATTLE","GIANT BOSS RAID","UNKNOWN"):
            self.assertEqual(self.action(mode=mode),Action.SKIP)

    def test_timeline_requires_team_1(self):
        self.assertEqual(self.action(mode="TIMELINE BATTLE"),Action.SELECT_TEAM_1)
        self.assertEqual(self.action(mode="TIMELINE BATTLE",team_1_verified=True),Action.TIMELINE_AUTO)

    def test_world_event_existing_score_skips_even_with_entries(self):
        self.assertEqual(self.action(mode="WORLD EVENT",best_score=3862486),Action.SKIP)

    def test_world_event_zero_score_is_one_run_only(self):
        result=decide(replace(self.o,mode="WORLD EVENT",best_score=0),self.raid,self.now)
        self.assertEqual((result.action,result.runs),(Action.WORLD_EVENT,1))

    def test_world_event_unreadable_score_never_enters(self):
        self.assertEqual(self.action(mode="WORLD EVENT",best_score=None),Action.STOP)

    def test_spending_energy_or_boost_requires_both_zero_counters(self):
        for energy,boost in ((4,0),(0,4),(4,4)):
            o=replace(self.o,mode="MAGNETO'S MIGHT",energy_cost=energy,boost_cost=boost,sweep_verified=True)
            for soul,seed in ((63,121),(0,121),(63,0)):
                with self.subTest(energy=energy,boost=boost,soul=soul,seed=seed):
                    raid=replace(self.raid,soul_remaining=soul,seed_remaining=seed)
                    self.assertEqual(decide(o,raid,self.now).action,Action.CHECK_GBR)
            self.assertEqual(decide(o,self.raid,self.now).action,Action.SWEEP)

    def test_stale_wrong_reset_and_wrong_cap_gbr_do_not_unlock(self):
        o=replace(self.o,mode="MAGNETO'S MIGHT",energy_cost=4,sweep_verified=True)
        for changes in ({"reset_id":"old"},{"soul_total":150},{"seed_total":200},
                        {"observed_at":self.now-timedelta(minutes=11)},
                        {"observed_at":self.now+timedelta(seconds=1)}):
            self.assertEqual(decide(o,replace(self.raid,**changes),self.now).action,Action.CHECK_GBR)

    def test_stale_screen_and_future_screen_stop(self):
        for seconds in (-31,1):
            self.assertEqual(self.action(observed_at=self.now+timedelta(seconds=seconds)),Action.STOP)

    def test_no_entries_skips(self):
        self.assertEqual(self.action(remaining=0),Action.SKIP)

    def test_malformed_observation_values_never_authorize_a_run(self):
        for changes in ({"remaining":True},{"remaining":5.5},{"remaining":1000},
                        {"crystal_cost":False},
                        {"ticket_icon_verified":"true"},{"boost_cost":"0"}):
            self.assertEqual(self.action(**changes),Action.STOP)

    def test_boolean_gbr_values_cannot_impersonate_zero(self):
        o=replace(self.o,mode="MAGNETO'S MIGHT",energy_cost=4,sweep_verified=True)
        self.assertEqual(decide(o,replace(self.raid,soul_remaining=False),self.now).action,Action.CHECK_GBR)

    def test_strict_counter_parser(self):
        self.assertEqual(parse_counter("0 / 165"),(0,165))
        for text in ("O/165","/165","165/0","166/165","0/165?",""):
            with self.assertRaises(ValueError):
                parse_counter(text)


if __name__=="__main__":
    unittest.main()
