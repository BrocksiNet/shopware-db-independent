# DAL integration failures on PostgreSQL (handoff E)

The suite is `vendor/bin/phpunit tests/integration/Core/Framework/DataAbstractionLayer` (801 tests).
The handoff started from 167 failures on PostgreSQL and 0 on MySQL.
Every number below says which instance HEAD it was measured at, because handoffs A, C and D commit to the same branch.

## Tooling

`scripts/group-phpunit-failures.py` groups the failures and errors of a junit file by SQLSTATE plus a normalised first message line.
Hex ids become `<id>`, quoted strings become `'?'`, numbers become `N`, the leading test id line is skipped.
Usage: `python3 -I scripts/group-phpunit-failures.py junit.xml --examples 3 [--json out.json]`.

## Measurement setup that matters

Three environment problems distorted the first runs.
They are not product bugs, and the next person will hit them again.

1. The suite database must be private to the run. `shopware_test` exists on MariaDB and on PostgreSQL and every handoff that starts the suite without a different `DATABASE_URL` uses it.
   Runs against one shared test database on MariaDB were flaky (`ManyToOneAssociationFieldResolverTest` passed 5 of 7 runs, then 5 of 5 against a private copy).
   For handoff E the private databases are `shopware_e_test` (a copy of `shopware_test`) on MariaDB and on PostgreSQL, selected with `DATABASE_URL=.../shopware_e`.
   They stay in place after the handoff, the lane database `shopware` was never touched.
2. The test database needs an admin user.
   `UpdatedByFieldTest` failed with "UUID has a invalid length" (8 tests) until a user row existed in `shopware_test`.
   I copied the lane admin user into it (the locale id is the one of the test database).
3. The random test order (`executionOrder="random"` in `phpunit.xml.dist`) makes a handful of tests fail on both databases with a foreign key violation on a language, state or shipping method id that does not exist.
   Example: `RepositoryFacadeTest`, `RepositoryWriterFacadeTest`, `TranslatedVersionsTest::testTranslationsFallbackToOriginal` and `AttributeEntityIntegrationTest::testTranslations` failed in several random-order runs on MariaDB too, and passed alone and in the default order.
   With `--order-by=default` and a private database MariaDB is green: 801 tests, 0 failures (HEAD a27c84adfe3).
   I did not find which test leaves the stale id behind (the ids are not in the cache directories, Valkey, `/tmp` or the databases I grepped), so this is left open.
   For comparable numbers all final runs below use `--order-by=default`.

## Before and after

Before: 172 failures in my first complete run (the handoff says 167; I did not find out where the five extra come from).
An earlier run with 761 tests was invalid because another session restarted PostgreSQL during it.
After: 24 failures with the default order at HEAD a27c84adfe3 on PostgreSQL, 0 on MariaDB.
Random-order runs on PostgreSQL gave 20 to 32 depending on HEAD and on the stale id flakiness above.

| Group (before, 172 failures) | Count | SQLSTATE | Layer | After |
| --- | --- | --- | --- | --- |
| Transaction of the previous test not closed (cascade) | 34 | - | cascade of the groups below | gone |
| `WriteTypeIntendException`, expected `InsertCommand` (cascade, rows left behind) | 32 | - | cascade | gone |
| `Unmapped MySQL type key for <table>.primary` | 29 | - | DDL rewriter | gone |
| Strict GROUP BY: `product.release_date` must appear in GROUP BY (date histogram) | 10 | 42803 | DAL | gone |
| `invalid input syntax for type integer: "N.N"` (score literal bound as text) | 10 | 22P02 | DAL | gone |
| Aggregate results differ as strings (`50.0000` expected) | 9 | - | price accessor | 8 left (handoff C) |
| `UUID has a invalid length` (`UpdatedByFieldTest`, no admin user in the test database) | 8 | - | test database | gone |
| Foreign key violation on `order` (`SET FOREIGN_KEY_CHECKS=0` was a no-op) | 8 | 23503 | translator | gone |
| `WasModifiedByUserFieldTest` (table declared `VARBINARY(16)`) | 7 | - | test assumes MySQL | gone |
| `product_search_keyword` foreign key | 4 | 23503 | indexer | 6 left (handoff B) |
| `SET @n = 0, @c = null` for paginated many to many | 3 | 42601 | DAL | gone |
| App synchronisation foreign key (stale language id) | 3 | 23503 | test environment | 1 left (open) |
| JSON field tests (`longtext` column, jsonpath error text, key order) and price json functions | 3 | 42883, 42601 | test assumes MySQL | gone |
| `CustomFieldTest::testStringEqualsCriteria` | 2 | - | collation | 2 left (decision) |
| Single tests (range aggregation 42804, restrict 23001, upsert 21000, indexers, tree, since, command) | 15 | mixed | see below | 8 left |

