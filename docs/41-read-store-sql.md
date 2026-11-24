# Read store on SQL JSON columns (wave 9, handoff S)

Handoff S of wave 9: one adapter for MySQL 8.4, MariaDB 10.11, PostgreSQL 18 and SQLite (`docs/38-read-store-plan.md`).
The adapter implements the port of `docs/40-read-store-port-and-document.md`.

## Status

| Milestone | Commit in `instance/` (`poc/read-store`) | Contents |
|---|---|---|
| Adapter ready | `6569e8606a1 feat(core): add SQL JSON read store adapters for MySQL, MariaDB, PostgreSQL and SQLite` | Adapter, compiler, four dialects, services, contract tests |
| Milestone 2 alignment | `208a0ea fix(core): align SQL read store scoring, collapse and bucket tie-breaking` | Context-language `score()`, scored collapse, ascending-key `Terms` tie-break |
| Indexing & Milestone 2 | `ae2cee9 perf(core): add promoted scalar and native JSON array indexes to SQL read store` | Promoted `active`, `manufacturer_id`, `display_group` columns, MySQL 8.4 multi-valued JSON indexes, PostgreSQL 18 GIN JSONB indexes, rebuild/verify/corpus/timings |

## Code layout

All code lives in `src/Core/Framework/ReadStore/Adapter/Sql/` and is `@internal`, package `framework`.

| File | Contents |
|---|---|
| `SqlStorage.php` | `Storage`, `FilterAware`, `SearchAware` and `AggregationAware` for any dialect; generations, queries, aggregations |
| `SqlQueryCompiler.php` | Filters, search, score, sort keys and group key as SQL; every field goes through `FieldResolver` |
| `JsonDialect.php` | The interface of everything that differs per engine |
| `MySqlJsonDialect.php`, `MariaDbJsonDialect.php`, `PostgreSqlJsonDialect.php`, `SqliteJsonDialect.php` | One dialect per engine, MariaDB extends MySQL |
| `Binder.php` | Named parameters, a placeholder is never used twice |
| `SqlScope.php`, `SqlSortKey.php` | Value objects of the compiler |
| `SqlConnectionFactory.php` | A plain DBAL connection from a URL and the dialect by name |
| `DependencyInjection/s.php` | The services `read_store.storage.sql-mysql`, `sql-mariadb`, `sql-pgsql` and `sql-sqlite` |

The adapter uses its own plain DBAL connection and not the Shopware connection.
The SQL is native to each engine and must not pass the PostgreSQL translator middleware.

## Tables and generations

A generation is a pair of tables, `<prefix>_<generation>` for the documents and `<prefix>_<generation>_kw` for the search keywords.
One table `<prefix>_meta` holds the live pointer (`live`) and one row `gen:<generation>` for every existing generation.
The live pointer is read from the database on every call, so every process sees a swap of another process.
`setup()` drops and creates the two tables of the generation.
`swap()` writes the pointer, drops the tables of the old live generation and deletes its meta row.
`store()` without a generation writes to the live and to every pending generation, `store()` with a generation writes to that one.
The document id is stored in lower case, `get()` and `mget()` lower case the id they look up and return the document under the requested id.
The generation name must match `[A-Za-z0-9_]+` and prefix plus name plus `_kw` must stay within 63 characters.

## DDL per engine

The document table keeps the insertion order in `seq` (MySQL, MariaDB, PostgreSQL) or in the implicit `rowid` (SQLite).
A document replaced by an upsert keeps its position, the same as the Array adapter.
In milestone 2 (`ae2cee9`), three hot scalar filter/group fields were promoted to nullable indexed columns on every engine (`active`, `manufacturer_id`, `display_group`), populated directly from the document in `storeChunk()`, and native JSON array indexes were added where the engine supports them: MySQL 8.4 multi-valued functional indexes (`CAST(doc->'$.<field>' AS CHAR(64) ARRAY)`) and PostgreSQL 18 `GIN` indexes on `(doc->'<field>')` for `categoryTree`, `propertyIds`, and `optionIds`.
In positive filter contexts (not inside `NOT` and without `null` as a candidate), `SqlQueryCompiler` omits the `COALESCE(..., FALSE)` wrapper and delegates list containment to `JsonDialect::indexedArrayContains()` so the planner uses the B-tree, multi-valued, or GIN indexes directly while preserving exact Kleene three-valued logic under `NOT`.

