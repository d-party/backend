import uuid

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase

from .consumers import AnimePartyConsumer
from .factories import AnimeRoomFactory, AnimeUserFactory
from .models import AnimeReaction, AnimeRoom, AnimeUser, ReactionStat, Setting


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
        # create 由来の user_list(1名)/room_setting を挟んで user_add が届く。順序非依存に待つ。
        user_add = await self._recv_until(communicator1, "user_add")
        assert user_add["user"]["user_name"] == user_name2
        # 2 名になった user_list を待つ（1 名時点の user_list を読み飛ばす）。
        user_list = await self._recv_until(communicator1, "user_list")
        while len(user_list["user_list"]) < 2:
            user_list = await self._recv_until(communicator1, "user_list")
        # user_list はホスト（オーナー）判定のため is_host を含む。
        hosts = {u["user_name"]: u["is_host"] for u in user_list["user_list"]}
        assert hosts[user_name1] is True
        assert hosts[user_name2] is False
        # user_list は表示アイコンのため user_icon も含む（未指定なら既定キー）。
        icons = {u["user_name"]: u["user_icon"] for u in user_list["user_list"]}
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
        video = await self._recv_until(communicator1, "video_operation")
        assert video["user"]["user_name"] == user_name2
        assert video["room_id"] == join_room_id
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

        # create/join 由来の room_setting 等を挟みうるので room_deleted まで読み進める。
        host_msg = await self._recv_until(host, "server_message")
        assert host_msg["message_type"] == "room_deleted"

        guest_msg = await self._recv_until(guest, "server_message")
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

        # join 由来の room_setting/user_list を含め、溜まったメッセージを一旦捌く。
        await self._drain(guest)
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
        host_msg = await self._recv_until(host, "server_message")
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

    # ── 詳細設定（Setting）関連のテスト ─────────────────────────────────────────
    async def _recv_until(self, communicator, action):
        """指定 action のメッセージが来るまで読み進めて返す（順序に依存しない検証用）。

        create/join では ``room_setting``（直接 send）と ``user_list``（channel layer 経由）の
        到達順が前後しうるため、特定 action を待つ検証はこのヘルパで順序非依存にする。
        """
        msg = await communicator.receive_json_from()
        while msg["action"] != action:
            msg = await communicator.receive_json_from()
        return msg

    async def _drain(self, communicator):
        """キューに溜まったメッセージをすべて読み捨てる。"""
        while await communicator.receive_nothing() is False:
            await communicator.receive_json_from()

    async def _create_room(self, communicator, user_name="host_user"):
        await communicator.send_json_to(
            {
                "action": "create",
                "user_name": user_name,
                "part_id": "123456",
                "request_id": 100,
            }
        )
        create = await self._recv_until(communicator, "create")
        return create["room_id"]

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_create_auto_creates_and_pushes_default_setting(self):
        """create 時に Setting が既定値(すべて False)で自動生成され、作成者へ
        room_setting が push されるテスト（後方互換: 既定は現行挙動）。"""
        host = WebsocketCommunicator(
            AnimePartyConsumer.as_asgi(), "/anime-store/party/"
        )
        await host.connect()
        room_id = await self._create_room(host)
        setting_msg = await self._recv_until(host, "room_setting")
        assert setting_msg["one_way"] is False
        assert setting_msg["owner_leave_delete"] is False
        assert setting_msg["disable_reaction"] is False
        # Setting 行がルームと 1:1（PK=room）で作成されている。
        assert await self.setting_exists(room_id) is True
        await host.disconnect()

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_update_setting_owner_updates_and_broadcasts(self):
        """オーナーが update_setting を送ると DB が更新され、room_setting が配信される。"""
        host = WebsocketCommunicator(
            AnimePartyConsumer.as_asgi(), "/anime-store/party/"
        )
        await host.connect()
        room_id = await self._create_room(host)
        await self._recv_until(host, "room_setting")

        await host.send_json_to(
            {
                "action": "update_setting",
                "one_way": True,
                "owner_leave_delete": False,
                "disable_reaction": True,
                "request_id": 100,
            }
        )
        updated = await self._recv_until(host, "room_setting")
        assert updated["one_way"] is True
        assert updated["disable_reaction"] is True

        setting = await self.get_setting(room_id)
        assert setting.one_way is True
        assert setting.disable_reaction is True
        await host.disconnect()

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_update_setting_non_host_ignored(self):
        """ホスト以外の update_setting は無視され、DB は変わらないテスト。"""
        host = WebsocketCommunicator(
            AnimePartyConsumer.as_asgi(), "/anime-store/party/"
        )
        await host.connect()
        room_id = await self._create_room(host)
        await self._recv_until(host, "room_setting")

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
        await self._recv_until(guest, "room_setting")
        # join 由来の user_list 等の残りも読み捨ててから沈黙を検証する。
        await self._drain(guest)

        # 非ホストが一方通行を有効化しようとしても無視される。
        await guest.send_json_to(
            {"action": "update_setting", "one_way": True, "request_id": 100}
        )
        assert await guest.receive_nothing() is True
        setting = await self.get_setting(room_id)
        assert setting.one_way is False

        await host.disconnect()

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_one_way_blocks_non_host_video_operation(self):
        """一方通行モードで、非ホストの video_operation はブロックされ、ホストの
        操作は通常どおり配信されるテスト。"""
        host = WebsocketCommunicator(
            AnimePartyConsumer.as_asgi(), "/anime-store/party/"
        )
        await host.connect()
        room_id = await self._create_room(host)
        await self._recv_until(host, "room_setting")
        await host.send_json_to(
            {"action": "update_setting", "one_way": True, "request_id": 100}
        )
        await self._recv_until(host, "room_setting")

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
        await self._recv_until(guest, "room_setting")
        # ゲスト join に伴う host 側の通知（user_add / user_list）を捌く。
        while await host.receive_nothing() is False:
            await host.receive_json_from()

        # 非ホスト（ゲスト）の動画操作はブロックされ、ホストへ届かない。
        await guest.send_json_to(
            {
                "action": "video_operation",
                "operation": "playing",
                "option": {
                    "time": "1",
                    "src": "blob:x",
                    "paused": "False",
                    "rate": "1",
                    "part_id": "00000000",
                },
                "request_id": 100,
            }
        )
        assert await host.receive_nothing() is True

        # ホストの動画操作は通常どおりゲストへ配信される。
        await host.send_json_to(
            {
                "action": "video_operation",
                "operation": "playing",
                "option": {
                    "time": "2",
                    "src": "blob:y",
                    "paused": "False",
                    "rate": "1",
                    "part_id": "123456",
                },
                "request_id": 100,
            }
        )
        vop = await self._recv_until(guest, "video_operation")
        assert vop["operation"] == "playing"

        await host.disconnect()

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_disable_reaction_not_broadcast_or_persisted(self):
        """リアクション禁止設定では、他参加者へ配信されず統計にも記録されないテスト。"""
        host = WebsocketCommunicator(
            AnimePartyConsumer.as_asgi(), "/anime-store/party/"
        )
        await host.connect()
        room_id = await self._create_room(host)
        await self._recv_until(host, "room_setting")
        await host.send_json_to(
            {"action": "update_setting", "disable_reaction": True, "request_id": 100}
        )
        await self._recv_until(host, "room_setting")

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
        await self._recv_until(guest, "room_setting")
        while await host.receive_nothing() is False:
            await host.receive_json_from()

        # ゲストがリアクションを送っても、ホストには届かない。
        await guest.send_json_to(
            {"action": "reaction", "reaction_type": "smile", "request_id": 100}
        )
        assert await host.receive_nothing() is True
        # 永続化もされない。
        assert await self.reaction_rows(room_id) == 0

        await host.disconnect()

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_owner_leave_delete_deletes_room_on_host_leave(self):
        """オーナー退室時自動削除が有効なら、ホスト退室でルームが論理削除され、
        残った参加者へ room_deleted が届くテスト。"""
        host = WebsocketCommunicator(
            AnimePartyConsumer.as_asgi(), "/anime-store/party/"
        )
        await host.connect()
        room_id = await self._create_room(host)
        await self._recv_until(host, "room_setting")
        await host.send_json_to(
            {
                "action": "update_setting",
                "owner_leave_delete": True,
                "request_id": 100,
            }
        )
        await self._recv_until(host, "room_setting")

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
        await self._recv_until(guest, "room_setting")

        # ホストが退室するとルームが自動削除される。
        await host.disconnect()

        deleted = await self._recv_until(guest, "server_message")
        assert deleted["message_type"] == "room_deleted"
        assert await self.room_alive(room_id) is False
        assert await self.alive_user_count(room_id) == 0

        await guest.disconnect()

    @database_sync_to_async
    def setting_exists(self, room_id):
        return Setting.objects.filter(room_id=room_id).exists()

    @database_sync_to_async
    def get_setting(self, room_id):
        return Setting.objects.get(room_id=room_id)

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
