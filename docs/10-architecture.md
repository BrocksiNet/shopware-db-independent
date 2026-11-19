# Architecture: from a PostgreSQL translator to a database independent core

State: instance branch `poc/db-independent` after wave 2 (2026-11-19).
Decisions behind this document: `docs/02-decisions.md`, rows of 2026-11-19.

## Goal

The same Shopware code installs and runs on MySQL, MariaDB, PostgreSQL and SQLite.
Switching means: point `DATABASE_URL` at another server (or file), run `system:install` with all migrations, and the shop works.
Moving the data of an existing shop from one database to another is a separate topic and not part of this goal.

## Current state: a translation layer

The core still writes MySQL SQL everywhere.
On PostgreSQL a chain of DBAL driver middlewares rewrites every statement before it reaches the server:

| Middleware / file | Lines | Job |
|---|---:|---|
| `SessionMiddleware` | 32 | session settings (time zone UTC) |
| `SqlTranslationMiddleware` | 241 | entry point, DDL savepoints, boolean column lookup |
| `MySQLToPostgreSQLTranslator` | 512 | backticks, functions, `INTERVAL`, `GROUP_CONCAT`, JSON and more, with a cache of up to 5,000 translated statements |
| `DdlRewriter` | 1001 | `CREATE` / `ALTER TABLE`, types, keys, foreign keys |
| `UpsertRewriter`, `InsertSelectRewriter`, `InsertSetRewriter`, `UpdateRewriter`, `DeleteRewriter`, `BooleanAssignmentRewriter` | 700 | DML forms that PostgreSQL writes differently |
| `ShowRewriter`, `InformationSchemaRewriter` | 163 | schema introspection |
| `IdCodecMiddleware` (+ statement, result) | 170 | `binary(16)` ids as native `uuid` |
| `ColumnCaseResult` / `ColumnCaseStatement` | 88 | column name case in results |
| `ExceptionConverterMiddleware` | 50 | lock timeout as `LockWaitTimeoutException` |
| `mysql-compat.sql` | 324 | 87 SQL functions that imitate MySQL functions and operators |

Together about 3,450 lines in `src/Core/Framework/Adapter/Database/PostgreSQL/`.
On top of that 45 other core files are changed (connection factory, installer, DAL query helpers, migration runtime, test bootstrap, a few raw-SQL services and six old migrations).

Result (`docs/09-test-run-on-postgresql.md`): all 910 migrations run with 0 schema differences, admin API, storefront and checkout work, about 90 % of the integration tests in five areas pass.

### Why this is not the target

- **SQL is parsed with regexes and hand written scanners.**
  Every new statement shape is a new rule, wave 2 still found gaps in comments, backticks and escapes.
- **One full translator per database.**
  SQLite would need a second MySQL-to-SQLite translator of the same size.
- **Cost on every statement.**
  Each statement is scanned by several rewriters, the boolean rewriter looks up column types; nobody has measured the overhead yet.
- **MySQL stays the reference.**
  The other databases can only imitate MySQL, they never use their own strengths (for example `jsonb` operators).
- **Behaviour differences stay hidden.**
  Booleans, case-insensitive comparison, strict `GROUP BY` and aborted transactions are patched at the wire instead of being decided in the code that depends on them.

The translator is still valuable: it is the inventory of every difference we hit, and it keeps code that writes raw MySQL running.

## Target architecture

```
              DAL (reader, searcher, aggregator, write gateway, field accessors)
              raw-SQL services on hot paths (cart, stock, SEO, indexers, ...)
                                   |
                             SqlDialect  <--- one implementation per database
                                   |
   +---------------+---------------+-----------------+----------------+
   | MySqlDialect  | MariaDbDialect| PostgreSqlDialect | SqliteDialect |
   +---------------+---------------+-----------------+----------------+
                                   |
       Connection factory per platform (DATABASE_URL scheme), session setup,
       id codec, exception mapping
                                   |
       Compatibility shim: MySQL-to-X translator, only for old migrations
       and extension code that still sends raw MySQL (deprecated path)
```

### 1. Connection per platform

`ConnectionFactory` already picks `MySQLFactory` or `PostgreSQLFactory` by the scheme of `DATABASE_URL`.
Each factory owns the session setup (MySQL `sql_mode`, PostgreSQL settings, SQLite `PRAGMA foreign_keys = ON`), the middlewares and the exception mapping.
A `SqliteFactory` is added the same way.

