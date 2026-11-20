# 23 PostgreSQL store API and admin API reads (wave 6, handoff D)

Question: what keeps the store API product listing with aggregations (1.69x of MariaDB after wave 5, 1.06x with persistent connections) and the admin product search with aggregations (1.86x, 1.20x) slower on PostgreSQL, and what can the dialect fix.

Short answer: nothing in the SQL of these two reads is slower on PostgreSQL.
With persistent connections the database time per request is lower on PostgreSQL than on MariaDB.
The part of the gap that was left is the connection and planning cost (docs/22) and, for the admin search, a different result page because of the NULL order (see "NULL order").
This handoff also changes the string filters (case-insensitive, accent-sensitive on PostgreSQL) and the NULL order of DAL sorts.

## Setup

- Catalog data set (docs/20), PostgreSQL 18.7, MariaDB 10.11, stacks of `scripts/benchmark.sh` with persistent connections: `mariadb-persistent` (port 8106), `pg-persistent` (8108, `DATABASE_PERSISTENT_CONNECTION=1`) and `pg-plancache` (8109, additionally `DATABASE_PLAN_CACHE=1`, docs/22).
- `plan_cache_mode` is `auto` (verified with `show plan_cache_mode`).
- The database containers ran at 4 CPU / 4 GiB while measuring and are back at 8 CPU / 16 GiB (checked with `podman inspect`).
- PostgreSQL settings during the measurement: `shared_buffers` 128 MB (server default after the reset of handoff A, no restart done here), `ALTER DATABASE bench_pg SET work_mem = '16MB'` and `effective_cache_size = '3GB'`, both reset afterwards.
  MariaDB: `innodb_buffer_pool_size` 1024 MiB, `sort_buffer_size` 16 MiB.
  The two servers are therefore not configured exactly like in wave 5; before and after use the same configuration, so only the before/after comparison per stack is clean.
- Statement capture: `ALTER DATABASE bench_pg SET log_min_duration_statement = 0` and the MariaDB slow log in a table (`long_query_time = 0`), one request per scenario after 8 warm-up requests, joined by `scripts/capture-statements.py`.
  The request times of a capture include the logging cost and are not benchmark results.
- Benchmark: `scripts/benchmark.sh run --only "with aggregations" --stacks mariadb-persistent,pg-persistent,pg-plancache --no-throughput --no-probes` with `RUNS=3`, repeated three times (3 repetitions, 9 run medians per stack and scenario, 60 requests per run).
  Raw data: `benchmark-results/wave6-D/` (`before1-3.json`, `after1-3.json`, `ratios.txt`, `statements-before.md`, `micro-filters.txt`, `explain-product-read.txt`).
- Host: the 1-minute load average was 9.5, 8.3, 8.1 during the three "before" repetitions and 8.6, 7.6, 10.4 during the three "after" repetitions (the host is shared with other sessions, so the numbers are noisy; see the ranges).
- "Before" is the instance snapshot `ccda386febb` (plan cache, no wave 6 D change), "after" is `7517df9090b` (string filters) plus the `CriteriaQueryBuilder` part of `03e1d43300f` (NULL order for every sort).
  The `EntityReader` part of that commit (window sort parts of paginated to-many reads) was not in the snapshot; the two scenarios do not use it.

## Statement ranking

`statements-before.md` has the per statement table of both scenarios.
One request of each scenario, warm, persistent connection:

| Scenario | Statements PG / MariaDB | DB time PG | DB time MariaDB |
|---|---|---|---|
| Store API listing with aggregations | 21 / 19 | 31 ms | 55 ms |
| Admin search with aggregations | 17 / 14 | 16 ms | 62 ms |

The statements of the two databases mostly do not join by text (`REPLACE(x::text, '-', '')` against `HEX`, JSON price functions), so the table lists the PostgreSQL statements by time and shows the MariaDB time only where the shape matches.
The slowest PostgreSQL statements are the product read with its joins (12.3 ms in the store request, 4.5 ms in the admin request, which includes cold plans), the properties terms aggregation (2.9 ms), the manufacturer aggregation (2.3 and 1.9 ms) and the `cheapestPrice` maximum (2.1 ms).
Where both sides have a matching statement, PostgreSQL is not slower: rating maximum 1.4 ms against 7.1 ms, stock average 0.6 against 1.9 ms, stock stats 0.6 against 2.1 ms.

`EXPLAIN (ANALYZE, BUFFERS)` of the product read of the store request with its 94 parameters (`explain-product-read.txt`, executed as a prepared statement on `bench_pg`):

| Execution | Planning | Execution |
|---|---|---|
| first (new backend session) | 25.2 ms | 4.0 ms |
| second | 0.38 ms | 0.79 ms |
| third | 0.35 ms | 0.83 ms |

The plan is a hash right join with one sequential scan and one index scan (verified in the plan text), the execution is below 1 ms once the pages are cached.
The cost of this statement on a cold backend is the 25 ms of planning (catalog cache of a new session), which is the cause of docs/22, not the SQL.
The aggregation and total count statements were ranked by their time only (each at most 3 ms on PostgreSQL), their plans were not analysed; the data sets are small (1840 products match the admin search, 231 the store listing), so larger data sizes (for example the JSON price maximum) were not measured.

