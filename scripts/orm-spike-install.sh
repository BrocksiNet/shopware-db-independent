#!/usr/bin/env bash
# Install Shopware into the database `orm_spike` of one engine and seed the wave 8 data set (orm-spike:seed).
# usage: scripts/orm-spike-install.sh mysql|mariadb|postgresql|sqlite [seed options, e.g. --products=500]
# Writes the log to /tmp/orm-spike-install-<engine>.log. The database is dropped and recreated.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/orm-spike-env.sh" "${1:-}"
shift || true
LOG="/tmp/orm-spike-install-$SPIKE_DB.log"
[ "$SPIKE_DB" = sqlite ] && podman exec $WEB sh -c 'mkdir -p var/switch && rm -f var/switch/orm_spike.sqlite*'
podman exec $WEB rm -rf "$SPIKE_CACHE"
{
  date
  spike_console system:install --basic-setup --drop-database --create-database --force --no-interaction
  spike_console cache:clear --no-interaction
  spike_console orm-spike:seed --no-interaction "$@"
  date
} > "$LOG" 2>&1
tail -3 "$LOG" | cut -c1-200
