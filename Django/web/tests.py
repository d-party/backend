# ランディング（/）・使い方（/usage）・ルーム遷移ロビー（/anime-store/lobby/...）は
# React フロントエンド（frontend サブモジュール）へ移行し、Django 側のルート/ビューは
# 廃止した。ロビーの room_id → リダイレクト URL 解決は api.views へ移設しており、
# その振る舞いは api/tests.py で検証する。
#
# web アプリに残るのは管理者向けの admin/chart（要ログイン）のみで、公開ページの
# ビューは存在しないため、ここにテストは無い。