Conclusion of the ranking: no statement of these two scenarios needs a different SQL shape or an index on PostgreSQL.

## Before and after

Median of the 9 run medians in ms (range of the run medians), ratio against `mariadb-persistent` of the same phase:

| Scenario | Stack | Before | After |
|---|---|---|---|
| Store listing | mariadb-persistent | 28.9 (23.6-40.7) | 30.9 (22.5-39.7) |
| | pg-persistent | 26.5 (24.2-31.9), 0.92x | 36.0 (23.9-64.1), 1.16x |
| | pg-plancache | 24.2 (20.9-28.4), 0.84x | 29.2 (21.3-33.9), 0.94x |
| Admin search | mariadb-persistent | 26.4 (22.3-28.9) | 30.8 (25.5-41.4) |
| | pg-persistent | 30.8 (28.5-44.2), 1.16x | 34.5 (30.1-47.7), 1.12x |
| | pg-plancache | 29.4 (24.8-240.5), 1.11x | 32.4 (29.0-48.2), 1.05x |

Per repetition medians are in `ratios.txt`.
Reading: with persistent connections and the plan cache the store listing is at 0.84x to 0.94x of MariaDB and the admin search at 1.05x to 1.11x, against 1.06x and 1.20x in wave 5 with persistent connections and 1.69x and 1.86x with a new connection per request.
Before and after differ by less than the spread of the runs, the change did not make these two scenarios slower or faster; the absolute values of the "after" phase are higher on MariaDB too, which points to the host load.
The one outlier of 240 ms is a single run of `pg-plancache` before.

MySQL and MariaDB SQL is unchanged by all changes below, they only differ from the PostgreSQL stacks through the dialect methods.

## NULL order

`EntityAggregatorTest::testTermsAggregationWithSorting` expects the NULL bucket last for `DESC`; MySQL sorts NULL as the smallest value, PostgreSQL as the largest.
The same holds for every DAL sort, and it changes results of the measured scenario:
the admin search sorts by `name ASC`, and the `name` of variants is NULL in the translation table (834 of 1916 `product_translation` rows of `bench_pg` have a NULL name).
On MariaDB page 1 holds 25 variants with a NULL name (response about 130 KB), on PostgreSQL it held 25 named products (302 KB), a different page with a different payload size and PHP hydration cost.
With a NULL free sort (`productNumber`) both databases return the same 25 products (139 475 against 139 830 bytes).
So the request times of the two databases in the wave 5 tables did not compare equal work.

Decision with a measurement (500 000 row scratch table, `ORDER BY num ... LIMIT 25`, `micro-filters.txt`):

| Sort | Execution |
|---|---|
| `ASC` (default btree index) | 0.060 ms |
| `ASC NULLS FIRST` | 34.3 ms |
| `DESC` | 0.034 ms |
| `DESC NULLS LAST` | 32.5 ms |

The explicit NULL placement defeats the default btree index (`ASC NULLS LAST`), as measured on a nullable column.
Results are what the DAL promises (same page on every database), speed on sorts that could use an index is the price.
Decision:

- `SqlDialect::sortDirectionWithMySqlNulls()` (PostgreSQL: `ASC NULLS FIRST`, `DESC NULLS LAST`; other dialects unchanged) is applied to every DAL sort (`CriteriaQueryBuilder::build()`, `EntityAggregator`), instance commits `028d4c97a54` (aggregations) and `03e1d43300f` (all sorts).
- The sorts seen in the captured statements are `COALESCE` of translation columns and `MIN()` of columns in grouped queries (`ORDER BY COALESCE(product.translation.name) ASC NULLS FIRST LIMIT 25`, `ORDER BY MIN(product.product_number) ASC NULLS FIRST LIMIT 500` in the PostgreSQL log), the benchmark shows no change (table above); whether an index served any of these sorts before was not checked.
- A table that needs an index for a sort can get one on `(col ASC NULLS FIRST)` or `(col DESC NULLS LAST)`; none is created now.
- `EntityReader` splits the sort parts of paginated to-many reads into expression, direction and NULL placement (`splitSortDirection()`); it used to cut the last four characters.
- `CriteriaQueryHelperTest` compares the order parts with the dialect specific direction.

Result in the admin search after the change: both databases return NULL-name variants first; the order inside the NULLs is not defined on either database, so the exact products of a page can still differ.

## String filters

`SqlQueryParser` wraps regular string columns (`StringField`, `LongTextField`) of `equals`, `equalsAny`, `contains`, `prefix` and `suffix` filters with `SqlDialect::caseInsensitive()` and binds `SqlDialect::caseInsensitiveValue()`.
On PostgreSQL this is `lower(col) COLLATE ucs_basic` and the lower-cased value, the `%` and `_` escaping runs after the lower-casing.
New dialect method `caseInsensitiveStringFilters()` (PostgreSQL true, MySQL, MariaDB and SQLite false) tells the parser when to fold; MySQL and MariaDB SQL is unchanged.
Sorting stays on the `ci` collation.