### MySQL 8.4

```sql
CREATE TABLE `<prefix>_<generation>` (
    seq BIGINT NOT NULL AUTO_INCREMENT,
    id VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    active TINYINT(1) NULL,
    manufacturer_id VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL,
    display_group VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL,
    doc JSON NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY `<table>_seq` (seq),
    KEY `<table>_active` (active),
    KEY `<table>_manufacturer` (manufacturer_id),
    KEY `<table>_display_group` (display_group),
    KEY `<table>_cat` ((CAST(doc->'$.categoryTree' AS CHAR(64) ARRAY))),
    KEY `<table>_prop` ((CAST(doc->'$.propertyIds' AS CHAR(64) ARRAY))),
    KEY `<table>_opt` ((CAST(doc->'$.optionIds' AS CHAR(64) ARRAY)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `<prefix>_<generation>_kw` (
    product_id VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    language_id VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    keyword_fold VARCHAR(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    ranking DOUBLE NOT NULL,
    KEY `<table>_product` (product_id),
    KEY `<table>_lookup` (language_id, keyword_fold)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

All id columns (`id`, `manufacturer_id`, `display_group`, `kw.product_id`, `kw.language_id`) share `utf8mb4 COLLATE utf8mb4_bin` so joins with `d.id = kw.product_id` and `COLLATE utf8mb4_bin` expressions never trigger collation mismatches (`ERROR 1253`) or prevent index usage on `kw.product_id`.
Upsert: `INSERT ... (id, active, manufacturer_id, display_group, doc) ... ON DUPLICATE KEY UPDATE ...`.

### MariaDB 10.11

The tables match MySQL except for the document column and the absence of multi-valued indexes (MariaDB 10.11 has neither functional/multi-valued JSON indexes nor `MEMBER OF`):

```sql
doc LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (JSON_VALID(doc))
```

MariaDB 10.11 has no native `JSON` type; the keyword `JSON` is an alias for `LONGTEXT` with this check.
The `CHECK` has to follow `NOT NULL`, with the check before it the statement is a syntax error (run on MariaDB 10.11, first contract run).

### PostgreSQL 18

```sql
CREATE COLLATION IF NOT EXISTS rs_unicode_ci (provider = icu, locale = 'und-u-ks-level1', deterministic = false);

CREATE TABLE "<prefix>_<generation>" (
    seq BIGSERIAL NOT NULL,
    id TEXT COLLATE "C" NOT NULL PRIMARY KEY,
    active SMALLINT NULL,
    manufacturer_id TEXT COLLATE "C" NULL,
    display_group TEXT COLLATE "C" NULL,
    doc JSONB NOT NULL
);
CREATE INDEX "<table>_active" ON "<table>" (active);
CREATE INDEX "<table>_manufacturer" ON "<table>" (manufacturer_id);
CREATE INDEX "<table>_display_group" ON "<table>" (display_group);
CREATE INDEX "<table>_cat" ON "<table>" USING GIN ((doc->'categoryTree'));
CREATE INDEX "<table>_prop" ON "<table>" USING GIN ((doc->'propertyIds'));
CREATE INDEX "<table>_opt" ON "<table>" USING GIN ((doc->'optionIds'));

