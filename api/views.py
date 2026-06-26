import datetime
import os
import re
import urllib.parse
from collections import defaultdict

import pandas as pd
from django.core.cache import cache
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from streamer.models import (
    AnimeReaction,
    AnimeRoom,
    AnimeUser,
    ReactionStat,
    ReactionType,
)

# Matches the previous ``distutils.version.StrictVersion`` accepted form: a
# strict ``major.minor.patch`` triple. ``distutils`` was removed in Python 3.12.
_STRICT_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")

# 統計の集計期間（``?days=N``）。未指定は 1 年、上限も 1 年。
DEFAULT_STATS_DAYS = 365
MAX_STATS_DAYS = 365
# 統計レスポンスをキャッシュする秒数。毎リクエストの DB 集計を避けるための TTL。
STATS_CACHE_SECONDS = int(os.getenv("STATS_CACHE_SECONDS", "300"))


def _parse_days(request) -> int | None:
    """Parse ``?days=N`` into ``1..365``; ``None`` signals an invalid request.

    Missing parameter defaults to ``DEFAULT_STATS_DAYS`` (1 year).
    """
    raw = request.GET.get("days")
    if raw is None:
        return DEFAULT_STATS_DAYS
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return None
    if days < 1 or days > MAX_STATS_DAYS:
        return None
    return days


def _bad_days() -> Response:
    return Response(
        {"message": f"days パラメータは 1〜{MAX_STATS_DAYS} の整数で指定してください"},
        status=status.HTTP_400_BAD_REQUEST,
    )


def _since(days: int) -> datetime.date:
    """Inclusive start date of a ``days``-long window ending today."""
    return datetime.date.today() - datetime.timedelta(days=days - 1)


def _cached(key: str, producer):
    """Return a cached stats payload, computing (and storing) it on a miss."""
    return cache.get_or_set(key, producer, STATS_CACHE_SECONDS)


def _reaction_counts_by_type(since: datetime.date) -> dict[str, int]:
    """Per-type reaction counts in ``[since, today]`` (folded + live rooms).

    Historical reactions live in ``ReactionStat`` (folded on room end); reactions
    of still-alive rooms remain in ``AnimeReaction`` and are added on top so the
    total reflects in-progress rooms too. Keyed by the stored ``reaction_type``
    value (e.g. ``"S"``).
    """
    merged: dict[str, int] = defaultdict(int)
    folded = (
        ReactionStat.objects.filter(date__gte=since)
        .values("reaction_type")
        .annotate(total=Sum("count"))
    )
    for row in folded:
        merged[row["reaction_type"]] += row["total"]
    live = (
        AnimeReaction.objects.filter(
            room_id__deleted_at__isnull=True, created_at__date__gte=since
        )
        .values("reaction_type")
        .annotate(total=Count("reaction_id"))
    )
    for row in live:
        merged[row["reaction_type"]] += row["total"]
    return merged


def _parse_strict_version(value: str) -> tuple[int, int, int] | None:
    """Parse a strict ``x.y.z`` version into a comparable tuple, else ``None``."""
    if _STRICT_VERSION_RE.match(value):
        major, minor, patch = (int(part) for part in value.split("."))
        return (major, minor, patch)
    return None


def _per_day_counts(model, since: datetime.date | None = None) -> list[dict]:
    """Return ``[{"day": date, "count": n}, ...]`` grouped by creation day.

    When ``since`` is given, only rows created on/after it are counted. Uses
    ``TruncDate`` so the query works across database backends (the previous
    ``.extra(select={"day": "date(created_at)"})`` was MySQL-specific).
    """
    qs = model.objects
    if since is not None:
        qs = qs.filter(created_at__date__gte=since)
    return list(
        qs.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Count("created_at"))
        .order_by("day")
    )


def _resample_per_day(
    rows: list[dict], since: datetime.date | None = None
) -> pd.DataFrame:
    """Fill gaps so every calendar day has a count.

    The series always extends to today; when ``since`` is given it also starts
    exactly at ``since`` (padding the leading days with zeros) so the window has
    a fixed length regardless of when the first event happened.
    """
    today = datetime.date.today()
    if since is not None and (len(rows) == 0 or rows[0]["day"] != since):
        rows = [{"day": since, "count": 0}] + rows
    if len(rows) == 0 or rows[-1]["day"] != today:
        rows = rows + [{"day": today, "count": 0}]
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
        days = _parse_days(request)
        if days is None:
            return _bad_days()
        since = _since(days)

        def produce():
            frame = _resample_per_day(_per_day_counts(AnimeUser, since), since)
            return frame.to_dict(orient="records")

        return Response({"data": _cached(f"stats:active-user-per-day:{days}", produce)})


class AnimeActiveRoomPerDayAPI(APIView):
    """Daily count of rooms created by users."""

    # 統計ダッシュボードはフロントエンドから誰でも閲覧できるよう公開（認証不要）。
    permission_classes = [AllowAny]

    def get(self, request, format=None) -> Response:
        days = _parse_days(request)
        if days is None:
            return _bad_days()
        since = _since(days)

        def produce():
            frame = _resample_per_day(_per_day_counts(AnimeRoom, since), since)
            return frame.to_dict(orient="records")

        return Response({"data": _cached(f"stats:active-room-per-day:{days}", produce)})


class AnimeRoomReactionCountAPI(APIView):
    """Per-type reaction counts."""

    # 統計ダッシュボードはフロントエンドから誰でも閲覧できるよう公開（認証不要）。
    permission_classes = [AllowAny]

    def get(self, request, format=None) -> Response:
        days = _parse_days(request)
        if days is None:
            return _bad_days()
        since = _since(days)

        def produce():
            merged = _reaction_counts_by_type(since)
            return [
                {"count": merged.get(value, 0), "reaction_type": label}
                for value, label in ReactionType.choices
            ]

        return Response({"data": _cached(f"stats:reaction-count:{days}", produce)})


class AnimeRoomReactionAllCountAPI(APIView):
    """Total reaction count."""

    # 統計ダッシュボードはフロントエンドから誰でも閲覧できるよう公開（認証不要）。
    permission_classes = [AllowAny]

    def get(self, request, format=None) -> Response:
        days = _parse_days(request)
        if days is None:
            return _bad_days()
        since = _since(days)

        def produce():
            return sum(_reaction_counts_by_type(since).values())

        count = _cached(f"stats:reaction-all-count:{days}", produce)
        return Response({"data": {"count": count}})


class AnimeUserAllCountAPI(APIView):
    """User count within the requested period (by creation date)."""

    # 統計ダッシュボードはフロントエンドから誰でも閲覧できるよう公開（認証不要）。
    permission_classes = [AllowAny]

    def get(self, request, format=None) -> Response:
        days = _parse_days(request)
        if days is None:
            return _bad_days()
        since = _since(days)

        def produce():
            return AnimeUser.objects.filter(created_at__date__gte=since).count()

        count = _cached(f"stats:user-all-count:{days}", produce)
        return Response({"data": {"count": count}})


class AnimeRoomAllCountAPI(APIView):
    """Room count within the requested period (by creation date)."""

    # 統計ダッシュボードはフロントエンドから誰でも閲覧できるよう公開（認証不要）。
    permission_classes = [AllowAny]

    def get(self, request, format=None) -> Response:
        days = _parse_days(request)
        if days is None:
            return _bad_days()
        since = _since(days)

        def produce():
            return AnimeRoom.objects.filter(created_at__date__gte=since).count()

        count = _cached(f"stats:room-all-count:{days}", produce)
        return Response({"data": {"count": count}})


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
