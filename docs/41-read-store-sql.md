# Read store on SQL JSON columns (wave 9, handoff S)

Handoff S of wave 9: one adapter for MySQL 8.4, MariaDB 10.11, PostgreSQL 18 and SQLite (`docs/38-read-store-plan.md`).
The adapter implements the port of `docs/40-read-store-port-and-document.md`.

## Status

| Milestone | Commit in `instance/` (`poc/read-store`) | Contents |
|---|---|---|
| Adapter ready | `6569e8606a1 feat(core): add SQL JSON read store adapters for MySQL, MariaDB, PostgreSQL and SQLite` | Adapter, compiler, four dialects, services, contract tests |
| Rebuild, verify, corpus | pending milestone 2 | Rebuild with `--verify`, criteria corpus, timings, sizes |

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
The adapter creates no index on the JSON documents yet, indexes are a milestone 2 question.

### MySQL 8.4

```sql
CREATE TABLE `<prefix>_<generation>` (
    seq BIGINT NOT NULL AUTO_INCREMENT,
    id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    doc JSON NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY `<table>_seq` (seq)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `<prefix>_<generation>_kw` (
    product_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    language_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    keyword_fold VARCHAR(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    ranking DOUBLE NOT NULL,
    KEY `<table>_product` (product_id),
    KEY `<table>_lookup` (language_id, keyword_fold)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

Upsert: `INSERT ... ON DUPLICATE KEY UPDATE doc = VALUES(doc)`.

### MariaDB 10.11

The tables are the MySQL tables except for the document column.

```sql
doc LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (JSON_VALID(doc))
```

MariaDB 10.11 has no native `JSON` type, the keyword `JSON` is an alias for `LONGTEXT` with this check.
The `CHECK` has to follow `NOT NULL`, with the check before it the statement is a syntax error (run on MariaDB 10.11, first contract run).

### PostgreSQL 18

```sql
CREATE COLLATION IF NOT EXISTS rs_unicode_ci (provider = icu, locale = 'und-u-ks-level1', deterministic = false);

CREATE TABLE "<prefix>_<generation>" (seq BIGSERIAL NOT NULL, id TEXT COLLATE "C" NOT NULL PRIMARY KEY, doc JSONB NOT NULL);

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
Upsert: `INSERT ... ON CONFLICT (id) DO UPDATE SET doc = EXCLUDED.doc`.

### SQLite

```sql
CREATE TABLE "<prefix>_<generation>" (id TEXT NOT NULL PRIMARY KEY, doc TEXT NOT NULL CHECK (json_valid(doc)));

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
| List contains | `JSON_CONTAINS(doc, JSON_QUOTE(:v), path)` | `@>` with `to_jsonb` | `EXISTS` over `json_each` |
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
| A multi-valued index (`CAST(... AS CHAR(32) ARRAY)`) is accepted and used by `MEMBER OF` | MySQL | Probe, not part of the adapter yet |
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

Pending milestone 2.

### Rebuild and `--verify`

Pending milestone 2.

### Table and index sizes

Pending milestone 2.

### Query timings

Pending milestone 2.
