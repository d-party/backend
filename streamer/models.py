import uuid

from django.db import models

from .fields import EncryptedCharField
from .mixins import LogicalDeletionMixin

# ---------------------------------------------------------------------------
# 抽象基底モデル（サービス共通のスキーマ）
#
# d-party は dアニメストア（``Anime*``）と DMM TV（``Dmm*``）の 2 サービスを扱う。
# 同時視聴の同期ロジック（consumer / stats / grace 削除）はサービス非依存なので、
# テーブルのスキーマも共通化する。共通フィールドをここに抽象基底として置き、
# サービスごとの具象モデルが継承する。**抽象継承は純 Python なので既存の
# ``anime_*`` テーブルにはスキーマ変化が起きない**（マイグレーション不要）。
#
# 具象モデルへの外部キー（``room`` 参照）だけは、参照先が具象ごとに異なるため
# 抽象基底に置けない（抽象基底の FK は単一ターゲットに固定されてしまう）。
# そのため FK/OneToOne は各具象モデル側で宣言する。
# ---------------------------------------------------------------------------


class BaseRoom(LogicalDeletionMixin):
    """ルームの共通スキーマ。具象は ``AnimeRoom`` / ``DmmRoom``。"""

    room_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    num_people = models.PositiveSmallIntegerField(default=1)
    sum_people = models.PositiveSmallIntegerField(default=1)
    part_id = models.CharField(max_length=16)
    # 視聴中コンテンツのタイトル。ルーム作成時に拡張機能がページ DOM から取得して
    # 一度だけ送信する（以降は更新しない）。OGP 等の表示に使う。
    title = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BaseSetting(models.Model):
    """ルームごとの詳細設定の共通スキーマ。具象は ``Setting`` / ``DmmSetting``。

    ルームと 1:1 で対応し、``room`` を主キーとして共有する（``room`` は具象側で宣言）。
    ルーム作成時に既定値（すべて ``False``）で自動生成され、以降はオーナー（ホスト）
    ユーザーのみが WebSocket（Channels）経由で更新できる。オーナー以外からの更新要求は
    consumer 側で無視される。旧クライアントは設定を送らないため、全 ``False`` = 現行の
    ルーム挙動となり後方互換が保たれる。

    Attributes:
        one_way: 一方通行（アクセラレーター）モード。オーナーのみが動画操作でき、
            オーナー以外からの動画操作はブロックされる（リアクションは許可）。有効時は
            オーナー退室でルームが自動削除される（``owner_leave_delete`` を含意）。
        owner_leave_delete: オーナー退室時にルームを自動削除する。
        disable_reaction: リアクションを禁止する。ブロードキャストも永続化もされない
            （送信者自身の画面にはクライアント側でローカル表示される）。
    """

    one_way = models.BooleanField(default=False)
    owner_leave_delete = models.BooleanField(default=False)
    disable_reaction = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BaseUser(LogicalDeletionMixin):
    """参加ユーザーの共通スキーマ。具象は ``AnimeUser`` / ``DmmUser``。"""

    user_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_name = EncryptedCharField(default="user", max_length=20)
    # 表示アイコン。フロント（拡張）が react-icons (Font Awesome 6) のキー文字列を送る。
    # アイコン名は PII ではないため平文。旧拡張が送らない場合は既定キーで、現行のシンプルな
    # ユーザーアイコン相当（FaRegUser）にフォールバックさせる。
    user_icon = models.CharField(default="FaRegUser", max_length=64)
    is_host = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.user_name


class ReactionType(models.TextChoices):
    cry = "C", "cry"
    middle_finger = "MF", "middle_finger"
    smile = "S", "smile"
    thumbs_up = "TU", "thumbs_up"
    fav = "F", "favorite"


class BaseReaction(LogicalDeletionMixin):
    """リアクション（1 タップ = 1 行）の共通スキーマ。具象は ``AnimeReaction`` / ``DmmReaction``。"""

    reaction_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reaction_type = models.CharField(max_length=3, choices=ReactionType.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class BaseRoomHistory(models.Model):
    """入退室履歴の共通スキーマ。具象は ``AnimeRoomHistory`` / ``DmmRoomHistory``。"""

    user_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=20)

    class Meta:
        abstract = True


class BaseReactionStat(models.Model):
    """日次 × 種別に畳み込んだリアクションの集計（共通スキーマ）。

    リアクションは 1 タップ = 1 行（``Base*Reaction``）で大量に蓄積されるため、ルームが
    終了する瞬間に ``cron.fold_room_reactions`` がそのルームのリアクションを日次×種別で
    ここへ加算し、元の生 Reaction 行はハードデリートする。これにより DB には集計済みの
    統計だけが残り、生データは溜まらない。``(date, reaction_type)`` で一意。

    具象（``ReactionStat`` / ``DmmReactionStat``）は制約・インデックス名が衝突しないよう
    それぞれ独自の ``Meta`` を宣言する。
    """

    date = models.DateField()
    reaction_type = models.CharField(max_length=3, choices=ReactionType.choices)
    count = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# dアニメストア（既存）: フィールド定義は従来と完全同一に保つ。抽象継承は純 Python
# なので ``streamer_animeroom`` などの既存テーブルにマイグレーションは発生しない。
# ---------------------------------------------------------------------------


class AnimeRoom(BaseRoom):
    pass


class Setting(BaseSetting):
    room = models.OneToOneField(
        AnimeRoom,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="setting",
    )


class AnimeUser(BaseUser):
    room_id = models.ForeignKey(
        AnimeRoom, on_delete=models.CASCADE, related_name="inroom"
    )


class AnimeReaction(BaseReaction):
    room_id = models.ForeignKey(AnimeRoom, on_delete=models.CASCADE)


class AnimeRoomHistory(BaseRoomHistory):
    room_id = models.ForeignKey(AnimeRoom, on_delete=models.CASCADE)


class ReactionStat(BaseReactionStat):
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["date", "reaction_type"], name="uniq_reactionstat_date_type"
            )
        ]
        indexes = [models.Index(fields=["date"])]


# ---------------------------------------------------------------------------
# DMM TV（新規）: 具象のみ追加。新テーブルなので追加マイグレーションのみが生成される。
# ---------------------------------------------------------------------------


class DmmRoom(BaseRoom):
    # DMM TV の content/season id は英数字で 25 文字前後あり、dアニメストアの数値 partId
    # より長い。抽象基底の part_id(max_length=16) を DMM 向けに拡張する（既存 anime 側の
    # スキーマには影響しない。抽象基底フィールドの上書きは Django が許可している）。
    part_id = models.CharField(max_length=128)


class DmmSetting(BaseSetting):
    room = models.OneToOneField(
        DmmRoom,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="setting",
    )


class DmmUser(BaseUser):
    room_id = models.ForeignKey(
        DmmRoom, on_delete=models.CASCADE, related_name="inroom"
    )


class DmmReaction(BaseReaction):
    room_id = models.ForeignKey(DmmRoom, on_delete=models.CASCADE)


class DmmRoomHistory(BaseRoomHistory):
    room_id = models.ForeignKey(DmmRoom, on_delete=models.CASCADE)


class DmmReactionStat(BaseReactionStat):
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["date", "reaction_type"],
                name="uniq_dmm_reactionstat_date_type",
            )
        ]
        indexes = [models.Index(fields=["date"])]
