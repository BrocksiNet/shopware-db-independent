# Benchmark: MariaDB against PostgreSQL

Update 2026-11-19: a rerun after wave 4 with MySQL 8.4, equal memory settings, persistent connections and PgBouncer is at the end of this document ("Rerun after wave 4").

First measured numbers for "is PostgreSQL faster, and what does the translator cost" (benchmark plan in `docs/11-database-comparison.md`).
MySQL 8 is not part of this run, because handoff A has not added a MySQL 8 lane yet.

## Result in short

- PostgreSQL is clearly slower than MariaDB in every scenario of this setup.
- Sequential latency is 1.27x to 2.32x of MariaDB, throughput with 4 parallel connections is 0.43x to 0.64x on reads.
- The bulk sync write is the worst case: 1.94x latency, and under 4 parallel connections it collapses to 0.4 requests per second with 11 failed requests (deadlocks, see open items).
- Most of the gap is time inside the PostgreSQL server (driver column), not PHP translation work.
- `SqlTranslationMiddleware` costs 1.7 to 4.0 % of the request wall time on reads and 8.3 % on the bulk write (about 0.06 to 0.14 ms per statement).
- `IdCodecMiddleware` costs 0.6 to 1.4 % of the wall time on reads and 3.6 % on the bulk write (about 0.03 to 0.07 ms per statement).
- Both layers together are at most 12 % of a request, so removing them would not close the gap.
- Install of the 910 migrations is the one thing where PostgreSQL is faster (9.9 s against 12.3 s).

This compares MariaDB running Shopware's MySQL SQL against PostgreSQL running the same SQL after translation.
It does not compare tuned native PostgreSQL SQL.
A reading as "PostgreSQL is slower than MariaDB" in general is not supported by these numbers.

## Method

Everything is driven by `scripts/benchmark.sh` (subcommands `snapshot`, `prepare`, `maintenance`, `stacks`, `run`, `all`), `scripts/benchmark-load.py` (load generator) and `scripts/benchmark-report.py` (tables below).
Raw results are in `docs/benchmark-results/` (`results.json`, `install-times.txt`, `snapshot-sha.txt`).

- Separate databases `bench_mariadb` (container `instance-database-1`, MariaDB 10.11.16) and `bench_pg` (container `instance-postgres-1`, PostgreSQL 18.7).
  The lane database `shopware` is never touched.
- Code snapshot: `git archive 37192c89348 src` plus a copy of `bin`, `config`, `custom`, `files`, `public`, `vendor` and the lock files into `/tmp/bench-src` inside `instance-web-1`.
  The benchmark therefore does not move while other sessions edit `instance/`.
- One php-fpm pool and one caddy per database inside `instance-web-1`, ports 8101 to 8103.
  `APP_ENV=prod`, Xdebug off, `opcache.validate_timestamps=0`, 8 static fpm workers, Shopware HTTP cache off.
  The Shopware object cache is warm; every URL inside a scenario is distinct, so a request is not answered from a cache hit of an earlier request in the same scenario.
- Data: `system:install --basic-setup` on a fresh database (5 times each for the install time), then `framework:demodata` once per database with the same numbers (`--media 100`, the download media are every 30th item), then `dal:refresh:index` 5 times.
  The demo data is random, so ids, names and variant counts differ between the two databases.
- Before the request measurements: `VACUUM (FULL, ANALYZE)` on PostgreSQL and `ANALYZE TABLE` on MariaDB.
  Repeated reindexing bloated the PostgreSQL tables, so without it the PostgreSQL numbers would be worse for a reason that has nothing to do with the dialect.
- Load tool: none of `ab`, `hey`, `k6` exists inside the container, so `benchmark-load.py` (Python standard library, `http.client`) runs inside the container and talks to the local caddy.
  The load generator shares the 8 CPUs of the container with php-fpm.
- Latency: sequential requests (concurrency 1), 5 runs per database, runs alternate between the databases (MariaDB, PostgreSQL, MariaDB, ...).
  Per scenario the table gives the median of the per-run medians, the p95 over all requests of all runs, and the range of the per-run medians.
- Throughput: 4 parallel connections, 5 runs per database, requests per second.
- Scenarios and requests per run: home 30, listing with filter 40 (category SEO URL, `products.id` not null filter), search 40 (ASCII words taken from the data), product detail 40 (SEO URL), store API product listing with aggregations 60, admin API product search with aggregations 60, bulk sync write 10 (each a `/api/_action/sync` upsert of 50 products).
  Categories use page 1 only, because page greater than 1 answers with a redirect.
- Significance rule: a difference is called clear when the ranges of the 5 per-run values of the two databases do not overlap.
  This is a conservative rule of thumb and not a statistical test.
- Translator and codec overhead: opt-in `TimingMiddleware` (`instance/src/Core/Framework/Adapter/Database/PostgreSQL/TimingMiddleware.php`), active only when the environment variable `SHOPWARE_PG_TIMING` names an output file.
  `PostgreSQLFactory` puts a probe between the layers: `driver` inside the session layer, `translated` outside the translator, `codec` outside the id codec.
  The cost of a layer is the difference of the totals of two neighbouring probes (time in prepare, query, exec, bind, execute and fetch).
  Each request writes one JSON line with wall time, the probe totals and the statement count.
  The probe pass is a separate pass of the same scenarios (the probes add their own cost, see the last table), the latency and throughput tables come from runs without probes.
  Nothing is active by default; without the variable the factory builds the original stack.

## Database settings

Both databases run with the defaults of their images, no tuning for either of them.
The only change is the same container limit for both: `podman update --cpus=4 --memory=4g` on both database containers during the measurement, restored to 8 CPUs and 16 GiB afterwards.

| Setting | MariaDB 10.11.16 | PostgreSQL 18.7 |
|---|---|---|
| Cache | `innodb_buffer_pool_size` 1 GiB | `shared_buffers` 128 MB, `effective_cache_size` 4 GB |
| Connections | `max_connections` 151 | `max_connections` 100 |
| Durability | `innodb_flush_log_at_trx_commit` 1, `sync_binlog` 0 | `fsync` on, `synchronous_commit` on |
| Work memory | `sort_buffer_size` 2 MiB, `tmp_table_size` 16 MiB | `work_mem` 4 MB |
| Log size | `innodb_log_file_size` 128 MiB | `max_wal_size` 1 GB |
| Pooling | none, a connection per php-fpm request | none, a connection per php-fpm request |
| Size after prepare | 134 MB (data plus index) | 230 MB (`pg_database_size`) |

The defaults are not equal in effect: the MariaDB buffer pool is 8 times the PostgreSQL `shared_buffers`.
The data set fits in memory on both sides, and PostgreSQL also uses the operating system cache, so no run was disk bound; a PostgreSQL run with larger `shared_buffers` was not made and could change the numbers.
Connections are opened per request on both sides; opening one costs about 4 ms on PostgreSQL and about 0.3 ms on MariaDB (measured separately from PHP, not part of the tables).
Pooling (PgBouncer or persistent connections) was not tested.

## Results

### Install, demo data and indexing (seconds, wall time of the console command)

| Step | Runs | MariaDB median | MariaDB min..max | PostgreSQL median | PostgreSQL min..max | PostgreSQL / MariaDB |
|---|---|---|---|---|---|---|
| system:install --basic-setup (910 migrations) | 5 | 12.3 | 10.9..13.2 | 9.9 | 9.0..11.2 | 0.80 |
| framework:demodata (once) | 1 | 36.5 | 36.5..36.5 | 56.0 | 56.0..56.0 | 1.53 |
| dal:refresh:index | 5 | 13.0 | 12.0..16.9 | 33.7 | 31.6..39.9 | 2.60 |

### Latency, sequential requests (milliseconds)

Median of the per-run medians, p95 over all requests of all runs, range of the per-run medians. Ratio is PostgreSQL / MariaDB.

| Scenario | Requests per run | MariaDB median | MariaDB p95 | MariaDB run medians | PostgreSQL median | PostgreSQL p95 | PostgreSQL run medians | Ratio | Clear |
|---|---|---|---|---|---|---|---|---|---|
| storefront home | 30 | 247.1 | 334.4 | 225.4..279.9 | 314.5 | 415.9 | 312.9..351.2 | 1.27 | yes |
| storefront listing with filter | 40 | 142.9 | 196.2 | 126.0..158.1 | 221.6 | 276.9 | 209.1..236.9 | 1.55 | yes |
| storefront search | 40 | 127.5 | 186.7 | 122.3..138.5 | 296.1 | 414.4 | 282.8..310.3 | 2.32 | yes |
| storefront product detail | 40 | 107.2 | 135.4 | 105.6..111.0 | 182.3 | 236.1 | 179.8..203.3 | 1.70 | yes |
| store API product listing with aggregations | 60 | 49.1 | 90.6 | 45.3..53.5 | 112.1 | 164.3 | 109.0..113.4 | 2.28 | yes |
| admin API product search with aggregations | 60 | 30.5 | 40.3 | 29.9..33.2 | 53.1 | 65.7 | 52.4..53.6 | 1.74 | yes |
| admin API bulk sync write (50 products) | 10 | 198.2 | 270.8 | 182.3..217.5 | 384.1 | 518.6 | 343.1..402.9 | 1.94 | yes |

### Throughput, 4 parallel connections (requests per second)

| Scenario | MariaDB median | MariaDB run range | PostgreSQL median | PostgreSQL run range | Ratio | Clear |
|---|---|---|---|---|---|---|
| storefront home | 13.2 | 12.4..13.6 | 8.4 | 7.5..9.0 | 0.64 | yes |
| storefront listing with filter | 27.2 | 26.5..28.9 | 16.3 | 15.5..17.4 | 0.60 | yes |
| storefront search | 27.8 | 26.6..30.4 | 12.3 | 12.2..13.1 | 0.44 | yes |
| storefront product detail | 31.5 | 31.1..33.4 | 18.3 | 17.1..18.8 | 0.58 | yes |
| store API product listing with aggregations | 60.5 | 59.9..67.7 | 26.0 | 25.1..26.4 | 0.43 | yes |
| admin API product search with aggregations | 110.1 | 99.8..110.8 | 65.9 | 57.5..67.3 | 0.60 | yes |
| admin API bulk sync write (50 products) | 17.1 | 15.3..17.4 | 0.4 | 0.2..0.4 | 0.02 | yes |

### Errors (responses other than 200, all runs)

| Scenario | MariaDB | PostgreSQL | Probe pass |
|---|---|---|---|
| storefront home | 0 | 0 | 0 |
| storefront listing with filter | 0 | 0 | 0 |
| storefront search | 0 | 0 | 0 |
| storefront product detail | 0 | 0 | 0 |
| store API product listing with aggregations | 0 | 0 | 0 |
| admin API product search with aggregations | 0 | 0 | 0 |
| admin API bulk sync write (50 products) | 0 | 11 | 0 |

### Where the time goes on PostgreSQL (probe pass, milliseconds per request, median)

driver = time inside the PDO calls, translator = SqlTranslationMiddleware (translation, rewriters, column case wrapper), codec = IdCodecMiddleware (bind and fetch conversion).

