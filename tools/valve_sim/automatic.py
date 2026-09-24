"""Persistent automatic laboratory simulation. Never sends controller commands.

The sole output is the non-forwarding loopback fake-valve receiver. Simulated
clock/soil/weather are explicit, and this is not production firmware dispatch.
"""
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from zoneinfo import ZoneInfo
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

from tools.irrigation_replay.draft import compile_draft
from tools.irrigation_replay.engine import dry_run
from tools.irrigation_replay.service import legal_intervals as service_intervals

TEST_PROFILE = dict(capacity=100, roots=.3, depletion=50, crop=1, rain=80)


def atomic(path, value):
    temp = path.with_suffix('.tmp')
    with temp.open('w') as stream:
        json.dump(value, stream, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Receiver:
    def __init__(self):
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(self, path):
        with self.opener.open(Request('http://127.0.0.1:18080/'+path), timeout=3) as response:
            return json.load(response)

    def status(self):
        result = self.request('status')
        if result.get('service') != 'opensprinkler-valve-simulator':
            raise ValueError('Expected the loopback fake-valve receiver')
        return result

    def set(self, sid, enabled):
        if type(sid) is not int or not 0 <= sid < 200:
            raise ValueError('Invalid simulated valve')
        result = self.request(f'sim/zone{sid+1}/' + ('on' if enabled else 'off'))
        if result.get('simulated') is not True or result.get('result') != 1:
            raise ValueError('Simulator did not acknowledge command')
        return result


def effective_draft(draft):
    result = copy.deepcopy(draft)
    # A separate effective copy; never overwrite the browser's calibration.
    source = result.setdefault('profile', {})
    assumed = []
    for key, value in TEST_PROFILE.items():
        if source.get(key) in (None, ''):
            source[key] = value
            assumed.append(key)
    config = compile_draft(result)
    if config.shortage != 'report_only':
        raise ValueError('Automatic simulation currently requires Report missed watering only; promotion persistence is not implemented')
    return result, config, assumed


def legal_intervals(draft, config, now, tz, location):
    return service_intervals(draft, config, now, tz, location, transition=5)


class Simulation:
    def __init__(self, directory, receiver=None, timezone_name='Europe/Paris', speed=60, location=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory/'state.json'
        self.receiver = receiver or Receiver()
        self.tz = ZoneInfo(timezone_name)
        self.speed = speed
        self.location = location
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.state = json.loads(self.path.read_text()) if self.path.exists() else dict(
            version=1, clock=int(time.time()), running=False, draft=None, balances={},
            events=[], records=[], next_plan=0, plan=None, generation=0, error=None)
        self.state.setdefault('ready', {})
        self.recovered = False
        self.last_checkpoint = time.monotonic()

    def persist(self):
        atomic(self.path, self.state)
        self.last_checkpoint = time.monotonic()

    def record(self, kind, **values):
        item = dict(kind=kind, at=self.state['clock'], real_at=time.time(), **values)
        self.state['record_sequence'] = self.state.get('record_sequence',0)+1
        self.state['records'].append(item)
        self.state['records'] = self.state['records'][-500:]
        with (self.directory/'history.jsonl').open('a') as stream:
            stream.write(json.dumps(item)+'\n')

    def soak(self, sid):
        if not self.state.get('effective'): return 0
        config=compile_draft(self.state['effective'])
        return max([0]+[z.soak_seconds for z in config.zones if z.station-1==sid]+[p.soak for p in config.fixed if p.sid==sid])

    def recover(self):
        status = self.receiver.status()
        for name, on in status['states'].items():
            if on:
                if not name.startswith('zone') or not name[4:].isdigit():
                    raise ValueError('An unrelated simulated valve is active')
                self.receiver.set(int(name[4:])-1, False)
        for event in self.state['events']:
            if event['status'] == 'running':
                event['status'] = 'interrupted'
                self.state['ready'][str(event['sid'])] = self.state['clock']+self.soak(event['sid'])
                for pulse in event['pulses']:
                    if pulse['status'] != 'done': pulse['status'] = 'cancelled'
                self.record('interrupted', name=event['name'], sid=event['sid'], detail='Restart: no refill credited')
        self.receiver_session = status['session']
        self.recovered = True
        self.persist()

    def configure(self, draft):
        effective, config, assumed = effective_draft(draft)
        digest = hashlib.sha256(json.dumps(draft, sort_keys=True).encode()).hexdigest()
        with self.lock:
            status = self.receiver.status()
            for p in draft['programs']:
                if p.get('enabled') and f"zone{p['sid']+1}" not in status['states']:
                    raise ValueError('A program references a missing simulated valve')
            if digest == self.state.get('config_hash'):
                return self.snapshot()
            self.pause('Configuration changed')
            old_balances = self.state['balances']
            balances = {}
            for zone in config.zones:
                profile = config.profiles[zone.profile_id]
                balances[str(zone.station-1)] = min(float(profile.capacity), old_balances.get(str(zone.station-1), float(profile.threshold)))
            self.state.update(draft=copy.deepcopy(draft), effective=effective, assumed_profile_fields=assumed,
                config_hash=digest, balances=balances, events=[], next_plan=0, plan=None,
                generation=self.state['generation']+1, error=None, running=True)
            self.record('configuration', detail='Applied saved browser draft to simulation; initial soil depletion is a test assumption')
            self.persist()
            return self.snapshot()

    def pause(self, reason='Paused by user'):
        for event in self.state['events']:
            if event['status'] == 'running':
                for pulse in event['pulses']:
                    if pulse['status'] == 'on':
                        self.receiver.set(event['sid'], False)
                event['status'] = 'interrupted'
                self.state['ready'][str(event['sid'])] = self.state['clock']+self.soak(event['sid'])
                for pulse in event['pulses']:
                    if pulse['status'] != 'done': pulse['status'] = 'cancelled'
                self.record('interrupted', name=event['name'], sid=event['sid'], detail=reason+'; no refill credited')
        self.state['running'] = False
        self.persist()

    def control(self, action):
        with self.lock:
            if action == 'pause':
                self.pause()
            elif action == 'resume':
                if not self.state['draft']: raise ValueError('Apply a saved draft first')
                self.recovered = False
                self.recover()
                self.state.update(running=True, error=None)
                self.record('resumed')
                self.persist()
            else:
                raise ValueError('Unknown simulation action')
            return self.snapshot()

    def make_plan(self):
        now = self.state['clock']
        draft = self.state['effective']
        config = compile_draft(draft)
        allowed, last = legal_intervals(draft, config, now, self.tz, self.location)
        future = {}
        for zone in config.zones:
            candidate = next((max(now+86400,a) for a,b in allowed[zone.id]
                              if max(now+86400,a)+zone.minimum_pulse_seconds <= b), None)
            if candidate is None:
                raise ValueError(f'No future service opportunity for {config.names[zone.id]} in 8 days')
            future[str(zone.station-1)] = candidate
        iso = lambda stamp: datetime.fromtimestamp(stamp, timezone.utc).isoformat()
        sids = sorted({z.station-1 for z in config.zones} | {p.sid for p in config.fixed})
        horizon = max([now+86400, *future.values()])
        runtime = dict(schema_version=1, as_of=iso(now), timezone=self.tz.key,
            calendar_through=last.isoformat(), eligible_station_sids=sids,
            resource=dict(max_active_valves=1, transition_seconds=5, closing_margin_seconds=0),
            states={str(sid): dict(at=iso(now), depletion_mm=self.state['balances'].get(str(sid),0),
                                  unresolved=[], ready_at=iso(max(now,self.state['ready'].get(str(sid),now)))) for sid in sids},
            next_service={sid:iso(stamp) for sid,stamp in future.items()},
            weather=dict(source='SYNTHETIC: 4 mm ETo/day, no rain; not live weather', classification='estimate',
                         units='mm', distribution='uniform_within_period',
                         periods=[dict(start=iso(now),end=iso(horizon),eto=4*(horizon-now)/86400)]))
        if self.location is not None: runtime['location'] = self.location
        report = dry_run(draft, runtime)
        existing = {e['id']:e for e in self.state['events']}
        events = []
        for d in report['decisions']+report.get('fixed_decisions',[]):
            if not d['pulses']:
                self.record('decision', name=d['program_name'], sid=d['sid'], detail=d['reason'])
                continue
            fixed = d.get('schedule_mode') == 'fixed'
            event_id = d['pulses'][0]['pulse_id'].rsplit('/',1)[0]
            if event_id in existing:
                events.append(existing[event_id]); continue
            event = dict(id=event_id, sid=d['sid'], name=d['program_name'], fixed=fixed,
                mode='fixed' if fixed else d['watering_mode'], status='pending', credited=False,
                planned_seconds=d['allocated_seconds'], pulses=[dict(p,status='pending') for p in d['pulses']])
            events.append(event)
            self.record('planned', name=event['name'], sid=event['sid'], seconds=event['planned_seconds'])
        # Keep completed/interrupted identity while its occurrence can reappear.
        keep = [e for e in self.state['events'] if e['status'] in ('complete','interrupted') and max(p['end'] for p in e['pulses']) >= now-86400]
        by_id = {e['id']:e for e in keep+events}
        self.state['events'] = list(by_id.values())
        boundary = report.get('window',{}).get('end',now+86400)
        if report.get('next_opening') is not None: boundary = min(boundary,report['next_opening'])
        self.state['next_plan'] = max(now+1,boundary)
        self.state['plan'] = dict(at=now,status=report['status'],next_plan=self.state['next_plan'],
            decisions=[dict(name=d['program_name'],sid=d['sid'],status=d['status'],reason=d['reason'],
                            seconds=d.get('allocated_seconds',0)) for d in report['decisions']+report.get('fixed_decisions',[])])
        self.persist()

    def next_boundary(self):
        times = [self.state['next_plan']]
        for e in self.state['events']:
            if e['status'] in ('complete','interrupted'): continue
            for p in e['pulses']:
                if p['status'] == 'pending': times.append(p['start'])
                elif p['status'] == 'on': times.append(p['end'])
        return max(self.state['clock'], min(times))

    def advance(self, target):
        """One virtual clock step, capped at a planned edge by the live loop."""
        with self.lock:
            if not self.recovered: self.recover()
            if not self.state['running']: return
            before_sequence = self.state.get('record_sequence',0)
            status = self.receiver.status()
            if status['session'] != self.receiver_session:
                raise ValueError('Valve simulator restarted; pause and reconcile before resuming')
            expected = {f"zone{e['sid']+1}" for e in self.state['events'] for p in e['pulses'] if p['status']=='on'}
            actual = {name for name,on in status['states'].items() if on}
            if actual != expected:
                raise ValueError('Simulated valve state changed outside this runner')
            now = self.state['clock']
            target = max(now, int(target))
            config = compile_draft(self.state['effective'])
            for zone in config.zones:
                profile = config.profiles[zone.profile_id]; sid=str(zone.station-1)
                self.state['balances'][sid] = min(float(profile.capacity), self.state['balances'][sid]+4*float(profile.crop_coefficient)*(target-now)/86400)
            self.state['clock'] = target
            # End first: exact adjacent events cannot overlap.
            for e in self.state['events']:
                if e['status'] != 'running': continue
                for p in e['pulses']:
                    if p['status'] == 'on' and p['end'] <= target:
                        self.receiver.set(e['sid'],False)
                        p['status']='done'
                        soak = self.soak(e['sid'])
                        self.state['ready'][str(e['sid'])] = target+soak
                        self.record('off',name=e['name'],sid=e['sid'],seconds=p['duration_seconds'])
                        if e['mode'] not in ('runtime','fixed'):
                            zone=next(z for z in config.zones if z.station-1==e['sid'])
                            key=str(e['sid'])
                            self.state['balances'][key]=max(0,self.state['balances'][key]-float(zone.net_rate)*p['duration_seconds'])
                if all(p['status']=='done' for p in e['pulses']):
                    if e['mode']=='runtime' and not e['credited']:
                        self.state['balances'][str(e['sid'])]=0
                        e['credited']=True
                    e['status']='complete'
                    self.record('completed',name=e['name'],sid=e['sid'],seconds=e['planned_seconds'],refill=e['credited'])
                    self.persist()
            if target >= self.state['next_plan']:
                running=[e for e in self.state['events'] if e['status']=='running']
                if running:
                    self.state['next_plan']=max(p['end'] for e in running for p in e['pulses'])
                else: self.make_plan()
            for e in self.state['events']:
                if e['status'] not in ('pending','running'): continue
                for p in e['pulses']:
                    if p['status']=='pending' and p['start'] <= target:
                        if target != p['start']:
                            e['status']='interrupted'
                            self.record('skipped',name=e['name'],sid=e['sid'],detail='Missed exact simulation start; no catch-up')
                            break
                        if target < self.state['ready'].get(str(e['sid']),0):
                            raise ValueError('Simulated valve soak has not elapsed')
                        if any(q['status']=='on' for other in self.state['events'] for q in other['pulses']):
                            raise ValueError('Planned valve overlap')
                        # Persist intent before I/O. A restart never replays an uncertain ON.
                        e['status']='running'; p['status']='on'; self.persist()
                        self.receiver.set(e['sid'],True)
                        self.record('on',name=e['name'],sid=e['sid'],seconds=p['duration_seconds'])
            if self.state.get('record_sequence',0) != before_sequence or time.monotonic()-self.last_checkpoint >= 10:
                self.persist()

    def snapshot(self):
        with self.lock:
            return dict(service='opensprinkler-automatic-simulation', running=self.state['running'],
                clock=self.state['clock'], local_time=datetime.fromtimestamp(self.state['clock'],self.tz).isoformat(),
                speed=self.speed, error=self.state['error'], config_hash=self.state.get('config_hash'),
                timezone=self.tz.key, profile=self.state.get('effective',{}).get('profile'),
                assumed_profile_fields=self.state.get('assumed_profile_fields',[]),
                assumptions=['SIMULATION ONLY: fake valves, no hardware or controller commands',
                    'Synthetic ETo: 4 mm/day; no rain; no live weather input',
                    'New soil balances start at the configured depletion threshold (test assumption)',
                    'Future service is an opportunity assumption, not a capacity guarantee',
                    'Clock freezes while paused or stopped; it may slow to process each event',
                    'A full completed runtime event assumes refill; misting never does'],
                balances=copy.deepcopy(self.state['balances']), plan=copy.deepcopy(self.state['plan']),
                active=[dict(sid=e['sid'],name=e['name'],until=p['end']) for e in self.state['events'] for p in e['pulses'] if p['status']=='on'],
                records=copy.deepcopy(self.state['records'][-100:]))

    def loop(self):
        previous=time.monotonic(); remainder=0
        while not self.stop.wait(.25):
            elapsed=time.monotonic()-previous; previous=time.monotonic()
            try:
                with self.lock:
                    if not self.recovered: self.recover()
                    if not self.state['running']: remainder=0; continue
                    remainder += elapsed*self.speed
                    jump=int(remainder)
                    target=min(self.state['clock']+jump,self.next_boundary())
                    remainder -= min(jump,max(0,target-self.state['clock']))
                    # Do not compress a backlog of simulated ON/OFF commands.
                    if target == self.next_boundary(): remainder=0
                    self.advance(target)
            except Exception as exc:
                with self.lock:
                    try: self.pause('Simulation fault')
                    except Exception: pass
                    self.state.update(running=False,error=str(exc))
                    self.record('error',detail=str(exc)); self.persist()
