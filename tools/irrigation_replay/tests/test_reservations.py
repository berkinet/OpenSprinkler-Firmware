import copy
import json
from pathlib import Path
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from tools.irrigation_replay.draft import compile_draft, InputErrors
from tools.irrigation_replay.engine import dry_run, timestamp
from tools.irrigation_replay.reservations import reservation_plan
from tools.irrigation_replay.service import legal_intervals

FIXTURES = Path(__file__).resolve().parents[1]/'fixtures'

class ReservationTests(unittest.TestCase):
    def setUp(self):
        self.draft=json.loads((FIXTURES/'editor-draft.json').read_text())
        self.runtime=json.loads((FIXTURES/'editor-runtime.json').read_text())
        self.draft['version']=5
        self.reservation=dict(id='reserved:pool',scheduleMode='reservation',name='Indigo pool refill',enabled=True,
                              days=[0],times=['06:02'],duration=2)
        self.runtime['resource']['transition_seconds']=5
        self.draft['programs'].append(self.reservation)
    def test_blocks_all_soil_with_transition_and_no_valve_or_credit(self):
        for window in self.draft['windows']: window['end']='07:00'
        r=dry_run(self.draft,self.runtime)
        block=r['reservations'][0]
        self.assertEqual(block['pulses'],[])
        self.assertNotIn('sid',block)
        self.assertEqual(block['end']-block['start'],120)
        self.assertEqual(block['start']-block['blocked_start'],self.runtime['resource']['transition_seconds'])
        pulses=[p for d in r['decisions'] for p in d['pulses']]
        self.assertTrue(pulses)
        self.assertTrue(all(p['end']<=block['blocked_start'] or p['start']>=block['blocked_end'] for p in pulses))
    def test_fixed_highest_priority_cannot_override(self):
        self.draft['programs'].append(dict(id='timed:mist',scheduleMode='fixed',sid=0,name='Mist',enabled=True,
            group=self.draft['groups'][0],amountMode='runtime',runtime=1,cycle=1,soak=0,minimum=1/60,
            days=list(range(7)),times=['06:02']))
        r=dry_run(self.draft,self.runtime)
        self.assertEqual(r['fixed_decisions'][0]['reason'],'external_reservation')
        self.assertFalse(r['fixed_decisions'][0]['pulses'])
    def test_independent_of_calibration_valves_weather_and_watering_restrictions(self):
        self.draft['programs']=[self.reservation];self.draft['profile']={}
        self.draft['windows']=[dict(days=[6],start='20:00',end='21:00')]
        self.draft['excluded']=self.runtime['as_of'][:10]
        self.runtime.update(eligible_station_sids=[],states={})
        self.runtime.pop('weather');self.runtime.pop('next_service')
        r=dry_run(self.draft,self.runtime)
        self.assertTrue(r['reservations']);self.assertEqual(r['decisions'],[])
    def test_disabled_inert_and_schema_mutually_exclusive(self):
        self.reservation['enabled']=False
        self.assertEqual(dry_run(self.draft,self.runtime)['reservations'],[])
        for key,value in [('sid',0),('group','Normal'),('runtime',5),('profile','garden')]:
            d=copy.deepcopy(self.draft);d['programs'][-1][key]=value
            with self.assertRaises(InputErrors):compile_draft(d)
    def test_invalid_duration_days_times_and_identity(self):
        for key,value in [('duration',0),('duration',1441),('duration',0.001),('days',[]),('times',['25:00']),('times',['06:00','06:00']),('id','timed:bad')]:
            d=copy.deepcopy(self.draft);d['programs'][-1][key]=value
            with self.assertRaises(InputErrors):compile_draft(d)
        self.draft['programs'].append(copy.deepcopy(self.reservation))
        with self.assertRaises(InputErrors):compile_draft(self.draft)
    def test_overlapping_reservations_merge_without_priority(self):
        self.draft['programs'].append(dict(self.reservation,id='reserved:other',times=['06:03']))
        now=timestamp(self.runtime['as_of'])
        rows,blocks=reservation_plan(compile_draft(self.draft),now,now+3600,ZoneInfo(self.runtime['timezone']),5)
        self.assertEqual(len(rows),2);self.assertEqual(len(blocks),1)
        self.assertEqual(blocks[0][1]-blocks[0][0],190)
    def test_restart_inside_previous_days_reservation(self):
        self.reservation.update(times=['23:50'],duration=30,days=[0])
        tz=ZoneInfo('Europe/Paris');now=int(datetime(2026,9,22,0,5,tzinfo=tz).timestamp())
        rows,blocks=reservation_plan(compile_draft(self.draft),now,now+86400,tz,5)
        self.assertEqual(len(rows),1);self.assertLess(blocks[0][0],now);self.assertGreater(blocks[0][1],now)
        self.assertEqual(rows[0]['local_end'],'2026-09-22T00:20:00+02:00')
    def test_dst_ambiguous_both_occurrences_and_nonexistent_not_dropped(self):
        self.reservation.update(times=['02:30'],duration=15,days=list(range(7)))
        tz=ZoneInfo('Europe/Paris')
        for month,day,elapsed in [(10,25,4500),(3,29,900)]:
            now=int(datetime(2026,month,day,tzinfo=tz).timestamp())
            rows,_=reservation_plan(compile_draft(self.draft),now,now+4*3600,tz,5)
            self.assertEqual(rows[0]['duration_seconds'],elapsed)
            if month==3:self.assertIn('T03:00:00',rows[0]['local_start'])
    def test_future_service_intervals_exclude_reservations(self):
        now=timestamp(self.runtime['as_of']);tz=ZoneInfo(self.runtime['timezone']);config=compile_draft(self.draft)
        intervals,last=legal_intervals(self.draft,config,now,tz,None,5)
        _,blocks=reservation_plan(config,now,now+8*86400,tz,5)
        self.assertTrue(intervals)
        for values in intervals.values():
            self.assertTrue(all(b<=c or a>=d for a,b in values for c,d in blocks))

if __name__=='__main__':unittest.main()