| Scenario | Requests | Statements | Wall | Database layers total | Driver | Translator | Translator share of wall | Id codec | Codec share of wall | PHP without database layers |
|---|---|---|---|---|---|---|---|---|---|---|
| storefront home | 30 | 62 | 336.2 | 197.0 | 184.3 | 8.5 | 2.5 % | 4.4 | 1.3 % | 139.1 |
| storefront listing with filter | 40 | 60 | 227.8 | 91.6 | 81.0 | 7.7 | 3.4 % | 3.2 | 1.4 % | 136.2 |
| storefront search | 40 | 56 | 277.7 | 165.1 | 154.2 | 7.6 | 2.7 % | 2.9 | 1.0 % | 112.6 |
| storefront product detail | 40 | 63 | 207.0 | 90.9 | 79.7 | 8.3 | 4.0 % | 2.7 | 1.3 % | 116.1 |
| store API product listing with aggregations | 60 | 19 | 118.6 | 76.3 | 73.4 | 2.0 | 1.7 % | 0.7 | 0.6 % | 42.3 |
| admin API product search with aggregations | 60 | 15 | 53.2 | 26.7 | 25.3 | 0.9 | 1.8 % | 0.4 | 0.8 % | 26.5 |
| admin API bulk sync write (50 products) | 10 | 361 | 414.8 | 314.8 | 265.5 | 34.4 | 8.3 % | 15.1 | 3.6 % | 100.0 |

Mean instead of median:

| Scenario | Wall | Driver | Translator | Id codec | Translator per statement (ms) | Codec per statement (ms) |
|---|---|---|---|---|---|---|
| storefront home | 342.2 | 188.6 | 8.5 | 4.5 | 0.137 | 0.071 |
| storefront listing with filter | 242.3 | 85.4 | 7.7 | 3.4 | 0.127 | 0.053 |
| storefront search | 280.0 | 157.0 | 7.7 | 3.1 | 0.135 | 0.052 |
| storefront product detail | 211.1 | 81.2 | 8.4 | 2.8 | 0.132 | 0.043 |
| store API product listing with aggregations | 119.8 | 75.8 | 2.0 | 0.7 | 0.106 | 0.037 |
| admin API product search with aggregations | 53.4 | 25.5 | 1.0 | 0.4 | 0.063 | 0.028 |
| admin API bulk sync write (50 products) | 420.2 | 270.9 | 34.5 | 15.4 | 0.095 | 0.042 |

Latency in the probe pass (client side, median, includes the probe overhead itself):

| Scenario | Probe pass | PostgreSQL without probes |
|---|---|---|
| storefront home | 336.3 | 314.5 |
| storefront listing with filter | 227.8 | 221.6 |
| storefront search | 277.9 | 296.1 |
| storefront product detail | 207.3 | 182.3 |
| store API product listing with aggregations | 119.2 | 112.1 |
| admin API product search with aggregations | 53.9 | 53.1 |
| admin API bulk sync write (50 products) | 415.2 | 384.1 |

## Reading

Clear differences (ranges of the run medians do not overlap): all 7 latency scenarios and all 7 throughput scenarios.
Noise: the run medians of one database vary by about 10 to 20 % (for example home on MariaDB 225 to 280 ms), because the host also ran other work (load about 10 on 8 CPUs).
The ratios are therefore good to roughly one decimal place; the ordering is not in doubt.

- Read pages: 1.27x (home) to 2.32x (search) slower on PostgreSQL.
  The gap is smallest where PHP rendering dominates (home: 139 ms of 336 ms outside the database layers) and largest where the database dominates.
- Store API and admin API reads: 1.74x and 2.28x slower, driver time is 73 ms of 119 ms and 25 ms of 53 ms.
- Throughput under 4 connections is worse than the latency ratio suggests (0.43x to 0.64x), consistent with the slower connect and the more expensive statements competing for the same 4 CPUs.
- The bulk write is 1.94x slower sequentially.
  In the parallel run PostgreSQL fails (11 of the requests, deadlocks on `product_keyword_dictionary` between concurrent writers), so the 0.4 requests per second is not a comparable throughput figure.
- Translator: 0.06 to 0.14 ms per statement, 1.7 to 4.0 % of wall time on reads, 8.3 % on the bulk write (361 statements per request, 34 ms).
  The id codec adds 0.03 to 0.07 ms per statement, 0.6 to 1.4 % on reads and 3.6 % on the write.
  Together at most 12 % of a request.
- The remaining gap is time inside the server (driver column) plus the connect cost.
  For example storefront search spends 154 ms of 278 ms inside the PDO calls on PostgreSQL, against a total of 128 ms for the whole request on MariaDB.
- Install is faster on PostgreSQL (0.80x), indexing is 2.6x slower and the demo data generation 1.5x slower (one run only, so the demo data figure is not a median).

What the numbers do not say:

- They do not show that PostgreSQL is slower in general.
  The SQL is written for MySQL and translated mechanically, the plans were not tuned and no PostgreSQL specific index was added.
- The per-layer numbers are probe differences.
  The probes themselves cost time; the probe pass is 1 to 31 ms slower than the clean runs in six scenarios and 18 ms faster for search, which shows the run to run noise of this setup is larger than the probe effect on the layer shares.
  The shares are therefore approximate.

## Findings about PostgreSQL behaviour found while measuring

- `search::detect-keywords` runs a `LIKE` filter on the `keyword` column (nondeterministic collation `ci`) and on the generated `reversed` column of `product_keyword_dictionary`.
  `EXPLAIN ANALYZE` shows a sequential scan (15 288 rows removed by the filter, about 8 ms in isolation).
  A pattern-capable index would be needed; the search ratio of 2.32 is the largest of the read pages, but I did not isolate this statement as its cause.
- `seo_url::replacement` takes about 13 ms per call on PostgreSQL and is called 4 times per storefront request.
- `ORDER BY RAND()` is not translated.
  `framework:demodata` fails on PostgreSQL because of it; the benchmark creates a `rand()` function in `bench_pg` only (documented in `scripts/benchmark.sh`).
  This is a gap in the translator, not a harness fix.
- Table bloat after repeated reindexing is large enough to matter, hence the `VACUUM (FULL, ANALYZE)` before measuring.
- Parallel bulk writes deadlock on `product_keyword_dictionary` on PostgreSQL (11 failed requests in the throughput runs).
  MariaDB had no errors.

## Open items

- No MySQL 8 numbers.
- No run with equalised or larger PostgreSQL `shared_buffers`, no pooling, no PostgreSQL specific indexes.
- No measurement of PostgreSQL cold cache and no disk bound data set.
- The demo data is small (about 230 MB on PostgreSQL); numbers at 10 to 100 times the size may rank differently.
- The deadlocks on `product_keyword_dictionary` need a look at the write order of the keyword indexer.
- Host load from other sessions was not controlled; repeat on a quiet machine for final numbers.
- The benchmark stacks, `/tmp/bench-src` and the databases `bench_mariadb` and `bench_pg` are left in place for a rerun (`scripts/benchmark.sh run`).

## Rerun after wave 4

Same harness and the same 7 scenarios, rerun on instance HEAD 21fc93eedd8 (keyword and seo url indexes via `SqlDialect::caseInsensitive()`, `mysql-compat.sql` loaded by `system:install`, DAL ids bound as hex strings).
Raw data in `docs/benchmark-results/wave4/` (`results.json`, `install-times.txt`, full tables in `report.md`).

### Result in short

- All 7 setups served every request without an error, including the parallel bulk write that deadlocked on PostgreSQL in the first run (now 6.9 requests per second and 0 errors, before 0.4 and 11 errors).
- PostgreSQL without pooling is 1.42x to 1.93x the MariaDB median latency (first run: 1.27x to 2.32x).
- With persistent connections PostgreSQL is 1.13x to 1.57x of MariaDB on reads and 1.83x on the bulk write.
- Persistent connections make PostgreSQL 1.16x to 1.55x faster than without; MariaDB and MySQL gain nothing measurable from them.
- PgBouncer in transaction mode helps less than persistent connections on most scenarios (for example admin API product search 36.2 ms against 33.0 ms, 51.1 ms without either).
- MySQL 8.4 sits between the two: 0.94x (store API listing) to 1.21x of MariaDB on reads, and PostgreSQL with persistent connections is within 1.03x to 1.17x of MySQL 8.4 with persistent connections on 5 of 7 scenarios (storefront search 1.43x, bulk write 1.32x).
- Install: PostgreSQL 6.5 s, MariaDB 8.0 s, MySQL 8.4 18.3 s (median of 5).
  Indexing: MariaDB 9.5 s, MySQL 12.5 s, PostgreSQL 15.6 s (first run on PostgreSQL 31.2 s, before vacuum).
- The translator costs 3.1 to 7.4 % of the wall time on reads and 9.0 % on the bulk write, the id codec 0.5 to 1.2 % on reads and 3.1 % on the write.
  Both are slightly higher shares than in the first run, because the rest of the request got faster; per statement they cost about the same.

### Latency, sequential requests, median of 5 run medians (ms)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent |
|---|---|---|---|---|---|---|---|
| storefront home | 207.2 | 248.0 | 294.4 | 261.0 | 210.0 | 245.8 | 254.3 |
| storefront listing with filter | 128.4 | 147.7 | 199.9 | 182.6 | 126.1 | 152.0 | 160.3 |
| storefront search | 133.5 | 160.9 | 257.4 | 220.6 | 137.2 | 150.9 | 215.8 |
| storefront product detail | 138.2 | 155.5 | 215.2 | 206.5 | 137.3 | 163.7 | 176.2 |
| store API product listing with aggregations | 47.6 | 44.6 | 81.5 | 60.7 | 47.9 | 48.2 | 56.4 |
| admin API product search with aggregations | 28.6 | 32.9 | 51.1 | 36.2 | 29.1 | 30.5 | 33.0 |
| admin API bulk sync write (50 products) | 204.3 | 258.1 | 378.1 | 369.6 | 194.7 | 269.4 | 355.5 |

### Throughput, 4 parallel connections, median of 5 runs (requests per second)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent |
|---|---|---|---|---|---|---|---|
| storefront home | 14.1 | 11.3 | 11.5 | 12.8 | 14.2 | 11.5 | 12.5 |
| storefront listing with filter | 26.4 | 20.8 | 15.6 | 18.6 | 25.3 | 23.1 | 20.7 |
| storefront search | 23.0 | 19.5 | 11.4 | 15.1 | 23.3 | 21.0 | 14.3 |
| storefront product detail | 23.4 | 20.3 | 15.9 | 16.6 | 25.1 | 18.7 | 21.6 |
| store API product listing with aggregations | 70.0 | 57.4 | 38.8 | 49.1 | 71.5 | 59.9 | 49.5 |
| admin API product search with aggregations | 103.3 | 87.8 | 57.3 | 90.0 | 104.2 | 98.0 | 94.7 |
| admin API bulk sync write (50 products) | 17.7 | 11.4 | 6.9 | 8.1 | 18.2 | 11.4 | 7.9 |

p95, per-run ranges, the error table and the PostgreSQL time breakdown are in `docs/benchmark-results/wave4/report.md`.
Several ratios have overlapping per-run ranges (column "clear" there), so differences below about 1.2x are not reliable.

### Settings of this run

| Setting | MariaDB 10.11.16 | MySQL 8.4.13 | PostgreSQL 18.7 |
|---|---|---|---|
| Container limit during the run | 4 CPUs, 4 GiB | 4 CPUs, 4 GiB | 4 CPUs, 4 GiB |
| Cache | `innodb_buffer_pool_size` 1 GiB | `innodb_buffer_pool_size` 1 GiB | `shared_buffers` 1 GB, `effective_cache_size` 3 GB |
| Work memory | `sort_buffer_size` 2 MiB, `tmp_table_size` 16 MiB, `join_buffer_size` 256 KiB | `sort_buffer_size` 16 MiB, `tmp_table_size` 16 MiB, `join_buffer_size` 256 KiB | `work_mem` 16 MB, `maintenance_work_mem` 256 MB |
| Binary log | off | off (`--skip-log-bin`), `innodb_redo_log_capacity` 128M | not applicable |
| Pooling | per request, or persistent | per request, or persistent | per request, persistent, or PgBouncer 1.26.1 (transaction mode, pool 20) |

Deviations, stated because they could matter:

