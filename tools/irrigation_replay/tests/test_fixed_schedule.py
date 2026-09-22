import copy
import json
from pathlib import Path
import unittest
from datetime import date
from zoneinfo import ZoneInfo

from tools.irrigation_replay.draft import compile_draft, InputErrors
from tools.irrigation_replay.engine import dry_run
from tools.irrigation_replay.fixed import exact_start

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'


class FixedScheduleTests(unittest.TestCase):
    def setUp(self):
        self.draft = json.loads((FIXTURES/'editor-draft.json').read_text())
        self.runtime = json.loads((FIXTURES/'editor-runtime.json').read_text())
        self.draft['version'] = 4
        self.fixed = dict(id='timed:mist', scheduleMode='fixed', sid=0, name='Misting',
            enabled=True, group=self.draft['groups'][0], permittedHours={'mode':'all'},
            amountMode='runtime', runtime=1, cycle=1, soak=0, minimum=1/60,
            days=list(range(7)), times=['06:00'])
        self.draft['programs'].append(self.fixed)

    def run_plan(self):
        return dry_run(self.draft, self.runtime)

    def test_shared_valve_has_separate_programs_and_no_double_refill(self):
        before = copy.deepcopy((self.draft, self.runtime))
        result = self.run_plan()
        mist = result['fixed_decisions'][0]
        self.assertEqual((mist['sid'], mist['allocated_seconds'], mist['delivery_basis']), (0, 60, 'no_soil_credit'))
        pulses = sorted([p for d in result['decisions']+result['fixed_decisions'] for p in d['pulses']], key=lambda p:p['start'])
        self.assertTrue(all(a['end'] <= b['start'] for a, b in zip(pulses, pulses[1:])))
        soil = next(d for d in result['decisions'] if d['sid'] == 0)
        self.assertGreaterEqual(soil['pulses'][0]['start'], mist['pulses'][0]['end']+60)
        self.assertEqual(result['depletion_at_start_mm']['sid:0'], 6)
        self.assertEqual(before, (self.draft, self.runtime))

    def test_fixed_only_needs_no_profile_weather_or_soil_state(self):
        self.draft['programs'] = [self.fixed]
        self.draft['profile'] = {}
        self.runtime.pop('weather'); self.runtime.pop('next_service')
        self.runtime['states']['0'].pop('depletion_mm')
        self.assertEqual(self.run_plan()['fixed_decisions'][0]['allocated_seconds'], 60)

    def test_weather_does_not_change_fixed_event(self):
        baseline = self.run_plan()['fixed_decisions']
        for period in self.runtime['weather']['periods']:
            period['eto'] = 50
        self.assertEqual(self.run_plan()['fixed_decisions'], baseline)

    def test_mutually_exclusive_schema_rejects_soil_settings_on_fixed_program(self):
        for key, value in [('profile','garden'), ('rate',10), ('depth',2)]:
            with self.subTest(key=key):
                bad = copy.deepcopy(self.draft); bad['programs'][-1][key] = value
                with self.assertRaises(InputErrors): compile_draft(bad)

    def test_priority_groups_settle_fixed_conflicts(self):
        self.fixed['group'] = self.draft['groups'][-1]
        other = dict(self.fixed, id='timed:other', name='Priority mist', sid=1, group=self.draft['groups'][0])
        self.draft['programs'].append(other)
        decisions = self.run_plan()['fixed_decisions']
        self.assertEqual([(d['program_id'], d['reason']) for d in decisions],
                         [('timed:other','scheduled'), ('timed:mist','priority_conflict')])
        self.assertFalse(decisions[1]['promotion_eligible'])

    def test_restrictions_skip_instead_of_shifting_or_truncating(self):
        for hours, times in [({'mode':'custom','start':'06:02','end':'06:04'}, ['06:00']),
                             ({'mode':'all'}, ['06:08'])]:
            self.fixed.update(permittedHours=hours, times=times, runtime=2, cycle=2)
            item = self.run_plan()['fixed_decisions'][0]
            self.assertEqual((item['reason'], item['pulses']), ('watering_restriction', []))
        self.draft['excluded'] = '2026-09-21'
        self.fixed.update(times=['06:00'], runtime=1, cycle=1)
        self.assertEqual(self.run_plan()['fixed_decisions'][0]['reason'], 'watering_restriction')

    def test_past_start_is_not_caught_up_and_unselected_day_is_absent(self):
        self.fixed.update(times=['05:59'], days=[0])
        self.assertEqual(self.run_plan()['fixed_decisions'], [])
        self.fixed.update(times=['06:00'], days=[1])  # Monday snapshot
        self.assertEqual(self.run_plan()['fixed_decisions'], [])

    def test_unresolved_or_not_ready_valve_blocks_fixed_event(self):
        self.runtime['states']['0']['unresolved'] = ['uncertain-run']
        self.assertEqual(self.run_plan()['fixed_decisions'][0]['reason'], 'unresolved_delivery')
        self.runtime['states']['0'].update(unresolved=[], ready_at='2026-09-21T06:01:00Z')
        self.assertEqual(self.run_plan()['fixed_decisions'][0]['reason'], 'valve_not_ready')
        del self.runtime['states']['0']
        with self.assertRaises(InputErrors): self.run_plan()

    def test_cycles_reserve_each_pulse_with_soak(self):
        self.fixed.update(runtime=3, cycle=1, soak=1)
        pulses = self.run_plan()['fixed_decisions'][0]['pulses']
        self.assertEqual(len(pulses), 3)
        self.assertTrue(all(b['start']-a['end'] == 60 for a,b in zip(pulses,pulses[1:])))

    def test_disabled_fixed_program_does_not_reserve_or_require_calibration(self):
        self.fixed.update(enabled=False, runtime='')
        self.assertEqual(self.run_plan()['fixed_decisions'], [])

    def test_invalid_or_duplicate_ids_times_and_days_are_rejected(self):
        for update in [dict(id='sid:0'), dict(times=['24:00']), dict(times=['06:00','06:00']),
                       dict(days=[]), dict(days=[True]), dict(runtime=0), dict(runtime=2000)]:
            with self.subTest(update=update):
                bad = copy.deepcopy(self.draft); bad['programs'][-1].update(update)
                with self.assertRaises(InputErrors): compile_draft(bad)
        self.draft['programs'].append(copy.deepcopy(self.fixed))
        with self.assertRaises(InputErrors): compile_draft(self.draft)

    def test_dst_missing_time_is_not_shifted_and_repeated_time_occurs_once(self):
        tz = ZoneInfo('Europe/Paris')
        self.assertIsNone(exact_start(date(2026,3,29), 150, tz))
        value = exact_start(date(2026,10,25), 150, tz)
        self.assertEqual(value, 1792888200)  # first 02:30, CEST

    def test_transition_margin_is_respected_between_fixed_pulses(self):
        self.fixed.update(runtime=2, cycle=1, soak=0)
        self.runtime['resource']['transition_seconds'] = 5
        result = self.run_plan()
        pulses = result['fixed_decisions'][0]['pulses']
        self.assertEqual(pulses[1]['start']-pulses[0]['end'], 5)
        self.runtime['resource']['closing_margin_seconds'] = 5
        self.fixed.update(times=['06:08'], runtime=1, cycle=1)
        self.assertEqual(self.run_plan()['fixed_decisions'][0]['reason'], 'watering_restriction')

    def test_night_only_blocks_midday_fixed_event(self):
        self.draft['windows'] = []
        self.runtime['location'] = {'latitude':48.8566,'longitude':2.3522}
        self.fixed.update(permittedHours={'mode':'night'}, times=['12:15'])
        self.draft['programs'] = [self.fixed]
        self.assertEqual(self.run_plan()['fixed_decisions'][0]['reason'], 'watering_restriction')

    def test_second_soil_program_for_same_valve_still_rejected(self):
        self.draft['programs'].append(copy.deepcopy(self.draft['programs'][0]))
        with self.assertRaises(InputErrors): compile_draft(self.draft)
