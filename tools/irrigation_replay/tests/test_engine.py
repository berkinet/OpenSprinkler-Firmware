import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.irrigation_replay.draft import InputErrors, compile_draft
from tools.irrigation_replay.engine import audit, dry_run

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'


class EngineContractTests(unittest.TestCase):
    def setUp(self):
        self.draft = json.loads((FIXTURES / 'editor-draft.json').read_text())
        self.runtime = json.loads((FIXTURES / 'editor-runtime.json').read_text())

    def run_plan(self):
        return dry_run(self.draft, self.runtime)

    def test_actual_draft_units_and_zero_based_valve_mapping(self):
        self.draft['programs'][0].update(efficiency=80, minimum=1/60, cycle=.5)
        config = compile_draft(self.draft)
        a, b = config.zones
        self.assertEqual((a.id, a.station, b.station), ('sid:0', 1, 2))
        self.assertEqual((a.cycle_seconds, a.soak_seconds, a.minimum_pulse_seconds), (30, 60, 1))
        self.assertAlmostEqual(float(a.efficiency), .8)
        self.assertEqual(config.profiles['garden'].capacity, 30)
        self.assertEqual(config.profiles['garden'].threshold, 15)

    def test_two_valves_full_partial_and_interleaved_soak(self):
        before = copy.deepcopy((self.draft, self.runtime))
        result = self.run_plan()
        self.assertEqual(result['status'], 'conditional_plan')
        a, b = result['decisions']
        self.assertEqual((a['sid'], a['status'], a['allocated_seconds'], a['elapsed_seconds']), (0, 'full', 300, 540))
        self.assertEqual((b['sid'], b['status'], b['allocated_seconds'], b['elapsed_seconds']), (1, 'partial', 240, 420))
        start = result['window']['start']
        self.assertEqual([(p['start']-start, p['end']-start) for p in a['pulses']],
                         [(0,60), (120,180), (240,300), (360,420), (480,540)])
        all_pulses = sorted(a['pulses']+b['pulses'], key=lambda p:p['start'])
        self.assertTrue(all(x['end'] <= y['start'] for x, y in zip(all_pulses, all_pulses[1:])))
        self.assertEqual(b['projection']['end_depletion_mm'], 15)
        self.assertEqual(result['promotion_candidates'], [1])
        self.assertEqual(result['depletion_at_start_mm'], {'sid:0':6, 'sid:1':6})
        self.assertEqual((self.draft, self.runtime), before)  # no invented delivery or tokens
        self.assertEqual(self.run_plan(), result)
        json.dumps(result, allow_nan=False)

    def test_changing_only_group_order_changes_allocation(self):
        self.draft['groups'].reverse()
        a, b = self.run_plan()['decisions']
        self.assertEqual((a['sid'], a['status'], b['sid'], b['status']), (1, 'full', 0, 'partial'))

    def test_short_window_reports_skip_instead_of_token_watering(self):
        self.draft['windows'][0]['end'] = '06:06'
        decisions = self.run_plan()['decisions']
        self.assertTrue(all(d['status'] == 'skipped' and not d['pulses'] for d in decisions))
        self.assertTrue(all(d['reason'] == 'planner_no_fit' for d in decisions))

    def test_collects_missing_form_fields_without_using_defaults(self):
        self.draft['profile'] = {}
        self.draft['programs'][0].update(rate='', soak='', minimum='')
        with self.assertRaises(InputErrors) as caught:
            self.run_plan()
        paths = {i['path'] for i in caught.exception.issues}
        self.assertTrue({'profile.capacity','profile.roots','profile.depletion','profile.crop','profile.rain',
                         'programs[0].rate','programs[0].soak','programs[0].minimum'} <= paths)

    def test_zero_factors_and_zero_soak_are_valid_but_blank_is_not_zero(self):
        self.draft['profile'].update(crop=0, rain=0)
        self.draft['programs'][0]['soak'] = 0
        config = compile_draft(self.draft)
        self.assertEqual(config.profiles['garden'].crop_coefficient, 0)
        self.assertEqual(config.zones[0].soak_seconds, 0)
        self.assertTrue(all(d['reason'] == 'not_due' for d in self.run_plan()['decisions']))

    def test_rejects_invalid_types_nonfinite_and_subsecond_durations(self):
        for key, value in [('rate', True), ('rate', float('nan')), ('rate', '72'),
                           ('cycle', .001), ('sid', False), ('efficiency', 101), ('enabled', 1)]:
            with self.subTest(key=key, value=value):
                draft = copy.deepcopy(self.draft)
                draft['programs'][0][key] = value
                with self.assertRaises(InputErrors):
                    compile_draft(draft)

    def test_rejects_unknown_fields_versions_and_references(self):
        bad = []
        for key,value in [('profile','unknown'),('group','Unknown'),('sid',1),('new_setting',5)]:
            d=copy.deepcopy(self.draft); d['programs'][0][key]=value; bad.append(d)
        d=copy.deepcopy(self.draft); d['version']=99; bad.append(d)
        d=copy.deepcopy(self.draft); d['groups']=['High',' high ']; bad.append(d)
        for draft in bad:
            with self.assertRaises(InputErrors):
                compile_draft(draft)

    def test_disabled_incomplete_draft_needs_no_runtime_state(self):
        self.draft['programs'][1].update(enabled=False, rate='', minimum='')
        self.runtime['states'].pop('1'); self.runtime['next_service'].pop('1')
        result = self.run_plan()
        self.assertEqual(len(result['decisions']), 1)
        self.assertEqual(result['disabled_programs'][0]['sid'], 1)
        self.assertEqual(result['disabled_programs'][0]['reason'], 'disabled')

    def test_state_has_to_be_reconciled_and_valve_available(self):
        for change in ('stale', 'unknown_sid', 'ready_missing', 'empty_depletion'):
            with self.subTest(change=change):
                self.setUp()
                if change == 'stale': self.runtime['states']['0']['at'] = '2026-09-20T06:00:00Z'
                if change == 'unknown_sid': self.runtime['eligible_station_sids'] = [1]
                if change == 'ready_missing': self.runtime['states']['0'].pop('ready_at')
                if change == 'empty_depletion': self.runtime['states']['0']['depletion_mm'] = ''
                with self.assertRaises(InputErrors): self.run_plan()

    def test_unknown_delivery_blocks_only_affected_zone(self):
        self.runtime['states']['0']['unresolved'] = ['uncertain-start-17']
        a, b = self.run_plan()['decisions']
        self.assertEqual(a['reason'], 'unresolved_observation')
        self.assertEqual(a['pulses'], [])
        self.assertEqual(b['status'], 'full')

    def test_weather_units_are_converted_once(self):
        self.runtime['weather']['periods'][1]['eto'] = 12.7
        expected = self.run_plan()['decisions']
        self.runtime['weather']['units'] = 'in'
        self.runtime['weather']['periods'][1]['eto'] = .5
        actual = self.run_plan()['decisions']
        self.assertEqual([d['allocated_seconds'] for d in actual], [d['allocated_seconds'] for d in expected])
        self.assertAlmostEqual(actual[1]['projection']['end_depletion_mm'], 15)

    def test_weather_gap_missing_horizon_and_undated_percentage_rejected(self):
        for change in ('gap', 'missing_horizon', 'percentage', 'distribution', 'too_short'):
            with self.subTest(change=change):
                self.setUp()
                if change == 'gap': self.runtime['weather']['periods'][1]['start']='2026-09-21T06:10:00Z'
                if change == 'missing_horizon': self.runtime['next_service'].pop('0')
                if change == 'percentage': self.runtime['weather']={'scale':100, 'eto':.15}
                if change == 'distribution': self.runtime['weather'].pop('distribution')
                if change == 'too_short': self.runtime['weather']['periods'].pop()
                with self.assertRaises(InputErrors): self.run_plan()

    def test_horizon_must_be_legal_and_have_time_for_minimum_pulse(self):
        for future in ('2026-09-21T06:05:00Z', '2026-09-22T05:59:00Z', '2026-09-22T06:09:00Z'):
            with self.subTest(future=future):
                self.runtime['next_service']['0'] = future
                with self.assertRaises(InputErrors): self.run_plan()

    def test_future_exclusion_invalidates_service_assumption(self):
        self.draft['excluded'] = '2026-09-22'
        with self.assertRaises(InputErrors): self.run_plan()

    def test_no_windows_and_exclusions_never_create_plan(self):
        for empty in (False, True):
            self.setUp()
            if empty: self.draft['windows'] = []
            else: self.draft['excluded'] = '2026-09-21'
            result = self.run_plan()
            self.assertEqual(result['status'], 'outside_watering_window')
            self.assertEqual(result['decisions'], [])

    def test_resource_capacity_and_timing_margins_are_explicit(self):
        self.runtime['resource']['max_active_valves'] = 2
        with self.assertRaises(InputErrors): self.run_plan()
        self.runtime['resource']['max_active_valves'] = 1
        self.runtime['resource']['transition_seconds'] = 5
        self.runtime['resource']['closing_margin_seconds'] = 10
        result = self.run_plan()
        pulses = sorted([p for d in result['decisions'] for p in d['pulses']], key=lambda p:p['start'])
        self.assertTrue(all(p['end'] <= result['window']['end']-10 for p in pulses))
        self.assertTrue(all(a['end']+5 <= b['start'] for a,b in zip(pulses,pulses[1:])))
        self.assertTrue(pulses)

    def test_existing_soak_readiness_limits_first_pulse(self):
        self.runtime['states']['0']['ready_at'] = '2026-09-21T06:01:00Z'
        result = self.run_plan()
        for d in result['decisions']:
            if d['sid'] == 0:
                self.assertTrue(d['pulses'])
                self.assertTrue(all(p['start'] >= result['window']['start']+60 for p in d['pulses']))

    def test_replanning_partway_through_window_never_schedules_in_past(self):
        self.runtime['as_of'] = '2026-09-21T06:02:00Z'
        for state in self.runtime['states'].values():
            state['at'] = self.runtime['as_of']
        result = self.run_plan()
        pulses = [p for d in result['decisions'] for p in d['pulses']]
        self.assertTrue(pulses)
        self.assertTrue(all(p['start'] >= result['window']['start'] for p in pulses))
        self.assertEqual(result['window']['end']-result['window']['start'], 420)

    def test_report_only_and_supplied_promotion_do_not_edit_membership(self):
        self.draft['shortage'] = 'report_only'
        self.assertEqual(self.run_plan()['promotion_candidates'], [])
        self.runtime['promoted_sids'] = [1]
        with self.assertRaises(InputErrors): self.run_plan()
        self.draft['shortage'] = 'promote_next'
        result = self.run_plan()
        low = next(d for d in result['decisions'] if d['sid']==1)
        self.assertEqual((low['configured_group'], low['effective_group']), ('Normal', 'High'))
        self.assertEqual(self.draft['programs'][1]['group'], 'Normal')

    def test_named_timezone_and_offset_aware_timestamps_required(self):
        for key, value in [('timezone', 'no-such-timezone'), ('as_of', '2026-09-21T06:00:00'),
                           ('calendar_through', '2028-01-01')]:
            self.setUp(); self.runtime[key] = value
            with self.assertRaises(InputErrors): self.run_plan()

    def test_audit_does_not_claim_runtime_readiness(self):
        result = audit(self.draft)
        self.assertEqual(result['status'], 'configuration_valid')
        self.assertTrue(result['runtime_required'])
        self.assertFalse(result['automatic_watering_enabled'])

    def test_cli_accepts_export_and_returns_json(self):
        result = subprocess.run([sys.executable, '-m', 'tools.irrigation_replay',
            '--draft', str(FIXTURES/'editor-draft.json'), '--runtime', str(FIXTURES/'editor-runtime.json')],
            capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)['status'], 'conditional_plan')

    def test_cli_missing_calibration_returns_blocked_json_and_exit_two(self):
        self.draft['programs'][0]['rate'] = ''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'draft.json'
            path.write_text(json.dumps(self.draft))
            result = subprocess.run([sys.executable, '-m', 'tools.irrigation_replay',
                '--draft', str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        report = json.loads(result.stdout)
        self.assertEqual(report['status'], 'blocked')
        self.assertEqual(report['issues'][0]['path'], 'programs[0].rate')


if __name__ == '__main__':
    unittest.main()
