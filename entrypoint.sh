#!/bin/sh
set -e

# Schedule the retention cleanup via system cron (replaces django-crontab).
# manage.py loads the env files itself, so the job needs no extra environment.
CRON_SCHEDULE="${CRON_SCHEDULE:-0 0 * * *}"
echo "$CRON_SCHEDULE cd /usr/src/app && python manage.py cleanup >> /var/log/cron.log 2>&1" > /etc/cron.d/d-party-cleanup
chmod 0644 /etc/cron.d/d-party-cleanup
crontab /etc/cron.d/d-party-cleanup
touch /var/log/cron.log
cron

if [ "$DEBUG" = "1" ]; then
    python manage.py runserver 0.0.0.0:8000
else
    # ASGI app served by gunicorn with the uvicorn worker (see gunicorn.conf.py).
    gunicorn
fi
