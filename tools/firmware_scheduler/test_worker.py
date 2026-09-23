import copy
from datetime import datetime
import json
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo
from tools.firmware_scheduler.worker import observation, daily_periods, reconcile, calculate
from tools.irrigation_replay.model import Profile

class WeatherTests(unittest.TestCase):
    def setUp(self):
        self.tz=ZoneInfo('Europe/Paris')
        self.at=int(datetime(2026,9,22,tzinfo=self.tz).timestamp())
        self.now=self.at+86400+3600
        self.raw=dict(v=1,u='us',wp='Apple',h=dict(at=self.at,eto=.1,p=.2))
        self.weather=dict(days={str(self.at):observation(self.raw,self.tz,self.now)})
    def test_units_and_period(self):
        item=self.weather['days'][str(self.at)]
        self.assertAlmostEqual(item['eto_mm'],2.54)
        self.assertAlmostEqual(item['rain_mm'],5.08)
        self.assertEqual(item['end'],self.at+86400)
    def test_missing_not_zero(self):
        del self.raw['h']['p']
        with self.assertRaises(ValueError): observation(self.raw,self.tz,self.now)
    def test_bad_date_units_stale(self):
        for changes in ({'u':'mm'},{'v':2},{'h':dict(at=self.at+1,eto=.1,p=0)}):
            with self.assertRaises(ValueError):observation(dict(self.raw,**changes),self.tz,self.now)
        with self.assertRaises(ValueError):observation(self.raw,self.tz,self.now+3*86400)
    def test_missing_complete_day_blocks(self):
        with self.assertRaises(ValueError):daily_periods(self.weather,self.tz,self.at-86400,self.now,self.now)
    def test_estimate_no_rain_credit(self):
        p=daily_periods(self.weather,self.tz,self.at,self.now,self.now)
        self.assertFalse(p[0]['estimated']);self.assertTrue(p[1]['estimated'])
        self.assertEqual(p[1]['rain_mm'],0)
    def test_replay_revision_and_refill(self):
        profile=Profile('garden',100,.3,.5,1,1)
        periods=[dict(start=0,end=86400,eto_mm=8,rain_mm=0)]
        events=[dict(sid=0,at=43200,kind='refill')]
        self.assertEqual(reconcile(0,10,0,86400,profile,periods,events),4)
        periods[0]['eto_mm']=4
        self.assertEqual(reconcile(0,10,0,86400,profile,periods,events),2)
        self.assertEqual(reconcile(0,10,0,86400,profile,periods,events),2)
    def test_dst_day_length(self):
        at=int(datetime(2026,10,25,tzinfo=self.tz).timestamp())
        raw=dict(v=1,u='us',wp='Apple',h=dict(at=at,eto=.1,p=0))
        self.assertEqual(observation(raw,self.tz,at+26*3600)['end']-at,25*3600)
    def test_missing_soil_input_preserves_fixed_schedule(self):
        d=json.loads((Path(__file__).parents[1]/'irrigation_replay/fixtures/fixed-events-draft.json').read_text())
        d['version']=4;d['windows']=[];d['shortage']='report_only';d['profile']={}
        d['programs'].append(dict(id='timed:mist',scheduleMode='fixed',sid=0,name='Mist',group='Normal',enabled=True,
            amountMode='runtime',runtime=3,cycle=1,soak=1,minimum=1/60,days=list(range(7)),times=['12:15']))
        r=dict(site=dict(timezone='Europe/Paris',initial={}),draft=d,offset=7200,anchor=self.now,
               eligible=[0,1],transition=5,delivery=[],unresolved={})
        result=calculate(r,self.weather,self.now)
        self.assertTrue(result['soil_error'])
        self.assertTrue(any(e['mode']=='fixed' for e in result['events']))
    def test_valid_profile_missing_initial_only_blocks_soil(self):
        d=json.loads((Path(__file__).parents[1]/'irrigation_replay/fixtures/fixed-events-draft.json').read_text())
        d['version']=4;d['windows']=[];d['shortage']='report_only'
        d['programs'].append(dict(id='timed:mist',scheduleMode='fixed',sid=0,name='Mist',group='Normal',enabled=True,
            amountMode='runtime',runtime=3,cycle=1,soak=1,minimum=1/60,days=list(range(7)),times=['12:15']))
        r=dict(site=dict(timezone='Europe/Paris',initial={}),draft=d,offset=7200,anchor=self.now,
               eligible=[0,1],transition=5,delivery=[],unresolved={})
        result=calculate(r,self.weather,self.now)
        self.assertTrue(result['unresolved'])
        self.assertTrue(all(e['mode']=='fixed' for e in result['events']))
        self.assertTrue(result['events'])

if __name__=='__main__':unittest.main()
