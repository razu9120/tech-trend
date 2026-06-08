#!/usr/bin/env python3
"""Fetch tech trend data and write Obsidian notes. No external dependencies."""

import json
import os
import re
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
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


def fetch_qiita_trending(count: int = 20) -> list[dict]:
    query = f"stocks:>20 created:>{SEVEN_DAYS_AGO}"
    url = (
        "https://qiita.com/api/v2/items"
        f"?per_page={count}&query={urllib.parse.quote(query)}"
    )
    headers = {"User-Agent": "tech-trend-bot/1.0"}
    token = os.environ.get("QIITA_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        print(f"    skipped ({e})")
        return []
    results = []
    for item in data:
        results.append({
            "title": (item.get("title") or "")[:60],
            "url": item.get("url", ""),
            "likes_count": item.get("likes_count", 0),
            "stocks_count": item.get("stocks_count", 0),
            "published_at": (item.get("created_at") or "")[:10],
            "tags": [t.get("name", "") for t in (item.get("tags") or [])],
        })
    return results


# note.com itself sits behind Cloudflare and hard-blocks datacenter IPs (e.g.
# GitHub Actions runners), so its API can't be reached from CI. Instead we query
# Google News (not IP-blocked) for note.com articles, then resolve each Google
# redirect link back to the real note.com URL — the project rule forbids
# redirect/short URLs in notes.
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_GNEWS_BATCH = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
_NOTE_URL_RE = re.compile(r"https://note\.com/[A-Za-z0-9_\-]+/n/[A-Za-z0-9]+")


def _resolve_gnews_url(link: str) -> str:
    """Resolve a Google News redirect link to the underlying note.com URL.

    The modern Google News link encodes the target in a protobuf id that must be
    exchanged via Google's batchexecute endpoint, using a signature/timestamp
    embedded in the article page. Returns "" on any failure.
    """
    try:
        art_id = link.split("/articles/")[1].split("?")[0]
    except IndexError:
        return ""
    headers = {"User-Agent": _BROWSER_UA}
    try:
        req = urllib.request.Request(link, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            page = resp.read().decode("utf-8", "replace")
        sg = re.search(r'data-n-a-sg="([^"]+)"', page)
        ts = re.search(r'data-n-a-ts="([^"]+)"', page)
        if not sg or not ts:
            return ""
        inner = json.dumps([
            "garturlreq",
            [["X", "X", ["X", "X"], None, [], 1, 1, "US:en", None, 1,
              None, None, None, None, None, 0, 1],
             "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
            art_id, int(ts.group(1)), sg.group(1),
        ])
        freq = json.dumps([[["Fbv4je", inner, None, "1"]]])
        data = urllib.parse.urlencode({"f.req": freq}).encode()
        req = urllib.request.Request(
            _GNEWS_BATCH, data=data,
            headers={**headers,
                     "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"    note url resolve failed ({e})")
        return ""
    m = _NOTE_URL_RE.search(body)
    return m.group(0) if m else ""


def fetch_note_trending(keywords: list[str] | None = None, per_keyword: int = 5) -> list[dict]:
    keywords = keywords or ["React", "Next.js", "プログラミング"]
    results: list[dict] = []
    seen: set[str] = set()
    for kw in keywords:
        query = urllib.parse.quote(f"site:note.com {kw}")
        url = f"https://news.google.com/rss/search?q={query}&hl=ja&gl=JP&ceid=JP:ja"
        req = urllib.request.Request(url, headers={"User-Agent": _BROWSER_UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                xml = resp.read().decode("utf-8", "replace")
        except urllib.error.URLError as e:
            print(f"    skipped '{kw}' ({e})")
            continue
        kept = 0
        for item in re.findall(r"<item>(.*?)</item>", xml, re.S):
            if kept >= per_keyword:
                break
            link_m = re.search(r"<link>(.*?)</link>", item, re.S)
            title_m = re.search(r"<title>(.*?)</title>", item, re.S)
            date_m = re.search(r"<pubDate>(.*?)</pubDate>", item, re.S)
            if not link_m or not title_m:
                continue
            # Filter by date BEFORE the (2-request) URL resolve to limit traffic.
            published_at = ""
            if date_m:
                try:
                    published_at = (
                        parsedate_to_datetime(date_m.group(1).strip())
                        .astimezone(JST).strftime("%Y-%m-%d")
                    )
                except (TypeError, ValueError):
                    published_at = ""
            if not published_at or published_at < SEVEN_DAYS_AGO:
                continue
            note_url = _resolve_gnews_url(link_m.group(1).strip())
            if not note_url or note_url in seen:
                continue
            seen.add(note_url)
            title = re.sub(r"\s*-\s*note\s*$", "", title_m.group(1).strip())
            results.append({
                "title": title[:60],
                "url": note_url,
                "published_at": published_at,
                "keyword": kw,
            })
            kept += 1
    results.sort(key=lambda r: r["published_at"], reverse=True)
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


def qiita_note(articles: list[dict]) -> str:
    lines = [
        "---",
        f"date: {TODAY}",
        "topic: qiita",
        "tags: [tech-trend, auto-generated]",
        "---",
        "",
        f"# Qiita 人気記事（週間） - {TODAY}",
        "",
        "過去 7 日間のストック数上位記事。",
        "",
        "| # | 記事 | 👍 LGTM | タグ | 公開日 |",
        "|---:|---|---:|---|---|",
    ]
    for i, a in enumerate(articles, 1):
        tags = ", ".join(a["tags"][:3]) if a["tags"] else "—"
        title = a["title"].replace("|", "｜")
        lines.append(
            f"| {i} | [{title}]({a['url']}) | {a['likes_count']:,} | {tags} | {a['published_at']} |"
        )
    lines.append("")
    return "\n".join(lines)


def note_note(articles: list[dict]) -> str:
    lines = [
        "---",
        f"date: {TODAY}",
        "topic: note",
        "tags: [tech-trend, auto-generated]",
        "---",
        "",
        f"# note 技術記事 - {TODAY}",
        "",
        "Google News 経由で取得した過去 7 日間の note 技術記事。",
        "",
        "| # | 記事 | キーワード | 公開日 |",
        "|---:|---|---|---|",
    ]
    for i, a in enumerate(articles, 1):
        title = a["title"].replace("|", "｜")
        lines.append(
            f"| {i} | [{title}]({a['url']}) | {a['keyword']} | {a['published_at']} |"
        )
    lines.append("")
    return "\n".join(lines)


def daily_note(
    react: list[dict],
    nextjs: list[dict],
    claude_code: list[dict],
    trending: list[dict],
    zenn: list[dict],
    qiita: list[dict],
    note: list[dict],
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
    lines += [
        "",
        "## Qiita 人気記事 Top 5（週間）",
        "",
    ]
    for a in qiita[:5]:
        lines.append(f"- [{a['title']}]({a['url']}) 👍{a['likes_count']:,}")
    lines += [
        "",
        "## note 技術記事 Top 5",
        "",
    ]
    for a in note[:5]:
        lines.append(f"- [{a['title']}]({a['url']}) `{a['published_at']}`")
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

    print("  Qiita 人気記事...")
    qiita = fetch_qiita_trending()

    print("  note 技術記事...")
    note = fetch_note_trending()

    write_note(BASE_DIR / "topics" / "react" / f"{TODAY}.md", releases_note("react", "React", react))
    write_note(BASE_DIR / "topics" / "nextjs" / f"{TODAY}.md", releases_note("nextjs", "Next.js", nextjs))
    write_note(BASE_DIR / "topics" / "claude-code" / f"{TODAY}.md", releases_note("claude-code", "Claude Code", claude_code))
    write_note(BASE_DIR / "topics" / "github-trending" / f"{TODAY}.md", trending_note(trending))
    write_note(BASE_DIR / "topics" / "zenn" / f"{TODAY}.md", zenn_note(zenn))
    write_note(BASE_DIR / "topics" / "qiita" / f"{TODAY}.md", qiita_note(qiita))
    write_note(BASE_DIR / "topics" / "note" / f"{TODAY}.md", note_note(note))
    write_note(BASE_DIR / "daily" / f"{TODAY}.md", daily_note(react, nextjs, claude_code, trending, zenn, qiita, note))

    print("Done.")


if __name__ == "__main__":
    main()
