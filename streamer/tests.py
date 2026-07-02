import uuid

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase

from .consumers import AnimePartyConsumer
from .factories import AnimeRoomFactory, AnimeUserFactory
from .models import AnimeReaction, AnimeRoom, AnimeUser, ReactionStat


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestAnimePartyConsumer(TransactionTestCase):
    def setUp(self):
        self.anime_room1 = AnimeRoomFactory()
        self.anime_room2 = AnimeRoomFactory()
        self.anime_user1 = AnimeUserFactory(room_id=self.anime_room1, is_host=True)
        self.anime_user2 = AnimeUserFactory(room_id=self.anime_room1, is_host=False)

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_anime_party_consumer_create_ok(self):
        """AnimeConsumerのcreate actionが正しく動作することを確認するテスト"""
        communicator = WebsocketCommunicator(
            AnimePartyConsumer.as_asgi(), "/anime-store/party/"
        )
        connected, subprotocol = await communicator.connect()
        assert connected
        user_name1 = "user_name1"
        user_icon1 = "FaCat"
        title1 = "鬼滅の刃 - 第1話 - 残酷"
        await communicator.send_json_to(
            {
                "action": "create",
                "user_name": user_name1,
                "user_icon": user_icon1,
                "part_id": "123456",
                "title": title1,
                "request_id": 100,
            }
        )
        response = await communicator.receive_json_from()
        assert response["action"] == "create"
        assert response["user"]["user_name"] == user_name1
        # 送信した user_icon が往復することを確認
        assert response["user"]["user_icon"] == user_icon1
        # userがデータベースに作られていることを確認
        assert await self.anime_user_exist(response["user"]["user_id"])
        # roomがデータベースに作られていることを確認
        assert await self.anime_room_exist(response["room_id"])
        # ルーム作成時に送られたタイトルが保存されていることを確認
        room = await self.get_anime_room(response["room_id"])
        assert room.title == title1
        await communicator.disconnect()

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_anime_party_consumer_join_ok(self):
        """AnimeConsumerのjoin actionが正しく動作することを確認するテスト"""
        communicator = WebsocketCommunicator(
            AnimePartyConsumer.as_asgi(), "/anime-store/party/"
        )
        connected, subprotocol = await communicator.connect()
        assert connected
        room_id = str(self.anime_room1.room_id)
        user_name = "user_name"
        await communicator.send_json_to(
            {
                "action": "join",
                "user_name": user_name,
                "room_id": room_id,
                "part_id": "123456",
                "request_id": 100,
            }
        )
        response = await communicator.receive_json_from()
        assert response["action"] == "join"
        # userがデータベースに作られていることを確認
        assert await self.anime_user_exist(response["user"]["user_id"])
        # user_icon を送らない旧拡張は既定アイコンにフォールバックする（後方互換）
        assert response["user"]["user_icon"] == "FaRegUser"
        await communicator.disconnect()

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_anime_party_consumer_join_ng(self):
        """AnimeConsumerのjoin actionが正しく動作することを確認するテスト"""
        communicator = WebsocketCommunicator(
            AnimePartyConsumer.as_asgi(), "/anime-store/party/"
        )
        connected, subprotocol = await communicator.connect()
        assert connected
        user_name = "user_name"
        await communicator.send_json_to(
            {
                "action": "join",
                "user_name": user_name,
                "room_id": str(uuid.uuid4()),
                "part_id": "123456",
                "request_id": 100,
            }
        )
        response = await communicator.receive_json_from()
        assert response["action"] == "server_message"
        assert response["message_type"] == "failed_join"
        await communicator.disconnect()

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_anime_party_consumer_video_action(self):
        """AnimeConsumerのcreate actionが正しく動作することを確認するテスト"""
        communicator1 = WebsocketCommunicator(
            AnimePartyConsumer.as_asgi(), "/anime-store/party/"
        )
        await communicator1.connect()
        user_name1 = "user_name1"
        await communicator1.send_json_to(
            {
                "action": "create",
                "user_name": user_name1,
                "part_id": "123456",
                "request_id": 100,
            }
        )
        response = await communicator1.receive_json_from()
        join_room_id = response["room_id"]
        create_user = response["user"]
        """AnimeConsumerのcreate actionが正しく動作することを確認するテスト"""
        communicator2 = WebsocketCommunicator(
            AnimePartyConsumer.as_asgi(), "/anime-store/party/"
        )
        await communicator2.connect()
        user_name2 = "user_name2"
        await communicator2.send_json_to(
            {
                "action": "join",
                "user_name": user_name2,
                "room_id": join_room_id,
                "part_id": "123456",
                "request_id": 100,
            }
        )
        response = await communicator1.receive_json_from()
        response = await communicator1.receive_json_from()
        assert response["action"] == "user_add"
        assert response["user"]["user_name"] == user_name2
        response = await communicator1.receive_json_from()
        assert response["action"] == "user_list"
        assert len(response["user_list"]) == 2
        # user_list はホスト（オーナー）判定のため is_host を含む。
        hosts = {u["user_name"]: u["is_host"] for u in response["user_list"]}
        assert hosts[user_name1] is True
        assert hosts[user_name2] is False
        # user_list は表示アイコンのため user_icon も含む（未指定なら既定キー）。
        icons = {u["user_name"]: u["user_icon"] for u in response["user_list"]}
        assert icons[user_name1] == "FaRegUser"
        assert icons[user_name2] == "FaRegUser"
        await communicator2.send_json_to(
            {
                "action": "video_operation",
                "operation": "playing",
                "option": {
                    "time": "1",
                    "src": "blob:https://anime.dmkt-sp.jp/xxxxxxxxxxxxxxxxxxx",
                    "paused": "False",
                    "rate": "1",
                    "part_id": "00000000",
                },
                "request_id": 100,
            }
        )
        response = await communicator1.receive_json_from()
        assert response["action"] == "video_operation"
        assert response["user"]["user_name"] == user_name2
        assert response["room_id"] == join_room_id
        await communicator1.disconnect()

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_anime_party_consumer_delete_room_ok(self):
        """ホストが delete_room を送ると、ルームが論理削除され、ルーム内の
        全員（ホスト自身を含む）へ room_deleted が通知されるテスト"""
        host = WebsocketCommunicator(
            AnimePartyConsumer.as_asgi(), "/anime-store/party/"
        )
        await host.connect()
        await host.send_json_to(
            {
                "action": "create",
                "user_name": "host_user",
                "part_id": "123456",
                "request_id": 100,
            }
        )
        create_response = await host.receive_json_from()
        room_id = create_response["room_id"]
        # create 直後の user_list を読み飛ばす。
        await host.receive_json_from()

        guest = WebsocketCommunicator(
            AnimePartyConsumer.as_asgi(), "/anime-store/party/"
        )
        await guest.connect()
        await guest.send_json_to(
            {
                "action": "join",
                "user_name": "guest_user",
                "room_id": room_id,
                "request_id": 100,
            }
        )
        # guest: join 応答 + user_list、host: user_add + user_list を読み飛ばす。
        await guest.receive_json_from()
        await guest.receive_json_from()
        await host.receive_json_from()
        await host.receive_json_from()

        # ホストがルーム削除を要求する。
        await host.send_json_to({"action": "delete_room", "request_id": 100})

        host_msg = await host.receive_json_from()
        assert host_msg["action"] == "server_message"
        assert host_msg["message_type"] == "room_deleted"

        guest_msg = await guest.receive_json_from()
        assert guest_msg["action"] == "server_message"
        assert guest_msg["message_type"] == "room_deleted"

        assert await self.room_alive(room_id) is False
        assert await self.alive_user_count(room_id) == 0

        # 既存テストにならい片方のみ切断する（num_people は作成者を数えないため、
        # 2 回 decrement すると CHECK 制約 >= 0 を割る既知の会計上の癖を避ける）。
        await host.disconnect()

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_anime_party_consumer_delete_room_non_host_ignored(self):
        """ホスト以外が delete_room を送っても無視され、ルームは残るテスト"""
        host = WebsocketCommunicator(
            AnimePartyConsumer.as_asgi(), "/anime-store/party/"
        )
        await host.connect()
        await host.send_json_to(
            {
                "action": "create",
                "user_name": "host_user",
                "part_id": "123456",
                "request_id": 100,
            }
        )
        create_response = await host.receive_json_from()
        room_id = create_response["room_id"]
        await host.receive_json_from()

        guest = WebsocketCommunicator(
            AnimePartyConsumer.as_asgi(), "/anime-store/party/"
        )
        await guest.connect()
        await guest.send_json_to(
            {
                "action": "join",
                "user_name": "guest_user",
                "room_id": room_id,
                "request_id": 100,
            }
        )
        await guest.receive_json_from()
        await guest.receive_json_from()
        await host.receive_json_from()
        await host.receive_json_from()

        # 非ホスト（ゲスト）が削除を要求しても無視される。
        await guest.send_json_to({"action": "delete_room", "request_id": 100})

        assert await guest.receive_nothing() is True
        assert await self.room_alive(room_id) is True
        assert await self.alive_user_count(room_id) == 2

        # 片方のみ切断する（num_people の二重 decrement による CHECK 制約違反を避ける）。
        await host.disconnect()

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_delete_room_folds_reactions_into_stats(self):
        """ホストの delete_room 時に、ルームのリアクションが ReactionStat へ
        畳み込まれ、生の AnimeReaction が物理削除されるテスト。"""
        host = WebsocketCommunicator(
            AnimePartyConsumer.as_asgi(), "/anime-store/party/"
        )
        await host.connect()
        await host.send_json_to(
            {
                "action": "create",
                "user_name": "host_user",
                "part_id": "123456",
                "request_id": 100,
            }
        )
        create_response = await host.receive_json_from()
        room_id = create_response["room_id"]
        await host.receive_json_from()  # create 直後の user_list を読み飛ばす。

        # MIRROR な test DB は他テストの ReactionStat 行が残りうるため差分で検証する。
        baseline = await self.smile_stat_total()

        # ホストがリアクションを送る（自分の group_send は届かないため受信しない）。
        await host.send_json_to(
            {"action": "reaction", "reaction_type": "smile", "request_id": 100}
        )
        await host.send_json_to(
            {"action": "reaction", "reaction_type": "smile", "request_id": 100}
        )

        # ルーム削除を要求し、room_deleted を待って畳み込み完了を保証する。
        await host.send_json_to({"action": "delete_room", "request_id": 100})
        host_msg = await host.receive_json_from()
        assert host_msg["message_type"] == "room_deleted"

        assert await self.reaction_rows(room_id) == 0
        assert await self.smile_stat_total() - baseline == 2

        await host.disconnect()

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_extra_reaction_broadcasts_but_is_not_persisted(self):
        """エクストラリアクション（Noto コードポイント id）は他参加者へブロード
        キャストされるが、統計用に永続化はされない（AnimeReaction を作らない）。"""
        host = WebsocketCommunicator(
            AnimePartyConsumer.as_asgi(), "/anime-store/party/"
        )
        await host.connect()
        await host.send_json_to(
            {
                "action": "create",
                "user_name": "host_user",
                "part_id": "123456",
                "request_id": 100,
            }
        )
        create_response = await host.receive_json_from()
        room_id = create_response["room_id"]
        await host.receive_json_from()  # create 直後の user_list を読み飛ばす。

        guest = WebsocketCommunicator(
            AnimePartyConsumer.as_asgi(), "/anime-store/party/"
        )
        await guest.connect()
        await guest.send_json_to(
            {
                "action": "join",
                "user_name": "guest_user",
                "room_id": room_id,
                "part_id": "123456",
                "request_id": 100,
            }
        )
        # ゲストがエクストラリアクション（カタログ id = 絵文字コードポイント）を送る。
        extra_id = "1f600"
        await guest.send_json_to(
            {"action": "reaction", "reaction_type": extra_id, "request_id": 100}
        )

        # ホストはブロードキャストを受信する（配信は従来どおり行われる）。参加に伴う
        # user_add / user_list 等が先に届きうるので reaction が来るまで読み進める。
        msg = await host.receive_json_from()
        while msg["action"] != "reaction":
            msg = await host.receive_json_from()
        assert msg["reaction_type"] == extra_id
        # 送信者を同梱する（バッジ表示の「ユーザー名 : リアクション」用）。
        assert msg["user"]["user_name"] == "guest_user"

        # ただし統計用の永続化はされない。
        assert await self.reaction_rows(room_id) == 0

        await guest.disconnect()
        await host.disconnect()

    # ── 観覧専用（spectator / タイマー）関連のテスト ─────────────────────────────
    async def _recv_until(self, communicator, action):
        """指定 action のメッセージが来るまで読み進めて返す（順序非依存）。"""
        msg = await communicator.receive_json_from()
        while msg["action"] != action:
            msg = await communicator.receive_json_from()
        return msg

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_spectate_receives_video_operation_with_title(self):
        """spectate で観覧参加すると video_operation を受信でき、title が追従する。
        観覧者は AnimeUser を作らないため人数・参加者一覧に出ない。"""
        host = WebsocketCommunicator(
            AnimePartyConsumer.as_asgi(), "/anime-store/party/"
        )
        await host.connect()
        await host.send_json_to(
            {
                "action": "create",
                "user_name": "host_user",
                "part_id": "123456",
                "title": "第1話",
                "request_id": 100,
            }
        )
        create = await self._recv_until(host, "create")
        room_id = create["room_id"]

        spectator = WebsocketCommunicator(
            AnimePartyConsumer.as_asgi(), "/anime-store/party/"
        )
        await spectator.connect()
        await spectator.send_json_to(
            {"action": "spectate", "room_id": room_id, "request_id": 100}
        )
        ack = await self._recv_until(spectator, "spectate")
        assert ack["room_id"] == room_id
        assert ack["part_id"] == "123456"
        assert ack["title"] == "第1話"

        # ホストがエピソードを進めながら再生状態を配信する。
        await host.send_json_to(
            {
                "action": "video_operation",
                "operation": "playing",
                "title": "第2話",
                "option": {
                    "time": "12",
                    "src": "blob:x",
                    "paused": "False",
                    "rate": "1",
                    "part_id": "222222",
                },
                "request_id": 100,
            }
        )
        vop = await self._recv_until(spectator, "video_operation")
        assert vop["operation"] == "playing"
        # タイマーがエピソード切替に追従できるよう title が載る。
        assert vop["title"] == "第2話"
        assert vop["option"]["time"] == 12

        # 観覧者は参加者としてカウントされない（host のみ）。
        assert await self.alive_user_count(room_id) == 1

        await spectator.disconnect()
        await host.disconnect()

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_spectate_failed_for_missing_room(self):
        """存在しないルームを観覧しようとすると failed_spectate が返る。"""
        spectator = WebsocketCommunicator(
            AnimePartyConsumer.as_asgi(), "/anime-store/party/"
        )
        await spectator.connect()
        await spectator.send_json_to(
            {"action": "spectate", "room_id": str(uuid.uuid4()), "request_id": 100}
        )
        msg = await self._recv_until(spectator, "server_message")
        assert msg["message_type"] == "failed_spectate"
        await spectator.disconnect()

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_spectate_survives_host_targeted_messages(self):
        """sync_request（HostSend）等が飛んでも観覧者はクラッシュしないテスト。

        観覧者は AnimeUser を持たないため、host_send ハンドラがガードされていないと
        renew_state で AttributeError → 1011 close となる。後続の video_operation を
        受信できることで接続の生存（＝クラッシュしていないこと）を確認する。"""
        host = WebsocketCommunicator(
            AnimePartyConsumer.as_asgi(), "/anime-store/party/"
        )
        await host.connect()
        await host.send_json_to(
            {
                "action": "create",
                "user_name": "host_user",
                "part_id": "123456",
                "request_id": 100,
            }
        )
        create = await self._recv_until(host, "create")
        room_id = create["room_id"]

        spectator = WebsocketCommunicator(
            AnimePartyConsumer.as_asgi(), "/anime-store/party/"
        )
        await spectator.connect()
        await spectator.send_json_to(
            {"action": "spectate", "room_id": room_id, "request_id": 100}
        )
        await self._recv_until(spectator, "spectate")

        # ホストが sync_request を投げる（HostSend が観覧者にも配送される）。
        await host.send_json_to({"action": "sync_request", "request_id": 100})
        # 直後に video_operation を送り、観覧者がまだ受信できる＝クラッシュしていない。
        await host.send_json_to(
            {
                "action": "video_operation",
                "operation": "playing",
                "option": {
                    "time": "1",
                    "src": "blob:x",
                    "paused": "False",
                    "rate": "1",
                    "part_id": "123456",
                },
                "request_id": 100,
            }
        )
        vop = await self._recv_until(spectator, "video_operation")
        assert vop["operation"] == "playing"

        await spectator.disconnect()
        await host.disconnect()

    @database_sync_to_async
    def reaction_rows(self, room_id):
        return AnimeReaction.objects.filter(room_id=room_id).count()

    @database_sync_to_async
    def smile_stat_total(self):
        from django.db.models import Sum

        return (
            ReactionStat.objects.filter(reaction_type="S").aggregate(t=Sum("count"))[
                "t"
            ]
            or 0
        )

    @database_sync_to_async
    def room_alive(self, room_id):
        return AnimeRoom.objects.alive().filter(room_id=room_id).exists()

    @database_sync_to_async
    def alive_user_count(self, room_id):
        return AnimeUser.objects.alive().filter(room_id=room_id).count()

    @database_sync_to_async
    def anime_user_exist(self, user_id):
        return AnimeUser.objects.filter(user_id=user_id).exists()

    @database_sync_to_async
    def get_anime_user(self, user_id):
        return AnimeUser.objects.get(user_id=user_id)

    @database_sync_to_async
    def anime_room_exist(self, room_id):
        return AnimeRoom.objects.filter(room_id=room_id).exists()

    @database_sync_to_async
    def get_anime_room(self, room_id):
        return AnimeRoom.objects.get(room_id=room_id)
