"""Daily reset, GBR clearance and full-batch sweep policy. No desktop input."""
from dataclasses import dataclass
from lib.farming import UNBOOSTED_SWEEPS
from datetime import datetime, time, timedelta, timezone
from enum import Enum

UTC=timezone.utc


def next_reset(now):
    if now.tzinfo is None:raise ValueError("Timezone-aware clock required")
    now=now.astimezone(UTC)
    boundary=datetime.combine(now.date(),time(15),UTC)
    return boundary if now<boundary else boundary+timedelta(days=1)


def reset_period(now):
    return (next_reset(now)-timedelta(days=1)).isoformat()


class DailyRaidGate:
    def __init__(self):
        self.counters={}
        self.verified_at=None
        self.expires_at=None

    def observe(self,key,counter,captured_at,now):
        if key not in ("soul","seed") or captured_at.tzinfo is None:return False
        if not timedelta(0)<=now-captured_at<=timedelta(seconds=30):return False
        if reset_period(captured_at)!=reset_period(now):return False
        cap=165 if key=="soul" else 300
        if not isinstance(counter,(tuple,list)) or len(counter)!=2 or any(type(n) is not int for n in counter):return False
        if counter[1]!=cap or not 0<=counter[0]<=cap:return False
        self.counters[key]=(tuple(counter),captured_at)
        if counter[0]!=0:
            self.verified_at=self.expires_at=None
            return False
        valid={name:value for name,value in self.counters.items()
               if reset_period(value[1])==reset_period(now)
               and timedelta(0)<=now-value[1]<=timedelta(minutes=10)}
        if valid.get("soul",(None,))[0]==(0,165) and valid.get("seed",(None,))[0]==(0,300):
            self.verified_at=max(value[1] for value in valid.values())
            self.expires_at=next_reset(now)
        return self.cleared(now)

    def cleared(self,now):
        return bool(self.verified_at and self.verified_at<=now<self.expires_at)

    def cache_record(self,now):
        if not self.cleared(now):return None
        return {"verified_at":self.verified_at.isoformat(),"expires_at":self.expires_at.isoformat(),
            "counters":{key:{"value":list(value),"captured_at":captured.isoformat()}
                for key,(value,captured) in self.counters.items()}}

    @classmethod
    def from_cache(cls,record,now):
        gate=cls()
        try:
            verified=datetime.fromisoformat(record['verified_at'])
            expires=datetime.fromisoformat(record['expires_at'])
            if verified.tzinfo is None or expires.tzinfo is None:return gate
            if not verified<=now<expires or expires!=next_reset(verified) or reset_period(verified)!=reset_period(now):return gate
            counters={}
            for key,cap in (("soul",165),("seed",300)):
                row=record['counters'][key];value=row['value']
                captured=datetime.fromisoformat(row['captured_at'])
                if value!=[0,cap] or any(type(n) is not int for n in value):return gate
                if captured.tzinfo is None or not timedelta(0)<=verified-captured<=timedelta(minutes=10):return gate
                if reset_period(captured)!=reset_period(now):return gate
                counters[key]=(tuple(value),captured)
            if max(captured for _,captured in counters.values())!=verified:return gate
            gate.counters=counters;gate.verified_at=verified;gate.expires_at=expires
        except (KeyError,TypeError,ValueError,AttributeError):pass
        return gate


class QueueAction(str,Enum):
    STOP="stopped"
    GBR="check_gbr"
    INSPECT="inspect_mission"
    BOOST="wait_boost"
    ENERGY="wait_energy"
    TICKETS="wait_tickets"
    CLEAR="clear_full_batch"
    SKIP="skip"
    WAIT="wait_reset"
    ERROR="needs_attention"


@dataclass(frozen=True)
class BatchEvidence:
    mode:str
    remaining:int
    selected:int
    energy_total:int|None
    boost_total:int|None
    ticket_total:int|None
    energy_available:int|None
    boost_available:int|None
    tickets_available:int|None
    captured_at:datetime
    crystal_total:int|None=None
    boosted:bool=False
    sweep_verified:bool=False
    result_verified:bool=False


@dataclass(frozen=True)
class QueueDecision:
    action:QueueAction
    reason:str


