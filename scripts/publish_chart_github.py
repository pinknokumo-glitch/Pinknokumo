"""Upload a local chart PNG to GitHub and optionally enable GitHub Pages."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.github_publisher import GitHubPublisher
from scripts.render_chart_png import render


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish a generated chart PNG to GitHub")
    parser.add_argument("--code", default="72030")
    parser.add_argument("--repository", default="pinknokumo-glitch/Pinknokumo")
    parser.add_argument("--enable-pages", action="store_true", help="Enable GitHub Pages from the main branch")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    token = os.getenv("GITHUB_CHARTS_TOKEN", "")
    publisher = GitHubPublisher(args.repository, token)
    chart_path = render(args.code)
    remote_path = f"charts/{args.code}.png"
    publisher.upload_file(chart_path, remote_path, f"Update {args.code} chart")
    if args.enable_pages:
        publisher.ensure_pages()
    print(f"Published chart URL: {publisher.public_url(remote_path)}")


if __name__ == "__main__":
    main()
