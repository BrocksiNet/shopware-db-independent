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

## Wave 6 (handoff B): lock order and fix

Instance commits (local, `instance/` is never pushed): `38f1d41ac6c` lock order fix, `e0e6f3d3fae` versioning fix (docs/21).

### Method

Private copy `bench_pg_b` of the catalog data, own PHP processes, 4 workers, `log_lock_waits = on`, `deadlock_timeout` at the default 1 s, `log_statement = mod` for single runs, deadlock counter from `pg_stat_database.deadlocks`.
The statement sequence of each backend was read from the log together with the two statements of each `deadlock detected` report.

### The deadlock pairs

The row that two requests share is a `product` row; the benchmark list has two products that are visible in all 6 sales channels, so concurrent requests of the list as built hit them.
The indexer statements that took part, with their PHP origin (all verified in the code):

| Statement | PHP origin | Locks rows |
|---|---|---|
| bulk `UPDATE product SET ... WHERE id IN (...)` for inheritance (`canonicalProduct`, `media`, `properties`, ...) | `InheritanceUpdater` (`UPDATE #root# ...`) | in the order of the query plan |
| bulk `UPDATE` of the many to many id fields | `ManyToManyIdFieldUpdater` | in the order of the query plan |
| bulk `UPDATE product SET available/stock ...` | `StockStorage::index` | in the order of the query plan |
| `UPDATE product SET category_tree = :tree WHERE id = :id AND version_id = :version`, one statement per product | `ProductCategoryDenormalizer`, loop inside one `RetryableTransaction` | one product after the other, in the order of the category map |
| `UPDATE product SET cheapest_price = :price WHERE id = :id ...`, `cheapest_price_accessor` | `CheapestPriceUpdater`, prepared statement per product | one product after the other |
| `UPDATE product SET rating_average = :average WHERE id = :id ...` | `RatingAverageUpdater` | one product after the other |
| the writer's own `UPDATE product` of the payload | `EntityWriteGateway` | in payload order |

The updaters run in autocommit mode or in short transactions of their own, after the write transaction has committed.
So two requests that share a product interleave on this sequence: one holds the lock of product A from a per-product loop statement or from a bulk statement that has finished its A row and waits for B, the other the other way round.
Example from the log of a baseline run: a bulk `UPDATE product SET "properties" = ...` (`InheritanceUpdater`) of one backend waited for a backend that was inside the `category_tree` loop of `ProductCategoryDenormalizer`, and that backend waited for the first one (`process 270 waits for ShareLock on transaction 6036313; blocked by process 268`, 268 waits for 270).
Sorting the commands of the writer and `ksort` on the category map (wave 5) did not help because the other statements still lock in plan order or in a different loop order; the pair is never between two sorted statements.

### Fix

`ProductIndexer::withProductRowLocks()` (PostgreSQL only): in one `RetryableTransaction` around `update()` (inheritance and stock) and around the updaters of `handle()`, the first statement is

```sql
SELECT id FROM product WHERE version_id = :version AND id IN (ids, their children, their parents) ORDER BY id FOR UPDATE
```

Rows are therefore taken once in primary key order before the first updater statement runs, so concurrent indexers queue on the first shared row and no cycle can form among the product rows of one message.
The updaters keep their own statements; they only run inside this transaction on PostgreSQL.
Other databases run the closure as it is.

Why PostgreSQL only: InnoDB detects a deadlock at once and the retry is cheap, so MariaDB and MySQL do not collapse (docs/13), and the extra `SELECT ... FOR UPDATE` would only add work there.
On PostgreSQL every deadlock waits for `deadlock_timeout`, so avoiding the cycle is the fix; `deadlock_timeout` is not changed.

Tests: `ProductIndexerTest::testUpdateLocksTheProductRowsInIdOrderOnPostgreSql` and `testUpdateTakesNoRowLocksOnMySql` (unit).

Test runs (private test databases `shopware_w6b_test`, dropped afterwards):

