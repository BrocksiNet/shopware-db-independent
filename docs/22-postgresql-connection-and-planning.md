# 22 PostgreSQL connection and planning cost (wave 6, handoff A)

Setting: catalog data set (docs/20), PostgreSQL 18, MariaDB 10.11, MySQL 8.4 in containers, php-fpm pools with 8 workers per stack (`scripts/benchmark.sh stacks`). The three database containers ran at 4 CPU / 4 GiB while measuring. The host was shared with about 40 unrelated containers, so the load was between 3 and 18 during the paired run; every block below carries its load in the raw log. Numbers from single blocks are noisy (identical blocks differ by up to 30 %), the planning milliseconds from `pg_stat_statements` are much steadier than the request medians.

Raw data: `benchmark-results/wave6-A-baseline.json` (first session), `wave6-A2-plancache-paired.log`, `wave6-A2-equality.txt`, `wave6-A2-engine-baseline.log`.

## Split of the request (what costs time)

Median ms per request, first session (`wave6-A-baseline.json`, 3 runs, noisy), PostgreSQL new connection per request / PgBouncer transaction mode / persistent connection, and MariaDB persistent:

| Scenario | PG new | PgBouncer | PG persistent | MariaDB persistent |
|---|---|---|---|---|
| home | 176.9 | 150.6 | 134.2 | 96.1 |
| listing | 116.1 | 92.5 | 86.5 | 61.7 |
| search | 138.9 | 122.1 | 112.0 | 80.2 |
| detail | 203.3 | 195.5 | 175.5 | 109.2 |

Connect and backend warm-up (`scripts/connect-microbench.php`, 100 connections each, run inside the web container against `bench_pg`, load 5):

| Step | new connection | persistent |
|---|---|---|
| PDO connect | 5.61 ms | 0.01 ms |
| `SET NAMES`, `SET TIME ZONE` | 0.23 ms | 0.14 ms |
| `select 1` | 0.40 ms | 0.23 ms |
| first `= ... collate ci` compare | 8.80 ms | 0.27 ms |
| second `collate ci` compare | 0.36 ms | 0.26 ms |

The ICU collator costs once per backend, not per statement (first compare 8.8 ms, second 0.36 ms, and 0.27 ms on a persistent backend). A new connection per request therefore pays about 5.6 + 8.4 = 14 ms for connect and ICU alone before the cold catalog caches. Persistent connections or a pooler remove it.

Planning (`pg_stat_statements` with `track_planning`, `scripts/planning-split.sh`), persistent connection without plan cache, mean of the two blocks of the paired run, ms per request: planning 17.5 (home), 11.3 (listing), 15.9 (search), 20.6 (detail) in the generic-mode half, and 24.9, 17.9, 21.3, 21.4 in the auto-mode half. Every DAL statement is planned again, 74 to 85 plans per request (`plans_per_request` 73.9, 64.2, 65.1, 85.4). Reason: DBAL's pdo_pgsql driver sets `PGSQL_ATTR_DISABLE_PREPARES`, so each statement goes out as an unnamed parse/bind/execute.

## Plan cache (before / after)

Implementation (`instance/`, commit `ccda386febb`): `PostgreSQL/PlanCache{Middleware,Connection,Statement}.php`, switched on with `DATABASE_PLAN_CACHE=1` and only active together with `DATABASE_PERSISTENT_CONNECTION=1`. It runs SQL-level `PREPARE name AS ...` once per backend and SQL text and `EXECUTE name(...)` afterwards; the adapter suite is green on PostgreSQL and MySQL (208 tests, MySQL unchanged because the middleware is PostgreSQL only).

Paired run, `pg-persistent` and `pg-plancache` interleaved, 2 blocks per stack and scenario, 10 runs per block (`wave6-A2-plancache-paired.log`, loads in the log). Median ms, planning ms per request, plans per request (mean of the 2 blocks):

Generic mode (`ALTER DATABASE bench_pg SET plan_cache_mode = force_generic_plan`, load 3 to 14):

| Scenario | persistent ms | plan cache ms | persistent plan ms | plan cache plan ms | plans/req (persistent -> cache) |
|---|---|---|---|---|---|
| home | 146.5 | 116.3 | 17.5 | 0.8 | 73.9 -> 8.6 |
| listing | 88.0 | 71.3 | 11.3 | 0.75 | 64.2 -> 7.3 |
| search | 107.1 | 91.6 | 15.9 | 5.8 | 65.1 -> 19.7 |
| detail | 134.8 | 125.1 | 20.6 | 7.35 | 85.4 -> 27.8 |

Auto mode (default `plan_cache_mode`, load 6 to 18; block 1 of the home scenario contained the warm-up of all 8 backends, so the second block is the steady one):

