"""DMM TV consumer の最小スモークテスト。

同時視聴の同期本体は ``BasePartyConsumer`` で dアニメと共有しており、その網羅的な
テストは ``tests.py``（``AnimePartyConsumer``）にある。ここでは DMM 用のサブクラスが
**正しく DMM 専用モデル（``DmmRoom`` / ``DmmUser`` / ``DmmReaction`` /
``DmmReactionStat``）を対象に動く**ことだけを確認する（サービス分離の回帰防止）。
"""

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.db.models import Sum
from django.test import TransactionTestCase

from .consumers import DmmPartyConsumer
from .models import DmmReaction, DmmReactionStat, DmmRoom, DmmUser


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestDmmPartyConsumer(TransactionTestCase):
    async def _recv_until(self, communicator, action):
        msg = await communicator.receive_json_from()
        while msg["action"] != action:
            msg = await communicator.receive_json_from()
        return msg

    async def _drain(self, communicator):
        while await communicator.receive_nothing() is False:
            await communicator.receive_json_from()

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_dmm_create_persists_dmm_models(self):
        """create が DmmRoom/DmmUser を生成し、長い DMM content id が切り詰められないこと。"""
        communicator = WebsocketCommunicator(
            DmmPartyConsumer.as_asgi(), "/dmm-tv/party/"
        )
        connected, _ = await communicator.connect()
        assert connected
        # DMM の content id は 25 文字前後（dアニメの数値 partId より長い）。
        content_id = "c7tzzizzvhuj53zhmpf9aa2c0"
        await communicator.send_json_to(
            {
                "action": "create",
                "user_name": "host",
                "user_icon": "FaCat",
                "part_id": content_id,
                "title": "大賢者リドルの時間逆行 - 第1話",
                "request_id": 1,
            }
        )
        create = await self._recv_until(communicator, "create")
        assert create["user"]["user_name"] == "host"
        assert await self.dmm_user_exist(create["user"]["user_id"])
        assert await self.dmm_room_exist(create["room_id"])
        room = await self.get_dmm_room(create["room_id"])
        # part_id(max_length=128) なので長い content id がそのまま保存される。
        assert room.part_id == content_id
        await communicator.disconnect()

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_dmm_reaction_persisted_and_folded_on_delete(self):
        """既定リアクションが DmmReaction に保存され、ルーム削除時に DmmReactionStat へ
        畳み込まれて生データが消えること（fold のサービス別モデル差し替えの確認）。"""
        communicator = WebsocketCommunicator(
            DmmPartyConsumer.as_asgi(), "/dmm-tv/party/"
        )
        await communicator.connect()
        await communicator.send_json_to(
            {
                "action": "create",
                "user_name": "host",
                "part_id": "c7tzzizzvhuj53zhmpf9aa2c0",
                "request_id": 1,
            }
        )
        create = await self._recv_until(communicator, "create")
        room_id = create["room_id"]
        # create が push する user_list / room_setting を読み捨て、以降の順序を確定させる。
        await self._drain(communicator)

        # MIRROR な test DB は他テスト/前回実行の DmmReactionStat 行が残りうる
        # （transaction=True はコミットしロールバックされない）ため差分で検証する。
        baseline = await self.dmm_stat_total()

        # 既定リアクション（ReactionType のメンバ）は永続化される。
        await communicator.send_json_to(
            {"action": "reaction", "reaction_type": "fav", "request_id": 2}
        )
        # user_list を要求し、その応答を待つことで先行の reaction 処理完了を保証する
        # （consumer はアクションを受信順に逐次処理する）。
        await communicator.send_json_to({"action": "user_list", "request_id": 3})
        await self._recv_until(communicator, "user_list")
        assert await self.dmm_reaction_count(room_id) == 1

        # ホストによる削除でリアクションが集計へ畳まれ、生データはハードデリートされる。
        await communicator.send_json_to({"action": "delete_room", "request_id": 4})
        await self._recv_until(communicator, "server_message")
        assert await self.dmm_reaction_count(room_id) == 0
        assert await self.dmm_stat_total() - baseline == 1
        await communicator.disconnect()

    # ── DB ヘルパ ─────────────────────────────────────────────────────────
    @database_sync_to_async
    def dmm_user_exist(self, user_id):
        return DmmUser.objects.filter(user_id=user_id).exists()

    @database_sync_to_async
    def dmm_room_exist(self, room_id):
        return DmmRoom.objects.filter(room_id=room_id).exists()

    @database_sync_to_async
    def get_dmm_room(self, room_id):
        return DmmRoom.objects.get(room_id=room_id)

    @database_sync_to_async
    def dmm_reaction_count(self, room_id):
        return DmmReaction.objects.filter(room_id=room_id).count()

    @database_sync_to_async
    def dmm_stat_total(self):
        return DmmReactionStat.objects.aggregate(total=Sum("count"))["total"] or 0