The "after" column counts the same groups in the default-order run at HEAD a27c84adfe3, so it also shows failures that were hidden behind the cascades before.

## Fixes per group

| Commit (instance, local) | Fix | Why this layer |
| --- | --- | --- |
| 92fa3568f28 | `DdlRewriter` accepts `PRIMARY KEY name (col)`; five DAL test tables declare ids as `binary(16)` instead of `varbinary(16)` | `Unmapped MySQL type key` came from the rewriter not reading the key with an index name, the `varbinary` declarations are a test-only mismatch with the migrations |
| eea83e91100 | Date histogram default sorting is `MIN(<accessor>)` | PostgreSQL requires every non-grouped column in an aggregate query to be aggregated |
| fdaa5cf5eaa | `SqlQueryParser` writes the score as a numeric literal (`%.14F`) in both `IF()` expressions | the translated `CASE WHEN ... THEN '?'` bound the float as text and PostgreSQL could not add it |
| b1f5b09d463 | `EntitySearcher` adds the to-many join state for score queries on PostgreSQL | `CriteriaQueryBuilder` removes the state for `limit 1` without total count, which left an aggregate score query with no GROUP BY |
| 689f915b106 | `SET FOREIGN_KEY_CHECKS=0/1` toggles `session_replication_role` replica/origin (translator, `DdlRewriter`) | tests and old migration code switch foreign key checks off; the switch was a `SELECT 1`, so inserts in the "wrong" order failed immediately |
| bae7f55833f | many to many pagination uses `ROW_NUMBER() OVER (PARTITION BY ...)` through a new `SqlDialect::rowNumberPerPartition()`; MySQL and MariaDB return null and keep the `@n`/`@c` counter | PostgreSQL has no session variables; the dialect keeps MySQL SQL and speed unchanged |
| a34954f4002 | `WasModifiedByUserFieldTest` table uses `binary(16)` | same test-only mismatch as above |
| e61e87a2dff | `JsonFieldTest` declares the JSON columns as `json`, compares ignoring key order and accepts the PostgreSQL jsonpath error text | the test created `longtext` columns and `jsonb_path_query_first` has no text overload; PostgreSQL `jsonb` orders keys; the error text is database specific |
| 38217724f21 | SQLSTATE `23001` becomes `ForeignKeyConstraintViolationException` in `ExceptionConverterMiddleware` | MySQL reports `ON DELETE RESTRICT` as a foreign key violation (1451), PostgreSQL has its own SQLSTATE |
| 287ed2682c0 | range aggregation builds `SUM(CASE WHEN <cond> IS NULL THEN NULL WHEN <cond> THEN 1 ELSE 0 END)` | `SUM(1 AND x >= a)` relies on MySQL treating a boolean as an integer; the CASE gives the same result on every database |

