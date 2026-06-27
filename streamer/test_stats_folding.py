"""Tests for reaction folding into ``ReactionStat`` on room end."""

import datetime

import pytest
from django.utils import timezone

from .cron import fold_room_reactions
from .factories import AnimeRoomFactory
from .models import AnimeReaction, ReactionStat


def _make_reaction(room, reaction_type: str, when: datetime.datetime):
    """Create a reaction then force ``created_at`` (``auto_now_add`` ignores it)."""
    reaction = AnimeReaction.objects.create(room_id=room, reaction_type=reaction_type)
    AnimeReaction.objects.filter(pk=reaction.pk).update(created_at=when)
    return reaction


@pytest.mark.django_db
def test_fold_room_reactions_aggregates_and_hard_deletes():
    """畳み込みで日次×種別に集計され、生の AnimeReaction は物理削除される。"""
    room = AnimeRoomFactory()
    day1 = timezone.now() - datetime.timedelta(days=2)
    day2 = timezone.now() - datetime.timedelta(days=1)
    _make_reaction(room, "S", day1)
    _make_reaction(room, "S", day1)
    _make_reaction(room, "F", day1)
    _make_reaction(room, "S", day2)

    fold_room_reactions(room.room_id)

    # 生データはハードデリート済み。
    assert AnimeReaction.objects.filter(room_id=room.room_id).count() == 0
    # day1: S=2, F=1 / day2: S=1。
    assert ReactionStat.objects.get(date=day1.date(), reaction_type="S").count == 2
    assert ReactionStat.objects.get(date=day1.date(), reaction_type="F").count == 1
    assert ReactionStat.objects.get(date=day2.date(), reaction_type="S").count == 1


@pytest.mark.django_db
def test_fold_room_reactions_accumulates_into_existing_rows():
    """同じ日×種別へ複数回畳み込むと count が加算される。"""
    day = timezone.now() - datetime.timedelta(days=1)

    room_a = AnimeRoomFactory()
    _make_reaction(room_a, "TU", day)
    _make_reaction(room_a, "TU", day)
    fold_room_reactions(room_a.room_id)

    room_b = AnimeRoomFactory()
    _make_reaction(room_b, "TU", day)
    fold_room_reactions(room_b.room_id)

    assert ReactionStat.objects.get(date=day.date(), reaction_type="TU").count == 3
