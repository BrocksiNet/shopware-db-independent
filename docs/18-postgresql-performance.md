# PostgreSQL performance: why the storefront is slower than on MariaDB

Source: wave 5, handoff A.
Status: complete; the statement capture, the ranked causes, two fixes with before/after numbers, the open causes and the reset list are below.

## Method

- Stacks: the benchmark stacks `pg` (port 8102) and `mariadb` (port 8101) of `scripts/benchmark.sh`, snapshot of `instance/` at `bde8801404f`, databases `bench_pg` and `bench_mariadb` (catalog data set), warm object cache, non-persistent connections.
- Per scenario `scripts/capture-requests.py` warms the stack with 8 requests of the same scenario and then sends one request with a fresh ordinal (6000, sales channel 0, the same URL on both databases).
- PostgreSQL log: `ALTER DATABASE bench_pg SET log_min_duration_statement = 0`, so only that database logs.
  A statement is the sum of its `parse`, `bind` and `execute` durations, calls count the `execute` lines.
- MariaDB log: `log_output = TABLE`, `long_query_time = 0`, `slow_query_log = 1`, rows of `mysql.slow_log` with `db = 'bench_mariadb'`.
- `scripts/capture-statements.py` slices both logs by the request windows and joins the statements by their DAL comment tag (`product-listing-route::loading::read`) or, without a tag, by the SQL text with literals, `replace(x::text, '-', '')` and `lower(hex(x))` removed.
  Statements without a tag that look different on the two databases do not join and show `-`.
- The raw logs are 16 MB and 5 MB and not committed; the per statement result of each scenario is in `docs/benchmark-results/wave5-statements/*.json`.
- Logging every statement slows both sides, the request times here (one request each) are higher than the benchmark medians and are not benchmark results.
  The column "DB ms" is the sum of the statement times inside the database server, it does not contain network, driver or PHP time.
- Settings changed for the capture: `shared_buffers` 1 GB, `effective_cache_size` 3 GB, `work_mem` 16 MB, `maintenance_work_mem` 256 MB on PostgreSQL (`scripts/benchmark.sh settings`, restart), the per-database `log_min_duration_statement` (reset right after), the MariaDB slow log globals (reset right after).
  The list of what is reset at the end of the handoff is at the end of this document.

## Statement capture

Statement counts are almost equal on both databases (a difference of one per scenario, for the PostgreSQL count wrapper), so no extra statements (savepoints, per connection setup) explain the gap.
The time inside the PostgreSQL server is 2.3x to 6.5x the MariaDB time, and it is concentrated in a few statements.

| Scenario | Request ms PG | Request ms MariaDB | PG statements | MariaDB statements | PG DB ms | MariaDB DB ms |
|---|---:|---:|---:|---:|---:|---:|
| storefront home | 312 | 173 | 75 | 74 | 173 | 76 |
| storefront listing with filter | 299 | 94 | 65 | 64 | 188 | 29 |
| storefront search | 359 | 97 | 66 | 65 | 244 | 38 |
| storefront product detail | 383 | 115 | 83 | 82 | 223 | 44 |

Statements that did not join (untagged statements written differently on the two databases) cost, summed per scenario:

| Scenario | PostgreSQL only: calls / ms | MariaDB only: calls / ms |
|---|---:|---:|
| storefront home | 19 / 40 | 18 / 12 |
| storefront listing with filter | 14 / 51 | 13 / 5 |
| storefront search | 18 / 48 | 17 / 5 |
| storefront product detail | 25 / 68 | 24 / 11 |

The per-statement tables below show the 12 most expensive PostgreSQL statements of each scenario.

### storefront home

