#!/bin/sh
set -e

# Reap any rooms/users left "alive" by an ungraceful shutdown of a *previous*
# process. WebSocket session state lives only in the Django process, so a hard
# crash leaves ghost rows that would keep inflating the /api/.../alive counts.
# This only closes rows whose updated_at is older than the staleness threshold,
# so it never touches sessions currently being served by another replica —
# safe to run on every start even with multiple replicas.
python manage.py close_active_sessions || true

if [ "$DEBUG" = "1" ]; then
    python manage.py runserver 0.0.0.0:8000
else
    # ASGI app served by gunicorn with the uvicorn worker (see gunicorn.conf.py).
    gunicorn
fi
