#!/bin/sh
# Benchmark MariaDB against PostgreSQL (translator based), see docs/13-benchmark.md.
# usage: scripts/benchmark.sh snapshot [sha]   copy the PHP code of a commit into the web container (isolated from live edits)
#        scripts/benchmark.sh prepare          5 timed installs per database, demo data, 5 timed dal:refresh:index runs per database
#        scripts/benchmark.sh stacks           start php-fpm + caddy per database (ports 8101 mariadb, 8102 pg, 8103 pg with timing probes)
#        scripts/benchmark.sh run [--merge] [--only name]   latency/throughput scenarios, alternating the databases, then the translator pass
#        scripts/benchmark.sh all
# The lane databases (`shopware`) are never touched, the benchmark uses the databases bench_mariadb and bench_pg.
# environment: WEB (instance-web-1), PG (instance-postgres-1), MARIA (instance-database-1), RUNS (5), SHA (HEAD of instance/), SIZE_PRODUCTS (2000)
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
WEB=${WEB:-instance-web-1}
PG=${PG:-instance-postgres-1}
MARIA=${MARIA:-instance-database-1}
RUNS=${RUNS:-5}
SRC=/tmp/bench-src
OUT=${OUT:-$ROOT/docs/benchmark-results}
APP_URL=http://127.0.0.1:8101
COMPAT="$ROOT/instance/src/Core/Framework/Adapter/Database/PostgreSQL/mysql-compat.sql"

db_url() {
    case $1 in
        mariadb) echo 'mysql://root:root@database/bench_mariadb' ;;
        pg) echo 'pgsql://shopware:shopware@postgres:5432/bench_pg' ;;
    esac
}

now() { python3 -c 'import time; print(time.time())'; }
elapsed() { python3 -c "print(round($2 - $1, 2))"; }

# console <mariadb|pg> args...: Symfony console in the snapshot, prod, no Xdebug
console() {
    K=$1; shift
    podman exec -w $SRC -e DATABASE_URL="$(db_url "$K")" -e APP_ENV=prod -e SHOPWARE_CACHE_ID="bench_$K" -e APP_URL=$APP_URL \
        -e SHOPWARE_HTTP_CACHE_ENABLED=0 -e PHP_INI_SCAN_DIR=/tmp/bench/conf.d "$WEB" php -d memory_limit=-1 bin/console "$@"
}

fresh_db() {
    case $1 in
        mariadb)
            podman exec "$MARIA" mariadb -uroot -proot -e 'drop database if exists bench_mariadb; create database bench_mariadb character set utf8mb4 collate utf8mb4_unicode_ci' ;;
        pg)
            podman exec "$PG" psql -U shopware -d postgres -q -c 'drop database if exists bench_pg with (force)' -c 'create database bench_pg'
            podman exec -i "$PG" psql -U shopware -d bench_pg -q -v ON_ERROR_STOP=1 < "$COMPAT" | tail -2
            # gap found by the benchmark: ORDER BY RAND() (demodata) is not translated, only this database gets the function
            podman exec "$PG" psql -U shopware -d bench_pg -q -c 'CREATE OR REPLACE FUNCTION rand() RETURNS double precision LANGUAGE sql VOLATILE AS $$ select random() $$' ;;
    esac
}

snapshot() {
    SHA=${1:-${SHA:-$(git -C "$ROOT/instance" rev-parse HEAD)}}
    echo "== snapshot of instance/ at $SHA in $WEB:$SRC"
    podman exec "$WEB" sh -c "rm -rf $SRC && mkdir -p $SRC/var $SRC/src /tmp/bench/conf.d && cd /var/www/html && cp -a bin config custom files public vendor composer.json composer.lock .env $SRC/ && rm -rf $SRC/public/media $SRC/public/thumbnail"
    git -C "$ROOT/instance" archive "$SHA" src | podman exec -i "$WEB" tar x -C $SRC
    # php.ini scan dir without Xdebug, opcache without timestamp checks
    podman exec "$WEB" sh -c 'rm -f /tmp/bench/conf.d/*; for f in /usr/local/etc/php/conf.d/*.ini; do case $f in *xdebug*) ;; *) cp $f /tmp/bench/conf.d/;; esac; done; echo "opcache.validate_timestamps=0" > /tmp/bench/conf.d/zz-bench.ini'
    echo "$SHA" > "$OUT/snapshot-sha.txt"
}

prepare() {
    mkdir -p "$OUT"
    : > "$OUT/install-times.txt"
    for K in mariadb pg; do
        for i in $(seq 1 "$RUNS"); do
            fresh_db "$K"
            S=$(now)
            console "$K" system:install --force --basic-setup --no-interaction > /tmp/bench-install-$K.log 2>&1 || { echo "install $K failed"; tail -20 /tmp/bench-install-$K.log; exit 1; }
            echo "install $K $i $(elapsed "$S" "$(now)")" | tee -a "$OUT/install-times.txt"
        done
        # the last install keeps its database for the demo data
        S=$(now)
        console "$K" framework:demodata --reset-defaults --products "${SIZE_PRODUCTS:-2000}" --categories 40 --manufacturers 20 --properties 10 \
            --customers 100 --orders 100 --reviews 100 --tags 20 --rules 5 --media 100 --no-interaction > /tmp/bench-demo-$K.log 2>&1 || { echo "demodata $K failed"; tr '\r' '\n' < /tmp/bench-demo-$K.log | grep -v '▓' | tail -12; exit 1; }
        echo "demodata $K 1 $(elapsed "$S" "$(now)")" | tee -a "$OUT/install-times.txt"
        for i in $(seq 1 "$RUNS"); do
            S=$(now)
            console "$K" dal:refresh:index --no-interaction > /tmp/bench-index-$K.log 2>&1 || { echo "index $K failed"; tail -10 /tmp/bench-index-$K.log; exit 1; }
            echo "index $K $i $(elapsed "$S" "$(now)")" | tee -a "$OUT/install-times.txt"
        done
        console "$K" cache:clear > /dev/null 2>&1
    done
}

