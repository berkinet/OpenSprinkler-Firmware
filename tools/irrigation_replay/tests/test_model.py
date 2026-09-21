import json
import unittest
from dataclasses import replace
from tools.irrigation_replay.model import Profile, Zone, Observation, Ledger


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.p = Profile('garden', 100, .3, .5)
        self.z = Zone('a', 1, 'garden', 'normal', 30, .8, 60, 60)
        self.ledger = Ledger({'garden': self.p}, {'a': self.z}, {'a': 12})

    def test_interrupted_delivery_is_actual_not_planned(self):
        self.ledger.put(Observation('pulse', 'a', 600, 'delivered_seconds', 600))
        self.assertEqual(self.ledger.state('a', 600)['depletion_mm'], 8)
        self.assertEqual(self.ledger.state('a', 599)['irrigation_input_mm'], 0)

    def test_duplicate_and_correction_replay(self):
        event = Observation('pulse', 'a', 600, 'delivered_seconds', 600)
        self.assertTrue(self.ledger.put(event))
        self.assertFalse(self.ledger.put(event))
        self.ledger.put(replace(event, amount=300, revision=2))
        self.assertFalse(self.ledger.put(event))
        self.assertEqual(self.ledger.state('a', 600)['depletion_mm'], 10)
        with self.assertRaises(ValueError):
            self.ledger.put(replace(event, amount=301, revision=2))

    def test_rain_overflow_does_not_cancel_later_et(self):
        self.ledger.put(Observation('rain', 'a', 1, 'rain_mm', 20))
        self.ledger.put(Observation('et', 'a', 2, 'eto_mm', 5))
        state = self.ledger.state('a', 2)
        self.assertEqual(state['depletion_mm'], 5)
        self.assertEqual(state['drainage_mm'], 8)

    def test_saturation_does_not_hide_demand(self):
        self.ledger.put(Observation('hot', 'a', 1, 'eto_mm', 25))
        state = self.ledger.state('a', 1)
        self.assertEqual(state['depletion_mm'], 30)
        self.assertEqual(state['demand_beyond_capacity_mm'], 7)

    def test_profile_sharing_keeps_independent_ledgers(self):
        b = replace(self.z, id='b', station=2)
        ledger = Ledger({'garden': self.p}, {'a': self.z, 'b': b}, {'a': 12, 'b': 12})
        ledger.put(Observation('pulse', 'a', 1, 'delivered_seconds', 600))
        self.assertEqual(ledger.state('a', 1)['depletion_mm'], 8)
        self.assertEqual(ledger.state('b', 1)['depletion_mm'], 12)

    def test_unknown_delivery_survives_restart_and_can_be_resolved(self):
        event = Observation('pulse', 'a', 1, 'unknown_delivery')
        self.ledger.put(event)
        snapshot = json.loads(json.dumps(self.ledger.checkpoint()))
        other = Ledger({'garden': self.p}, {'a': self.z}, {'a': 12})
        other.restore(snapshot)
        self.assertEqual(other.state('a', 1)['unresolved'], ['pulse'])
        other.put(replace(event, kind='delivered_seconds', amount=300, revision=2))
        self.assertEqual(other.state('a', 1)['unresolved'], [])
        self.assertEqual(other.state('a', 1)['depletion_mm'], 10)

    def test_restoring_bad_checkpoint_does_not_destroy_ledger(self):
        self.ledger.put(Observation('rain', 'a', 1, 'rain_mm', 2))
        with self.assertRaises(ValueError):
            self.ledger.restore([dict(id='bad',zone_id='unknown',at=1,kind='eto_mm',amount=2)])
        self.assertEqual(self.ledger.state('a', 1)['depletion_mm'], 10)

    def test_inputs_reject_nonfinite_boolean_and_invalid_ranges(self):
        for value in (float('nan'), float('inf'), -1, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                replace(self.p, capacity_mm_per_m=value)
        with self.assertRaises(ValueError):
            replace(self.z, minimum_pulse_seconds=61)
        with self.assertRaises(ValueError):
            Observation('x','a',1,'delivered_seconds',1.5)
        with self.assertRaises(ValueError):
            Observation('x','a',1,'unknown_delivery',2)


if __name__ == '__main__':
    unittest.main()
