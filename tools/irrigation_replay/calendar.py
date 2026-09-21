"""Explicit local calendar rules resolved to UTC, with conservative DST edges."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from .model import integer


def boundary(day, minute, tz, opening):
    """Nonexistent minutes advance; ambiguous openings late, closings early."""
    integer(minute)
    if minute > 1440:
        raise ValueError('minute outside local day')
    local = datetime.combine(day, time()) + timedelta(minutes=minute)
    for _ in range(181):
        choices = set()
        for fold in (0, 1):
            aware = local.replace(tzinfo=tz, fold=fold)
            stamp = int(aware.timestamp())
            if datetime.fromtimestamp(stamp, tz).replace(tzinfo=None) == local:
                choices.add(stamp)
        if choices:
            return max(choices) if opening else min(choices)
        local += timedelta(minutes=1)
    raise ValueError('local boundary cannot be resolved within three hours')


def normalize(intervals):
    result = []
    for a, b in sorted(intervals):
        if b <= a:
            continue
        if result and a <= result[-1][1]:
            result[-1] = (result[-1][0], max(b, result[-1][1]))
        else:
            result.append((a, b))
    return result


def resolve_calendar(timezone_name, first_date, last_date, weekdays, windows,
                     excluded_dates=()):
    """Resolve inclusive local-date range; dates/rules supplied by fixtures.

    Windows are [opening minute, closing minute], with 1440 allowed as close.
    Equal endpoints are invalid; use [0,1440] for a whole day. Weekdays 0..6.
    Overnight continuation is allowed only when BOTH dates are permitted.
    """
    tz = ZoneInfo(timezone_name)
    first, last = date.fromisoformat(first_date), date.fromisoformat(last_date)
    if last < first or (last-first).days > 366:
        raise ValueError('calendar range must be 0..366 days')
    for value in weekdays:
        integer(value)
        if value > 6:
            raise ValueError('invalid weekday')
    for a, b in windows:
        integer(a)
        integer(b)
        if a >= 1440 or b > 1440 or a == b:
            raise ValueError('invalid local window')
    excluded = {date.fromisoformat(x) for x in excluded_dates}
    legal = lambda d: d.weekday() in weekdays and d not in excluded
    intervals = []
    origin = first-timedelta(days=1)
    while origin <= last:
        if legal(origin):
            for a, b in windows:
                segments = [(origin, a, b)] if b > a else [
                    (origin, a, 1440), (origin+timedelta(days=1), 0, b)]
                for day, begin, end in segments:
                    if first <= day <= last and legal(day):
                        intervals.append((boundary(day, begin, tz, True),
                                          boundary(day, end, tz, False)))
        origin += timedelta(days=1)
    return normalize(intervals)
