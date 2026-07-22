"""Break down completed backtest trades by the regime on their signal date."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping


class RegimeBacktestAnalyzer:
    def summarize(self, trades: Iterable[object], regime_by_date: Mapping[str, str]) -> dict[str, dict[str, float | int]]:
        grouped: dict[str, list[object]] = defaultdict(list)
        for trade in trades:
            grouped[regime_by_date.get(trade.signal_date, "unknown")].append(trade)
        result = {}
        for regime, group in sorted(grouped.items()):
            returns = [float(trade.return_percent) for trade in group]
            drawdowns = [float(trade.max_drawdown_percent) for trade in group]
            result[regime] = {
                "trade_count": len(group),
                "average_return_percent": round(sum(returns) / len(returns), 2),
                "win_rate_percent": round(sum(value > 0 for value in returns) / len(returns) * 100, 2),
                "max_drawdown_percent": round(min(drawdowns), 2),
            }
        return result
