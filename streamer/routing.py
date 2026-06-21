from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path("anime-store/party/", consumers.AnimePartyConsumer.as_asgi()),
]
