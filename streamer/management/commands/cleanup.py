"""Run the streamer retention/cleanup jobs.

Replaces the ``django-crontab`` registration; schedule this via the container's
system cron (see ``entrypoint.sh``):

    python manage.py cleanup
"""

from django.core.management.base import BaseCommand

from streamer import cron


class Command(BaseCommand):
    help = "Logically/hard delete expired AnimeRoom / AnimeUser / AnimeReaction rows."

    def handle(self, *args, **options):
        for job in cron.ALL_JOBS:
            job()
            self.stdout.write(self.style.SUCCESS(f"ran {job.__name__}"))
