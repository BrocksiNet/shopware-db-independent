# PostgreSQL parallel writes (wave 5 B)

## Question

The Admin API bulk sync write of 50 products with 4 parallel connections gave 9.9 (MariaDB), 7.1 (MySQL) and 1.1 (PostgreSQL) requests per second in the catalog run.
Sequential latency was 572 ms against 332 ms, so the parallel case is far worse than the sequential one.
This document records what the writers wait for.

## Method

- `scripts/parallel-writes.py` drives the scenario inside the web container.
  It reuses the client, token and product discovery of `scripts/benchmark-load.py`.
  Flags: `--seq`, `--par`, `--workers`, `--repeats`, `--size`, `--start`, `--dedupe`, `--same`.
  It prints one JSON line with the sequential median, parallel requests per second and the HTTP statuses.
- All runs used private copies of the catalog database on their own PHP processes (`bench_pg_b`, `bench_mariadb_b`), not the databases of handoff A.
- Sampling on PostgreSQL: `pg_stat_activity` every 150 ms (wait event, state, `pg_blocking_pids()`, query start), `log_lock_waits = on`, `log_statement = all` for single runs, `pg_stat_database.deadlocks` before and after each run.
  On MariaDB: `Innodb_deadlocks`.
- Each parallel figure is a run of several requests per worker, repeated, with the spread given as a range.

## Findings

### 1. The collapse is deadlocks, and PostgreSQL pays for each of them with `deadlock_timeout`

- The parallel runs produced 7 to 22 deadlocks per run on PostgreSQL and 1 to 5 on MariaDB (counters above).
- InnoDB detects a cycle immediately.
  PostgreSQL only looks for a cycle after `deadlock_timeout` (default 1 s), so every deadlock stalls two or more connections for one second.
- `EntityWriteGateway::execute` wraps the write in `RetryableWriteTransaction`.
  A deadlock replays the whole transaction, so the error is hidden (HTTP 200) and only shows as latency.
  When the retries run out the request returns HTTP 500 (SQLSTATE 40P01).
  This was seen with identical payloads.
- Evidence for the cost multiplier: with `deadlock_timeout = 100 ms` the same payload gave 4.3 to 5.65 requests per second, against 0.82 to 3.96 at 1 s.

### 2. All deadlocks are on the `product` table

- The log shows the blocked statements are `UPDATE product ...` bulk statements of the indexer (inheritance, `categories`, `category_tree`, `cheapest_price*`) against the writer transaction, and indexer statements against each other.
  `pg_stat_activity` samples show `Lock/transactionid` waits between two such statements, for example `UPDATE "product" SET "categories" = ...` against `UPDATE product SET category_tree = ...`.
- No other table appeared in a deadlock report.
  Rejected hypotheses: keyword dictionary (not involved after wave 4 A), foreign key checks (no `KEY SHARE` waits seen), savepoints per statement (not active), increment or cache tables (no waits seen).

### 3. The trigger is the benchmark data, not the payload size

- The product list of the scenario contains two products that are visible in all 6 sales channels (positions 90 and 91, repeated every 92 entries).
  Concurrent windows of 50 consecutive products therefore share two hot rows.
- With deduplicated or disjoint product sets there were 0 deadlocks and 4.0 to 4.4 requests per second on PostgreSQL.
- With identical payloads (`--same`) the throughput falls to 0.02 to 0.04 requests per second and some requests fail with HTTP 500.
- A real shop that syncs overlapping product sets from several workers shows the same behaviour.

## Fixes tried

Two lock order changes were built and measured:

- Stable sort of the `UpdateCommand` runs of one entity by primary key in `EntityWriteGateway::executeCommands`.
- `ksort` of the category map in `ProductCategoryDenormalizer` before the update loop.

Result: no reduction.
At 100 ms deadlock timeout the baseline had 2 to 5 deadlocks per run and the changed code 0 to 8.
`EXPLAIN` shows the indexer bulk statements already scan `product_pkey` in id order, so the remaining inversion is not between two sorted statements.
Both changes were reverted and not committed.
No code in `instance/` changed in this handoff.

## Open causes

- The actor that locks the shared rows in a different order is not identified.
  The multi-statement indexer sequence (inheritance, category tree, cheapest price, rating, listing, keyword) runs as separate short transactions or autocommit statements after the write, so two requests that share a product interleave on it.
  A candidate direction, not verified: lock the affected `product` rows up front in id order (`SELECT ... ORDER BY id FOR UPDATE`) at the start of the indexer, as `ChildCountUpdater` already does for parent rows.
- `deadlock_timeout` is a superuser setting and cannot be set from the application.
  Lowering it (for example to 100 ms to 200 ms) is the cheapest mitigation measured here and should be a documented recommendation for PostgreSQL installations.
- The catalog run figure of 1.1 requests per second is therefore mostly an artefact of two shared rows in the benchmark list plus the one second cycle detection.
  Handoff F should rerun with the deduplicated list (`--dedupe`) next to the original.

## Settings changed and reset

- `ALTER SYSTEM SET deadlock_timeout` (100 ms), `log_lock_waits`, `log_statement` on `instance-postgres-1`, reset with `ALTER SYSTEM RESET` and `pg_reload_conf()`.
  Verified afterwards: `deadlock_timeout = 1s`, `log_lock_waits = off`, `log_statement = none`.
- Databases `bench_pg_b` and `bench_mariadb_b` created for the runs and dropped.
  The lane database `shopware` was not touched.
- Incident: a `pkill psql` inside `instance-postgres-1` sent PostgreSQL into crash recovery at about 15:34 UTC.
  The server recovered by itself and was healthy afterwards, but queries of other sessions at that time may have failed.
- No translator rules were added.