- The MariaDB `sort_buffer_size` stayed at 2 MiB: the harness sets 16 MiB with `SET GLOBAL`, but MariaDB was restarted after an out-of-memory kill and the value was lost; MySQL had 16 MiB.
- `join_buffer_size` was 1 GiB on both MySQL engines from the lane compose file; a first full run ended with MariaDB killed for memory (exit 137) under the 4 GiB limit.
  I set it to the server default of 256 KiB on both before this run and MariaDB was not killed again; that this was the cause is not proven.
- PostgreSQL was tuned in the lane container (`ALTER SYSTEM` and a restart), not in a separate container; there is no run with default PostgreSQL settings this time.
- Host load at the start was 6.8 (desktop applications, database containers near idle); the stack order rotates between runs to spread that noise.

### Still open

- The demo data is still `framework:demodata` (small, 81 MB on PostgreSQL after `VACUUM FULL`); next run uses the catalogs of https://github.com/shopwareLabs/shopware-catalog-generator as a larger and more realistic data set.
- Storefront search and the bulk write remain the largest gaps on PostgreSQL even with persistent connections.
- The environment changes above are reset after the catalog run (PostgreSQL `ALTER SYSTEM RESET`, PgBouncer container removed).

## Catalog data set

Same harness, same 7 setups, same instance snapshot (21fc93eedd8) as the rerun after wave 4, but the data comes from the 6 catalog templates of https://github.com/shopwareLabs/shopware-catalog-generator (commit 5d71970e1c5234872cee764941741ca5942d5f68) instead of `framework:demodata`.
`DATASET=catalog sh scripts/benchmark.sh prepare` installs, creates an integration, uploads the templates through the Admin API of a php-fpm stack on the target database and runs `dal:refresh:index`; the demodata path is unchanged.
Raw data in `docs/benchmark-results/wave4-catalog/` (`results.json`, `install-times.txt`, `catalog-import.txt`, generator logs in `catalog-errors-*.txt`, full tables in `report.md`).

### Result in short

- The catalog upload succeeded on MariaDB and MySQL 8.4 on the first attempt and on PostgreSQL only after a fix in `SeoUrlPersister` (finding 1 below); after the fix all three databases hold identical counts.
- PostgreSQL then failed every storefront request and every store API product listing on the template sales channels with USD as currency (finding 2 below); the benchmark ran with the template sales channels and their domains set to EUR on all three databases.
- With that workaround all 7 setups served all requests without an error.
- PostgreSQL without pooling is 2.60x to 3.56x the MariaDB median latency on the 4 storefront scenarios and 1.63x to 1.96x on the store API listing, admin search and bulk write (demo data: 1.42x to 1.93x on all 7).
- With persistent connections PostgreSQL is 2.23x to 3.06x of MariaDB on the storefront and 1.07x to 1.63x on the other three (demo data: 1.13x to 1.57x on reads, 1.83x on the write).
- MySQL 8.4 is 1.01x to 1.17x of MariaDB on all 7 scenarios (demo data: 0.94x to 1.26x).
- PgBouncer lowers the PostgreSQL median on every scenario except the bulk write (571.8 ms without, 580.3 ms with), and persistent connections lower it on every scenario.
- The bulk write on PostgreSQL reached 1.1 requests per second with 4 parallel connections (range 0.5 to 1.9 over 5 runs), MariaDB 9.9; the demo data rerun reached 6.9 on PostgreSQL.
  I did not investigate why.
- On PostgreSQL the PDO driver time is 161.4 ms of 251.9 ms wall time on the storefront home page and 130.0 of 187.4 ms on the filtered listing; the translator share of the wall time is 1.9 % to 8.6 % and the id codec share 0.3 % to 3.6 %.

### Data set

| Item | Count (identical on MariaDB, MySQL 8.4, PostgreSQL) |
|---|---|
| Products without parent | 542 |
| Variants | 1298 |
| Categories | 503 |
| Media | 2206 |
| Product media | 2781 |
| Property options | 1113 |
| SEO urls | 6811 (MariaDB and PostgreSQL, counted after the upload) |
| Sales channels | 8 (6 templates plus the install defaults Storefront and Headless) |

The upload ran with `IMAGE_PROVIDER=none`.

| Size of the database (MB) | MariaDB | MySQL 8.4 | PostgreSQL |
|---|---|---|---|
| After the upload (`data_length + index_length`, `pg_database_size`) | 82.8 | 40.6 | 113.3 |
| After the benchmark | 93.5 | 90.8 | 278.4 |

PostgreSQL was 64 MB after `VACUUM FULL` before the run (189 MB before the vacuum); the growth to 278.4 MB comes from the run, which included the bulk writes.
The MySQL value after the upload is smaller than after the run and I did not check whether the table statistics were stale at that point.

### Import results

Upload time per template in seconds, `bun run generate --name=<template>` against the stack on the target database.

| Template | MariaDB | MySQL 8.4 | PostgreSQL (after the fix) | PostgreSQL (first attempt, before the fix) |
|---|---|---|---|---|
| beauty | 26.38 | 28.50 | 51.75 | 46.32 |
| drugstore | 28.07 | 27.15 | 52.09 | 46.73 |
| electronics | 28.10 | 28.39 | 58.38 | 3.17 (failed, see finding 1) |
| fashion | 34.79 | 35.87 | 51.99 | 60.30 |
| garden | 33.65 | 35.22 | 54.73 | 53.81 |
| music | 32.58 | 31.92 | 52.72 | 59.28 |

Wall time of the whole upload step including setup: MariaDB 33.5 s, MySQL 8.4 32.5 s, PostgreSQL 53.4 s (after the fix).
Install, 5 runs, median: MariaDB 8.5 s, MySQL 8.4 20.5 s, PostgreSQL 8.1 s.
`dal:refresh:index`, 5 runs, median: MariaDB 7.1 s, MySQL 8.4 9.8 s, PostgreSQL 11.8 s.

Errors of the upload:

- Every one of the 18 generator runs (6 templates on 3 databases) exits with code 1: `Error [GENERATE_FAILED]: 1 post-processor error(s): theme (1)`.
  The reason is the same on all databases: `POST _action/theme/<id>/assign/<salesChannelId>` returns 400 `THEME__COMPILING_ERROR`, "Unable to compile the theme "Storefront". Unable to resolve file "Resources/app/storefront/dist/storefront/storefront.js". Did you forget to build the theme?".
  The storefront of the instance is not built, so the theme compile fails; products, categories, media and SEO urls are written before that step and the counts above are complete.
  The snapshot contains the copied `src/Storefront/Resources/app/storefront/vendor` directory.
- No other non-2xx response occurred on MariaDB and MySQL 8.4; the full logs are in `catalog-errors-mariadb.txt` and `catalog-errors-mysql.txt`.

### Finding 1: PostgreSQL rejects the SEO url bulk insert (electronics template)

First attempt, request on PostgreSQL during the electronics upload:

```
[Internal Server Error] An exception occurred while executing a query: SQLSTATE[22P02]: Invalid text representation: 7 ERROR:  invalid input syntax for type uuid: "me,sGAؕO:^\h\"
```

The statement is the bulk `INSERT INTO "seo_url" (id, sales_channel_id, language_id, foreign_key, ...)` of `SeoUrlPersister`, which goes through `MultiInsertQueryQueue`; the failing value is a bound parameter of that statement.
Cause, read in the code: `SeoUrlPersister` bound the 16-byte ids as strings.
`IdCodecMiddleware::encode` converts a string parameter to a uuid only if it is not valid UTF-8 or contains a NUL byte; a random id that happens to be valid UTF-8 stays raw and PostgreSQL rejects it.
The upload stopped after 3.17 s and `dal:refresh:index` then failed on the same value, so the first PostgreSQL attempt ended with 452 products (542 expected).
Fix in the instance (commit bde8801404f on `poc/db-independent`, not pushed): `SeoUrlPersister` passes `ParameterType::BINARY` for `id`, `sales_channel_id`, `language_id` and `foreign_key`.
After the fix the PostgreSQL upload succeeded with the counts above; the same file was copied into the benchmark snapshot.
The change has no effect on MySQL and MariaDB.
The other `MultiInsertQueryQueue` callers also bind ids as strings and share the weakness of the codec; I did not check them one by one.

### Finding 2: PostgreSQL fails price calculations with a currency factor other than 1

The template sales channels and their English domains use USD (factor 1.17085), the German domains EUR.
On PostgreSQL every request of these scenarios returned 500 in a check: storefront home, listing, search, product detail and the store API product listing; MariaDB and MySQL answered them with 200.
The error is the same in all of them:

```
SQLSTATE[42883]: Undefined function: 7 ERROR: operator does not exist: text * numeric
LINE 2: ...currencyb7d2554b0ce847cd82f3ac9bd1c0dfca.gross')) * 1.17085)...
HINT: No operator matches the given name and argument types. You might need to add explicit type casts.
```

The statement multiplies the JSON price extract, which is text on PostgreSQL, with the currency factor; MySQL and MariaDB convert implicitly.
The admin API scenarios returned 200 on PostgreSQL.
This is a translator finding and is not fixed.
To get comparable numbers I set `sales_channel.currency_id` of the 6 template channels and `currency_id` of their 12 domains to EUR (factor 1) in the three `bench_*` databases with SQL after the upload.
Whether a factor of 1 skips the multiplication, or why it passes, I did not look up; the requests succeed with EUR.

### Latency, sequential requests, median of 5 run medians (ms)

| Scenario | n | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent |
|---|---|---|---|---|---|---|---|---|
| storefront home | 30 | 97.4 | 103.3 | 253.5 | 221.1 | 96.7 | 101.2 | 215.7 |
| storefront listing with filter | 40 | 60.9 | 61.6 | 200.4 | 169.7 | 62.8 | 64.8 | 170.7 |
| storefront search | 40 | 72.7 | 80.8 | 258.5 | 235.7 | 74.9 | 77.7 | 219.0 |
| storefront product detail | 40 | 84.2 | 85.6 | 290.1 | 248.7 | 83.7 | 90.9 | 255.7 |
| store API product listing with aggregations | 60 | 33.2 | 36.3 | 54.2 | 32.0 | 26.2 | 27.3 | 28.1 |
| admin API product search with aggregations | 60 | 27.3 | 31.9 | 53.6 | 39.6 | 25.6 | 29.4 | 31.6 |
| admin API bulk sync write (50 products) | 10 | 332.0 | 387.8 | 571.8 | 580.3 | 325.1 | 394.7 | 529.4 |

### Throughput, 4 parallel connections, median of 5 runs (requests per second)

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL + PgBouncer | MariaDB persistent | MySQL 8.4 persistent | PostgreSQL persistent |
|---|---|---|---|---|---|---|---|
| storefront home | 35.6 | 32.4 | 13.5 | 15.6 | 35.6 | 33.3 | 16.0 |
| storefront listing with filter | 56.5 | 53.0 | 16.6 | 18.4 | 49.2 | 49.3 | 19.2 |
| storefront search | 45.8 | 44.4 | 12.8 | 14.6 | 48.7 | 44.5 | 15.9 |
| storefront product detail | 39.8 | 35.2 | 11.7 | 14.2 | 38.6 | 40.3 | 13.7 |
| store API product listing with aggregations | 98.0 | 92.7 | 56.3 | 89.1 | 106.2 | 87.5 | 95.9 |
| admin API product search with aggregations | 131.8 | 116.6 | 68.3 | 101.9 | 131.6 | 124.2 | 120.8 |
| admin API bulk sync write (50 products) | 9.9 | 7.1 | 1.1 | 1.4 | 9.4 | 7.1 | 3.2 |

Error counts are 0 for all 7 setups in all 7 scenarios and in the probe pass.
p95, per-run ranges and the PostgreSQL time breakdown are in `docs/benchmark-results/wave4-catalog/report.md`.
Whether per-run ranges overlap is listed in the "clear" column of `report.md`.

