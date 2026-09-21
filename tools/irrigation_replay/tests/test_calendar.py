import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from tools.irrigation_replay.calendar import resolve_calendar, normalize


class CalendarTests(unittest.TestCase):
    def test_overlap_normalized(self):
        self.assertEqual(normalize([(0,10),(5,15),(15,20),(30,40)]),[(0,20),(30,40)])

    def test_overnight_excluded_second_day(self):
        result=resolve_calendar('Europe/Paris','2026-09-21','2026-09-22',range(7),[(1380,60)],['2026-09-22'])
        tz=ZoneInfo('Europe/Paris')
        local=[(datetime.fromtimestamp(a,tz).isoformat(),datetime.fromtimestamp(b,tz).isoformat()) for a,b in result]
        self.assertEqual(local,[('2026-09-21T00:00:00+02:00','2026-09-21T01:00:00+02:00'),
                                ('2026-09-21T23:00:00+02:00','2026-09-22T00:00:00+02:00')])

    def test_dst_spring_missing_boundary(self):
        result=resolve_calendar('Europe/Paris','2026-03-29','2026-03-29',[6],[(150,210)])
        self.assertEqual(result[0][1]-result[0][0],1800)

    def test_dst_fall_ambiguous_boundaries(self):
        # Late 02:15 opening is later than early 02:45 close: conservative empty window.
        self.assertEqual(resolve_calendar('Europe/Paris','2026-10-25','2026-10-25',[6],[(135,165)]),[])
        result=resolve_calendar('Europe/Paris','2026-10-25','2026-10-25',[6],[(135,210)])
        self.assertEqual(result[0][1]-result[0][0],4500)

    def test_empty_or_invalid_rules(self):
        with self.assertRaises(ValueError):
            resolve_calendar('Europe/Paris','2026-09-21','2026-09-22',[0],[(60,60)])
        self.assertEqual(resolve_calendar('Europe/Paris','2026-09-21','2026-09-21',[1],[(0,1440)]),[])


if __name__ == '__main__':
    unittest.main()
