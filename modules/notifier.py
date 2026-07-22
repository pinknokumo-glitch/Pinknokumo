"""Opt-in LINE Messaging API notifications for screening summaries."""
from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv


@dataclass(frozen=True)
class NotificationResult:
    provider: str
    status: str
    response_text: str | None = None


def format_screening_message(
    profile: str, hits: Sequence[Mapping[str, object]], max_candidates: int = 10,
    comments_by_code: Mapping[str, str] | None = None, as_of_date: str | None = None,
) -> str:
    header = f"StockAI Navigator\nプロファイル: {profile}\nヒット件数: {len(hits)}件"
    if as_of_date:
        header += f"\n判定基準日: {as_of_date}"
    if not hits:
        return header
    comments_by_code = comments_by_code or {}
    lines = [header, "候補:"]
    for hit in hits[:max_candidates]:
        code = str(hit["code"])
        company_name = str(hit.get("company_name") or "").strip()
        score = hit.get("expectation_score")
        score_text = "未算出" if score is None else f"{float(score):.1f}/100"
        label = f"{company_name}（{code}）" if company_name else code
        lines.append(f"- {label}\n  期待値スコア: {score_text}")
        reason = str(hit.get("reason") or "").strip()
        if reason:
            lines.append(f"  抽出理由: {reason}")
        comment = comments_by_code.get(code)
        if comment:
            lines.append(f"  {comment}")
    if len(hits) > max_candidates:
        lines.append(f"ほか{len(hits) - max_candidates}件")
    lines.append("過去データの統計であり、将来の結果を保証するものではありません。")
    return "\n".join(lines)[:5000]


class LineNotifier:
    endpoint = "https://api.line.me/v2/bot/message/push"

    def __init__(self, config: Mapping[str, object]) -> None:
        self.config = config["notification"]["line"]

    def chart_urls(self, codes: Sequence[str]) -> list[str]:
        """Return opt-in HTTPS chart URLs from the deployment-specific template."""
        template = str(self.config.get("chart_public_url_template") or "").strip()
        if not template:
            return []
        if "{code}" not in template:
            raise ValueError("chart_public_url_template must contain {code}")
        max_images = int(self.config.get("max_chart_images", 3))
        urls = [template.replace("{code}", code) for code in codes[:max_images]]
        for url in urls:
            parsed = urlparse(url)
            if parsed.scheme != "https" or not parsed.netloc:
                raise ValueError("chart_public_url_template must produce an HTTPS URL")
            if not parsed.path.lower().endswith((".png", ".jpg", ".jpeg")):
                raise ValueError("LINE chart URLs must point to PNG or JPEG images")
        return urls

    @staticmethod
    def build_messages(message: str, chart_urls: Sequence[str] = ()) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [{"type": "text", "text": message}]
        messages.extend({"type": "image", "originalContentUrl": url, "previewImageUrl": url} for url in chart_urls)
        return messages

    def send(self, message: str, chart_urls: Sequence[str] = ()) -> NotificationResult:
        if not self.config["enabled"]:
            return NotificationResult("line", "disabled")
        load_dotenv()
        token = os.getenv(self.config["channel_access_token_env"])
        recipient = os.getenv(self.config["recipient_env"])
        if not token or not recipient:
            return NotificationResult("line", "missing_credentials")
        payload = json.dumps({"to": recipient, "messages": self.build_messages(message, chart_urls)}).encode("utf-8")
        request = Request(self.endpoint, data=payload, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=15) as response:
                return NotificationResult("line", "sent", response.read().decode("utf-8", errors="replace"))
        except HTTPError as error:
            return NotificationResult("line", f"http_{error.code}", error.read().decode("utf-8", errors="replace"))
        except URLError as error:
            return NotificationResult("line", "network_error", str(error.reason))