| Statement (PostgreSQL text) | PG calls | PG ms | MariaDB calls | MariaDB ms |
|---|---:|---:|---:|---:|
| `-- header::navigation::read SELECT REPLACE(category.id::text, '-', '') as category.id, REPLACE(category.versio` | 2 | 60.9 | 2 | 4.5 |
| `SELECT REPLACE(category.parent_id::text, '-', '') as category-ids.key, COUNT(category.id) as category-ids.coun` | 2 | 30.9 | - | - |
| `-- product-listing-route::loading::read SELECT REPLACE(product.id::text, '-', '') as product.id, REPLACE(produ` | 1 | 8.8 | 1 | 7.4 |
| `SELECT LOWER(HEX(app_feature.app_id)) AS app_id, app.name AS app_name, app.active AS app_active, app.version A` | 1 | 7.4 | 1 | 0.9 |
| `-- product-listing-route::loading::search-ids SELECT any_value(REPLACE(product.id::text, '-', '')) as id, any_` | 2 | 7.1 | 2 | 9.3 |
| `-- product-listing-route::loading::aggregation::properties SELECT REPLACE(product.properties.id::text, '-', ''` | 1 | 4.3 | 1 | 5.0 |
| `-- product-listing-route::loading::aggregation::price SELECT MIN(IFNULL(COALESCE((ROUND((ROUND(CAST((JSON_UNQU` | 1 | 3.7 | 1 | 5.1 |
| `-- product-listing-route::loading::aggregation::options SELECT REPLACE(product.options.id::text, '-', '') as o` | 1 | 3.3 | 1 | 2.9 |
| `-- category::data::read SELECT REPLACE(category.id::text, '-', '') as category.id, REPLACE(category.version_id` | 1 | 2.9 | 1 | 1.0 |
| `-- seo_url::replacement SELECT seo_path_info, path_info, sales_channel_id FROM seo_url WHERE (seo_url.is_canon` | 3 | 2.5 | 3 | 3.5 |
| `SELECT COUNT(*) FROM (-- product-listing-route::loading::search-ids SELECT any_value(REPLACE(product.id::text,` | 1 | 2.1 | - | - |
| `-- product-listing-route::loading::aggregation::rating-exists SELECT MAX(IFNULL(product.rating_average, produc` | 1 | 2.0 | 1 | 2.8 |

Unique statements: PostgreSQL 62, MariaDB 61, same text after normalisation 48.

### storefront listing with filter

| Statement (PostgreSQL text) | PG calls | PG ms | MariaDB calls | MariaDB ms |
|---|---:|---:|---:|---:|
| `-- header::navigation::read SELECT REPLACE(category.id::text, '-', '') as category.id, REPLACE(category.versio` | 2 | 81.4 | 2 | 2.6 |
| `SELECT REPLACE(category.parent_id::text, '-', '') as category-ids.key, COUNT(category.id) as category-ids.coun` | 2 | 46.1 | - | - |
| `-- seo-url::resolve SELECT id, path_info pathInfo, seo_path_info seoPathInfo, is_canonical isCanonical, sales_` | 3 | 11.3 | 3 | 1.5 |
| `-- product-listing-route::loading::search-ids SELECT any_value(REPLACE(product.id::text, '-', '')) as id, any_` | 1 | 4.7 | 1 | 2.0 |
| `-- category::data::read SELECT REPLACE(category.id::text, '-', '') as category.id, REPLACE(category.version_id` | 1 | 3.4 | 1 | 0.7 |
| `-- product-listing-route::loading::aggregation::properties SELECT REPLACE(product.properties.id::text, '-', ''` | 1 | 2.4 | 1 | 0.6 |
| `-- product-listing-route::loading::aggregation::options SELECT REPLACE(product.options.id::text, '-', '') as o` | 1 | 2.3 | 1 | 0.4 |
| `-- header::languages::search-ids SELECT any_value(REPLACE(language.id::text, '-', '')) as id FROM language LEF` | 1 | 2.3 | 1 | 0.4 |
| `-- seo_url::replacement SELECT seo_path_info, path_info, sales_channel_id FROM seo_url WHERE (seo_url.is_canon` | 3 | 2.0 | 3 | 2.4 |
| `SELECT custom_entity.name, custom_entity.fields, custom_entity.flags FROM custom_entity LEFT JOIN app ON app.i` | 1 | 1.8 | - | - |
| `-- footer-pagelet::shipping-methods::search-ids SELECT any_value(REPLACE(shipping_method.id::text, '-', '')) a` | 1 | 1.7 | 1 | 0.5 |
| `-- product-listing-route::loading::aggregation::price SELECT MIN(IFNULL(COALESCE((ROUND((ROUND(CAST((JSON_UNQU` | 1 | 1.6 | 1 | 0.7 |