### Behaviour change

Verified with queries:

| Comparison | PostgreSQL before (`ci`) | PostgreSQL now | MariaDB (`utf8mb4_unicode_ci`) | MySQL 8.4 (`utf8mb4_0900_ai_ci`) | SQLite |
|---|---|---|---|---|---|
| `'Müller' = 'müller'` | true | true | true | true | true (NOCASE folds ASCII only) |
| `'MÜLLER' = 'müller'` | true | true | true | true | false (NOCASE does not fold `Ü`) |
| `'Müller' = 'muller'` | true | false | true | true | false |

So on PostgreSQL `Müller` no longer matches `muller` in DAL string filters, as decided on 2026-11-20 (speed over accent-insensitivity).
Case folding of non-ASCII letters keeps working (`lower()` folds `Ü`).
MySQL and MariaDB keep matching accents.
SQLite already compared accent-sensitive and case-insensitive for ASCII only; it stays unchanged and is not folded by the dialect.
Custom field string equals stay case-insensitive on every database (handoff C, docs/21).

### Speed

Scratch table with the `ci` collation, 500 000 rows, median execution time (`micro-filters.txt`):

| Filter | `ci` collation (before) | `lower() COLLATE ucs_basic`, no index | with index |
|---|---|---|---|
| `equals` | 6.2 ms (btree) | 56.1 ms | 0.07 ms |
| `equalsAny` (10 values) | 7.5 ms (btree) | 48.4 ms | 0.14 ms |
| `prefix` | 224 ms (seq scan) | 57.1 ms | 6.3 ms |
| `contains` | 1567 ms (seq scan) | 61.7 ms | 7.6 ms (`gin_trgm_ops`) |

Without an index, `lower()` is 4 to 25 times faster than `ci` for `LIKE` and slower than the plain btree for `equals` (the `ci` btree serves `=` only).
Hence the migration `Migration1795000001PostgreSqlStringFilterIndexes` adds expression btrees `((lower(col) COLLATE ucs_basic))` for the columns that are looked up by value: `product.product_number`, `product.manufacturer_number`, `product.ean`, `customer.customer_number`, `customer.email`, `order.order_number`, `promotion.code`, `promotion_individual_code.code`, `sales_channel_domain.url`, `user.username`, `user.email`, `newsletter_recipient.email`, `media.file_name`, `tag.name`, `custom_field.name`.
No `gin_trgm_ops` index is created: none of the measured scenarios filters with `contains` on a column that scans enough rows; the table shows the cost of adding one.
The indexes are not part of the two benchmark scenarios (their filters are `range` and `equals` on ids), so the benchmark table does not show them.

### Tests

New: unit `SqlQueryParserTest::testStringFiltersAreCaseInsensitiveOnPostgreSql` (data provider with the five filters), `testStringFiltersAreUnchangedOnMariaDb`, `testNonStringColumnsAreNotLoweredOnPostgreSql`; unit `CaseInsensitiveTest::testOnlyPostgreSqlFoldsStringFilters` and `testSortDirectionWithMySqlNulls`; integration `SqlQueryParserTest::testStringFiltersAreCaseInsensitive` and `testStringFiltersAndAccents` (accent handling per database).
No existing DAL test changed its expectation because of the filters; `CriteriaQueryHelperTest` changed because of the NULL placement.

## Results of the suites

`tests/integration/Core/Framework/DataAbstractionLayer --order-by=default`, private databases `shopware_w6d_test`, run with no other phpunit process in the container, final code (`03e1d43300f`):

| Database | Result |
|---|---|
| PostgreSQL 18 | 804 tests, 5494 assertions, 2 failures |
| MariaDB 10.11 | 804 tests, 5495 assertions, OK |

The two PostgreSQL failures are known and not caused by this handoff: `RefreshIndexCommandTest::testExecuteWithSkipSeoUpdaterOption` (no storefront sales channel in the PostgreSQL test database) and `EntityDefinitionHasSinceTest::testAllDefinitionsHasSince` (leftover `custom_entity_test` row), both listed in the wave 6 README.
MySQL 8.4 has no `shopware_test` database and was not run.
Unit tests `tests/unit/Core/Framework/Adapter/Database` and `.../DataAbstractionLayer`: 1682 tests OK against PostgreSQL and against MariaDB.

Note for parallel sessions: two earlier runs that overlapped with phpunit processes of other sessions in the same container had 11 to 15 spurious failures in `Facade/*`, `AttributeEntityIntegrationTest` and `TranslationTest` (`language` row missing for a foreign key, changing tests from run to run, different cache ids did not help).
Running the same tests alone, or the whole suite with nothing else running, was clean; the cause of the interference was not analysed.

## Reset of the server settings

`log_min_duration_statement`, `work_mem` and `effective_cache_size` on `bench_pg` are reset (`pg_db_role_setting` has no row for the database), MariaDB `slow_query_log` 0, `long_query_time` 10, `log_output` FILE and an empty `mysql.slow_log`, container limits 8 CPU / 16 GiB, the php-fpm and caddy stacks of this handoff are stopped.
