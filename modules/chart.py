"""Dependency-free SVG price charts built from locally stored prices."""
from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from typing import Iterable


class StockChartRenderer:
    """Render a compact candlestick chart without contacting an external service."""

    width = 1200
    height = 675
    margin_left = 78
    margin_right = 28
    margin_top = 58
    margin_bottom = 62

    @classmethod
    def render(cls, code: str, prices: Iterable[dict[str, object]], company_name: str | None = None) -> str:
        rows = list(prices)
        if not rows:
            raise ValueError("No prices available for chart")
        rows = rows[-180:]
        values = [float(row[key]) for row in rows for key in ("low", "high") if row.get(key) is not None]
        if not values:
            raise ValueError("Chart prices must contain high and low values")
        low, high = min(values), max(values)
        padding = max((high - low) * 0.06, 1.0)
        low, high = low - padding, high + padding
        plot_width = cls.width - cls.margin_left - cls.margin_right
        plot_height = cls.height - cls.margin_top - cls.margin_bottom

        def x(index: int) -> float:
            return cls.margin_left + (plot_width * index / max(len(rows) - 1, 1))

        def y(value: float) -> float:
            return cls.margin_top + ((high - value) / (high - low)) * plot_height

        def moving_average(window: int) -> list[float | None]:
            closes = [float(row["close"]) for row in rows]
            return [None if index + 1 < window else sum(closes[index - window + 1:index + 1]) / window for index in range(len(closes))]

        def line_path(series: list[float | None]) -> str:
            commands: list[str] = []
            started = False
            for index, value in enumerate(series):
                if value is None:
                    started = False
                    continue
                commands.append(f"{'M' if not started else 'L'} {x(index):.1f} {y(value):.1f}")
                started = True
            return " ".join(commands)

        grid = []
        for step in range(5):
            value = low + ((high - low) * step / 4)
            position = y(value)
            grid.append(f'<line x1="{cls.margin_left}" y1="{position:.1f}" x2="{cls.width - cls.margin_right}" y2="{position:.1f}" class="grid"/>')
            grid.append(f'<text x="{cls.margin_left - 10}" y="{position + 5:.1f}" class="axis" text-anchor="end">{value:,.0f}</text>')
        candles = []
        body_width = max(2.0, min(8.0, plot_width / len(rows) * 0.62))
        for index, row in enumerate(rows):
            open_, close = float(row["open"]), float(row["close"])
            color = "#d94747" if close >= open_ else "#3478bd"
            top, bottom = min(y(open_), y(close)), max(y(open_), y(close))
            candles.append(f'<line x1="{x(index):.1f}" y1="{y(float(row["high"])):.1f}" x2="{x(index):.1f}" y2="{y(float(row["low"])):.1f}" stroke="{color}" stroke-width="1"/>')
            candles.append(f'<rect x="{x(index) - body_width / 2:.1f}" y="{top:.1f}" width="{body_width:.1f}" height="{max(bottom - top, 1):.1f}" fill="{color}"/>')
        labels = []
        for index in sorted({0, len(rows) // 2, len(rows) - 1}):
            label = str(rows[index]["trade_date"])
            labels.append(f'<text x="{x(index):.1f}" y="{cls.height - 28}" class="axis" text-anchor="middle">{escape(label)}</text>')
        latest = rows[-1]
        title = f'{company_name} ({code})' if company_name else code
        return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{cls.width}" height="{cls.height}" viewBox="0 0 {cls.width} {cls.height}" role="img" aria-label="{escape(title)} price chart">
  <style>.title{{font:600 24px sans-serif;fill:#1f2937}}.sub{{font:14px sans-serif;fill:#4b5563}}.axis{{font:13px sans-serif;fill:#4b5563}}.grid{{stroke:#d1d5db;stroke-width:1}}.sma25{{fill:none;stroke:#e08b17;stroke-width:2}}.sma75{{fill:none;stroke:#7d4fc1;stroke-width:2}}</style>
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="{cls.margin_left}" y="30" class="title">{escape(title)} 日足</text>
  <text x="{cls.margin_left}" y="50" class="sub">終値 {float(latest['close']):,.0f}　表示期間 {escape(str(rows[0]['trade_date']))} — {escape(str(latest['trade_date']))}</text>
  {''.join(grid)}
  {''.join(candles)}
  <path d="{line_path(moving_average(25))}" class="sma25"/>
  <path d="{line_path(moving_average(75))}" class="sma75"/>
  <line x1="{cls.margin_left}" y1="{cls.height - cls.margin_bottom}" x2="{cls.width - cls.margin_right}" y2="{cls.height - cls.margin_bottom}" class="grid"/>
  {''.join(labels)}
  <line x1="{cls.width - 245}" y1="32" x2="{cls.width - 220}" y2="32" class="sma25"/><text x="{cls.width - 212}" y="37" class="sub">25日移動平均</text>
  <line x1="{cls.width - 118}" y1="32" x2="{cls.width - 93}" y2="32" class="sma75"/><text x="{cls.width - 85}" y="37" class="sub">75日移動平均</text>
</svg>'''

    @staticmethod
    def write(svg: str, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(svg, encoding="utf-8")
        return destination

    @staticmethod
    def default_path(root: str | Path, code: str) -> Path:
        stamp = datetime.now().strftime("%Y%m%d")
        return Path(root) / "reports" / "charts" / f"{code}_{stamp}.svg"