| Scenario | persistent ms (block 1 / 2) | plan cache ms (block 1 / 2) | persistent plan ms | plan cache plan ms | plans/req |
|---|---|---|---|---|---|
| home | 201.2 / 147.1 | 255.9 / 140.2 | 24.9 | 6.1 | 73.9 -> 20.7 |
| listing | 174.2 / 90.7 | 117.6 / 75.9 | 17.9 | 3.2 | 64.2 -> 13.5 |
| search | 111.3 / 134.8 | 109.1 / 112.9 | 21.3 | 13.3 | 65.1 -> 31.2 |
| detail | 128.8 / 141.7 | 131.4 / 120.5 | 21.4 | 13.3 | 85.4 -> 47.1 |

Reading: the plan cache removes 63-95 % of the planning time in generic mode and 38-82 % in auto mode. In auto mode the heaviest statements keep custom plans (first session: 362 of 408 statements of the detail request planned again), so generic mode leaves much less planning. Request medians fall by 9-29 ms in generic mode (home -30, listing -17, search -16, detail -10). Execution time per request does not change (for example listing 3.2 ms vs 3.0 ms).

Against MariaDB persistent from the first session (different time, so only an indication): the ratio of PG plan cache (generic) to MariaDB persistent is about 1.21 (home), 1.16 (listing), 1.14 (search), 1.15 (detail); PG persistent without plan cache is 1.52, 1.43, 1.34, 1.23 on the same basis.

What stays in planning with the cache in generic mode: 0.4-1.1 ms (home, listing), about 6 ms (search), about 7.4 ms (detail), all per request. I did not investigate why search and detail keep more plans (27.8 plans per detail request).

Limits found:

- Behind PgBouncer transaction mode SQL-level `PREPARE` does not work; the plan cache needs persistent connections to PostgreSQL.
- For the `EXECUTE` parameters the cache uses per-statement `ATTR_EMULATE_PREPARES` and binds bools as '1'/'0'.

## Result equality and `force_generic_plan`

- `scripts/compare-responses.py` (run in the web container, 12 requests per scenario) compares the response bodies of `pg-persistent` and `pg-plancache` after normalizing csrf tokens, long ids and random numeric element ids (`filter-manufacturer-1089875894`; the first run showed those differ even between two requests to the same stack, so the normalization removes them). Result in auto mode and in `force_generic_plan` mode: same 12, different 0 for all 4 scenarios (`wave6-A2-equality.txt`).
- Detail statement (19 joins, 11 parameters, `EXPLAIN (ANALYZE, SUMMARY, COSTS OFF, TIMING OFF) EXECUTE`): the plan tree is identical for custom and generic plan except that parameters show as `$n` instead of literals. Planning 5.8 ms on the first generic execution and 0.04-0.05 ms afterwards; execution 0.66-1.0 ms either way.
- All 72 distinct SELECT statements of two detail requests, each executed twice with `force_custom_plan` and with `force_generic_plan` on the same parameters: summed execution time 12.4 ms custom vs 10.3 ms generic. In 21 of the 72 the plan shape differs under the generic plan (for example Hash Right Join vs Nested Loop Left Join on `sales_channel_translation`, and a `product_review` statement with `status = $1` that turns into a sequential scan plus hash join). Only one statement got slower by more than 2x plus 0.3 ms: that `product_review` statement, 0.04 ms to 0.25 ms.
- Verdict: results are equal and on the catalog data no generic plan is worse in a way that matters. But a generic plan can choose a plan from default selectivity (the `product_review` seq scan would grow with that table). So `force_generic_plan` is safe for results, not proven safe for run time on other data. Decision: do not set it globally and do not set it as default in the plan cache. The default stays `auto`, where PostgreSQL itself falls back to custom plans when the generic plan is estimated worse; it still removes 38-82 % of planning. Use `force_generic_plan` only as an opt-in per database (`ALTER DATABASE ... SET`) after checking the installation's data, or per statement shape later.

## Planner settings on the detail statement

`join_collapse_limit` etc., 25 `EXPLAIN (SUMMARY)` runs per setting on the prepared detail statement with `force_custom_plan` (`psql` session in the container, load 5; `wave6-A2-planner-settings.txt` was too large to keep, the numbers are here):

| Setting | Planning median ms | Top plan cost |
|---|---|---|
| default | 5.1 (repeat 5.3) | 99.29 |
| `join_collapse_limit = 1` | 3.2 | 103.91 |
| `join_collapse_limit = 1`, `from_collapse_limit = 1` | 3.3 | 103.91 |
| `join_collapse_limit = 8` | 5.2 | 99.29 |
| `geqo_threshold = 10` | 5.6 | 99.29 |
| `geqo = off` | 5.3 | 99.29 |

`join_collapse_limit = 1` saves 37 % planning (1.9 ms) on this statement and changes the join order (the plan cost is 4.6 % higher by estimate, execution not measured). The GEQO settings change nothing (plan and cost are the same as the default). Not committed: it saves less than the plan cache and it changes plans. `= ANY(?::uuid[])` was not tested (time).

