#!/bin/sh
# Benchmark MariaDB, MySQL 8.4 and PostgreSQL (translator based), see docs/13-benchmark.md.
# usage: scripts/benchmark.sh snapshot [sha]   copy the PHP code of a commit into the web container (isolated from live edits)
#        scripts/benchmark.sh prepare          5 timed installs per database, demo data, 5 timed dal:refresh:index runs per database
#                                              DATASET=catalog: instead of framework:demodata upload the 6 templates of shopware-catalog-generator (CATGEN, /tmp/catgen) through the Admin API
#        scripts/benchmark.sh settings         equal memory settings for the three database servers (see docs/13-benchmark.md)
#        scripts/benchmark.sh pooler           start PgBouncer (transaction mode) in front of bench_pg
#        scripts/benchmark.sh stacks           start php-fpm + caddy per stack (see STACK_LIST), pg-timing is the PostgreSQL stack with timing probes
#        scripts/benchmark.sh run [--merge] [--only name] [--stacks a,b]   latency/throughput scenarios, alternating the stacks, then the translator pass
#        scripts/benchmark.sh all
# The lane databases (`shopware`) are never touched, the benchmark uses the databases bench_mariadb and bench_pg.
# environment: DATASET (demodata|catalog), CATGEN (checkout of shopwareLabs/shopware-catalog-generator), WEB (instance-web-1), PG (instance-postgres-1), MARIA (instance-database-1), MYSQL (instance-mysql-1), RUNS (5), SHA (HEAD of instance/), SIZE_PRODUCTS (2000)
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
WEB=${WEB:-instance-web-1}
PG=${PG:-instance-postgres-1}
MARIA=${MARIA:-instance-database-1}
MYSQL=${MYSQL:-instance-mysql-1}
BOUNCER=${BOUNCER:-instance-pgbouncer-1}
DBS=${DBS:-"mariadb mysql pg"}
RUNS=${RUNS:-5}
SRC=/tmp/bench-src
OUT=${OUT:-$ROOT/docs/benchmark-results}
APP_URL=http://127.0.0.1:8101
DATASET=${DATASET:-demodata}
CATGEN=${CATGEN:-/tmp/catgen}
BUN=${BUN:-$HOME/.bun/bin/bun}
TEMPLATES=${TEMPLATES:-"beauty drugstore electronics fashion garden music"}
RELAY=${RELAY:-bench-relay}

db_url() {
    case $1 in
        mariadb) echo 'mysql://root:root@database/bench_mariadb' ;;
        mysql) echo 'mysql://root:root@mysql/bench_mysql' ;;
        pg) echo 'pgsql://shopware:shopware@postgres:5432/bench_pg' ;;
        pgbouncer) echo 'pgsql://shopware:shopware@pgbouncer:6432/bench_pg' ;;
    esac
}

now() { python3 -c 'import time; print(time.time())'; }
elapsed() { python3 -c "print(round($2 - $1, 2))"; }

# console <mariadb|mysql|pg> args...: Symfony console in the snapshot, prod, no Xdebug
console() {
    K=$1; shift
    podman exec -w $SRC -e DATABASE_URL="$(db_url "$K")" -e APP_ENV=prod -e SHOPWARE_CACHE_ID="bench_$K" -e APP_URL=$APP_URL \
        -e SHOPWARE_HTTP_CACHE_ENABLED=0 -e PHP_INI_SCAN_DIR=/tmp/bench/conf.d "$WEB" php -d memory_limit=-1 bin/console "$@"
}

fresh_db() {
    case $1 in
        mariadb)
            podman exec "$MARIA" mariadb -uroot -proot -e 'drop database if exists bench_mariadb; create database bench_mariadb character set utf8mb4 collate utf8mb4_unicode_ci' ;;
        mysql)
            podman exec "$MYSQL" mysql -uroot -proot -e 'drop database if exists bench_mysql; create database bench_mysql character set utf8mb4 collate utf8mb4_unicode_ci' 2>/dev/null ;;
        pg)
            # mysql-compat.sql (functions, casts, collation) is loaded by system:install since wave 4
            podman exec "$PG" psql -U shopware -d postgres -q -c 'drop database if exists bench_pg with (force)' -c 'create database bench_pg' ;;
    esac
}

