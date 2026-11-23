#!/bin/bash
# R1 step 2: plan of the main read statement per engine, shape and scenario; needs scripts/orm-spike-r1-capture*.sh run before.
# writes /tmp/r1/plans.jsonl and the raw plans to /tmp/r1plan/ inside the web container (copied to /tmp/r1/plan/)
cd "$(dirname "$0")/.." || exit 1
export SPIKE_CACHE_BASE=/tmp/sw-orm-spike-r1
RUNS=${RUNS:-7}
: > /tmp/r1/plans.jsonl
mkdir -p /tmp/r1/plan
for ENG in mysql mariadb postgresql sqlite; do
  . scripts/orm-spike-env.sh "$ENG"
  cp scripts/orm-spike-r1-plans.php instance/orm-spike-r1-plans.php
  podman exec $WEB mkdir -p /tmp/r1 /tmp/r1plan
  for SH in none join batch join+batch; do
    for S in S1 S2 S3 S5; do
      F=/tmp/r1/sql-$ENG-$S.jsonl; [ $SH != none ] && F=/tmp/r1/sql-$ENG-$SH-$S.jsonl
      podman cp "$F" "$WEB:$F"
      OUT=$(podman exec -e DATABASE_URL=$SPIKE_URL $WEB php -d display_errors=0 orm-spike-r1-plans.php $ENG "$F" "/tmp/r1plan/$ENG-$SH-$S.txt" $RUNS 2>&1 | tail -1)
      echo "{\"shape\":\"$SH\",\"scenario\":\"$S\",\"plan\":$OUT}" >> /tmp/r1/plans.jsonl
      podman cp "$WEB:/tmp/r1plan/$ENG-$SH-$S.txt" "/tmp/r1/plan/$ENG-$SH-$S.txt" 2>/dev/null
    done
  done
done
rm -f instance/orm-spike-r1-plans.php
