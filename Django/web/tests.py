from http import HTTPStatus

import pytest
from django.test import Client, TestCase

from streamer.factories import AnimeRoomFactory


class TestIndexView(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.endpoint = "/"

    @pytest.mark.django_db
    def test_ok_200(self):
        response = self.client.get(self.endpoint)
        assert response.status_code == HTTPStatus.OK


class TestUsageView(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.endpoint = "/usage"

    @pytest.mark.django_db
    def test_ok_200(self):
        response = self.client.get(self.endpoint)
        assert response.status_code == HTTPStatus.OK


class TestAnimeRobbyView(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.anime_room = AnimeRoomFactory()
        self.endpoint = "/anime-store/lobby/{}"

    @pytest.mark.django_db
    def test_ok_200(self):
        response = self.client.get(self.endpoint.format(str(self.anime_room.room_id)))
        assert response.status_code == HTTPStatus.OK

    @pytest.mark.django_db
    def test_ok_404(self):
        response = self.client.get(self.endpoint.format("hello"))
        assert response.status_code == HTTPStatus.NOT_FOUND

    @pytest.mark.django_db
    def test_ok_404(self):
        self.anime_room.delete()
        response = self.client.get(self.endpoint.format(str(self.anime_room.room_id)))
        assert response.status_code == HTTPStatus.NOT_FOUND
