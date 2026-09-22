"""Cross-language SunCalc parity and timezone/overnight handling."""
from datetime import date
import json
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo
from tools.irrigation_replay.solar import sun_times, night_intervals

class SolarTests(unittest.TestCase):
    def test_matches_bundled_suncalc_on_normal_and_dst_dates(self):
        fixtures = Path(__file__).resolve().parents[1]/'fixtures'/'solar-reference.json'
        for item in json.loads(fixtures.read_text()):
            rise, setting = sun_times(date.fromisoformat(item['date']), ZoneInfo(item['timezone']), item['latitude'], item['longitude'])
            self.assertAlmostEqual(rise, item['sunrise'], delta=.002)
            self.assertAlmostEqual(setting, item['sunset'], delta=.002)

    def test_night_uses_next_dates_sunrise_and_rejects_missing_polar_events(self):
        day = date(2026, 10, 24)
        tz = ZoneInfo('Europe/Paris')
        intervals = night_intervals('Europe/Paris', day, day, dict(latitude=48.8566, longitude=2.3522))
        tomorrow = sun_times(date(2026, 10, 25), tz, 48.8566, 2.3522)
        self.assertLess(abs(intervals[-1][1]-tomorrow[0]), 1)
        self.assertGreater(intervals[-1][1]-intervals[-1][0], 12*3600)
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            night_intervals('Europe/Paris', date(2026, 6, 21), date(2026, 6, 21), dict(latitude=89, longitude=0))
