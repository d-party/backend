"""Close any rooms / users that are still marked alive at startup.

Channels の WebSocket セッションはプロセス内 (`AnimePartyConsumer`) にのみ存在
するため、Django プロセス（コンテナ）が落ちると ``disconnect`` が呼ばれず
``AnimeRoom`` / ``AnimeUser`` が ``alive`` のまま残る。次回コンテナ起動時に
これらを論理削除しておかないと、統計 API（``alive`` 件数）に幽霊セッションが
残り続けてしまう。

冪等な操作なので、起動毎に無条件で実行してよい。
"""

from django.core.management.base import BaseCommand

from streamer.models import AnimeRoom, AnimeUser


class Command(BaseCommand):
    help = "Logically delete all AnimeRoom / AnimeUser rows still marked alive."

    def handle(self, *args, **options):
        users = AnimeUser.objects.alive().count()
        rooms = AnimeRoom.objects.alive().count()
        AnimeUser.objects.alive().delete()
        AnimeRoom.objects.alive().delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"closed {users} alive user(s) and {rooms} alive room(s)"
            )
        )
