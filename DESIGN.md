# Tech Trend Auto-Fetch システム設計

**方針確定済み**
- 実行方式：GitHub Actions（毎日 JST 7:00 = UTC 22:00）
- プッシュ先：`main` ブランチ
- 通知：なし
- 情報粒度：要約 + 元ソースのリンク

---

## 1. ノート構造設計

- [ ] フォルダ構成を決める

  ```
  tech-trend/
  ├── daily/
  │   └── YYYY-MM-DD.md       # 全トピックを横断した日次サマリー
  ├── topics/
  │   ├── react/
  │   │   └── YYYY-MM-DD.md   # React 日次レポート
  │   ├── nextjs/
  │   │   └── YYYY-MM-DD.md
  │   ├── claude-code/
  │   │   └── YYYY-MM-DD.md
  │   └── github-trending/
  │       └── YYYY-MM-DD.md
  └── .claude/
      └── skills/             # Claude Code ローカルスキル
  ```

- [ ] ノートの YAML frontmatter スキーマを決める

  ```yaml
  ---
  date: YYYY-MM-DD
  topic: react | nextjs | claude-code | github-trending
  tags: [tech-trend, auto-generated]
  ---
  ```

- [ ] 見出し構成テンプレートを決める

  ```markdown
  # {Topic} - YYYY-MM-DD

  ## 概要
  （2〜3 文の要約）

  ## 主なトピック
  - **タイトル** — 1行要約 ([ソース]({url}))
  - ...

  ## 注目リポジトリ（github-trending のみ）
  | リポジトリ | スター | 説明 |
  |---|---|---|
  ```

---

## 2. Rules（CLAUDE.md）

- [ ] 収集対象と検索クエリ方針を定義する

  | トピック | 検索クエリ例 | 主要ソース |
  |---|---|---|
  | React | `React latest news site:react.dev OR site:github.com/facebook/react` | react.dev/blog, github releases |
  | Next.js | `Next.js new release OR changelog` | nextjs.org/blog, github releases |
  | Claude Code | `Claude Code updates site:docs.anthropic.com OR site:github.com/anthropics` | docs.anthropic.com, anthropic.com/news |
  | GitHub Trending | GitHub API `/search/repositories` (weekly stars) | api.github.com |

- [ ] ノート品質ルールを明記する
  - 要約は日本語で記述する
  - ソースリンクは必ず元記事 URL を記載する（短縮 URL 禁止）
  - 情報は過去 7 日以内のものに限る
  - 同日のノートが存在する場合は上書きする

- [ ] コミットメッセージ規則を決める
  - 形式：`auto: fetch tech-trend YYYY-MM-DD`

---

## 3. Skills（`.claude/skills/`）

GitHub Actions が本番自動化を担うが、ローカルでの手動実行・デバッグ用に Skills を用意する。

### 3-1. `fetch-all-trends`

- [ ] `.claude/skills/fetch-all-trends/SKILL.md` を作成する

  ```yaml
  ---
  name: fetch-all-trends
  description: 全トピック（React/Next.js/Claude Code/GitHub Trending）の最新情報を手動取得してノートを生成する。
  disable-model-invocation: true
  allowed-tools: WebSearch WebFetch Write Bash(git *)
  ---
  ```

  - 処理内容：後述の fetch-react / fetch-nextjs / fetch-claude-code / fetch-github-trending を順次呼び出し、daily サマリーを生成して git commit & push する

### 3-2. `fetch-react`

- [ ] `.claude/skills/fetch-react/SKILL.md` を作成する

  ```yaml
  ---
  name: fetch-react
  description: React の最新ニュース・リリースを取得して topics/react/YYYY-MM-DD.md を生成する。
  disable-model-invocation: true
  allowed-tools: WebSearch WebFetch Write
  ---
  ```

### 3-3. `fetch-nextjs`

- [ ] `.claude/skills/fetch-nextjs/SKILL.md` を作成する（fetch-react と同構成）

### 3-4. `fetch-claude-code`

- [ ] `.claude/skills/fetch-claude-code/SKILL.md` を作成する（fetch-react と同構成）

### 3-5. `fetch-github-trending`

- [ ] `.claude/skills/fetch-github-trending/SKILL.md` を作成する

  ```yaml
  ---
  name: fetch-github-trending
  description: GitHub Trending（週間）のトップリポジトリを取得して topics/github-trending/YYYY-MM-DD.md を生成する。
  disable-model-invocation: true
  allowed-tools: WebSearch WebFetch Write Bash(curl *)
  ---
  ```

  - GitHub Search API `GET /search/repositories?q=created:>DATE&sort=stars&order=desc&per_page=10` を利用（トークン不要の public API）

---

## 4. GitHub Actions ワークフロー

### 4-1. ワークフローファイル

- [ ] `.github/workflows/fetch-tech-trend.yml` を作成する

  ```yaml
  name: Fetch Tech Trend

  on:
    schedule:
      - cron: '0 22 * * *'   # 毎日 UTC 22:00 = JST 07:00
    workflow_dispatch:        # 手動実行も可能にする

  permissions:
    contents: write           # commit & push に必要

  jobs:
    fetch:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4

        - name: Fetch trends
          run: python3 scripts/fetch_trends.py

        - name: Commit and push
          run: |
            git config user.name  "github-actions[bot]"
            git config user.email "github-actions[bot]@users.noreply.github.com"
            git add -A
            git diff --cached --quiet || git commit -m "auto: fetch tech-trend $(date +%Y-%m-%d)"
            git push
  ```

### 4-2. スクリプト（`scripts/fetch_trends.py`）

- [ ] `scripts/fetch_trends.py` を作成する
  - Python 標準ライブラリのみ使用（`urllib`、`json`）— 追加インストール不要
  - GitHub Releases API でリリース情報を取得（React / Next.js / Claude Code）
  - GitHub Search API で直近 7 日間作成のスター急上昇リポジトリを取得
  - 取得結果を規定フォーマットの Markdown に整形して `topics/` と `daily/` に書き出す

  **処理フロー：**
  ```
  1. 実行日付を取得（YYYY-MM-DD）
  2. GitHub Releases API → React / Next.js / Claude Code の最新リリース一覧
  3. GitHub Search API  → 過去7日作成リポジトリをスター順で取得
  4. Markdown ファイルを生成・保存
  ```

  **GitHub API 制限：** 認証なしで 60 req/時間。1実行で最大 4 リクエストのため問題なし。

### 4-3. GitHub Secrets 設定

**不要**（外部 API キー不使用）

---

## 5. コスト

**完全無料**
- GitHub Actions：パブリックリポジトリは無制限
- GitHub API：認証なしで 60 req/時間（1実行 = 最大 4 リクエスト）
- 外部 API キー：不要

---

## 6. 実装順序

- [x] **Step 1** フォルダ構成と CLAUDE.md を作成する
- [x] **Step 2** `scripts/fetch_trends.py` を実装しローカルで動作確認する
- [x] **Step 3** `.github/workflows/fetch-tech-trend.yml` を作成する
- [x] **Step 4** `.claude/skills/` にローカル用スキルを追加する
- [ ] **Step 5** `workflow_dispatch` で手動実行して動作確認する（GitHub へ push 後）
- [ ] **Step 6** 生成されたノートの品質を確認し、フォーマットを調整する
- [ ] **Step 7** スケジュール実行（毎日 JST 7:00）を確認する
- [ ] **Step 8** 1 週間分のノートが正常に蓄積されることを確認する