snapshot() {
    SHA=${1:-${SHA:-$(git -C "$ROOT/instance" rev-parse HEAD)}}
    echo "== snapshot of instance/ at $SHA in $WEB:$SRC"
    podman exec "$WEB" sh -c "rm -rf $SRC && mkdir -p $SRC/var $SRC/src /tmp/bench/conf.d && cd /var/www/html && cp -a bin config custom files public vendor composer.json composer.lock .env $SRC/ && rm -rf $SRC/public/media $SRC/public/thumbnail"
    git -C "$ROOT/instance" archive "$SHA" src | podman exec -i "$WEB" tar x -C $SRC
    # theme compilation (catalog data set) needs the scss vendor files that are not in git (~vendor/bootstrap)
    podman exec "$WEB" cp -a /var/www/html/src/Storefront/Resources/app/storefront/vendor $SRC/src/Storefront/Resources/app/storefront/
    # php.ini scan dir without Xdebug, opcache without timestamp checks
    podman exec "$WEB" sh -c 'rm -f /tmp/bench/conf.d/*; for f in /usr/local/etc/php/conf.d/*.ini; do case $f in *xdebug*) ;; *) cp $f /tmp/bench/conf.d/;; esac; done; echo "opcache.validate_timestamps=0" > /tmp/bench/conf.d/zz-bench.ini'
    echo "$SHA" > "$OUT/snapshot-sha.txt"
}

# db_sql <mariadb|mysql|pg> <sql>: one value per column, tab separated, no header
db_sql() {
    case $1 in
        mariadb) podman exec "$MARIA" mariadb -uroot -proot -N bench_mariadb -e "$2" ;;
        mysql) podman exec "$MYSQL" mysql -uroot -proot -N bench_mysql -e "$2" 2>/dev/null ;;
        pg) podman exec "$PG" psql -U shopware -d bench_pg -At -F "$(printf '\t')" -c "$2" ;;
    esac
}
db_size_mb() {
    case $1 in
        mariadb) db_sql mariadb "select round(sum(data_length+index_length)/1048576,1) from information_schema.tables where table_schema='bench_mariadb'" ;;
        mysql) db_sql mysql "select round(sum(data_length+index_length)/1048576,1) from information_schema.tables where table_schema='bench_mysql'" ;;
        pg) db_sql pg "select round(pg_database_size('bench_pg')/1048576.0,1)" ;;
    esac
}
catalog_counts() {
    db_sql "$1" "select (select count(*) from product where parent_id is null), (select count(*) from product where parent_id is not null), (select count(*) from category), (select count(*) from media), (select count(*) from product_media), (select count(*) from property_group_option), (select count(*) from sales_channel)"
}

# catalog_import <mariadb|mysql|pg>: integration, then the 6 templates of shopware-catalog-generator through the Admin API of a php-fpm stack on port 8101, reached from the host through a socat container on port 18101 (the sales channel domains are built from that URL: http://<template>.localhost:18101)
catalog_import() {
    K=$1
    LOG=$OUT/catalog-import.txt
    podman exec "$WEB" pkill -f 'bench/[a-z-]*/' 2>/dev/null || true
    start_stack upload 8101 "$K" "$K"
    podman exec "$WEB" touch $SRC/install.lock
    podman stop "$RELAY" > /dev/null 2>&1 || true
    podman container rm "$RELAY" > /dev/null 2>&1 || true
    podman run -d --name "$RELAY" --network instance_default -p 18101:8101 --entrypoint sh docker.io/library/alpine:latest -c 'apk add --no-cache socat >/dev/null 2>&1; exec socat tcp-listen:8101,fork,reuseaddr tcp:web:8101' > /dev/null
    sleep 6
    console "$K" integration:create bench-catalog --admin --access-key=SWIABENCHCATALOG0000000001 --secret-access-key=benchcatalogsecret0000000000000000000000001 --no-interaction > /tmp/bench-integration-$K.log 2>&1 || { echo "integration $K failed"; tail -5 /tmp/bench-integration-$K.log; exit 1; }
    echo "catalog $K integration created" | tee -a "$LOG"
    for T in $TEMPLATES; do
        S=$(now)
        RC=0
        (cd "$CATGEN" && SW_ENV_URL=http://localhost:18101 SW_CLIENT_ID=SWIABENCHCATALOG0000000001 SW_CLIENT_SECRET=benchcatalogsecret0000000000000000000000001 \
            AI_PROVIDER=pollinations AI_API_KEY=pk_unused_template_upload IMAGE_PROVIDER=none \
            "$BUN" run generate --name="$T") > "/tmp/bench-catalog-$K-$T.log" 2>&1 || RC=$?
        echo "catalog $K $T upload_seconds=$(elapsed "$S" "$(now)") exit=$RC" | tee -a "$LOG"
        if [ "$RC" != 0 ]; then
            { echo "---- generator failure $K $T (exit $RC), full log:"; tr '\r' '\n' < "/tmp/bench-catalog-$K-$T.log"; echo "---- end"; } >> "$OUT/catalog-errors-$K.txt"
            echo "catalog $K $T FAILED, log in catalog-errors-$K.txt" | tee -a "$LOG"
        fi
        grep -c -E '(^|[^0-9])(4|5)[0-9][0-9]([^0-9]|$)' "/tmp/bench-catalog-$K-$T.log" | sed "s/^/catalog $K $T log_lines_with_4xx_5xx=/" | tee -a "$LOG"
    done
    podman exec "$WEB" pkill -f 'bench/upload/' 2>/dev/null || true
    podman stop "$RELAY" > /dev/null 2>&1 || true
    podman container rm "$RELAY" > /dev/null 2>&1 || true
}