Unique statements: PostgreSQL 52, MariaDB 51, same text after normalisation 43.

### storefront search

| Statement (PostgreSQL text) | PG calls | PG ms | MariaDB calls | MariaDB ms |
|---|---:|---:|---:|---:|
| `-- header::navigation::read SELECT REPLACE(category.id::text, '-', '') as category.id, REPLACE(category.versio` | 2 | 73.5 | 2 | 2.5 |
| `-- search::detect-keywords SELECT keyword, IF (lower(keyword) COLLATE ucs_basic LIKE $1 OR lower(keyword) COLL` | 1 | 58.3 | 1 | 7.7 |
| `SELECT REPLACE(category.parent_id::text, '-', '') as category-ids.key, COUNT(category.id) as category-ids.coun` | 2 | 40.1 | - | - |
| `-- search-page::read SELECT REPLACE(product.id::text, '-', '') as product.id, REPLACE(product.version_id::text` | 1 | 10.2 | 1 | 2.5 |
| `-- seo-url::resolve SELECT id, path_info pathInfo, seo_path_info seoPathInfo, is_canonical isCanonical, sales_` | 3 | 9.1 | 3 | 1.4 |
| `-- search-page::search-ids SELECT ranked.id, ranked.product_number, ranked.auto_increment, ranked._score FROM ` | 2 | 6.7 | 2 | 1.4 |
| `-- search-page::aggregation::options SELECT REPLACE(product.options.id::text, '-', '') as options.key, COUNT(p` | 1 | 4.0 | 1 | 0.9 |
| `-- search-page::aggregation::manufacturer SELECT REPLACE(IFNULL(product.product_manufacturer_id, product.paren` | 1 | 3.9 | 1 | 1.3 |
| `-- search-page::aggregation::properties SELECT REPLACE(product.properties.id::text, '-', '') as properties.key` | 1 | 3.9 | 1 | 0.9 |
| `-- search-page::aggregation::price SELECT MIN(IFNULL(COALESCE((ROUND((ROUND(CAST((JSON_UNQUOTE(JSON_EXTRACT(pr` | 1 | 3.2 | 1 | 1.4 |
| `-- search-page::aggregation::rating-exists SELECT MAX(IFNULL(product.rating_average, product.parent.rating_ave` | 1 | 2.6 | 1 | 0.9 |
| `-- header::languages::search-ids SELECT any_value(REPLACE(language.id::text, '-', '')) as id FROM language LEF` | 1 | 2.4 | 1 | 0.4 |

Unique statements: PostgreSQL 51, MariaDB 50, same text after normalisation 38.

### storefront product detail

