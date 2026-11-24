#!/usr/bin/env bash
# R5 load run with the CPU seconds of the write database container (cgroup cpu.stat usage_usec, read on the host at the start and end mark of each level).
# usage: RS_DB=read_store_large scripts/read-store-load.sh mysql|postgresql <impl> [read-store:load options, default --concurrency=1,8,32 --duration=60s]
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/read-store-env.sh" "${1:-}"
IMPL="${2:?impl}"
shift 2
[ $# -eq 0 ] && set -- --concurrency=1,8,32 --duration=60s
start=0
spike_console_for "$IMPL" read-store:load --impl="$IMPL" --markers "$@" | while IFS= read -r line; do
  case "$line" in
    "MARK start"*) start=$(rs_cpu_usec) ;;
    "MARK end"*)   end=$(rs_cpu_usec); echo "  write database CPU: $(awk -v a="$start" -v b="$end" 'BEGIN{printf "%.1f", (b-a)/1e6}') s ($RS_DB_CONTAINER, ${line#MARK end })" ;;
    *) echo "$line" ;;
  esac
done
