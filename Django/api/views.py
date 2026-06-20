import datetime
import os
import re

import pandas as pd
from django.db.models import Count
from django.db.models.functions import TruncDate
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAdminUser
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

    permission_classes = [IsAdminUser]

    def get(self, request, format=None) -> Response:
        frame = _resample_per_day(_per_day_counts(AnimeUser))
        return Response({"data": frame.to_dict(orient="records")})


class AnimeActiveRoomPerDayAPI(APIView):
    """Daily count of rooms created by users."""

    permission_classes = [IsAdminUser]

    def get(self, request, format=None) -> Response:
        frame = _resample_per_day(_per_day_counts(AnimeRoom))
        return Response({"data": frame.to_dict(orient="records")})


class AnimeRoomReactionCountAPI(APIView):
    """Per-type reaction counts."""

    permission_classes = [IsAdminUser]

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

    permission_classes = [IsAdminUser]

    def get(self, request, format=None) -> Response:
        return Response({"data": {"count": AnimeReaction.objects.all().count()}})


class AnimeUserAllCountAPI(APIView):
    """Total user count."""

    permission_classes = [IsAdminUser]

    def get(self, request, format=None) -> Response:
        return Response({"data": {"count": AnimeUser.objects.all().count()}})


class AnimeRoomAllCountAPI(APIView):
    """Total room count."""

    permission_classes = [IsAdminUser]

    def get(self, request, format=None) -> Response:
        return Response({"data": {"count": AnimeRoom.objects.all().count()}})


class AnimeUserAliveCountAPI(APIView):
    """Currently connected user count."""

    permission_classes = [IsAdminUser]

    def get(self, request, format=None) -> Response:
        return Response({"data": {"count": AnimeUser.objects.alive().count()}})


class AnimeRoomAliveCountAPI(APIView):
    """Currently active room count."""

    permission_classes = [IsAdminUser]

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
