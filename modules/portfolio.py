"""Read-only valuation of user-entered portfolio positions."""
from __future__ import annotations

import sqlite3


class PortfolioAnalyzer:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def positions(self) -> dict[str, object]:
        rows = self.connection.execute(
            """SELECT p.code, p.quantity, p.average_cost, p.note, p.updated_at, m.company_name,
                 (SELECT close FROM price_daily d WHERE d.code=p.code ORDER BY trade_date DESC LIMIT 1) AS latest_close,
                 (SELECT trade_date FROM price_daily d WHERE d.code=p.code ORDER BY trade_date DESC LIMIT 1) AS price_date
               FROM portfolio_position p LEFT JOIN master_stock m ON m.code=p.code ORDER BY p.code"""
        ).fetchall()
        positions = []
        total_value = 0.0
        for row in rows:
            item = dict(row)
            close = item["latest_close"]
            cost = float(item["quantity"]) * float(item["average_cost"])
            value = float(item["quantity"]) * float(close) if close is not None else None
            item.update({"cost_basis": cost, "market_value": value, "unrealized_profit_loss": value - cost if value is not None else None})
            if value is not None:
                total_value += value
            positions.append(item)
        for item in positions:
            item["weight_percent"] = round(item["market_value"] / total_value * 100, 2) if item["market_value"] is not None and total_value else None
        return {"total_market_value": total_value, "positions": positions}
