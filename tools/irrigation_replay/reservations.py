"""Mandatory external-control periods: no valves, priority or delivery credit."""
from datetime import datetime, timedelta
from .calendar import boundary, normalize


def reservation_plan(config, now, end, tz, transition):
    # Include yesterday's start, plus tomorrow's transition edge. Durations are
    # elapsed seconds. At a repeated DST time cover both possible occurrences;
    # nonexistent starts advance to the next valid minute, never disappear.
    day = datetime.fromtimestamp(now-transition, tz).date()-timedelta(days=1)
    last = datetime.fromtimestamp(end+transition, tz).date()
    output, blocks = [], []
    while day <= last:
        for p in config.reservations:
            if day.weekday() not in p.days:
                continue
            for minute in p.times:
                start = boundary(day, minute, tz, False)
                finish = boundary(day, minute, tz, True)+p.duration
                left, right = start-transition, finish+transition
                if right <= now or left >= end:
                    continue
                blocks.append((left, right))
                output.append(dict(program_id=p.id, program_name=p.name,
                    schedule_mode='reservation', status='reserved', reason='external_control',
                    start=start, end=finish, blocked_start=left, blocked_end=right,
                    local_start=datetime.fromtimestamp(start, tz).isoformat(),
                    local_end=datetime.fromtimestamp(finish, tz).isoformat(),
                    duration_seconds=finish-start, transition_seconds=transition,
                    pulses=[], delivery_basis='no_soil_credit', promotion_eligible=False))
        day += timedelta(days=1)
    return sorted(output, key=lambda item: item['start']), normalize(blocks)