CREATE TABLE "<prefix>_<generation>_kw" (
    product_id TEXT COLLATE "C" NOT NULL,
    language_id TEXT COLLATE "C" NOT NULL,
    keyword_fold TEXT COLLATE "C" NOT NULL,
    ranking DOUBLE PRECISION NOT NULL
);
CREATE INDEX "<table>_product" ON "<table>" (product_id);
CREATE INDEX "<table>_lookup" ON "<table>" (language_id, keyword_fold);
```

The collation `rs_unicode_ci` is created in the database of the connection by `setup()` (`IF NOT EXISTS`) and stays when the generations are dropped.
Positive list containment compiles to `(d.doc->'categoryTree') @> jsonb_build_array(CAST(:p AS TEXT))`, which matches the `GIN` expression index directly and evaluates to `FALSE` (not `TRUE`) on bare scalar strings.
Upsert: `INSERT ... ON CONFLICT (id) DO UPDATE SET active = EXCLUDED.active, manufacturer_id = EXCLUDED.manufacturer_id, display_group = EXCLUDED.display_group, doc = EXCLUDED.doc`.

### SQLite

```sql
CREATE TABLE "<prefix>_<generation>" (
    id TEXT NOT NULL PRIMARY KEY,
    active INTEGER NULL,
    manufacturer_id TEXT NULL,
    display_group TEXT NULL,
    doc TEXT NOT NULL CHECK (json_valid(doc))
);
CREATE INDEX "<table>_active" ON "<table>" (active);
CREATE INDEX "<table>_manufacturer" ON "<table>" (manufacturer_id);
CREATE INDEX "<table>_display_group" ON "<table>" (display_group);

CREATE TABLE "<prefix>_<generation>_kw" (product_id TEXT NOT NULL, language_id TEXT NOT NULL, keyword_fold TEXT NOT NULL, ranking REAL NOT NULL);
CREATE INDEX "<table>_product" ON "<table>" (product_id);
CREATE INDEX "<table>_lookup" ON "<table>" (language_id, keyword_fold);
```

The dialect registers a function `rs_fold` (`QueryEvaluator::fold()`) and a collation `rs_unicode` (ICU `root`, primary strength) on the PDO connection through `Pdo\Sqlite::createFunction()` and `createCollation()`.
This needs PHP 8.4 (`Pdo\Sqlite`), on another connection class the dialect throws `NotSupportedByEngine`.
Upsert: `INSERT ... ON CONFLICT (id) DO UPDATE SET doc = excluded.doc`.

## How a query maps to SQL

Every field goes through `FieldResolver::resolve()`, so `price`, `cheapestPrice` and the rounding check of the port behave exactly as in the Array adapter.
The resolved paths become JSON paths bound as parameters, several paths (`cheapestPrice` per rule) are combined with `COALESCE`.
A value has a type only when the JSON value has that type, a JSON `null` and a missing key are both SQL `NULL`.
Filter expressions are three valued like the reference, a document matches when the expression is true.

| Reference | MySQL, MariaDB | PostgreSQL | SQLite |
|---|---|---|---|
| Text of a value | `CASE WHEN JSON_TYPE(JSON_EXTRACT(doc, path)) = 'STRING' THEN JSON_UNQUOTE(...)` | `doc #>> path` guarded by `jsonb_typeof` | `json_extract` guarded by `json_type` |
| Number | `CAST(... AS DOUBLE)` | `CAST(... AS DOUBLE PRECISION)` | `CAST(... AS REAL)` |
| Case and accent insensitive equals | `COLLATE utf8mb4_unicode_ci` | `COLLATE rs_unicode_ci` | `rs_fold(x) = :folded` |
| Contains, prefix | `LIKE` with `utf8mb4_unicode_ci`, escaped pattern | `LIKE` with `rs_unicode_ci` | `instr(rs_fold(x), needle)` or `substr` |
| List contains | `JSON_CONTAINS(JSON_EXTRACT(doc, path), JSON_QUOTE(:v))` | `@>` with `to_jsonb` | `EXISTS` over `json_each` |
| Terms on a list | `JSON_TABLE` | `jsonb_array_elements_text` | `json_each` |
| Null order | natural | `NULLS FIRST` for `ASC`, `NULLS LAST` for `DESC` | `NULLS FIRST` for `ASC`, `NULLS LAST` for `DESC` |
| Unbounded `LIMIT` | `18446744073709551615` | `ALL` | `-1` |

