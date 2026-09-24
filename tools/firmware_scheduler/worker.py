"""One-shot planner invoked by OpenSprinkler's Linux firmware.

The parent owns configuration, durable execution records and the station queue.
This process can query the configured OS weather service; it cannot operate valves.
UTC is used throughout; OS local-epoch time is converted at the C++ queue boundary.
"""
import copy
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.irrigation_replay.draft import compile_draft
from tools.irrigation_replay.engine import dry_run
from tools.irrigation_replay.service import legal_intervals

TEST_PROFILE = dict(capacity=100, roots=.3, depletion=50, crop=1, rain=80)


def iso(at):
    return datetime.fromtimestamp(at, timezone.utc).isoformat()


def finite(value, minimum=0, maximum=1000):
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError('Missing or invalid numeric input')
    return float(value)


def observation(payload, tz, now):
    if payload.get('v') != 1 or payload.get('u') != 'us':
        raise ValueError('Unsupported OS weather schema or units')
    h = payload.get('h', {})
    at = h.get('at')
    if type(at) is not int:
        raise ValueError('Historical weather has no dated period')
    day = datetime.fromtimestamp(at, tz)
    if (day.hour, day.minute, day.second) != (0, 0, 0):
        raise ValueError('Historical period is not site local midnight')
    end = int((day + timedelta(days=1)).timestamp())
    if end > now or now - end > 2*86400:
        raise ValueError('Historical OS weather is stale or future-dated')
    return dict(start=at, end=end, eto_mm=finite(h.get('eto'), maximum=4)*25.4,
                rain_mm=finite(h.get('p'), maximum=40)*25.4,
                provider=str(payload.get('wp', 'unknown')), fetched_at=now)


def weather_update(request, tz, now, fetch=urlopen):
    weather = copy.deepcopy(request.get('weather') or {})
    weather.setdefault('days', {})
    if now - weather.get('last_attempt', 0) < (900 if weather.get('error') else 3600):
        return weather
    weather['last_attempt'] = now
    try:
        source = request['source']
        host = source['host']
        if '://' not in host:
            host = 'https://' + host
        parsed = urlsplit(host)
        if parsed.scheme not in ('https', 'http') or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError('Invalid configured OS weather service')
        # Firmware string options store the contents of wto without outer braces.
        wto = source['options']
        if isinstance(wto, dict):
            wto = json.dumps(wto, separators=(',', ':'))[1:-1]
        query = urlencode(dict(loc=source['location'], scope='h', wto=wto))
        with fetch(host.rstrip('/') + '/weatherSensorData?' + query, timeout=8) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError('OS weather response too large')
        item = observation(json.loads(raw), tz, now)
        weather['days'][str(item['start'])] = item
        weather['error'] = None
    except Exception as exc:
        # Never print a URL: it can contain a private location/provider key.
        weather['error'] = 'OS weather unavailable: ' + type(exc).__name__
    return weather


def daily_periods(weather, tz, start, end, now):
    """Observed past days; today's ETo is an explicitly labeled persistence estimate.

    Rain is only credited for completed, observed days. Replaying from the initial
    anchor reconciles yesterday's estimate with its new observation without
    counting rain or ETo twice. Missing complete days block soil scheduling.
    """
    day = datetime.fromtimestamp(start, tz).replace(hour=0, minute=0, second=0, microsecond=0)
    today = datetime.fromtimestamp(now, tz).date()
    latest = max(weather['days'].values(), key=lambda d: d['start'], default=None)
    if latest is None or now-latest['end'] > 2*86400:
        raise ValueError('No fresh dated OS ETo observation')
    periods = []
    while int(day.timestamp()) < end:
        a, b = int(day.timestamp()), int((day+timedelta(days=1)).timestamp())
        value = weather['days'].get(str(a))
        if value is None and day.date() < today:
            raise ValueError('Missing historical weather for '+day.date().isoformat())
        if value is None:
            value = dict(eto_mm=latest['eto_mm'], rain_mm=0)
        periods.append(dict(start=a, end=b, eto_mm=value['eto_mm'], rain_mm=value['rain_mm'],
                            estimated=day.date() >= today))
        day += timedelta(days=1)
    return periods


def reconcile(sid, initial, anchor, at, profile, periods, delivery):
    balance = finite(initial, maximum=float(profile.capacity))
    cursor = anchor
    events = sorted((e for e in delivery if e['sid'] == sid and anchor <= e['at'] <= at), key=lambda e: e['at'])
    def accrue(a, b, value):
        for p in periods:
            seconds = max(0, min(b, p['end'])-max(a, p['start']))
            net = p['eto_mm']*float(profile.crop_coefficient)-p['rain_mm']*float(profile.effective_rain)
            value = max(0, min(float(profile.capacity), value+net*seconds/(p['end']-p['start'])))
        return value
    for event in events:
        balance = accrue(cursor, event['at'], balance)
        if event['kind'] == 'refill':
            balance = 0
        elif event['kind'] == 'depth':
            balance = max(0, balance-finite(event['mm']))
        cursor = event['at']
    return accrue(cursor, at, balance)