def batch_decision(evidence,gate,now):
    unboosted=evidence.mode in UNBOOSTED_SWEEPS
    if not unboosted and not gate.cleared(now):return QueueDecision(QueueAction.GBR,"GBR rewards must be checked for this reset")
    if evidence.captured_at.tzinfo is None or not timedelta(0)<=now-evidence.captured_at<=timedelta(seconds=30):
        return QueueDecision(QueueAction.INSPECT,"Refresh mission and resource values")
    if reset_period(evidence.captured_at)!=reset_period(now):
        return QueueDecision(QueueAction.INSPECT if unboosted else QueueAction.GBR,"Daily reset crossed during inspection")
    if type(evidence.remaining) is not int or not 0<=evidence.remaining<=100:
        return QueueDecision(QueueAction.ERROR,"Remaining reward entries unreadable")
    if unboosted and evidence.remaining>5:return QueueDecision(QueueAction.ERROR,"Converging daily entries exceed five")
    if evidence.remaining==0:return QueueDecision(QueueAction.SKIP,"No reward entries remain")
    if type(evidence.selected) is not int or evidence.selected!=evidence.remaining:
        return QueueDecision(QueueAction.INSPECT,"Select every remaining entry as one full batch")
    costs=(evidence.boost_total,evidence.crystal_total)
    if any(type(n) is not int or n<0 for n in costs):
        return QueueDecision(QueueAction.ERROR,"Read boost and crystal costs before clearing")
    if evidence.crystal_total!=0 or not evidence.sweep_verified:
        return QueueDecision(QueueAction.ERROR,"Only verified ticket sweeps with no crystals are allowed")
    if unboosted:
        if evidence.boost_total!=0:return QueueDecision(QueueAction.ERROR,"Converging Fates must have verified zero boost cost")
        return QueueDecision(QueueAction.CLEAR,f"Ticket sweep all {evidence.remaining} Converging Fates entries; no boost or GBR gate")
    if type(evidence.boost_available) is not int or evidence.boost_available<0:
        return QueueDecision(QueueAction.INSPECT,"Read current boost points")
    if type(evidence.boosted) is not bool or not evidence.boosted or evidence.boost_total<=0:
        return QueueDecision(QueueAction.BOOST,"Wait for enough boost for the full batch; never clear unboosted")
    if evidence.boost_available<evidence.boost_total:
        return QueueDecision(QueueAction.BOOST,f"Need {evidence.boost_total} boost for all {evidence.remaining} clears; have {evidence.boost_available}")
    return QueueDecision(QueueAction.CLEAR,f"Clear all {evidence.remaining} entries with boost and existing tickets")


class ContinuousQueue:
    def __init__(self,gate=None):
        self.gate=gate or DailyRaidGate()
        self.running=False
        self.period=None
        self.completed=set()
        self.pending=None
        self.generation=0
        self.error=None

    def start(self,now):
        if self.pending:
            raise RuntimeError("Verify the previous clear's outcome before restarting")
        self.running=True
        self.error=None
        self.generation+=1
        self.rollover(now)

    def stop(self):
        self.running=False
        self.generation+=1

    def resume_verification(self,now):
        if not self.pending:raise RuntimeError("No pending outcome to verify")
        self.running=True;self.generation+=1;self.rollover(now)

    def rollover(self,now):
        period=reset_period(now)
        if self.period!=period:
            self.period=period
            self.completed.clear()
            return True
        return False

    def next_mode(self,modes,now):
        self.rollover(now)
        if not self.running:return None
        return next((name for name in modes if name not in self.completed),None)

    def authorize(self,evidence,now):
        self.rollover(now)
        if not self.running:return QueueDecision(QueueAction.STOP,"Queue stopped")
        if self.pending:return QueueDecision(QueueAction.ERROR,"Previous clear outcome must be verified; no retry")
        if evidence.mode in self.completed:return QueueDecision(QueueAction.SKIP,"Already completed for this reset")
        decision=batch_decision(evidence,self.gate,now)
        if decision.action==QueueAction.CLEAR:
            # Commit pending BEFORE sending any spending input.
            self.pending=(self.period,evidence.mode,evidence.remaining)
        return decision

    def verified_complete(self,mode,captured_at,now):
        if captured_at.tzinfo is None or not timedelta(0)<=now-captured_at<=timedelta(seconds=30):
            raise ValueError("Fresh completion evidence required")
        if self.pending and self.pending[1]!=mode:raise ValueError("Different mission is pending")
        pending=self.pending
        self.pending=None
        self.rollover(now)
        if pending is None or pending[0]==self.period:
            self.completed.add(mode)

    def fail(self,reason):
        self.error=reason
        self.stop()