Ids are compared as lower case bytes (`COLLATE "C"`, `ascii_bin`, `LOWER()` with a binary collation).
The keyword table holds one row per keyword with the keyword folded by `QueryEvaluator::fold()` in PHP, so the keyword match is a byte comparison on every engine.
The score is a scalar subquery over the keyword rows of all languages, as in `QueryEvaluator::score()`.
A collapse is a `ROW_NUMBER() OVER (PARTITION BY group ORDER BY sort keys, id)` plus `MIN` or `MAX` window functions for the group order, the paging comes after the collapse.
Each aggregation is one query over the filters, ids and search term plus the filters of the aggregation, post filters do not apply to aggregations.

## Dialect gaps found

| Gap | Engine | Evidence |
|---|---|---|
| `JSON_VALUE` returns `NULL` for a string of 1000 characters because its default return type is `VARCHAR(512)` | MySQL | Probe in `orm_spike`; the adapter uses `JSON_UNQUOTE(JSON_EXTRACT())` |
| `JSON_VALUE` returns `1` and `0` for booleans, MySQL returns `true` and `false` | MariaDB | Probe; the adapter reads booleans through `JSON_UNQUOTE(JSON_EXTRACT())` on both |
| `JSON_VALUE` on an object or an array is `NULL` | MariaDB | Probe |
| `MEMBER OF` and functional indexes are syntax errors | MariaDB | Probe; the adapter uses `JSON_CONTAINS` |
| A multi-valued index (`CAST(... AS CHAR(64) ARRAY)`) is accepted and used by `MEMBER OF`, but throws `ERROR 3903 (22018)` if a document writes explicit JSON `null` into the indexed array key | MySQL | Probe on MySQL 8.4 (`{"categoryTree": null}` rejected, missing key `{}` and `[]` accepted); safe for product documents because `ProductDocumentBuilder` always emits JSON arrays |
| Charset mismatch between `d.id` (`utf8mb4_bin`) and `kw.product_id` (`ascii_bin`) silently prevents MariaDB/MySQL from using `kw_product` in correlated `EXISTS` subqueries | MySQL, MariaDB | `EXPLAIN` on MariaDB 10.11 during `rs_k_corpus` run; fixed by aligning all id columns to `utf8mb4 COLLATE utf8mb4_bin` |
| The jsonb operator `?` is read as a PDO placeholder | PostgreSQL | Probe; the adapter uses `@>` |
| `LIKE '%strasse%'` is true for `Straße` with the ICU collation, false in the reference (no `ß` expansion) | PostgreSQL | Probe with `rs_unicode_ci` |
| `=` and `COUNT(DISTINCT)` with `utf8mb4_unicode_ci` treat `ß` as `ss`, the reference fold does not | MySQL, MariaDB | Probe: `'Straße' = 'strasse'` is true |
| `LIKE '%strasse%'` is false for `Straße`, like the reference | MySQL, MariaDB | Probe |
| Collation order for exotic punctuation may differ from ICU `root` primary | MySQL, MariaDB, PostgreSQL | Not measured, the order of sorts and terms is only compared on the contract fixtures |
| JSON key order is not kept (MySQL `JSON`, PostgreSQL `jsonb`), `get()` returns the same values with sorted keys | MySQL, PostgreSQL | Contract assertions compare arrays without key order |
| `Terms` with a limit keeps the larger key of buckets with the same count | all | `QueryEvaluator::buckets()` sorts equal counts by descending key (checked with four buckets of two documents, the evaluator returns `cc` and `dd` for a limit of 2), the adapter does the same in PHP |

