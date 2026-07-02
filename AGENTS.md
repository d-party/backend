# AGENTS.md — d-party Backend

このサブモジュール（`d-party-Backend`）で作業する AI エージェント・開発者向けのガイドです。
ルートの [`../AGENTS.md`](../AGENTS.md) も併せて参照してください。

## What this is

dアニメストアの「同時視聴」を支える **Django バックエンド**です。中心は
**WebSocket（Django Channels）** によるルーム内の動画プレイヤー同期で、
REST API（統計・バッジ・拡張機能バージョン確認・ロビー解決）と管理画面を提供します。
ユーザー向け公開ページ（LP・使い方・Q&A・統計・ルーム遷移ロビー）は **React フロント
エンド（`../frontend`）** へ移行済みで、nginx が公開ページをフロントへ、`/api`・`/admin`・
WebSocket（`/anime-store/party/`）を Django へ振り分けます。

> **最重要:** WebSocket のメッセージプロトコル（`streamer/format.py` の `action` と
> ペイロード形状）、DB モデルの意味、REST API の契約は **外部（Chrome 拡張・フロント）との
> 公開インターフェース**です。リファクタ時もこれらの挙動を変えないでください。

## Stack（モダナイズ後）

| 項目 | 採用 |
|---|---|
| 言語 | Python 3.14 |
| フレームワーク | Django 5.2 (LTS) · Channels 4 · DRF · djangochannelsrestframework |
| ASGI | gunicorn + `uvicorn-worker`（本番） / `runserver`（dev, DEBUG=1） |
| DB | **PostgreSQL 16**（`django-prometheus` 経由で計測） |
| キャッシュ/レイヤ | Redis 7（`channels-redis`） |
| パッケージ管理 | **uv**（`pyproject.toml` / `uv.lock`、PEP 621 + dependency-groups） |
| Lint/Format | **ruff**（`uvx ruff format` / `uvx ruff check`） |
| テスト | pytest（`pytest-django` · `pytest-asyncio` · `factory-boy` · `pytest-cov`） |
| 暗号化 | `streamer/fields.py` の Fernet ベース `EncryptedCharField`（`cryptography`） |
| 論理削除 | `streamer/mixins.py` の `LogicalDeletionMixin`（自前実装） |
| 監視 | Prometheus + Grafana + cadvisor + node-exporter |
| リバースプロキシ | Nginx |
| DB 管理 UI | Adminer（`http://localhost:8080`） |

### モダナイズで置き換えた / 削除した依存（挙動は維持）

| Before（unmaintained 等） | After |
|---|---|
| Poetry | uv |
| mysqlclient / MySQL | psycopg / PostgreSQL |
| pydantic v1 | pydantic v2（`response` 直列化は `SerializeAsAny` で v1 互換を維持） |
| django-boost（`LogicalDeletionMixin` / admin） | 自前 `streamer/mixins.py`・`streamer/admin.py` |
| django-cryptography（`encrypt`） | 自前 `streamer/fields.py`（Fernet） |
| django-dynamic-shields | 自前のプレーンな shields.io エンドポイント（`api/views.py`） |
| django-crontab | 撤去（保持期間クリーンアップ自体を廃止。リアクションはルーム終了時に `ReactionStat` へ畳み込み） |
| distutils `StrictVersion` | `api/views.py` の strict `x.y.z` パーサ |
| `.extra(select={"day": "date(...)"})`（MySQL 依存） | ORM `TruncDate`（DB 非依存） |
| black | ruff |
| django-request / django-debreach | 削除（解析は Prometheus/Grafana、CSRF は Django 標準） |

## レイアウト

