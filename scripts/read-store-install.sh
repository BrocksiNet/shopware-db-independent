#!/usr/bin/env bash
# Install Shopware into the database $RS_DB (default read_store_large) and seed the wave 9 data set (orm-spike:seed with search keywords).
# usage: RS_DB=read_store_large scripts/read-store-install.sh mysql|postgresql [seed options, default --simple=100000 --parents=10000 --keywords]
# Writes the log to /tmp/read-store-install-<db>-<engine>.log. The database is dropped and recreated.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/read-store-env.sh" "${1:-}"
shift || true
[ $# -eq 0 ] && set -- --simple=100000 --parents=10000 --keywords
LOG="/tmp/read-store-install-$RS_DB-$SPIKE_DB.log"
podman exec $WEB rm -rf "$SPIKE_CACHE"
{
  date
  spike_console system:install --basic-setup --drop-database --create-database --force --no-interaction
  spike_console cache:clear --no-interaction
  spike_console orm-spike:seed --no-interaction "$@"
  date
} > "$LOG" 2>&1
tail -3 "$LOG" | cut -c1-200
