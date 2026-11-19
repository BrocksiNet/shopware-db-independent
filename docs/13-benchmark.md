# Benchmark: MariaDB against PostgreSQL

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
