# Summary after wave 5: findings and architecture

State: 2026-11-19, research repo at `d642c48`, instance branch `poc/db-independent` at `f6a37fd183f` (101 commits on trunk `ae0190f5892`, 460 files changed).
Every number below comes from one of the numbered docs, the source is linked in each section.

## In one paragraph

The same Shopware code now installs and runs on MySQL 8.4, MariaDB 10.11 and PostgreSQL 18, and gets through `system:install` and a few storefront and admin routes on SQLite.
SQL that differs per database goes through a `SqlDialect` per database, ids are hex strings above the connection, and the MySQL-to-PostgreSQL translator is left as a shim for old migrations and extension SQL.
PostgreSQL was 2.6x to 3.6x slower than MariaDB on the storefront with realistic catalog data; wave 5 brought that to 1.8x to 2.0x (1.35x to 1.64x with persistent connections).
The gap that is left is mostly a fixed cost per request (new backend, planning of wide DAL statements), not the translator and the id codec (1.9 % to 8.6 % and 0.3 % to 3.6 % of the wall time on the catalog run).

## Where we started

Shopware writes MySQL SQL in many places (`docs/01-initial-findings.md`, `docs/04-inventory-summary.md`):

- 446 files use the connection, 241 of them contain MySQL-specific SQL.
- 507 text columns rely on the case-insensitive collation `utf8mb4_unicode_ci`.
- 715 id columns are `binary(16)`, and 309 files outside the migrations convert ids between hex and bytes by hand.
- 910 migrations are written in MySQL DDL.

The first port (waves 1 and 2) put a translator between Shopware and PostgreSQL that rewrites every statement; it found the differences fast but is not a target (`docs/10-architecture.md`, "Why this is not the target").

## Architecture now

```mermaid
flowchart TD
    subgraph app["Shopware code"]
        DAL["DAL<br/>reader, searcher, aggregator,<br/>write gateway, field accessors"]
        RAW["Raw SQL services<br/>cart, stock, SEO, indexers, ..."]
        MIG["910 historic migrations<br/>and extension SQL (MySQL)"]
    end

    DAL --> DIALECT
    RAW --> IDB
    DAL --> IDB

    subgraph dialect["Per database decisions"]
        DIALECT["SqlDialect<br/>MySql / MariaDb / PostgreSql / Sqlite"]
        IDB["IdBinding<br/>hex ids in, per-database binding"]
    end

    DIALECT --> CF
    IDB --> CF
    MIG --> CF

    CF["ConnectionFactory<br/>picks the factory by the DATABASE_URL scheme"]
    CF --> MYF["MySQLFactory"]
    CF --> PGF["PostgreSQLFactory"]
    CF --> SLF["SqliteFactory"]

    MYF --> MY[("MySQL 8.4<br/>MariaDB 10.11")]

    PGF --> PGMW["Middlewares<br/>session, translator shim,<br/>id codec, exception mapping"]
    PGMW --> PG[("PostgreSQL 18")]

    SLF --> SLMW["Middlewares<br/>session and PHP functions,<br/>translation, DDL rewrite"]
    SLMW --> SL[("SQLite 3")]
```

### `SqlDialect`

One interface (`instance/src/Core/Framework/Adapter/Database/Dialect/SqlDialect.php`), one implementation per database, chosen by the platform of the connection (`SqlDialectFactory`).
Each method exists because a concrete difference needed it:

| Method | Why it exists | Doc |
|---|---|---|
| `quoteIdentifier()` | backticks against double quotes | 10, 17 |
| `upsert()` | `ON DUPLICATE KEY` reacts to every unique key, `ON CONFLICT` names one | 10 |
| `groupConcat()` | `GROUP_CONCAT` against `string_agg` | 10 |
| `jsonExtract()`, `jsonExtractText()`, `jsonValue()`, `jsonBind()`, `jsonSet()` | `JSON_*` functions against `jsonb` operators | 10 |
| `jsonExtractNumber()` | PostgreSQL has no `text * numeric`, prices in other currencies failed with HTTP 500 | 20 |
| `idToText()`, `idParameterType()`, `idListParameterType()` | `binary(16)` against native `uuid` | 15 |
| `caseInsensitive()` | `ci` collation of MySQL, `lower(col) COLLATE ucs_basic` with an index on PostgreSQL | 16 |
| `subqueryFence()` | forces PostgreSQL to compute `lower()` once per row in the keyword lookup | 18 |
| `rowNumberPerPartition()` | `ROW_NUMBER() OVER (PARTITION BY ...)` on PostgreSQL and SQLite, MySQL keeps its `@n` session variable counter | code |

