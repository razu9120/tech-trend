# tech-trend

React / Next.js / Claude Code / GitHub Trending の最新情報を毎日自動取得して Obsidian ノートとして蓄積するリポジトリ。

## ノート構造

```
daily/YYYY-MM-DD.md          # 全トピック横断の日次サマリー
topics/react/YYYY-MM-DD.md
topics/nextjs/YYYY-MM-DD.md
topics/claude-code/YYYY-MM-DD.md
topics/github-trending/YYYY-MM-DD.md
```

## ノートフォーマット規則

- frontmatter に `date`, `topic`, `tags: [tech-trend, auto-generated]` を含める
- 情報は過去 7 日以内のものに限る
- ソースリンクは必ず元記事の URL を記載する（短縮 URL 禁止）
- 同日のノートが存在する場合は上書きする
- コミットメッセージ形式: `auto: fetch tech-trend YYYY-MM-DD`

## 自動化

- GitHub Actions（`.github/workflows/fetch-tech-trend.yml`）が毎日 JST 7:00 に実行
- スクリプト: `scripts/fetch_trends.py`（Python 標準ライブラリのみ、外部 API キー不要）

## ローカル手動実行

```bash
python3 scripts/fetch_trends.py
```

または Claude Code から `/fetch-all-trends` スキルを使う。
