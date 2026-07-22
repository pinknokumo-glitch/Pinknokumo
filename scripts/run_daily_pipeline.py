"""Run the daily refresh, report, chart publication, and optional LINE notification."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.daily_job import DailyUpdateJob  # noqa: E402
from modules.ai_comment import AnalysisCommentary  # noqa: E402
from modules.batch_backtest import BatchBacktester  # noqa: E402
from modules.database import Database  # noqa: E402
from modules.github_publisher import GitHubPublisher  # noqa: E402
from modules.notifier import LineNotifier, format_candidate_message, format_screening_message  # noqa: E402
from modules.reporting import DailyReportBuilder  # noqa: E402
from modules.repository import StockRepository  # noqa: E402
from modules.screener import Screener  # noqa: E402
from scripts.render_chart_png import render  # noqa: E402


def load_yaml(path: str) -> dict:
    with (ROOT / path).open(encoding="utf-8") as file:
        return yaml.safe_load(file)


def publish_charts(codes: list[str], repository: str) -> list[str]:
    load_dotenv(ROOT / ".env")
    publisher = GitHubPublisher(repository, os.getenv("GITHUB_CHARTS_TOKEN", ""))
    urls = []
    for code in codes:
        chart_path = render(code)
        remote_path = f"charts/{code}.png"
        publisher.upload_file(chart_path, remote_path, f"Update {code} chart")
        urls.append(publisher.public_url(remote_path))
    return urls


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the StockAI daily pipeline")
    parser.add_argument("--notify", action="store_true", help="Publish charts and send the result to LINE")
    parser.add_argument("--skip-update", action="store_true", help="Use the data currently stored in SQLite")
    parser.add_argument("--skip-backtest", action="store_true", help="Skip score and commentary refresh")
    parser.add_argument("--holding-days", type=int, default=60)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--repository", default="pinknokumo-glitch/Pinknokumo")
    args = parser.parse_args()

    settings = load_yaml("config/settings.yaml")
    indicators = load_yaml("config/indicators.yaml")
    screening = load_yaml("config/screening.yaml")
    regime = load_yaml("config/regime.yaml")
    backtest = load_yaml("config/backtest.yaml")
    scoring = load_yaml("config/scoring.yaml")
    notification = load_yaml("config/notification.yaml")
    profile = args.profile or screening["active_profile"]

    database = Database(ROOT / settings["database"]["path"])
    database.initialize()
    update = None
    if not args.skip_update:
        update = DailyUpdateJob(database, settings, regime).run()
        print(json.dumps({"daily_update": update}, ensure_ascii=False, indent=2))

    if not args.skip_backtest:
        rule = screening["profiles"].get(profile)
        if rule is None:
            raise ValueError(f"Unknown profile: {profile}")
        analysis = BatchBacktester(database, indicators, backtest, scoring).run(
            profile, rule, args.holding_days,
        )
        database.save_job_run(
            "daily_backtest",
            "success" if not analysis["failed_count"] else "partial_failure",
            analysis,
        )
        print(json.dumps({"daily_backtest": {
            "profile": profile,
            "processed_count": analysis["processed_count"],
            "failed_count": analysis["failed_count"],
        }}, ensure_ascii=False, indent=2))

    with database.connect() as connection:
        hits = Screener(connection, indicators, screening).run(profile)
        screening_date = connection.execute("SELECT MAX(trade_date) FROM price_daily").fetchone()[0]
        repository = StockRepository(connection)
        comments = {}
        for hit in hits:
            code = str(hit["code"])
            result = repository.latest_backtest_result(code, profile)
            backtest_comment = str(result["comment"]) if result and result.get("comment") else None
            comments[code] = AnalysisCommentary.integrated_comment(hit, backtest_comment)
        report = DailyReportBuilder(connection).build()
    report_path = DailyReportBuilder.write(report, DailyReportBuilder.default_path(ROOT))
    print(f"Report written: {report_path}")
    print(f"Screening: {profile} / {len(hits)} matching stocks")

    if not args.notify:
        return 0

    line_config = notification["notification"]["line"]
    max_candidates = int(line_config["max_candidates"])
    max_images = int(line_config.get("max_chart_images", 3))
    delivery_limit = min(max_candidates, max_images)
    delivery_hits = hits[:delivery_limit]
    codes = [str(hit["code"]) for hit in delivery_hits]
    chart_urls = []
    chart_warning = None
    if codes:
        try:
            chart_urls = publish_charts(codes, args.repository)
        except Exception as error:
            chart_warning = f"チャート更新失敗: {type(error).__name__}"
            print(f"Warning: {chart_warning}")
    warnings = []
    if update and (update.get("failed") or update.get("financial_failed")):
        failed_count = len(update.get("failed", [])) + len(update.get("financial_failed", []))
        warnings.append(f"データ更新の一部に失敗しました（{failed_count}件）。")
    if chart_warning:
        warnings.append("チャートを更新できなかったため、今回はテキストのみ送信します。")
    notifier = LineNotifier(notification)
    if not delivery_hits:
        message = format_screening_message(profile, hits, max_candidates, comments, screening_date)
        if warnings:
            message += "\n\n注意:\n" + "\n".join(f"- {warning}" for warning in warnings)
        result = notifier.send(message)
        database.save_notification(result.provider, result.status, message, result.response_text)
        print(f"Notification: {result.provider} / {result.status} / candidates=0")
        return 0 if result.status == "sent" else 1

    results = []
    for index, hit in enumerate(delivery_hits):
        code = str(hit["code"])
        message = format_candidate_message(
            profile, hit, index + 1, len(delivery_hits), comments.get(code), screening_date,
        )
        if index == len(delivery_hits) - 1:
            omitted = len(hits) - len(delivery_hits)
            if omitted > 0:
                message += f"\n\nほか{omitted}件（配信上限のため省略）"
            if warnings:
                message += "\n\n注意:\n" + "\n".join(f"- {warning}" for warning in warnings)
        candidate_chart = chart_urls[index:index + 1]
        result = notifier.send(message, candidate_chart)
        database.save_notification(result.provider, result.status, message, result.response_text)
        results.append(result)
        print(
            f"Notification candidate {index + 1}/{len(delivery_hits)}: "
            f"{result.provider} / {result.status} / images={len(candidate_chart)}"
        )
        if result.status != "sent":
            break
    return 0 if len(results) == len(delivery_hits) and all(result.status == "sent" for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
