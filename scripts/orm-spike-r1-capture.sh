#!/bin/bash
# R1 step 1: capture the exact SQL with parameters the DAL (DAL v2 untouched) sends for S1, S2, S3, S5, per engine.
# usage: scripts/orm-spike-r1-capture.sh [engines...]; writes /tmp/r1/sql-<engine>-<scenario>.jsonl
cd "$(dirname "$0")/.." || exit 1
export SPIKE_CACHE_BASE=/tmp/sw-orm-spike-r1
ENGINES=("$@"); [ ${#ENGINES[@]} -eq 0 ] && ENGINES=(mysql mariadb postgresql sqlite)
mkdir -p /tmp/r1
for ENG in "${ENGINES[@]}"; do
  . scripts/orm-spike-env.sh "$ENG"
  for S in S1 S2 S3 S5; do
    podman exec $WEB rm -f /tmp/sql-$S.jsonl
    spike_console orm-spike:bench --impl=dalv2 --scenario=$S --iterations=1 --warmup=0 --option sqllog=/tmp/sql-$S.jsonl --output-dir=var/orm-spike-r1/cap/$ENG > /tmp/r1/cap-$ENG-$S.log 2>&1
    podman cp $WEB:/tmp/sql-$S.jsonl /tmp/r1/sql-$ENG-$S.jsonl
  done
done
