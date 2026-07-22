"""Simple, deterministic capital simulation based on completed backtest trades."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class SimulatedTrade:
    entry_date: str
    exit_date: str
    allocated_capital: float
    realised_capital: float
    return_percent: float


class PortfolioSimulator:
    def run(self, trades: Iterable[object], config: Mapping[str, object]) -> dict[str, object]:
        settings = config["simulation"]
        initial = float(settings["initial_capital"])
        position_size, max_positions = float(settings["position_size"]), int(settings["max_positions"])
        if initial <= 0 or position_size <= 0 or max_positions < 1:
            raise ValueError("simulation settings must be positive")
        cash, active, completed = initial, [], []
        equity_curve = [("start", initial)]
        skipped = 0
        for trade in sorted(trades, key=lambda item: (item.entry_date, item.exit_date)):
            released = [item for item in active if item[0] <= trade.entry_date]
            active = [item for item in active if item[0] > trade.entry_date]
            if released:
                cash += sum(capital for _, capital in released)
                equity_curve.append((trade.entry_date, cash + sum(capital for _, capital in active)))
            if len(active) >= max_positions or cash < position_size:
                skipped += 1
                continue
            allocation = min(position_size, cash)
            cash -= allocation
            realised = allocation * (1 + float(trade.return_percent) / 100)
            active.append((trade.exit_date, realised))
            completed.append(SimulatedTrade(trade.entry_date, trade.exit_date, allocation, realised, float(trade.return_percent)))
        for exit_date, capital in sorted(active):
            cash += capital
            equity_curve.append((exit_date, cash))
        peak, max_drawdown = initial, 0.0
        for _, equity in equity_curve:
            peak = max(peak, equity)
            max_drawdown = min(max_drawdown, (equity / peak - 1) * 100)
        return {
            "initial_capital": initial, "final_capital": round(cash, 2),
            "return_percent": round((cash / initial - 1) * 100, 2),
            "realised_trade_count": len(completed), "skipped_trade_count": skipped,
            "realised_max_drawdown_percent": round(max_drawdown, 2),
            "equity_curve": [{"date": date, "equity": round(equity, 2)} for date, equity in equity_curve],
        }
