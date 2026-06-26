"""Periodic maintenance jobs.

Previously scheduled through the unmaintained ``django-crontab``; now invoked
by the ``cleanup`` management command (driven by the container's system cron).

The deletion semantics are unchanged: ``QuerySet.delete()`` performs a logical
delete, ``QuerySet.delete(hard=True)`` performs a hard delete — both persist
immediately, so the previous (no-op, and on a ``QuerySet`` actually invalid)
``.save()`` follow-up calls have been removed.
"""

import datetime
import os

from django.db.models import Count, F
from django.db.models.functions import TruncDate

from .models import AnimeReaction, AnimeRoom, AnimeUser, ReactionStat


def _cutoff(days: int) -> datetime.datetime:
    return datetime.datetime.now() - datetime.timedelta(days=days)


def fold_room_reactions(room_id) -> None:
    """Fold a room's reactions into ``ReactionStat`` then hard-delete the rows.

    Called whenever a room ends (host delete / grace-period delete / idle
    cleanup). Reactions are aggregated per ``(creation day, reaction_type)`` and
    added to the matching ``ReactionStat`` row (created if missing), so the raw
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


def animeroom_auto_logical_delete():
    """Logically delete AnimeRooms that have outlived the logical retention.

    Folds each expiring room's reactions into ``ReactionStat`` (and hard-deletes
    the raw rows) before the room itself is logically deleted.
    """
    days = int(os.getenv("LOGICAL_DIVIDE_DAY", default="3"))
    expiring = AnimeRoom.objects.alive().filter(updated_at__lte=_cutoff(days))
    for room_id in list(expiring.values_list("room_id", flat=True)):
        fold_room_reactions(room_id)
    expiring.delete()


def animeroom_auto_hard_delete():
    """Hard delete AnimeRooms that have outlived the hard retention."""
    days = int(os.getenv("HARD_DIVIDE_DAY", default="365"))
    AnimeRoom.objects.all().filter(updated_at__lte=_cutoff(days)).delete(hard=True)


def animeuser_auto_logical_delete():
    """Logically delete AnimeUsers that have outlived the logical retention."""
    days = int(os.getenv("LOGICAL_DIVIDE_DAY", default="3"))
    AnimeUser.objects.alive().filter(updated_at__lte=_cutoff(days)).delete()


def animeuser_auto_hard_delete():
    """Hard delete AnimeUsers that have outlived the hard retention."""
    days = int(os.getenv("HARD_DIVIDE_DAY", default="365"))
    AnimeUser.objects.all().filter(updated_at__lte=_cutoff(days)).delete(hard=True)


ALL_JOBS = (
    animeroom_auto_logical_delete,
    animeuser_auto_logical_delete,
    animeroom_auto_hard_delete,
    animeuser_auto_hard_delete,
)
