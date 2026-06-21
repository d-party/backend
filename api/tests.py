import os

import pytest
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from streamer.factories import AnimeRoomFactory


class TestVersionCheckAPI(APITestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.endpoint = "/api/v1/chrome-extension/version-check"

    @pytest.mark.django_db
    def test_version_check_possible_ok_200(self):
        """version checkが成功する場合のテストケース
        求められる最小のバージョンを超えている場合、status_code:200が返ることを確認
        is_possibleがtrueであることを確認
        """
        get_params = {"extension-version": "1000.0.0"}
        response = self.client.get(self.endpoint, get_params)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_possible"]
        assert type(response.data["is_possible"]) == bool

    @pytest.mark.django_db
    def test_version_check_possible_edgecase_ok_200(self):
        """version checkが成功する場合のテストケース
        求められる最小のバージョンとイコールの場合、status_code:200が返ることを確認
        is_possibleがtrueであることを確認
        """
        get_params = {
            "extension-version": str(os.getenv("CHROME_EXTENSION_REQUIRED_VERSION"))
        }
        response = self.client.get(self.endpoint, get_params)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_possible"]
        assert type(response.data["is_possible"]) == bool

    @pytest.mark.django_db
    def test_version_check_impossible_ok_200(self):
        """version checkが失敗する場合のテストケース
        求められる最小のバージョンを超えていない場合、status_code:200が返ることを確認
        is_possibleがfalseであることを確認
        """
        get_params = {"extension-version": "0.0.0"}
        response = self.client.get(self.endpoint, get_params)
        assert response.status_code == status.HTTP_200_OK
        assert not response.data["is_possible"]
        assert type(response.data["is_possible"]) == bool

    @pytest.mark.django_db
    def test_version_check_ng_406(self):
        """version checkが失敗する場合のテストケース
        フォーマット通りではない場合に、406が返ってくることを確認
        """
        get_params = {"extension-version": "string"}
        response = self.client.get(self.endpoint, get_params)
        assert response.status_code == status.HTTP_406_NOT_ACCEPTABLE
        get_params = {"extension-version": 1000}
        response = self.client.get(self.endpoint, get_params)
        assert response.status_code == status.HTTP_406_NOT_ACCEPTABLE
        get_params = {"extension-version": "1000.0.0.0.0"}
        response = self.client.get(self.endpoint, get_params)
        assert response.status_code == status.HTTP_406_NOT_ACCEPTABLE

    @pytest.mark.django_db
    def test_version_check_ng_400(self):
        """version checkが失敗する場合のテストケース
        extension-versionが存在しない場合、400が返ってくることを確認
        """
        response = self.client.get(self.endpoint)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        get_params = {"version": "1000.0.0"}
        response = self.client.get(self.endpoint, get_params)
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestAnimeStoreLobbyResolveAPI(APITestCase):
    def setUp(self) -> None:
        self.client = APIClient()

    def endpoint(self, room_id) -> str:
        return f"/api/v1/anime-store/lobby/{room_id}"

    @pytest.mark.django_db
    def test_lobby_resolve_ok_200(self):
        """ルームが存在する場合、redirect_url と保存済みタイトルを返すことを確認"""
        room = AnimeRoomFactory(part_id="654321", title="鬼滅の刃 - 第1話 - 残酷")
        response = self.client.get(self.endpoint(room.room_id))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["part_id"] == "654321"
        assert response.data["room_id"] == str(room.room_id)
        assert response.data["title"] == "鬼滅の刃 - 第1話 - 残酷"
        assert "partId=654321" in response.data["redirect_url"]

    @pytest.mark.django_db
    def test_lobby_resolve_not_found_404(self):
        """存在しないルーム ID では 404 が返ることを確認"""
        import uuid

        response = self.client.get(self.endpoint(uuid.uuid4()))
        assert response.status_code == status.HTTP_404_NOT_FOUND
