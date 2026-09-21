"""Single-resource, single-window reference planner with explicit dry projections."""
from dataclasses import dataclass
from fractions import Fraction
from math import ceil, floor
from .model import integer, identifier, number


@dataclass(frozen=True, order=True)
class Pulse:
    start: int
    end: int
    zone_id: str

    def __post_init__(self):
        integer(self.start)
        integer(self.end)
        identifier(self.zone_id)
        if self.end <= self.start:
            raise ValueError('empty or reversed pulse')


@dataclass(frozen=True)
class Window:
    id: str
    start: int
    end: int
    transition_seconds: int = 0
    closing_margin_seconds: int = 0

    def __post_init__(self):
        identifier(self.id)
        integer(self.start)
        integer(self.end)
        integer(self.transition_seconds)
        integer(self.closing_margin_seconds)
        if self.end <= self.start or self.closing_margin_seconds >= self.end-self.start:
            raise ValueError('empty window after margin')


@dataclass(frozen=True)
class ETPeriod:
    start: int
    end: int
    eto_mm: float

    def __post_init__(self):
        integer(self.start)
        integer(self.end)
        if self.end <= self.start or number(self.eto_mm) < 0:
            raise ValueError('invalid ET period')


def validate_projection(periods, start, horizon):
    integer(horizon)
    if horizon <= start or not periods:
        raise ValueError('explicit future service horizon and ET coverage required')
    cursor = start
    for period in periods:
        if period.start != cursor:
            raise ValueError('projection gap, overlap or unordered periods')
        cursor = period.end
    if cursor != horizon:
        raise ValueError('projection must end at next-service horizon')


def free_intervals(window, reserved):
    """Subtract all reservations plus a global between-valve transition gap."""
    end = window.end - window.closing_margin_seconds
    cursor = window.start
    result = []
    for pulse in sorted(reserved):
        a = pulse.start - window.transition_seconds
        b = pulse.end + window.transition_seconds
        if a > cursor:
            result.append((cursor, min(a, end)))
        cursor = max(cursor, b)
        if cursor >= end:
            break
    if cursor < end:
        result.append((cursor, end))
    return [(a, b) for a, b in result if b > a]


def pack(zone, seconds, window, reserved=(), ready_at=None):
    """Greedy earliest feasible pulses; failure is not an optimality proof.

    Operates on a private reservation list, so failure cannot leak allocation.
    """
    integer(seconds, 1)
    if ready_at is not None:
        integer(ready_at)
    ready = max(window.start, ready_at if ready_at is not None else window.start)
    remaining = seconds
    pulses = []
    while remaining:
        chosen = None
        for a, b in free_intervals(window, [*reserved, *pulses]):
            start = max(a, ready)
            duration = min(remaining, zone.cycle_seconds, b-start)
            if 0 < remaining-duration < zone.minimum_pulse_seconds:
                duration = remaining-zone.minimum_pulse_seconds
            if duration >= zone.minimum_pulse_seconds:
                chosen = Pulse(start, start+duration, zone.id)
                break
        if chosen is None:
            return None
        pulses.append(chosen)
        remaining -= chosen.end-chosen.start
        ready = chosen.end+zone.soak_seconds
    return pulses


def project(depletion, profile, zone, periods, pulses):
    """Piecewise-linear demand/delivery; report stress even before a refill.

    Uses potential ET above RAW; excess beyond TAW remains visible rather than
    capped, for diagnostics only. No future rain is credited in this version.
    """
    points = sorted({p.start for p in periods} | {p.end for p in periods} |
                    {p.start for p in pulses} | {p.end for p in pulses})
    d = number(depletion)
    peak = d
    stress_seconds = Fraction(0)
    drainage = Fraction(0)
    for start, end in zip(points, points[1:]):
        et_rate = sum((number(p.eto_mm)*number(profile.crop_coefficient)/(p.end-p.start)
                       for p in periods if p.start <= start < p.end), Fraction(0))
        water_rate = sum((zone.net_rate for p in pulses if p.start <= start < p.end), Fraction(0))
        slope = et_rate-water_rate
        delta = slope*(end-start)
        raw_end = d+delta
        next_d = max(0, raw_end)
        if slope == 0:
            if d > profile.threshold:
                stress_seconds += end-start
        elif slope > 0:
            stress_seconds += max(0, min(Fraction(end-start),
                                          (raw_end-profile.threshold)/slope))
        else:
            stress_seconds += max(0, min(Fraction(end-start),
                                          (d-profile.threshold)/(-slope)))
        drainage += max(0, -raw_end)
        d = next_d
        peak = max(peak, d)
    return dict(end_depletion_mm=float(d), peak_depletion_mm=float(peak),
                stress_seconds=float(stress_seconds), drainage_mm=float(drainage))


