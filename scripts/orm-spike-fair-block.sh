#!/bin/bash
# S4 timing block of docs/35: bare and full write variants next to dal and dalv2, all engines, doc 34 protocol.
# usage: scripts/orm-spike-fair-block.sh [engines...]   (default: mysql mariadb postgresql sqlite)
# Log: /tmp/fair-run/progress.log, call logs in /tmp/fair-run/calls/, results copied to /tmp/fair-results/ (TAG=-2 appends a suffix to all three).
# Stops the other lanes like handoff E1 and restarts them plus removes the lock on exit, also on failure.
cd "$(dirname "$0")/.." || exit 1
LOCK=/tmp/wave8-timing.lock
LIST=/tmp/wave8-stopped-containers.txt
TAG=${TAG:-}   # TAG=-2 for a repetition, results then go to /tmp/fair-results-2
RUN=/tmp/fair-run$TAG
RES=/tmp/fair-results$TAG
OUT=var/orm-spike-fair-bench$TAG
export SPIKE_CACHE_BASE=/tmp/sw-orm-spike-fair
ENGINES=("$@"); [ ${#ENGINES[@]} -eq 0 ] && ENGINES=(mysql mariadb postgresql sqlite)
mkdir -p $RUN/calls; : > $RUN/progress.log
log() { echo "$(date +%H:%M:%S) $*" >> $RUN/progress.log; }
load() { uptime | sed 's/.*averages: //'; }

if [ -e $LOCK ] && [ "$(cat $LOCK)" != "FAIR" ]; then log "lock held by $(cat $LOCK), abort"; exit 1; fi
echo FAIR > $LOCK

cleanup() {
  log "cleanup start"
  podman exec instance-web-1 sh -c "cd /var/www/html/var && tar cf - orm-spike-fair-bench$TAG" 2>/dev/null | { rm -rf $RES; mkdir -p $RES; tar xf - -C $RES; }
  if [ -s $LIST ]; then
    xargs podman start < $LIST >/dev/null 2>&1
    running=$(podman ps --format '{{.Names}}' | grep -v '^instance-' | wc -l)
    want=$(wc -l < $LIST)
    log "lanes running $running of $want"
    [ "$running" -ge "$want" ] && rm -f $LIST
  fi
  rm -f $LOCK
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
"dalv2|--option count=window --option agg=stats --option write=key+upd"
"dalv2|--option count=window --option agg=stats --option write=key+upd --option proj=1"
"dbal|"
"dbal|--option full=1"
"doctrine|--option mode=idiomatic"
"doctrine|--option mode=idiomatic --option full=1"
"doctrine|--option mode=optimized"
"doctrine|--option mode=optimized --option full=1"
"cycle|--option variant=idiomatic"
"cycle|--option variant=idiomatic --option full=1"
"cycle|--option variant=optimized"
"cycle|--option variant=optimized --option full=1"
)

for ENG in "${ENGINES[@]}"; do
  . scripts/orm-spike-env.sh "$ENG"
  log "== engine $ENG"
  spike_console cache:clear > $RUN/calls/$ENG-cacheclear.log 2>&1
  echo "load_$ENG=$(load)" >> $RUN/conditions.txt
  i=0
  for c in "${configs[@]}"; do
    i=$((i+1)); impl=${c%%|*}; opts=${c#*|}
    if [ "$impl" != dal ]; then
      spike_console orm-spike:bench --impl=$impl --scenario=S4 --iterations=1 --warmup=0 --verify $opts --output-dir=$OUT/verify/$ENG/c$i > $RUN/calls/$ENG-c$i-verify.log 2>&1
      log "$ENG c$i $impl $opts verify rc=$?"
    fi
  done
  i=0
  for c in "${configs[@]}"; do
    i=$((i+1)); impl=${c%%|*}; opts=${c#*|}
    s=$(date +%s)
    spike_console orm-spike:bench --impl=$impl --scenario=S4 --iterations=50 --warmup=5 $opts --output-dir=$OUT/bench/$ENG/c$i > $RUN/calls/$ENG-c$i-bench.log 2>&1
    log "$ENG c$i $impl $opts bench rc=$? $(( $(date +%s) - s ))s load $(load)"
  done
done
echo "load_end=$(load)" >> $RUN/conditions.txt
log "ALL DONE"
