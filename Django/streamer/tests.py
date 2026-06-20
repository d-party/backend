import uuid

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase

from .consumers import AnimePartyConsumer
from .factories import AnimeRoomFactory, AnimeUserFactory
from .models import AnimeRoom, AnimeUser


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
        await communicator.send_json_to(
            {
                "action": "create",
                "user_name": user_name1,
                "part_id": "123456",
                "request_id": 100,
            }
        )
        response = await communicator.receive_json_from()
        assert response["action"] == "create"
        assert response["user"]["user_name"] == user_name1
        # userがデータベースに作られていることを確認
        assert self.anime_user_exist(response["user"]["user_id"])
        # roomがデータベースに作られていることを確認
        assert self.anime_room_exist(response["room_id"])
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
        assert self.anime_user_exist(response["user"]["user_id"])
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
        assert response["message"] == "failed_join"
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
