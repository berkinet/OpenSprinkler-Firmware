import json
import unittest
from dataclasses import replace
from pathlib import Path
from tools.irrigation_replay.model import Profile, Zone
from tools.irrigation_replay.planner import (Window, ETPeriod, Pulse, pack,
    project, plan, Promotions)
from tools.irrigation_replay.replay import replay

ROOT = Path(__file__).resolve().parents[2]


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.p = Profile('garden',100,.3,.5)
        self.z = Zone('bed',1,'garden','normal',30,.8,1800,0)

    def planning(self, seconds, depletion=12, etc=6, zone=None, **kwargs):
        zone = zone or self.z
        w = Window('today',0,seconds)
        return plan(w,[zone],{'garden':self.p},['normal'],
                    {zone.id:{'depletion_mm':depletion,'unresolved':[]}},
                    {zone.id:[ETPeriod(0,seconds,0),ETPeriod(seconds,86400,etc)]},
                    {zone.id:86400},**kwargs)[0]

    def test_full_and_partial_numeric_oracles(self):
        self.assertEqual(self.planning(1800)['allocated_seconds'],1800)
        result = self.planning(480)
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['allocated_seconds'],450)
        self.assertEqual(result['minimum_refill_mm'],3)
        self.assertEqual(result['projection']['end_depletion_mm'],15)
        self.assertEqual(result['projection']['stress_seconds'],0)
        self.assertTrue(result['promotion_eligible'])

    def test_insufficient_partial_and_storage_infeasible(self):
        result = self.planning(420)
        self.assertEqual(result['reason'],'insufficient_on_time')
        self.assertEqual(result['allocated_seconds'],0)
        self.assertEqual(result['projection']['end_depletion_mm'],18)
        result = self.planning(1800,etc=20)
        self.assertEqual(result['reason'],'storage_horizon_infeasible')
        self.assertEqual(result['minimum_refill_mm'],17)
        self.assertFalse(result['promotion_eligible'])

    def test_cycle_soak_numeric_oracle(self):
        zone = replace(self.z,cycle_seconds=60,soak_seconds=60)
        pulses = pack(zone,300,Window('w',0,540))
        expected = [(0,60),(120,180),(240,300),(360,420),(480,540)]
        self.assertEqual([(p.start,p.end) for p in pulses],expected)
        self.assertIsNone(pack(zone,300,Window('w',0,539)))
        other = replace(zone,id='b',station=2)
        self.assertEqual(pack(other,60,Window('w',0,540),pulses),[Pulse(60,120,'b')])

    def test_minimum_tail_rebalanced(self):
        zone = replace(self.z,cycle_seconds=60,soak_seconds=10,minimum_pulse_seconds=30)
        self.assertEqual(pack(zone,70,Window('w',0,80)),[Pulse(0,40,'bed'),Pulse(50,80,'bed')])
        self.assertIsNone(pack(zone,29,Window('w',0,80)))

    def test_failed_packing_has_no_side_effect(self):
        reserved = [Pulse(30,50,'other')]
        before = list(reserved)
        self.assertIsNone(pack(self.z,200,Window('w',0,60),reserved))
        self.assertEqual(reserved,before)

    def test_delay_margin_and_previous_valve_off(self):
        w = Window('w',0,100,transition_seconds=5,closing_margin_seconds=5)
        reserved = [Pulse(0,20,'other')]
        self.assertEqual(pack(self.z,70,w,reserved),[Pulse(25,95,'bed')])
        self.assertIsNone(pack(self.z,71,w,reserved))
        self.assertEqual(pack(self.z,30,w,ready_at=60),[Pulse(60,90,'bed')])

    def test_projection_gap_unknown_delivery_disabled_and_not_due(self):
        self.assertEqual(self.planning(480,depletion=1,etc=1)['reason'],'not_due')
        self.assertEqual(self.planning(480,zone=replace(self.z,enabled=False))['reason'],'disabled')
        w=Window('w',0,480)
        args=(w,[self.z],{'garden':self.p},['normal'])
        result=plan(*args,{'bed':{'depletion_mm':12,'unresolved':['x']}},{},{})[0]
        self.assertEqual(result['reason'],'unresolved_observation')
        result=plan(*args,{'bed':{'depletion_mm':12}},{'bed':[ETPeriod(0,100,1)]},{'bed':200})[0]
        self.assertEqual(result['reason'],'missing_projection')
        self.assertFalse(result['promotion_eligible'])

    def test_full_refill_still_reports_preexisting_stress(self):
        result=self.planning(4000,depletion=20,etc=0)
        self.assertEqual(result['status'],'full')
        self.assertGreater(result['projection']['stress_seconds'],0)

    def test_partial_endpoint_cannot_hide_earlier_stress(self):
        # Delayed access causes stress first; a later 450s pulse can fix the
        # endpoint but cannot claim adequate moisture over the whole horizon.
        w=Window('w',0,1800)
        result=plan(w,[self.z],{'garden':self.p},['normal'],
                    {'bed':{'depletion_mm':14}},
                    {'bed':[ETPeriod(0,600,4),ETPeriod(600,86400,0)]},
                    {'bed':86400},reserved=[Pulse(0,1300,'other')])[0]
        self.assertEqual(result['reason'],'trajectory_not_sufficient')
        self.assertEqual(result['allocated_seconds'],0)

    def test_priority_then_relative_depletion(self):
        other=replace(self.z,id='other',station=2,group_id='high')
        w=Window('w',0,1800)
        states={'bed':{'depletion_mm':12},'other':{'depletion_mm':10}}
        projections={z.id:[ETPeriod(0,1800,0),ETPeriod(1800,86400,8)] for z in [self.z,other]}
        result=plan(w,[self.z,other],{'garden':self.p},['high','normal'],states,projections,{'bed':86400,'other':86400})
        self.assertEqual(result[0]['zone_id'],'other')
        self.assertEqual(result[0]['status'],'full')
        self.assertEqual(result[1]['status'],'skipped')
        # Same group uses greatest projected depletion first.
        result=plan(w,[self.z,replace(other,group_id='normal')],{'garden':self.p},['normal'],states,projections,{'bed':86400,'other':86400})
        self.assertEqual(result[0]['zone_id'],'bed')

    def test_promoted_zone_is_not_watered_without_demand(self):
        self.assertEqual(self.planning(480,depletion=1,etc=0,promoted={'bed'})['reason'],'not_due')

    def test_rational_runtime_cannot_overfill_to_round_up(self):
        # Full is 0.5 seconds; minimum useful runtime is one second.
        result=self.planning(480,depletion=1/300,etc=15)
        self.assertEqual(result['allocated_seconds'],0)
        self.assertEqual(result['reason'],'runtime_resolution_or_minimum_pulse')

    def test_same_valve_reservation_and_duplicate_mapping_rejected(self):
        with self.assertRaises(ValueError):
            self.planning(480,reserved=[Pulse(0,30,'bed')])

    def test_fixture_replay_is_deterministic_and_does_not_credit_plans(self):
        fixture=json.loads((ROOT/'irrigation_replay/fixtures/capacity-and-soak.json').read_text())
        result=replay(fixture)
        self.assertEqual(result,replay(fixture))
        decisions=result['windows'][0]['decisions']
        self.assertEqual([r['status'] for r in decisions],['full','partial'])
        self.assertEqual([r['allocated_seconds'] for r in decisions],[300,240])
        self.assertEqual(result['ledger_at_end']['A']['depletion_mm'],6)
        self.assertEqual(result['windows'][0]['promotions']['tokens'],{'B':'tomorrow'})

    def test_projected_stress_duration(self):
        result=project(12,self.p,self.z,[ETPeriod(0,100,6)],[])
        self.assertEqual(result['stress_seconds'],50)
        self.assertEqual(result['peak_depletion_mm'],18)