| Statement (PostgreSQL text) | PG calls | PG ms | MariaDB calls | MariaDB ms |
|---|---:|---:|---:|---:|
| `-- header::navigation::read SELECT REPLACE(category.id::text, '-', '') as category.id, REPLACE(category.versio` | 2 | 77.3 | 2 | 3.1 |
| `SELECT REPLACE(category.parent_id::text, '-', '') as category-ids.key, COUNT(category.id) as category-ids.coun` | 2 | 30.7 | - | - |
| `SELECT REPLACE(product.id::text, '-', '') as id, REPLACE(child.id::text, '-', '') as child_id FROM product LEF` | 1 | 17.8 | - | - |
| `-- breadcrumb-builder::search-ids SELECT REPLACE(category.id::text, '-', '') as id, category.auto_increment FR` | 1 | 17.3 | 1 | 0.3 |
| `-- product-detail-route::read SELECT REPLACE(product.id::text, '-', '') as product.id, REPLACE(product.version` | 1 | 12.2 | 1 | 5.2 |
| `-- seo-url::resolve SELECT id, path_info pathInfo, seo_path_info seoPathInfo, is_canonical isCanonical, sales_` | 3 | 9.3 | 3 | 1.2 |
| `SELECT REPLACE(product.id::text, '-', '') as product.id, REPLACE(product.version_id::text, '-', '') as product` | 1 | 6.5 | - | - |
| `-- breadcrumb-builder::main-category::read SELECT REPLACE(product.id::text, '-', '') as product.id, REPLACE(pr` | 1 | 4.2 | 1 | 1.6 |
| `SELECT any_value(REPLACE(product.id::text, '-', '')) as id, any_value(product.product_number) as product_numbe` | 1 | 3.1 | - | - |
| `-- product-detail-route::association::properties::read SELECT REPLACE(property_group_option.id::text, '-', '')` | 1 | 3.0 | 1 | 0.5 |
| `-- product-detail-route::association::mainCategories::read SELECT REPLACE(main_category.id::text, '-', '') as ` | 1 | 2.1 | 1 | 0.5 |
| `-- product-detail-route::find-best-variant::search-ids SELECT REPLACE(product.id::text, '-', '') as id, produc` | 1 | 2.0 | 1 | 0.4 |

Unique statements: PostgreSQL 69, MariaDB 68, same text after normalisation 49.

## Timing note on the statement capture

PostgreSQL went through crash recovery at 15:24 UTC (postmaster start 15:24:20 UTC; psql processes of another session were killed), and the statement capture above was taken at 15:27 UTC, shortly after, with a partly cold buffer cache.
Each captured request was preceded by 8 warm-up requests of the same scenario, but the per statement milliseconds of the capture tables (PG column) may be somewhat inflated by the restart and were not repeated.
The ranking of the causes does not rest on those numbers alone: the plans were measured with `EXPLAIN (ANALYZE)` later, and the before/after benchmark runs were taken between 15:50 and 16:20 UTC, outside the window.

## Ranked causes

Numbers are milliseconds per request, taken from the captured request (logging on, so inflated) and from `EXPLAIN (ANALYZE)` of the captured statements with their parameters.
Every cause was checked with a plan or a measurement.

| Rank | Cause | Scenarios | ms per request on PostgreSQL | MariaDB for the same work | Status |
|---|---|---|---:|---:|---|
| 1 | `category.path LIKE '%\|id\|%'` in `header::navigation::read` (2 calls per request) on the nondeterministic ICU collation `ci`: seq scan over about 500 categories, every row compared through ICU, 24-26 ms per call, about 0.3 ms with a deterministic collation | all four | 50-60 | 4.5 | fixed |
| 2 | Keyword lookup `search::detect-keywords`: about 96 OR-ed `lower(col) COLLATE ucs_basic LIKE` clauses over about 4,450 dictionary rows evaluate `lower()` in every clause (58 ms against 7.7 ms); a trigram index cannot serve the prefix patterns | search | 50 | 7.7 | fixed |
| 3 | Cold backend per request on non-persistent connections: PDO connect 7.1 ms (MariaDB 1.0 ms), first use of the ICU collator about 7.7 ms per backend, cold catalog and plan caches (home statements: planning 30-41 ms cold against 15 ms warm, execution 23 against 13 ms), about 36 ms plus connect per request | all four | 40-45 | 1 | open (persistent connections or a pooler) |
| 4 | Planning cost of wide DAL statements; the sum of the warm planning times is 15 (home), 23 (listing), 31 (search), 68 ms (detail); the 19-join product detail statement plans in about 5 ms warm and 15-48 ms cold, on a persistent connection the `bind` sums stay at 41-100 ms because planning is inherent to the SQL shape | all four, most on detail | 15-68 warm | below 3 (MariaDB parse and optimize) | open |
| 5 | Untagged statements that do not join between the databases (see table above): 40-68 ms against 5-12 ms | all four | about 20 over the join table | | open, not analysed per statement |

