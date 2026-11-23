#!/bin/bash
# R1 step 1b: capture the SQL of DAL v2 with shape=join, batch and join+batch; writes /tmp/r1/sql-<engine>-<shape>-<scenario>.jsonl
cd "$(dirname "$0")/.." || exit 1
export SPIKE_CACHE_BASE=/tmp/sw-orm-spike-r1
ENGINES=("$@"); [ ${#ENGINES[@]} -eq 0 ] && ENGINES=(mysql mariadb postgresql sqlite)
mkdir -p /tmp/r1
for ENG in "${ENGINES[@]}"; do
  . scripts/orm-spike-env.sh "$ENG"
  for SH in join batch join+batch; do
    for S in S1 S2 S3 S5; do
      podman exec $WEB rm -f /tmp/sql-$S.jsonl
      spike_console orm-spike:bench --impl=dalv2 --scenario=$S --iterations=1 --warmup=0 --option sqllog=/tmp/sql-$S.jsonl --option shape=$SH --output-dir=var/orm-spike-r1/cap/$ENG > /tmp/r1/cap-$ENG-$SH-$S.log 2>&1
      podman cp $WEB:/tmp/sql-$S.jsonl /tmp/r1/sql-$ENG-$SH-$S.jsonl
    done
  done
done