# one php-fpm pool (static, 8 workers) plus one caddy per stack: name port database timing-file
start_stack() {
    NAME=$1; PORT=$2; K=$3; TIMING=${4:-}
    podman exec "$WEB" pkill -f "bench/$NAME/" 2>/dev/null || true
    sleep 1
    podman exec "$WEB" sh -c "mkdir -p /tmp/bench/$NAME
cat > /tmp/bench/$NAME/fpm.conf <<CONF
[global]
daemonize = no
error_log = /tmp/bench/$NAME/fpm.log
[www]
listen = /tmp/bench/$NAME/fpm.sock
clear_env = no
pm = static
pm.max_children = 8
catch_workers_output = yes
env[DATABASE_URL] = $(db_url "$K")
env[APP_ENV] = prod
env[APP_URL] = $APP_URL
env[SHOPWARE_CACHE_ID] = bench_$K
env[SHOPWARE_HTTP_CACHE_ENABLED] = 0
$([ -n "$TIMING" ] && echo "env[SHOPWARE_PG_TIMING] = $TIMING")
CONF
cat > /tmp/bench/$NAME/Caddyfile <<CONF
{
	admin off
	auto_https off
}
:$PORT {
	root * $SRC/public
	php_fastcgi unix//tmp/bench/$NAME/fpm.sock
	file_server
}
CONF"
    podman exec -d -e PHP_INI_SCAN_DIR=/tmp/bench/conf.d "$WEB" php-fpm -F -y /tmp/bench/$NAME/fpm.conf >/dev/null
    podman exec -d "$WEB" /usr/sbin/caddy run --config /tmp/bench/$NAME/Caddyfile --adapter caddyfile >/dev/null
    sleep 2
}

# the repeated index runs leave the PostgreSQL tables bloated (product: 442 MB heap for 3900 rows), one maintenance pass per database before measuring
maintenance() {
    echo "== size before: $(podman exec "$PG" psql -U shopware -d bench_pg -Atc "select pg_size_pretty(pg_database_size('bench_pg'))")"
    podman exec "$PG" psql -U shopware -d bench_pg -q -c 'VACUUM (FULL, ANALYZE)'
    echo "== size after VACUUM FULL, ANALYZE: $(podman exec "$PG" psql -U shopware -d bench_pg -Atc "select pg_size_pretty(pg_database_size('bench_pg'))")"
    podman exec "$MARIA" sh -c "mariadb -uroot -proot -N -e \"select concat('analyze table bench_mariadb.', table_name, ';') from information_schema.tables where table_schema='bench_mariadb' and table_type='BASE TABLE'\" | mariadb -uroot -proot > /dev/null"
    echo "== mariadb ANALYZE TABLE done"
}

stacks() {
    start_stack mariadb 8101 mariadb
    start_stack pg 8102 pg
    start_stack pgtime 8103 pg /tmp/bench/timing.jsonl
    podman exec "$WEB" sh -c 'for p in 8101 8102 8103; do curl -s -o /dev/null -w "$p %{http_code}\n" -H "Host: 127.0.0.1:8101" http://127.0.0.1:$p/; done'
}

run() {
    mkdir -p "$OUT"
    # same limits for both database containers (the web container shares the 8 CPUs of the VM with the load generator)
    for c in "$PG" "$MARIA"; do podman update --cpus=4 --memory=4g "$c" > /dev/null; done
    podman exec "$WEB" touch $SRC/install.lock
    podman cp "$ROOT/scripts/benchmark-load.py" "$WEB:/tmp/bench/benchmark-load.py"
    podman exec "$WEB" python3 /tmp/bench/benchmark-load.py --runs "$RUNS" --out /tmp/bench/results.json "$@"
    podman cp "$WEB:/tmp/bench/results.json" "$OUT/results.json"
    # podman update can not remove a limit again, 8 CPUs and 16 GB are what the VM has
    for c in "$PG" "$MARIA"; do podman update --cpus=8 --memory=16g "$c" > /dev/null; done
}

case ${1:-} in
    snapshot) mkdir -p "$OUT"; snapshot "${2:-}" ;;
    prepare) prepare; maintenance ;;
    maintenance) maintenance ;;
    stacks) stacks ;;
    run) shift; run "$@" ;;
    all) mkdir -p "$OUT"; snapshot "${2:-}"; prepare; maintenance; stacks; run ;;
    *) sed -n 2,10p "$0"; exit 1 ;;
esac
