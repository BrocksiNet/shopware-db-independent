#!/usr/bin/env bash
# Install Shopware from scratch on one database, load demo data, index, smoke test, print the time of every step.
# usage: scripts/switch-db.sh mysql|mariadb|postgresql|sqlite
# sqlite installs into the file var/switch/shopware_switch.sqlite of instance/ (inside instance-web-1, outside the lane database), the file is deleted first.
# Writes tab separated results to docs/switch-results/<db>.tsv (run id, step, result, seconds, detail).
# Never touches the lane database `shopware`: the target is always the separate database `shopware_switch`,
# DATABASE_URL is passed with `podman exec -e`, the lane .env stays untouched.
# The smoke test runs against a second web process (`php -S`) inside instance-web-1 with its own port and APP_CACHE_DIR.
set -u
DB="${1:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"
WEB=instance-web-1
case "$DB" in
  mysql)      URL='mysql://root:root@mysql:3306/shopware_switch'; PORT=8092
              SQL() { podman exec instance-mysql-1 mysql -uroot -proot -N -B shopware_switch -e "$1" 2>/dev/null; } ;;
  mariadb)    URL='mysql://root:root@database:3306/shopware_switch'; PORT=8093
              SQL() { podman exec instance-database-1 mariadb -uroot -proot -N -B shopware_switch -e "$1" 2>/dev/null; } ;;
  postgresql) URL='pgsql://shopware:shopware@postgres:5432/shopware_switch'; PORT=8094
              SQL() { podman exec instance-postgres-1 psql -U shopware -d shopware_switch -At -c "$1" 2>/dev/null; } ;;
  sqlite)     URL='sqlite:////var/www/html/var/switch/shopware_switch.sqlite'; PORT=8095
              podman exec $WEB sh -c 'mkdir -p var/switch && rm -f var/switch/shopware_switch.sqlite*' >/dev/null 2>&1
              SQL() { podman exec $WEB php -r '$p = new PDO("sqlite:/var/www/html/var/switch/shopware_switch.sqlite"); foreach ($p->query($argv[1]) as $r) { echo implode("\t", array_filter($r, "is_int", ARRAY_FILTER_USE_KEY)), "\n"; }' "$1" 2>/dev/null; } ;;
  *) echo "usage: $0 mysql|mariadb|postgresql|sqlite"; exit 2 ;;
esac
APP_URL="http://localhost:$PORT"
CACHE="/tmp/sw-switch-$DB"
RESULTS="$HERE/../docs/switch-results/$DB.tsv"
RUN="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$(dirname "$RESULTS")"
ENVS=(-e APP_ENV=prod -e "APP_CACHE_DIR=$CACHE" -e "APP_URL=$APP_URL" -e "DATABASE_URL=$URL" -e SHOPWARE_HTTP_CACHE_ENABLED=0)
FAILS=0
now() { python3 -c 'import time;print(time.time())'; }
record() { # step result seconds detail
  printf '%-28s %-5s %8.1fs  %s\n' "$1" "$2" "$3" "$4"
  printf '%s\t%s\t%s\t%.1f\t%s\n' "$RUN" "$1" "$2" "$3" "$4" >> "$RESULTS"
  [ "$2" = PASS ] || FAILS=$((FAILS + 1))
}
run() { # step command...   (output goes to /tmp/switch-<db>-<step>.log)
  local step="$1"; shift
  local log="/tmp/switch-$DB-${step// /-}.log" t0 t1 rc
  t0=$(now); "$@" > "$log" 2>&1; rc=$?; t1=$(now)
  if [ $rc -eq 0 ]; then record "$step" PASS "$(python3 -c "print($t1-$t0)")" ""
  else record "$step" FAIL "$(python3 -c "print($t1-$t0)")" "exit $rc, see $log: $(grep -iE 'exception|error' "$log" | head -1 | cut -c1-160)"; fi
  return $rc
}
console() { podman exec "${ENVS[@]}" $WEB bin/console "$@"; }
stop_web() { podman exec $WEB pkill -f "S 127.0.0.1:$PORT" >/dev/null 2>&1 || true; }
trap stop_web EXIT

echo "== $DB ($URL, run $RUN)"
stop_web
podman exec $WEB rm -rf "$CACHE"

T_ALL=$(now)
run "system:install" console system:install --basic-setup --drop-database --create-database --force --no-interaction || exit 1
run "framework:demodata" console framework:demodata --reset-defaults --products 200 --categories 20 --manufacturers 10 --properties 10 --customers 10 --orders 10 --tags 20 --rules 10 --promotions 3 --newsletter-recipients 5 --reviews 10 --media 100 --no-interaction || exit 1
run "dal:refresh:index" console dal:refresh:index --no-interaction || exit 1
run "cache:clear" console cache:clear --no-interaction

t0=$(now)
podman exec -d "${ENVS[@]}" -e PHP_CLI_SERVER_WORKERS=4 $WEB php -d variables_order=EGPCS -S "127.0.0.1:$PORT" -t public public/index.php >/dev/null
for _ in $(seq 1 30); do
  podman exec $WEB curl -s -o /dev/null "$APP_URL/store-api/context" && break; sleep 1
done
record "web process start" PASS "$(python3 -c "print($(now)-$t0)")" "php -S 127.0.0.1:$PORT"

KEY="$(SQL "select sc.access_key from sales_channel sc join sales_channel_domain d on d.sales_channel_id = sc.id where d.url = '$APP_URL'" | head -1)"
if [ -z "$KEY" ]; then record "sales channel key" FAIL 0 "no sales channel with domain $APP_URL"; exit 1; fi
t0=$(now)
podman exec -i $WEB python3 - "$APP_URL" "$KEY" < "$HERE/switch-smoke.py" > "/tmp/switch-$DB-smoke.log" 2>&1
while IFS='|' read -r tag name res ms detail; do
  [ "$tag" = STEP ] || continue
  record "smoke: $name" "$res" "$(python3 -c "print($ms/1000)")" "$detail"
done < "/tmp/switch-$DB-smoke.log"
grep -qc STEP "/tmp/switch-$DB-smoke.log" || record "smoke" FAIL 0 "no output, see /tmp/switch-$DB-smoke.log"
record "total (install to smoke)" "$([ $FAILS -eq 0 ] && echo PASS || echo FAIL)" "$(python3 -c "print($(now)-$T_ALL)")" "$FAILS failed steps"
exit $((FAILS > 0))