The generation of the terms buckets and the ordering of buckets happen in PHP with the ICU `root` collator at primary strength, the same as `QueryEvaluator`.
All buckets are fetched and then sliced in PHP.
Pushing the limit down into SQL is a milestone 2 question.

## Capability matrix

The compiler is shared, so the matrix is the same for the four engines.
`NotSupportedByEngine` is thrown for anything the SQL cannot answer exactly, the caller falls back to the DAL.

| Feature | Answered | `NotSupportedByEngine` |
|---|---|---|
| `Storage` (`setup`, `swap`, `store`, `remove`, `get`, `mget`, `clear`, `destroy`) | yes | no |
| `filter()` without search term | yes | with a search term (the Array adapter does the same, use `search()`) |
| `search()` or-logic and and-logic, score | yes | no |
| `Equals`, `EqualsAny` on id, string, translated string, int, float, bool, datetime, list | yes | a non string candidate on an id, string, datetime, list or custom field |
| `Equals` on a custom field | yes, with string candidates | other candidates |
| `Contains`, `Prefix` | on id, string, text, datetime | on numbers, bool, lists, custom fields |
| `Range` | on int, float, id, datetime, string, text | on bool, lists, custom fields; a non numeric bound on a number; a non string bound on a string |
| `Multi`, `Not` | yes | no |
| Sorting | on scalar fields and `_score` | on lists, custom fields |
| Collapse | on id fields | other types |
| `Total::EXACT` | yes | no |
| `price`, `cheapestPrice` | yes when the context rounds like the currency | otherwise, thrown by `FieldResolver` |
| `Terms` | on scalar fields and lists, null bucket included | custom fields |
| `Min`, `Max` | numbers, bool, id, datetime | strings (ties of a collation have no exact answer), lists, custom fields |
| `Avg`, `Sum`, `Stats` | numbers and bool | strings, lists, custom fields |
| `Count` | numbers, bool, id, datetime, strings | lists, custom fields |
| Queries without a live generation | throw `ReadStoreException::noLiveGeneration()` | the Array adapter returns an empty result instead |

`Min`, `Max`, `Avg`, `Sum` and `Stats` convert numbers to `DOUBLE`, integers above 2^53 would lose precision.
The sum and the average add doubles in the order of the engine, the Array adapter adds them in the order of the documents.

## Contract results

The contract suite of `docs/40-read-store-port-and-document.md` runs per engine in `tests/unit/Core/Framework/ReadStore/Adapter/Sql/` (`MySqlStorageTest`, `MariaDbStorageTest`, `PostgreSqlStorageTest`, `SqliteStorageTest`).
Each class adds seven tests of its own (five unsupported queries, a missing live generation, a second instance that sees the live generation).
A class is skipped when its database is not reachable.

| Engine | Database | Result |
|---|---|---|
| MySQL 8.4 | `mysql://mysql:3306/orm_spike` | 57 tests, 208 assertions, all passed, none incomplete |
| MariaDB 10.11 | `mysql://database:3306/orm_spike` | 57 tests, 208 assertions, all passed, none incomplete |
| PostgreSQL 18 | `pgsql://postgres:5432/orm_spike` | 57 tests, 208 assertions, all passed, none incomplete |
| SQLite | `/var/www/html/var/switch/rs_test.sqlite` | 57 tests, 208 assertions, all passed, none incomplete |

The tests use the table prefix `rs_test` and drop their tables in `tearDown()`.

## Services

