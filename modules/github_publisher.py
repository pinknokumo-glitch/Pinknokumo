"""Minimal GitHub Contents and Pages publisher for public chart images."""
from __future__ import annotations

import base64
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class GitHubPublisher:
    api_base = "https://api.github.com"

    def __init__(self, repository: str, token: str, branch: str = "main") -> None:
        if "/" not in repository:
            raise ValueError("repository must use owner/name format")
        if not token:
            raise ValueError("GitHub token is required")
        self.repository = repository
        self.token = token
        self.branch = branch

    def request(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            f"{self.api_base}{path}", data=data, method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2026-03-10",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = response.read().decode("utf-8")
                return response.status, json.loads(payload) if payload else {}
        except HTTPError as error:
            payload = error.read().decode("utf-8", errors="replace")
            details = json.loads(payload) if payload.startswith("{") else {"message": payload}
            if error.code == 404:
                return 404, details
            raise RuntimeError(f"GitHub API error {error.code}: {details.get('message', payload)}") from error

    def upload_file(self, local_path: str | Path, remote_path: str, message: str) -> dict:
        source = Path(local_path)
        if not source.is_file():
            raise FileNotFoundError(source)
        lookup_path = f"/repos/{self.repository}/contents/{remote_path}?ref={self.branch}"
        status, existing = self.request("GET", lookup_path)
        body: dict[str, str] = {
            "message": message,
            "content": base64.b64encode(source.read_bytes()).decode("ascii"),
            "branch": self.branch,
        }
        if status == 200 and existing.get("sha"):
            body["sha"] = existing["sha"]
        _, result = self.request("PUT", f"/repos/{self.repository}/contents/{remote_path}", body)
        return result

    def ensure_pages(self) -> dict:
        status, existing = self.request("GET", f"/repos/{self.repository}/pages")
        if status == 200:
            return existing
        _, result = self.request(
            "POST", f"/repos/{self.repository}/pages",
            {"source": {"branch": self.branch, "path": "/"}},
        )
        return result

    def public_url(self, remote_path: str) -> str:
        owner, repository = self.repository.split("/", 1)
        return f"https://{owner}.github.io/{repository}/{remote_path}"
