# Sourced by the wave 8 scripts: DATABASE_URL and helpers for the `orm_spike` database of one engine.
# usage: . scripts/orm-spike-env.sh mysql|mariadb|postgresql|sqlite
# Never touches the lane database `shopware` or `shopware_switch`.
WEB=instance-web-1
case "${1:-}" in
  mysql)      SPIKE_URL='mysql://root:root@mysql:3306/orm_spike' ;;
  mariadb)    SPIKE_URL='mysql://root:root@database:3306/orm_spike' ;;
  postgresql) SPIKE_URL='pgsql://shopware:shopware@postgres:5432/orm_spike' ;;
  sqlite)     SPIKE_URL='sqlite:////var/www/html/var/switch/orm_spike.sqlite' ;;
  *) echo "usage: . $0 mysql|mariadb|postgresql|sqlite"; return 2 2>/dev/null || exit 2 ;;
esac
SPIKE_DB="$1"
# every session sets its own cache base (e.g. SPIKE_CACHE_BASE=/tmp/sw-orm-spike-doctrine) so parallel handoffs do not rebuild the same cache
SPIKE_CACHE="${SPIKE_CACHE_BASE:-/tmp/sw-orm-spike}-$1"
# run bin/console inside the web container against the orm_spike database of the engine
spike_console() { podman exec -e APP_ENV=prod -e "APP_CACHE_DIR=$SPIKE_CACHE" -e "DATABASE_URL=$SPIKE_URL" -e APP_URL=http://localhost:8099 -e SHOPWARE_HTTP_CACHE_ENABLED=0 $WEB bin/console "$@"; }