### 2. `SqlDialect`

A service with one implementation per database, injected where SQL is generated.
The method list comes straight from what we had to translate (DAL findings in `docs/inventory/dal/findings.md`, rewriters above):

| Dialect method | Replaces today | Used by |
|---|---|---|
| `quoteIdentifier()` | backticks, static `EntityDefinitionQueryHelper::escape()` (1,434 backticks in 135 raw-SQL files) | everywhere |
| `upsert(table, columns, conflictKey, updateColumns)` | `ON DUPLICATE KEY`, `REPLACE INTO`, `INSERT IGNORE`, `UpsertRewriter` | write gateway, `MultiInsertQueryQueue`, persisters |
| `groupConcat(expr, separator, orderBy)` | `GROUP_CONCAT(... SEPARATOR ...)` (59 in 20 files) | reader, indexers |
| `jsonExtract()`, `jsonSet()`, `jsonContains()`, `jsonLength()` | `JSON_*` (90 in 19 files), `JsonFieldAccessorBuilder` | field accessors, rule and promotion updaters |
| `idToText()`, `idParameterType()`, `idListParameterType()` | `LOWER(HEX())` (364 in 140 files), `Uuid::fromHexToBytes`, `ArrayParameterType::BINARY` | everywhere ids leave SQL as text |
| `caseInsensitiveEquals()` / `caseInsensitiveLike()` | implicit `utf8mb4_unicode_ci` (507 columns) | search, unique checks |
| `dateFormat()`, `dateAdd()`, `timeZoneConvert()` | `DATE_FORMAT`, `INTERVAL`, `CONVERT_TZ` | date histogram aggregation, scheduled cleanups |
| `limitedDelete()` / `limitedUpdate()` | `DELETE ... LIMIT n` | cleanup tasks |
| `forUpdate()` | `FOR UPDATE` (not allowed with `GROUP BY` on PostgreSQL, absent in SQLite) | stock, number ranges |
| `booleanLiteral()` / boolean binding | `0` / `1` for `TINYINT(1)`, `BooleanAssignmentRewriter` | writes |
| `isRetryable(exception)` | `RetryableQuery` / `RetryableTransaction` assumptions, `ExceptionConverterMiddleware` | retry logic |

The DAL has four interfaces (reader, searcher, aggregator, write gateway) and a small set of query helpers, so most of the DAL work is injecting the dialect into those few classes.

### 3. Ids

MySQL and MariaDB store `binary(16)`, PostgreSQL native `uuid`, SQLite a 16 byte `BLOB`.
Today the code passes ids as 16 raw bytes (`Uuid::fromHexToBytes()`, `ArrayParameterType::BINARY`, `LOWER(HEX(id))` in SELECTs) and on PostgreSQL the `IdCodecMiddleware` converts them on the wire.

Target (decision 2026-11-19, `docs/02-decisions.md`): code above the connection works with ids as hex strings only.
The dialect decides the storage type and binds them: `idParameterType()` / `idListParameterType()` for parameters, `idToText()` for ids selected as text.
The binary uuid helpers in SQL code and the id codec middleware go away, the codec stays only in the compatibility shim for extension SQL.

212 files call the binary uuid helpers directly, so this is the widest single change.
Most call sites follow a few patterns, so the migration should be mostly automated (a Rector rule plus a check that no new byte binding gets in), with manual work for the rest.
Extensions that bind ids as bytes keep working on MySQL and MariaDB, and through the shim elsewhere, during a deprecation period.

### 4. Schema and migrations

- **History (910 core migrations):** stay MySQL SQL and run through the compatibility shim on other databases.
  `scripts/check-migrations-on-postgresql.sh` proves the result equals the MySQL schema, the same check is needed for SQLite.
- **New migrations:** written against a portable API (DBAL `Schema` objects or a Shopware migration helper on top of the dialect), so they need no translation.
  The schema check in CI catches migrations that only work on MySQL.
- **Introspection:** `Column`, `TableHelper`, `information_schema` and `SHOW` queries go through DBAL's schema manager instead of MySQL catalog tables.

### 5. Behaviour differences are decided, not patched

