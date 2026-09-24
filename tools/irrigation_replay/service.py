"""Legal future service opportunities, without a capacity guarantee."""
from datetime import datetime, timedelta
from .calendar import normalize, resolve_calendar
from .solar import night_intervals
from .reservations import reservation_plan
from .fixed import subtract


def legal_intervals(draft, config, now, tz, location, transition=0):
    first = datetime.fromtimestamp(now, tz).date()
    last = first+timedelta(days=8)
    rules = config.rules or ((tuple(range(7)), 0, 1440),)
    base = normalize([i for days, a, b in rules for i in resolve_calendar(
        tz.key, first.isoformat(), last.isoformat(), days, [(a, b)], config.excluded)])
    if not config.rules and draft['version'] < 3:
        base = []
    result = {}
    end = int(datetime.combine(last+timedelta(days=1), datetime.min.time(), tz).timestamp())
    _, blocks = reservation_plan(config, now, end, tz, transition)
    for zone in config.zones:
        hours = config.hours[zone.id]
        daily = (night_intervals(tz.key, first, last, location) if hours == 'night' else
                 base if hours is None else resolve_calendar(tz.key, first.isoformat(), last.isoformat(), range(7), [hours]))
        result[zone.id] = subtract(normalize([(max(a,c), min(b,d)) for a,b in base for c,d in daily if max(a,c)<min(b,d)]), blocks)
    return result, last