Implementations are small: `MariaDbDialect` 19 lines (inherits from MySQL), `MySqlDialect` 144, `PostgreSqlDialect` 221, `SqliteDialect` 179.

### Ids

```mermaid
flowchart LR
    subgraph before["Before"]
        A1["PHP code<br/>Uuid::fromHexToBytes()"] -->|"16 bytes"| A2["IdCodecMiddleware<br/>guesses which values are ids"]
        A2 -->|"uuid text"| A3[("PostgreSQL uuid")]
    end
    subgraph after["Now"]
        B1["PHP code<br/>hex strings only"] --> B2["IdBinding::value() / type()"]
        B2 -->|"MySQL, MariaDB, SQLite: 16 bytes"| B3[("binary(16)")]
        B2 -->|"PostgreSQL: hex text"| B4[("uuid")]
    end
```

- `IdBinding` (static facade on top of the dialect decision) is used in 313 files of `src` outside the migrations; a Rector rule did most of the rewrite (`docs/15-id-spike.md`).
- Files that still bind ids as bytes: 309 before, 12 now (section 8 of doc 15).
- Codec conversions in the measured flows: 6,465 before wave 4, 204 now.
- The codec stays only for old migrations and extension SQL; its default stays `guess`, because a strict mode only helps once every caller is typed (`docs/20-currency-seo-codec.md`).

### Translator shim

About 3,650 lines in `Adapter/Database/PostgreSQL/` (translator, DDL and DML rewriters, id codec, `mysql-compat.sql` with the functions that imitate MySQL).
The installer loads `mysql-compat.sql` itself, so no manual step is left (`docs/17-install-and-translator.md`).
All 910 migrations run through it with 0 schema differences against MySQL (2,168 columns, 726 indexes, 1,878 constraints).
New rules are only added when there is no other way; the target is that core SQL no longer needs it.

### Schema differences on PostgreSQL

Two PostgreSQL-only migrations in `core.V6_8`, no-ops on the other databases:

- `Migration1795000000PostgreSqlCaseInsensitiveSearchIndexes`: `lower(...) COLLATE ucs_basic` expression indexes and trigram indexes for search keywords and SEO paths.
- `Migration1795000100PostgreSqlCategoryPathCollation`: `category.path` (lowercase hex ids) on the deterministic `ucs_basic` collation.

## How a storefront read reaches PostgreSQL

```mermaid
sequenceDiagram
    participant C as Controller / route
    participant D as DAL (EntityReader, EntitySearcher)
    participant S as SqlDialect + IdBinding
    participant T as Translator shim
    participant K as Id codec (guess)
    participant P as PostgreSQL

    C->>D: Criteria
    D->>S: quote, JSON, group concat, ids
    S-->>D: PostgreSQL SQL, ids as hex text
    D->>T: statement
    Note over T: leftover MySQL constructs only,<br/>1.9 to 8.6 % of the wall time (catalog run)
    T->>K: translated statement
    Note over K: 0.3 to 3.6 % of the wall time (catalog run)
    K->>P: execute
    P-->>D: rows (ids already hex)
```

## Findings

### Correctness

