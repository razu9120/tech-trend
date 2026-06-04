#!/usr/bin/env python3
"""Fetch tech trend data and write Obsidian notes. No external dependencies."""

import json
import os
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
_gh_token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
if _gh_token:
    HEADERS["Authorization"] = f"Bearer {_gh_token}"


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


def fetch_zenn_trending(count: int = 20) -> list[dict]:
    url = f"https://zenn.dev/api/articles?order=liked_count&period=week&count={count}"
    req = urllib.request.Request(url, headers={"User-Agent": "tech-trend-bot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        print(f"    skipped ({e})")
        return []
    results = []
    for item in data.get("articles", []):
        username = (item.get("user") or {}).get("username", "")
        slug = item.get("slug", "")
        results.append({
            "title": item.get("title", "")[:60],
            "url": f"https://zenn.dev/{username}/articles/{slug}",
            "liked_count": item.get("liked_count", 0),
            "emoji": item.get("emoji") or "",
            "published_at": (item.get("published_at") or "")[:10],
            "topics": [t.get("display_name", "") for t in (item.get("topics") or [])],
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


def zenn_note(articles: list[dict]) -> str:
    lines = [
        "---",
        f"date: {TODAY}",
        "topic: zenn",
        "tags: [tech-trend, auto-generated]",
        "---",
        "",
        f"# Zenn 人気記事（週間） - {TODAY}",
        "",
        "過去 7 日間のいいね数上位記事。",
        "",
        "| # | 記事 | ❤️ | タグ | 公開日 |",
        "|---:|---|---:|---|---|",
    ]
    for i, a in enumerate(articles, 1):
        emoji = a["emoji"] + " " if a["emoji"] else ""
        topics = ", ".join(a["topics"][:3]) if a["topics"] else "—"
        lines.append(
            f"| {i} | [{emoji}{a['title']}]({a['url']}) | {a['liked_count']:,} | {topics} | {a['published_at']} |"
        )
    lines.append("")
    return "\n".join(lines)


def daily_note(
    react: list[dict],
    nextjs: list[dict],
    claude_code: list[dict],
    trending: list[dict],
    zenn: list[dict],
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
    lines += [
        "",
        "## Zenn 人気記事 Top 5（週間）",
        "",
    ]
    for a in zenn[:5]:
        emoji = a["emoji"] + " " if a["emoji"] else ""
        lines.append(f"- [{emoji}{a['title']}]({a['url']}) ❤️{a['liked_count']:,}")
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

    print("  Zenn 人気記事...")
    zenn = fetch_zenn_trending()

    write_note(BASE_DIR / "topics" / "react" / f"{TODAY}.md", releases_note("react", "React", react))
    write_note(BASE_DIR / "topics" / "nextjs" / f"{TODAY}.md", releases_note("nextjs", "Next.js", nextjs))
    write_note(BASE_DIR / "topics" / "claude-code" / f"{TODAY}.md", releases_note("claude-code", "Claude Code", claude_code))
    write_note(BASE_DIR / "topics" / "github-trending" / f"{TODAY}.md", trending_note(trending))
    write_note(BASE_DIR / "topics" / "zenn" / f"{TODAY}.md", zenn_note(zenn))
    write_note(BASE_DIR / "daily" / f"{TODAY}.md", daily_note(react, nextjs, claude_code, trending, zenn))

    print("Done.")


if __name__ == "__main__":
    main()
