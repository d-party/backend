#!/bin/sh
set -e

# Schedule the retention cleanup via system cron (replaces django-crontab).
# cron runs with a minimal PATH (no /opt/venv/bin), so use the venv python
# explicitly. manage.py loads the env files itself.
CRON_SCHEDULE="${CRON_SCHEDULE:-0 0 * * *}"
PYTHON_BIN="$(command -v python)"
# cron は親プロセスの環境変数を引き継がないため、settings.py が参照する DEBUG
# などのコンテナ env を取りこぼす。コンテナ起動時の env をスナップショットして
# おき、cron ジョブから source する。
ENV_SNAPSHOT=/etc/cron.d/d-party-env.sh
{
    echo "#!/bin/sh"
    # 値に空白等が含まれてもよいよう、各値をシェル用にクォートする。
    env | awk -F= 'NF>=2 {
        key=$1
        val=substr($0, length(key)+2)
        gsub(/'\''/, "'\''\\'\'''\''", val)
        printf "export %s='\''%s'\''\n", key, val
    }'
} > "$ENV_SNAPSHOT"
chmod 0644 "$ENV_SNAPSHOT"
{
    echo "PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    echo "$CRON_SCHEDULE root . $ENV_SNAPSHOT; cd /usr/src/app && $PYTHON_BIN manage.py cleanup >> /var/log/cron.log 2>&1"
} > /etc/cron.d/d-party-cleanup
chmod 0644 /etc/cron.d/d-party-cleanup
touch /var/log/cron.log
cron

# Close any rooms/users that were left "alive" by the previous process. The
# WebSocket session state lives only in the Django process, so without this
# the /api/.../alive endpoints would keep counting ghost sessions forever.
python manage.py close_active_sessions || true

if [ "$DEBUG" = "1" ]; then
    python manage.py runserver 0.0.0.0:8000
else
    # ASGI app served by gunicorn with the uvicorn worker (see gunicorn.conf.py).
    gunicorn
fi