def calculate(request, weather, now):
    site, draft = request['site'], copy.deepcopy(request['draft'])
    tz = ZoneInfo(site['timezone'])
    if int(datetime.fromtimestamp(now, tz).utcoffset().total_seconds()) != request['offset']:
        raise ValueError('Controller timezone offset differs from the named site timezone')
    provisional = site.get('provisional') is True
    if provisional:
        for key, value in TEST_PROFILE.items():
            if draft.setdefault('profile', {}).get(key) in ('', None):
                draft['profile'][key] = value
    # Incomplete soil inputs do not prevent an independent fixed-time program.
    soil_error = None
    try:
        config = compile_draft(draft)
    except ValueError as exc:
        soil_error = str(exc)
        for p in draft['programs']:
            if p.get('scheduleMode') not in ('fixed', 'reservation'):
                p['enabled'] = False
        config = compile_draft(draft)  # Still reject malformed fixed/structural input.
    if config.shortage != 'report_only':
        raise ValueError('Firmware currently supports report-only shortage policy; promotion is not yet implemented')
    anchor = request['anchor']
    if anchor > now:
        raise ValueError('Clock precedes the initial soil-state timestamp')
    balances, unresolved, future = {}, {}, {}
    allowed, last = legal_intervals(draft, config, now, tz, request.get('location'), max(1, request['transition']))
    for zone in config.zones:
        sid = str(zone.station-1)
        profile = config.profiles[zone.profile_id]
        try:
            initial = site.get('initial', {}).get(sid)
            if initial is None and provisional:
                initial = float(profile.threshold)
            periods = daily_periods(weather, tz, anchor, now, now)
            balances[sid] = reconcile(zone.station-1, initial, anchor, now, profile, periods, request.get('delivery', []))
        except ValueError as exc:
            balances[sid] = 0
            unresolved[sid] = [str(exc)]
        candidate = next((max(now+86400, a) for a, b in allowed[zone.id]
                          if max(now+86400, a)+zone.minimum_pulse_seconds <= b), None)
        if candidate is None:
            raise ValueError('No future legal service opportunity in eight days')
        future[sid] = candidate
    horizon = max([now+86400, *future.values()])
    latest = max(weather.get('days', {}).values(), key=lambda d: d['start'], default=None)
    if latest is None or now-latest['end'] > 2*86400:
        for zone in config.zones:
            unresolved[str(zone.station-1)] = ['No fresh dated OS ETo observation']
    source = 'OS '+(latest['provider'] if latest else 'weather unavailable')
    sids = sorted({z.station-1 for z in config.zones} | {p.sid for p in config.fixed})
    runtime = dict(schema_version=1, as_of=iso(now), timezone=tz.key,
        calendar_through=last.isoformat(), eligible_station_sids=request['eligible'],
        resource=dict(max_active_valves=1, transition_seconds=max(1, request['transition']), closing_margin_seconds=0),
        states={str(sid): dict(at=iso(now), depletion_mm=balances.get(str(sid), 0),
            unresolved=request.get('unresolved', {}).get(str(sid), []),
            ready_at=iso(max(now, request.get('ready', {}).get(str(sid), now)))) for sid in sids},
        soil_input_issues=unresolved, next_service={sid: iso(at) for sid, at in future.items()},
        weather=dict(source=source+'; future ETo estimated from latest observed day; no forecast rain credit',
            classification='estimate', units='mm', distribution='uniform_within_period',
            periods=[dict(start=iso(now), end=iso(horizon), eto=(latest['eto_mm'] if latest else 0)*(horizon-now)/86400)]))
    if request.get('location') is not None:
        runtime['location'] = request['location']
    # Soil input problems must not block misting on that same physical valve.
    report = dry_run(draft, runtime)
    events = []
    for d in report['decisions'] + report['fixed_decisions']:
        if not d['pulses']:
            continue
        fixed = d.get('schedule_mode') == 'fixed'
        zone = next((z for z in config.zones if z.station-1 == d['sid']), None)
        program = next((p for p in config.fixed if p.id == d.get('program_id')), None)
        event_id = d['pulses'][0]['pulse_id'].rsplit('/', 1)[0]
        events.append(dict(id=event_id, sid=d['sid'], name=d['program_name'],
            mode='fixed' if fixed else d['watering_mode'], status='pending',
            soak=program.soak if fixed else zone.soak_seconds,
            net_rate=0 if fixed or zone.watering_mode == 'runtime' else float(zone.net_rate),
            planned_seconds=d['allocated_seconds'],
            pulses=[dict(start=p['start'], end=p['end'], status='pending') for p in d['pulses']]))
    if sum(len(e['pulses']) for e in events) > 4096:
        raise ValueError('Plan exceeds firmware pulse limit')
    return dict(events=events, balances=balances, soil_error=soil_error, unresolved=unresolved,
        provisional=provisional, profile=draft['profile'], weather_source=runtime['weather']['source'],
        report=report, planned_at=now)


def main():
    source, target = map(Path, sys.argv[1:3])
    request = json.loads(source.read_text())
    result = dict(revision=request['revision'])
    try:
        tz = ZoneInfo(request['site']['timezone'])
        result['weather'] = weather_update(request, tz, int(time.time()))
        # A short lead permits the firmware to install the first queue item.
        planned_at=max(int(time.time())+3,request.get('last_off',0)+max(1,request.get('transition',5)))
        result.update(calculate(request, result['weather'], planned_at))
    except Exception as exc:
        result['error'] = str(exc)
    temp = target.with_suffix('.tmp')
    with temp.open('w') as stream:
        json.dump(result, stream, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(target)


if __name__ == '__main__':
    main()