### Comparison with the demo data rerun

Ratios of the median latency, same harness; the demo data column is taken from the section "Rerun after wave 4".

| Scenario | PostgreSQL / MariaDB, demo data | PostgreSQL / MariaDB, catalog | PostgreSQL persistent / MariaDB persistent, demo data | PostgreSQL persistent / MariaDB persistent, catalog | MySQL 8.4 / MariaDB, demo data | MySQL 8.4 / MariaDB, catalog |
|---|---|---|---|---|---|---|
| storefront home | 1.42 | 2.60 | 1.21 | 2.23 | 1.20 | 1.06 |
| storefront listing with filter | 1.56 | 3.29 | 1.27 | 2.72 | 1.15 | 1.01 |
| storefront search | 1.93 | 3.56 | 1.57 | 2.92 | 1.21 | 1.11 |
| storefront product detail | 1.56 | 3.45 | 1.28 | 3.06 | 1.13 | 1.02 |
| store API product listing with aggregations | 1.71 | 1.63 | 1.18 | 1.07 | 0.94 | 1.09 |
| admin API product search with aggregations | 1.79 | 1.96 | 1.13 | 1.23 | 1.15 | 1.17 |
| admin API bulk sync write (50 products) | 1.85 | 1.72 | 1.83 | 1.63 | 1.26 | 1.17 |

- The PostgreSQL gap on the storefront scenarios roughly doubled with the catalog data (for example filtered listing 1.56x to 3.29x); on store API listing, admin search and bulk write it stayed within 0.1x to 0.2x.
- In absolute numbers the MariaDB storefront medians are lower on the catalog (home 97.4 ms against 207.2 ms) while the PostgreSQL ones are about equal (home 253.5 ms against 294.4 ms, filtered listing 200.4 against 199.9) or higher (product detail 290.1 against 215.2).
- The two runs differ in more than the data: the catalog run has 6 sales channels with rotating Host headers, 4 pages per channel instead of 20 for the store API listing, SEO urls of the channel language, and different settings (below), so absolute numbers are not directly comparable and I did not find out which difference causes the gap on the storefront.
- PostgreSQL with persistent connections is faster than without on every scenario (ratio of the medians 1.13x to 1.93x).

### Settings and deviations of the catalog run

| Setting | MariaDB 10.11.16 | MySQL 8.4.13 | PostgreSQL 18.7 |
|---|---|---|---|
| Container limit during the run | 4 CPUs, 4 GiB | 4 CPUs, 4 GiB | 4 CPUs, 4 GiB |
| Cache | `innodb_buffer_pool_size` 1 GiB | `innodb_buffer_pool_size` 1 GiB | `shared_buffers` 1 GB, `effective_cache_size` 3 GB |
| Work memory | `sort_buffer_size` 16 MiB, `join_buffer_size` 256 KiB | `sort_buffer_size` 16 MiB, `join_buffer_size` 256 KiB | `work_mem` 16 MB, `maintenance_work_mem` 256 MB |
| Pooling | per request, or persistent | per request, or persistent | per request, persistent, or PgBouncer 1.26.1 (transaction mode, pool 20) |

- MariaDB `sort_buffer_size` was 16 MiB this time (2 MiB in the rerun after wave 4), so the two runs differ in that setting.
- `join_buffer_size` was set to 256 KiB with `SET GLOBAL` on MariaDB and MySQL, as in the rerun after wave 4.
- The generator needs an `AI_API_KEY` even for templates; a dummy value and `IMAGE_PROVIDER=none` were used, no AI call was made.
- Host port 8101 was taken by another lane, so the upload went through a socat container on host port 18101 and the generator ran with `SW_ENV_URL=http://127.0.0.1:18101`.
  The sales channel domains were therefore created as `http://<template>.127.0.0.1:18101`; Symfony treats a host whose last label is numeric as an IP address and answers 400 "Invalid Host", so I rewrote the 12 domain urls with SQL to `http://<template>.localhost:18101` on all three databases after the upload.
  `scripts/benchmark.sh` now uses `http://localhost:18101` for new imports; that path was not run end to end.
- The load generator reads the template channels, their primary domains, products visible in the channel and the SEO urls of the channel language, and rotates the storefront requests over the 6 channels with the matching Host header.
  Latencies are computed from 200 responses only; there were no other responses.
- After the domain and currency updates I removed `var/cache/prod_h*` of the benchmark stacks and restarted them; a `cache:clear` run on the console did not take effect for the php-fpm pools because their cache directory differs.
- The PostgreSQL upload that ended in finding 1 is kept in `wave4-catalog/catalog-import.txt`, `catalog-errors-pg.txt` and `install-times-first-attempt.txt`; the successful upload is in `wave4-catalog/pg-rerun/`.
  `install-times.txt` combines the install and index runs of the first attempt (MariaDB, MySQL) with the catalog and index runs of the PostgreSQL rerun.

### Still open

- PostgreSQL translator finding 2 (text times numeric on the price extract) is not fixed; USD sales channels cannot be served on PostgreSQL until it is.
- The storefront gap on PostgreSQL (2.6x to 3.6x of MariaDB) and the low bulk write throughput were not analysed; the probe pass shows the time inside the PDO calls, not why the statements are slow.
- The theme of the template sales channels is not compiled because the storefront is not built; storefront pages are served without it.

## Rerun after wave 5

Same harness, same catalog data in `bench_mariadb`, `bench_mysql` and `bench_pg`, same 7 setups and same settings as the catalog run above, measured on the instance snapshot f6a37fd183f (the catalog run used 21fc93eedd8).
Raw data in `docs/benchmark-results/wave5-catalog/` (`results.json`, `report.md`, `snapshot-sha.txt`, `host-load-at-start.txt`, `parallel-writes.txt`, `usd-http-check.txt`, `usd-run/`, `deadlock-100ms/`).
All 7 setups served all requests of all 7 scenarios without an error (0 non-200 responses in the latency, throughput and probe passes).

### Result in short

- PostgreSQL without pooling is 1.77x to 2.01x the MariaDB median latency on the 4 storefront scenarios (before 2.60x to 3.56x) and 1.69x to 1.86x on store API listing, admin search and bulk write (before 1.63x to 1.96x).
- With persistent connections the storefront gap is 1.35x to 1.64x (before 2.23x to 3.05x), the other three are 1.06x, 1.20x and 1.60x (before 1.07x, 1.23x, 1.63x).
- PostgreSQL storefront throughput with 4 parallel connections rose from 11.7 to 16.6 requests per second to 20.6 to 28.3, the MariaDB values are 35.0 to 52.9.
- The PostgreSQL median latency fell on all 7 scenarios (storefront home 253.5 to 181.3 ms, filtered listing 200.4 to 118.4 ms, search 258.5 to 149.0 ms, product detail 290.1 to 155.2 ms); the MariaDB medians also moved (home 97.4 to 102.5 ms, product detail 84.2 to 77.3 ms, store API listing 33.2 to 22.6 ms), so the ratio is the figure to compare, not the milliseconds.
- MySQL 8.4 is 0.91x to 1.21x of MariaDB.
- The bulk write is unchanged in ratio (1.72x before and after); its parallel throughput on PostgreSQL is 1.6 requests per second (before 1.1), MariaDB 12.1, see the deadlock rows below.
- USD (one channel, Beauty, set to USD on all three databases): HTTP 200 on all storefront pages, prices equal across the three databases, see below.

### Ratios before and after

Ratio of the median latency; "before" is the catalog run (`wave4-catalog/report.md`), "after" this run (`wave5-catalog/report.md`).

| Scenario | PG/MariaDB before | PG/MariaDB after | PG pers./MariaDB pers. before | after | MySQL/MariaDB before | after | PG ms before | PG ms after |
|---|---|---|---|---|---|---|---|---|
| storefront home | 2.60 | 1.77 | 2.23 | 1.35 | 1.06 | 1.04 | 253.5 | 181.3 |
| storefront listing with filter | 3.29 | 1.86 | 2.72 | 1.38 | 1.01 | 1.00 | 200.4 | 118.4 |
| storefront search | 3.56 | 1.92 | 2.92 | 1.44 | 1.11 | 1.01 | 258.5 | 149.0 |
| storefront product detail | 3.45 | 2.01 | 3.05 | 1.64 | 1.02 | 0.99 | 290.1 | 155.2 |
| store API product listing with aggregations | 1.63 | 1.69 | 1.07 | 1.06 | 1.09 | 0.91 | 54.2 | 38.3 |
| admin API product search with aggregations | 1.96 | 1.86 | 1.23 | 1.20 | 1.17 | 1.02 | 53.6 | 39.7 |
| admin API bulk sync write (50 products) | 1.72 | 1.72 | 1.63 | 1.60 | 1.17 | 1.21 | 571.8 | 427.1 |

### Throughput, 4 parallel connections, median of 5 runs (requests per second)

| Scenario | MariaDB rps before | after | PG rps before | after | PG persistent rps before | after |
|---|---|---|---|---|---|---|
| storefront home | 35.6 | 35.0 | 13.5 | 20.6 | 16.0 | 25.3 |
| storefront listing with filter | 56.5 | 52.0 | 16.6 | 28.3 | 19.2 | 39.4 |
| storefront search | 45.8 | 52.9 | 12.8 | 26.0 | 15.9 | 34.5 |
| storefront product detail | 39.8 | 47.3 | 11.7 | 21.9 | 13.7 | 28.8 |
| store API product listing with aggregations | 98.0 | 119.5 | 56.3 | 68.1 | 95.9 | 111.4 |
| admin API product search with aggregations | 131.8 | 150.4 | 68.3 | 79.6 | 120.8 | 137.9 |
| admin API bulk sync write (50 products) | 9.9 | 12.1 | 1.1 | 1.6 | 3.2 | 1.0 |

The PostgreSQL persistent bulk write throughput fell from 3.2 to 1.0 although its sequential latency fell (529.4 to 398.3 ms); the per-run ranges of the parallel runs are in `report.md`, and the cause is the row deadlock of docs/19 (see the deadlock rows), not a change in the statements.

### Which wave 5 fix explains which change

- Storefront scenarios: the `category.path` collation migration and the keyword `lower()` fix of [docs/18](18-postgresql-performance.md) remove the ICU comparison of `LIKE '%|id|%'` on the nondeterministic collation, which was the largest share of the storefront gap (docs/18 reports 2.35x to 3.12x falling to 1.66x to 1.98x; this run measures 1.77x to 2.01x).
- Store API listing, admin search: no wave 5 change targets them, the ratios stay at 1.69x to 1.86x (before 1.63x to 1.96x), which is inside the spread I saw between runs.
- Bulk write: [docs/19](19-postgresql-parallel-writes.md) explains the low parallel throughput by product row deadlocks multiplied by `deadlock_timeout` of 1 s; there is no code fix, so the ratio of the sequential latency is unchanged.
- [docs/20](20-currency-seo-codec.md) (currency numeric extract, SEO ids, codec), [docs/21](21-dal-failures-postgresql.md) (DAL failures, empty many-to-many id fields NULL on PostgreSQL) and the remaining id sites of docs/15 section 8 are correctness and cleanup changes; I did not isolate their speed effect, the codec share of the wall time in the probe pass is 0.3 % to 4.4 %.

### Parallel bulk write and deadlocks (separate rows)

`scripts/parallel-writes.py` (docs/19), payload of the benchmark bulk write, 10 sequential and 20 parallel requests with 4 workers, 3 repeats, DB containers limited to 4 CPUs / 4 GiB, all responses 200 (93 per row).

