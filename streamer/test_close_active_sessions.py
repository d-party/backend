"""Tests for the startup ghost-session reaper (``close_active_sessions``).

Only rooms/users whose ``updated_at`` is older than ``STALE_AFTER`` should be
closed; sessions touched recently (i.e. still being served) must be left alive
so that running on a fresh replica never wipes another replica's live sessions.
"""

import datetime

import pytest
from django.core.management import call_command
from django.utils import timezone

from .factories import AnimeRoomFactory, AnimeUserFactory
from .models import AnimeRoom, AnimeUser


def _set_updated_at(instance, when):
    """Force ``updated_at`` past the ``auto_now`` that fires on save."""
    type(instance).objects.filter(pk=instance.pk).update(updated_at=when)


@pytest.mark.django_db
def test_closes_only_stale_alive_rows():
    stale = timezone.now() - datetime.timedelta(days=2)
    fresh = timezone.now() - datetime.timedelta(minutes=5)

    stale_user = AnimeUserFactory()
    fresh_user = AnimeUserFactory()
    _set_updated_at(stale_user.room_id, stale)
    _set_updated_at(stale_user, stale)
    _set_updated_at(fresh_user.room_id, fresh)
    _set_updated_at(fresh_user, fresh)

    call_command("close_active_sessions")

    # 古い (>1日) 行は論理削除され、新しい行は alive のまま残る。
    assert AnimeUser.objects.alive().filter(pk=stale_user.pk).exists() is False
    assert AnimeRoom.objects.alive().filter(pk=stale_user.room_id.pk).exists() is False
    assert AnimeUser.objects.alive().filter(pk=fresh_user.pk).exists() is True
    assert AnimeRoom.objects.alive().filter(pk=fresh_user.room_id.pk).exists() is True


@pytest.mark.django_db
def test_idempotent_and_keeps_recent_room():
    room = AnimeRoomFactory()
    _set_updated_at(room, timezone.now())

    call_command("close_active_sessions")
    call_command("close_active_sessions")

    assert AnimeRoom.objects.alive().filter(pk=room.pk).exists() is True
