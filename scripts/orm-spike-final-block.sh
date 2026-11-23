#!/bin/bash
# Final timing block of wave 8 (handoff E1): unattended, all engines, all configs.
# usage: scripts/orm-spike-final-block.sh [engines...]   (default: mysql mariadb postgresql sqlite)
# Log: /tmp/e1-run/progress.log, per call logs in /tmp/e1-run/calls/, results copied to /tmp/e1-results/.
# Restarts the stopped lanes and removes the lock on exit, also on failure.
cd "$(dirname "$0")/.." || exit 1
LOCK=/tmp/wave8-timing.lock
LIST=/tmp/wave8-stopped-containers.txt
RUN=/tmp/e1-run
RES=/tmp/e1-results
OUT=var/orm-spike-e1
export SPIKE_CACHE_BASE=/tmp/sw-orm-spike-e1
ENGINES=("$@"); [ ${#ENGINES[@]} -eq 0 ] && ENGINES=(mysql mariadb postgresql sqlite)
mkdir -p $RUN/calls; : > $RUN/progress.log; rm -f $RUN/cold.txt
log() { echo "$(date +%H:%M:%S) $*" >> $RUN/progress.log; }
load() { uptime | sed 's/.*averages: //'; }

if [ -e $LOCK ] && [ "$(cat $LOCK)" != "E1" ]; then log "lock held by $(cat $LOCK), abort"; exit 1; fi
echo E1 > $LOCK
LOCKED=1

cleanup() {
  log "cleanup start"
  podman exec instance-web-1 sh -c "cd /var/www/html/var && tar cf - orm-spike-e1" 2>/dev/null | { rm -rf $RES; mkdir -p $RES; tar xf - -C $RES; }
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
"dbal|"
"doctrine|--option mode=idiomatic"
"doctrine|--option mode=optimized"
"cycle|--option variant=idiomatic"
"cycle|--option variant=optimized"
"dalv2|"
"dalv2|--option count=window --option agg=stats --option write=key+upd"
"dalv2|--option count=window --option agg=stats --option write=key+upd --option proj=1"
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
  # cold cache (cache:clear without warm-up, plain cache:clear warms the cache again): clear, then one timed S2 call (wall time includes podman exec and kernel boot), then a warm call for reference
  for impl in dal dbal doctrine cycle dalv2; do
   for rep in 1 2 3 4 5; do
    spike_console cache:clear --no-warmup > /dev/null 2>&1
    t0=$(perl -MTime::HiRes=time -e 'printf "%.3f", time')
    spike_console orm-spike:bench --impl=$impl --scenario=S2 --iterations=1 --warmup=0 --output-dir=$OUT/cold/$ENG/$impl > $RUN/calls/$ENG-$impl-cold.log 2>&1
    rc=$?
    t1=$(perl -MTime::HiRes=time -e 'printf "%.3f", time')
    spike_console orm-spike:bench --impl=$impl --scenario=S2 --iterations=1 --warmup=0 --output-dir=$OUT/warm/$ENG/$impl > $RUN/calls/$ENG-$impl-warm.log 2>&1
    t2=$(perl -MTime::HiRes=time -e 'printf "%.3f", time')
    echo "$ENG $impl $rc $(echo "$t1 - $t0" | bc) $(echo "$t2 - $t1" | bc)" >> $RUN/cold.txt
    log "$ENG cold $impl rc=$rc"
   done
  done
  # leave a warm cache behind for the next steps
done
echo "load_end=$(load)" >> $RUN/conditions.txt
log "ALL DONE"
