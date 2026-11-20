#!/bin/sh
# Split of the DB server time per request into planning and execution with pg_stat_statements (docs/22).
# usage: scripts/planning-split.sh <stack> <scenario substring> [runs]
# needs: pg_stat_statements in bench_pg, pg_stat_statements.track = all, the stacks of scripts/benchmark.sh, DATASET=catalog
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
STACK=$1; SCEN=$2; RUNS=${3:-3}
PG=instance-postgres-1
q() { podman exec $PG psql -U shopware -d bench_pg -Atc "$1"; }
q "select pg_stat_statements_reset()" > /dev/null
podman cp "$ROOT/scripts/benchmark-load.py" instance-web-1:/tmp/bench/benchmark-load.py
podman exec instance-web-1 python3 /tmp/bench/benchmark-load.py --runs "$RUNS" --dataset catalog --out /tmp/bench/split.json --only "$SCEN" --stacks "$STACK" --no-throughput --no-probes > /tmp/split-run.log
podman cp instance-web-1:/tmp/bench/split.json /private/tmp/split.json
python3 - "$STACK" "$SCEN" "$RUNS" <<PY
import json,subprocess,statistics,sys
stack,scen,runs=sys.argv[1],sys.argv[2],int(sys.argv[3])
r=json.load(open('/tmp/split.json'))['scenarios']
name=[k for k in r if scen in k][0]; n=r[name]['n']; reqs=8+runs*n
lat=[x for run in r[name]['latency'][stack] for x in run]
out=subprocess.run(['podman','exec','$PG','psql','-U','shopware','-d','bench_pg','-Atc',
 "select coalesce(sum(total_plan_time),0), coalesce(sum(total_exec_time),0), coalesce(sum(calls),0), coalesce(sum(plans),0) from pg_stat_statements where dbid=(select oid from pg_database where datname='bench_pg') and query not like '%pg_stat_statements%' and query not like '%pg_prepared_statements%' and query not like 'DEALLOCATE%'"],capture_output=True,text=True).stdout.strip().split('|')
plan,ex,calls,plans=map(float,out)
print(json.dumps({'stack':stack,'scenario':name,'requests':reqs,'median_ms':round(statistics.median(lat)*1000,1),'plan_ms_per_request':round(plan/reqs,2),'exec_ms_per_request':round(ex/reqs,2),'statements_per_request':round(calls/reqs,1),'plans_per_request':round(plans/reqs,1)}))
PY
