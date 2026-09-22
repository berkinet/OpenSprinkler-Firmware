"""Configuration-to-plan dry run. Pure orchestration, no dispatch or persistence.

Consumes an exported UI draft and an explicit reconciled runtime snapshot.
Future service times are assumptions, not reservations solved by this increment.
"""
from dataclasses import asdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .calendar import normalize, resolve_calendar
from .solar import night_intervals
from .fixed import fixed_plan
from .draft import InputErrors, Validator, compile_draft, quantity, shape, text
from .model import integer, number
from .planner import ETPeriod, Window, plan


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('expected an ISO timestamp with UTC offset')
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None or dt.utcoffset() is None or dt.microsecond:
        raise ValueError('timestamp must have a UTC offset and whole seconds')
    return integer(int(dt.timestamp()))


def sid_list(values):
    if not isinstance(values, list):
        raise ValueError('expected a list of zero-based station IDs')
    for value in values:
        integer(value)
    if len(set(values)) != len(values):
        raise ValueError('duplicate station ID')
    return values


def weather_periods(weather):
    shape(weather, ('source', 'classification', 'units', 'distribution', 'periods'))
    text(weather.get('source'))
    if weather.get('classification') not in ('forecast', 'estimate'):
        raise ValueError('planning weather must be classified forecast or estimate')
    if weather.get('distribution') != 'uniform_within_period':
        raise ValueError('explicit uniform_within_period ET assumption required')
    if weather.get('units') not in ('mm', 'in'):
        raise ValueError('ETo units must be mm or in')
    factor = number('25.4') if weather['units'] == 'in' else number(1)
    raw = weather.get('periods')
    if not isinstance(raw, list) or not raw:
        raise ValueError('dated ETo periods are required')
    result = []
    for item in raw:
        shape(item, ('start', 'end', 'eto'))
        period = ETPeriod(timestamp(item.get('start')), timestamp(item.get('end')),
                          quantity(item.get('eto'), zero=True)*factor)
        if result and period.start != result[-1].end:
            raise ValueError('weather periods must be contiguous, ordered and nonoverlapping')
        result.append(period)
    return result


def clip_weather(periods, start, end):
    if periods[0].start > start or periods[-1].end < end:
        raise ValueError('dated ETo coverage does not span the next-service horizon')
    return [ETPeriod(max(start, p.start), min(end, p.end),
             number(p.eto_mm)*(min(end, p.end)-max(start, p.start))/(p.end-p.start))
            for p in periods if p.start < end and p.end > start]


def audit(draft):
    config = compile_draft(draft)
    return dict(schema_version=1, mode='offline_no_controller_io',
                status='configuration_valid', enabled_programs=len(config.zones)+len(config.fixed),
                disabled_programs=list(config.disabled),
                runtime_required=['as_of and named timezone', 'eligible station IDs',
                    'resource limits and timing margins', 'reconciled per-valve depletion and soak readiness',
                    'dated ETo estimates', 'future service assumptions'],
                automatic_watering_enabled=False)


