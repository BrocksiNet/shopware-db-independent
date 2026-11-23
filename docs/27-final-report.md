# 27 Final report: Shopware database independent

Status: 2026-11-22, after wave 7.
Instance branch `poc/db-independent` at `87e1768ce3a` (local, on trunk `ae0190f5892`).
This closes phase 7 of `docs/00-plan.md` ("required core changes, effort, breaking changes for extensions").
Details stay in the numbered docs; `docs/summary.md` is the technical overview.

## TL;DR

- The same Shopware code installs and runs on MySQL 8.4, MariaDB 10.11 and PostgreSQL 18; SQLite installs, passes the smoke requests and runs the DAL suite (`docs/summary.md`, `docs/24`).
- The approach that works is a `SqlDialect` per database under the DAL and for raw SQL, hex ids above the connection, native `uuid` on PostgreSQL, and the MySQL-to-PostgreSQL translator only as a shim for old migrations and extension SQL (`docs/10`, `docs/02`).
- The 910 migrations of a default install run on PostgreSQL through the shim, and the catalog matches a reference converted from the installed MariaDB schema (0 differences in columns, index and constraint definitions); that is a structural check of the translation, not equivalence with MySQL (`docs/17`, `docs/37`).
- DAL integration suite: 804 tests, 0 failures on PostgreSQL and MariaDB; SQLite 795 of 804 (`docs/21` "Wave 7", `docs/24`).
- Storefront on PostgreSQL: 1.13x to 1.46x of MariaDB with persistent connections and the plan cache, up to 1.9x with a new connection per request; it started at 2.6x to 3.6x (`docs/13` "Rerun after wave 7").
- Writes stay the weak spot: bulk write 520 ms against 264 ms, parallel writes 3.89 against about 12.5 requests per second, 0 deadlocks (`docs/13`, `docs/26`).
- 29 findings help Shopware on MySQL as it is today (8 performance, 11 robustness, 3 bugs, 4 portability, 2 ideas, 1 cleanup, `docs/core-findings.md`).
- Size of the PoC: 118 commits, 479 files, +14,289 / -2,515 lines; proof of concept quality, not merge-ready.

## What the experiment answered

| Question | Answer | Doc |
|---|---|---|
| Can Shopware run on another database without a rewrite? | Yes, through a dialect layer and a cleanup of MySQL assumptions in the core | 10, summary |
| Is a translator in front of PostgreSQL enough? | No as a target: it found the differences fast, but it costs time per statement and hides the SQL; it stays as a compatibility shim | 10, 17, 25 |
| How do ids work across databases? | Hex strings above the connection, `IdBinding` per dialect, native `uuid` on PostgreSQL | 15, 20 |
| How fast is PostgreSQL with realistic data? | Reads 1.1x to 1.5x with persistent connections and plan cache, writes about 2x; the gap left is a fixed cost per request (new backend, planning of wide DAL statements), not the translator or the id codec | 13, 18, 22, 25, 26 |
| Does the abstraction hold for a third database? | SQLite needed only its dialect and shims for the DAL suite; migrations are the blocker | 14, 24 |
| Do the store plugins rely on MySQL? | See "Extensions" below | 28 |

## Why stop the broad experiment now

- Wave 7 gains were mostly within the spread of the runs; the only clear effect was the trigram index for search (149.6 to 93.5 ms, `docs/13` "Rerun after wave 7").
- The remaining performance levers change Shopware for every database: fewer joins in the DAL read path, one scored-ids subselect instead of repeated keyword subqueries, batched indexer updates (`docs/25`, `docs/26`, `docs/core-findings.md` rows 24 and 29).
- The open questions need decisions, not measurements: accent and case semantics of string filters, a database-neutral migration API, the deprecation path for extension SQL.
- Optional single spike before an RFC: estimate the gain of fewer joins in the read path on PostgreSQL and MySQL, since it is the largest lever left and was never measured (`docs/22` "Reducing joins in a later wave", `docs/25`).

## What is not proven

- Integration suites outside the DAL were last measured in phase 6 (`docs/09`): Checkout 57, System 85, Content/Product 54 failures on PostgreSQL; since then only the DAL suite (804) and `Content/Product/DataAbstractionLayer` (72) were brought to 0.
- `tests/integration/Core/System/CustomEntity`: 9 of 12 fail on PostgreSQL (`docs/21` "Wave 7").
- PHPUnit on PostgreSQL runs with per-statement savepoints; production code that catches a failed statement and continues is not checked everywhere (`docs/09`, summary "Correctness").
- Elasticsearch/OpenSearch, read replicas, `DATABASE_SSL_*` and the admin worker were not tested on PostgreSQL (`instance/.env.pgsql.dist`).
- Every timing comes from one developer machine with other workloads; differences below about 10 % are not reliable (`docs/13`, `docs/26`).
- Extensions were only scanned statically, not run (see below).

## Extensions

Static scan of 3,747 Shopware 6 store plugins (mirror snapshot of 2026-10-02), details and method in `docs/28-plugin-sql-inventory.md`.