`DependencyInjection/s.php` registers `read_store.storage.sql-mysql`, `sql-mariadb`, `sql-pgsql` and `sql-sqlite` with the tag `read_store.storage` and the attribute `key`.
Each service gets its own connection from the environment variable `READ_STORE_SQL_MYSQL_URL`, `READ_STORE_SQL_MARIADB_URL`, `READ_STORE_SQL_PGSQL_URL` or `READ_STORE_SQL_SQLITE_URL`, with defaults in the file.
A container built from `readstore.php` and `s.php` alone instantiates the MySQL and SQLite services and lists five tagged storages (run in the web container).
The compiled container of the running Shopware instance has to be rebuilt to contain them.

## Timings, sizes and verify

All milestone 2 timings below are sanity runs (`other lanes stopped: no`, `APP_ENV=prod`, MySQL 8.4 write DB, separate `read_store` DB except where noted).
Canonical stopped-lanes timings belong to handoff F.

### Rebuild, `--verify`, and 35-entry criteria corpus

On `orm_spike` (5,000 products), all four engines pass `orm-spike:bench --verify` on S1, S2, S3, S5 and R4; R3b matches every hit and aggregation except DAL finding 36 (`manufacturers` count 71 vs DAL 73).
On `rs_k_corpus` (35 criteria entries from `docs/40-read-store-port-and-document.md`), all four engines pass identically:

| Store | `--verify` (`orm_spike`) | Criteria corpus (`rs_k_corpus`, 35 entries) |
|---|---|---|
| `store-sql-mysql` | S1, S2, S3, R4, S5 OK; R3b finding 36 only | 28 match, 5 dal-defect, 2 fallback, 0 diff |
| `store-sql-mariadb` | S1, S2, S3, R4, S5 OK; R3b finding 36 only | 28 match, 5 dal-defect, 2 fallback, 0 diff |
| `store-sql-pgsql` | S1, S2, S3, R4, S5 OK; R3b finding 36 only | 28 match, 5 dal-defect, 2 fallback, 0 diff |
| `store-sql-sqlite` | S1, S2, S3, R4, S5 OK; R3b finding 36 only | 28 match, 5 dal-defect, 2 fallback, 0 diff |

### Indexing impact on `orm_spike` (5,000 products)

Unindexed JSON scans (`208a0ea`) versus promoted scalar columns + native JSON array indexes (`ae2cee9`), 5 warm-up and 50 measured iterations, median / p95 in ms (write-DB statements in parentheses; host load ~6.5–7.5, other lanes stopped: no):

| Store | Layout | R7 rebuild | S1 | S2 | S3 | R3b | R4 |
|---|---|---|---|---|---|---|---|
| `sql-mysql` (separate DB) | unindexed JSON | 4.4 s (1,143/s) | 18.61 / 25.25 (0) | 0.22 / 0.30 (0) | 30.91 / 35.66 (0) | 26.15 / 33.10 (2) | 1.26 / 1.58 (0) |
| `sql-mysql` (same DB `orm_spike`) | unindexed JSON | 2.6 s (1,898/s) | 15.66 / 18.39 (0) | 0.21 / 0.27 (0) | 26.99 / 31.43 (0) | 24.38 / 30.71 (2) | 1.08 / 1.34 (0) |
| `sql-mysql` (separate DB) | **indexed (`ae2cee9`)** | 3.2 s (1,563/s) | **4.00 / 5.07** (0) | 0.23 / 0.32 (0) | 48.06 / 58.31 (0) | 26.12 / 38.49 (2) | 2.11 / 3.74 (0) |
| `sql-mariadb` | unindexed `LONGTEXT` | 2.4 s (2,102/s) | 381.20 / 423.90 (0) | 0.24 / 0.31 (0) | 618.40 / 737.38 (0) | 987.16 / 1061.28 (2) | 0.88 / 1.25 (0) |
| `sql-mariadb` | **indexed (`ae2cee9`)** | 2.8 s (1,786/s) | 391.22 / 476.37 (0) | 0.19 / 0.29 (0) | **117.10 / 136.15** (0) | **213.35 / 253.87** (2) | 0.88 / 1.21 (0) |
| `sql-pgsql` | unindexed TOAST `JSONB` | 2.7 s (1,885/s) | 796.58 / 954.73 (0) | 0.26 / 0.54 (0) | 981.09 / 1169.87 (0) | 1891.34 / 2289.72 (2) | 2.60 / 4.34 (0) |
| `sql-pgsql` | **indexed (`ae2cee9`)** | 3.2 s (1,563/s) | **28.62 / 46.79** (0) | 0.30 / 0.43 (0) | **124.06 / 144.58** (0) | **378.90 / 517.56** (2) | 1.73 / 1.99 (0) |
| `sql-sqlite` | unindexed `TEXT` | 2.6 s (1,899/s) | 192.92 / 235.19 (0) | 0.05 / 0.09 (0) | 288.84 / 383.05 (0) | 4390.09 / 5079.23 (2) | 0.57 / 0.82 (0) |
| `sql-sqlite` | **indexed (`ae2cee9`)** | 3.2 s (1,563/s) | 200.54 / 536.46 (0) | 0.05 / 0.07 (0) | 322.24 / 726.09 (0) | 3973.59 / 7061.71 (2) | 0.51 / 0.63 (0) |

