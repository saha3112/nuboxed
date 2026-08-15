#!/bin/sh
set -eu

# A deployment container should be self-initialising.  These commands are
# deliberately controlled by environment variables so operators can disable
# them when migrations/static files are managed by a separate release job.
if [ "${RUN_MIGRATIONS:-True}" = "True" ]; then
    python manage.py migrate --noinput
fi

if [ "${RUN_COLLECTSTATIC:-True}" = "True" ]; then
    python manage.py collectstatic --noinput
fi

exec "$@"