Hypotheses of the handoff that were rejected by measurement:

- PL/pgSQL functions of `mysql-compat.sql`: the schema has one PL/pgSQL function (`json_valid(text)`) and a DO block; every function used in the storefront statements is `LANGUAGE sql IMMUTABLE`, so they inline.
- `json` instead of `jsonb`: all 220 JSON columns are `jsonb`.
- Missing indexes behind foreign keys: of 418 foreign keys none is without an index that starts with the foreign key column.
- Different statement count (savepoints, `SET` per connection): 75 against 74, 65 against 64, 66 against 65, 83 against 82.
- Generic plans: the captured request uses unnamed statements, planning happens in `bind` every time (see cause 4).
- Translator and id codec: below 10 % of the request, as in the probe pass of the benchmark.

`bench_pg` lacked the wave 4 migration `Migration1795000000PostgreSqlCaseInsensitiveSearchIndexes` (no `pg_trgm`, no `ucs_basic` indexes); I created those indexes by hand to test them, they did not help the keyword query, and I dropped them again.

## Fixes

### 1. Deterministic collation for `category.path`

`Migration1795000100PostgreSqlCategoryPathCollation` (PostgreSQL only, no-op on every other platform and when the column already uses `ucs_basic`) changes `category.path` to `text COLLATE ucs_basic`.
`path` holds `|hex|hex|` of lowercase hex ids, so the result of the `LIKE` is the same as with `ci`.
The migration runs through the native connection because `ALTER TABLE` of a column type is outside the translator.

### 2. One `lower()` per dictionary row in the keyword lookup

`KeywordLoader::fetch()` reads `lower(keyword)` and `lower(reversed)` once per row in a derived table with `OFFSET 0`, and the LIKE clauses use the two columns.
The fence comes from the new method `SqlDialect::subqueryFence()` (`' OFFSET 0'` on PostgreSQL, empty string on MySQL, MariaDB and SQLite); on those three the query shape is unchanged.
Measured on the captured statement: about 7 ms with the fence (a `MATERIALIZED` CTE gives the same), 60-90 ms before.
The unit test `KeywordLoaderTest::testFetchLowersTheDictionaryOncePerRowOnPostgreSql` guards the shape.

No translator rule was added.

### Before and after

Method: `scripts/benchmark.sh run --only "<scenario>" --stacks mariadb,pg --no-throughput --no-probes --dataset catalog` with `RUNS=3` per scenario, repeated 3 times; the table shows the median of the 3 repetitions, in brackets the range of the 3 repetitions.
Before: snapshot `bde8801404f`, `bench_pg` unchanged.
After: snapshot `689f915b106` (contains the two fixes) and `ALTER TABLE category ALTER COLUMN path TYPE text COLLATE ucs_basic` applied to `bench_pg`.
The snapshot at `689f915b106` contains commit `b4f6492fdf5` of handoff C (numeric JSON extract for price accessors), which fails on `bench_pg` (`jsonb_path_query_first(text, jsonpath) does not exist`, HTTP 500, `bench_pg` price columns are not `jsonb` there), so for the measurement I restored the price accessor builders and their two service definition files to the state of `bde8801404f` inside the snapshot (`/tmp/bench-src`, not in the repository).
That failure is not part of this handoff and needs a look by handoff C.

| Scenario | PG before ms | PG after ms | PG change | MariaDB before ms | MariaDB after ms | PG / MariaDB before | PG / MariaDB after |
|---|---:|---:|---:|---:|---:|---:|---:|
| storefront home | 302.5 (297-337) | 184.2 (175-217) | -39 % | 128.9 (123-137) | 111.1 (108-130) | 2.35 | 1.66 |
| storefront listing with filter | 228.9 (223-229) | 125.8 (122-133) | -45 % | 78.6 (70-82) | 69.3 (64-70) | 2.91 | 1.82 |
| storefront search | 299.0 (296-308) | 152.5 (148-165) | -49 % | 95.8 (94-96) | 77.1 (77-81) | 3.12 | 1.98 |
| storefront product detail | 329.2 (326-343) | 180.2 (178-192) | -45 % | 110.0 (107-112) | 93.9 (88-104) | 2.99 | 1.92 |

