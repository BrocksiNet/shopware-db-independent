# Review round 2: id codec cache, batched update semantics, schema claim

Date: 2026-11-23.
Base: `instance/` branches `poc/db-independent` and `poc/orm-spike`, PHP 8.4.17, DBAL 4.4.5.
The review found three problems and an overstated claim; this doc records the fixes and what they were verified with.

## P1: id codec column type cache (PostgreSQL)

Problem: `IdCodecResult` cached "is column N of this SQL a `uuid` column" in a static array keyed by SQL text.
The same SQL text can return other types after DDL, and on another connection (temporary objects are per session), so a `text` column could be decoded as an id or a `uuid` column left as 36 characters.

Fix (`poc/db-independent` commit `071e6d9bea0`, merged into `poc/orm-spike` as `1a5393f3565`):

- The cache lives in `IdCodecColumnTypes`, one instance per connection.
- Every statement whose first keyword is not one of `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `WITH`, `VALUES`, `BEGIN`, `START`, `COMMIT`, `SAVEPOINT`, `RELEASE`, `SHOW`, `EXPLAIN` drops the entries of all connections in the process, and so does a rollback.
  Leading whitespace, comments (including the `#` comments Shopware puts in front of queries) and parentheses are skipped.
- A per-result cache instead was rejected: `PDOStatement::getColumnMeta()` cost 137 µs per call, a trivial query 156 µs, so it would add about one round trip per `uuid` column and query.

Verification:

- Two new integration tests (same SQL after a type change by DDL; same SQL on a second connection with its own temporary view) fail on the old code and pass on the new one.
- PostgreSQL adapter unit tests 180 (1 skipped), codec integration tests 7, PHPStan and php-cs-fixer clean.
- DAL integration suite on PostgreSQL: 804 tests, 1 failure, `MultiInsertQueryQueueTest::testNullableDatetime`, the known timing flake (`docs/15-id-spike.md`, `docs/20-currency-seo-codec.md`).
- Storefront requests (home, category, search, login, cart): 385 statements, 0 cache drops.
  Before the `#` comment fix, 16 of 169 statements dropped it.
- The reviewer's reproduction returns 16 bytes for the `uuid` column and 36 characters for the `text` column in both orders.

Not covered, documented in the class: DDL by another process while a long-running worker keeps running, and DDL inside a function called from a `SELECT`.

## P2: batched updates and unique constraints (DAL v2, lever W1b)

Problem: one `UPDATE ... CASE` checks unique indexes row by row in the order the plan visits the rows, single updates check them in command order.
With `a = 1, b = 2`, "b to 3, a to 2" succeeds one by one but fails as one statement when `a` is changed first; "a to 2, b to 3" fails one by one but can succeed as one statement.
The order inside one statement is not stable: on SQLite it differed between bound parameters and literal values.

Fix (`poc/orm-spike` commits `9cbb0be4f9e` and `c8c6866ac19`): an update that changes a column of a unique index or of the primary key is never batched.
The unique columns are read once per table and process through the DBAL schema manager.
DBAL skips the internal `sqlite_autoindex_*` indexes (`SQLiteSchemaManager::selectIndexColumns()`, `NOT LIKE 'sqlite_%'`), which back inline `UNIQUE` constraints such as `product.product_number`; on SQLite the gateway reads `pragma_index_list` itself.

## P3: failure attribution of a failed batch

Problem: when a batch failed, no command was marked failed, or the command that only triggered the flush was, so `WriteCommandExceptionEvent` listeners and import/export (which counts errors from `isFailed()`) blamed the wrong row.

Fix (commit `9cbb0be4f9e`): each batch runs inside the savepoint `dal_v2_batched_update` when a transaction is open.
On an error the gateway rolls back to the savepoint and replays the commands of the batch one by one; the first command that fails is marked failed and its exception is thrown.
The command that triggered the flush is no longer marked.

## Verification of P2 and P3

`tests/unit/Core/Framework/OrmSpike/DalV2/Write/WriteGatewayV2BatchSemanticsTest.php` runs on in-memory SQLite, or on another engine through `DAL_V2_GATEWAY_TEST_URL` (plus the same `DATABASE_URL` for MySQL and MariaDB, the identifier quoting follows the global dialect).

