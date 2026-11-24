# Sourced by the wave 9 scripts: DATABASE_URL and helpers for a read store database (default `read_store_large`) of one engine.
# usage: RS_DB=read_store_large . scripts/read-store-env.sh mysql|postgresql
# `orm_spike` is wave 8 (scripts/orm-spike-env.sh). Never touches `shopware`, `shopware_test`, `shopware_switch` or `bench_*`.
WEB=instance-web-1
RS_DB="${RS_DB:-read_store_large}"
case "$RS_DB" in shopware|shopware_test|shopware_switch|bench_*) echo "refusing database $RS_DB"; return 2 2>/dev/null || exit 2 ;; esac
case "${1:-}" in
  mysql)      SPIKE_URL="mysql://root:root@mysql:3306/$RS_DB" ;;
  postgresql) SPIKE_URL="pgsql://shopware:shopware@postgres:5432/$RS_DB" ;;
  *) echo "usage: . $0 mysql|postgresql"; return 2 2>/dev/null || exit 2 ;;
esac
SPIKE_DB="$1"
SPIKE_CACHE="${SPIKE_CACHE_BASE:-/tmp/sw-read-store}-$RS_DB-$1"
# bin/console in the web container against $RS_DB, no PHP memory limit (large seeds)
spike_console() { podman exec -e APP_ENV=prod -e "APP_CACHE_DIR=$SPIKE_CACHE" -e "DATABASE_URL=$SPIKE_URL" -e APP_URL=http://localhost:8099 -e SHOPWARE_HTTP_CACHE_ENABLED=0 $WEB php -d memory_limit=-1 bin/console "$@"; }

# O1 (`dal-opensearch`): the lane OpenSearch with the index prefix rs_o1_<database>_ (never the lane's own indices).
# SHOPWARE_ES_INDEXING_ENABLED stays 0 here, the rebuild command (R7) switches it on for its es:index child process only.
RS_ES_PREFIX="rs_o1_${RS_DB}_"
# the PostgreSQL correctness run gets its own indices so it never overwrites the MySQL ones
[ "$1" = postgresql ] && RS_ES_PREFIX="rs_o1_${RS_DB}_pg_"
spike_console_es() { podman exec -e APP_ENV=prod -e "APP_CACHE_DIR=$SPIKE_CACHE-es" -e "DATABASE_URL=$SPIKE_URL" -e APP_URL=http://localhost:8099 -e SHOPWARE_HTTP_CACHE_ENABLED=0 -e SHOPWARE_ES_ENABLED=1 -e SHOPWARE_ES_INDEXING_ENABLED=0 -e "SHOPWARE_ES_INDEX_PREFIX=$RS_ES_PREFIX" -e SHOPWARE_ES_THROW_EXCEPTION=1 $WEB php -d memory_limit=-1 bin/console "$@"; }
# console for an implementation id: the OpenSearch environment for dal-opensearch (and store ids that need it), the plain one otherwise
spike_console_for() { local impl="$1"; shift; case "$impl" in dal-opensearch) spike_console_es "$@" ;; *) spike_console "$@" ;; esac; }
# container of the write database, for the CPU counter
case "$1" in mysql) RS_DB_CONTAINER=instance-mysql-1 ;; postgresql) RS_DB_CONTAINER=instance-postgres-1 ;; esac
rs_cpu_usec() { podman exec "$RS_DB_CONTAINER" sh -c "grep '^usage_usec' /sys/fs/cgroup/cpu.stat" | awk '{print $2}'; }