Noise: the machine ran other sessions in parallel; the repetitions of one cell differ by up to 15 % (home before and after, detail after on MariaDB).
MariaDB shows no slowdown, it is 8-20 % faster in the second run, which is the noise of the shared machine and not an effect of the change (the fixes do not change any MariaDB statement).
The unit tests of both fixes pass on MySQL as well as on PostgreSQL.
The final numbers come from handoff F.

Verification: adapter tests (185) and `KeywordLoaderTest` green on PostgreSQL and MySQL, `scripts/check-migrations-on-postgresql.sh` reports 0 schema differences, php-cs-fixer ran on the touched files, PHPStan reports no error in the touched files.

## Open causes

| Cause | Effort | Proposed owner |
|---|---|---|
| Cold backend per request (connect 7 ms, ICU initialisation 7.7 ms, cold caches, about 36 ms): persistent connections (`DATABASE_PERSISTENT_CONNECTION`) or PgBouncer in transaction mode with plain statements; measured in the wave 4 persistent runs, which do not close the gap alone because planning stays | small as configuration, medium for a documented default | wave 5 F / docs |
| Planning of wide DAL statements (15-68 ms warm per request): `join_collapse_limit = 1` saves about 40 % on the 19-join detail statement, but changes plans of every query and is risky; real remedies are fewer joins per statement (read path of the DAL) or prepared statements with a plan cache (a server prepared statement per DAL template) | large | later wave |
| The `ci` collation makes every `Contains`, `Prefix`, `Suffix` and `Equals` filter built by `SqlQueryParser` on a string column slow (seq scan through ICU, each `LIKE` about 50 times slower than on `ucs_basic`); I changed only `category.path` because for the other columns the accent and case semantics of `ci` is the behaviour users see in search and filters | medium, needs a decision on semantics (functional indexes on `lower(col) COLLATE ucs_basic` exist from the wave 4 migration but only serve case-insensitive matches) | decision first |
| Untagged statements that do not join (cause 5) | medium, needs per statement EXPLAIN | wave 5 F |

## Settings changed and reset

| Setting | Changed by | State at the end |
|---|---|---|
| PostgreSQL `shared_buffers` 1 GB, `effective_cache_size` 3 GB, `work_mem` 16 MB, `maintenance_work_mem` 256 MB (`ALTER SYSTEM`, restart) | `scripts/benchmark.sh settings` | left as set, they are the benchmark baseline of all wave 5 runs and handoff F needs them; `ALTER SYSTEM RESET` plus a restart removes them |
| MariaDB `sort_buffer_size`, `tmp_table_size`, `max_heap_table_size` 16 MiB (`SET GLOBAL`) | `scripts/benchmark.sh settings` | left as set for the same reason, a restart of `instance-database-1` resets them |
| PostgreSQL `log_min_duration_statement = 0` on `bench_pg` (`ALTER DATABASE`) | capture | reset (`ALTER DATABASE bench_pg RESET log_min_duration_statement`) |
| MariaDB `slow_query_log`, `long_query_time`, `log_output` | capture | reset; `mysql.slow_log` was truncated |
| `bench_pg`: extension `pg_trgm` and the test indexes | experiments | dropped |
| `bench_pg`: `category.path` collation | fix 1 | `ucs_basic` (the migration does the same on any install) |
| Container limits of the database containers | harness | 8 CPUs / 16 GiB, as before |

Background processes: the benchmark stacks of `scripts/benchmark.sh stacks` were stopped with `stop-stacks`.
