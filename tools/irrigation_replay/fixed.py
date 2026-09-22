"""Exact local-time reservations for the offline planner; never dispatches.

Fixed events do not imply a soil refill. Missing clock times are skipped; an
ambiguous DST time occurs once, on its first occurrence. No late catch-up.
"""
from dataclasses import asdict
from datetime import datetime, time, timedelta

from .draft import Validator, shape
from .planner import Pulse


def exact_start(day, minute, tz):
    local = datetime.combine(day, time()) + timedelta(minutes=minute)
    stamp = int(local.replace(tzinfo=tz, fold=0).timestamp())
    return stamp if datetime.fromtimestamp(stamp, tz).replace(tzinfo=None) == local else None


def event_pulses(program, start, transition=0):
    remaining, cursor, pulses = program.runtime, start, []
    while remaining:
        duration = min(remaining, program.cycle)
        if 0 < remaining-duration < program.minimum:
            duration = remaining-program.minimum
        if duration < program.minimum:
            return []
        pulses.append(Pulse(cursor, cursor+duration, program.id))
        remaining -= duration
        cursor += duration + max(program.soak, transition)
    return pulses


def subtract(intervals, blocks):
    result = list(intervals)
    for left, right in blocks:
        result = [(c, d) for a, b in result for c, d in
                  ((a, min(b, left)), (max(a, right), b)) if c < d]
    return result


def fixed_plan(config, runtime, now, end, tz, allowed, transition, timestamp):
    """Reserve exact slots before flexible work; group order settles conflicts.

    Snapshot readiness/unresolved delivery applies to both policies on a valve.
    This reference increment reserves upcoming events only, never past events.
    """
    candidates = []
    day = datetime.fromtimestamp(now, tz).date()
    last = datetime.fromtimestamp(end, tz).date()
    while day <= last:
        for p in config.fixed:
            if day.weekday() not in p.days:
                continue
            for minute in p.times:
                stamp = exact_start(day, minute, tz)
                if stamp is None and datetime.fromtimestamp(now, tz).replace(tzinfo=None) <= datetime.combine(day, time())+timedelta(minutes=minute) < datetime.fromtimestamp(end, tz).replace(tzinfo=None):
                    # No invented replacement time at spring-forward.
                    candidates.append((config.groups.index(p.group), day.isoformat(), minute, p.id, p, None))
                elif stamp is not None and now <= stamp < end:
                    candidates.append((config.groups.index(p.group), day.isoformat(), minute, p.id, p, stamp))
        day += timedelta(days=1)
    v = Validator()
    states = {}
    for sid in {item[4].sid for item in candidates if item[5] is not None}:
        path = f'runtime.states.{sid}'
        state = v.get(path, lambda: shape((runtime.get('states') or {}).get(str(sid)),
                                         ('at', 'depletion_mm', 'unresolved', 'ready_at')))
        if state is not None:
            at = v.get(path+'.at', lambda: timestamp(state.get('at')))
            ready = v.get(path+'.ready_at', lambda: timestamp(state.get('ready_at')))
            if at != now:
                v.issues.append(dict(path=path+'.at', message='snapshot must be reconciled exactly through as_of'))
            unresolved = state.get('unresolved')
            if not isinstance(unresolved, list) or any(not isinstance(x, str) or not x.strip() for x in unresolved):
                v.issues.append(dict(path=path+'.unresolved', message='explicit unresolved delivery list required'))
            states[sid] = (ready, unresolved)
    v.finish()
    output, reservations, accepted = [], [], []
    for _, day, minute, _, p, stamp in sorted(candidates):
        pulses = event_pulses(p, stamp, transition) if stamp is not None else []
        reason = None
        if stamp is None:
            reason = 'nonexistent_local_time'
        elif states[p.sid][1]:
            reason = 'unresolved_delivery'
        elif stamp < states[p.sid][0]:
            reason = 'valve_not_ready'
        elif not pulses:
            reason = 'minimum_pulse_not_met'
        elif any(not any(a <= pulse.start and pulse.end <= b for a, b in allowed[p.id]) for pulse in pulses):
            reason = 'watering_restriction'
        else:
            for pulse in pulses:
                for previous, owner in accepted:
                    gap = max(transition, p.soak, owner.soak) if p.sid == owner.sid else transition
                    if pulse.start < previous.end+gap and pulse.end+gap > previous.start:
                        reason = 'priority_conflict'
        if reason is None:
            reservations.extend(pulses)
            accepted.extend((pulse, p) for pulse in pulses)
        delivered = [] if reason else pulses
        output.append(dict(program_id=p.id, sid=p.sid, program_name=p.name, schedule_mode='fixed',
            configured_group=p.group, status='skipped' if reason else 'fixed', reason=reason or 'scheduled',
            scheduled_local=f'{day}T{minute//60:02d}:{minute%60:02d}',
            delivery_basis='no_soil_credit', full_seconds=p.runtime,
            allocated_seconds=sum(x.end-x.start for x in delivered), promotion_eligible=False,
            pulses=[dict(asdict(x), sid=p.sid, duration_seconds=x.end-x.start,
                         pulse_id=f'{p.id}/{stamp}/{i+1}',
                         local_start=datetime.fromtimestamp(x.start, tz).isoformat(),
                         local_end=datetime.fromtimestamp(x.end, tz).isoformat()) for i, x in enumerate(delivered)]))
    # Retain physical-valve soak separation even though program IDs differ.
    for zone in config.zones:
        blocks = [(pulse.start-max(zone.soak_seconds, owner.soak),
                   pulse.end+max(zone.soak_seconds, owner.soak))
                  for pulse, owner in accepted if owner.sid == zone.station-1]
        allowed[zone.id] = subtract(allowed[zone.id], blocks)
    return output, sorted(reservations)
