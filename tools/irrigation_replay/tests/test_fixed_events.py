"""Fixed event amounts, conditional projections and explicit refill completion."""
import json
from pathlib import Path
import unittest
from tools.irrigation_replay.draft import compile_draft, InputErrors
from tools.irrigation_replay.engine import dry_run
from tools.irrigation_replay.model import Ledger, Observation

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'

class FixedEventsTests(unittest.TestCase):
    def setUp(self):
        self.draft = json.loads((FIXTURES/'editor-draft.json').read_text())
        self.runtime = json.loads((FIXTURES/'editor-runtime.json').read_text())
        self.draft['version'] = 2
        self.draft['programs'] = self.draft['programs'][:1]
        self.draft['programs'][0].update(amountMode='runtime', runtime=5, depth='', rate='', efficiency='')
        self.runtime['states'].pop('1')
        self.runtime['next_service'].pop('1')

    def decision(self):
        return dry_run(self.draft, self.runtime)['decisions'][0]

    def test_permitted_hours_inherit_override_and_soak_fit(self):
        self.draft['windows'][0]['end'] = '06:30'
        self.draft['defaultHours'] = dict(mode='custom', start='06:00', end='06:08')
        d = self.decision()
        self.assertEqual(d['status'], 'skipped')  # Five one-minute pulses need nine minutes.
        self.assertEqual(d['pulses'], [])
        self.draft['programs'][0]['permittedHours'] = dict(mode='all')
        self.assertEqual(self.decision()['status'], 'full')
        self.draft['programs'][0]['permittedHours'] = dict(mode='inherit')
        self.assertEqual(self.decision()['status'], 'skipped')
        self.draft['defaultHours']['end'] = '06:09'
        self.assertEqual(self.decision()['status'], 'full')

    def test_overnight_hours_and_site_restrictions_intersect(self):
        self.draft['defaultHours'] = dict(mode='custom', start='22:00', end='06:09')
        self.assertEqual(self.decision()['status'], 'full')
        self.draft['windows'][0]['end'] = '06:08'
        self.assertEqual(self.decision()['status'], 'skipped')
        self.draft['defaultHours'] = dict(mode='all')
        self.assertEqual(self.decision()['status'], 'skipped')

    def test_future_service_must_respect_program_hours(self):
        self.draft['defaultHours'] = dict(mode='custom', start='06:01', end='07:00')
        with self.assertRaisesRegex(InputErrors, 'within program permitted hours'):
            self.decision()

    def test_bad_hours_are_rejected(self):
        for hours in ({'mode': 'custom', 'start': '06:00', 'end': '06:00'},
                      {'mode': 'custom', 'start': '25:00', 'end': '06:00'},
                      {'mode': 'all', 'start': '06:00'}, {'mode': 'unknown'}, 4):
            self.draft['defaultHours'] = hours
            with self.assertRaises(InputErrors):
                compile_draft(self.draft)

    def test_weather_changes_due_decision_never_full_runtime(self):
        for demand, due in [(0, False), (12, True), (14, True)]:
            self.runtime['weather']['periods'][1]['eto'] = demand
            d = self.decision()
            self.assertEqual(d['allocated_seconds'], 300 if due else 0)
            self.assertEqual(d['status'], 'full' if due else 'skipped')
        self.assertIsNone(d['allocated_mm'])
        self.assertEqual(d['delivery_basis'], 'assumed_refill')
        self.assertEqual([p['duration_seconds'] for p in d['pulses']], [60]*5)
        self.assertEqual(d['elapsed_seconds'], 540)
        self.assertEqual(d['projection']['end_depletion_mm'], 14)

    def test_current_deficit_does_not_scale_minutes(self):
        for depletion in (4, 8, 12):
            self.runtime['states']['0']['depletion_mm'] = depletion
            self.assertEqual(self.decision()['allocated_seconds'], 300)

    def test_runtime_event_that_cannot_fit_is_skipped_without_partial(self):
        self.draft['windows'][0]['end'] = '06:08'
        d = self.decision()
        self.assertEqual((d['status'], d['allocated_seconds'], d['pulses']), ('skipped', 0, []))
        self.assertTrue(d['promotion_eligible'])

    def test_fixed_depth_runtime_does_not_follow_current_deficit(self):
        self.draft['programs'][0].update(amountMode='depth', depth=6, rate=72, efficiency=100)
        self.runtime['weather']['periods'][1]['eto'] = 12
        for depletion in (4, 6, 8):
            self.runtime['states']['0']['depletion_mm'] = depletion
            self.assertEqual(self.decision()['allocated_seconds'], 300)
        self.draft['programs'][0]['efficiency'] = 50
        self.draft['windows'][0]['end'] = '06:30'
        self.assertEqual(self.decision()['allocated_seconds'], 600)

    def test_validation_and_legacy_compatibility(self):
        for value in ('', 0, -1, True, .001):
            self.draft['programs'][0]['runtime'] = value
            with self.assertRaises(InputErrors): compile_draft(self.draft)
        self.draft['programs'][0]['runtime'] = 5
        self.assertEqual(compile_draft(self.draft).zones[0].runtime_seconds, 300)
        self.draft['version'] = 1
        with self.assertRaises(InputErrors): compile_draft(self.draft)
        original = json.loads((FIXTURES/'editor-draft.json').read_text())
        self.assertEqual(compile_draft(original).zones[0].watering_mode, 'legacy')

    def test_only_verified_complete_event_resets_ledger(self):
        config = compile_draft(self.draft)
        zone = config.zones[0]
        ledger = Ledger(config.profiles, {zone.id: zone}, {zone.id: 12})
        before = ledger.checkpoint()
        self.decision()  # A plan never writes the ledger.
        self.assertEqual(ledger.checkpoint(), before)
        ledger.put(Observation('event-a', zone.id, 10, 'delivered_seconds', 60))
        self.assertEqual(ledger.state(zone.id, 10)['depletion_mm'], 12)
        self.assertEqual(ledger.state(zone.id, 10)['unresolved'], ['event-a'])
        with self.assertRaises(ValueError):
            ledger.put(Observation('event-a', zone.id, 20, 'completed_refill_seconds', 299, 2))
        completion = Observation('event-a', zone.id, 20, 'completed_refill_seconds', 300, 2)
        ledger.put(completion)
        self.assertFalse(ledger.put(completion))  # Retry is idempotent.
        self.assertEqual(ledger.state(zone.id, 20)['depletion_mm'], 0)
        self.assertEqual(ledger.state(zone.id, 20)['unresolved'], [])
        ledger.put(Observation('weather', zone.id, 30, 'eto_mm', 4))
        self.assertEqual(ledger.state(zone.id, 30)['depletion_mm'], 4)
        restored = Ledger(config.profiles, {zone.id: zone}, {zone.id: 12})
        restored.restore(ledger.checkpoint())
        self.assertEqual(restored.state(zone.id, 30), ledger.state(zone.id, 30))
        # A correction withdrawing completion must remove the assumed refill.
        ledger.put(Observation('event-a', zone.id, 20, 'unknown_delivery', 0, 3))
        self.assertEqual(ledger.state(zone.id, 30)['depletion_mm'], 16)

    def test_missing_profile_still_blocks_runtime_mode(self):
        self.draft['profile'] = {}
        with self.assertRaises(InputErrors): compile_draft(self.draft)

    def test_actual_v2_browser_fixture_with_both_amount_modes(self):
        draft = json.loads((FIXTURES/'fixed-events-draft.json').read_text())
        runtime = json.loads((FIXTURES/'editor-runtime.json').read_text())
        result = dry_run(draft, runtime)
        self.assertEqual([d['watering_mode'] for d in result['decisions']], ['runtime', 'depth'])
        self.assertEqual([d['allocated_seconds'] for d in result['decisions']], [300, 240])
        self.assertIsNone(result['decisions'][0]['allocated_mm'])
        self.assertEqual(result['decisions'][1]['status'], 'partial')
