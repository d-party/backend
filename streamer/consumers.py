import asyncio
import json
import uuid

from channels.db import database_sync_to_async
from django.db import transaction
from djangochannelsrestframework.decorators import action
from djangochannelsrestframework.generics import GenericAsyncAPIConsumer

from .cron import fold_room_reactions
from .format import (
    Create,
    GroupSend,
    HostSend,
    Join,
    Leave,
    OperationNotification,
    Reaction,
    RoomSend,
    RoomSetting,
    ServerMessage,
    SettingSend,
    SyncRequest,
    SyncResponse,
    User,
    UserAdd,
    UserList,
    UserSend,
    VideoOperation,
)
from .models import AnimeReaction, AnimeRoom, AnimeUser, ReactionType, Setting
from .util import is_valid_uuid

# ホストの WS が一瞬落ちた / タブをリロードしただけでルームが即消え
# すると、ゲストが共有リンクを踏んだときにもう failed_join になる。
# 最後のユーザが離脱しても N 秒はルームを生かしておき、その間に誰かが
# 再参加したら削除をキャンセルして生かす。ディスクに状態を持たずプロセス
# 内の dict + asyncio.Task で追跡（runserver / 単一 daphne ワーカー前提）。
ROOM_GRACE_SECONDS = 60.0
_pending_room_deletes: dict[str, asyncio.Task] = {}


@database_sync_to_async
def _count_alive_users_in_room(room_id_str: str) -> int:
    return AnimeUser.objects.alive().filter(room_id=room_id_str).count()


@database_sync_to_async
def _logical_delete_room_if_empty(room_id_str: str) -> bool:
    """Delete room only if it is still empty. Returns True if deleted."""
    qs = AnimeRoom.objects.alive().filter(room_id=room_id_str)
    if not qs.exists():
        return False
    if AnimeUser.objects.alive().filter(room_id=room_id_str).exists():
        return False
    # ルームが終了するので、リアクションを集計テーブルへ畳んで生データを削除する。
    fold_room_reactions(room_id_str)
    qs.delete()  # logical
    return True


def _cancel_pending_room_delete(room_id_str: str) -> None:
    """Cancel a scheduled grace-period delete if any (e.g., on rejoin)."""
    task = _pending_room_deletes.pop(room_id_str, None)
    if task and not task.done():
        task.cancel()


def _schedule_room_delete(room_id_str: str, delay: float = ROOM_GRACE_SECONDS) -> None:
    """Schedule a logical-delete after `delay` seconds, replacing any prior task."""
    _cancel_pending_room_delete(room_id_str)

    async def _delete_after() -> None:
        try:
            await asyncio.sleep(delay)
            await _logical_delete_room_if_empty(room_id_str)
        except asyncio.CancelledError:
            pass
        finally:
            _pending_room_deletes.pop(room_id_str, None)

    _pending_room_deletes[room_id_str] = asyncio.create_task(_delete_after())


