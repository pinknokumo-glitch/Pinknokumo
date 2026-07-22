"""Generate a LINE-compatible PNG from locally stored price data.

This script does not upload or publish the resulting image.
"""
from __future__ import annotations

import argparse
import sys
import struct
import zlib
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.chart import StockChartRenderer
from modules.database import Database
from modules.repository import StockRepository

def _write_png(path: Path, width: int, height: int, pixels: bytearray) -> None:
    """Write an RGB PNG with only the standard library."""
    rows = b"".join(b"\x00" + pixels[row * width * 3:(row + 1) * width * 3] for row in range(height))
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def _render_pixels(prices: list[dict[str, object]]) -> tuple[int, int, bytearray]:
    width, height, margin_left, margin_right, margin_top, margin_bottom = 1200, 675, 78, 28, 58, 62
    pixels = bytearray([255, 255, 255]) * (width * height)
    rows = prices[-180:]
    lows_highs = [float(row[key]) for row in rows for key in ("low", "high")]
    low, high = min(lows_highs), max(lows_highs)
    padding = max((high - low) * 0.06, 1.0)
    low, high = low - padding, high + padding
    plot_width, plot_height = width - margin_left - margin_right, height - margin_top - margin_bottom

    def x(index: int) -> int:
        return round(margin_left + plot_width * index / max(len(rows) - 1, 1))
    def y(value: float) -> int:
        return round(margin_top + ((high - value) / (high - low)) * plot_height)
    def pixel(px: int, py: int, color: tuple[int, int, int]) -> None:
        if 0 <= px < width and 0 <= py < height:
            start = (py * width + px) * 3
            pixels[start:start + 3] = bytes(color)
    def line(x1: int, y1: int, x2: int, y2: int, color: tuple[int, int, int], thickness: int = 1) -> None:
        steps = max(abs(x2 - x1), abs(y2 - y1), 1)
        for step in range(steps + 1):
            px, py = round(x1 + (x2 - x1) * step / steps), round(y1 + (y2 - y1) * step / steps)
            for dx in range(-(thickness // 2), thickness // 2 + 1):
                for dy in range(-(thickness // 2), thickness // 2 + 1):
                    pixel(px + dx, py + dy, color)
    def rect(left: int, top: int, right: int, bottom: int, color: tuple[int, int, int]) -> None:
        for py in range(max(0, top), min(height, bottom + 1)):
            for px in range(max(0, left), min(width, right + 1)):
                pixel(px, py, color)
    for step in range(5):
        grid_y = y(low + (high - low) * step / 4)
        line(margin_left, grid_y, width - margin_right, grid_y, (220, 224, 230))
    body_width = max(2, min(8, round(plot_width / len(rows) * 0.62)))
    for index, row in enumerate(rows):
        open_, close = float(row["open"]), float(row["close"])
        color = (217, 71, 71) if close >= open_ else (52, 120, 189)
        line(x(index), y(float(row["high"])), x(index), y(float(row["low"])), color)
        top, bottom = sorted((y(open_), y(close)))
        rect(x(index) - body_width // 2, top, x(index) + body_width // 2, max(top + 1, bottom), color)
    closes = [float(row["close"]) for row in rows]
    for window, color in ((25, (224, 139, 23)), (75, (125, 79, 193))):
        previous = None
        for index in range(window - 1, len(closes)):
            point = (x(index), y(sum(closes[index - window + 1:index + 1]) / window))
            if previous:
                line(*previous, *point, color, 2)
            previous = point
    return width, height, pixels


def render(code: str, output_path: str | None = None) -> Path:
    with (ROOT / "config" / "settings.yaml").open(encoding="utf-8") as file:
        settings = yaml.safe_load(file)
    database = Database(ROOT / settings["database"]["path"])
    database.initialize()
    with database.connect() as connection:
        repository = StockRepository(connection)
        prices = repository.prices(code, "daily", limit=180)
        overview = repository.overview(code)
    company_name = (overview or {}).get("master", {}).get("company_name") if (overview or {}).get("master") else None
    svg = StockChartRenderer.render(code, prices, company_name)
    chart_dir = ROOT / "reports" / "charts"
    stamp = datetime.now().strftime("%Y%m%d")
    svg_path = chart_dir / f"{code}_{stamp}.svg"
    png_path = Path(output_path) if output_path else chart_dir / f"{code}_{stamp}.png"
    StockChartRenderer.write(svg, svg_path)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    width, height, pixels = _render_pixels(prices)
    _write_png(png_path, width, height, pixels)
    if not png_path.exists() or png_path.stat().st_size == 0:
        raise RuntimeError("PNG chart generation failed")
    return png_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render a local LINE-compatible chart PNG")
    parser.add_argument("--code", default="72030")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    print(f"Chart written: {render(args.code, args.output)}")