| Row | Setting | Sequential median ms (3 repeats) | Parallel requests per second (3 repeats, median) |
|---|---|---|---|
| MariaDB | product list as the benchmark builds it | 245.9, 237.0, 239.9 | 11.49, 12.17, 13.12 (12.17) |
| MariaDB | `--dedupe` | 238.6, 234.3, 234.6 | 11.51, 13.4, 13.84 (13.4) |
| PostgreSQL | product list as the benchmark builds it, `deadlock_timeout` 1 s | 432.8, 433.0, 422.9 | 3.5, 1.36, 1.02 (1.36) |
| PostgreSQL | `--dedupe`, `deadlock_timeout` 1 s | 427.0, 403.7, 413.5 | 7.73, 7.33, 7.27 (7.33) |

Benchmark scenario "admin API bulk sync write (50 products)", PostgreSQL and MariaDB only, 5 runs each, `deadlock_timeout` 100 ms (`ALTER SYSTEM` plus reload, reset afterwards; `deadlock-100ms/`):

| Row | Latency median ms | Parallel requests per second median (range) |
|---|---|---|
| PostgreSQL, `deadlock_timeout` 100 ms | 434.5 | 5.9 (5.7 to 6.1) |
| PostgreSQL, `deadlock_timeout` 1 s (main run above) | 427.1 | 1.6 |
| MariaDB (same run as the 100 ms row) | 249.4 | 12.2 (11.7 to 12.8) |

With `deadlock_timeout` at 100 ms the parallel throughput on PostgreSQL is 3.7 times the 1 s value and the sequential latency does not change; removing the products that are visible in several channels gives 5.4 times the throughput of the original list at 1 s.
Both measurements agree with the cause named in docs/19.

### Catalog data in USD (docs/20 currency fix over HTTP)

The sales channel Beauty and its two domains were set to USD on all three databases (the other 5 channels stayed EUR), the benchmark stack caches were removed and the stacks restarted.
Without removing `var/cache/prod_h*` of the benchmark stacks the first requests still showed EUR prices.
HTTP status and the prices of the page text are in `usd-http-check.txt`; the host header was `beauty.localhost:18101`.

| Page | Status MariaDB / MySQL / PostgreSQL | First prices (identical on all three) |
|---|---|---|
| home | 200 / 200 / 200 | $16.38, $7.01 |
| category Makeup-Bags | 200 / 200 / 200 | $32.77, $19.89, $42.14 |
| product Angled-Brow-Brush | 200 / 200 / 200 | $16.38, $7.01, $7.48, $10.29 |
| product Blending-Sponge | 200 / 200 / 200 | $9.36, $16.38, $7.01, $7.48 |
| search "brush" | 200 / 200 / 200 | $12.87, $17.55, $17.55, then the sixth price differs: $52.68 (MariaDB, PostgreSQL), $18.72 (MySQL) |

- $16.38 is the EUR price 13.99 times the factor 1.17085 of USD; the price calculation that failed on PostgreSQL in finding 2 of the catalog run now works.
- The search result order of the sixth hit differs on MySQL; I did not look into why, the page was 200 and the first five prices matched.

Storefront scenarios with Beauty in USD, median latency in ms (3 databases, 5 runs; `usd-run/report.md`) and the ratio PostgreSQL / MariaDB:

| Scenario | MariaDB | MySQL 8.4 | PostgreSQL | PostgreSQL / MariaDB | Throughput MariaDB / MySQL / PostgreSQL (rps) |
|---|---|---|---|---|---|
| storefront home | 83.2 | 85.2 | 149.1 | 1.79 | 39.9 / 37.9 / 22.3 |
| storefront listing with filter | 51.2 | 50.4 | 97.7 | 1.91 | 63.0 / 62.8 / 33.4 |
| storefront search | 60.6 | 62.2 | 119.3 | 1.97 | 53.2 / 51.8 / 26.9 |
| storefront product detail | 71.0 | 70.9 | 142.9 | 2.01 | 47.4 / 47.8 / 22.3 |

0 errors on all three databases.
The absolute numbers are lower than in the main run for all three databases, which I attribute to a lower host load at that time (the main run started at load average 7.45, this run later at about 3 to 5); I did not measure that further.
The channel was set back to EUR afterwards.

### Settings and deviations of the wave 5 run

- Host load at the start of the main run: `18:59 up 2 days, 10:53, 8 users, load averages: 7.45 7.06 7.91`.
  The machine was running other lanes' containers (idle) and nothing of mine apart from the benchmark; the load was already about 9 before I started any command, and I did not find its source.
- Settings as in the catalog run, verified before the run: PostgreSQL `shared_buffers` 1GB, `effective_cache_size` 3GB, `work_mem` 16MB, `maintenance_work_mem` 256MB; MariaDB and MySQL `innodb_buffer_pool_size` 1 GiB, `sort_buffer_size`, `tmp_table_size` and `max_heap_table_size` 16 MiB; container limit 4 CPUs / 4 GiB during the runs; PgBouncer 1.26.1 transaction mode, pool 20.
- The MySQL container was stopped (exit 137) when I started and was started again; its command line sets `join_buffer_size=1024M`, which I set to 262144 with `SET GLOBAL` on MySQL and MariaDB before the run (MariaDB was at 262144 already).
- `database:migrate --all` runs only the identifier `core`; the wave 5 migrations (`Migration1795000000`, `Migration1795000100`) belong to `core.V6_8` and were applied with `database:migrate core.V6_8 --all` on all three databases (19 migrations each, the other 17 were older pending V6_8 migrations, so MariaDB and MySQL differ from the catalog run in those too).
  PostgreSQL already had `category.path` on `ucs_basic`; three `lower(...)` expression indexes exist on `bench_pg`.
- `dal:refresh:index` took 10 s (MariaDB), 13 s (MySQL), 13 s (PostgreSQL); `VACUUM (FULL, ANALYZE)` reduced `bench_pg` from 280 MB to 71 MB; `ANALYZE TABLE` ran on all tables of both MySQL engines.
- The first `run` call failed immediately because I had not set `DATASET=catalog` ("no category with products found"); it measured nothing, the second call is the result.
- `install-times.txt` does not exist for this run, the report script was fed an empty one.
- The Symfony caches of the three benchmark php-fpm stacks are the `var/cache/prod_h*` directories of the web container; removing the three that were created by the stacks and restarting them made the USD currency visible (see the USD section).

### Still open

- The storefront gap on PostgreSQL is 1.77x to 2.01x of MariaDB, 1.35x to 1.64x with persistent connections; I did not analyse the remaining part.
- The bulk write on PostgreSQL is serialised by product row deadlocks (docs/19), not fixed in code.

## Data set rebuild for wave 6

Handoff P rebuilt `bench_mariadb`, `bench_mysql` and `bench_pg` from the catalog generator before the wave 6 measurements.

