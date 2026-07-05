import datetime
import os

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from streamer.factories import AnimeRoomFactory, AnimeUserFactory, DmmRoomFactory
from streamer.models import (
    AnimeReaction,
    DmmReaction,
    DmmReactionStat,
    ReactionStat,
)


def _clear_reaction_tables() -> None:
    """Drop reaction rows so reaction-count assertions are deterministic.

    The test DB uses a ``MIRROR`` config, so rows committed by ``transaction=True``
    tests (e.g. the consumer folding test) are not flushed between runs. Called in
    ``setUp`` it runs inside the per-test transaction and is rolled back afterwards,
    so it only hides that committed pollution for the duration of one test.

    統計はサービス横断で合算するため（``_reaction_counts_by_type``）、DMM の生／集計
    リアクションも一緒にクリアする（DMM consumer テストが DmmReactionStat をコミットする）。
    """
    ReactionStat.objects.all().delete()
    AnimeReaction.objects.all().delete(hard=True)
    DmmReactionStat.objects.all().delete()
    DmmReaction.objects.all().delete(hard=True)


class TestHealthCheckAPI(APITestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.endpoint = "/api/v1/health"

    @pytest.mark.django_db
    def test_health_check_ok_200(self):
        """ヘルスチェックエンドポイントが 200 を返し、ボディが空であることを確認"""
        response = self.client.get(self.endpoint)
        assert response.status_code == status.HTTP_200_OK
        assert response.content == b""


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


class TestDmmTvLobbyResolveAPI(APITestCase):
    def setUp(self) -> None:
        self.client = APIClient()

    def endpoint(self, room_id) -> str:
        return f"/api/v1/dmm-tv/lobby/{room_id}"

    @pytest.mark.django_db
    def test_lobby_resolve_splits_season_and_content(self):
        """part_id="season/content" を再生ページ URL の season/content へ分解することを確認"""
        season_id = "4wkcznqei1bwdh0axu7zyojaa"
        content_id = "5kx6qgf15fhe80w4ndxppnyb7"
        room = DmmRoomFactory(
            part_id=f"{season_id}/{content_id}", title="大賢者リドル - 第1話"
        )
        response = self.client.get(self.endpoint(room.room_id))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["part_id"] == f"{season_id}/{content_id}"
        assert response.data["room_id"] == str(room.room_id)
        assert response.data["title"] == "大賢者リドル - 第1話"
        url = response.data["redirect_url"]
        assert "tv.dmm.com/vod/playback/on-demand/" in url
        assert f"content={content_id}" in url
        assert f"season={season_id}" in url
        assert "party=join" in url

    @pytest.mark.django_db
    def test_lobby_resolve_content_only_when_no_slash(self):
        """スラッシュを含まない part_id は content のみ（season なし）として扱う"""
        content_id = "c7tzzizzvhuj53zhmpf9aa2c0"
        room = DmmRoomFactory(part_id=content_id)
        response = self.client.get(self.endpoint(room.room_id))
        assert response.status_code == status.HTTP_200_OK
        url = response.data["redirect_url"]
        assert f"content={content_id}" in url
        assert "season=" not in url

    @pytest.mark.django_db
    def test_lobby_resolve_not_found_404(self):
        """存在しないルーム ID では 404 が返ることを確認"""
        import uuid

        response = self.client.get(self.endpoint(uuid.uuid4()))
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestStatsDaysParam(APITestCase):
    """``?days=N`` の検証（未指定→既定、範囲外→400）。"""

    def setUp(self) -> None:
        self.client = APIClient()
        self.endpoint = "/api/v1/statistics/anime-store/active-user-per-day"

    @pytest.mark.django_db
    def test_missing_days_defaults_ok_200(self):
        response = self.client.get(self.endpoint)
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.django_db
    def test_days_out_of_range_400(self):
        for bad in ("0", "366", "-1", "abc", "1.5"):
            response = self.client.get(self.endpoint, {"days": bad})
            assert response.status_code == status.HTTP_400_BAD_REQUEST, bad

    @pytest.mark.django_db
    def test_days_in_range_ok_200(self):
        for ok in ("1", "30", "365"):
            response = self.client.get(self.endpoint, {"days": ok})
            assert response.status_code == status.HTTP_200_OK, ok


class TestStatsPeriodScope(APITestCase):
    """期間スコープ（累計・リアクション）が days に従うことを確認。"""

    def setUp(self) -> None:
        self.client = APIClient()
        _clear_reaction_tables()

    @staticmethod
    def _make_reaction(room, reaction_type, when):
        reaction = AnimeReaction.objects.create(
            room_id=room, reaction_type=reaction_type
        )
        AnimeReaction.objects.filter(pk=reaction.pk).update(created_at=when)
        return reaction

    @pytest.mark.django_db
    def test_user_all_count_respects_days(self):
        """40 日前のユーザーは 30 日窓では数えず 365 日窓では数える。

        テスト DB は ``MIRROR`` 設定で他テストの行が残りうるため、絶対値ではなく
        「40 日前ユーザーを 1 人足すと 365 日窓だけ +1 される」差分で検証する。
        """
        from streamer.models import AnimeUser

        AnimeUserFactory()  # recent（auto_now_add で created_at=now）
        old = AnimeUserFactory()
        AnimeUser.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - datetime.timedelta(days=40)
        )
        endpoint = "/api/v1/statistics/anime-store/anime-user-all-count"

        c30 = self.client.get(endpoint, {"days": "30"}).data["data"]["count"]
        c365 = self.client.get(endpoint, {"days": "365"}).data["data"]["count"]
        assert c30 >= 1  # recent は 30 日窓に入る
        assert c365 - c30 >= 1  # 40 日前ユーザーは 365 日窓のみに入る

    @pytest.mark.django_db
    def test_reaction_counts_come_from_reactionstat_and_live(self):
        """リアクション集計は ReactionStat（畳み込み済み）と alive ルームの合算。"""
        today = timezone.now().date()
        ReactionStat.objects.create(date=today, reaction_type="S", count=5)
        live_room = AnimeRoomFactory()  # alive
        self._make_reaction(live_room, "S", timezone.now())

        by_type = self.client.get(
            "/api/v1/statistics/anime-store/anime-reaction-count", {"days": "30"}
        )
        smile = next(r for r in by_type.data["data"] if r["reaction_type"] == "smile")
        assert smile["count"] == 6  # 5 (folded) + 1 (live)

        total = self.client.get(
            "/api/v1/statistics/anime-store/anime-reaction-all-count", {"days": "30"}
        )
        assert total.data["data"]["count"] == 6

    @pytest.mark.django_db
    def test_reaction_counts_include_dmm_sources(self):
        """リアクション集計は DMM（DmmReactionStat + alive DmmRoom）も合算する。

        統計はサービス横断（``REACTION_SOURCES``）なので、dアニメと DMM の畳み込み済み
        （``ReactionStat`` / ``DmmReactionStat``）と alive ルームの生リアクションが両方とも
        同じ集計に足し込まれる。
        """
        today = timezone.now().date()
        # dアニメ: 畳み込み 2 + alive 1 = 3
        ReactionStat.objects.create(date=today, reaction_type="S", count=2)
        anime_room = AnimeRoomFactory()
        self._make_reaction(anime_room, "S", timezone.now())
        # DMM: 畳み込み 3 + alive 1 = 4
        DmmReactionStat.objects.create(date=today, reaction_type="S", count=3)
        dmm_room = DmmRoomFactory()
        dmm = DmmReaction.objects.create(room_id=dmm_room, reaction_type="S")
        DmmReaction.objects.filter(pk=dmm.pk).update(created_at=timezone.now())

        by_type = self.client.get(
            "/api/v1/statistics/anime-store/anime-reaction-count", {"days": "30"}
        )
        smile = next(r for r in by_type.data["data"] if r["reaction_type"] == "smile")
        assert smile["count"] == 7  # (2+1) anime + (3+1) dmm

        total = self.client.get(
            "/api/v1/statistics/anime-store/anime-reaction-all-count", {"days": "30"}
        )
        assert total.data["data"]["count"] == 7


class TestStatsCache(APITestCase):
    """キャッシュヒット時に DB の変化が TTL 内では反映されないこと。"""

    def setUp(self) -> None:
        self.client = APIClient()
        self.endpoint = "/api/v1/statistics/anime-store/anime-reaction-all-count"
        _clear_reaction_tables()

    @pytest.mark.django_db
    def test_response_is_cached(self):
        today = timezone.now().date()
        ReactionStat.objects.create(date=today, reaction_type="S", count=3)

        first = self.client.get(self.endpoint, {"days": "30"})
        assert first.data["data"]["count"] == 3

        # キャッシュ後に DB を増やしても、同一キーは TTL 内でキャッシュ値を返す。
        ReactionStat.objects.filter(date=today, reaction_type="S").update(count=99)
        second = self.client.get(self.endpoint, {"days": "30"})
        assert second.data["data"]["count"] == 3  # キャッシュヒット
