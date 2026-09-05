import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from modules.database import Database
from scripts import run_backtest_requests as worker


class RequestedAnalysisTests(unittest.TestCase):
    def run_worker(self, dataset='123', claimed=True):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / 'test.db')
            database.initialize()
            with database.connect() as conn:
                conn.execute('CREATE TABLE evening_analysis_codes(code TEXT PRIMARY KEY)')
                conn.execute("INSERT INTO evening_analysis_codes VALUES ('7203')")
            item = {'id': 7, 'user_id': 'owner', 'code': '7203',
                    'dataset_run_id': dataset, 'input_snapshot': {'holding_days': 250}}
            preference = MagicMock(holding_days=250, trade_direction='long',
                                   expectation_evaluation_mode='period_end', target_return_percent=5)
            def http(url, key, method, path, payload=None):
                if method == 'GET':
                    return [item]
                if path.endswith('&status=eq.pending'):
                    return [item] if claimed else []
                return []
            with patch.dict('os.environ', {'SUPABASE_URL': 'https://test', 'SUPABASE_SERVICE_ROLE_KEY': 'test'}), \
                 patch.object(worker, 'Database', return_value=database), \
                 patch.object(worker, 'request', side_effect=http) as send, \
                 patch.object(worker.CloudPreferenceClient, 'validate', return_value=preference) as validate, \
                 patch.object(worker.CloudPreferenceClient, 'fetch_all', side_effect=AssertionError('must use snapshot')), \
                 patch.object(worker, 'apply_preference', return_value=({'profiles': {'x': {}}}, 'x')), \
                 patch.object(worker, 'apply_expectation_preference', return_value=({'profiles': {'x': {}}}, 'x')), \
                 patch.object(worker, 'preference_signature', return_value='snapshot'), \
                 patch.object(worker, 'BatchBacktester') as backtest, \
                 patch.object(worker.StockRepository, 'latest_backtest_result', return_value={'summary': {}}):
                status = worker.main('7', '123')
            return status, send.call_args_list, validate, backtest

    def test_uses_saved_snapshot_and_computes_only_one_code(self):
        status, calls, validate, backtest = self.run_worker()
        self.assertEqual(status, 0)
        self.assertEqual(validate.call_args.args[0], {'holding_days': 250})
        self.assertEqual(backtest.return_value.run.call_args.kwargs['codes'], ['7203'])
        self.assertEqual(backtest.return_value.run.call_args.args[2], 250)
        self.assertEqual(calls[-1].args[4]['status'], 'complete')
        self.assertEqual(calls[-1].args[4]['result_json']['dataset_run_id'], '123')

    def test_mismatched_snapshot_fails_without_computing(self):
        status, calls, _, backtest = self.run_worker(dataset='124')
        self.assertEqual(status, 1)
        backtest.assert_not_called()
        self.assertEqual(calls[-1].args[4]['status'], 'failed')

    def test_already_claimed_request_is_not_recomputed(self):
        status, _, _, backtest = self.run_worker(claimed=False)
        self.assertEqual(status, 0)
        backtest.assert_not_called()


if __name__ == '__main__':
    unittest.main()