Key takeaways from the indexing comparison:

- **PostgreSQL 18**: GIN indexes on `categoryTree`/`propertyIds`/`optionIds` plus promoted scalar columns cut S1 by **27.8×** (796.6 → 28.6 ms), S3 by **7.9×** (981.1 → 124.1 ms), and R3b by **5.0×** (1,891.3 → 378.9 ms) by avoiding TOAST decompression of non-matching 4.5 KB `JSONB` blobs.
- **MySQL 8.4**: multi-valued JSON index on `categoryTree` cut S1 by **4.7×** (18.6 → 4.0 ms); placing the read-store tables in the same database versus a separate database on the same MySQL server changes latency by only ~1–3 ms.
- **MariaDB 10.11**: promoted `manufacturer_id`/`display_group` cut S3 by **5.3×** (618.4 → 117.1 ms) and R3b by **4.6×** (987.2 → 213.4 ms), but without native JSON array indexes S1 still scans every `LONGTEXT` row (~391 ms on 5k).
- **SQLite 3.51**: fastest single-key/mget reads (0.05 ms S2, 0.51 ms R4 in-process), but lacks JSON array indexes and suffers severely on correlated keyword scoring subqueries (`R3b` ~4.0 s on 5k).

### Rebuild and table/index sizes on `read_store_large` (150,000 products)

Sequential rebuild (`SqlDocumentBuilder`, batch 500, 6,004 write-DB statements per rebuild), measured with `ae2cee9` indexes on `read_store_large` (each store dropped after measuring):

| Engine | R7 total | Docs/s | Doc table (data + idx) | Keyword table (data + idx) | Total size on disk |
|---|---|---|---|---|---|
| MySQL 8.4 (`sql-mysql`) | 115.3 s | 1,301 | 1,108.0 + 86.6 = 1,194.6 MiB | 182.7 + 198.7 = 381.4 MiB | **1,576.0 MiB** |
| MariaDB 10.11 (`sql-mariadb`) | 82.7 s | 1,813 | 877.0 + 51.4 = 928.4 MiB | 177.7 + 182.7 = 360.4 MiB | **1,288.8 MiB** |
| PostgreSQL 18 (`sql-pgsql`) | 102.7 s | 1,461 | 423.9 (TOAST) + 36.5 = 460.4 MiB | 179.5 + 87.5 = 267.0 MiB | **727.4 MiB** |
| SQLite 3.51 (`sql-sqlite`) | 93.2 s | 1,610 | single file (`read-store.sqlite`) | included in file | **1,126 MiB** (1.1 GiB) |

PostgreSQL's TOAST compression shrinks the document table to less than half of MySQL's InnoDB JSON size (460.4 vs 1,194.6 MiB), at the cost of CPU decompression whenever queries must inspect fields inside `doc` (such as `visibilities`, `price`, `name`, or `propertyIds` unnesting).

