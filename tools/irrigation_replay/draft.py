"""Compile the real browser v1 draft into the offline engine's configuration.

No controller reads, defaults for missing calibration, or runtime state writes.
Paths in errors refer to exported form fields so configuration gaps are visible.
"""
from dataclasses import dataclass
from datetime import date
import re

from .model import Profile, Zone, integer, number


class InputErrors(ValueError):
    def __init__(self, issues):
        self.issues = issues
        super().__init__('; '.join(f'{i["path"]}: {i["message"]}' for i in issues))


class Validator:
    def __init__(self):
        self.issues = []

    def get(self, path, callback):
        try:
            return callback()
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            self.issues.append(dict(path=path, message=str(exc)))
            return None

    def finish(self):
        if self.issues:
            raise InputErrors(self.issues)


def shape(value, keys):
    if not isinstance(value, dict):
        raise ValueError('expected an object')
    extra = set(value) - set(keys)
    if extra:
        raise ValueError('unmapped fields: ' + ', '.join(sorted(extra)))
    return value


def text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('a nonempty name is required')
    return value.strip()


def quantity(value, *, zero=False, maximum=None):
    # An empty form value means uncalibrated, never zero or a synthetic default.
    if value is None or value == '':
        raise ValueError('not configured')
    if type(value) not in (int, float):
        raise ValueError('expected a JSON number')
    n = number(value)
    if n < 0 or (n == 0 and not zero) or (maximum is not None and n > maximum):
        raise ValueError('value outside permitted range')
    return n


def seconds(minutes, *, zero=False):
    n = quantity(minutes, zero=zero) * 60
    rounded = round(n)
    # JSON represents a one-second UI duration as 0.016666666666666666 minutes.
    if abs(n - rounded) > number('0.0000001') or (rounded == 0 and not zero):
        raise ValueError('duration must resolve to whole seconds')
    return rounded


