"""
ASGI config for d_party project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "d_party.settings")

# application = get_asgi_application()
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import OriginValidator

import streamer.routing

from . import settings

allowed_hosts = [
    os.environ["D_ANIME_STORE_DOMAIN"],
    "http://" + os.environ["D_ANIME_STORE_DOMAIN"],
    "https://" + os.environ["D_ANIME_STORE_DOMAIN"],
    "http://" + os.environ["D_ANIME_STORE_DOMAIN"] + ":80",
    "https://" + os.environ["D_ANIME_STORE_DOMAIN"] + ":443",
]

# タイマー画面は d-party フロントエンド（MY_DOMAIN）のオリジンから WebSocket を張り、
# spectate で観覧専用参加する。拡張機能（D_ANIME_STORE_DOMAIN）とは別オリジンのため、
# MY_DOMAIN 由来のオリジンも WS の OriginValidator に許可する（許可の拡大のみ）。
_my_domain = os.environ["MY_DOMAIN"]
allowed_hosts += [
    _my_domain,
    "http://" + _my_domain,
    "https://" + _my_domain,
    "http://www." + _my_domain,
    "https://www." + _my_domain,
]

if settings.DEBUG:
    allowed_hosts += ["*"]


application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": OriginValidator(
            AuthMiddlewareStack(URLRouter(streamer.routing.websocket_urlpatterns)),
            allowed_hosts,
        ),
    }
)