Translator shim: two changes touch it (`SET FOREIGN_KEY_CHECKS` and the `PRIMARY KEY name` regex).
Both are old SQL, not DAL SQL: tests and migrations send these statements as strings.
No alternative through `SqlDialect` exists for them, because the callers do not use the dialect.
No other translator rule was added.
No new `ParameterType::BINARY` or `Uuid::fromHexToBytes` call site was added.

## The `VersioningTest::testDeleteNoneExistingVersion` foreign key failure

The failing statement is the insert into `product_search_keyword` with a `product_version_id` that has just been deleted:
`Key (product_id, product_version_id) is not present in table "product"` (reproduced with the single test).

Mechanism, verified in the code:
`product.repository->delete()` in the version context triggers `ProductIndexer`, which calls `SearchKeywordUpdater::update()` for the deleted version.
`SearchKeywordUpdater::insertKeywords()` writes through `new MultiInsertQueryQueue($connection, 50, true)`, the third argument is `ignoreErrors`.
On MySQL that is `INSERT IGNORE`, which turns a foreign key violation into a warning and the row is silently dropped.
On PostgreSQL the same flag is `ON CONFLICT DO NOTHING` (`UpsertRewriter`, `PostgreSqlDialect::upsert`), which only covers unique conflicts, so the foreign key error is raised.

So it is not a delete order problem: the updater indexes a product version that no longer exists, MySQL hides that.
The same mechanism explains `TranslatedVersionsTest` (6 tests).
The fix belongs to handoff B (keyword indexer): skip products that are not in the version anymore, or insert with `INSERT ... SELECT ... WHERE EXISTS`.

## Remaining failures (default order, HEAD a27c84adfe3, PostgreSQL)

| Tests | Count | Cause (verified) | Needed change | Owner |
| --- | --- | --- | --- | --- |
| `EntityAggregatorTest` (testTermsAggregation, testStatsAggregation, testMinAggregation, testMaxAggregation and variants) | 8 | Price aggregates return `'50.0000000000000000'`, the test expects `'50.0000'` (decimal scale of the `ROUND(CAST(... AS DECIMAL(30,20)))` expression in `PriceFieldAccessorBuilder`) | Give the price accessor the same scale on PostgreSQL, or compare numerically in the test | handoff C |
| `PriceFieldTest::testCashRoundingFilter` | 1 | `Failed asserting that false is true`, same price accessor | check after the accessor fix above | handoff C |
| `MultiInsertQueryQueueTest::testAddUpdateFieldOnDuplicateKey` | 1 | `ON CONFLICT DO UPDATE command cannot affect row a second time`, two rows with the same key in one statement | merge duplicates in the queue before the upsert | handoff C |
| `TranslatedVersionsTest`, `VersioningTest::testDeleteNoneExistingVersion` | 6 | see section above | updater skips non-existing versions | handoff B |
| `ManyToManyIdFieldIndexerTest::testResetRelation` | 1 | the id field is `[]` on PostgreSQL where MySQL stores `NULL` after the reset | indexer writes `NULL` for an empty set | handoff B |
| `CustomFieldTest::testStringEqualsCriteria` | 2 | the test expects `custom.string = 'a'` to match `'A'` (MySQL collation), PostgreSQL compares case sensitive | product decision: keep MySQL behaviour through `SqlDialect::caseInsensitive()` or document the difference | decision needed, then DAL |
| `AttributeEntityIntegrationTest::testTranslations` | 1 | foreign key on language, same stale id flakiness as in the setup section | find the test that leaves the stale id | open |
| `RefreshIndexCommandTest::testExecuteWithSkipSeoUpdaterOption` | 1 | not analysed | - | open |
| `TreeIndexerTest::testIndexTree` | 1 | not analysed | - | open |
| `EntityDefinitionHasSinceTest::testAllDefinitionsHasSince` | 1 | reports `custom_entity_test` as the only definition without a `since`, a definition registered by another test | not analysed on MySQL either | open |
| `Facade\RepositoryFacadeTest::testSearchIdsIntegration` | 1 | stale id flakiness (setup section) | - | open |

