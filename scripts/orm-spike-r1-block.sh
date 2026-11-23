#!/bin/bash
# Timing block of wave 8 (handoff R1, lock letter R): DAL v2 read shape: unattended, all engines, all configs.
# usage: scripts/orm-spike-r1-block.sh [engines...]   (default: mysql mariadb postgresql sqlite)
# Log: /tmp/r1-run/progress.log, per call logs in /tmp/r1-run/calls/, results copied to /tmp/r1-results/.
# Restarts the stopped lanes and removes the lock on exit, also on failure.
cd "$(dirname "$0")/.." || exit 1
LOCK=/tmp/wave8-timing.lock
LIST=/tmp/wave8-stopped-containers.txt
RUN=/tmp/r1-run
RES=/tmp/r1-results
OUT=var/orm-spike-r1
export SPIKE_CACHE_BASE=/tmp/sw-orm-spike-r1
ENGINES=("$@"); [ ${#ENGINES[@]} -eq 0 ] && ENGINES=(mysql mariadb postgresql sqlite)
mkdir -p $RUN/calls; : > $RUN/progress.log; rm -f $RUN/cold.txt
log() { echo "$(date +%H:%M:%S) $*" >> $RUN/progress.log; }
load() { uptime | sed 's/.*averages: //'; }

if [ -e $LOCK ] && [ "$(cat $LOCK)" != "R" ]; then log "lock held by $(cat $LOCK), abort"; exit 1; fi
echo R > $LOCK
LOCKED=1

cleanup() {
  log "cleanup start"
  podman exec instance-web-1 sh -c "cd /var/www/html/var && tar cf - orm-spike-r1" 2>/dev/null | { rm -rf $RES; mkdir -p $RES; tar xf - -C $RES; }
  if [ -s $LIST ]; then
    xargs podman start < $LIST >/dev/null 2>&1
    running=$(podman ps --format '{{.Names}}' | grep -v '^instance-' | sort > $RUN/running.txt; wc -l < $RUN/running.txt)
    want=$(wc -l < $LIST)
    log "lanes running $running of $want"
    [ "$running" -ge "$want" ] && rm -f $LIST
  fi
  [ -n "$LOCKED" ] && rm -f $LOCK
  log "cleanup done (lock removed, list $( [ -e $LIST ] && echo KEPT || echo removed ))"
}
trap cleanup EXIT

podman ps --format '{{.Names}}' | grep -v '^instance-' > $LIST && xargs podman stop < $LIST >/dev/null 2>&1
log "stopped $(wc -l < $LIST) lanes; load $(load)"
echo "lanes_stopped=$(wc -l < $LIST)" > $RUN/conditions.txt
echo "load_start=$(load)" >> $RUN/conditions.txt

configs=(
"dal|"
"dalv2|"
"dalv2|--option shape=join"
"dalv2|--option shape=batch"
"dalv2|--option shape=join+batch"
"dalv2|--option count=window --option agg=stats --option write=key+upd --option proj=1"
"dalv2|--option shape=join+batch --option count=window --option agg=stats --option write=key+upd --option proj=1"
)

for ENG in "${ENGINES[@]}"; do
  . scripts/orm-spike-env.sh "$ENG"
  log "== engine $ENG"
  spike_console cache:clear > $RUN/calls/$ENG-cacheclear.log 2>&1
  log "$ENG cache:clear rc=$? load $(load)"
  echo "load_$ENG=$(load)" >> $RUN/conditions.txt
  # COLD_ONLY=1 skips verify and bench (rerun of the cold part only)
  if [ -z "$COLD_ONLY" ]; then
  # verify once per config
  i=0
  for c in "${configs[@]}"; do
    i=$((i+1)); impl=${c%%|*}; opts=${c#*|}
    if [ "$impl" != dal ]; then
      spike_console orm-spike:bench --impl=$impl --scenario=all --iterations=1 --warmup=0 --verify $opts --output-dir=$OUT/verify/$ENG/c$i > $RUN/calls/$ENG-c$i-verify.log 2>&1
      log "$ENG c$i $impl $opts verify rc=$?"
    fi
  done
  # bench
  i=0
  for c in "${configs[@]}"; do
    i=$((i+1)); impl=${c%%|*}; opts=${c#*|}
    s=$(date +%s)
    spike_console orm-spike:bench --impl=$impl --scenario=all --iterations=50 --warmup=5 $opts --output-dir=$OUT/bench/$ENG/c$i > $RUN/calls/$ENG-c$i-bench.log 2>&1
    log "$ENG c$i $impl $opts bench rc=$? $(( $(date +%s) - s ))s load $(load)"
  done
  fi
  # leave a warm cache behind for the next steps
done
echo "load_end=$(load)" >> $RUN/conditions.txt
log "ALL DONE"