# このリポジトリ（backend）は django サーバ単体。nginx / postgres / redis /
# prometheus / grafana / adminer 等のオーケストレーション（docker-compose）は
# d-party モノレポのルートにあり、本リポジトリは build context として参照される。
```
backend/   ← リポジトリ直下が django プロジェクト
  pyproject.toml          uv（依存・ruff・pytest 設定）
  uv.lock
  Dockerfile              python:3.14-slim + uv（venv は /opt/venv）
  .dockerignore           イメージから dev/CI 用ファイルを除外
  entrypoint.sh           close_active_sessions（>1日経過の ghost のみ回収）→ runserver / gunicorn
  gunicorn.conf.py        uvicorn-worker
  conftest.py             テスト時は InMemoryChannelLayer に差し替え
  manage.py               /env_files/*.env があれば読み込み（無ければ環境変数）
  .env.django             Django 用 env（DB/Redis ホスト・統計キャッシュ TTL 等）
  d_party/                settings.py · asgi.py（ProtocolTypeRouter）· urls.py
  streamer/               ★同時視聴のコア
    consumers.py          AnimePartyConsumer（create/join/leave/video_operation/sync/reaction…）
    format.py             pydantic v2 メッセージ定義（公開プロトコル）
    models.py             AnimeRoom / AnimeUser / AnimeReaction / AnimeRoomHistory
    mixins.py             LogicalDeletionMixin（alive/dead/delete(hard=)）
    fields.py             EncryptedCharField（保存時暗号化）
    routing.py            ws: anime-store/party/
    cron.py               fold_room_reactions（ルーム終了時にリアクションを ReactionStat へ畳み込む）
    management/commands/close_active_sessions.py  起動時に >1日経過の ghost セッションを回収
  api/                    DRF（統計 / shields バッジ / 拡張機能バージョン確認）
  web/                    管理者向け統計チャートのテンプレート（admin/chart のみ。
                          LP・使い方・ロビーは frontend へ移行）
```

### Request / data flow

```
Chrome 拡張 (content script) ──wss──▶ Nginx ──▶ Django(ASGI/Channels)
                                              ├─ REST API (DRF)     : /api/*
                                              ├─ WebSocket          : /anime-store/party/
                                              └─ 管理画面 (Jazzmin) : /admin/*
Django ──▶ PostgreSQL（永続化） / Redis（Channels レイヤ）
```

## 設定の外部化（k3s 移行を見据えて）

サービス間のホスト解決は **すべて環境変数（.env ファイル）に外出し** している。Docker では
Compose のサービス名で解決し、k3s 等へ移行する際は env（ConfigMap）を差し替えるだけでよい。

| 変数 | 既定（Docker） | 用途 | 置き場所 |
|---|---|---|---|
| `DATABASE_HOST` / `DATABASE_PORT` | `postgres` / `5432` | Django → PostgreSQL | `.env.django` |
| `REDIS_HOST` / `REDIS_PORT` | `redis` / `6379` | Channels レイヤ | `.env.django` |
| `DJANGO_UPSTREAM` | `django:8000` | nginx → Django | ルート `.env.global` |
| `FRONTEND_UPSTREAM` | `frontend:3000` | nginx → フロント | ルート `.env.global` |
| `GRAFANA_UPSTREAM` | `grafana:3000` | nginx → Grafana | ルート `.env.global` |

- nginx / `.env.global` 等のインフラ設定は **d-party モノレポのルート**にある。アプリ側の
  nginx 設定やコードを触らず、env だけで解決先を変更できる。
- k3s では各 Service の DNS（例: `django.<ns>.svc.cluster.local:8000`）を上記変数へ設定する。

## Common commands

### 起動（Docker, 推奨）

docker-compose は **モノレポのルート**にある（このリポジトリは django 単体）。
全サービスを起動する場合はルートで:

```bash
# d-party モノレポのルートで
docker compose build
docker compose up -d
# 初回のみ（migration ファイルはリポジトリにコミット済みなので migrate のみ。
# モデルを変更したときだけローカルで makemigrations して生成物をコミットする）
docker compose exec django python manage.py migrate
docker compose exec django python manage.py collectstatic --noinput
```

> `django` は `postgres` の healthcheck 完了を待って起動します（compose の `depends_on`）。

