"""Persistent passive-supply clock, independent of the daily reset."""
from datetime import datetime,timedelta

CAPACITY=timedelta(hours=12)
EARLY=timedelta(minutes=10)

def next_supply_check(now,last_claim=None,fill=None):
    if last_claim is not None:
        if last_claim.tzinfo is None or last_claim>now:raise ValueError('Invalid Dispatch claim time')
        due=last_claim+CAPACITY-EARLY
        # A check near the boundary may see supplies still filling.
        return due if due>now else now+timedelta(minutes=10)
    if isinstance(fill,(int,float)) and 0<=fill<=1:
        return now+max(timedelta(minutes=10),CAPACITY*(1-fill)-EARLY)
    return now+timedelta(minutes=15)

def load_schedule(record,now):
    try:
        last=datetime.fromisoformat(record['last_claimed_at']) if record.get('last_claimed_at') else None
        due=datetime.fromisoformat(record['next_check_at'])
        if due.tzinfo is None or (last is not None and (last.tzinfo is None or last>now)):raise ValueError('Invalid timestamp')
        if due>now+CAPACITY:raise ValueError('Invalid future check')
        return last,max(now,due)
    except (ValueError,TypeError,KeyError,AttributeError):return None,now
