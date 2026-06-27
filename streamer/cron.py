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


def fold_room_reactions(room_id) -> None:
    """Fold a room's reactions into ``ReactionStat`` then hard-delete the rows.

    Called whenever a room ends (host delete / grace-period delete). Reactions
    are aggregated per ``(creation day, reaction_type)`` and added to the
    matching ``ReactionStat`` row (created if missing), so the raw
    ``AnimeReaction`` rows can be removed for good — only aggregates remain.
    """
    rows = (
        AnimeReaction.objects.filter(room_id=room_id)
        .annotate(day=TruncDate("created_at"))
        .values("day", "reaction_type")
        .annotate(n=Count("reaction_id"))
    )
    for row in rows:
        _, created = ReactionStat.objects.get_or_create(
            date=row["day"],
            reaction_type=row["reaction_type"],
            defaults={"count": row["n"]},
        )
        if not created:
            ReactionStat.objects.filter(
                date=row["day"], reaction_type=row["reaction_type"]
            ).update(count=F("count") + row["n"])
    AnimeReaction.objects.filter(room_id=room_id).delete(hard=True)
