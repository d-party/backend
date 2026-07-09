"""django-unfold の管理画面ダッシュボード用コールバック。

``settings.UNFOLD`` の ``DASHBOARD_CALLBACK`` / ``ENVIRONMENT`` から参照される。
同時視聴サービスの状態を一目で把握できる KPI カードとリアクション内訳を、
トップページ（``admin:index``）へ差し込む。
"""

from __future__ import annotations

from django.conf import settings
from django.db.models import Count, Sum
from django.utils.timezone import localdate

from streamer.models import (
    AnimeReaction,
    AnimeRoom,
    AnimeUser,
    ReactionStat,
    ReactionType,
)


def environment_callback(request):
    """右上に表示する環境バッジ ``[ラベル, 色]`` を返す。

    色は unfold のラベル種別（``success`` / ``warning`` / ``danger`` / ``info``）。
    """
    if settings.DEBUG:
        return ["Development", "warning"]
    return ["Production", "danger"]


def _reaction_breakdown():
    """種別ごとの累計リアクション数を求める。

    リアクションはルーム終了時に ``ReactionStat`` へ日次×種別で畳み込まれ、生の
    ``AnimeReaction`` はハードデリートされる。したがって「畳み込み済みの集計」と
    「まだルームが生きている未畳み込みの生データ」を合算する。
    """
    counts: dict[str, int] = {value: 0 for value, _label in ReactionType.choices}

    folded = ReactionStat.objects.values("reaction_type").annotate(total=Sum("count"))
    for row in folded:
        counts[row["reaction_type"]] = counts.get(row["reaction_type"], 0) + (
            row["total"] or 0
        )

    live = (
        AnimeReaction.objects.alive()
        .values("reaction_type")
        .annotate(total=Count("reaction_id"))
    )
    for row in live:
        counts[row["reaction_type"]] = (
            counts.get(row["reaction_type"], 0) + row["total"]
        )

    label_of = dict(ReactionType.choices)
    total = sum(counts.values())
    breakdown = [
        {
            "label": label_of.get(value, value),
            "count": count,
            "percent": round(count / total * 100) if total else 0,
        }
        for value, count in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    ]
    return breakdown, total


def dashboard_callback(request, context):
    """トップページへ KPI カードとリアクション内訳を追加する。"""
    today = localdate()

    alive_rooms = AnimeRoom.objects.alive().count()
    alive_users = AnimeUser.objects.alive().count()
    rooms_today = AnimeRoom.objects.filter(created_at__date=today).count()

    breakdown, total_reactions = _reaction_breakdown()

    context.update(
        {
            "dp_cards": [
                {
                    "title": "アクティブなルーム",
                    "value": alive_rooms,
                    "icon": "meeting_room",
                    "description": "現在 alive な視聴ルーム",
                },
                {
                    "title": "接続中ユーザー",
                    "value": alive_users,
                    "icon": "group",
                    "description": "現在 alive な参加ユーザー",
                },
                {
                    "title": "本日作成ルーム",
                    "value": rooms_today,
                    "icon": "today",
                    "description": "論理削除済みを含む本日の作成数",
                },
                {
                    "title": "累計リアクション",
                    "value": f"{total_reactions:,}",
                    "icon": "favorite",
                    "description": "ReactionStat + 未畳み込みの合算",
                },
            ],
            "dp_reaction_breakdown": breakdown,
        }
    )
    return context
