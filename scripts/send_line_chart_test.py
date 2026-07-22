"""Send one LINE notification containing a published stock chart."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.notifier import LineNotifier  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", default="72030")
    args = parser.parse_args()

    with (ROOT / "config" / "notification.yaml").open(encoding="utf-8") as file:
        config = yaml.safe_load(file)

    notifier = LineNotifier(config)
    chart_urls = notifier.chart_urls([args.code])
    message = (
        "StockAI Navigator\n"
        "チャート付きLINE通知の接続テストです。\n"
        f"銘柄コード: {args.code}\n"
        "※投資判断はご自身で行ってください。"
    )
    result = notifier.send(message, chart_urls)
    print(f"status={result.status}")
    print(f"images={len(chart_urls)}")
    if result.response_text:
        print(f"response={result.response_text[:300]}")
    return 0 if result.status == "sent" else 1


if __name__ == "__main__":
    raise SystemExit(main())
