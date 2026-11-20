# Storefront search and detail on PostgreSQL

Wave 7, handoff R.
After wave 6 the PG/MariaDB median ratio was 1.63 for search (2.20 with a new connection per request) and 1.61 for detail.
Home (1.19) and listing (1.12) were close, so this doc looks for what is specific to search and detail.

Raw data: `docs/benchmark-results/wave7-R/` (PG log, MariaDB slow log export, per-scenario statement tables in `statements.md`, benchmark JSON of every run).

## Method

- Statement capture with `scripts/capture-requests.py` and `scripts/capture-statements.py`, one request per page, persistent connections, same URLs and data on both databases, catalog dataset.
- PostgreSQL: `ALTER DATABASE bench_pg SET log_min_duration_statement = 0`, read from the container log.
- MariaDB: slow log into the table `mysql.slow_log` with `long_query_time = 0`.
- Both settings are reset (see "Settings changed and reset").
- The capture requests are slower than normal requests because of the logging, so the request times in the first table are only for comparing the DB share.
- The benchmark stacks run from a code snapshot in `/tmp/bench-src` with `opcache.validate_timestamps=0`; a change in `instance/` only counts after `scripts/benchmark.sh stacks`.

## Statement split per request

Host load while capturing: about 6, other lanes stopped: yes.

| Page | PG request ms | PG DB ms | MariaDB request ms | MariaDB DB ms | Statements PG / MariaDB |
|---|---:|---:|---:|---:|---|
| search | 153 | 77 | 99 | 36 | 66 / 64 |
| detail | 145 | 40 | 109 | 27 | 83 / 81 |
| home | 134 | 38 | 125 | 43 | 75 / 73 |
| listing | 81 | 19 | 90 | 20 | 65 / 63 |

The statement counts are the same within two, so the gap is not a round trip count.
The search page shows 77 ms DB time on PG against 36 on MariaDB in this capture (earlier captures on MariaDB gave 26 to 36 ms).

### Search, top statements

| Statement | PG ms | MariaDB ms |
|---|---:|---:|
| `search-page::search-ids` (2 calls) | 8.6 | 1.2 |
| aggregation `properties` | 8.5 | 0.7 |
| aggregation `price` | 7.9 | 1.0 |
| aggregation `options` | 7.8 | 0.6 |
| aggregation `manufacturer` | 7.5 | 0.9 |
| aggregation `shipping-free-filter` | 7.4 | 0.6 |
| aggregation `rating-exists` | 7.1 | 0.7 |
| `search-page::read` | 6.4 | 1.8 |
| `search::detect-keywords` | 5.3 | 13.1 |

Cause, verified with `EXPLAIN (ANALYZE, BUFFERS)` (`explain-agg-manufacturer.txt`):
each of these statements filters `product_search_keyword` with `lower(keyword) COLLATE ucs_basic = $1 OR lower(keyword) COLLATE ucs_basic LIKE '%organizer%'`.
The leading wildcard cannot use a btree.
The plan is a sequential scan of 34,193 rows (942 pages, `Rows Removed by Filter: 34191`), 8.4 ms warm and 17 ms cold.
With `enable_seqscan = off` the planner still scans sequentially, so no existing index can serve the filter.
About seven statements per request repeat the scan, which is about 56 ms.
MariaDB runs the same pattern in under 1 ms per statement.

### Detail, top statements

DB time is only about 13 ms higher on PG (40 against 27 ms).
`product-detail-route::read` takes 8.2 against 2.8 ms and `breadcrumb-builder::main-category` 3.4 against 1.3 ms.
Most of the detail gap is outside the statement execution, see the next section.

## Time outside the statement execution

The `pg-timing` stack reports the time per request in the driver, the translator and the id codec layer (new connection per request, search and detail page).

| Page | Translator layer before | after | Wall before | Wall after |
|---|---:|---:|---:|---:|
| detail | 19.4 / 18.4 ms | 2.9 / 2.8 ms | 180 / 168 ms | 156 / 150 ms |
| search | 10.4 / 10.1 ms | 3.5 / 3.1 ms | 148 / 141 ms | 142 / 122 ms |

Driver time is 75 to 83 ms and the id codec about 1 ms.

