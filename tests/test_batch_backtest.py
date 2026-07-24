from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from modules.batch_backtest import BatchBacktester
from modules.database import Database


INDICATORS_DISABLED = {
    "indicators": {
        "rsi": {"enabled": False},
        "macd": {"enabled": False},
        "moving_average": {"enabled": False},
        "bollinger_bands": {"enabled": False},
        "stochastic": {"enabled": False},
        "adx": {"enabled": False},
        "atr": {"enabled": False},
    }
}

SCORING = {
    "expectation_score": {
        "weights": {
            "average_return": 0.4,
            "win_rate": 0.25,
            "max_drawdown": 0.2,
            "sample_size": 0.15,
        },
        "targets": {
            "average_return_percent": 10,
            "win_rate_percent": 60,
            "max_drawdown_percent": -15,
            "sample_size": 50,
        },
    }
}


class CandidateBatchBacktestTests(unittest.TestCase):
    def test_explicit_codes_limit_analysis_to_matching_stocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "stockai.db")
            database.initialize()
            dates = pd.bdate_range("2025-01-01", periods=90)
            rows = []
            for code in ("11110", "22220"):
                for offset, trade_date in enumerate(dates):
                    close = 100 + offset
                    rows.append({
                        "code": code,
                        "trade_date": trade_date.date().isoformat(),
                        "open": close,
                        "high": close + 1,
                        "low": close - 1,
                        "close": close,
                        "adjusted_close": close,
                        "volume": 1000,
                        "dividends": 0,
                        "stock_splits": 0,
                    })
            database.upsert_rows("price_daily", rows, ["code", "trade_date"])

            result = BatchBacktester(
                database,
                INDICATORS_DISABLED,
                {"backtest": {}},
                SCORING,
            ).run(
                "matched_only",
                {"field": "daily.close", "operator": ">", "value": 0},
                holding_days=20,
                codes=["22220", "22220"],
            )

            self.assertEqual(result["processed_count"], 1)
            self.assertEqual(result["results"][0]["code"], "22220")
            with database.connect() as connection:
                saved_codes = [
                    row[0] for row in connection.execute(
                        "SELECT code FROM analysis_snapshot ORDER BY code"
                    )
                ]
            self.assertEqual(saved_codes, ["22220"])


if __name__ == "__main__":
    unittest.main()
