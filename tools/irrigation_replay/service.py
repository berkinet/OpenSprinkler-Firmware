"""Legal future service opportunities, without a capacity guarantee."""
from datetime import datetime, timedelta
from .calendar import normalize, resolve_calendar
from .solar import night_intervals


def legal_intervals(draft, config, now, tz, location):
    first = datetime.fromtimestamp(now, tz).date()
    last = first+timedelta(days=8)
    rules = config.rules or ((tuple(range(7)), 0, 1440),)
    base = normalize([i for days, a, b in rules for i in resolve_calendar(
        tz.key, first.isoformat(), last.isoformat(), days, [(a, b)], config.excluded)])
    if not config.rules and draft['version'] < 3:
        base = []
    result = {}
    for zone in config.zones:
        hours = config.hours[zone.id]
        daily = (night_intervals(tz.key, first, last, location) if hours == 'night' else
                 base if hours is None else resolve_calendar(tz.key, first.isoformat(), last.isoformat(), range(7), [hours]))
        result[zone.id] = normalize([(max(a,c), min(b,d)) for a,b in base for c,d in daily if max(a,c)<min(b,d)])
    return result, last