### ローカル（uv, コンテナ無し）

```bash
uv sync                       # 依存をインストール（.venv 作成）
uv run python manage.py check
uv run pytest                 # conftest.py が InMemoryChannelLayer を使うため Redis 不要
uvx ruff format .             # 整形
uvx ruff check . --fix        # Lint（自動修正）
```

必要な環境変数（コンテナ外で動かす場合）: `SECRET_KEY`, `DEBUG`, `MY_DOMAIN`,
`POSTGRES_DB`, `POSTGRES_PASSWORD`, `DATABASE_USER`, `DATABASE_HOST`, `DATABASE_PORT`,
`DATABASE_ENGINE`, `REDIS_HOST`, `REDIS_PORT`, `LANGUAGE_CODE`, `TIME_ZONE`,
`D_ANIME_STORE_DOMAIN`, `CHROME_EXTENSION_REQUIRED_VERSION`。

### ghost セッションの回収

時間ベースの保持期間クリーンアップ（旧 system cron）は廃止した。リアクションはルーム終了時に
`fold_room_reactions` が `ReactionStat` へ畳み込むため生データは溜まらない。

ハードクラッシュ（graceful でない停止）で `disconnect` が走らず alive のまま残った
`AnimeRoom`/`AnimeUser` は、起動時の `close_active_sessions` が回収する。セッションは 1 日以上
続かない前提で、`updated_at` が 1 日以上前の alive 行だけを論理削除するため、複数レプリカで
別 Pod の稼働中セッションを巻き込まない（手動実行も可）。

```bash
docker compose exec django python manage.py close_active_sessions
```

## 動作確認 URL（ローカル）

| URL | 内容 |
|-----|------|
| `http://localhost` | アプリ（Nginx 経由） |
| `http://localhost:8000` | Django 直接（debug-toolbar） |
| `http://localhost:8080` | Adminer（PostgreSQL 管理） |
| `http://localhost:9090` | Prometheus |
| `http://localhost:3000` | Grafana |

## コアを壊さないための注意

- **WebSocket プロトコル**: `streamer/format.py` の各クラスの `action` 値・フィールド名・
  ネスト構造は固定。pydantic v2 では基底型フィールド（`response`）の直列化で
  サブクラス固有フィールドが落ちるため、`SerializeAsAny` を必ず使うこと。
- **モデル意味論**: `LogicalDeletionMixin` の `objects.alive()` / `delete()`（論理）/
  `delete(hard=True)`（物理）の挙動は `mixins.py` で再現済み。変更しない。
- **暗号化**: `AnimeUser.user_name` は `EncryptedCharField` で保存時暗号化（鍵は
  `SECRET_KEY` 由来）。`SECRET_KEY` を変えると既存データは復号できなくなる。
- **API 契約**: `api/urls.py` のパスとレスポンス形状（特に shields は
  `{"schemaVersion":1, ...}`）は外部バッジ・拡張から参照される。
- **タイマー / 観覧専用（spectator）**: `spectate` アクションは `AnimeUser` を作らずグループへ
  読み取り専用参加する（人数/一覧/ホスト委譲/自動削除に非影響）。タイマー画面（フロント）が
  `video_operation` を受信して再生位置を計算するための経路。`video_operation` の任意 `title` は
  エピソード切替の追従用（旧クライアントは送らないため `None`）。フロント（`MY_DOMAIN`）の
  オリジンから WS を張るため、`asgi.py` の `OriginValidator` に `MY_DOMAIN` を許可済み。
  `host_send`/`user_send` は `anime_user is None`（spectator）をガードすること。

## サブモジュール運用

このディレクトリは独立した Git リポジトリ（`d-party-Backend`）です。変更はここで
ブランチを切り、上流へ PR を出してください。ルート monorepo 側は参照 SHA のみ管理します。
詳細は [`../AGENTS.md`](../AGENTS.md) を参照。
