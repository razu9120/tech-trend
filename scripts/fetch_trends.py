#!/usr/bin/env python3
"""Fetch tech trend data and write Obsidian notes. No external dependencies."""

import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
TODAY = datetime.now(JST).strftime("%Y-%m-%d")
SEVEN_DAYS_AGO = (datetime.now(JST) - timedelta(days=7)).strftime("%Y-%m-%d")
BASE_DIR = Path(__file__).parent.parent

HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "tech-trend-bot/1.0",
}


def gh_get(url: str):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_releases(owner: str, repo: str, count: int = 5) -> list[dict]:
    url = f"https://api.github.com/repos/{owner}/{repo}/releases?per_page={count}"
    releases = gh_get(url)
    results = []
    for r in releases:
        body_first_line = ""
        if r.get("body"):
            for line in r["body"].splitlines():
                line = line.strip().lstrip("#").strip()
                if line and not line.startswith("<!--"):
                    body_first_line = line[:150]
                    break
        results.append({
            "title": r.get("name") or r["tag_name"],
            "tag": r["tag_name"],
            "url": r["html_url"],
            "date": (r.get("published_at") or "")[:10],
            "prerelease": r.get("prerelease", False),
            "summary": body_first_line,
        })
    return results


def fetch_trending() -> list[dict]:
    url = (
        "https://api.github.com/search/repositories"
        f"?q=created:>{SEVEN_DAYS_AGO}&sort=stars&order=desc&per_page=10"
    )
    data = gh_get(url)
    results = []
    for item in data.get("items", []):
        results.append({
            "name": item["full_name"],
            "url": item["html_url"],
            "stars": item["stargazers_count"],
            "description": (item.get("description") or "").replace("|", "｜")[:80],
            "language": item.get("language") or "",
        })
    return results


def write_note(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  wrote {path.relative_to(BASE_DIR)}")


def releases_note(topic: str, display: str, releases: list[dict]) -> str:
    lines = [
        "---",
        f"date: {TODAY}",
        f"topic: {topic}",
        "tags: [tech-trend, auto-generated]",
        "---",
        "",
        f"# {display} - {TODAY}",
        "",
        "## 最新リリース",
        "",
    ]
    if not releases:
        lines += ["_この期間にリリースはありませんでした。_", ""]
        return "\n".join(lines)
    for r in releases:
        pre = " _(pre-release)_" if r["prerelease"] else ""
        date = f" `{r['date']}`" if r["date"] else ""
        lines.append(f"### [{r['title']}]({r['url']}){pre}{date}")
        if r["summary"]:
            lines.append(f"{r['summary']}")
        lines.append("")
    return "\n".join(lines)


def trending_note(repos: list[dict]) -> str:
    lines = [
        "---",
        f"date: {TODAY}",
        "topic: github-trending",
        "tags: [tech-trend, auto-generated]",
        "---",
        "",
        f"# GitHub Trending - {TODAY}",
        "",
        f"過去 7 日間（{SEVEN_DAYS_AGO} 以降）に作成されたスター急上昇リポジトリ。",
        "",
        "| リポジトリ | ⭐ Stars | 言語 | 説明 |",
        "|---|---:|---|---|",
    ]
    for r in repos:
        lang = r["language"] or "—"
        lines.append(
            f"| [{r['name']}]({r['url']}) | {r['stars']:,} | {lang} | {r['description']} |"
        )
    lines.append("")
    return "\n".join(lines)


def daily_note(
    react: list[dict],
    nextjs: list[dict],
    claude_code: list[dict],
    trending: list[dict],
) -> str:
    def recent(releases: list[dict], n: int = 3) -> list[dict]:
        return [r for r in releases if not r["prerelease"]][:n] or releases[:n]

    def section(name: str, releases: list[dict]) -> list[str]:
        items = recent(releases)
        if not items:
            return [f"### {name}", "", "_最新リリースなし_", ""]
        out = [f"### {name}", ""]
        for r in items:
            date = f" `{r['date']}`" if r["date"] else ""
            out.append(f"- [{r['title']}]({r['url']}){date}")
        return out + [""]

    lines = [
        "---",
        f"date: {TODAY}",
        "topic: daily",
        "tags: [tech-trend, auto-generated]",
        "---",
        "",
        f"# Tech Trend Daily - {TODAY}",
        "",
        "## リリース情報",
        "",
        *section("React", react),
        *section("Next.js", nextjs),
        *section("Claude Code", claude_code),
        "## GitHub Trending Top 5",
        "",
    ]
    for r in trending[:5]:
        lang = f" `{r['language']}`" if r["language"] else ""
        lines.append(f"- [{r['name']}]({r['url']}) ⭐{r['stars']:,}{lang} — {r['description']}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    print(f"Fetching tech trends for {TODAY}...")

    print("  React releases...")
    react = fetch_releases("facebook", "react")

    print("  Next.js releases...")
    nextjs = fetch_releases("vercel", "next.js")

    print("  Claude Code releases...")
    try:
        claude_code = fetch_releases("anthropics", "claude-code")
    except urllib.error.HTTPError as e:
        print(f"    skipped (HTTP {e.code})")
        claude_code = []

    print("  GitHub Trending...")
    trending = fetch_trending()

    write_note(BASE_DIR / "topics" / "react" / f"{TODAY}.md", releases_note("react", "React", react))
    write_note(BASE_DIR / "topics" / "nextjs" / f"{TODAY}.md", releases_note("nextjs", "Next.js", nextjs))
    write_note(BASE_DIR / "topics" / "claude-code" / f"{TODAY}.md", releases_note("claude-code", "Claude Code", claude_code))
    write_note(BASE_DIR / "topics" / "github-trending" / f"{TODAY}.md", trending_note(trending))
    write_note(BASE_DIR / "daily" / f"{TODAY}.md", daily_note(react, nextjs, claude_code, trending))

    print("Done.")


if __name__ == "__main__":
    main()
