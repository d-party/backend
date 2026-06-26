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
    # 表示アイコン。フロント（拡張）が react-icons (Font Awesome 6) のキー文字列を送る。
    # アイコン名は PII ではないため平文。旧拡張が送らない場合は既定キーで、現行のシンプルな
    # ユーザーアイコン相当（FaRegUser）にフォールバックさせる。
    user_icon = models.CharField(default="FaRegUser", max_length=64)
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


class ReactionStat(models.Model):
    """日次 × 種別に畳み込んだリアクションの集計。

    リアクションは 1 タップ = 1 行（``AnimeReaction``）で大量に蓄積されるため、ルームが
    終了する瞬間に ``cron.fold_room_reactions`` がそのルームのリアクションを日次×種別で
    ここへ加算し、元の ``AnimeReaction`` 行はハードデリートする。これにより DB には
    集計済みの統計だけが残り、生データは溜まらない。``(date, reaction_type)`` で一意。
    """

    date = models.DateField()
    reaction_type = models.CharField(max_length=3, choices=ReactionType.choices)
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["date", "reaction_type"], name="uniq_reactionstat_date_type"
            )
        ]
        indexes = [models.Index(fields=["date"])]