prepare() {
    mkdir -p "$OUT"
    : > "$OUT/install-times.txt"
    [ "$DATASET" = catalog ] && : > "$OUT/catalog-import.txt"
    for K in $DBS; do
        for i in $(seq 1 "$RUNS"); do
            fresh_db "$K"
            S=$(now)
            console "$K" system:install --force --basic-setup --no-interaction > /tmp/bench-install-$K.log 2>&1 || { echo "install $K failed"; tail -20 /tmp/bench-install-$K.log; exit 1; }
            echo "install $K $i $(elapsed "$S" "$(now)")" | tee -a "$OUT/install-times.txt"
        done
        # the last install keeps its database for the data set
        S=$(now)
        if [ "$DATASET" = catalog ]; then
            catalog_import "$K"
            echo "catalog $K 1 $(elapsed "$S" "$(now)")" | tee -a "$OUT/install-times.txt"
            echo "catalog $K counts after upload (products, variants, categories, media, product_media, options, sales_channels, size_mb): $(catalog_counts "$K" | tr '\t' ' ') $(db_size_mb "$K")" | tee -a "$OUT/catalog-import.txt"
        else
            console "$K" framework:demodata --reset-defaults --products "${SIZE_PRODUCTS:-2000}" --categories 40 --manufacturers 20 --properties 10 \
                --customers 100 --orders 100 --reviews 100 --tags 20 --rules 5 --media 100 --no-interaction > /tmp/bench-demo-$K.log 2>&1 || { echo "demodata $K failed"; tr '\r' '\n' < /tmp/bench-demo-$K.log | grep -v '▓' | tail -12; exit 1; }
            echo "demodata $K 1 $(elapsed "$S" "$(now)")" | tee -a "$OUT/install-times.txt"
        fi
        for i in $(seq 1 "$RUNS"); do
            S=$(now)
            console "$K" dal:refresh:index --no-interaction > /tmp/bench-index-$K.log 2>&1 || { echo "index $K failed"; tail -10 /tmp/bench-index-$K.log; exit 1; }
            echo "index $K $i $(elapsed "$S" "$(now)")" | tee -a "$OUT/install-times.txt"
        done
        console "$K" cache:clear > /dev/null 2>&1
    done
}

# one php-fpm pool (static, 8 workers) plus one caddy per stack: name port database-url-key cache-key timing-file persistent(0|1)
start_stack() {
    NAME=$1; PORT=$2; U=$3; K=$4; TIMING=${5:-}; PERSIST=${6:-0}
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
env[DATABASE_URL] = $(db_url "$U")
env[APP_ENV] = prod
env[APP_URL] = $APP_URL
env[SHOPWARE_CACHE_ID] = bench_$K
env[SHOPWARE_HTTP_CACHE_ENABLED] = 0
$([ -n "$TIMING" ] && echo "env[SHOPWARE_PG_TIMING] = $TIMING")
$([ "$PERSIST" -ge 1 ] && echo "env[DATABASE_PERSISTENT_CONNECTION] = 1")
$([ "$PERSIST" = 2 ] && echo "env[DATABASE_PLAN_CACHE] = 1")
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
    podman exec "$MYSQL" sh -c "mysql -uroot -proot -N -e \"select concat('analyze table bench_mysql.', table_name, ';') from information_schema.tables where table_schema='bench_mysql' and table_type='BASE TABLE'\" 2>/dev/null | mysql -uroot -proot > /dev/null 2>&1"
    echo "== mysql ANALYZE TABLE done"
}

