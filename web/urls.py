from django.urls import path

from . import views

urlpatterns = [
    # ランディング / 使い方 / ルーム遷移ロビーは React フロントエンド（frontend
    # サブモジュール）へ移行済み。nginx が公開ページをフロントへ振り分ける。
    # 統計チャートは管理者向けのため Django 側に残す。
    path("admin/chart", views.AdminChartsView.as_view()),
]