class AnimePartyConsumer(GenericAsyncAPIConsumer):
    permission_classes = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 入室したAnimeRoomのオブジェクト
        self.anime_room = None
        # ユーザー情報
        self.anime_user = None
        # ルームの詳細設定のローカルキャッシュ（{one_way, owner_leave_delete,
        # disable_reaction}）。create/join で読み込み、setting_send で更新する。
        # 一方通行モードの動画操作ブロック等をこのキャッシュで判定し、都度 DB を引かない。
        self.room_setting = None

    # ── 詳細設定のキャッシュ参照ヘルパ（純粋・同期）─────────────────────────────
    def _one_way(self) -> bool:
        return bool((self.room_setting or {}).get("one_way"))

    def _disable_reaction(self) -> bool:
        return bool((self.room_setting or {}).get("disable_reaction"))

    def _effective_owner_leave_delete(self) -> bool:
        """オーナー退室時自動削除の実効値。一方通行モードはこれを含意する。"""
        s = self.room_setting or {}
        return bool(s.get("owner_leave_delete")) or bool(s.get("one_way"))

    async def connect(self):
        await self.accept()

    async def disconnect(self, close_code):
        """websocketを閉じた場合の処理
        self.close()でも呼び出される

        Args:
            close_code (int): WebSocket のクローズコード
        """
        await self.leave_party()

    @action()
    async def create(
        self, part_id, user_name, title="", user_icon="FaRegUser", **kwargs
    ):
        # create room
        self.anime_room = await self.database_create_room(part_id=part_id, title=title)
        # create user
        self.anime_user = await self.database_create_user(
            user_name=user_name,
            room_id=self.anime_room,
            is_host=True,
            user_icon=user_icon,
        )
        await self.channel_layer.group_add(
            str(self.anime_room.room_id), self.channel_name
        )
        user = User(**self.anime_user.__dict__)
        create = Create(room_id=self.anime_room.room_id, user=user)
        await self.send(text_data=json.dumps(create.model_dump(mode="json")))
        user_list = await self.database_user_list()
        user_list_data = UserList(user_list=user_list)
        response_data = RoomSend(
            response=user_list_data,
            sender_channel_name=self.channel_name,
        )
        await self.channel_layer.group_send(
            str(self.anime_room.room_id),
            response_data.model_dump(mode="json"),
        )
        # ルームと 1:1 の詳細設定を既定値(すべて False)で自動生成し、作成者へ通知する。
        # 初期設定はこの直後にクライアントが update_setting で適用する運用のため、create
        # メッセージ自体は変更しない（設定を送らない旧拡張は全 False = 現行挙動）。
        self.room_setting = await self.database_get_or_create_setting()
        await self.send(
            text_data=json.dumps(
                RoomSetting(**self.room_setting).model_dump(mode="json")
            )
        )

    @action()
    async def join(
        self, room_id: uuid, user_name: str, user_icon="FaRegUser", **kwargs
    ):
        """joinを受け取った場合のアクション
        joinを受け取った場合、ルームが存在していればルームに参加する

        Args:
            room_id (uuid): AnimeRoomオブジェクトに存在するroom_id
            user_name (str): ユーザーが指定する事ができるユーザー名
            user_icon (str): ユーザーが指定する react-icons (FA6) のキー。旧拡張は送らないため既定値あり。
        """
        # 接続要求されたルームのオブジェクトがあれば取得（deleted_at が入っているものは弾く）
        self.anime_room = await self.database_get_or_none_room(room_id=room_id)
        if self.anime_room is None:
            # ルームが存在しない/既に終了している場合は failed_join を通知してクローズ。
            # 旧実装は send 後に leave_party() を呼んでいたが anime_user 未生成のため
            # 早期 return するだけで WS が開いたままになり、後続の sync_request 等が
            # self.anime_user.__dict__ で AttributeError を起こして 1011 close を招く。
            failed = ServerMessage(message_type="failed_join")
            await self.send(text_data=json.dumps(failed.model_dump(mode="json")))
            await self.close()
            return
        # このルームに猶予期間の削除予約があれば取り消す
        _cancel_pending_room_delete(str(self.anime_room.room_id))
        # ルームが存在しているのであればAnimeUserオブジェクトを作成
        self.anime_user = await self.database_create_user(
            user_name=user_name, room_id=self.anime_room, user_icon=user_icon
        )
        await self.channel_layer.group_add(
            str(self.anime_room.room_id), self.channel_name
        )
        user = User(**self.anime_user.__dict__)
        join = Join(room_id=self.anime_room.room_id, user=user)
        await self.send(text_data=json.dumps(join.model_dump(mode="json")))
        user_add = UserAdd(user=user)
        response_data = GroupSend(
            response=user_add,
            sender_channel_name=self.channel_name,
        )
        await self.database_increase_num_people()
        await self.channel_layer.group_send(
            str(self.anime_room.room_id),
            response_data.model_dump(mode="json"),
        )
        user_list = await self.database_user_list()
        user_list_data = UserList(user_list=user_list)
        response_data = RoomSend(
            response=user_list_data,
            sender_channel_name=self.channel_name,
        )
        await self.channel_layer.group_send(
            str(self.anime_room.room_id),
            response_data.model_dump(mode="json"),
        )
        # 参加者へ現在の詳細設定を通知する。非オーナーはこれを見て一方通行モード時の
        # 動画操作 UI を抑止できる（強制自体はサーバ側 video_operation で行う）。
        self.room_setting = await self.database_load_setting()
        await self.send(
            text_data=json.dumps(
                RoomSetting(**self.room_setting).model_dump(mode="json")
            )
        )

    @action()
    async def leave(self, **kwargs):
        """leaveを受け取った場合のアクション
        websocketを終了する
        """
        await self.database_renew_state()
        await self.close()

    # send method
    @action()
    async def video_operation(self, operation: str, option: dict, **kwargs):
        """video_operationを受け取った場合のアクション
        video_operationを送信元以外のクライアントに対して送信し、画面を同期する

        Args:
            operation (str): 操作名(seek,stop,,,etc)
            option (dict): 動画プレイヤー情報
        """
        if self.anime_room is None or self.anime_user is None:
            return
        await self.database_renew_state()
        # 一方通行(アクセラレーター)モードでは、オーナー以外の動画操作をブロックする。
        # is_host を先に見て短絡するのでホスト操作にはオーバーヘッドが無い。
        if not self.anime_user.is_host and self._one_way():
            return
        video_operation = VideoOperation(
            room_id=self.anime_room.room_id,
            operation=operation,
            user=User(**self.anime_user.__dict__).model_dump(),
            option=option,
        )
        response_data = GroupSend(
            response=video_operation,
            sender_channel_name=self.channel_name,
        )
        if (
            video_operation.option.part_id != self.anime_room.part_id
            and self.anime_user.is_host
        ):
            await self.database_update_room_part_id(video_operation.option.part_id)
        await self.channel_layer.group_send(
            str(self.anime_room.room_id),
            response_data.model_dump(mode="json"),
        )

    @action()
    async def sync_request(self, **kwargs):
        """sync_requestを受け取った場合のアクション
        sync_requestはホストの状態に動画プレイヤーを同期を要求するアクション
        """
        if self.anime_room is None or self.anime_user is None:
            return
        await self.database_renew_state()
        sync_request = SyncRequest(user=User(**self.anime_user.__dict__).model_dump())
        response_data = HostSend(
            response=sync_request,
            sender_channel_name=self.channel_name,
        )
        await self.channel_layer.group_send(
            str(self.anime_room.room_id),
            response_data.model_dump(mode="json"),
        )

    @action()
    async def sync_response(self, to_user: uuid, option: dict, **kwargs):
        """sync_responseを受け取った場合のアクション
        sync_responseはsync_requestを送信したユーザーに対する返信

        Args:
            to_user (uuid): 送信先のAnimeUserオブジェクトのID
            option (dict): 動画プレイヤー情報
        """
        if self.anime_room is None or self.anime_user is None:
            return
        await self.database_renew_state()
        sync_response = SyncResponse(option=option)
        response_data = UserSend(
            response=sync_response,
            to_user=to_user,
            sender_channel_name=self.channel_name,
        )
        await self.channel_layer.group_send(
            str(self.anime_room.room_id),
            response_data.model_dump(mode="json"),
        )

    @action()
    async def operation_notification(self, operation: str, **kwargs):
        """operation_notificationを受け取った場合のアクション

        Args:
            operation (str): 操作の種類
        """
        if self.anime_room is None or self.anime_user is None:
            return
        await self.database_renew_state()
        operation_notification = OperationNotification(
            room_id=self.anime_room.room_id,
            operation=operation,
            user=User(**self.anime_user.__dict__).model_dump(),
        )
        response_data = GroupSend(
            response=operation_notification, sender_channel_name=self.channel_name
        )
        await self.channel_layer.group_send(
            str(self.anime_room.room_id),
            response_data.model_dump(mode="json"),
        )

    @action()
    async def reaction(self, reaction_type: str, **kwargs):
        """reactionを受け取った場合のアクション

        Args:
            reaction_type (str): リアクションの種類

        デフォルトリアクション（``ReactionType`` のメンバ）はブロードキャストに加えて
        統計用に永続化する。拡張機能側のエクストラリアクション（Noto コードポイントの
        id）はブロードキャストのみ行い、**永続化しない**（統計対象外）。これにより
        未知の id でも ``ReactionType[...]`` の ``KeyError`` を起こさず安全に配信する。
        """
        if self.anime_room is None or self.anime_user is None:
            return
        # リアクション禁止設定では、ブロードキャストも永続化も行わない。送信者自身の画面
        # には拡張機能側がローカルに表示する（「自分にだけは表示される」）ため、サーバは
        # ここで黙って破棄するだけでよい。
        if self._disable_reaction():
            return
        reaction = Reaction(
            reaction_type=reaction_type,
            user=User(**self.anime_user.__dict__).model_dump(),
        )
        response_data = GroupSend(
            response=reaction, sender_channel_name=self.channel_name
        )
        await self.channel_layer.group_send(
            str(self.anime_room.room_id),
            response_data.model_dump(mode="json"),
        )
        if reaction_type in ReactionType.__members__:
            await self.database_create_reaction(reaction_type=reaction_type)

    @action()
    async def user_list(self, **kwargs):
        """user_listを受け取った場合のアクション"""
        if self.anime_room is None or self.anime_user is None:
            return
        user_list = await self.database_user_list()
        response_data = UserList(user_list=user_list)
        await self.send(text_data=json.dumps(response_data.model_dump(mode="json")))

    @action()
    async def delete_room(self, **kwargs):
        """ホスト（オーナー）がルームを削除するアクション。

        ルーム内の全員（送信者を含む）へ ``room_deleted`` を通知してから、
        ルームと参加者をまとめて論理削除する。ホスト以外からの要求は無視する。
        """
        if self.anime_room is None or self.anime_user is None:
            return
        await self.database_renew_state()
        if not self.anime_user.is_host:
            return
        room_id_str = str(self.anime_room.room_id)
        # 猶予期間の自動削除が予約されていれば取り消す（ここで明示的に削除するため）。
        _cancel_pending_room_delete(room_id_str)
        server_message = ServerMessage(message_type="room_deleted")
        response_data = RoomSend(
            response=server_message,
            sender_channel_name=self.channel_name,
        )
        await self.channel_layer.group_send(
            room_id_str,
            response_data.model_dump(mode="json"),
        )
        await self.database_delete_room_and_users()

    @action()
    async def update_setting(
        self,
        one_way: bool = False,
        owner_leave_delete: bool = False,
        disable_reaction: bool = False,
        **kwargs,
    ):
        """ルームの詳細設定を更新するアクション（オーナー限定）。

        入室時の初期設定・入室後の変更の両方でクライアントから送られる。ホスト（オーナー）
        以外からの要求は無視する。更新後はルーム全員へ ``room_setting`` を配信し、各接続の
        ローカルキャッシュ（一方通行判定等に使用）も同時に更新する。
        """
        if self.anime_room is None or self.anime_user is None:
            return
        await self.database_renew_state()
        if not self.anime_user.is_host:
            return
        self.room_setting = await self.database_update_setting(
            one_way=bool(one_way),
            owner_leave_delete=bool(owner_leave_delete),
            disable_reaction=bool(disable_reaction),
        )
        room_setting = RoomSetting(**self.room_setting)
        response_data = SettingSend(
            response=room_setting,
            sender_channel_name=self.channel_name,
        )
        await self.channel_layer.group_send(
            str(self.anime_room.room_id),
            response_data.model_dump(mode="json"),
        )

    async def room_send(self, data: dict):
        """自分を含むグループに所属するユーザーへの一斉送信

        Args:
            data (dict): group_send 経由で渡る dict。``response`` にクライアントへ
                送る本文を持つ。
        """
        await self.send(text_data=json.dumps(data["response"]))

    async def setting_send(self, data: dict):
        """詳細設定の変更を全員（送信者含む）へ配信し、各接続のローカルキャッシュも更新する。

        ``room_send`` と違い、クライアントへ転送するだけでなく、この接続が一方通行モード等の
        判定に使う ``self.room_setting`` を最新値へ更新する（都度 DB を引かないための同期）。
        """
        response = data["response"]
        self.room_setting = {
            "one_way": bool(response.get("one_way", False)),
            "owner_leave_delete": bool(response.get("owner_leave_delete", False)),
            "disable_reaction": bool(response.get("disable_reaction", False)),
        }
        await self.send(text_data=json.dumps(response))

    async def group_send(self, data: dict):
        """自分以外のグループに所属するユーザーへの一斉送信

        Args:
            data (dict): group_send 経由で渡る dict。``response`` の本文と、
                送信元を示す ``sender_channel_name`` を持つ。
        """
        if self.channel_name != data["sender_channel_name"]:
            await self.send(text_data=json.dumps(data["response"]))

    async def host_send(self, data: dict):
        """ルームのホストユーザーにのみ送信

        Args:
            data (dict): group_send 経由で渡る dict。``response`` の本文と
                ``sender_channel_name`` を持つ。
        """
        await self.database_renew_state()
        if self.channel_name != data["sender_channel_name"] and self.anime_user.is_host:
            await self.send(text_data=json.dumps(data["response"]))

    async def user_send(self, data: dict):
        """特定のユーザーにのみ送信

        Args:
            data (dict): to_userというカラムが存在している必要がある
        """
        if self.channel_name != data["sender_channel_name"] and str(
            self.anime_user.user_id
        ) == str(data["to_user"]["user_id"]):
            await self.send(text_data=json.dumps(data["response"]))

    async def leave_party(self):
        """サーバーから離脱する場合の共通処理
        データベースからの論理削除などを行い、ルーム内のユーザーに通知する
        """
        if self.anime_room is None or self.anime_user is None:
            return
        leave = Leave(user=User(**self.anime_user.__dict__).model_dump())
        response_data = GroupSend(
            response=leave,
            sender_channel_name=self.channel_name,
        )

        await self.database_delete_user()
        await self.database_decrease_num_people()
        user_count = await self.database_get_user_count()
        # オーナー退室時自動削除（一方通行モードはこれを含意）。オーナーが抜けたら残りの
        # 参加者ごとルームを即削除し、全員へ room_deleted を通知する。猶予削除やホスト委譲は
        # 行わない。
        if self.anime_user.is_host and self._effective_owner_leave_delete():
            room_id_str = str(self.anime_room.room_id)
            _cancel_pending_room_delete(room_id_str)
            server_message = ServerMessage(message_type="room_deleted")
            send_data = RoomSend(
                response=server_message,
                sender_channel_name=self.channel_name,
            )
            await self.channel_layer.group_send(
                room_id_str,
                send_data.model_dump(mode="json"),
            )
            await self.database_delete_room_and_users()
            await self.channel_layer.group_discard(room_id_str, self.channel_name)
            return
        if user_count < 1:
            # 即消しだとホストの一瞬切断・タブリロードでルームが消え、
            # ゲストが全員 failed_join になる。猶予期間中に誰かが再参加したら join 側で
            # cancel される。
            _schedule_room_delete(str(self.anime_room.room_id))
        if user_count >= 1 and self.anime_user.is_host:
            next_host = await self.database_promote_next_host()
            if next_host is not None:
                server_message = ServerMessage(message_type="host_change")
                send_data = HostSend(
                    response=server_message, sender_channel_name=self.channel_name
                )
                await self.channel_layer.group_send(
                    str(self.anime_room.room_id),
                    send_data.model_dump(mode="json"),
                )
        await self.channel_layer.group_send(
            str(self.anime_room.room_id),
            response_data.model_dump(mode="json"),
        )
        user_list = await self.database_user_list()
        user_list_data = UserList(user_list=user_list)
        response_data = RoomSend(
            response=user_list_data,
            sender_channel_name=self.channel_name,
        )
        await self.channel_layer.group_send(
            str(self.anime_room.room_id),
            response_data.model_dump(mode="json"),
        )
        await self.channel_layer.group_discard(
            str(self.anime_room.room_id), self.channel_name
        )

    # control database
    @database_sync_to_async
    def database_create_user(
        self,
        user_name: str,
        room_id,
        is_host: bool = False,
        user_icon: str = "FaRegUser",
    ):
        """データベース上にユーザーを作成する

        Args:
            user_name (str): ユーザーが任意に指定可能な名前
            room_id (AnimeRoom): 紐づく AnimeRoom オブジェクト
            is_host (bool, optional): ホストユーザーの場合はTrueにする
            user_icon (str, optional): react-icons (FA6) のキー。未指定なら既定アイコン。

        Returns:
            AnimeUser : 作成したユーザーのオブジェクト
        """
        return AnimeUser.objects.create(
            user_name=user_name, room_id=room_id, is_host=is_host, user_icon=user_icon
        )

    @database_sync_to_async
    def database_delete_user(self):
        """データベースからユーザーを削除する（論理削除）"""
        self.anime_user.delete()

    @database_sync_to_async
    def database_create_room(self, part_id: str, title: str = ""):
        """データベース上にルームを作成する
        クライアント側でルーム作成が押された場合に呼び出される

        Args:
            part_id (str): 現在視聴している動画のID(dアニメストアが発行)
            title (str): 視聴中アニメのタイトル(拡張機能がページ DOM から取得)

        Returns:
            AnimeRoom: 作成したルームのオブジェクト
        """
        return AnimeRoom.objects.create(part_id=part_id, title=title)

    @database_sync_to_async
    def database_update_room_part_id(self, part_id: str):
        """part_idの更新
        次の動画に進んだ場合など、ホストユーザーが見ている動画のIDを更新する場合に呼び出される
        新規に入ったユーザーはこの更新されたIDの動画にリダイレクトされる

        Args:
            part_id (str): 現在視聴している動画のID(dアニメストアが発行)
        """
        self.anime_room.part_id = part_id
        self.anime_room.save()

    @database_sync_to_async
    def database_delete_room_and_users(self):
        """ルームと、その中の生存ユーザーをまとめて論理削除する。

        ホストがルームを削除したときに呼ぶ。QuerySet の ``delete()`` は
        ``LogicalDeletionMixin`` により論理削除（``deleted_at`` 付与）。
        """
        room_id = self.anime_room.room_id
        # ルームが終了するので、リアクションを集計テーブルへ畳んで生データを削除する。
        fold_room_reactions(room_id)
        AnimeUser.objects.alive().filter(room_id=room_id).delete()
        AnimeRoom.objects.alive().filter(room_id=room_id).delete()

    @database_sync_to_async
    def database_increase_num_people(self):
        """人が増えた場合にデータベースのnum_peopleとsum_peopleを加算する"""
        self.anime_room.num_people = int(self.anime_room.num_people) + 1
        # TODO
        # sum_peopleがなぜか減ってしまう問題が発生している。特に減らすコードはどこにも書いていないのになぜ・・・
        # 最悪ユーザーをカウントすればいいだけなので問題ないけど
        self.anime_room.sum_people = int(self.anime_room.sum_people) + 1
        self.anime_room.save()

    @database_sync_to_async
    def database_decrease_num_people(self):
        """人が減った場合にnum_peopleを減らす"""
        self.anime_room.num_people = int(self.anime_room.num_people) - 1
        self.anime_room.save()

    @database_sync_to_async
    def database_promote_next_host(self):
        """残った生存ユーザーのうち最古の 1 人をホストへアトミックに昇格させる。

        次ホストの選定と昇格を 1 トランザクション（``select_for_update``）で行う。
        「選定 → 昇格」の await 境界で当人が離脱し、論理削除済みの行をホストに
        昇格させてしまう競合を防ぐ（旧実装は ``.earliest()`` で空のとき
        ``DoesNotExist`` を投げて 1011 close を招いていた）。ルームが空なら ``None``。
        """
        with transaction.atomic():
            next_user = (
                AnimeUser.objects.select_for_update()
                .alive()
                .filter(room_id=self.anime_room.room_id)
                .order_by("created_at")
                .first()
            )
            if next_user is None:
                return None
            next_user.is_host = True
            next_user.save(update_fields=["is_host"])
            return next_user

    @database_sync_to_async
    def database_get_user_count(self):
        """ルーム内の人数を取得する"""
        ar = AnimeRoom.objects.get(room_id=self.anime_room.room_id)
        return ar.inroom.alive().count()

    @database_sync_to_async
    def database_get_or_none_room(self, room_id):
        """ルームが存在していれば、ルームのオブジェクトを取得、そうでなければNoneを返す

        Args:
            room_id (uuid): 検索するAnimeRoomのID

        Returns:
            AnimeRoom | None: ルームのオブジェクト。見つからない場合はNone
        """
        if not is_valid_uuid(uuid_to_test=room_id):
            return None
        # 論理削除済みのルームには参加させない（旧実装は .filter() だけで deleted_at を
        # 無視していたため、削除直後のルームに join できてしまうバグがあった）。
        return AnimeRoom.objects.alive().filter(room_id=room_id).first()

    @database_sync_to_async
    def database_renew_state(self):
        """インスタンス化しているユーザー情報とルーム情報をデータベースに合わせる"""
        user_id = self.anime_user.user_id
        self.anime_user = AnimeUser.objects.get(user_id=user_id)
        room_id = self.anime_room.room_id
        self.anime_room = AnimeRoom.objects.get(room_id=room_id)

    @database_sync_to_async
    def database_user_list(self):
        """ルーム内のユーザーを取得する"""
        ar = AnimeRoom.objects.get(room_id=self.anime_room.room_id)
        user_list = ar.inroom.alive().values(
            "user_name", "user_id", "is_host", "user_icon"
        )
        return list(user_list)

    @database_sync_to_async
    def database_create_reaction(self, reaction_type):
        """リアクションを保存する"""
        return AnimeReaction.objects.create(
            room_id=self.anime_room, reaction_type=ReactionType[reaction_type].value
        )

    @staticmethod
    def _setting_to_dict(setting: Setting) -> dict:
        return {
            "one_way": setting.one_way,
            "owner_leave_delete": setting.owner_leave_delete,
            "disable_reaction": setting.disable_reaction,
        }

    @database_sync_to_async
    def database_get_or_create_setting(self):
        """ルームの詳細設定を既定値で取得/作成する（ルーム作成時に呼ぶ）。"""
        setting, _ = Setting.objects.get_or_create(room=self.anime_room)
        return self._setting_to_dict(setting)

    @database_sync_to_async
    def database_load_setting(self):
        """ルームの詳細設定を読み込む。無ければ既定値（すべて False）を返す。

        旧クライアントが作成した Setting 行の無いルームへ後方互換で参加する場合にも
        安全に既定値へフォールバックする。
        """
        setting = Setting.objects.filter(room=self.anime_room).first()
        if setting is None:
            return {
                "one_way": False,
                "owner_leave_delete": False,
                "disable_reaction": False,
            }
        return self._setting_to_dict(setting)

    @database_sync_to_async
    def database_update_setting(
        self, one_way: bool, owner_leave_delete: bool, disable_reaction: bool
    ):
        """ルームの詳細設定を更新する（オーナー限定の update_setting から呼ぶ）。"""
        setting, _ = Setting.objects.get_or_create(room=self.anime_room)
        setting.one_way = one_way
        setting.owner_leave_delete = owner_leave_delete
        setting.disable_reaction = disable_reaction
        setting.save(
            update_fields=[
                "one_way",
                "owner_leave_delete",
                "disable_reaction",
                "updated_at",
            ]
        )
        return self._setting_to_dict(setting)