def dry_run(draft, runtime):
    config = compile_draft(draft)
    v = Validator()
    v.get('runtime', lambda: shape(runtime, ('schema_version', 'as_of', 'timezone',
          'calendar_through', 'eligible_station_sids', 'resource', 'states',
          'next_service', 'weather', 'promoted_sids', 'location')))
    v.finish()
    if type(runtime.get('schema_version')) is not int or runtime['schema_version'] != 1:
        raise InputErrors([dict(path='runtime.schema_version', message='unsupported runtime version')])
    now = v.get('runtime.as_of', lambda: timestamp(runtime.get('as_of')))
    tz = v.get('runtime.timezone', lambda: ZoneInfo(text(runtime.get('timezone'))))
    through = v.get('runtime.calendar_through', lambda: date.fromisoformat(runtime.get('calendar_through')))
    eligible = v.get('runtime.eligible_station_sids', lambda: sid_list(runtime.get('eligible_station_sids')))
    resource = v.get('runtime.resource', lambda: shape(runtime.get('resource'),
                            ('max_active_valves', 'transition_seconds', 'closing_margin_seconds')))
    transition = margin = None
    if resource is not None:
        if type(resource.get('max_active_valves')) is not int or resource['max_active_valves'] != 1:
            v.issues.append(dict(path='runtime.resource.max_active_valves', message='only one shared active valve is supported'))
        transition = v.get('runtime.resource.transition_seconds', lambda: integer(resource.get('transition_seconds')))
        margin = v.get('runtime.resource.closing_margin_seconds', lambda: integer(resource.get('closing_margin_seconds')))
    promoted = v.get('runtime.promoted_sids', lambda: sid_list(runtime.get('promoted_sids', [])))
    soil_sids = {z.station-1 for z in config.zones}
    active_sids = soil_sids | {p.sid for p in config.fixed}
    if eligible is not None and not active_sids <= set(eligible):
        v.issues.append(dict(path='runtime.eligible_station_sids', message='an enabled program references an unavailable, disabled, master or bundled valve'))
    if promoted is not None:
        if not set(promoted) <= soil_sids or (promoted and config.shortage != 'promote_next'):
            v.issues.append(dict(path='runtime.promoted_sids', message='promotion requires an enabled valve and promote_next policy'))
    v.finish()
    first = datetime.fromtimestamp(now, tz).date()
    if through < first or (through-first).days > 366:
        raise InputErrors([dict(path='runtime.calendar_through', message='calendar horizon must be within 366 days after as_of')])
    intervals = normalize([interval for days, start, end in config.rules
        for interval in resolve_calendar(runtime['timezone'], first.isoformat(), through.isoformat(),
                                          days, [(start, end)], config.excluded)])
    # v3 makes an empty calendar unrestricted. Preserve v1/v2 fail-closed drafts.
    if not config.rules and draft['version'] >= 3:
        intervals = []
        day = first
        while day <= through:
            intervals.extend(resolve_calendar(runtime['timezone'], day.isoformat(), day.isoformat(),
                                               range(7), [(0, 1440)], config.excluded))
            day += timedelta(days=1)
    calendar_margin = margin if config.rules or draft['version'] < 3 else 0
    zone_intervals = {}
    nights = None
    if 'night' in config.hours.values():
        nights = v.get('runtime.location', lambda: night_intervals(runtime['timezone'], first, through, runtime.get('location')))
        v.finish()
    for zone in (*config.zones, *config.fixed):
        hours = config.hours[zone.id]
        if hours == 'night':
            daily = nights
        elif hours is None:
            daily = intervals
        else:
            daily = resolve_calendar(runtime['timezone'], first.isoformat(), through.isoformat(), range(7), [hours])
        # Keep planning-day boundaries; do not merge unrestricted consecutive days.
        zone_intervals[zone.id] = [(max(a, c), min(b-calendar_margin, d))
            for a, b in intervals for c, d in daily if max(a, c) < min(b-calendar_margin, d)]
    planning_intervals = intervals
    if not config.rules and draft['version'] >= 3:
        # Night intervals stay continuous across midnight. A fully unrestricted
        # schedule uses a rolling 24-hour planning horizon rather than infinity.
        zone_intervals = {z: normalize(items) for z, items in zone_intervals.items()}
        planning_intervals = normalize([item for items in zone_intervals.values() for item in items])
    current = next(((a, b) for a, b in planning_intervals if a <= now < b-margin), None)
    if current and not config.rules and draft['version'] >= 3:
        current = (current[0], min(current[1], now+86400))
    result = dict(schema_version=1, mode='offline_no_controller_io',
        automatic_watering_enabled=False, as_of=runtime['as_of'], timezone=runtime['timezone'],
        disabled_programs=list(config.disabled),
        assumptions=['one shared active valve', 'no legacy weather-percentage scaling',
            'uniform ETo within each supplied period', 'no forecast rain credit',
            'caller-supplied next service times; future capacity is not verified',
            'depletion snapshot is already reconciled through as_of',
            'plans are not delivered water; no ledger or promotion state is changed',
            'runtime-mode full events assume refill only upon verified complete delivery',
            'fixed full-event amounts are never multiplied by weather demand',
            'fixed-time slots reserved before flexible soil work; groups resolve fixed-time conflicts',
            'fixed-time misting receives no soil-water credit',
            'fixed times preview the next 24 hours; no catch-up or automatic next-run promotion'],
        legal_windows=[dict(start=a, end=b) for a, b in intervals])
    fixed_end = min(now+86400, int(datetime.combine(through+timedelta(days=1), datetime.min.time(), tz).timestamp()))
    fixed_allowed = {key: [(a, b-max(0, margin-calendar_margin)) for a, b in values]
                     for key, values in zone_intervals.items()}
    fixed_output, reserved = fixed_plan(config, runtime, now, fixed_end, tz, fixed_allowed, transition, timestamp)
    for zone in config.zones:
        # fixed_plan subtracts same-valve soak periods from these intervals.
        zone_intervals[zone.id] = fixed_allowed[zone.id]
    result['fixed_decisions'] = fixed_output
    if not config.zones:
        return dict(result, status='conditional_plan' if config.fixed else 'no_enabled_programs', decisions=[])
    if current is None:
        following = next((a for a, b in planning_intervals if a > now and b-a > margin), None)
        return dict(result, status='outside_watering_window', next_opening=following, decisions=[])
    window = Window(f'window:{current[0]}:{current[1]}', now, current[1], transition, margin)
    periods = v.get('runtime.weather', lambda: weather_periods(runtime.get('weather')))
    states_raw = v.get('runtime.states', lambda: shape(runtime.get('states'), [str(s) for s in active_sids]))
    future_raw = v.get('runtime.next_service', lambda: shape(runtime.get('next_service'), [str(s) for s in active_sids]))
    states, ready, horizons, projections = {}, {}, {}, {}
    for zone in config.zones:
        sid = str(zone.station-1)
        path = f'runtime.states.{sid}'
        if states_raw is not None:
            state = v.get(path, lambda: shape(states_raw.get(sid), ('at', 'depletion_mm', 'unresolved', 'ready_at')))
            if state is not None:
                at = v.get(path+'.at', lambda: timestamp(state.get('at')))
                if at is not None and at != now:
                    v.issues.append(dict(path=path+'.at', message='snapshot must be reconciled exactly through as_of'))
                d = v.get(path+'.depletion_mm', lambda: quantity(state.get('depletion_mm'), zero=True,
                                                               maximum=config.profiles[zone.profile_id].capacity))
                ready[zone.id] = v.get(path+'.ready_at', lambda: timestamp(state.get('ready_at')))
                unresolved = state.get('unresolved')
                if not isinstance(unresolved, list) or any(not isinstance(x, str) or not x.strip() for x in unresolved):
                    v.issues.append(dict(path=path+'.unresolved', message='explicit list of unresolved input/delivery IDs required'))
                states[zone.id] = dict(depletion_mm=d, unresolved=unresolved)
        if future_raw is not None:
            path = f'runtime.next_service.{sid}'
            future = v.get(path, lambda: timestamp(future_raw.get(sid)))
            if future is not None:
                if not any(future >= current[1] and a <= future and future+zone.minimum_pulse_seconds <= b-(margin-calendar_margin)
                           for a, b in zone_intervals[zone.id]):
                    v.issues.append(dict(path=path, message='service must fit at least a minimum pulse in a later legal window within program permitted hours'))
                if ready.get(zone.id) is not None and future < ready[zone.id]:
                    v.issues.append(dict(path=path, message='service precedes valve soak readiness'))
                horizons[zone.id] = future
                if periods is not None:
                    projections[zone.id] = v.get(path, lambda: clip_weather(periods, now, future))
    v.finish()
    decisions = plan(window, config.zones, config.profiles, config.groups, states,
                     projections, horizons, promoted={f'sid:{sid}' for sid in promoted}, ready_at=ready, allowed=zone_intervals, reserved=reserved)
    output = []
    for decision in decisions:
        zone = next(z for z in config.zones if z.id == decision['zone_id'])
        pulses = [dict(asdict(p), sid=zone.station-1, duration_seconds=p.end-p.start,
                       pulse_id=f'{window.id}/{zone.id}/{i+1}',
                       local_start=datetime.fromtimestamp(p.start, tz).isoformat(),
                       local_end=datetime.fromtimestamp(p.end, tz).isoformat())
                  for i, p in enumerate(decision['pulses'])]
        output.append(dict(decision, sid=zone.station-1, program_name=config.names[zone.id],
                           pulses=pulses, horizon_basis='supplied_not_capacity_verified',
                           elapsed_seconds=pulses[-1]['end']-pulses[0]['start'] if pulses else 0))
    # Fraction stays internal; report values are JSON numbers.
    return dict(result, status='conditional_plan', window=asdict(window), decisions=output,
                depletion_at_start_mm={z: float(s['depletion_mm']) for z, s in states.items()},
                weather_source=runtime['weather']['source'],
                promotion_candidates=[d['sid'] for d in output if d['promotion_eligible']]
                    if config.shortage == 'promote_next' else [])
