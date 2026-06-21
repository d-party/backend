import uuid

from django.db import models

from .fields import EncryptedCharField
from .mixins import LogicalDeletionMixin


class AnimeRoom(LogicalDeletionMixin):
    room_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    num_people = models.PositiveSmallIntegerField(default=1)
    sum_people = models.PositiveSmallIntegerField(default=1)
    part_id = models.CharField(max_length=16)
    # 視聴中アニメのタイトル。ルーム作成時に拡張機能がページ DOM から取得して
    # 一度だけ送信する（以降は更新しない）。OGP 等の表示に使う。
    title = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class AnimeUser(LogicalDeletionMixin):
    user_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_name = EncryptedCharField(default="user", max_length=20)
    room_id = models.ForeignKey(
        AnimeRoom, on_delete=models.CASCADE, related_name="inroom"
    )
    is_host = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user_name


class ReactionType(models.TextChoices):
    cry = "C", "cry"
    middle_finger = "MF", "middle_finger"
    smile = "S", "smile"
    thumbs_up = "TU", "thumbs_up"
    fav = "F", "favorite"


class AnimeReaction(LogicalDeletionMixin):
    reaction_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room_id = models.ForeignKey(AnimeRoom, on_delete=models.CASCADE)
    reaction_type = models.CharField(max_length=3, choices=ReactionType.choices)
    created_at = models.DateTimeField(auto_now_add=True)


class AnimeRoomHistory(models.Model):
    user_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room_id = models.ForeignKey(AnimeRoom, on_delete=models.CASCADE)
    type = models.CharField(max_length=20)
