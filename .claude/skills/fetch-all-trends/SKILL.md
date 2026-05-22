---
name: fetch-all-trends
description: React / Next.js / Claude Code / GitHub Trending の最新情報を手動取得して Obsidian ノートを生成し git push する。
disable-model-invocation: true
allowed-tools: Bash(python3 *) Bash(git *)
---

## 概要

GitHub Actions と同じスクリプト `scripts/fetch_trends.py` をローカルで実行し、
`daily/` および `topics/` 以下に本日付のノートを生成して main にプッシュする。

## 実行手順

1. スクリプトを実行してノートを生成する

```bash
python3 scripts/fetch_trends.py
```

2. 変更があれば commit して push する

```bash
git add -A
git diff --cached --quiet && echo "変更なし" || git commit -m "auto: fetch tech-trend $(date +%Y-%m-%d)" && git push
```

## 注意

- 同日のノートが既にある場合は上書きされる
- GitHub API の認証なし制限は 60 req/時間。通常の利用では超えない
