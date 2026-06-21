import datetime
import os
import re
import urllib.parse

import pandas as pd
from django.db.models import Count
from django.db.models.functions import TruncDate
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from streamer.models import AnimeReaction, AnimeRoom, AnimeUser, ReactionType

# Matches the previous ``distutils.version.StrictVersion`` accepted form: a
# strict ``major.minor.patch`` triple. ``distutils`` was removed in Python 3.12.
_STRICT_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _parse_strict_version(value: str) -> tuple[int, int, int] | None:
    """Parse a strict ``x.y.z`` version into a comparable tuple, else ``None``."""
    if _STRICT_VERSION_RE.match(value):
        major, minor, patch = (int(part) for part in value.split("."))
        return (major, minor, patch)
    return None


def _per_day_counts(model) -> list[dict]:
    """Return ``[{"day": date, "count": n}, ...]`` grouped by creation day.

    Uses ``TruncDate`` so the query works across database backends (the
    previous ``.extra(select={"day": "date(created_at)"})`` was MySQL-specific).
    """
    return list(
        model.objects.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Count("created_at"))
        .order_by("day")
    )


def _resample_per_day(rows: list[dict]) -> pd.DataFrame:
    """Fill gaps so every calendar day up to today has a count."""
    if len(rows) == 0 or rows[-1]["day"] != datetime.date.today():
        rows = rows + [{"day": datetime.date.today(), "count": 0}]
    frame = pd.DataFrame(rows).set_index("day").asfreq("1D", fill_value=0)
    frame["day"] = frame.index.map(lambda x: x.to_pydatetime().date())
    return frame


