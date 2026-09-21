"""Validated configuration and chronological, revisable synthetic water ledger."""
from dataclasses import dataclass, asdict
from fractions import Fraction
from math import isfinite


def number(value):
    if isinstance(value, bool):
        raise ValueError('boolean is not a water quantity')
    try:
        result = Fraction(str(value))
    except (ValueError, TypeError, ZeroDivisionError) as exc:
        raise ValueError('expected finite numeric value') from exc
    try:
        finite = isfinite(float(result))
    except OverflowError as exc:
        raise ValueError('numeric value is out of range') from exc
    if not finite:
        raise ValueError('expected finite numeric value')
    return result


def integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f'expected integer >= {minimum}')
    return value


def identifier(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('identifier must be a nonempty string')
    return value


@dataclass(frozen=True)
class Profile:
    id: str
    capacity_mm_per_m: float
    root_depth_m: float
    allowed_depletion: float
    crop_coefficient: float = 1
    effective_rain: float = 1
    version: int = 1

    def __post_init__(self):
        identifier(self.id)
        integer(self.version, 1)
        if number(self.capacity_mm_per_m) <= 0 or number(self.root_depth_m) <= 0:
            raise ValueError('soil capacity and root depth must be positive')
        if not 0 < number(self.allowed_depletion) <= 1:
            raise ValueError('allowed depletion must be in (0,1]')
        if number(self.crop_coefficient) < 0 or not 0 <= number(self.effective_rain) <= 1:
            raise ValueError('invalid crop coefficient or rain factor')

    @property
    def capacity(self):
        return number(self.capacity_mm_per_m) * number(self.root_depth_m)

    @property
    def threshold(self):
        return self.capacity * number(self.allowed_depletion)


@dataclass(frozen=True)
class Zone:
    id: str
    station: int
    profile_id: str
    group_id: str
    application_mm_per_hour: float
    efficiency: float
    cycle_seconds: int
    soak_seconds: int
    minimum_pulse_seconds: int = 1
    enabled: bool = True

    def __post_init__(self):
        for item in (self.id, self.profile_id, self.group_id):
            identifier(item)
        integer(self.station, 1)
        integer(self.cycle_seconds, 1)
        integer(self.soak_seconds)
        integer(self.minimum_pulse_seconds, 1)
        if self.minimum_pulse_seconds > self.cycle_seconds:
            raise ValueError('minimum pulse exceeds cycle limit')
        if number(self.application_mm_per_hour) <= 0 or not 0 < number(self.efficiency) <= 1:
            raise ValueError('invalid application rate or efficiency')
        if type(self.enabled) is not bool:
            raise ValueError('enabled must be boolean')

    @property
    def net_rate(self):
        return number(self.application_mm_per_hour) * number(self.efficiency) / 3600


@dataclass(frozen=True)
class Observation:
    """An explicit point contribution, not a daily weather interval.

    ET is netted at `at`; callers must split intervals around watering/rain events
    if chronological wetting/drainage matters. Revisions replace the same event.
    """
    id: str
    zone_id: str
    at: int
    kind: str  # eto_mm, rain_mm, delivered_seconds, unknown_delivery, missing_weather
    amount: float = 0
    revision: int = 1

    def __post_init__(self):
        identifier(self.id)
        identifier(self.zone_id)
        integer(self.at)
        integer(self.revision, 1)
        if self.kind not in {'eto_mm', 'rain_mm', 'delivered_seconds',
                             'unknown_delivery', 'missing_weather'}:
            raise ValueError('unsupported observation kind')
        if number(self.amount) < 0:
            raise ValueError('negative observation')
        if self.kind in {'unknown_delivery', 'missing_weather'} and self.amount != 0:
            raise ValueError('unknown observation cannot assert an amount')
        if self.kind == 'delivered_seconds':
            integer(self.amount)


class Ledger:
    def __init__(self, profiles, zones, initial):
        self.profiles = dict(profiles)
        self.zones = dict(zones)
        self.initial = {k: number(v) for k, v in initial.items()}
        if set(self.initial) != set(self.zones):
            raise ValueError('initial depletion required for every zone')
        if len({z.station for z in zones.values()}) != len(zones):
            raise ValueError('each station must map to exactly one valve/zone')
        for key, zone in self.zones.items():
            if key != zone.id or zone.profile_id not in self.profiles:
                raise ValueError('invalid zone/profile reference')
            if not 0 <= self.initial[key] <= self.profiles[zone.profile_id].capacity:
                raise ValueError('initial depletion outside reservoir')
        self.events = {}

    def put(self, event):
        if event.zone_id not in self.zones:
            raise ValueError('unknown zone')
        key = (event.zone_id, event.id)
        previous = self.events.get(key)
        if previous:
            if event.revision < previous.revision:
                return False
            if event.revision == previous.revision:
                if event != previous:
                    raise ValueError('conflicting payload for same event revision')
                return False
        self.events[key] = event
        return True

    def state(self, zone_id, through):
        integer(through)
        zone = self.zones[zone_id]
        profile = self.profiles[zone.profile_id]
        depletion = self.initial[zone_id]
        drainage = excess_demand = irrigation = Fraction(0)
        unresolved = []
        # IDs provide deterministic ordering of simultaneous observations. Fixture
        # authors must separate timestamps if physical order matters.
        for event in sorted(self.events.values(), key=lambda e: (e.at, e.id)):
            if event.zone_id != zone_id or event.at > through:
                continue
            if event.kind in {'unknown_delivery', 'missing_weather'}:
                unresolved.append(event.id)
                continue
            amount = number(event.amount)
            if event.kind == 'eto_mm':
                depletion += amount * number(profile.crop_coefficient)
            elif event.kind == 'rain_mm':
                depletion -= amount * number(profile.effective_rain)
            else:
                credit = amount * zone.net_rate
                irrigation += credit
                depletion -= credit
            drainage += max(0, -depletion)
            excess_demand += max(0, depletion - profile.capacity)
            depletion = min(profile.capacity, max(0, depletion))
        return dict(depletion_mm=float(depletion), drainage_mm=float(drainage),
                    demand_beyond_capacity_mm=float(excess_demand),
                    irrigation_input_mm=float(irrigation), unresolved=unresolved,
                    profile_version=profile.version)

    def checkpoint(self):
        return [asdict(e) for e in sorted(self.events.values(), key=lambda e: (e.zone_id, e.id))]

    def restore(self, events):
        # Validate into a fresh ledger before replacing state.
        replacement = Ledger(self.profiles, self.zones, self.initial)
        for item in events:
            replacement.put(Observation(**item))
        self.events = replacement.events