| Finding | Cause | State | Doc |
|---|---|---|---|
| A failed statement aborts the transaction on PostgreSQL | catch-and-continue code without savepoints | PHPUnit runs with per-statement savepoints on PostgreSQL (`SHOPWARE_PG_STATEMENT_SAVEPOINTS`); production code paths are not all checked | 09 |
| `GROUP BY` is strict on PostgreSQL, MySQL runs without `ONLY_FULL_GROUP_BY` | queries rely on the lenient mode | rewritten in the places of docs/06 (for example `StatesUpdater` with `EXISTS`) | 06, 09 |
| Prices in a currency with a factor gave HTTP 500 | `text * numeric` | fixed through `jsonExtractNumber()` | 20 |
| SEO url bulk insert rejected on PostgreSQL (`invalid input syntax for type uuid`) | 16-byte ids bound as strings, the codec leaves valid UTF-8 values raw | fixed, ids as hex | 13, 20 |
| About 1 in 11,000 random ids is valid UTF-8, the codec guesses them as text | untyped byte binding | callers typed, 12 files left | 20, 15 |
| Empty many-to-many id fields stored `[]` instead of `NULL` | `CONCAT` ignores a `NULL` aggregate on PostgreSQL | fixed | 21 |
| Keyword search is accent-sensitive on PostgreSQL | `lower()` replaces the accent-insensitive `ci` collation | accepted trade-off | 16 |

DAL integration suite (801 tests) on PostgreSQL: 184 failures at the first measurement (docs/09), 167 at the start of wave 5, 24 now (MariaDB 0).
The remaining 24 are grouped by cause in `docs/21-dal-failures-postgresql.md` and are wave 6, handoff C.

### Performance

```mermaid
flowchart TD
    GAP["Storefront on catalog data<br/>PostgreSQL 2.6x to 3.6x of MariaDB"]
    GAP --> F1["category.path LIKE on the ICU collation<br/>50 to 60 ms per request"]
    GAP --> F2["Keyword lookup evaluates lower() in every OR branch<br/>about 50 ms on search"]
    GAP --> O1["New backend per request<br/>connect 7 ms, ICU warm-up 7.7 ms, cold caches"]
    GAP --> O2["Planning of wide DAL statements<br/>15 to 68 ms warm per request"]
    GAP --> O3["Parallel writes deadlock on product rows<br/>each one waits deadlock_timeout 1 s"]

    F1 --> FIX1["ucs_basic collation<br/>fixed in wave 5"]
    F2 --> FIX2["subqueryFence, lower() once per row<br/>fixed in wave 5"]
    O1 --> OPEN1["persistent connections or a pooler<br/>wave 6 A"]
    O2 --> OPEN2["prepared statements, per-statement planner hints<br/>wave 6 A"]
    O3 --> OPEN3["find and fix the lock order<br/>wave 6 B"]

    classDef fixed fill:#d4edda,stroke:#2e7d32,color:#1b5e20
    classDef open fill:#fff3cd,stroke:#b8860b,color:#5d4300
    class FIX1,FIX2 fixed
    class OPEN1,OPEN2,OPEN3 open
```

Median latency, PostgreSQL divided by MariaDB, catalog data set (`docs/13-benchmark.md`, "Ratios before and after"):

| Scenario | Before wave 5 | After wave 5 | After, both with persistent connections | PostgreSQL ms after |
|---|---:|---:|---:|---:|
| storefront home | 2.60 | 1.77 | 1.35 | 181.3 |
| storefront listing with filter | 3.29 | 1.86 | 1.38 | 118.4 |
| storefront search | 3.56 | 1.92 | 1.44 | 149.0 |
| storefront product detail | 3.45 | 2.01 | 1.64 | 155.2 |
| store API listing with aggregations | 1.63 | 1.69 | 1.06 | 38.3 |
| admin API search with aggregations | 1.96 | 1.86 | 1.20 | 39.7 |
| admin API bulk sync write (50 products) | 1.72 | 1.72 | 1.60 | 427.1 |

MySQL 8.4 is 0.91x to 1.21x of MariaDB on the same scenarios.

Parallel bulk writes, 4 workers, requests per second: MariaDB 12.2 to 13.4, PostgreSQL 1.36.
With products that are visible in several channels removed from the list (`--dedupe`) PostgreSQL reaches 7.33, with `deadlock_timeout` at 100 ms 5.9 (`docs/19-postgresql-parallel-writes.md`).
So the collapse is a few shared rows plus PostgreSQL's one second deadlock detection; the code that takes the rows in the wrong order is not found yet.

What the measurements ruled out (docs/13, docs/18): the translator and the id codec (at most about 12 % of a request together, on the bulk write; less on reads), PL/pgSQL functions (all used functions are inlinable SQL), `json` instead of `jsonb` (all 220 JSON columns are `jsonb`), missing foreign key indexes (none), more statements per request (same count as MariaDB within one).