- Instance snapshot: `f6a37fd183f` (`scripts/benchmark.sh snapshot f6a37fd183f`, also written to `docs/benchmark-results/snapshot-sha.txt`).
- Generator: https://github.com/shopwareLabs/shopware-catalog-generator at commit `5d71970e1c5234872cee764941741ca5942d5f68`, checked out in `/tmp/catgen`, `bun install`.
- Command: `DATASET=catalog RUNS=1 scripts/benchmark.sh prepare` with `OUT=/tmp/p-out`, so the install ran once per database instead of 5 times and the raw files are not in the repo.
- Host load average at the start 5.61, at the end 9.45 (other lanes' containers were running, and handoff C ran the DAL suite on `shopware_test` at the same time).

| Step (seconds, reported by the script) | MariaDB 10.11 | MySQL 8.4 | PostgreSQL 18.7 |
|---|---|---|---|
| `system:install --basic-setup` | 10.7 | 20.6 | 10.5 |
| Catalog upload of the 6 templates | 35.0 | 35.6 | 53.3 |
| `dal:refresh:index` (first run, after the upload) | 8.0 | 10.4 | 14.5 |

The whole `prepare` took about 18 minutes including the snapshot copy (wall clock, 1065 s).

| Item | MariaDB | MySQL 8.4 | PostgreSQL |
|---|---|---|---|
| Products without parent | 542 | 542 | 542 |
| Variants | 1298 | 1298 | 1298 |
| Categories | 503 | 503 | 503 |
| Media | 2206 | 2206 | 2206 |
| Product media | 2781 | 2781 | 2781 |
| Property options | 1113 | 1113 | 1113 |
| SEO urls | 6811 | 6811 | 6811 |
| Sales channels / domains | 8 / 14 | 8 / 14 | 8 / 14 |
| Size after upload (MB) | 86.9 | 49.6 | 137.1 |

After the upload I ran, on all three: `database:migrate core.V6_8 --all` (19 migrations each), an update of `sales_channel.currency_id` and `sales_channel_domain.currency_id` from USD to EUR (the 6 template channels and their 12 domains, 0 USD rows left), `dal:refresh:index` again, `ANALYZE TABLE` on all 250 tables of both MySQL engines (250 of 250 status OK) and `VACUUM (FULL, ANALYZE)` on `bench_pg` (67 MB afterwards).
`category.path` on `bench_pg` uses `ucs_basic` and three `lower(...)` expression indexes exist.

Deviations:

- Every template upload exits with 1 (6 of 6 on each database): the only error is the known theme compile failure, `Error [GENERATE_FAILED]: 1 post-processor error(s): theme (1)`; the data is complete.
- `scripts/compare-schema.py check bench_pg` reports 6 differences against `scripts/expected-catalog.json`, all explained: `category.path` is `ucs_basic` instead of `ci` and three `lower(...)` indexes exist (wave 5 changes, the expected file is older), and `state_machine_transition` has the unique index `(action_name, state_machine_id, from_state_id)` instead of the 4 column one (V6_8 migration `Migration1787763662`, run by `core.V6_8 --all`).
- `scripts/benchmark.sh stacks` returned 200 on the 7 stacks of the three databases for the default Storefront host and 500 on the PgBouncer stack (port 8105), because no PgBouncer container runs (`scripts/benchmark.sh pooler` was not run).
- Smoke check with the template channel hosts `beauty.localhost:18101` and `electronics-de.localhost:18101`: 200 on the MariaDB, MySQL and PostgreSQL stacks.
- `join_buffer_size` is still 1 GiB on MariaDB and MySQL (container command line); I did not change it, measuring handoffs must `SET GLOBAL join_buffer_size = 262144` first.
- The stacks are stopped (`stop-stacks`).

## Rerun after wave 6

Same harness and catalog data in `bench_mariadb`, `bench_mysql` and `bench_pg` as the wave 5 rerun, measured on the instance snapshot `03e1d43300f` (wave 5: `f6a37fd183f`), with one extra setup: PostgreSQL with persistent connections and the plan cache (`pg-plancache`, `DATABASE_PERSISTENT_CONNECTION=1`, `DATABASE_PLAN_CACHE=1`, recommendation of [docs/22](22-postgresql-connection-and-planning.md)).
Raw data in `docs/benchmark-results/wave6-catalog/` (`results.json`, `report.md`, `run.log`, `parallel-writes.txt`, `null-order-*`, `host-load-at-start.txt`, `host-load-at-end.txt`).
All 8 setups served all requests of all 7 scenarios without an error (0 non-200 responses in the latency, throughput and probe passes, `report.md` "Errors").
Host load: `12:09 load averages: 3.64 3.98 5.42` before I started, `12:11 5.54 4.80 5.52` at the start of the run, `12:43 2.34 3.52 4.61` at its end; nothing else of mine ran during the timings, other lanes' containers were idle but running (load source not isolated).

### Result in short

- The PostgreSQL gap to MariaDB did not move much: storefront 1.71x to 2.20x (wave 5: 1.77x to 2.01x), store API listing 1.79x, admin search 1.85x, bulk write 2.18x (wave 5: 1.69x, 1.86x, 1.72x).
  The milliseconds on PostgreSQL fell on all 4 storefront scenarios (home 181.3 to 162.9, listing 118.4 to 106.5, search 149.0 to 130.7, detail 155.2 to 149.8), but MariaDB fell as well (search 77.5 to 59.5, listing 63.7 to 57.5), so the ratio only shows what fell on both.
- With persistent connections the gap is 1.19x to 1.71x on the storefront (wave 5: 1.35x to 1.64x); with persistent connections and the plan cache 1.12x to 1.63x.
  Storefront search and product detail are 1.6x to 1.7x in all persistent setups, they do not profit from the plan cache here (97.1 against 99.5 ms for search).
- Store API listing and admin search stay at 1.79x and 1.85x without pooling; with persistent connections 20.3 and 24.9 ms against 28.2 and 21.5 ms on MariaDB persistent.
  The ratio 0.72 of the store API listing comes from a noisy MariaDB persistent value (range of the 5 run medians 19.2 to 29.7 ms against 21.3 to 29.8 ms on plain MariaDB), not from a PostgreSQL gain.
- The bulk write is slower on PostgreSQL than in wave 5 (555.3 against 427.1 ms median, 2.18x against 1.72x) while MariaDB is unchanged (254.2 against 249.0 ms).
  Parallel throughput of the bulk write rose from 1.6 to 3.8 requests per second, and the parallel runs of `parallel-writes.py` had 0 deadlocks in 12 runs (wave 5: deadlock waits, docs/19), see below.
- MySQL 8.4 is 1.00x to 1.07x of MariaDB on 6 scenarios and 1.21x on the bulk write.

### Ratios before and after

Ratio of the median latency; "before" is wave 5 (`wave5-catalog/report.md`), "after" this run (`wave6-catalog/report.md`), PostgreSQL against MariaDB of the same setting.
The setup "PG pers. + plan cache" has no wave 5 value; its ratio is against MariaDB persistent.

| Scenario | PG/MariaDB before | after | PG + PgBouncer/MariaDB before | after | PG pers./MariaDB pers. before | after | PG pers. + plan cache/MariaDB pers. after | MySQL/MariaDB before | after | PG ms before | PG ms after |
|---|---|---|---|---|---|---|---|---|---|---|---|
| storefront home | 1.77 | 1.71 | 1.46 | 1.42 | 1.35 | 1.37 | 1.19 | 1.04 | 1.00 | 181.3 | 162.9 |
| storefront listing with filter | 1.86 | 1.85 | 1.49 | 1.50 | 1.38 | 1.19 | 1.12 | 1.00 | 1.07 | 118.4 | 106.5 |
| storefront search | 1.92 | 2.20 | 1.49 | 1.80 | 1.44 | 1.68 | 1.63 | 1.01 | 1.03 | 149.0 | 130.7 |
| storefront product detail | 2.01 | 2.03 | 1.71 | 1.65 | 1.64 | 1.71 | 1.61 | 0.99 | 1.00 | 155.2 | 149.8 |
| store API product listing with aggregations | 1.69 | 1.79 | 1.10 | 1.25 | 1.06 | 0.72 | 0.80 | 0.91 | 1.01 | 38.3 | 40.7 |
| admin API product search with aggregations | 1.86 | 1.85 | 1.23 | 1.26 | 1.20 | 1.16 | 1.16 | 1.02 | 1.04 | 39.7 | 41.0 |
| admin API bulk sync write (50 products) | 1.72 | 2.18 | 1.73 | 2.23 | 1.60 | 2.03 | 1.97 | 1.21 | 1.21 | 427.1 | 555.3 |

Median latency in ms of this run (median of 5 run medians): MariaDB 95.1 / 57.5 / 59.5 / 73.8 / 22.8 / 22.2 / 254.2, MariaDB persistent 96.1 / 59.5 / 59.4 / 70.9 / 28.2 / 21.5 / 251.7, PostgreSQL 162.9 / 106.5 / 130.7 / 149.8 / 40.7 / 41.0 / 555.3, PostgreSQL persistent 131.7 / 70.9 / 99.5 / 121.0 / 20.3 / 24.9 / 510.6, PostgreSQL persistent + plan cache 114.3 / 66.8 / 97.1 / 114.1 / 22.6 / 25.0 / 497.0 (scenarios in the table order).
Per-run ranges are in `report.md`; the ranges of PostgreSQL and MariaDB do not overlap in the plain setups.

Admin search: the wave 5 ratio of 1.86x compared different result pages, as handoff D found ([docs/23](23-postgresql-api-reads.md)): the scenario sorts by `name`, and 834 of 1916 `product_translation` rows have a NULL name, which MariaDB sorts first and PostgreSQL sorted last, so page 1 held 25 variants on MariaDB and 25 named products on PostgreSQL.
This run follows the MySQL NULL order on PostgreSQL (commit `03e1d43300f`), so the pages are the same and 1.85x is the first like-for-like value; I did not re-measure wave 5 with the old code, so I cannot say how much of the earlier 1.86x was the page.
This scenario rotates its sort field (`name`, `productNumber`, `stock`) and its page between requests.

### Throughput, 4 parallel connections, median of 5 runs (requests per second)

| Scenario | MariaDB rps before | after | PG rps before | after | PG persistent rps before | after | PG pers. + plan cache after |
|---|---|---|---|---|---|---|---|
| storefront home | 35.0 | 36.6 | 20.6 | 21.6 | 25.3 | 27.0 | 31.0 |
| storefront listing with filter | 52.0 | 60.5 | 28.3 | 32.3 | 39.4 | 44.4 | 52.0 |
| storefront search | 52.9 | 55.3 | 26.0 | 25.0 | 34.5 | 32.3 | 33.5 |
| storefront product detail | 47.3 | 45.5 | 21.9 | 22.7 | 28.8 | 28.1 | 29.3 |
| store API product listing with aggregations | 119.5 | 110.8 | 68.1 | 68.5 | 111.4 | 108.8 | 114.2 |
| admin API product search with aggregations | 150.4 | 140.5 | 79.6 | 78.0 | 137.9 | 138.5 | 130.0 |
| admin API bulk sync write (50 products) | 12.1 | 11.5 | 1.6 | 3.8 | 1.0 | 3.8 | 3.6 |

The plan cache setup has the highest PostgreSQL value in 5 of the 7 rows (home 31.0, listing 52.0, search 33.5, detail 29.3, store API 114.2); on search, detail and store API the lead over PostgreSQL persistent is 1 to 5 %, I did not test whether that is outside the spread between runs (`report.md` "range of the 5 runs").

### Which wave 6 commit explains which change

- Bulk write parallel throughput 1.6 to 3.8 requests per second and 0 deadlocks: `38f1d41ac6c` (ordered row locks in `ProductIndexer`, handoff B).
  Backed by a run: with the two B files (`ProductIndexer.php` before `38f1d41ac6c`, `SearchKeywordUpdater.php` before `e0e6f3d3fae`) put back into the benchmark snapshot, the same row (list as built, PostgreSQL plain stack) gave 0.85, 0.67 and 0.57 requests per second and 454.8, 479.8 and 438.2 ms sequential median, against 3.97, 3.91, 3.98 and 528.2, 526.9, 508.2 ms with the final code.
  So the locks cost 47 ms (medians 479.8 against 526.9 ms, 10 %) of sequential latency in this setup and remove the deadlock waits; I did not count deadlocks of the old-code runs.
  The old code's 479.8 ms is itself above the wave 5 value of 432.8 ms of the same row, so the rise of the sequential latency since wave 5 is only partly the locks; I did not find the rest.
  Which statement of the lock path costs the time I did not isolate.
- `SearchKeywordUpdater` fix `e0e6f3d3fae` is a correctness fix (docs/19); one extra `SELECT` per call, not isolated.
- String filter change `028d4c97a54` (`lower() COLLATE ucs_basic`, 16 expression indexes): the storefront scenarios send no filter on the columns it changes, I measured no storefront effect I can attribute to it; its effect on filters is in [docs/23](23-postgresql-api-reads.md).
- NULL order `03e1d43300f`: changes the pages of the admin search (above) and the sort plan of one statement, see the NULL order section.
- Plan cache and persistent connections (docs/22, not a code commit of this wave): persistent connections lower PostgreSQL storefront latency from 162.9 to 131.7 ms (home) and 40.7 to 20.3 ms (store API); the plan cache adds 131.7 to 114.3 ms on home, 70.9 to 66.8 listing, 121.0 to 114.1 detail and nothing measurable on search (99.5 to 97.1 ms).
- Storefront search got worse in ratio (1.92x to 2.20x) because MariaDB got faster (77.5 to 59.5 ms), PostgreSQL got faster too (149.0 to 130.7 ms); I have no wave 6 commit that targets search and did not find the cause.
- `a3770fd3f5e` (handoff C, dialect fixes) and the docs/21 changes target correctness; I measured no speed effect.

### Parallel bulk write and deadlocks (separate rows)

`scripts/parallel-writes.py` (docs/19), payload of the benchmark bulk write, 10 sequential and 20 parallel requests with 4 workers, 3 repeats run one after the other (one `--repeats 1` call each), DB containers limited to 4 CPUs / 4 GiB, `deadlock_timeout` 1 s (default), all responses 200 (33 per run).
Deadlock count is the difference of `pg_stat_database.deadlocks` of `bench_pg` before and after each run.
Host load: `12:44 load averages: 2.65 3.34 4.47` at the start, `12:46 4.49 3.81 4.51` at the end (`parallel-writes.txt`).

| Row | Setting | Sequential median ms (3 repeats) | Parallel requests per second (3 repeats, median) | Deadlocks per run | Wave 5 parallel median |
|---|---|---|---|---|---|
| MariaDB | product list as the benchmark builds it | 259.8, 241.1, 242.9 | 12.87, 12.11, 12.8 (12.8) | n/a | 12.17 |
| MariaDB | `--dedupe` | 239.0, 230.9, 233.2 | 12.78, 13.33, 12.29 (12.78) | n/a | 13.4 |
| PostgreSQL | product list as the benchmark builds it | 528.2, 526.9, 508.2 | 3.97, 3.91, 3.98 (3.97) | 0, 0, 0 | 1.36 |
| PostgreSQL | `--dedupe` | 492.3, 527.0, 543.3 | 5.99, 5.94, 6.12 (5.99) | 0, 0, 0 | 7.33 |

The list as built is now 2.9 times the wave 5 throughput (3.97 against 1.36); `--dedupe` is still higher (5.99) but lower than in wave 5 (7.33), and its sequential median is higher too (492 to 543 ms against 404 to 427 ms); I did not find the reason.
PostgreSQL is 0.31 times MariaDB's parallel throughput on the list as built (wave 5: 0.11).
In this block I limited the containers to 4 CPUs / 4 GiB myself and reset them afterwards.

### NULL order check

Question (user decision 2026-11-20): does the MySQL NULL order on every PG sort cost an index scan in real statements?
Method: `ALTER DATABASE bench_pg SET log_min_duration_statement = 0`, one pass (`--runs 1 --stacks pg`, outside the timed runs) over the 7 scenarios, then `RESET`.
The log held 1260 statements with `NULLS FIRST` or `NULLS LAST`, 39 distinct after replacing literals and ids (`null-order-statements.json`).
For each distinct statement I ran `EXPLAIN (GENERIC_PLAN, COSTS OFF)` as sent and with the `NULLS ...` words removed (default order of PostgreSQL); the plans are in `null-order-generic-plans.json`.

- 37 of 39 have a sort node with both variants (translation names through `COALESCE`, `MIN(...)` aggregates, `stock`, positions, priorities, `product_review.created_at`): the explicit order costs nothing there, no index could serve them.
- 2 of 39 (76 + 3 executions) lose an index scan: `SELECT ... FROM product WHERE version_id = $1 AND stock >= $2 ORDER BY product.product_number ASC NULLS FIRST LIMIT 25 [OFFSET n]`, from the admin search scenario when the sort field is `productNumber`.
  With the default order it uses `product.uniq.product.product_number__version_id` without a sort; with the explicit order PostgreSQL runs a bitmap heap scan on 1840 rows and a top-N sort.
  `EXPLAIN (ANALYZE)` on `bench_pg`, page 5, `stock >= 4`, 5 runs each, run alone (`null-order-explain.txt`): explicit 18.7, 9.8, 9.3, 9.2, 9.2 ms, default 6.2, 8.4, 6.0, 6.1, 5.9 ms.
  In the statement log the 76 executions of the page statement took 669.2 ms in total (8.8 ms each).
- Index that serves the explicit order (checked inside a transaction and rolled back, not added): `CREATE INDEX ON product (product_number NULLS FIRST, version_id)`; the statement then runs in 0.11 to 0.26 ms with an index scan on it.
  I did not find why the existing index with the default order needs 6 ms (141 buffers) against 0.1 ms for the new one, and I have no number for MySQL.
- Cost in the benchmark: about 3 ms per request that sorts by product number (1 in 3 admin search requests, median 41.0 ms), which is below the spread of the run medians of the scenario (40.4 to 41.9 ms), so the timed run cannot show it.
  On the 500k-row case of docs/23 the same effect is 0.06 to 34 ms, so it grows with the table; the catalog has 1840 product rows.

### Settings and deviations of the wave 6 run

- PostgreSQL after `scripts/benchmark.sh settings` (restart): `shared_buffers` 1GB, `effective_cache_size` 3GB, `work_mem` 16MB, `maintenance_work_mem` 256MB; MariaDB and MySQL `innodb_buffer_pool_size` 1 GiB, `sort_buffer_size`, `tmp_table_size` and `max_heap_table_size` 16 MiB (as found); `join_buffer_size` 262144 set with `SET GLOBAL` on both before the run; container limit 4 CPUs / 4 GiB during the runs; PgBouncer 1.26.1 transaction mode, pool 20 (started with `scripts/benchmark.sh pooler`).
- Extra setup `pg-plancache` (stack port 8109, `DATABASE_PERSISTENT_CONNECTION=1`, `DATABASE_PLAN_CACHE=1`, `plan_cache_mode` auto), added to `scripts/benchmark-report.py` as label; `--stacks` listed the 8 setups.
- Migrations: `database:migrate --all` and `database:migrate core.V6_8 --all` on all three databases, then `dal:refresh:index` (MariaDB 9 s, MySQL 9 s, PostgreSQL 19 s), `VACUUM (FULL, ANALYZE)` (`bench_pg` 179 MB to 68 MB) and `ANALYZE TABLE` on both MySQL engines.
  `bench_pg` has 18 indexes with `lower(` in their definition, 16 of them named `idx.pg_*_lower`.
- `install-times.txt` is empty, as in wave 5.
- Experiment with the old B files: I copied the two files into `/tmp/bench-src` of the web container, restarted the stacks, measured, restored the HEAD files and compared them with `cmp`; the timed run had finished before that.
- I did not rebuild the data; handoff P built it, so wave 5 and wave 6 milliseconds come from different database files of the same generator.

### Still open

- Storefront gap on PostgreSQL 1.19x to 2.20x; the search scenario shows no gain from persistent connections plus plan cache.
- The bulk write is 2.18x of MariaDB; the lock path of B costs about 47 ms of sequential latency in the PostgreSQL stack, which statement causes it I did not isolate.
- The `product_number` sort index with `NULLS FIRST` (above) is not added.

## Rerun after wave 7

Same harness, same catalog data in `bench_mariadb`, `bench_mysql` and `bench_pg` and the same 8 setups as the wave 6 rerun, measured on the instance snapshot `87e1768ce3a` (wave 6: `03e1d43300f`), handoff F.
Raw data in `docs/benchmark-results/wave7-catalog/` (`results.json`, `report.md`, `run.log`, `parallel-writes.txt`, `paired-blocks-summary.txt`, `wave6-vs-wave7-ratios.txt`, the `w6cmp-*` and `admin-*` JSON files).
All 8 setups served all requests of all 7 scenarios without an error (0 non-200 responses in the latency, throughput and probe passes, `report.md` "Errors").
Other lanes stopped: yes (46 containers of other sw-dev lanes stopped under `/tmp/wave7-timing.lock`, started again afterwards; wave 6 was measured with them running).
Host load: `16:57 load averages: 6.58 10.85 13.98` at the start of the main run, `17:24 4.70 8.16 10.38` at its end; before I stopped the other lanes the host showed 9.13 14.13 15.70.
The main run took 27 minutes and ran alone; the later blocks ran one after the other, never together.

### Settings and state of this run

- PostgreSQL after `scripts/benchmark.sh settings` (restart): `shared_buffers` 1GB, `effective_cache_size` 3GB, `work_mem` 16MB, `maintenance_work_mem` 256MB (wave 7 W ran on the defaults, this run does not).
  MariaDB and MySQL `innodb_buffer_pool_size` 1 GiB, `sort_buffer_size`, `tmp_table_size`, `max_heap_table_size` 16 MiB (as found, `settings-before.txt`), `join_buffer_size` 262144 set with `SET GLOBAL` on both before the run.
  Container limit 4 CPUs / 4 GiB during the main run (`benchmark.sh run`) and the parallel writes, PgBouncer 1.26.1 transaction mode, pool 20.
- Maintenance before measuring: `VACUUM (FULL, ANALYZE)` on `bench_pg` (605 MB to 113 MB, the bulk write runs of W and R had bloated it again), `ANALYZE TABLE` on both MySQL engines.
- Indexes of `bench_pg` at the start: the trigram index `product_search_keyword.idx.pg_keyword_trgm` (migration 1795000201) existed, the product number NULLS FIRST index `product.idx.pg_product_number_nulls_first` (migration 1795000200) did not.
  I created it with the definition of the migration (`CREATE INDEX ... ON "product" ("product_number" NULLS FIRST, "version_id")`) before the main run.
  Both indexes existed during the main run, the paired home and search block, and the parallel writes.
  During the "without index" blocks below I dropped them and created them again with the same definitions; both exist at the end (checked in `pg_indexes`).
- The wave 6 code runs in a second snapshot `/tmp/bench-src-w6` (`git archive 03e1d43300f src` plus the same vendor tree and config), on its own php-fpm and caddy processes and ports (8117 new connection, 8118 persistent, 8119 persistent + plan cache), same databases; `instance/` was not switched.
  The load script is a copy of `scripts/benchmark-load.py` that only adds these three names (`/tmp/f7-load.py`, not committed); the wave 6 snapshot and processes were removed afterwards.
- Note for the wave 6 comparison: the databases changed between wave 6 and 7 as well (VACUUM FULL, indexes), so "wave 6 code" below always means the code on the current database.

### Result in short

- The PostgreSQL median ratios to MariaDB moved down on 5 of 7 scenarios in the plain setup (home 1.71 to 1.53, search 2.20 to 1.84, detail 2.03 to 1.88, bulk write 2.18 to 1.97, listing 1.85 to 1.79) and up on admin search (1.85 to 2.01) and store API listing (1.79 to 1.80).
  Those changes are mostly not larger than the spread: the ranges of the 5 run medians of wave 6 and wave 7 overlap for 31 of the 35 setup and scenario values compared (5 setups, 7 scenarios); the 4 that do not overlap are listed below.
- Storefront search and detail ratios with persistent connections fell (search 1.68 to 1.38, detail 1.71 to 1.40) but only because MariaDB persistent got slower (search 59.4 to 72.6 ms, detail 70.9 to 78.4 ms, both clear), PostgreSQL persistent stayed where it was (search 99.5 to 100.0 ms, detail 121.0 to 109.9 ms with overlapping ranges).
  I did not find why MariaDB got slower.
- Trigram index on the search keyword scan: verified effect on the same stack and the same code in paired blocks, PostgreSQL persistent 149.6 ms without the index and 93.5 ms with it (clear, ranges 137.3..180.1 and 82.2..112.6), details below.
  In the main run search PG persistent is 100.0 ms (ratio to MariaDB persistent 1.38) against 99.5 ms in wave 6, so the main run shows no gain over wave 6 on search; I did not find why, see the search section below.
- The APCu translation cache and the wave 7 code in general: no change larger than the spread in paired runs, except one (home, plain PostgreSQL, 141.1 against 145.1 ms).
- Bulk write: PG 520.3 ms (wave 6 555.3), MariaDB 263.7 (254.2); ranges overlap (PG 485.4..1258.9, one slow run), the 2.18x to 1.97x is not outside the spread.
  The sequential cost is the same as wave 6 in the parallel-writes rows (below).
- NULLS FIRST index: no effect visible in the admin search scenario (below).
- MySQL 8.4 is 0.98x to 1.06x of MariaDB on the 6 read scenarios and 1.41x on the bulk write (wave 6: 1.21x; MySQL plain 371.2 ms, range 297.5..551.0, MariaDB 263.7).

### Ratios before and after

Ratio of the median latency; "before" is wave 6 (`wave6-catalog/report.md`), "after" this run (`wave7-catalog/report.md`), PostgreSQL against MariaDB of the same setting, MySQL against MariaDB of the plain setting.

| Scenario | PG/MariaDB before | after | PG + PgBouncer/MariaDB before | after | PG pers./MariaDB pers. before | after | PG pers. + plan cache/MariaDB pers. before | after | MySQL/MariaDB before | after | PG ms before | PG ms after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| storefront home | 1.71 | 1.53 | 1.42 | 1.32 | 1.37 | 1.33 | 1.19 | 1.13 | 1.00 | 1.04 | 162.9 | 145.6 |
| storefront listing with filter | 1.85 | 1.79 | 1.50 | 1.39 | 1.19 | 1.26 | 1.12 | 1.14 | 1.07 | 1.06 | 106.5 | 101.0 |
| storefront search | 2.20 | 1.84 | 1.80 | 1.41 | 1.68 | 1.38 | 1.63 | 1.46 | 1.03 | 0.99 | 130.7 | 148.3 |
| storefront product detail | 2.03 | 1.88 | 1.65 | 1.50 | 1.71 | 1.40 | 1.61 | 1.44 | 1.00 | 0.98 | 149.8 | 150.5 |
| store API product listing with aggregations | 1.79 | 1.80 | 1.25 | 1.15 | 0.72 | 0.90 | 0.80 | 0.93 | 1.01 | 1.01 | 40.7 | 38.3 |
| admin API product search with aggregations | 1.85 | 2.01 | 1.26 | 1.29 | 1.16 | 1.06 | 1.16 | 1.01 | 1.04 | 1.04 | 41.0 | 45.5 |
| admin API bulk sync write (50 products) | 2.18 | 1.97 | 2.23 | 2.11 | 2.03 | 1.91 | 1.97 | 1.88 | 1.21 | 1.41 | 555.3 | 520.3 |

Median latency in ms of this run (median of 5 run medians): MariaDB 94.9 / 56.4 / 80.4 / 80.3 / 21.3 / 22.7 / 263.7, MariaDB persistent 93.9 / 54.8 / 72.6 / 78.4 / 21.1 / 23.5 / 263.4, PostgreSQL 145.6 / 101.0 / 148.3 / 150.5 / 38.3 / 45.5 / 520.3, PostgreSQL persistent 125.0 / 69.0 / 100.0 / 109.9 / 19.0 / 25.0 / 503.9, PostgreSQL persistent + plan cache 106.4 / 62.3 / 106.1 / 112.9 / 19.5 / 23.9 / 496.3 (scenarios in the table order).
Per-run ranges are in `report.md` and `wave6-vs-wave7-ratios.txt`.

### Which wave 6 to 7 differences are larger than the spread

A difference counts as clear when the ranges of the 5 run medians of the two runs do not overlap (the criterion of `benchmark-report.py`).
Of the 35 setup and scenario pairs compared (MariaDB, PostgreSQL, PostgreSQL persistent, PostgreSQL persistent + plan cache, MariaDB persistent, times 7 scenarios) 4 are clear:

| Value | Wave 6 median (range) | Wave 7 median (range) |
|---|---|---|
| storefront search, PostgreSQL | 130.7 (125.8..132.2) | 148.3 (133.1..158.9), slower |
| storefront search, MariaDB persistent | 59.4 (58.3..64.3) | 72.6 (66.9..80.4), slower |
| storefront detail, MariaDB | 73.8 (72.4..75.4) | 80.3 (77.0..133.7), slower |
| storefront detail, MariaDB persistent | 70.9 (69.6..73.0) | 78.4 (73.4..99.7), slower |

All four are slower in wave 7, none is faster; none of the faster PostgreSQL values (home 162.9 to 145.6, listing, store API, bulk write) is outside the spread.
The wave 7 ranges are wider than the wave 6 ones for MariaDB and PostgreSQL alike (for example bulk write PostgreSQL 485.4..1258.9 against 514.3..563.8), the host was shared and its load varied during the blocks, so I treat every ratio change above that is not in this table as unproven.

### Paired runs against the wave 6 code

Method: both code states run in the same interleaved run (`benchmark-load.py` alternates the stacks inside every run), same database state, same minute; 5 runs of the scenario, median of the 5 run medians with the range.
Block 1 (home, then search) with both indexes present, `w6cmp-*-index.json`, host load `17:25 3.50 7.09 9.80` at the start and `17:30 5.97 5.49 8.19` at the end of the block:

| Scenario, setup | Wave 6 code ms (range) | Wave 7 code ms (range) | Clear |
|---|---|---|---|
| home, new connection | 145.1 (143.8..147.7) | 141.1 (139.3..141.8) | yes, 4 ms (2.8 %) |
| home, persistent | 116.6 (115.0..117.7) | 110.3 (108.3..115.3) | no, ranges overlap |
| home, persistent + plan cache | 95.6 (94.2..115.0) | 97.8 (96.5..102.6) | no |
| search, new connection | 144.5 (117.3..148.7) | 113.5 (109.2..144.8) | no, ranges overlap (runs 4 and 5 of both jumped to 140 to 149 ms) |
| search, persistent | 90.5 (87.9..105.2) | 93.5 (82.2..112.6) | no |
| search, persistent + plan cache | 94.3 (84.8..104.3) | 85.1 (80.3..108.1) | no |

MariaDB persistent in the same block: home 83.0 (81.6..84.8), search 69.1 (58.5..87.1).
Ratios in this block, PG persistent over MariaDB persistent: home 1.33 (wave 7 code) against 1.40 (wave 6 code), search 1.35 against 1.31.

So of the wave 7 code changes with an expected effect on page time (APCu translation cache, NULLS FIRST index, the DAL and custom entity fixes) I can show only the 4 ms on plain home; in wave 7 R's probe numbers the translator layer fell from 10 to 19 ms to about 3 ms per request, but that is a small part of a 140 ms request and below the spread of the run medians here.

### Search: the trigram index

Same block layout with the keyword trigram index dropped (and the NULLS FIRST index dropped, irrelevant for search), `w6cmp-search-noindex.json`, host load `17:31 5.74 5.47 8.09` at its start; the index block above is block 1.

| Setup | No trigram index ms (range) | With trigram index ms (range) | Clear |
|---|---|---|---|
| PG new connection, wave 7 code | 187.8 (159.1..213.2) | 113.5 (109.2..144.8) | yes |
| PG persistent, wave 7 code | 149.6 (137.3..180.1) | 93.5 (82.2..112.6) | yes |
| PG persistent + plan cache, wave 7 code | 152.0 (124.3..158.9) | 85.1 (80.3..108.1) | yes |
| PG persistent, wave 6 code | 155.3 (125.5..167.7) | 90.5 (87.9..105.2) | yes |
| MariaDB persistent | 61.2 (59.9..73.1) | 69.1 (58.5..87.1) | no |

Without the index (the wave 6 database state) wave 6 code and wave 7 code are the same (149.6 against 155.3 ms persistent, ranges overlap), so the APCu cache does not show here either.
Ratio PG persistent over MariaDB persistent: 2.44 without the index, 1.35 with it.
The index also exists in the main run, where search PG persistent is 100.0 ms (range 86.4..153.6) and 1.38 of MariaDB persistent.
The main run shows no gain over wave 6 on search (99.5 ms), although the paired blocks show a clear gain against the state without the index; I cannot say why, the wave 6 database state cannot be rebuilt cheaply and I did not re-measure it, and one of the 5 run medians of the main run is 153.6 ms.
The index was used in the main run (`pg_stat_user_indexes.idx_scan` 40,563 at the end of the main run).

### NULLS FIRST index (admin search sorted by product number)

Paired runs ABAB on the admin search scenario (sort field rotates `name`, `productNumber`, `stock`; stacks MariaDB persistent, PG persistent, PG persistent + plan cache), index dropped, present, dropped, present:

| Run | PG persistent ms (range) | PG persistent + plan cache ms (range) | MariaDB persistent ms |
|---|---|---|---|
| no index 1 | 25.6 (25.0..32.6) | 29.5 (25.5..43.4) | 23.5 |
| with index 1 | 25.4 (25.1..56.6) | 24.8 (24.4..52.6) | 23.2 |
| no index 2 | 25.9 (25.1..29.9) | 26.8 (25.5..29.7) | 22.5 |
| with index 2 | 28.4 (25.1..29.8) | 25.6 (24.8..30.5) | 23.0 |

No difference larger than the spread, as expected from the wave 6 estimate (about 3 ms in 1 of 3 requests on 1840 product rows, below the spread).
The index matters for larger tables (docs/23, 500k rows).
The main run's admin search ratio of 2.01 on the plain setup (45.5 against 22.7 ms, ranges 39.2..58.5 and 22.0..38.9) I did not find a cause for; the persistent setups are 1.06 and 1.01.

### Throughput, 4 parallel connections, median of 5 runs (requests per second)

| Scenario | MariaDB rps before | after | PG rps before | after | PG persistent rps before | after | PG pers. + plan cache before | after |
|---|---|---|---|---|---|---|---|---|
| storefront home | 36.6 | 40.5 | 21.6 | 24.7 | 27.0 | 31.3 | 31.0 | 38.4 |
| storefront listing with filter | 60.5 | 58.1 | 32.3 | 34.0 | 44.4 | 47.7 | 52.0 | 56.3 |
| storefront search | 55.3 | 51.7 | 25.0 | 27.8 | 32.3 | 36.2 | 33.5 | 38.8 |
| storefront product detail | 45.5 | 48.0 | 22.7 | 26.1 | 28.1 | 34.2 | 29.3 | 35.6 |
| store API product listing with aggregations | 110.8 | 104.2 | 68.5 | 66.5 | 108.8 | 105.0 | 114.2 | 109.5 |
| admin API product search with aggregations | 140.5 | 149.1 | 78.0 | 90.1 | 138.5 | 151.7 | 130.0 | 152.0 |
| admin API bulk sync write (50 products) | 11.5 | 11.7 | 3.8 | 3.7 | 3.8 | 3.7 | 3.6 | 3.8 |

The ranges of the 5 runs are in `report.md`.
PostgreSQL persistent storefront throughput is 12 to 22 % higher than in wave 6 (home 27.0 to 31.3, search 32.3 to 36.2, detail 28.1 to 34.2), MariaDB's own values moved between -7 and +11 %; I did not compare against the wave 6 ranges and do not attribute the rise to a code change.

### Parallel bulk write and deadlocks (separate rows)

`scripts/parallel-writes.py`, same payload and method as wave 6 (10 sequential and 20 parallel requests with 4 workers, 3 repeats as separate calls, MariaDB and PostgreSQL alternating), DB containers limited to 4 CPUs / 4 GiB, `deadlock_timeout` 1 s, all responses 200 (33 per run).
Deadlocks are the difference of `pg_stat_database.deadlocks` of `bench_pg` before and after each run.
Host load: `17:37 6.78 7.02 7.93` at the start, `17:39 5.11 6.48 7.61` at the end (`parallel-writes.txt`).

| Row | Setting | Sequential median ms (3 repeats) | Parallel requests per second (3 repeats, median) | Deadlocks per run | Wave 6 parallel median |
|---|---|---|---|---|---|
| MariaDB | product list as the benchmark builds it | 257.3, 251.6, 245.2 | 12.21, 12.73, 12.52 (12.52) | n/a | 12.8 |
| MariaDB | `--dedupe` | 263.5, 234.8, 235.8 | 12.06, 12.68, 12.65 (12.65) | n/a | 12.78 |
| PostgreSQL | product list as the benchmark builds it | 533.8, 511.3, 526.7 | 3.84, 3.89, 3.92 (3.89) | 0, 0, 0 | 3.97 |
| PostgreSQL | `--dedupe` | 503.0, 507.7, 515.7 | 5.73, 5.64, 5.67 (5.67) | 0, 0, 0 | 5.99 |

PostgreSQL is 0.31 times MariaDB's parallel throughput on the list as built (wave 6: 0.31), 0.45 with `--dedupe`.
The values are within 3 % to 6 % of wave 6 (the wave 6 repeats of the PostgreSQL rows were 3.91 to 3.98 and 5.94 to 6.12 requests per second), the bulk write has no code change in wave 7 and shows no change here.
Sequential latency of the bulk write is the same as wave 6 (PostgreSQL 511 to 534 ms against 508 to 528 ms).

### Resets of the wave 7 run

All verified after the last block:

- `ALTER SYSTEM RESET ALL` and a restart of `instance-postgres-1`: `postgresql.auto.conf` holds no entry, `shared_buffers` 128MB, `log_min_duration_statement` -1, `pg_db_role_setting` has 0 rows.
- Databases in the PostgreSQL server: `bench_pg`, `postgres`, `shopware`, `shopware_switch`, `shopware_test` (no extra databases); the lane database `shopware` was not touched.
- `join_buffer_size` 1073741824 on MariaDB and MySQL 8.4; MariaDB `long_query_time` 10, `slow_query_log` 0.
- Containers `instance-postgres-1`, `instance-database-1`, `instance-mysql-1` at 8 CPUs / 16 GiB (`NanoCpus` 8000000000, `Memory` 17179869184).
- PgBouncer container stopped and removed, benchmark php-fpm and caddy processes stopped, `/tmp/bench-src-w6` removed.
- The other lanes (46 containers) started again from the saved list, `/tmp/wave7-timing.lock` and `/tmp/wave7-stopped-containers.txt` removed.
- Left in place on purpose: `bench_pg` indexes `product_search_keyword.idx.pg_keyword_trgm` and `product.idx.pg_product_number_nulls_first` (both as the migrations define them), `/tmp/bench-src` at `87e1768ce3a` and the benchmark stacks directory `/tmp/bench` in the web container.

### Still open

- Storefront gap on PostgreSQL with persistent connections and the plan cache is 1.13x to 1.46x of MariaDB persistent in this run; search and detail are the largest (1.46x and 1.44x), and what is left is planning and the repeated keyword score subquery (`docs/25`, not changed in wave 7).
- Run-to-run drift of the host (MariaDB search 59.5 to 80.4 ms between wave 6 and 7 with the same code) is larger than most wave 6 to 7 differences; a decision about a quieter benchmark host or a fixed number of paired repeats is needed before an effect below 10 % is claimed.
- Bulk write 1.97x of MariaDB, 475 `UPDATE product` per request (`docs/26`), not changed.
