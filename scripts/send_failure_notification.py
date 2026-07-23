"""Send a minimal LINE alert when the cloud daily workflow fails."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.notifier import LineNotifier  # noqa: E402


def main() -> int:
    with (ROOT / "config" / "notification.yaml").open(encoding="utf-8") as file:
        config = yaml.safe_load(file)
    repository = os.getenv("GITHUB_REPOSITORY", "pinknokumo-glitch/Pinknokumo")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    job_label = os.getenv("STOCKAI_JOB_LABEL", "日次処理")
    run_url = f"https://github.com/{repository}/actions/runs/{run_id}" if run_id else "GitHub Actionsを確認してください。"
    timestamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    message = (
        "StockAI Navigator 障害通知\n"
        f"{job_label}が正常に完了しませんでした。\n発生時刻: {timestamp}\n確認: {run_url}\n"
        "秘密情報や認証情報は通知に含まれていません。"
    )
    result = LineNotifier(config).send(message)
    print(f"Failure notification: {result.provider} / {result.status}")
    return 0 if result.status == "sent" else 1


if __name__ == "__main__":
    raise SystemExit(main())