## Engine baseline

`scripts/engine-baseline.sh` (sysbench 1.0.20 Debian image `sysbench-pg-arm`, pgbench 18 from `postgres:18-alpine`), scratch databases `sysbench_mariadb`, `sysbench_mysql`, `sysbench_pg` (dropped afterwards), 8 tables with 100000 rows, 8 threads, 30 s, 3 runs, persistent connections. Reduced from the handoff (1, 8 and 32 threads, 60 s, `oltp_read_write` skipped). The client shares the CPUs with the databases and the host load was 12-30, so the values are low and noisy; the table gives the median of 3 runs and the range.

| Test | MariaDB 10.11 | MySQL 8.4 | PostgreSQL 18 |
|---|---|---|---|
| `oltp_point_select`, queries/s | 251 424 (237k-311k) | 333 550 (323k-349k) | 285 647 (257k-300k) |
| `oltp_read_only`, queries/s | 182 953 (176k-195k) | 187 889 (159k-221k) | 147 087 (135k-183k) |
| `oltp_read_only`, p95 ms (3 runs) | 1.25 / 1.47 / 1.61 | 1.23 / 1.96 / 1.55 | 1.25 / 2.14 / 2.03 |

pgbench scale 10, 8 clients, 30 s, 3 runs (tps): select-only `-S` 87 433 / 104 486 / 96 942 (latency 0.077-0.091 ms); select-only with `-C` (new connection per transaction) 138 / 148 / 153 tps (latency 52-58 ms); TPC-B-like 3 534 / 6 854 / 5 452; TPC-B-like with `-C` 147 / 161 / 119. A new connection costs 50 ms or more per transaction here with 8 clients on 4 CPUs (the single connection in the Shopware microbench above costs 5.6 ms, so this is a contended number, not the cost of one connect).

I did not compare the numbers with the published ones (smalldatum, Dolthub, Percona); I have not read them in this session.

Conclusion: on simple OLTP reads PostgreSQL gives 1.14x MariaDB and 0.86x MySQL on point selects, and 0.80x MariaDB and 0.78x MySQL queries/s on `oltp_read_only`, so the engine explains a gap of about 1.25x on read-only work (noisy, 3 runs). The storefront gap on PostgreSQL is 1.7-1.9x with a new connection per request and 1.4-1.6x with persistent connections (first session medians against MariaDB persistent). With persistent connections and the plan cache the gap measured is 1.14-1.21x, in the range of the engine difference. What lies above the engine gap is access pattern: new backend per request (connect 5.6 ms plus ICU 8.4 ms plus cold caches) and replanning of every DAL statement (11-25 ms per request).

## Recommendation: connection mode

1. Production PostgreSQL installs run persistent connections (`DATABASE_PERSISTENT_CONNECTION=1`, which already exists) and the plan cache (`DATABASE_PLAN_CACHE=1`), with `plan_cache_mode` left on `auto`. Size `max_connections` for php-fpm workers times web nodes, because each worker keeps its backend.
2. PgBouncer in transaction mode is the fallback when connections must be pooled (many nodes): measured 150.6 / 92.5 / 122.1 / 195.5 ms against 134.2 / 86.5 / 112.0 / 175.5 for persistent (first session). It removes connect and ICU but not planning, and SQL-level prepares do not work behind it, so no plan cache. A pooler with prepared statement support (PgBouncer 1.21 `max_prepared_statements`) was not measured.
3. What Shopware needs to change to make this the default on PostgreSQL: set both variables in the `.env` template for the PostgreSQL profile, document `max_connections` sizing, and keep `DATABASE_PLAN_CACHE` ignored on MySQL (it is).

## Reducing joins in a later wave

Verdict: not worth doing for planning cost. With the plan cache in generic mode the planning left is 7.4 ms of 125 ms for the detail request (6 %), 5.8 ms of 92 ms for search, below 1 ms for home and listing; in auto mode it is 13.3 ms for detail and search. Removing joins could win back at most those 7-13 ms per request for detail. Joins removed for other reasons (handoff D) are welcome, but planning is no longer the argument.

## Resets

Changed for the measurements and reset afterwards, each checked with a query: the eight `ALTER SYSTEM` settings (`postgresql.auto.conf` empty, after a restart `work_mem` 4096, `effective_cache_size` 524288, `maintenance_work_mem` 65536, `shared_preload_libraries` empty, `plan_cache_mode` auto, all source `default`; `shared_buffers` 16384 from the configuration file), `pg_stat_statements` dropped in `bench_pg`, no per-database settings left (`pg_db_role_setting` empty), `join_buffer_size` 1073741824 on MariaDB and MySQL, the three database containers at 8 CPU / 16 GiB, stacks 8101-8109 and `instance-pgbouncer-1` stopped, `sysbench_*` databases dropped.
