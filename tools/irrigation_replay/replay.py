"""Fixture-only command line. Produces plans, never valve commands."""
import json
from dataclasses import asdict
from .model import Profile, Zone, Observation, Ledger
from .planner import Window, ETPeriod, Pulse, Promotions, plan


def unique(items, factory):
    result = {}
    for item in items:
        value = factory(**item)
        if value.id in result:
            raise ValueError('duplicate configuration ID')
        result[value.id] = value
    return result


def replay(fixture):
    if fixture.get('schema_version') != 1:
        raise ValueError('unsupported fixture schema')
    profiles = unique(fixture['profiles'], Profile)
    zones = unique(fixture['zones'], Zone)
    ledger = Ledger(profiles, zones, fixture['initial_depletion_mm'])
    for item in fixture.get('observations', []):
        ledger.put(Observation(**item))
    promotions = Promotions(fixture.get('promotion_policy', 'report_only'))
    reports = []
    last_end = -1
    seen = set()
    for item in fixture['windows']:
        window = Window(**item['window'])
        if window.id in seen or window.start < last_end:
            raise ValueError('replay windows must be unique and chronological/nonoverlapping')
        seen.add(window.id)
        last_end = window.end
        states = {z: ledger.state(z, window.start) for z in zones}
        periods = {z: [ETPeriod(**p) for p in data] for z, data in item.get('projections', {}).items()}
        decisions = plan(window, list(zones.values()), profiles, fixture['groups'],
                         states, periods, item.get('next_service', {}),
                         reserved=[Pulse(**p) for p in item.get('reservations', [])],
                         promoted=promotions.active(window.id),
                         ready_at=item.get('ready_at', {}))
        promotions.close(window.id, decisions, item.get('next_eligible_window', {}))
        output = []
        for decision in decisions:
            output.append({**decision, 'pulses': [dict(asdict(p),
                pulse_id=f'{window.id}/{decision["zone_id"]}/{i+1}')
                for i, p in enumerate(decision['pulses'])]})
        reports.append(dict(window=asdict(window), ledger_at_start=states,
                            decisions=output, promotions=promotions.checkpoint()))
        # Exercise checkpoint roundtrip between windows. Plans are deliberately
        # NOT converted to observed delivery. Fixture observations are explicit.
        ledger.restore(json.loads(json.dumps(ledger.checkpoint())))
        promotions = Promotions.restore(json.loads(json.dumps(promotions.checkpoint())))
    return dict(schema_version=1, mode='offline_no_controller_io',
                assumptions=['one active valve resource', 'explicit next-service times',
                             'piecewise-constant projected ET', 'no forecast rain credit',
                             'plans are not delivery records', 'initial profile held fixed'],
                windows=reports, ledger_at_end={z: ledger.state(z, max(0, last_end)) for z in zones})
