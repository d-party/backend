import os

import pytest
from rest_framework import status
from rest_framework.test import APIClient, APITestCase


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