class ChromeExtensionVersionCheckAPI(APIView):
    """Check whether a Chrome extension version is compatible with the backend."""

    permission_classes = [AllowAny]

    def get(self, request, format=None) -> Response:
        if "extension-version" not in request.GET:
            return Response(
                {"message": "extension-versionパラメータが存在しません"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        current_version = _parse_strict_version(
            str(request.GET.get("extension-version"))
        )
        required_version = _parse_strict_version(
            str(os.getenv("CHROME_EXTENSION_REQUIRED_VERSION"))
        )
        if current_version is None or required_version is None:
            return Response(
                {"message": "求めているバージョンの記法と一致しません"},
                status=status.HTTP_406_NOT_ACCEPTABLE,
            )

        return Response(
            {"is_possible": current_version >= required_version},
            status=status.HTTP_200_OK,
        )


class AnimeActiveUserPerDayAPI(APIView):
    """Daily count of users that have ever been in a room."""

    # 統計ダッシュボードはフロントエンドから誰でも閲覧できるよう公開（認証不要）。
    permission_classes = [AllowAny]

    def get(self, request, format=None) -> Response:
        frame = _resample_per_day(_per_day_counts(AnimeUser))
        return Response({"data": frame.to_dict(orient="records")})


class AnimeActiveRoomPerDayAPI(APIView):
    """Daily count of rooms created by users."""

    # 統計ダッシュボードはフロントエンドから誰でも閲覧できるよう公開（認証不要）。
    permission_classes = [AllowAny]

    def get(self, request, format=None) -> Response:
        frame = _resample_per_day(_per_day_counts(AnimeRoom))
        return Response({"data": frame.to_dict(orient="records")})


class AnimeRoomReactionCountAPI(APIView):
    """Per-type reaction counts."""

    # 統計ダッシュボードはフロントエンドから誰でも閲覧できるよう公開（認証不要）。
    permission_classes = [AllowAny]

    def get(self, request, format=None) -> Response:
        response = [
            {
                "count": AnimeReaction.objects.filter(reaction_type=value)
                .all()
                .count(),
                "reaction_type": label,
            }
            for value, label in ReactionType.choices
        ]
        return Response({"data": response})


class AnimeRoomReactionAllCountAPI(APIView):
    """Total reaction count."""

    # 統計ダッシュボードはフロントエンドから誰でも閲覧できるよう公開（認証不要）。
    permission_classes = [AllowAny]

    def get(self, request, format=None) -> Response:
        return Response({"data": {"count": AnimeReaction.objects.all().count()}})


class AnimeUserAllCountAPI(APIView):
    """Total user count."""

    # 統計ダッシュボードはフロントエンドから誰でも閲覧できるよう公開（認証不要）。
    permission_classes = [AllowAny]

    def get(self, request, format=None) -> Response:
        return Response({"data": {"count": AnimeUser.objects.all().count()}})


class AnimeRoomAllCountAPI(APIView):
    """Total room count."""

    # 統計ダッシュボードはフロントエンドから誰でも閲覧できるよう公開（認証不要）。
    permission_classes = [AllowAny]

    def get(self, request, format=None) -> Response:
        return Response({"data": {"count": AnimeRoom.objects.all().count()}})


class AnimeUserAliveCountAPI(APIView):
    """Currently connected user count."""

    # 統計ダッシュボードはフロントエンドから誰でも閲覧できるよう公開（認証不要）。
    permission_classes = [AllowAny]

    def get(self, request, format=None) -> Response:
        return Response({"data": {"count": AnimeUser.objects.alive().count()}})


class AnimeRoomAliveCountAPI(APIView):
    """Currently active room count."""

    # 統計ダッシュボードはフロントエンドから誰でも閲覧できるよう公開（認証不要）。
    permission_classes = [AllowAny]

    def get(self, request, format=None) -> Response:
        return Response({"data": {"count": AnimeRoom.objects.alive().count()}})


class _ShieldsView(APIView):
    """Base view returning a shields.io endpoint badge payload.

    Replaces the unmaintained ``django-dynamic-shields`` dependency while
    keeping the public badge JSON contract (``schemaVersion`` 1).
    """

    permission_classes = [AllowAny]

    def shields_data(self) -> dict:
        raise NotImplementedError

    def get(self, request, format=None) -> Response:
        return Response({"schemaVersion": 1, **self.shields_data()})


class RoomCountShieldsAPI(_ShieldsView):
    def shields_data(self) -> dict:
        return {"label": "TotalRoom", "message": str(AnimeRoom.objects.all().count())}


class RoomCountParDayShieldsAPI(_ShieldsView):
    def shields_data(self) -> dict:
        frame = _resample_per_day(_per_day_counts(AnimeRoom))
        mean = "{:.2f}".format(frame["count"].mean()) + "/day"
        return {
            "label": "Room",
            "message": mean,
            "color": "brightgreen",
            "cacheSeconds": 86400,
        }


class UserCountShieldsAPI(_ShieldsView):
    def shields_data(self) -> dict:
        return {"label": "TotalUser", "message": str(AnimeUser.objects.all().count())}


class UserCountParDayShieldsAPI(_ShieldsView):
    def shields_data(self) -> dict:
        frame = _resample_per_day(_per_day_counts(AnimeUser))
        mean = "{:.2f}".format(frame["count"].mean()) + "/day"
        return {
            "label": "User",
            "message": mean,
            "color": "brightgreen",
            "cacheSeconds": 86400,
        }


class ReactionCountShieldsAPI(_ShieldsView):
    def shields_data(self) -> dict:
        return {
            "label": "TotalReaction",
            "message": str(AnimeReaction.objects.all().count()),
        }


class AnimeStoreLobbyResolveAPI(APIView):
    """Resolve a room id to the dアニメストア redirect URL.

    Server-side replacement for the old ``web.views.AnimeRoomLobby`` template
    view: the React frontend's room-transition page (``/anime-store/lobby/
    <room_id>``) calls this to learn where to redirect the user once the
    extension has confirmed it is installed and compatible.
    """

    permission_classes = [AllowAny]

    def get(self, request, room_id, format=None) -> Response:
        # 旧 anime.dmkt-sp.jp から animestore.docomo.ne.jp へ移行済み。
        anime_store_domain = os.environ.get(
            "D_ANIME_STORE_DOMAIN", "animestore.docomo.ne.jp"
        )
        try:
            anime_room = AnimeRoom.objects.get(room_id=room_id)
        except AnimeRoom.DoesNotExist:
            return Response(
                {"message": "ルームが見つかりません"},
                status=status.HTTP_404_NOT_FOUND,
            )
        if anime_room.deleted_at is not None:
            return Response(
                {"message": "ルームは終了しています"},
                status=status.HTTP_404_NOT_FOUND,
            )

        base_url = f"https://{anime_store_domain}/animestore/sc_d_pc?"
        url_param = urllib.parse.urlencode(
            {
                "partId": anime_room.part_id,
                "party": "join",
                "room_id": str(room_id),
            }
        )
        return Response(
            {
                "redirect_url": base_url + url_param,
                "part_id": anime_room.part_id,
                "room_id": str(room_id),
                "title": anime_room.title,
            },
            status=status.HTTP_200_OK,
        )