# name:port:url-key:cache-key:timing-file:persistent
STACK_LIST="mariadb:8101:mariadb:mariadb mysql:8104:mysql:mysql pg:8102:pg:pg pgbouncer:8105:pgbouncer:pg mariadb-persistent:8106:mariadb:mariadb:-:1 mysql-persistent:8107:mysql:mysql:-:1 pg-persistent:8108:pg:pg:-:1 pg-plancache:8109:pg:pg:-:2 pg-timing:8103:pg:pg:/tmp/bench/timing.jsonl:0"
stacks() {
    PORTS=""
    for entry in $STACK_LIST; do
        IFS=: read -r NAME PORT U K T P <<EOF
$entry
EOF
        [ "$T" = "-" ] && T=""
        start_stack "$NAME" "$PORT" "$U" "$K" "$T" "${P:-0}"
        PORTS="$PORTS $PORT"
    done
    podman exec "$WEB" sh -c "for p in $PORTS; do curl -s -o /dev/null -w \"\$p %{http_code}\n\" -H 'Host: 127.0.0.1:8101' http://127.0.0.1:\$p/; done"
}
stop_stacks() { podman exec "$WEB" pkill -f 'bench/[a-z-]*/' 2>/dev/null || true; }
# equal settings of the three servers: 1 GiB cache, 16 MiB sort/work memory, no binary log, synchronous commit everywhere
settings() {
    podman exec "$PG" psql -U shopware -d postgres -q -c "ALTER SYSTEM SET shared_buffers='1GB'" -c "ALTER SYSTEM SET effective_cache_size='3GB'" -c "ALTER SYSTEM SET work_mem='16MB'" -c "ALTER SYSTEM SET maintenance_work_mem='256MB'"
    podman restart "$PG" > /dev/null
    for i in $(seq 1 30); do podman exec "$PG" pg_isready -U shopware -q && break; sleep 1; done
    podman exec "$PG" psql -U shopware -Atc "select name||'='||setting||coalesce(unit,'') from pg_settings where name in ('shared_buffers','effective_cache_size','work_mem','maintenance_work_mem')"
    podman exec "$MARIA" mariadb -uroot -proot -e "SET GLOBAL sort_buffer_size=16*1024*1024, tmp_table_size=16*1024*1024, max_heap_table_size=16*1024*1024"
}
pooler() {
    podman stop "$BOUNCER" > /dev/null 2>&1 || true
    podman container rm "$BOUNCER" > /dev/null 2>&1 || true
    podman run -d --name "$BOUNCER" --network instance_default --network-alias pgbouncer --entrypoint sh docker.io/edoburu/pgbouncer:latest -c '
mkdir -p /tmp/pgb
echo "\"shopware\" \"shopware\"" > /tmp/pgb/userlist.txt
cat > /tmp/pgb/pgbouncer.ini <<CONF
[databases]
bench_pg = host=postgres port=5432 dbname=bench_pg
[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
auth_type = scram-sha-256
auth_file = /tmp/pgb/userlist.txt
pool_mode = transaction
max_client_conn = 500
default_pool_size = 20
max_prepared_statements = 200
ignore_startup_parameters = extra_float_digits
CONF
exec pgbouncer /tmp/pgb/pgbouncer.ini' > /dev/null
    sleep 2
    podman logs "$BOUNCER" 2>&1 | tail -3
}
run() {
    mkdir -p "$OUT"
    # same limits for both database containers (the web container shares the 8 CPUs of the VM with the load generator)
    for c in "$PG" "$MARIA" "$MYSQL"; do podman update --cpus=4 --memory=4g "$c" > /dev/null; done
    podman exec "$WEB" touch $SRC/install.lock
    podman cp "$ROOT/scripts/benchmark-load.py" "$WEB:/tmp/bench/benchmark-load.py"
    podman exec "$WEB" python3 /tmp/bench/benchmark-load.py --runs "$RUNS" --dataset "$DATASET" --out /tmp/bench/results.json "$@"
    podman cp "$WEB:/tmp/bench/results.json" "$OUT/results.json"
    # podman update can not remove a limit again, 8 CPUs and 16 GB are what the VM has
    for c in "$PG" "$MARIA" "$MYSQL"; do podman update --cpus=8 --memory=16g "$c" > /dev/null; done
}

case ${1:-} in
    snapshot) mkdir -p "$OUT"; snapshot "${2:-}" ;;
    prepare) prepare; maintenance ;;
    catalog) mkdir -p "$OUT"; catalog_import "${2:?database}" ;;
    settings) settings ;;
    pooler) pooler ;;
    stop-stacks) stop_stacks ;;
    maintenance) maintenance ;;
    stacks) stacks ;;
    run) shift; run "$@" ;;
    all) mkdir -p "$OUT"; snapshot "${2:-}"; settings; pooler; prepare; maintenance; stacks; run ;;
    *) sed -n 2,10p "$0"; exit 1 ;;
esac
