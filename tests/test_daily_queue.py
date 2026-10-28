from dataclasses import replace
from datetime import datetime,timedelta,timezone
import unittest
from lib.daily_queue import DailyRaidGate,ContinuousQueue,BatchEvidence,QueueAction,batch_decision,next_reset,reset_period
from lib.resource_check import click_game_point,InputNotSent,resource_status


class DailyQueueTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,18,16,tzinfo=timezone.utc)
        self.gate=DailyRaidGate()
        self.gate.observe("soul",(0,165),self.now,self.now)
        self.gate.observe("seed",(0,300),self.now,self.now)
        self.batch=BatchEvidence("CUTTING CABLE",3,3,12,12,3,100,12,30,self.now,0,True,True)

    def test_reset_is_15_utc_through_dst_change(self):
        for day in (18,24,25,26):
            before=datetime(2026,10,day,14,59,59,tzinfo=timezone.utc)
            reset=next_reset(before)
            self.assertEqual(reset.hour,15)
            self.assertNotEqual(reset_period(before),reset_period(reset))
            self.assertEqual(next_reset(reset),reset+timedelta(days=1))

    def test_clearance_lasts_to_next_reset(self):
        self.assertTrue(self.gate.cleared(self.now+timedelta(hours=20)))
        self.assertFalse(self.gate.cleared(next_reset(self.now)))

    def test_saved_clearance_survives_restart_but_not_reset(self):
        record=self.gate.cache_record(self.now)
        later=self.now+timedelta(hours=8)
        restored=DailyRaidGate.from_cache(record,later)
        self.assertTrue(restored.cleared(later))
        self.assertEqual(restored.counters,self.gate.counters)
        self.assertFalse(DailyRaidGate.from_cache(record,next_reset(self.now)).cleared(next_reset(self.now)))
        restored.observe('seed',(1,300),later,later)
        self.assertIsNone(restored.cache_record(later))

    def test_invalid_cache_never_authorizes_raid_clearance(self):
        from copy import deepcopy
        record=self.gate.cache_record(self.now)
        for field,value in [('verified_at',(self.now+timedelta(hours=1)).isoformat()),
                            ('expires_at',(next_reset(self.now)+timedelta(days=1)).isoformat())]:
            bad=deepcopy(record);bad[field]=value
            self.assertFalse(DailyRaidGate.from_cache(bad,self.now).cleared(self.now))
        bad=deepcopy(record);bad['counters']['seed']['value']=[1,300]
        self.assertFalse(DailyRaidGate.from_cache(bad,self.now).cleared(self.now))
        for bad in (None,{},'bad'):
            self.assertFalse(DailyRaidGate.from_cache(bad,self.now).cleared(self.now))

    def test_cached_gbr_with_new_balance_survives_ten_minutes(self):
        later=self.now+timedelta(hours=8)
        balances=({"energy":(100,120),"boost":100},later)
        status=resource_status(self.gate.counters,balances,later,self.gate)
        self.assertIn("GBR complete",status)

    def test_guard_rejects_input_before_native_calls(self):
        with self.assertRaises(InputNotSent):click_game_point(0,100,100,guard=lambda:False)

    def test_counters_cannot_be_mixed_across_reset(self):
        gate=DailyRaidGate()
        boundary=next_reset(self.now)
        gate.observe("soul",(0,165),boundary-timedelta(seconds=1),boundary-timedelta(seconds=1))
        gate.observe("seed",(0,300),boundary,boundary)
        self.assertFalse(gate.cleared(boundary))

    def test_nonzero_counter_revokes_clearance(self):
        self.gate.observe("seed",(1,300),self.now,self.now)
        self.assertFalse(self.gate.cleared(self.now))

    def test_all_three_or_wait_no_partial_batch(self):
        self.assertEqual(batch_decision(self.batch,self.gate,self.now).action,QueueAction.CLEAR)
        self.assertEqual(batch_decision(replace(self.batch,boost_available=11),self.gate,self.now).action,QueueAction.BOOST)
        self.assertEqual(batch_decision(replace(self.batch,selected=2),self.gate,self.now).action,QueueAction.INSPECT)

    def test_unboosted_never_falls_back_to_energy(self):
        for change in ({"boosted":False},{"boost_total":0},{"boost_available":0}):
            self.assertEqual(batch_decision(replace(self.batch,**change),self.gate,self.now).action,QueueAction.BOOST)

    def test_missing_costs_crystals_and_balances_block(self):
        for change in ({"crystal_total":1},{"boost_total":None},{"sweep_verified":False}):
            self.assertEqual(batch_decision(replace(self.batch,**change),self.gate,self.now).action,QueueAction.ERROR)
        self.assertEqual(batch_decision(replace(self.batch,energy_available=1),self.gate,self.now).action,QueueAction.CLEAR)
        self.assertEqual(batch_decision(replace(self.batch,tickets_available=1),self.gate,self.now).action,QueueAction.CLEAR)

    def test_reset_immediately_before_clear_blocks(self):
        boundary=next_reset(self.now)
        evidence=replace(self.batch,captured_at=boundary-timedelta(seconds=1))
        self.assertEqual(batch_decision(evidence,self.gate,boundary).action,QueueAction.GBR)

    def test_stop_prevents_any_spending(self):
        queue=ContinuousQueue(self.gate)
        queue.start(self.now)
        queue.stop()
        self.assertEqual(queue.authorize(self.batch,self.now).action,QueueAction.STOP)

    def test_uncertain_clear_not_retried(self):
        queue=ContinuousQueue(self.gate)
        queue.start(self.now)
        self.assertEqual(queue.authorize(self.batch,self.now).action,QueueAction.CLEAR)
        self.assertEqual(queue.authorize(self.batch,self.now).action,QueueAction.ERROR)
        queue.fail("timeout")
        with self.assertRaises(RuntimeError):queue.start(self.now)

    def test_done_missions_reopen_on_reset_only(self):
        queue=ContinuousQueue(self.gate)
        queue.start(self.now)
        queue.authorize(self.batch,self.now)
        queue.verified_complete(self.batch.mode,self.now,self.now)
        self.assertIsNone(queue.next_mode([self.batch.mode],self.now))
        boundary=next_reset(self.now)
        self.assertEqual(queue.next_mode([self.batch.mode],boundary),self.batch.mode)
        self.assertFalse(queue.gate.cleared(boundary))

    def test_old_result_does_not_complete_new_day(self):
        queue=ContinuousQueue(self.gate)
        queue.start(self.now)
        queue.authorize(self.batch,self.now)
        boundary=next_reset(self.now)
        queue.verified_complete(self.batch.mode,boundary,boundary)
        self.assertNotIn(self.batch.mode,queue.completed)
