# d-party Backend

[![CI](https://github.com/d-party/backend/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/d-party/backend/actions/workflows/ci.yml)
[![Code Quality Review](https://github.com/d-party/backend/actions/workflows/code-quality-review.yml/badge.svg)](https://github.com/d-party/backend/actions/workflows/code-quality-review.yml)

[![Coverage badge](https://raw.githubusercontent.com/d-party/backend/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/d-party/backend/blob/python-coverage-comment-action-data/htmlcov/index.html)
[![Website](https://img.shields.io/website?label=d-party.net&up_message=online&url=https%3A%2F%2Fd-party.net)](https://d-party.net)
[![Security Headers](https://img.shields.io/security-headers?url=https%3A%2F%2Fd-party.net)](https://securityheaders.com/?q=https%3A%2F%2Fd-party.net&followRedirects=on)
[![Mozilla HTTP Observatory Grade](https://img.shields.io/mozilla-observatory/grade/d-party.net?publish)](https://observatory.mozilla.org/analyze/d-party.net)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/d-Party/d-Party-Backend/blob/main/LICENSE)
[![room-par-day](https://img.shields.io/endpoint?url=https://d-party.net/api/shields/room-par-day)](https://d-party.net)
[![user-par-day](https://img.shields.io/endpoint?url=https://d-party.net/api/shields/user-par-day)](https://d-party.net)

[![Docker](https://img.shields.io/badge/-Docker-EEE.svg?logo=docker&style=flat)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python:3.13-F9DC3E.svg?logo=python&style=flat)](https://www.python.org/)
[![Django:6.0](https://img.shields.io/badge/Django:6.0-092E20.svg?logo=django&style=flat)](https://www.djangoproject.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL:16-336791.svg?logo=postgresql&style=flat&logoColor=white)](https://www.postgresql.org/)
[![Nginx](https://img.shields.io/badge/-Nginx-5.svg?logo=nginx&style=flat)](https://www.nginx.co.jp/)
[![Redis](https://img.shields.io/badge/Redis:7-511.svg?logo=redis&style=flat)](https://redis.io/)
[![uv](https://img.shields.io/badge/uv-managed-DE5FE9.svg?logo=uv&style=flat)](https://docs.astral.sh/uv/)

d-Party のバックエンド部分を担当するフォルダ

> 開発・エージェント向けの詳細は [`AGENTS.md`](AGENTS.md) を参照。
> （Python 3.13 · Django 6.0 · PostgreSQL · uv · ruff へモダナイズ済み）

## 初回起動コマンド

初回は Django の migrate と collectstatic が必要になります。

従って初回起動時は以下のコマンドで実行する必要があります。

```bash
docker compose build --no-cache
docker compose up -d
docker compose exec django python manage.py makemigrations streamer
docker compose exec django python manage.py migrate
docker compose exec django python manage.py collectstatic --noinput
```

また 2 回目以降の起動であれば、`docker compose up -d`のみで起動することができます。
`django` コンテナは `postgres` の healthcheck 完了を待ってから起動します。

## 開発

settings.py で`debug = True`においてコンテナを起動させた場合に 8000 ポートにデプロイされている Django コンテナに直接アクセスすることで、Django を直叩きしてデバッグできます（debug-toolbar は撤去済み。解析は Prometheus/Grafana を利用）。

### 環境変数（dev / prod の出し分け）

`DEBUG` や `MY_DOMAIN` などの環境固有値は、monorepo ルートの env ファイルから
Compose 経由で注入されます（backend 単体ではなく、ルートで `docker compose` を実行する）。

- **dev**（ルート `.env.dev`、`DEBUG=1`）… `entrypoint.sh` が `runserver` を起動し、
  `localhost:8000` で Django を直叩きできる。
- **prod**（ルート `.env.prod`、`DEBUG=0`）… `gunicorn`（uvicorn worker）で ASGI 配信。

> `manage.py` は `/env_files/.env.global` を `override=True` で読み込みます。そのため
> **共有値のみ** `.env.global` に置き、環境固有値（`DEBUG` / `MY_DOMAIN` 等）は
> ルートの `.env.dev` / `.env.prod` に分離しています（`.env.global` に残すと prod 値が
> dev 値で上書きされるため）。詳細はルートの
> [README の「環境設定」](https://github.com/d-party/d-party#環境設定dev--prod-の出し分け)を参照。

### 開発環境を初期化

開発環境を初期化したい場合以下の手順をたどってください

1. コンテナの停止(`docker compose down`)
2. `Postgres` ディレクトリにある data ディレクトリを中身ごと削除する
3. Django/streamer ディレクトリにある migrations ディレクトリを中身事削除する

### テストを実行

テストを実行したい場合、全てのコンテナを立ち上げてから、以下のコマンドを実行してください。

```bash
docker compose exec django pytest --cov
```

> ローカル（コンテナ無し）でも `cd Django && uv run pytest` で実行できます。
> テストは `conftest.py` で InMemoryChannelLayer を使うため Redis は不要です。

#### カバレッジ（PR へのコメント / バッジ）

CI の `pytest` ジョブは `uv run pytest --cov --cov-report=xml` を実行し、
[`py-cov-action/python-coverage-comment-action`](https://github.com/py-cov-action/python-coverage-comment-action)
で **PR にカバレッジのサマリコメント** を投稿します。外部 SaaS（Codecov 等）は使わず、
`GITHUB_TOKEN` だけで動きます。バッジとカバレッジ履歴は専用ブランチ
`python-coverage-comment-action-data` に保存され、README 冒頭のバッジがそこを参照します。

action は `coverage.xml` ではなく **`.coverage`（binary）** を読むため、
`pyproject.toml` の `[tool.coverage.run]` で `relative_files = true` を有効にしています
（CI とローカルで絶対パスが異なると差分が正しく解決できないため）。

**一度だけ必要な設定（リポジトリ管理者）**

1. この PR を main へマージする。
2. main への最初の CI 実行で、action が `python-coverage-comment-action-data` ブランチを
   自動生成する（手動で作る必要はない）。
3. そのブランチが **ブランチ保護の対象になっていない** ことを確認する
   （ワイルドカードの保護ルールがある場合のみ要注意）。
4. Settings → Actions → General → *Workflow permissions* が
   **Read and write permissions** になっていることを確認する
   （ジョブ側でも `contents: write` / `pull-requests: write` を宣言済み）。
5. 以上で README 冒頭のカバレッジバッジが表示される。表示されない場合は、生成された
   `python-coverage-comment-action-data` ブランチの README に出力される最新の
   バッジ URL を確認して差し替える。

> 旧 Codecov 連携（`CODECOV_TOKEN` シークレットと codecov バッジ）は廃止しました。
> シークレットは不要になったので削除して構いません。
> なお `GIST_TOKEN` / gist ID は **不要** です。この action は v3 以降、バッジの保存先を
> Gist から上記のデータブランチへ移行しており、gist 関連の入力は存在しません。

### Lint / Format（ruff）

フォーマッタ・Lint・import 順序（旧 black + isort + flake8 系）はすべて **ruff** に統一
されています。設定は `pyproject.toml` の `[tool.ruff]` にあり、`select` に `I`（isort）を
含むため `ruff check` が import 順序も検査します。

```bash
uv sync
uv run ruff format .          # 整形
uv run ruff check . --fix     # Lint + import 整列（自動修正）
```

CI（`.github/workflows/ci.yml` の `ruff` ジョブ）は **検証のみ** を行い、違反があれば
失敗します（旧 `autoblack.yml` のようにブランチへ自動コミット / force-push はしません）。
手元で以下が通ることを確認してから push してください。

```bash
uv run ruff format --check .
uv run ruff check .
```

`pre-commit install` しておけば、コミット時に同じ ruff フックが走ります
（`.pre-commit-config.yaml`）。

### ライセンスチェックを実行

ライセンスチェックを実行したい場合、全てのコンテナを立ち上げてから、以下のコマンドを実行してください。

```bash
docker compose exec django pip-licenses
```

### 依存関係の可視化

依存関係の可視化を実行したい場合、全てのコンテナを立ち上げてから、以下のコマンドを実行してください。

```bash
docker compose exec django pipdeptree --graph-output dot > dependencies.dot
```

### Chrome 拡張機能からローカルバックエンドへ接続する（PNA の無効化）

dアニメストア (`https://anime.dmkt-sp.jp`) のページに注入された Chrome 拡張機能の
content script からローカルの `localhost` バックエンドへ繋ぐと、Chrome の
**Private Network Access (PNA)** によって接続が **コンソールにエラーを出さずサイレントに
遮断** されます（WebSocket は `code=1006 wasClean=false` で即時 close、`fetch` は
`Failed to fetch`）。「公開ネットワーク → プライベートネットワーク」への接続が
Chrome 130+ で塞がれているためです。

開発時のみ、Chrome のフラグを無効化して回避します。

1. Chrome のアドレスバーに以下を 1 つずつ開く:

   - `chrome://flags/#private-network-access-send-preflights`
   - `chrome://flags/#private-network-access-respect-preflight-results`
   - `chrome://flags/#local-network-access-check-websockets` （Chrome の新しい版で PNA から改称・WebSocket 専用の判定を行うフラグ）

2. 各フラグのドロップダウンを **Disabled** に変更
3. 右下に表示される **「Relaunch」** ボタンで Chrome を再起動

> 本番サイト (`https://d-party.net`) は public origin 同士なので PNA の影響を受けません。
> 上記フラグはローカル開発でのみ無効化してください。

恒久対応（拡張機能側）は WebSocket の生成を service worker (background) に移し、
`chrome-extension://` origin から接続する構成への変更です。

### その他

開発に必要な情報は出来る限り、[wiki](https://github.com/d-party/d-party-Backend/wiki)に集約しています。
適宜ご参照ください。

また、質問事項などがありましたら、[ディスカッション](https://github.com/d-party/d-party-Backend/discussions)からご連絡ください。

## 関連リンク

### リリース

- [d-party.net](https://d-party.net/)

### 拡張機能

#### ウェブストア

- [d-party - Chrome ウェブストア](https://chrome.google.com/webstore/detail/d-party/ibmlcfpijglpfbfgaleaeooebgdgcbpc)

#### リポジトリ

- [d-party/d-party-Chrome-Extensions](https://github.com/d-party/d-party-Chrome-Extensions)