| Difference | Decision needed |
|---|---|
| Booleans are `TINYINT(1)` on MySQL | bind PHP booleans through the dialect so every database gets its own type; keep the shim for old SQL |
| Case-insensitive text (507 columns) | per column: nondeterministic ICU collation on PostgreSQL, `NOCASE` (ASCII only) on SQLite, or explicit `caseInsensitiveEquals()` |
| `ONLY_FULL_GROUP_BY` is off on MySQL (`MySQLFactory`) | fix the DAL queries that rely on it, then MySQL can run with it on too |
| A failed statement aborts the transaction on PostgreSQL | catch-and-continue sites use savepoints (`transactional()`) on every database |
| Unique key race and lock behaviour | retries and conflict targets through `upsert()` and `isRetryable()` |

### 6. Raw SQL outside the DAL

446 files use the connection, 241 of them contain MySQL-specific SQL (`docs/04-inventory-summary.md`).
Order: the request paths that matter (cart, checkout, stock, SEO, indexers, scheduled tasks), then the rest.
Each file either moves to the DAL, to DBAL's `QueryBuilder` plus dialect, or stays on the shim with a deprecation note.

### 7. Tests and CI

- PHPUnit bootstrap works per platform (done for PostgreSQL in wave 2, `TestBootstrap.php`).
- CI matrix: MySQL, MariaDB, PostgreSQL, SQLite; each runs the migration schema check and a defined integration subset.

### 8. Extensions

- Extensions that use the DAL get the database independence for free.
- Extensions with raw MySQL keep working on MySQL and MariaDB, and through the shim elsewhere, as long as the shim understands their SQL.
- The dialect is offered as a public service so extensions can migrate; the shim gets a deprecation path.

## Change list

Effort is an estimate (S: days, M: weeks, L: months for one developer), not measured.

| # | Area | Size (measured) | Change | Effort | Breaking for extensions |
|---|---|---|---|---|---|
| 1 | Connection factories | 3 classes, exists for MySQL and PostgreSQL | add SQLite, move session setup and middlewares per platform | S | no |
| 2 | `SqlDialect` interface and three implementations | the methods in the table above | extract from the rewriters and the DAL findings | M | no (new API) |
| 3 | DAL on the dialect | 4 interfaces, 16 generation points (`docs/inventory/dal/findings.md`) | inject the dialect, drop static `escape()` | M | yes for code calling `EntityDefinitionQueryHelper::escape()` statically |
| 4 | Id handling | 715 id columns, 212 files with binary uuid helpers | ids as hex strings above the connection, the dialect binds them; Rector rule for the call sites; codec only in the shim | L | yes for raw SQL binding ids as bytes |
| 5 | Raw SQL on hot paths | 241 files with MySQL constructs | rewrite by request path, rest stays on the shim | L | no |
| 6 | Migrations | 910 historic, plus every new one | history on the shim, new ones portable, schema check per database in CI | M | new migrations must be portable |
| 7 | Introspection | `Column`, `TableHelper`, `SHOW`, `information_schema` | DBAL schema manager | S | rarely |
| 8 | Behaviour decisions | 507 case-insensitive columns, booleans, `GROUP BY`, transaction abort | decide per item, fix the code that depends on it | M | possibly (case sensitivity) |
| 9 | Installer and setup | `SystemInstallCommand`, `SetupDatabaseAdapter`, connection information | platform aware (already partly done) | S | no |
| 10 | Test bootstrap and CI matrix | `TestBootstrap.php`, CI config | one job per database | M | no |
| 11 | Compatibility shim | today's translator | keep, limit to migrations and extension SQL, deprecate | S | no |

## How we get there in the proof of concept

1. **Switch harness:** one script installs Shopware from scratch on MySQL 8, MariaDB and PostgreSQL, runs a smoke test and records the times (`docs/11-database-comparison.md`).
2. **Benchmark harness:** same data, same resources, numbers per database, including the cost of the translator itself.
3. **Dialect spike:** extract `SqlDialect` for upsert, JSON and ids (the id parameter types included), move the DAL to it, keep all tests and the schema check green on MySQL and PostgreSQL.
4. **Id spike:** the id API on top of the dialect, a Rector rule, one request path converted end to end without the id codec, measured.
5. **SQLite spike:** how far `system:install` and the storefront get on SQLite with the dialect plus a shim; the result tells whether the dialect method list is complete.

## Open questions

- How far does a portable migration API go before migrations need per-database code?
- Is the per-statement cost of the shim small enough to keep it for extension SQL in production, or only for installs and updates?
- Case-insensitive text: one rule for all 507 columns, or a decision per column?
