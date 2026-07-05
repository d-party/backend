"""Reaction folding on room end.

A room's per-tap ``AnimeReaction`` rows are folded into the compact
``ReactionStat`` aggregate the moment the room ends (host delete / grace-period
delete) and the raw rows are hard-deleted, so the database only retains
aggregates. This is part of the stats contract and runs from ``consumers.py`` —
it is *not* a scheduled job (the previous time-based retention cron has been
removed; ``AnimeReaction`` no longer accumulates unbounded thanks to folding).
"""

from django.db.models import Count, F
from django.db.models.functions import TruncDate

from .models import AnimeReaction, ReactionStat


def fold_room_reactions(room_id, *, reaction_model=None, stat_model=None) -> None:
    """Fold a room's reactions into the stat aggregate then hard-delete the rows.

    Called whenever a room ends (host delete / grace-period delete). Reactions
    are aggregated per ``(creation day, reaction_type)`` and added to the
    matching stat row (created if missing), so the raw reaction rows can be
    removed for good — only aggregates remain.

    ``reaction_model`` / ``stat_model`` はサービス別に差し替える（dアニメ /
    DMM）。未指定なら従来どおり dアニメの ``AnimeReaction`` → ``ReactionStat``。
    """
    reaction_model = reaction_model or AnimeReaction
    stat_model = stat_model or ReactionStat
    rows = (
        reaction_model.objects.filter(room_id=room_id)
        .annotate(day=TruncDate("created_at"))
        .values("day", "reaction_type")
        .annotate(n=Count("reaction_id"))
    )
    for row in rows:
        _, created = stat_model.objects.get_or_create(
            date=row["day"],
            reaction_type=row["reaction_type"],
            defaults={"count": row["n"]},
        )
        if not created:
            stat_model.objects.filter(
                date=row["day"], reaction_type=row["reaction_type"]
            ).update(count=F("count") + row["n"])
    reaction_model.objects.filter(room_id=room_id).delete(hard=True)
