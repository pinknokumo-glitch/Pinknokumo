"""Record a bounded, credential-free failure even when dependency install failed."""
import json
import os
from urllib.request import Request, urlopen


def main():
    request_id = os.environ["ANALYSIS_REQUEST_ID"]
    if not request_id.isdigit():
        raise ValueError("Invalid request id")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    headers = {"apikey": key, "Content-Type": "application/json"}
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    req = Request(
        os.environ["SUPABASE_URL"].rstrip("/") +
        f"/rest/v1/backtest_requests?id=eq.{request_id}&status=in.(pending,processing)",
        headers=headers, method="PATCH",
        data=json.dumps({"status": "failed", "error_message":
            "分析処理が完了しませんでした。夕方データの保存状況と分析ワークフローを確認してください。"}).encode(),
    )
    with urlopen(req, timeout=20):
        pass


if __name__ == "__main__":
    main()