| Test | What it checks |
|---|---|
| `testNonUniqueColumnsAreStillBatched` | three stock updates are one `UPDATE` |
| `testUpdatesOfAUniqueColumnAreSentOneByOne` | three updates of an inline `UNIQUE` column are three statements |
| `testUniqueSwapThatSucceedsOneByOneSucceedsWithBatching` | "b to 3, a to 2" succeeds with and without batching |
| `testUniqueSwapThatFailsOneByOneFailsWithBatching` | "a to 2, b to 4" fails on `a` with and without batching, rows unchanged |
| `testFailedBatchMarksTheFailingCommandForTheExceptionEvent` | a CHECK violation of the second of three commands marks only that command, also inside the event listener |

- Old gateway: 3 of the first 4 tests fail on SQLite, MySQL 8.4, MariaDB 10.11 and PostgreSQL 18.
  `testUpdatesOfAUniqueColumnAreSentOneByOne` was added afterwards and failed on SQLite with the first fix (1 statement instead of 3); the replay had hidden the missing detection in the other tests.
- New gateway: 5 tests, 16 assertions pass on all four engines.
- The reviewer's reproduction script matches the one-by-one behaviour on SQLite, MySQL and MariaDB.
- `tests/integration/Core/Framework/OrmSpike` and `tests/unit/Core/Framework/OrmSpike` on PostgreSQL: 9 tests, 32 assertions pass.
- PHPStan reports only the 6 "Expected domain exception class" findings that exist on the gateway before this change.

Not rerun: the S4 timings of docs 33 to 36.
The fix adds a savepoint and its release per chunk of up to 100 rows, and the schema introspection costs about 8 to 30 ms per table, once per process; updates of unique columns (for example `productNumber`) are no longer batched at all.
The E3.04 draft (`docs/issues/E3-dal-v2/04-batched-entity-updates.md`) now lists both rules; the filed issue https://github.com/shopware/shopware/issues/23308 does not have them yet.

## Related upstream work

The open pull request https://github.com/shopware/shopware/pull/18898 batches the indexer updates of E2.01 with a `MultiUpdateQueryQueue` in the same `CASE ... ELSE <column> END` shape.
The two rules above do not apply to it: the columns it writes (`cheapest_price`, `category_tree`, `path`, `level`, `thumbnails_ro`) are in no unique index of `product`, `category` and `media`, and there are no write commands to mark failed.
The `ELSE <column>` branch also keeps it free of casts on PostgreSQL (`docs/36`).
Its `display_group` statements keep `SHA2(HEX(...))`, which is MySQL-only, as trunk does today.

## Correction: "0 schema differences against MySQL"

The summary, the final report, the E5 drafts and the video said that all 910 core migrations run on PostgreSQL with zero schema differences to MySQL.
What `scripts/check-migrations-on-postgresql.sh` checks (rerun 2026-11-23: 910 of 910 migrations, 2,168 columns, 726 indexes, 1,878 constraints, 0 differences):

- It compares the PostgreSQL catalog with `scripts/expected-catalog.json`, written on 2026-11-18 from a database built by `docs/inventory/schema/mysql-to-pg-ddl.py`, which converts the installed MariaDB schema.
  So it proves that the PHP rewriter and a second, independent converter produce the same PostgreSQL structure; both use the same type mapping (`BINARY(16)` to `uuid`, `TINYINT(1)` to `boolean`, JSON `LONGTEXT` to `jsonb`, ...).
- Names, column order and comments are not compared (`docs/07-migrations-on-postgresql.md`).
- `system:install` runs `core.V6_3` to `core.V6_7` only, 910 migrations.
  The 22 `core.V6_8` migrations, five of them PostgreSQL-only, are not in the check; with them applied, the catalog has 6 intended differences (`docs/13-benchmark.md`).
- Behaviour differs on purpose where the structure is equal, for example string filters (`lower(col) COLLATE ucs_basic`, case-insensitive but accent-sensitive, `docs/02-decisions.md`) and the NULL order of sorts.

The wording is corrected in `docs/summary.md`, `docs/27-final-report.md`, `docs/10-architecture.md`, `docs/issues/E5-postgresql/00-epic.md`, `docs/issues/E5-postgresql/01-postgresql-driver.md`, `video/build.py` and `video/deck.html`.
The dated logs (`docs/06`, `docs/18`) keep their wording, it records what was reported at the time.

## Evidence limits that stay

- PostgreSQL stays experimental, and the batched update stays behind its experimental switch.
- The DAL suite is green on PostgreSQL apart from the known timing flake; other integration areas were measured in wave 3 at about 90 percent (`docs/09`) and not rerun completely.
- Timings come from one machine and one data set.