### Query timings on `read_store_large` (150,000 products, sanity run)

Other lanes stopped: no (host load 6.6–12.4).
Cells: median / p95 in ms (write-DB statements in parentheses).
Iterations: 15 (3 warm-up) for fast cells; 5 (1 warm-up) for `sql-pgsql` S3/R3b; 3 (1 warm-up) for `sql-mariadb` S1/S3/R3b and `sql-sqlite` S1/S3.

| Store | S1 | S2 | S3 | R3b | R4 |
|---|---|---|---|---|---|
| `store-sql-mysql` | 57.04 / 69.45 (0) | 0.21 / 0.29 (0) | 4,851.79 / 5,970.41 (0) | 710.20 / 783.19 (2) | 1.50 / 2.18 (0) |
| `store-sql-pgsql` | 719.88 / 809.61 (0) | 0.34 / 0.52 (0) | 3,895.76 / 4,299.77 (0) | 5,613.18 / 6,031.57 (2) | 1.55 / 1.97 (0) |
| `store-sql-mariadb` | 15,108.04 / 15,450.58 (0) | 0.21 / 0.25 (0) | 26,960.37 / 28,089.06 (0) | 19,674.64 / 22,714.37 (2) | 0.98 / 1.69 (0) |
| `store-sql-sqlite` | 5,807.48 / 6,733.08 (0) | 0.05 / 0.10 (0) | 8,186.49 / 9,677.97 (0) | >315,000 (aborted at 315 s on 1st iter) | 0.51 / 0.76 (0) |

Short R5 sanity load (15–20 s per level, 0 errors):

| Store | c | Throughput/s | p50 ms | p95 ms | R1 / R2 / R3b p50 ms | Write-DB stmts/req | `instance-mysql-1` CPU s |
|---|---|---|---|---|---|---|---|
| `store-sql-mysql` | 1 | 5.8 | 0.7 | 774.0 | 0.3 / 63.8 / 735.2 | 0.4 | 14.7 (shared server) |
| `store-sql-mysql` | 8 | 16.5 | 73.2 | 2,169.9 | 0.3 / 86.3 / 2,032.6 | 0.4 | 111.6 (shared server) |
| `store-sql-pgsql` | 1 | 0.8 | 1.2 | 6,333.4 | 0.6 / 796.5 / 5,861.2 | 0.3 | 1.2 |
| `store-sql-pgsql` | 8 | 1.4 | 846.1 | 20,267.4 | 0.7 / 863.8 / 15,324.1 | 0.5 | 10.1 |
| `store-sql-mariadb` | 1 | 0.2 | 1.5 | 18,695.4 | 0.6 / 12,839.4 / 18,695.4 | 0.4 | 0.6 |

**Verdict for SQL JSON stores at 150,000 products**:
All four SQL engines excel at primary-key hydration (`S2` 0.05–0.34 ms, `R4` 0.51–1.55 ms — 10–90× faster than DAL `S2` 4.53 ms).
For catalog listings and faceted aggregations, however, JSON-in-SQL degrades sharply at 150k products: `sql-mysql` holds `S1` to 57 ms via its multi-valued `categoryTree` index, but `S3` (price range + 7 aggregations including `JSON_TABLE` unnesting) takes 4.85 s — slower than plain relational DAL (2.72 s).
`sql-pgsql` pays heavy TOAST decompression on `S1` (720 ms), `S3` (3.90 s) and `R3b` (5.61 s).
`sql-mariadb` (15–27 s) and `sql-sqlite` (5.8 s–>315 s) are non-viable for catalog search/listing at 150k products, making SQL JSON viable as a **key-value/detail document store** or on small catalogs (≤5k products on MySQL 8.4), not as a standalone faceted catalog query engine at 150k scale.