class PromotionTests(unittest.TestCase):
    def test_lifetime_duplicate_close_and_checkpoint(self):
        state=Promotions('promote_next')
        short=[dict(zone_id='a',promotion_eligible=True)]
        state.close('today',short,{'a':'tomorrow'})
        self.assertEqual(state.active('tomorrow'),{'a'})
        self.assertFalse(state.close('today',short,{'a':'later'}))
        state=Promotions.restore(json.loads(json.dumps(state.checkpoint())))
        self.assertEqual(state.active('tomorrow'),{'a'})
        state.close('tomorrow',[dict(zone_id='a',promotion_eligible=False)],{})
        self.assertEqual(state.tokens,{})

    def test_invalid_close_is_transactional(self):
        state=Promotions('promote_next')
        before=state.checkpoint()
        with self.assertRaises(ValueError):
            state.close('today',[dict(zone_id='a',promotion_eligible=True)],{'a':'today'})
        self.assertEqual(state.checkpoint(),before)

    def test_report_only_and_renewal_not_stacking(self):
        decisions=[dict(zone_id='a',promotion_eligible=True)]
        state=Promotions()
        state.close('today',decisions,{'a':'tomorrow'})
        self.assertEqual(state.tokens,{})
        state=Promotions('promote_next')
        state.close('today',decisions,{'a':'tomorrow'})
        state.close('tomorrow',decisions,{'a':'later'})
        self.assertEqual(state.tokens,{'a':'later'})


class SmallPackingOracleTests(unittest.TestCase):
    def test_small_single_zone_against_exhaustive_search(self):
        # Independently enumerate all integral pulse lengths and start times.
        # In an empty one-zone window, greedy must match exact feasibility.
        def feasible(total, end, cycle, soak, minimum, start=0):
            if total == 0:
                return True
            for duration in range(minimum,min(cycle,total)+1):
                for begin in range(start,end-duration+1):
                    if feasible(total-duration,end,cycle,soak,minimum,begin+duration+soak):
                        return True
            return False
        for cycle in range(1,5):
            for minimum in range(1,cycle+1):
                for soak in range(3):
                    zone=Zone('a',1,'p','g',1,1,cycle,soak,minimum)
                    for end in range(1,9):
                        for total in range(1,9):
                            with self.subTest(cycle=cycle,minimum=minimum,soak=soak,end=end,total=total):
                                expected=feasible(total,end,cycle,soak,minimum)
                                self.assertEqual(pack(zone,total,Window('w',0,end)) is not None,expected)


if __name__ == '__main__':
    unittest.main()
