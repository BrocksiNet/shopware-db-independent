#!/usr/bin/env bash
# Wave 9 handoff P baseline timing block: dal (O0), dalv2 (O0b) and dal-opensearch (O1) on MySQL 8.4.
# S1 to S3, R3b and R4 on orm_spike and read_store_large (5 warm-up, 50 measured iterations), R5 on read_store_large.
# Takes the lock /tmp/wave9-timing.lock (handoff letter P), stops the containers of the other sw-dev lanes and starts exactly those again at the end, also on failure.
# usage: scripts/read-store-baseline.sh   (log: /tmp/read-store-baseline-<time>.log)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
LOCK=/tmp/wave9-timing.lock
STOPPED=/tmp/wave9-stopped-containers.txt
LOG="/tmp/read-store-baseline-$(date +%Y%m%d-%H%M%S).log"
if [ -e "$LOCK" ] && [ "$(cat "$LOCK")" != P ]; then echo "lock held by $(cat "$LOCK")"; exit 1; fi
echo P > "$LOCK"
restore() {
  if [ -s "$STOPPED" ]; then xargs podman start < "$STOPPED" > /dev/null; fi
  rm -f "$STOPPED" "$LOCK"
  echo "other lanes started again, lock removed" | tee -a "$LOG"
}
trap restore EXIT
podman ps --format '{{.Names}}' | grep -v '^instance-' > "$STOPPED" || true
xargs podman stop < "$STOPPED" > /dev/null
sleep 60
{ echo "other lanes stopped: yes ($(wc -l < "$STOPPED" | tr -d ' ') containers)"; uptime; } | tee -a "$LOG"

for ds in orm_spike read_store_large; do
  export RS_DB=$ds
  . "$HERE/read-store-env.sh" mysql
  for impl in dal dalv2 dal-opensearch; do
    echo "=== $ds $impl: S1 S2 S3 R3b R4 ===" | tee -a "$LOG"
    uptime | tee -a "$LOG"
    spike_console_for $impl orm-spike:bench --impl=$impl --scenario=S1,S2,S3,R3b,R4 --iterations=50 --warmup=5 2>&1 | tee -a "$LOG"
    uptime | tee -a "$LOG"
  done
done

export RS_DB=read_store_large
. "$HERE/read-store-env.sh" mysql
for impl in dal dalv2 dal-opensearch; do
  echo "=== read_store_large $impl: R5 ===" | tee -a "$LOG"
  uptime | tee -a "$LOG"
  "$HERE/read-store-load.sh" mysql $impl --concurrency=1,8,32 --duration=60s 2>&1 | tee -a "$LOG"
  uptime | tee -a "$LOG"
done
echo "log: $LOG"
