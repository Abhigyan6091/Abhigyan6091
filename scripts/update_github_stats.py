#!/usr/bin/env python3
"""Generate a self-contained SVG summary of a GitHub user's public repositories.

Uses only the Python standard library and GitHub's REST API. In GitHub Actions,
set GH_TOKEN to the built-in GITHUB_TOKEN to increase API rate limits.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

USERNAME = os.environ.get("GITHUB_USERNAME", "Abhigyan6091").strip()
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "github-stats.svg"


def api_get(url: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-profile-stats-generator",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GitHub API returned HTTP {exc.code} for {url}: {body[:300]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach GitHub API: {exc.reason}") from exc


def fetch_all_public_repositories(username: str) -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    page = 1
    while True:
        query = urllib.parse.urlencode(
            {"per_page": 100, "page": page, "type": "owner", "sort": "updated"}
        )
        batch = api_get(f"https://api.github.com/users/{urllib.parse.quote(username)}/repos?{query}")
        if not isinstance(batch, list):
            raise RuntimeError("Unexpected response while listing public repositories.")
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def fetch_language_bytes(repo: dict[str, Any]) -> dict[str, int]:
    url = repo.get("languages_url")
    if not url:
        return {}
    payload = api_get(url)
    if not isinstance(payload, dict):
        return {}
    return {str(name): int(size) for name, size in payload.items() if isinstance(size, int)}


def text(x: object) -> str:
    return escape(str(x), quote=True)


def stat_group(x: int, label: str, x_position: int) -> str:
    return f'''<g transform="translate({x_position}, 77)">
      <text x="0" y="0" class="number">{x:,}</text>
      <text x="0" y="25" class="label">{text(label.upper())}</text>
    </g>'''


def build_svg(repos: list[dict[str, Any]], languages: dict[str, int]) -> str:
    repo_count = len(repos)
    stars = sum(int(repo.get("stargazers_count", 0) or 0) for repo in repos)
    forks = sum(int(repo.get("forks_count", 0) or 0) for repo in repos)
    top_languages = sorted(languages.items(), key=lambda item: item[1], reverse=True)[:5]
    max_bytes = max((size for _, size in top_languages), default=1)

    language_svg: list[str] = []
    if top_languages:
        for index, (name, size) in enumerate(top_languages):
            y = 111 + index * 23
            bar_width = max(3, int(245 * size / max_bytes))
            language_svg.append(
                f'''<g transform="translate(0, {y})">
                  <text x="0" y="0" class="lang">{text(name)}</text>
                  <rect x="112" y="-10" width="245" height="7" rx="3.5" fill="#21262D" />
                  <rect x="112" y="-10" width="{bar_width}" height="7" rx="3.5" fill="#8B7CF6" />
                </g>'''
            )
    else:
        language_svg.append('<text x="0" y="160" class="muted">No language data found yet.</text>')

    refreshed = datetime.now(timezone.utc).strftime("%d %b %Y · %H:%M UTC")
    languages_block = "\n".join(language_svg)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="920" height="275" viewBox="0 0 920 275" role="img" aria-labelledby="title desc">
  <title id="title">GitHub stats for {text(USERNAME)}</title>
  <desc id="desc">Public repository count, stars, forks, and most-used languages from public repository metadata.</desc>
  <defs>
    <style>
      .heading {{ font: 700 16px 'Segoe UI', Arial, sans-serif; fill: #F0F6FC; letter-spacing: 1.5px; }}
      .subheading {{ font: 12px 'Segoe UI', Arial, sans-serif; fill: #8B949E; }}
      .number {{ font: 700 30px 'Segoe UI', Arial, sans-serif; fill: #F0F6FC; }}
      .label {{ font: 600 10px 'Segoe UI', Arial, sans-serif; fill: #8B949E; letter-spacing: 1px; }}
      .section {{ font: 700 11px 'Segoe UI', Arial, sans-serif; fill: #C9D1D9; letter-spacing: 1.3px; }}
      .lang {{ font: 12px 'Segoe UI', Arial, sans-serif; fill: #C9D1D9; }}
      .muted {{ font: 12px 'Segoe UI', Arial, sans-serif; fill: #8B949E; }}
    </style>
  </defs>
  <rect x="1" y="1" width="918" height="273" rx="16" fill="#0D1117" stroke="#30363D" />
  <rect x="1" y="1" width="6" height="273" rx="3" fill="#8B7CF6" />
  <text x="30" y="35" class="heading">GITHUB SNAPSHOT</text>
  <text x="30" y="54" class="subheading">@{text(USERNAME)} · public repositories</text>
  {stat_group(repo_count, "Public repositories", 30)}
  {stat_group(stars, "Stars received", 205)}
  {stat_group(forks, "Forks received", 380)}
  <line x1="540" y1="70" x2="540" y2="235" stroke="#30363D" />
  <text x="575" y="80" class="section">TOP LANGUAGES BY CODE SIZE</text>
  <g transform="translate(575, 0)">{languages_block}</g>
  <line x1="30" y1="232" x2="890" y2="232" stroke="#21262D" />
  <text x="30" y="254" class="muted">Auto-generated from the GitHub API · public data only</text>
  <text x="890" y="254" text-anchor="end" class="muted">Updated {text(refreshed)}</text>
</svg>
'''


def main() -> int:
    if not USERNAME:
        print("GITHUB_USERNAME is required.", file=sys.stderr)
        return 2

    repos = fetch_all_public_repositories(USERNAME)
    # Avoid counting the code in forks as the user's own language distribution.
    language_repos = [repo for repo in repos if not repo.get("fork", False)]
    languages: dict[str, int] = {}
    for repo in language_repos:
        for language, byte_count in fetch_language_bytes(repo).items():
            languages[language] = languages.get(language, 0) + byte_count

    svg = build_svg(repos, languages)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(svg, encoding="utf-8")
    print(f"Updated {OUTPUT} using {len(repos)} public repositories.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
