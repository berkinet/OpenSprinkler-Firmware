import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from tools.valve_sim.automatic import Simulation


class Receiver:
    def __init__(self):
        self.session='test'; self.states={f'zone{i}':False for i in range(1,17)}; self.commands=[]
    def status(self):
        return dict(session=self.session, states=copy.deepcopy(self.states))
    def set(self,sid,on):
        self.states[f'zone{sid+1}']=on; self.commands.append((sid,on))
        self.assert_single()
    def assert_single(self):
        if sum(self.states.values())>1: raise AssertionError('Two valves active')


def draft():
    return dict(version=4,groups=['High','Low'],windows=[],excluded='',shortage='report_only',profile={},programs=[
        dict(sid=0,name='Soil',profile='garden',group='High',enabled=True,amountMode='runtime',
             runtime=5,cycle=1,soak=1,minimum=1/60,rate='',efficiency='',depth='',permittedHours={'mode':'all'}),
        dict(id='timed:mist',scheduleMode='fixed',sid=0,name='Mist',group='High',enabled=True,
             amountMode='runtime',runtime=1,cycle=1,soak=0,minimum=1/60,days=list(range(7)),times=['12:01'],permittedHours={'mode':'all'})])


class AutomaticTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.receiver=Receiver()
        self.sim=Simulation(self.temp.name,receiver=self.receiver,timezone_name='UTC')
        self.now=int(datetime(2026,9,23,12,0,tzinfo=timezone.utc).timestamp())
        self.sim.state['clock']=self.now
        self.sim.configure(draft())

    def step(self):
        self.sim.advance(self.sim.next_boundary())

    def through(self, target):
        for _ in range(200):
            self.sim.advance(min(target,self.sim.next_boundary()))
            if self.sim.state['clock']>=target: return
        self.fail('Clock failed to advance')

    def test_runtime_full_credit_only_after_all_pulses_and_mist_never_refills(self):
        self.step()
        soil=next(e for e in self.sim.state['events'] if not e['fixed'])
        mist=next(e for e in self.sim.state['events'] if e['fixed'])
        self.through(mist['pulses'][-1]['end'])
        self.assertGreater(self.sim.state['balances']['0'],15)
        self.assertFalse(mist['credited'])
        self.through(soil['pulses'][-1]['end'])
        self.assertEqual(self.sim.state['balances']['0'],0)
        self.assertTrue(soil['credited'])
        self.assertFalse(any(self.receiver.states.values()))
        self.assertEqual(sum(r['kind']=='completed' and r.get('refill') for r in self.sim.state['records']),1)
        self.sim.advance(self.sim.state['clock'])
        self.assertEqual(sum(r['kind']=='completed' and r.get('refill') for r in self.sim.state['records']),1)

    def test_restart_interrupts_active_event_without_replaying_on_or_credit(self):
        self.step(); self.step()
        self.assertTrue(any(self.receiver.states.values()))
        restarted=Simulation(self.temp.name,receiver=self.receiver,timezone_name='UTC')
        restarted.recover()
        self.assertFalse(any(self.receiver.states.values()))
        self.assertTrue(any(e['status']=='interrupted' for e in restarted.state['events']))
        self.assertGreater(restarted.state['balances']['0'],0)
        before=len(self.receiver.commands)
        restarted.advance(restarted.state['clock'])
        self.assertEqual(len(self.receiver.commands),before)

    def test_complete_persistence_and_idempotent_config_application(self):
        self.through(self.now+1000)
        self.sim.persist()  # explicit checkpoint; the live loop checkpoints every ten seconds
        before=copy.deepcopy(self.sim.state)
        self.sim.configure(draft())
        self.assertEqual(self.sim.state,before)
        restored=Simulation(self.temp.name,receiver=self.receiver,timezone_name='UTC')
        restored.recover()
        self.assertEqual(restored.state['balances'],before['balances'])
        self.assertEqual(restored.state['events'],before['events'])

    def test_profile_assumptions_do_not_change_input_draft(self):
        original=draft(); before=copy.deepcopy(original)
        self.sim.configure(original)
        self.assertEqual(original,before)
        self.assertEqual(self.sim.state['draft']['profile'],{})
        self.assertEqual(len(self.sim.snapshot()['assumed_profile_fields']),5)

    def test_multi_day_balance_changes_frequency_not_runtime(self):
        self.through(self.now+5*86400)
        runs=[r for r in self.sim.state['records'] if r['kind']=='completed' and r.get('name')=='Soil']
        self.assertGreaterEqual(len(runs),2)
        self.assertLess(len(runs),5)
        self.assertEqual({r['seconds'] for r in runs},{300})
        self.assertTrue(any(r.get('detail')=='not_due' for r in self.sim.state['records']))

    def test_fixed_priority_skips_conflict_and_restrictions_are_hard(self):
        d=draft(); d['programs']=[d['programs'][1],dict(d['programs'][1],id='timed:low',sid=1,name='Low mist',group='Low')]
        d['defaultHours']={'mode':'all'}; self.sim.configure(d); self.step()
        self.assertTrue(any(r.get('detail')=='priority_conflict' for r in self.sim.state['records']))
        self.through(self.now+180)
        self.assertNotIn((1,True),self.receiver.commands)
        d['programs'][0]['permittedHours']={'mode':'custom','start':'13:00','end':'14:00'}
        self.sim.configure(d); self.step()
        self.assertTrue(any(r.get('detail')=='watering_restriction' for r in self.sim.state['records']))

    def test_pause_freezes_clock_and_resume_does_not_refill_interruption(self):
        self.step(); self.step()
        self.sim.control('pause'); now=self.sim.state['clock']; before=self.sim.state['balances']['0']
        self.assertFalse(any(self.receiver.states.values()))
        self.sim.advance(now+3600)
        self.assertEqual(self.sim.state['clock'],now)
        self.sim.control('resume'); self.sim.advance(now)
        self.assertEqual(self.sim.state['balances']['0'],before)

    def test_invalid_update_preserves_running_configuration(self):
        before=copy.deepcopy(self.sim.state); bad=draft(); bad['programs'][0]['cycle']=''
        with self.assertRaises(ValueError): self.sim.configure(bad)
        self.assertEqual(self.sim.state,before)

    def test_receiver_restart_blocks_until_reconciled(self):
        self.step(); self.receiver.session='replacement'
        with self.assertRaisesRegex(ValueError,'restarted'): self.step()
        self.sim.control('resume'); self.step()

    def test_fixed_only_requires_no_calibration_and_stays_on_exact_time(self):
        d=draft(); d['programs']=d['programs'][1:]; self.sim.configure(d)
        self.step(); self.assertFalse(any(self.receiver.states.values()))
        self.step(); self.assertEqual(self.sim.state['clock'],self.now+60)
        self.assertTrue(self.receiver.states['zone1'])
        self.step(); self.assertFalse(self.receiver.states['zone1'])
        self.assertEqual(self.sim.state['balances'],{})