| Group | Plugins | Share | Meaning for a PostgreSQL driver |
|---|---|---|---|
| No PHP, or PHP without raw SQL | 1,701 | 45 % | portable as far as the DAL is |
| Raw SQL without MySQL-specific constructs | 93 | 2.5 % | portable |
| Raw SQL the shim translates | 477 | 12.7 % | runs through the shim, breaks once the shim goes |
| MySQL-only DDL in migrations | 1,122 | 29.9 % | needs the shim's DDL rewrites or a neutral migration API |
| Constructs the shim has no rule for | 354 | 9.4 % | breaks on PostgreSQL today |

- 2,045 plugins (55 %) contain raw SQL; 1,389 have MySQL-only DDL in 7,505 migration classes, and `BINARY(16)` id columns appear in 1,376.
- The most common gaps without a shim rule: `information_schema` views PostgreSQL does not have or that filter on `DATABASE()` (219 plugins), date difference functions (77), JSON functions without a compat function (77).
- The 625 apps contain no PHP and no SQL and are not affected.
- The scan is regex based on tokenized PHP; SQL built by concatenation is only seen in parts, so the numbers are an estimate, checked by hand on 36 plugins plus 6 more by me.

Consequence: the shim cannot be dropped for years, a public dialect service and a neutral migration API are prerequisites before PostgreSQL support, and a `shopware-cli` check can tell vendors which of their statements will not run.

## Required core changes

| # | Change | Breaking | Helps MySQL alone |
|---|---|---|---|
| 1 | Core findings as normal fixes: typed parameters, explicit NULL order, `fetchOne()` instead of `rowCount()` after SELECT, savepoints where code continues after a failed statement | no | yes |
| 2 | `SqlDialect` service in the core, first with the MySQL/MariaDB implementation only; move MySQL-specific SQL (241 files in wave 1) behind it | no | readability, testability |
| 3 | Hex ids above the connection, `IdBinding` instead of manual hex/bytes conversion (309 files outside migrations before, 12 left in the PoC, `docs/15`), Rector rules | yes for extensions with raw SQL on ids, deprecate first | fewer conversion bugs |
| 4 | Fewer statements per write: batched indexer updates (475 `UPDATE product` per bulk write) | no | yes |
| 5 | Database-neutral migration API for new migrations; old ones keep running through the shim | new API, no break | yes, also for SQLite |
| 6 | PostgreSQL dialect, `PostgreSQLFactory`, PG-only indexes, `mysql-compat.sql`, translator shim | no (new driver) | no |
| 7 | Decision on string filter semantics: accent-sensitive `lower()` (fast) or the `ci` collation (about 50x slower `LIKE`) | behaviour change on PostgreSQL only | no |
| 8 | Public dialect service and shim lifetime for extensions, check in `shopware-cli` | deprecation | no |

## Integration plan

The phases follow the release rhythm: non-breaking work in minors, breaking work announced one major ahead.

| Phase | When | Content | Exit criterion |
|---|---|---|---|
| 0 Decision | first quarter | RFC/ADR from this report; business case (cloud, managed databases, enterprise demand, CI and support cost of a further database); supported or community target | go or stop; phase 1 is worth doing even on stop |
| 1 Groundwork, MySQL only | year 1, minors | changes 1, 2, 4; dialect interface with one implementation; deprecations for manual id conversion and raw MySQL in core | no PostgreSQL code merged, MySQL suites green, measurable gains from the findings |
| 2 Breaking prerequisites | next major | changes 3, 5, 8; public dialect service; extension guide; `shopware-cli` check for MySQL-only SQL | extensions can write portable SQL; core has no raw MySQL outside the dialect |
| 3 PostgreSQL experimental | following year | change 6 behind a flag; nightly CI with the DAL and integration suites on PostgreSQL; recommended setup (persistent connections or a pooler, plan cache, PG indexes); decision 7 | full integration suite green on PostgreSQL; storefront within an agreed factor of MySQL |
| 4 PostgreSQL supported | year 3 | CI matrix for every PR, performance budget, hosting partner guidance, OpenSearch and replica support | support policy published |
| (optional) SQLite for development and CI | after phase 2 | SQLite dialect for local development and single-process CI | DAL and API suites green on SQLite |

## Risks

- Extensions with raw MySQL are the largest unknown for customers; the shim covers simple DML, not everything (`docs/28`).
- Running two or three databases in CI permanently costs time on every change.
- Write and import performance on PostgreSQL (about 2x) matters for large catalogs and ERP syncs.
- Behaviour that MySQL users get without asking: accent-insensitive search, lenient `GROUP BY`, implicit casts, NULL order.
- The PoC branch is far from trunk; landing it means re-doing the work in reviewable steps, not merging the branch.
- Value for the effort is doubtful (feedback from a core developer, 2026-11-23, reported, not measured here): PostgreSQL maintainers told them years ago that database benchmarks are mostly synthetic and that several applications got slower after a port from MySQL or MariaDB, and the extension, hosting and tooling ecosystem around Shopware is built on MySQL.
  The measurements here point the same way: in the storefront and write runs PostgreSQL stayed slower than MariaDB (storefront 1.13x to 1.46x, writes about 2x).
