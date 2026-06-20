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

from .models import AnimeReaction, AnimeRoom, AnimeUser


def _cutoff(days: int) -> datetime.datetime:
    return datetime.datetime.now() - datetime.timedelta(days=days)


def animeroom_auto_logical_delete():
    """Logically delete AnimeRooms that have outlived the logical retention."""
    days = int(os.getenv("LOGICAL_DIVIDE_DAY", default="3"))
    AnimeRoom.objects.alive().filter(updated_at__lte=_cutoff(days)).delete()


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


def animereaction_auto_hard_delete():
    """Hard delete AnimeReactions that have outlived the hard retention."""
    days = int(os.getenv("REACTION_HARD_DIVIDE_DAY", default="90"))
    AnimeReaction.objects.all().filter(created_at__lte=_cutoff(days)).delete(hard=True)


ALL_JOBS = (
    animeroom_auto_logical_delete,
    animeuser_auto_logical_delete,
    animeroom_auto_hard_delete,
    animeuser_auto_hard_delete,
    animereaction_auto_hard_delete,
)
