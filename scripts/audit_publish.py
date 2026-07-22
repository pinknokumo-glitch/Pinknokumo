"""Fail when files intended for publication contain secrets or private runtime data."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", "data", "reports", "work", "build", ".gradle"}
SKIP_NAMES = {".env"}
TEXT_SUFFIXES = {".py", ".ps1", ".md", ".yaml", ".yml", ".json", ".toml", ".txt", ".properties", ".kts", ".xml", ".gitignore"}
PATTERNS = {
    "GitHub token": re.compile(r"(?:github_pat_|ghp_)[A-Za-z0-9_]{20,}"),
    "LINE bearer token": re.compile(r"Bearer\s+[A-Za-z0-9._-]{40,}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}
FORBIDDEN_TRACKED_PREFIXES = ("data/", "reports/", "work/")
FORBIDDEN_TRACKED_NAMES = {".env"}


def candidate_files() -> list[Path]:
    files = []
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if not path.is_file() or path.name in SKIP_NAMES or any(part in SKIP_PARTS for part in relative.parts):
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name == ".gitignore":
            files.append(path)
    return files


def tracked_runtime_files() -> list[str]:
    """Return generated/private files accidentally committed to Git."""
    if not (ROOT / ".git").exists():
        return []
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=False
    )
    if result.returncode != 0:
        return []
    tracked = result.stdout.decode("utf-8", errors="replace").split("\0")
    return sorted(
        path for path in tracked
        if path in FORBIDDEN_TRACKED_NAMES or path.startswith(FORBIDDEN_TRACKED_PREFIXES)
    )


def main() -> int:
    findings = []
    findings.extend(f"{path}: private/runtime file is tracked by Git" for path in tracked_runtime_files())
    for path in candidate_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{path.relative_to(ROOT)}: {label}")
    if findings:
        print("Publish audit failed:")
        print("\n".join(f"- {finding}" for finding in findings))
        return 1
    print(f"Publish audit passed: {len(candidate_files())} text files checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