def minute(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
        raise ValueError('expected HH:MM in 24-hour time')
    h, m = map(int, value.split(':'))
    return 60*h + m


def weekday_list(value):
    if not isinstance(value, list) or not value:
        raise ValueError('select at least one weekday')
    for day in value:
        integer(day)
        if day > 6:
            raise ValueError('weekday must be 0 (Monday) through 6 (Sunday)')
    if len(set(value)) != len(value):
        raise ValueError('duplicate weekday')
    return tuple(value)


@dataclass(frozen=True)
class DraftConfig:
    profiles: dict
    zones: tuple
    names: dict
    disabled: tuple
    groups: tuple
    rules: tuple
    excluded: tuple
    shortage: str


def compile_draft(draft):
    """All enabled programs must be calibrated; disabled drafts stay inert."""
    v = Validator()
    v.get('draft', lambda: shape(draft, ('version', 'programs', 'groups', 'windows',
                                        'excluded', 'shortage', 'profile')))
    v.finish()
    if type(draft.get('version')) is not int or draft['version'] != 1:
        raise InputErrors([dict(path='version', message='unsupported draft version')])
    groups = draft.get('groups')
    def group_names():
        if not isinstance(groups, list) or not groups:
            raise ValueError('at least one ordered priority group is required')
        for name in groups:
            if text(name) != name:
                raise ValueError('group names must already be trimmed')
        if len({g.lower() for g in groups}) != len(groups):
            raise ValueError('group names must be unique, ignoring case')
        return tuple(groups)
    ordered = v.get('groups', group_names)
    policy = draft.get('shortage')
    if policy not in ('report_only', 'promote_next'):
        v.issues.append(dict(path='shortage', message='unknown capacity-shortfall policy'))
    rules = []
    windows = draft.get('windows')
    if not isinstance(windows, list):
        v.issues.append(dict(path='windows', message='expected a list'))
    else:
        for i, rule in enumerate(windows):
            path = f'windows[{i}]'
            if v.get(path, lambda: shape(rule, ('days', 'start', 'end'))) is None:
                continue
            days = v.get(path+'.days', lambda: weekday_list(rule.get('days')))
            start = v.get(path+'.start', lambda: minute(rule.get('start')))
            end = v.get(path+'.end', lambda: minute(rule.get('end')))
            if start is not None and end is not None and start == end:
                v.issues.append(dict(path=path, message='opening and closing must differ'))
            if days is not None and start is not None and end is not None:
                rules.append((days, start, end))
    def exclusions():
        value = draft.get('excluded')
        if not isinstance(value, str):
            raise ValueError('expected date text from the form')
        result = re.split(r'[\s,]+', value.strip()) if value.strip() else []
        for item in result:
            if date.fromisoformat(item).isoformat() != item:
                raise ValueError('excluded dates must use YYYY-MM-DD')
        return tuple(sorted(set(result)))
    excluded = v.get('excluded', exclusions)
    raw_profile = v.get('profile', lambda: shape(draft.get('profile'),
                        ('capacity', 'roots', 'depletion', 'crop', 'rain')))
    programs = draft.get('programs')
    if not isinstance(programs, list):
        v.issues.append(dict(path='programs', message='expected a list'))
        programs = []
    profiles, zones, names, disabled, seen = {}, [], {}, [], set()
    for i, p in enumerate(programs):
        path = f'programs[{i}]'
        if v.get(path, lambda: shape(p, ('sid', 'name', 'profile', 'group', 'enabled',
                                        'rate', 'efficiency', 'cycle', 'soak', 'minimum'))) is None:
            continue
        sid = v.get(path+'.sid', lambda: integer(p.get('sid')))
        name = v.get(path+'.name', lambda: text(p.get('name')))
        if sid is not None:
            if sid in seen:
                v.issues.append(dict(path=path+'.sid', message='valve already has a program'))
            seen.add(sid)
        if p.get('profile') != 'garden':
            v.issues.append(dict(path=path+'.profile', message='unknown profile'))
        if ordered is not None and p.get('group') not in ordered:
            v.issues.append(dict(path=path+'.group', message='unknown priority group'))
        if type(p.get('enabled')) is not bool:
            v.issues.append(dict(path=path+'.enabled', message='expected a boolean'))
            continue
        if not p['enabled']:
            disabled.append(dict(sid=sid, name=name, reason='disabled'))
            continue
        rate = v.get(path+'.rate', lambda: quantity(p.get('rate')))
        efficiency = v.get(path+'.efficiency', lambda: quantity(p.get('efficiency'), maximum=100))
        cycle = v.get(path+'.cycle', lambda: seconds(p.get('cycle')))
        soak = v.get(path+'.soak', lambda: seconds(p.get('soak'), zero=True))
        minimum = v.get(path+'.minimum', lambda: seconds(p.get('minimum')))
        if minimum is not None and cycle is not None and minimum > cycle:
            v.issues.append(dict(path=path+'.minimum', message='minimum pulse exceeds cycle'))
        if all(x is not None for x in (sid, name, rate, efficiency, cycle, soak, minimum)) and minimum <= cycle:
            zone = v.get(path, lambda: Zone(f'sid:{sid}', sid+1, 'garden', p.get('group'),
                                           rate, efficiency/100, cycle, soak, minimum))
            if zone is not None:
                zones.append(zone)
                names[zone.id] = name
    if any(isinstance(p, dict) and p.get('enabled') is True for p in programs) and raw_profile is not None:
        values = {}
        for key in ('capacity', 'roots', 'depletion', 'crop', 'rain'):
            values[key] = v.get('profile.'+key, lambda key=key: quantity(
                raw_profile.get(key), zero=key in ('crop', 'rain'),
                maximum=100 if key in ('depletion', 'rain') else None))
        if all(n is not None for n in values.values()):
            profiles['garden'] = Profile('garden', values['capacity'], values['roots'],
                values['depletion']/100, values['crop'], values['rain']/100)
    v.finish()
    return DraftConfig(profiles, tuple(zones), names, tuple(disabled), ordered,
                       tuple(rules), excluded, policy)
