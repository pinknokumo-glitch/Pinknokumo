import unittest
from pathlib import Path

import pandas as pd
import yaml

from modules.specified_analysis import analyze


class SpecifiedAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.scoring = yaml.safe_load((Path(__file__).resolve().parents[1] / 'config/scoring.yaml').read_text(encoding='utf-8'))
        self.frame = pd.DataFrame({'trade_date': ['2026-01-01', '2026-01-02', '2026-01-03'],
                                   'close': [100, 110, 90], 'high': [200, 120, 115], 'low': [1, 95, 80]})

    def test_close_entry_future_only_and_both_targets(self):
        r = analyze(self.frame, 2, 20, 20, self.scoring)
        self.assertEqual(r['summary']['trade_count'], 1)
        self.assertAlmostEqual(r['summary']['average_return_percent'], -10)
        self.assertAlmostEqual(r['summary']['max_drawdown_percent'], -20)
        self.assertEqual(r['summary']['win_rate_percent'], 0)
        self.assertEqual(r['specified_targets']['up_target_probability_percent'], 100)
        self.assertEqual(r['specified_targets']['down_target_probability_percent'], 100)
        self.assertEqual(r['specified_targets']['median_sessions_to_up_target'], 1)
        self.assertEqual(r['specified_targets']['median_sessions_to_down_target'], 2)
        self.assertEqual(r['reference_price'], 90)
        self.assertEqual(r['up_target_price'], 108)
        self.assertEqual(r['reference_date'], '2026-01-03')

    def test_short_history_is_not_zero_score(self):
        r = analyze(self.frame, 60, 20, 10, self.scoring)
        self.assertIsNone(r['expectation']['score'])
        self.assertIsNone(r['summary']['win_rate_percent'])

    def test_missing_window_is_excluded_not_compressed(self):
        self.frame.loc[1, 'close'] = float('nan')
        r = analyze(self.frame, 1, 20, None, self.scoring)
        self.assertEqual(r['summary']['trade_count'], 0)

    def test_optional_targets_and_no_entry_filter(self):
        r = analyze(self.frame, 1, None, None, self.scoring)
        self.assertEqual(r['summary']['trade_count'], 2)
        self.assertIsNone(r['specified_targets']['up_target_probability_percent'])

    def test_validation(self):
        for days, up in [(0, 20), (1001, 20), (2, float('nan')), (2, 101)]:
            with self.assertRaises(ValueError):
                analyze(self.frame, days, up, 10, self.scoring)

    def test_migration_is_independent_and_owner_scoped(self):
        sql = (Path(__file__).resolve().parents[1] / 'supabase/independent_stock_analysis_upgrade.sql').read_text(encoding='utf-8')
        self.assertNotIn('screening_preferences', sql)
        self.assertIn('uid uuid := auth.uid()', sql)
        self.assertIn('where user_id=uid', sql)
        self.assertIn('up_target_percent is not distinct from p_up', sql)
        self.assertIn('from public, anon', sql)
