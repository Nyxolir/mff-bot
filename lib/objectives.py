"""Requirement-driven mission quantities; unknown inspections never authorize spending."""
from dataclasses import dataclass
from datetime import datetime
import re
from lib.daily_queue import reset_period

EXCLUDED_EVENTS={"OTHERWORLD BATTLE PASS","FUTURE PASS"}


def excluded_event(title):
    normalized=re.sub(r"[^A-Z0-9\s]","",title.upper())
    return " ".join(normalized.split()) in EXCLUDED_EVENTS


@dataclass(frozen=True)
class Objective:
    source:str
    kind:str
    done:int
    total:int
    text:str


def parse_objectives(source,text):
    """Extract only the three authorized objective types from complete task rows."""
    normalized=re.sub(r"\s+"," ",text.upper())
    rows=[]
    for match in re.finditer(r"(?:\[)?(?:DIMENSION MISSION|DISPATCH MISSION)(?:\])?",normalized):
        part=normalized[match.start():]
        next_mode=re.search(r"\[(?!DIMENSION MISSION|DISPATCH MISSION)[A-Z -]+\]",part[1:])
        if next_mode:part=part[:next_mode.start()+1]
        counter=re.search(r"\(?\b(\d+)\s*/\s*(\d+)\b\)?",part[:220])
        if not counter:raise ValueError("Relevant objective progress unreadable: "+part[:100])
        done,total=map(int,counter.groups())
        if not 0<=done<=total or total<1:raise ValueError("Invalid objective progress")
        clause=part[:counter.start()]
        kind=None
        if "DIMENSION MISSION" in clause:
            if "CONTRIBUTION" in clause and re.search(r"ACQUIRE|ACQUIR",clause):kind="contribution"
            elif "CLEAR" in clause:kind="dimension"
        elif "DISPATCH MISSION" in clause and "CLEAR" in clause and "ENERGY" in clause:kind="dispatch_energy"
        if kind:rows.append(Objective(source,kind,done,total,clause.strip()))
    # Some events put the mode after the verb rather than in a [MODE] prefix.
    for match in re.finditer(r"(?:ACQUIRE|CLAIM|OBTAIN)\s+(?:THE\s+)?(?:DIMENSION MISSION\s+)?CONTRIBUTION REWARD",normalized):
        part=normalized[match.start():match.start()+220]
        if "DIMENSION MISSION" not in part:continue
        counter=re.search(r"\b(\d+)\s*/\s*(\d+)\b",part)
        if not counter:raise ValueError("Contribution objective progress unreadable")
        done,total=map(int,counter.groups())
        if not 0<=done<=total or total<1:raise ValueError("Invalid contribution objective progress")
        if not any(row.kind=="contribution" and row.done==done and row.total==total for row in rows):
            rows.append(Objective(source,"contribution",done,total,part[:counter.start()].strip()))
    return rows


@dataclass(frozen=True)
class MissionPlan:
    dimension_clears:int
    claim_contribution:bool
    dispatch_clears:int
    dispatch_sector:int=7
    dispatch_mission:int=1


class ObjectiveLedger:
    def __init__(self):self.period=None;self.required_sources=set();self.finished=set();self.rows={}

    def begin(self,now,event_titles):
        self.period=reset_period(now)
        self.required_sources={"Daily Challenges",*(name for name in event_titles if not excluded_event(name))}
        self.finished=set();self.rows={}

    def observe(self,source,rows):
        if source not in self.required_sources:raise ValueError("Unexpected objective source")
        for row in rows:self.rows[(source,row.kind,row.text)]=row

    def finish(self,source):self.finished.add(source)

    def finish_max_level_pass(self,source):
        if source not in self.required_sources or source in {'Daily Challenges','Event Quest'}:
            raise ValueError('Maximum-level skip is only valid for an inspected pass')
        self.rows={key:row for key,row in self.rows.items() if key[0]!=source}
        self.finished.add(source)

    def plan(self,now):
        if self.period!=reset_period(now) or self.finished!=self.required_sources or not self.required_sources:
            raise ValueError("Daily challenges and all non-excluded events must be fully inspected")
        outstanding=[row for row in self.rows.values() if row.done<row.total]
        if any(row.total-row.done>1 and not (row.source=='Event Quest' and row.kind=='dimension') for row in outstanding):
            raise ValueError("Objective asks for more than the authorized single clear/reward")
        contribution=any(row.kind=="contribution" for row in outstanding)
        dimension=max([5 if contribution else 0]+[row.total-row.done for row in outstanding if row.kind=='dimension'])
        if dimension>100:raise ValueError('Dimension requirement exceeds a daily mission batch')
        return MissionPlan(dimension,contribution,int(any(row.kind=="dispatch_energy" for row in outstanding)))


def normal_alliance_allowed(variant,remaining,auto_available):
    return variant.strip().upper()=="NORMAL" and type(remaining) is int and remaining>0 and auto_available is True


def dispatch_start_reason(values,gate,captured_at,now,plan):
    from datetime import timedelta
    if not plan or plan.dispatch_clears!=1:return "No event requires an energy Dispatch clear"
    if reset_period(captured_at)!=reset_period(now) or not timedelta(0)<=now-captured_at<=timedelta(seconds=30):return "Refresh Dispatch evidence"
    if not gate.cleared(now):return "GBR clearance required before energy/boost spending"
    if (values.get("sector"),values.get("mission"))!=(7,1):return "Only Dispatch 7-1 is allowed"
    if values.get("crystal_total")!=0 or not values.get("start_verified"):return "Dispatch start/costs not verified"
    if not values.get("use_energy"):return "Enable Use Energy for the event requirement"
    keys=("boost_cost","boost_available")
    if any(type(values.get(key)) is not int or values[key]<0 for key in keys):return "Dispatch costs/balances unreadable"
    if values["boost_cost"]<=0:return "Boosted run cost must be positive"
    if values["boost_available"]<values["boost_cost"]:return "Wait for enough boost for Dispatch 7-1"
    return None