def plan(window, zones, profiles, groups, states, projections, horizons,
         reserved=(), promoted=(), unmet_since=None, ready_at=None):
    """Pure plan: does not write ledger, tokens or control hardware.

    Group list is highest priority first. Explicit horizons are supplied by the
    fixture author; this function does not infer future feasible service slots.
    """
    if len(groups) != len(set(groups)) or not groups:
        raise ValueError('groups must be unique and ordered')
    for group in groups:
        identifier(group)
    if len({z.id for z in zones}) != len(zones) or len({z.station for z in zones}) != len(zones):
        raise ValueError('duplicate zone or valve/station mapping')
    ids = {z.id for z in zones}
    if not set(promoted) <= ids:
        raise ValueError('promotion references unknown zone')
    reservations = sorted(reserved)
    if any(a.end+window.transition_seconds > b.start for a, b in zip(reservations, reservations[1:])):
        raise ValueError('existing reservations violate resource capacity or transition gap')
    # External work for a managed valve needs delivery accounting, not just a
    # generic blocked interval. Reject ambiguous same-valve ownership here.
    if any(p.zone_id in ids for p in reservations):
        raise ValueError('reserved work conflicts with managed valve ownership')
    ranks = {g: i for i, g in enumerate(groups)}
    candidates = []
    for zone in zones:
        if zone.group_id not in ranks or zone.profile_id not in profiles:
            raise ValueError('unknown group/profile')
        state = states[zone.id]
        profile = profiles[zone.profile_id]
        d = number(state['depletion_mm'])
        if not 0 <= d <= profile.capacity:
            raise ValueError('depletion outside reservoir')
        periods = projections.get(zone.id, [])
        horizon = horizons.get(zone.id)
        projection_error = None
        try:
            validate_projection(periods, window.start, horizon)
            if horizon < window.end:
                raise ValueError('next service must not precede current window end')
        except (ValueError, TypeError):
            projection_error = 'missing_projection'
        total = sum((number(p.eto_mm)*number(profile.crop_coefficient) for p in periods), Fraction(0)) if not projection_error else Fraction(0)
        rank = max(0, ranks[zone.group_id] - (zone.id in promoted))
        oldest = (unmet_since or {}).get(zone.id, window.start)
        integer(oldest)
        candidates.append((rank, -(d+total)/profile.threshold, oldest, zone.id,
                           zone, profile, d, total, projection_error))
    decisions = []
    for rank, _, _, _, zone, profile, d, total, error in sorted(candidates):
        minimum = max(Fraction(0), d+total-profile.threshold)
        full_seconds = floor(d/zone.net_rate)
        min_seconds = max(zone.minimum_pulse_seconds, ceil(minimum/zone.net_rate))
        record = dict(zone_id=zone.id, configured_group=zone.group_id,
                      effective_group=groups[rank], full_refill_mm=float(d),
                      minimum_refill_mm=None if error else float(minimum), full_seconds=full_seconds,
                      minimum_seconds=None if error else min_seconds, allocated_seconds=0, allocated_mm=0.0,
                      status='skipped', reason='', pulses=[], promotion_eligible=False,
                      next_service=horizons.get(zone.id), projection=None)
        reason = None
        if not zone.enabled:
            reason = 'disabled'
        elif state := states[zone.id].get('unresolved'):
            reason = 'unresolved_observation'
            record['unresolved'] = list(state)
        elif error:
            reason = error
        elif d+total < profile.threshold:
            reason = 'not_due'
        elif minimum > d:
            reason = 'storage_horizon_infeasible'
        elif full_seconds < zone.minimum_pulse_seconds or min_seconds > full_seconds:
            reason = 'runtime_resolution_or_minimum_pulse'
        if reason is None:
            base = project(d, profile, zone, projections[zone.id], [])
            record['projection'] = base
            attempts = [('full', full_seconds)]
            if min_seconds < full_seconds:
                attempts.append(('partial', min_seconds))
            had_fit = False
            for status, seconds in attempts:
                pulses = pack(zone, seconds, window, reservations,
                              (ready_at or {}).get(zone.id))
                if pulses is None:
                    continue
                had_fit = True
                projection = project(d, profile, zone, projections[zone.id], pulses)
                # A partial must satisfy the whole modeled horizon. Full refill
                # can treat an already stressed zone but must report that stress.
                if status == 'partial' and projection['peak_depletion_mm'] > float(profile.threshold)+1e-9:
                    continue
                if projection['drainage_mm'] > 1e-9:
                    continue
                reservations.extend(pulses)
                record.update(status=status, reason='allocated', allocated_seconds=seconds,
                              allocated_mm=float(seconds*zone.net_rate), pulses=pulses,
                              projection=projection, promotion_eligible=(status == 'partial'))
                break
            else:
                available = sum(b-a for a, b in free_intervals(window, reservations))
                if had_fit:
                    record['reason'] = 'trajectory_not_sufficient'
                elif min_seconds > available:
                    record['reason'] = 'insufficient_on_time'
                    record['promotion_eligible'] = True
                else:
                    record['reason'] = 'planner_no_fit'
                    record['promotion_eligible'] = True
        else:
            record['reason'] = reason
            if not error:
                record['projection'] = project(d, profile, zone, projections[zone.id], [])
        decisions.append(record)
    return decisions


class Promotions:
    """One-rank, nonstacking tokens; finalise once at an eligible window close."""
    def __init__(self, mode='report_only'):
        if mode not in {'report_only', 'promote_next'}:
            raise ValueError('unknown promotion policy')
        self.mode = mode
        self.tokens = {}
        self.closed = set()

    def active(self, window_id):
        return {z for z, target in self.tokens.items() if target == window_id}

    def close(self, window_id, decisions, next_eligible):
        if window_id in self.closed:
            return False
        identifier(window_id)
        tokens = {z: target for z, target in self.tokens.items() if target != window_id}
        if self.mode == 'promote_next':
            for decision in decisions:
                zone = decision['zone_id']
                if decision['promotion_eligible'] and next_eligible.get(zone):
                    target = identifier(next_eligible[zone])
                    if target == window_id or target in self.closed:
                        raise ValueError('promotion must target a future eligible window')
                    tokens[zone] = target
        self.closed.add(window_id)
        self.tokens = tokens
        return True

    def checkpoint(self):
        return dict(mode=self.mode, tokens=dict(self.tokens), closed=sorted(self.closed))

    @classmethod
    def restore(cls, data):
        result = cls(data['mode'])
        result.tokens = dict(data['tokens'])
        result.closed = set(data['closed'])
        if any(target in result.closed for target in result.tokens.values()):
            raise ValueError('promotion targets a closed window')
        return result