Cause, verified: `MySQLToPostgreSQLTranslator` keeps its translation cache in a PHP array, so every PHP-FPM request translates every statement again.
A cold `translate()` of the statements of one request costs 6.5 ms (detail) and 4.9 ms (search) in a plain loop (`/tmp/cold.php` style microbenchmark, warm 0.005 ms); inside the request the layer measures 10 to 19 ms.
The other layer checks (`isDdl`, `matches`) cost about 0.02 ms.
Planning is the other part: `docs/22` measured 15.9 ms (search) and 20.6 ms (detail) without the plan cache.
`pg_stat_statements` is not loaded in this container (`shared_preload_libraries` is empty), so `scripts/planning-split.sh` does not run; the `docs/22` numbers were not measured again.

## New connection per request

A replay of the captured SELECTs through PDO (15 repetitions, median, 48 of 51 search statements and 66 of 69 detail statements, the others have leftover parameters):

| Page | connect | first pass on a new backend | second pass, same backend |
|---|---:|---:|---:|
| search | 4.7 ms | 65.5 ms | 38.1 ms |
| detail | 4.5 ms | 70.6 ms | 41.9 ms |

A new PostgreSQL backend costs about 27 to 29 ms extra on its first pass (cold catalog and collation caches in the new process) plus the connect.
That is a per-request cost PG pays and MariaDB (threads, shared caches) does not, which explains why the new connection ratio is far above the persistent one.
Not explained: why the MariaDB new-connection time fell between wave 5 and wave 6.
The wave 5 snapshot and settings cannot be rebuilt cheaply, so I could not check it.

## Fixes

### 1. Trigram index for the keyword scan

Migration `Migration1795000200PostgreSqlSearchKeywordTrigramIndex` (PG only, no-op elsewhere or when `pg_trgm` cannot be created):

```sql
CREATE INDEX "product_search_keyword.idx.pg_keyword_trgm" ON product_search_keyword
USING gin ((lower(keyword) COLLATE ucs_basic) gin_trgm_ops)
```

The same filter takes 0.1 to 0.2 ms with a bitmap index scan, the index is 2.2 MB for a 7.5 MB table.
Patterns shorter than three characters (`%or%`) still scan sequentially (8.6 ms).

Medians of 5 run medians, same code, same state, `RUNS=5`, host load about 4 to 6, other lanes stopped: yes.

| Search, ms | Before | After |
|---|---:|---:|
| pg-persistent | 146.8 | 109.2 |
| pg-plancache | 136.1 | 97.5 |
| pg (new connection) | 170.4 | 142.6 |
| mariadb | 66.4 | 69.7 |
| mariadb-persistent | 68.4 | 69.0 |

pg-persistent over mariadb-persistent goes from 2.15 to 1.58, the new connection ratio from 2.57 to about 2.05.
MariaDB is not affected (the index is created only on PostgreSQL).

### 2. Shared translation cache

`MySQLToPostgreSQLTranslator::translate()` additionally reads and writes APCu (key from the file mtime and a hash of the SQL, 24 h TTL, statements up to 64 KB), when APCu is loaded.
Unit test: `testTranslationIsSharedBetweenInstancesThroughApcu` (skipped without APCu).
Verified effect: the translator layer drops from 10 to 19 ms to about 3 ms per request (table above).
The effect on the wall time is not resolved: the end-to-end A/B pairs ran at host load 9 to 30 and swung by 10 to 20 percent, so I do not claim a wall time gain beyond the probe numbers.
A final repeat of the end-to-end run (script bug in the file name, load 10 to 17) gave no usable data and is not reported.

## What is left

- Search is still about 1.6 times MariaDB with persistent connections (109 against 69 ms).
  The remaining part is the plan time per statement and the cost of seven aggregations that each repeat the keyword score subquery (idea for core, not measured).
- A join reduction in the DAL read path would cut planning and execution on both databases.
  I did not start it and did not measure the size of the gain; no estimate is given because I have no measurement.
- Detail: the remaining gap is planning (about 21 ms without the plan cache, `docs/22`) and untagged statements I could not match by text.
- New connection: the first pass cost of a new backend (about 28 ms) needs a pooler or persistent connections, the code cannot remove it.
- Keywords shorter than three characters still scan sequentially.

## Settings changed and reset

- `ALTER DATABASE bench_pg SET log_min_duration_statement = 0`, reset with `ALTER DATABASE ... RESET`.
- MariaDB `slow_query_log`, `log_output = TABLE`, `long_query_time = 0`, reset to off, table and 10 s, `mysql.slow_log` truncated.
- Extension `pg_trgm` and the trigram index exist in `bench_pg` (matching the migration, kept).
- `/tmp/bench-src` holds a snapshot of HEAD `3b492636a18` plus the translator file of the translator commit, replacing the earlier snapshot of another handoff.