### Switching

`scripts/switch-db.sh` installs from scratch, loads demo data, indexes and runs a smoke test (storefront, admin API, sync API, store API checkout) on each database.
All 9 runs passed; empty database to working shop takes about 35 to 50 seconds on every database (`docs/12-switch-test.md`).

### SQLite

`system:install` runs with 5 of 1,542 migrations missing; storefront home, login, admin token, product search and product write work (`docs/14-sqlite-spike.md`).
It is not faster for the measured requests (PHP dominates), allows one writer at a time, and its `ALTER TABLE` limits make every migration a rewrite.
Recommendation of the spike: keep SQLite out of the first supported set and revisit it once migrations have a database-neutral definition.

## Database differences that shaped the design

| Topic | MySQL / MariaDB | PostgreSQL | SQLite | Handled by |
|---|---|---|---|---|
| Ids | `binary(16)` | native `uuid` | `BLOB` | `IdBinding`, dialect |
| Case-insensitive text | collation `utf8mb4_unicode_ci` | ICU collation `ci`, `lower()` with index where it matters | `NOCASE`, ASCII only | `caseInsensitive()`, migrations |
| Upsert | `ON DUPLICATE KEY UPDATE` | `ON CONFLICT (target)` | `ON CONFLICT (target)` | `upsert()` |
| JSON | `JSON` / `LONGTEXT` | `jsonb` | text with JSON functions | `json*()` methods |
| Error inside a transaction | transaction usable | transaction aborted | statement rolled back | savepoints |
| Deadlock detection | immediate | after `deadlock_timeout` (1 s) | single writer | open, wave 6 B |
| Connections | thread per connection | process per connection | in process | open, wave 6 A |

Full table: `docs/11-database-comparison.md`.

## Timeline

```mermaid
timeline
    title Waves of the proof of concept
    Wave 1 : migrations on PostgreSQL through the translator
           : DTO slice, admin areas, hardening
    Wave 2 : PHPStan, parser robustness, runtime gaps
           : PHPUnit on PostgreSQL
           : target architecture with SqlDialect
    Wave 3 : switch harness, first benchmark
           : dialect spike, SQLite spike, id spike
    Wave 4 : PostgreSQL hot spots, benchmark rerun
           : installer without manual steps, native quoting
           : DAL on IdBinding
    Catalog run : 6 catalog generator templates as data set
                : PostgreSQL 2.6-3.6x on the storefront
    Wave 5 : storefront gap 2.6-3.6x to 1.8-2.0x
           : parallel write deadlocks explained
           : currency and SEO fixes, remaining id call sites
           : DAL failures 167 to 24
    Wave 6 : connection and planning cost, lock order
           : last DAL failures, API reads
```

## Decisions

From `docs/02-decisions.md` and the wave handoffs:

- One code base, the database is chosen by `DATABASE_URL`; moving data between databases is out of scope.
- PostgreSQL stores ids as native `uuid`.
- `SqlDialect` per database in the core, the translator only as a shim for old migrations and extension SQL.
- Code above the connection uses hex ids only, `IdBinding` binds them per database.
- Id codec default stays `guess`.
- SQLite is the third database to prove the abstraction, not a production target.
- Custom field string equals is case-insensitive on every database, as on MySQL (decided for wave 6).

## Open

| Topic | Numbers today | Next |
|---|---|---|
| Fixed cost per request on PostgreSQL | connect 7 ms, ICU 7.7 ms, planning 15 to 68 ms | wave 6 A, connection mode recommendation |
| Parallel write deadlocks | 1.36 against 12 to 13 requests per second | wave 6 B, lock order |
| DAL integration failures | 24 on PostgreSQL | wave 6 C |
| Store API and admin search | 1.69x and 1.86x | wave 6 D, per statement analysis |
| `ci` collation on string filters | each `LIKE` about 50x slower than on `ucs_basic` | needs a decision on accent and case semantics |
| Migrations | historic ones depend on the translator | a database-neutral migration API, also the precondition for SQLite |
| Extensions with raw MySQL | run through the shim | deprecation path, public dialect service |
