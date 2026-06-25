import asyncio
import json
import uuid

from channels.db import database_sync_to_async
from djangochannelsrestframework.decorators import action
from djangochannelsrestframework.generics import GenericAsyncAPIConsumer

from .format import (
    Create,
    GroupSend,
    HostSend,
    Join,
    Leave,
    OperationNotification,
    Reaction,
    RoomSend,
    ServerMessage,
    SyncRequest,
    SyncResponse,
    User,
    UserAdd,
    UserList,
    UserSend,
    VideoOperation,
)
from .models import AnimeReaction, AnimeRoom, AnimeUser, ReactionType
from .util import is_valid_uuid, uuid_json_encoder

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
        json.JSONEncoder.default = uuid_json_encoder
        # 入室したAnimeRoomのオブジェクト
        self.anime_room = None
        # ユーザー情報
        self.anime_user = None

    async def connect(self):
        await self.accept()

    async def disconnect(self, close_code):
        """websocketを閉じた場合の処理
        self.close()でも呼び出される

        Args:
            close_code ([type]): [description]
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
        await self.send(text_data=json.dumps(create.model_dump()))
        user_list = await self.database_user_list()
        user_list_data = UserList(user_list=user_list)
        response_data = RoomSend(
            response=user_list_data,
            sender_channel_name=self.channel_name,
        )
        await self.channel_layer.group_send(
            str(self.anime_room.room_id),
            json.loads(json.dumps(response_data.model_dump())),
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
            await self.send(text_data=json.dumps(failed.model_dump()))
            await self.close()
            return
        # このルームに猟予期間の削除予約があれば取り消す
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
        await self.send(text_data=json.dumps(join.model_dump()))
        user_add = UserAdd(user=user)
        response_data = GroupSend(
            response=user_add,
            sender_channel_name=self.channel_name,
        )
        await self.database_increase_num_people()
        await self.channel_layer.group_send(
            str(self.anime_room.room_id),
            json.loads(json.dumps(response_data.model_dump())),
        )
        user_list = await self.database_user_list()
        user_list_data = UserList(user_list=user_list)
        response_data = RoomSend(
            response=user_list_data,
            sender_channel_name=self.channel_name,
        )
        await self.channel_layer.group_send(
            str(self.anime_room.room_id),
            json.loads(json.dumps(response_data.model_dump())),
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
            json.loads(json.dumps(response_data.model_dump())),
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
            json.loads(json.dumps(response_data.model_dump())),
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
            json.loads(json.dumps(response_data.model_dump())),
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
            json.loads(json.dumps(response_data.model_dump())),
        )

    @action()
    async def reaction(self, reaction_type: str, **kwargs):
        """reactionを受け取った場合のアクション

        Args:
            reaction_type (str): リアクションの種類
        """
        if self.anime_room is None or self.anime_user is None:
            return
        reaction = Reaction(reaction_type=reaction_type)
        response_data = GroupSend(
            response=reaction, sender_channel_name=self.channel_name
        )
        await self.channel_layer.group_send(
            str(self.anime_room.room_id),
            json.loads(json.dumps(response_data.model_dump())),
        )
        await self.database_create_reaction(reaction_type=reaction_type)

    @action()
    async def user_list(self, **kwargs):
        """user_listを受け取った場合のアクション"""
        if self.anime_room is None or self.anime_user is None:
            return
        user_list = await self.database_user_list()
        response_data = UserList(user_list=user_list)
        await self.send(text_data=json.dumps(response_data.model_dump()))

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
        # 猟予期間の自動削除が予約されていれば取り消す（ここで明示的に削除するため）。
        _cancel_pending_room_delete(room_id_str)
        server_message = ServerMessage(message_type="room_deleted")
        response_data = RoomSend(
            response=server_message,
            sender_channel_name=self.channel_name,
        )
        await self.channel_layer.group_send(
            room_id_str,
            json.loads(json.dumps(response_data.model_dump())),
        )
        await self.database_delete_room_and_users()

    async def room_send(self, data: dict):
        """自分を含むのグループに所属するユーザーへの一斉送信

        Args:
            data (dict): [description]
        """
        await self.send(text_data=json.dumps(data["response"]))

    async def group_send(self, data: dict):
        """自分以外のグループに所属するユーザーへの一斉送信

        Args:
            data (dict): [description]
        """
        if self.channel_name != data["sender_channel_name"]:
            await self.send(text_data=json.dumps(data["response"]))

    async def host_send(self, data: dict):
        """ルームのホストユーザーにのみ送信

        Args:
            data (dict): [description]
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
        if user_count < 1:
            # 即消しだるとホストの一瞬切断・タブリロードでルームが消え、
            # ゲストが全員 failed_join になる。猟予期間中に誰かが再参加したら join 側で
            # cancel される。
            _schedule_room_delete(str(self.anime_room.room_id))
        if user_count >= 1 and self.anime_user.is_host:
            next_host = await self.database_get_next_host_or_none()
            await self.database_host_change_user(next_host.user_id)
            server_message = ServerMessage(message_type="host_change")
            send_data = HostSend(
                response=server_message, sender_channel_name=self.channel_name
            )
            await self.channel_layer.group_send(
                str(self.anime_room.room_id),
                json.loads(json.dumps(send_data.model_dump())),
            )
        await self.channel_layer.group_send(
            str(self.anime_room.room_id),
            json.loads(json.dumps(response_data.model_dump())),
        )
        user_list = await self.database_user_list()
        user_list_data = UserList(user_list=user_list)
        response_data = RoomSend(
            response=user_list_data,
            sender_channel_name=self.channel_name,
        )
        await self.channel_layer.group_send(
            str(self.anime_room.room_id),
            json.loads(json.dumps(response_data.model_dump())),
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
            user_name ([type]): ユーザーが任意に指定可能な名前
            room_id ([type]): AnimeRoomに存在するID
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
        """データベースからユーザーを削除する"""
        self.anime_user.delete()
        self.anime_user.save()

    @database_sync_to_async
    def database_create_room(self, part_id: str, title: str = ""):
        """データベース上にルームを作成する
        クライアント側でルーム作成が押された場合に呼び出される

        Args:
            part_id ([str]): 現在視聴している動画のID(dアニメストアが発行)
            title ([str]): 視聴中アニメのタイトル(拡張機能がページ DOM から取得)

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
            part_id ([type]):現在視聴している動画のID(dアニメストアが発行)
        """
        self.anime_room.part_id = part_id
        self.anime_room.save()

    @database_sync_to_async
    def database_delete_room(self):
        """ルームの論理削除を行う"""
        self.anime_room.delete()
        self.anime_room.save()

    @database_sync_to_async
    def database_delete_room_and_users(self):
        """ルームと、その中の生存ユーザーをまとめて論理削除する。

        ホストがルームを削除したときに呼ぶ。QuerySet の ``delete()`` は
        ``LogicalDeletionMixin`` により論理削除（``deleted_at`` 付与）。
        """
        room_id = self.anime_room.room_id
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
    def database_get_next_host_or_none(self):
        ar = AnimeRoom.objects.get(room_id=self.anime_room.room_id)
        return ar.inroom.alive().earliest("created_at")

    @database_sync_to_async
    def database_get_user_count(self):
        """ルーム内の人数を取得する"""
        ar = AnimeRoom.objects.get(room_id=self.anime_room.room_id)
        return ar.inroom.alive().count()

    @database_sync_to_async
    def database_get_or_none_room(self, room_id):
        """ルームが存在していれば、ルームのオブジェクトを取得、そうでなければNoneを返す

        Args:
            room_id ([type]): 検索するAnimeRoomのID

        Returns:
            [AnimeRoom.objects,None]: ルームのオブジェクトか見つからない場合はNone
        """
        if not is_valid_uuid(uuid_to_test=room_id):
            return None
        # 論理削除済みのルームには参加させない（旧実装は .filter() だけで deleted_at を
        # 無視していたため、削除直後のルームに join できてしまうバグがあった）。
        return AnimeRoom.objects.alive().filter(room_id=room_id).first()

    @database_sync_to_async
    def database_host_change_user(self, user_id):
        au = AnimeUser.objects.get(user_id=user_id)
        au.is_host = True
        au.save()
        return au

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