- Unit tests `tests/unit/Core/Content/Product/DataAbstractionLayer` and `tests/unit/Core/Framework/Adapter/Database`: 274 tests green on PostgreSQL and on MariaDB.
- `tests/integration/Core/Content/Product/DataAbstractionLayer`: MariaDB 72 tests green; PostgreSQL 5 errors and 2 failures (`VariantListingIndexerTest` x4 GROUP BY, `VariantListingUpdaterTest::testUpdateAppliesSha256DisplayGroupForListingGroupConfiguration` uuid against text, `ProductSearchConfigFieldExceptionHandlerTest::testDuplicateInsert`, `CheapestPriceTest::testAggregation`).
  These 7 are pre-existing: the same 7 fail with the old `ProductIndexer` and `SearchKeywordUpdater` loaded in front of the autoloader (files of the commit before `38f1d41ac6c`), and no stack trace of the whole PostgreSQL run contains `ProductIndexer.php` or `SearchKeywordUpdater.php`.
  They belong to the DAL failure list of docs/21 (handoff C).
- One run showed an additional foreign key error in `SearchKeywordUpdaterTest` (a data set whose `product_manufacturer_translation` insert referenced a language id missing in the test database, raised in the writer, not in the indexer); it did not reproduce in 3 reruns of the class and did not occur in the two full runs with the old code.

### Result

Same session, same stacks, DB containers limited to 4 CPUs / 4 GiB (restored to 8 CPUs / 16 GiB), payload and settings as in docs/13 "Parallel bulk write and deadlocks", 93 requests per row, all HTTP 200.
"Before" is the code without `38f1d41ac6c` and `e0e6f3d3fae` on the same stack, run right before.
Load average (1 min / 5 min / 15 min) from `uptime` after each row; the machine was busier than in the wave 5 runs, so the absolute numbers are lower than in docs/13.

| Row | Deadlocks (counter) | Sequential median ms (3 repeats) | Parallel requests per second (3 repeats, median) | Load average |
|---|---|---|---|---|
| PostgreSQL, list as built, before | 31 | 783.8, 688.4, 658.7 | 1.89, 1.59, 1.07 (1.59) | 6.86 / 7.46 / 11.21 |
| PostgreSQL, list as built, after | 0 | 650.6, 749.5, 664.1 | 3.41, 2.86, 3.09 (3.09) | 5.49 / 7.49 / 11.86 |
| PostgreSQL, `--dedupe`, before | 0 | 642.6, 640.8, 650.6 | 4.75, 5.02, 5.26 (5.02) | 6.44 / 7.29 / 11.00 |
| PostgreSQL, `--dedupe`, after | 0 | 632.0, 596.0, 593.8 | 4.79, 6.01, 5.72 (5.72) | 6.59 / 7.53 / 11.72 |
| MariaDB, list as built, after | not read | 309.6, 273.1, 354.7 | 10.52, 9.24, 10.82 (10.52) | 6.92 / 7.54 / 11.63 |

- Deadlocks on the list as built go from 31 to 0, and the throughput is 1.9 times the before value in the same session.
  The first session's informal check (baseline 1.14 rps with 45 deadlocks, about 2.3 times after the fix, load 16 to 19) points the same way but was not recorded.
- The list as built does not reach the `--dedupe` value (3.09 against 5.72): requests that share the two hot products now wait for each other on those rows.
- MariaDB: the code path is unchanged on MariaDB (`withProductRowLocks()` calls the closure directly; the keyword updater filter only runs in a non-live version), and it was run once after the change, not before; 10.52 is lower than the wave 5 value of 12.17 at a higher load.
- Sequential latency on PostgreSQL (about 650 ms) is the same with and without the fix in this session, and above the 430 ms of docs/13 because of the load at the time.

### Not done

- The lock covers the `product` rows only. The deadlocks seen in wave 5 and 6 were on `product`; the older catalog run (docs/13) also named `product_keyword_dictionary`, which this fix does not touch and which was not looked at again.
