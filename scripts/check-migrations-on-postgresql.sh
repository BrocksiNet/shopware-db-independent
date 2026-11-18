#!/bin/sh
# Runs all core migrations on an empty PostgreSQL database and compares the resulting schema with the expected one.
# usage: scripts/check-migrations-on-postgresql.sh
# environment: PG_CONTAINER (instance-postgres-1), WEB_CONTAINER (instance-web-1), PG_USER (shopware), PG_PASSWORD (shopware), CHECK_DATABASE (shopware_migrations)
# exit code: 0 when every migration ran and the schema equals scripts/expected-catalog.json
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PG_CONTAINER=${PG_CONTAINER:-instance-postgres-1}
WEB_CONTAINER=${WEB_CONTAINER:-instance-web-1}
PG_USER=${PG_USER:-shopware}
PG_PASSWORD=${PG_PASSWORD:-shopware}
DB=${CHECK_DATABASE:-shopware_migrations}
COMPAT="$ROOT/instance/src/Core/Framework/Adapter/Database/PostgreSQL/mysql-compat.sql"

psql_admin() { podman exec -i "$PG_CONTAINER" psql -U "$PG_USER" -v ON_ERROR_STOP=1 -q "$@"; }

echo "== empty database $DB"
psql_admin -d postgres -c "DROP DATABASE IF EXISTS \"$DB\" WITH (FORCE)" -c "CREATE DATABASE \"$DB\""
psql_admin -d "$DB" < "$COMPAT" > /dev/null

echo "== system:install (runs the update and the destructive migrations)"
podman exec -e "DATABASE_URL=pgsql://$PG_USER:$PG_PASSWORD@postgres:5432/$DB" -e APP_ENV=prod "$WEB_CONTAINER" \
    sh -c 'php bin/console system:install --force --no-interaction > /tmp/check-migrations.log 2>&1' \
    || { echo "system:install failed, see /tmp/check-migrations.log in $WEB_CONTAINER"; podman exec "$WEB_CONTAINER" grep -m1 -B2 -A8 CRITICAL /tmp/check-migrations.log || true; exit 1; }

echo "== migrations"
COUNTS=$(podman exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$DB" -Atc 'select count(*), count(*) filter (where "update" is not null), count(*) filter (where update_destructive is not null) from migration')
echo "total|update|destructive: $COUNTS"
TOTAL=${COUNTS%%|*}
[ "$COUNTS" = "$TOTAL|$TOTAL|$TOTAL" ] || { echo "not every migration ran"; exit 1; }

echo "== schema"
PG_CONTAINER=$PG_CONTAINER PG_USER=$PG_USER python3 "$ROOT/scripts/compare-schema.py" check "$DB"
