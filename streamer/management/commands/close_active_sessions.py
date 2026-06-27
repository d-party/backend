"""Reap stale "alive" rooms / users left behind by an ungraceful shutdown.

Channels WebSocket session state lives only in the Django process
(`AnimePartyConsumer`). On a graceful shutdown each connection's
``disconnect`` fires and ``leave_party`` cleans up the rows, but on a hard
crash (OOMKill / node loss / SIGKILL) ``disconnect`` never runs and the
``AnimeRoom`` / ``AnimeUser`` rows stay ``alive`` forever — inflating the
``alive`` count stats.

A real session never lasts longer than ``STALE_AFTER`` (an active room keeps
its ``updated_at`` fresh — the host broadcasts a sync every few seconds — so a
row whose ``updated_at`` is older than the threshold is certainly a ghost).
We therefore close only rows older than that threshold rather than *all* alive
rows. This makes the command safe to run at every container start even with
multiple replicas: a freshly started replica will not wipe the live sessions
served by another replica, since those have a recent ``updated_at``.

Idempotent, so it is fine to run unconditionally on every startup.
"""

import datetime

from django.core.management.base import BaseCommand
from django.utils.timezone import now

from streamer.models import AnimeRoom, AnimeUser

# Sessions are not expected to last this long; anything older that is still
# marked alive is a leftover ghost from an ungraceful shutdown.
STALE_AFTER = datetime.timedelta(days=1)


class Command(BaseCommand):
    help = (
        "Logically delete AnimeRoom / AnimeUser rows still marked alive whose "
        "updated_at is older than the staleness threshold (leftover ghosts)."
    )

    def handle(self, *args, **options):
        cutoff = now() - STALE_AFTER
        users = AnimeUser.objects.alive().filter(updated_at__lt=cutoff)
        rooms = AnimeRoom.objects.alive().filter(updated_at__lt=cutoff)
        user_count = users.count()
        room_count = rooms.count()
        users.delete()
        rooms.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"closed {user_count} stale user(s) and {room_count} stale room(s)"
            )
        )