## Checks

- Adapter unit tests (`tests/unit/Core/Framework/Adapter/Database`): 192 tests, OK on PostgreSQL and MariaDB.
- php-cs-fixer on all touched files: clean.
- PHPStan on the touched source files reports `SqlQueryParser::$connection is never read`.
  That property became unused with the id migration commit 21fc93eedd8, not with a handoff E commit.
- Database changes for this handoff: created `shopware_e` and `shopware_e_test` on both servers (copy of `shopware_test`), inserted the admin user into the PostgreSQL `shopware_test`.
  No `ALTER SYSTEM`, `SET GLOBAL`, restart or extension change.

## Recheck by the coordinator

- Rerun at instance HEAD `b6ae634e8e0` (after handoff D's Content and System commits), default order, `shopware_e`: PostgreSQL 30, MariaDB 0.
  The extra six are the stale id group (`RepositoryFacadeTest` 6 instead of 1, `ManyToOneAssociationFieldResolverTest` 2, which pass alone) plus `SqlQueryParserTest::testFindProductsWithoutCategory`, which also failed alone.
- Cause of `testFindProductsWithoutCategory` and `ManyToManyIdFieldIndexerTest::testResetRelation`: `ManyToManyIdFieldUpdater` writes `CONCAT('[', GROUP_CONCAT(...), ']')`.
  For an empty set MySQL returns `NULL`, PostgreSQL's `CONCAT` ignores the `NULL` aggregate and stores `[]`, so `EqualsFilter('categoryIds', null)` finds nothing.
- Fix `f1b5f0db8f0`: `CASE WHEN COUNT(*) = 0 THEN NULL ELSE ... END`, the same result on both databases.
  Both tests pass on PostgreSQL and MariaDB; existing rows with `[]` are corrected by `dal:refresh:index`.
- Rerun at `f1b5f0db8f0`, default order: PostgreSQL 801 tests, 24 failures (5 errors, 19 failures), MariaDB 801 tests, 0 failures.
  The 24 contain the stale id group with 6 `RepositoryFacadeTest` failures, so the count moves by a few between runs.

## Wave 6 (handoff C)

Runs in default order against private copies of `shopware_test` (`shopware_w6c_test` on PostgreSQL and MariaDB), instance HEAD `f6a37fd183f` before and `a3770fd3f5e` after.
MySQL has no `shopware_test` database in the lane, so the integration suite was not run on MySQL; the unit tests of the adapter and the DAL (1660 tests) ran on MySQL, MariaDB and PostgreSQL.

| | Tests | Failures | Errors |
| --- | --- | --- | --- |
| PostgreSQL before | 801 | 13 | 5 |
| PostgreSQL after | 802 | 1 | 4 |
| MariaDB before | 801 | 0 | 0 |
| MariaDB after | 802 | 0 | 0 |

The 24 failures of the wave 5 recheck were 18 in this first run (the stale id tests passed in all three runs I did, so they are not reproducible here).

### Fix per group

| Group | Cause (verified) | Fix |
| --- | --- | --- |
| `EntityAggregatorTest` 7 of 8, `PriceFieldTest::testCashRoundingFilter` | The cash rounding expression `ROUND(x * m, 0) / m` returns scale 4 on MySQL (`div_precision_increment`) and 16 digits on PostgreSQL. The cash rounding filter failed for another reason: MySQL applies the currency factor to a DOUBLE (`text + 0.0`), PostgreSQL to an exact `numeric`, so `13.016666666666666 * 1.5` is 19.525 in double and 19.52499... exact, which rounds to the other cash step. | `SqlDialect::decimalDivisionScale($sql, 4)` (PostgreSQL `CAST(... AS NUMERIC(30, 4))`, MySQL unchanged) and `SqlDialect::castToFloat($sql)` (PostgreSQL `CAST(... AS double precision)`, MySQL unchanged) in `PriceFieldAccessorBuilder`. |
| `MultiInsertQueryQueueTest::testAddUpdateFieldOnDuplicateKey` | Two rows with the same key in one `ON CONFLICT DO UPDATE` statement. | `MultiInsertQueryQueue::mergeCollidingRows()` merges rows with the same key (first row kept, update columns from the last row) before the statement is built. The key comes from `SqlDialect::upsertCollisionColumns()` (PostgreSQL: conflict target or primary key, other dialects: empty, nothing is merged, SQL unchanged). |
| `CustomFieldTest::testStringEqualsCriteria` (2) | Case-sensitive `=` on the extracted JSON text. | `SqlQueryParser` wraps the accessor of a custom field with a text or html type (`LongTextField`, `StringField` mapping) in `SqlDialect::caseInsensitive()` and binds `SqlDialect::caseInsensitiveValue($value)`, for `EqualsFilter` and `EqualsAnyFilter`. MySQL and MariaDB SQL and parameters are unchanged. No index is lost: there is no index on `custom_fields` in the PostgreSQL schema (no `pg_indexes` entry mentions `custom_fields`), the filter was a sequential scan before. |
| `TreeIndexerTest::testIndexTree` | The test resets the rows with `WHERE HEX(id) IN (:ids)`; `HEX()` is upper case, the ids are lower case, and only a case-insensitive collation matches. The `UPDATE` changed no row. | The test binds the ids through `IdBinding`. |
| `RefreshIndexCommandTest::testExecuteWithSkipSeoUpdaterOption` | Test database, not code: the PostgreSQL `shopware_test` has one sales channel (headless), the MariaDB one also a storefront channel with a domain. Without a storefront channel the SEO URL updater has nothing to generate (`seo_url` stays empty). After `APP_ENV=test bin/console sales-channel:create:storefront` against `shopware_w6c_test` the test passes. | none in code; the private copy got a storefront sales channel. `shopware_test` on PostgreSQL still lacks it, the next run on a fresh copy needs the same command. |
| `EntityDefinitionHasSinceTest::testAllDefinitionsHasSince` | Test database, not code: the PostgreSQL `shopware_test` held a leftover `custom_entity` row `custom_entity_test` (from a failed `CustomEntityLifecycleServiceTest` run, a custom entity registers a definition from that table). The row was gone after the next CustomEntity run and the test passed. MariaDB had no such row. | none in code. Cause of the leftover: `tests/integration/Core/System/CustomEntity` fails on PostgreSQL, first error `Unmapped MySQL type bytea for custom_entity_test.id` in `DdlRewriter.php:722` while the schema updater creates the custom entity table. |

### Left

| Tests | Count | Cause (verified) | Needed change | Owner |
| --- | --- | --- | --- | --- |
| `EntityAggregatorTest::testTermsAggregationWithSorting` | 1 | A terms aggregation sorted by `product.categories.name` DESC returns the NULL bucket first on PostgreSQL (`NULLS FIRST` is the default for DESC), the test expects it last as on MySQL. The DAL states no NULL order anywhere (`grep NULLS` finds nothing). | The same fix applies to every `ORDER BY` of `FieldSorting`: `NULLS LAST` for DESC and `NULLS FIRST` for ASC through the dialect. It changes the read path SQL shape and a default btree index can not serve `ASC NULLS FIRST`, so it needs a measurement first. Not done here. | handoff D (read path) |
| `TranslatedVersionsTest` (3), `VersioningTest::testDeleteNoneExistingVersion` | 4 errors | `product_search_keyword` rows for a product version that was already removed, see the section above. | fixed in wave 6 B (below) | done |
| `CustomEntityLifecycleServiceTest` (outside the DAL suite) | not counted | `Unmapped MySQL type bytea for custom_entity_test.id`, see above | `DdlRewriter` mapping for custom entity tables | handoff B or A (schema) |
| `VariantListingIndexerTest` (4 errors) | 4 | `GROUP BY` error on PostgreSQL in the variant listing indexer, seen in the wave 6 B run of `tests/integration/Core/Content/Product/DataAbstractionLayer` ([docs/19](19-postgresql-parallel-writes.md) "Wave 6"); the same 7 tests fail with the code before `38f1d41ac6c`, so they predate wave 6 B; cause not analysed | not analysed | open |
| `VariantListingUpdaterTest::testUpdateAppliesSha256DisplayGroupForListingGroupConfiguration` | 1 | uuid compared with text on PostgreSQL (same source and run as above); cause not analysed further | not analysed | open |
| `ProductSearchConfigFieldExceptionHandlerTest::testDuplicateInsert` | 1 | fails on PostgreSQL (same source and run); cause not analysed | not analysed | open |
| `CheapestPriceTest::testAggregation` | 1 | fails on PostgreSQL (same source and run); cause not analysed | not analysed | open |

Stale id group (`AttributeEntityIntegrationTest::testTranslations`, `RepositoryFacadeTest`, `ManyToOneAssociationFieldResolverTest`): passed in all three default order runs on a private database, no failure to analyse.
I did not bisect it, since it did not reproduce.

### New SqlDialect methods

| Method | MySQL, MariaDB | PostgreSQL | SQLite |
| --- | --- | --- | --- |
| `caseInsensitive($columnSql)` (existing) | column unchanged | `lower(col) COLLATE ucs_basic` | `lower(col)` |
| `caseInsensitiveValue($value)` (new, the bound side of the same comparison) | value unchanged | `mb_strtolower($value)` | `mb_strtolower($value)` |
| `decimalDivisionScale($sql, $scale)` | unchanged | `CAST($sql AS NUMERIC(30, $scale))` | unchanged |
| `castToFloat($sql)` | unchanged | `CAST($sql AS double precision)` | unchanged |
| `upsertCollisionColumns($table, $conflictColumns)` | `[]` | conflict columns or primary key | `[]` |

Handoff D: the string filters for regular columns use the same pair, `$dialect->caseInsensitive($select)` on the column side and `$dialect->caseInsensitiveValue($value)` on the value side (an `IN` list maps each value).
`SqlQueryParser::isCustomFieldString()` is the only place that decides that a column is compared case-insensitive today; D replaces that decision for regular string fields and keeps the two calls.

### Checks

- php-cs-fixer clean, PHPStan clean on the touched files (the unmatched ignore patterns of a partial run and the SQLite middleware errors belong to other work).
- Unit tests: adapter and DAL (1660 tests) OK on MySQL, MariaDB and PostgreSQL; new unit tests for the five dialect methods and the queue merge, new integration test `testStringEqualsAnyCriteriaIsCaseInsensitive` (PostgreSQL and MariaDB OK).
- Commit `87783e92dad` carries the message of this work but contains only a whitespace change of `composer.json` (a path mistake while committing, the file was another session's uncommitted change); the code is in `a3770fd3f5e`.
- Database changes: created `shopware_w6c_test` on PostgreSQL and MariaDB, added a storefront sales channel to the PostgreSQL copy, dropped both at the end.

## Wave 6 (handoff B): versioning failures fixed

Instance commit `e0e6f3d3fae`: `SearchKeywordUpdater::update()` now drops the products that have no row in a non-live version (`filterProductsOfVersion()`, one `SELECT id FROM product WHERE id IN (:ids) AND version_id = :version`) before it indexes keywords, so no keyword row is written for a version the product is not in.
MySQL dropped those rows through `INSERT IGNORE`, PostgreSQL raised the foreign key error (mechanism above).
Checked on PostgreSQL with `TranslatedVersionsTest` and `VersioningTest`: without the commit 4 errors (1 in `VersioningTest`, 3 in `TranslatedVersionsTest`), with it both classes pass (38 and 7 tests); on MariaDB both classes pass as well.
