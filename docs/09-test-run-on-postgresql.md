# PHPUnit on PostgreSQL: first measurement (phase 6)

Date: 2026-11-19.
Scope: make the integration tests bootstrap and run against PostgreSQL, count pass and fail per area, classify the failures.
Base: `instance/` branch `poc/postgresql`, PostgreSQL 18, PHP 8.4 (lane `pg`).

## What was needed to bootstrap

The bootstrap (`src/Core/TestBootstrap.php`, `TestBootstrapper`) appends `_test` to the database name from `DATABASE_URL` and installs it, so the lane database `shopware` is never touched.
On PostgreSQL the installer failed in one place: `INSERT INTO user (...)` (a reserved word, the translator did not quote it), fixed in commit `c128cd391bc`.
Nothing else in the bootstrap needed a platform branch: the test database `shopware_test` is created and installed (251 tables, the same count as the lane database).

PostgreSQL differs from MySQL in one way that hits almost every integration test.
Each test runs inside a transaction (`DatabaseTransactionBehaviour`), and application code catches failing statements (unique violation in the context persister, `SET FOREIGN_KEY_CHECKS`, ...).
MySQL keeps the transaction usable after such a failure, PostgreSQL aborts it (`current transaction is aborted`), and the nesting check of the trait then fails every following test of the run.
In test mode (`DATABASE_URL` starts with `pgsql:` or `postgres:`, the bootstrap sets `SHOPWARE_PG_STATEMENT_SAVEPOINTS=1`) the SQL translation middleware runs each statement inside a transaction in its own savepoint.
Production behaviour is unchanged, the flag is off outside the test bootstrap.

## Commands

```bash
# inside the lane container, DATABASE_URL=pgsql://shopware:shopware@postgres:5432/shopware (test database: shopware_test)
podman exec instance-web-1 sh -c 'cd /var/www/html; vendor/bin/phpunit tests/unit --no-progress --log-junit /tmp/d-unit.xml > /tmp/d-unit.txt 2>&1'
podman exec instance-web-1 sh -c 'cd /var/www/html; vendor/bin/phpunit tests/integration/Core/Framework/DataAbstractionLayer --no-progress --log-junit /tmp/d-dal.xml > /tmp/d-dal.txt 2>&1'
# same for Core/Content/Product, Core/Content/Newsletter, Core/Checkout, Core/System
# MySQL comparison: DATABASE_URL=$MYSQL_URL in front of vendor/bin/phpunit
```

The mysql-compat functions are loaded into `shopware_test` with `psql -d shopware_test < mysql-compat.sql` (idempotent), as for the lane database.
Runtime: the five integration areas take between 5 and 11 minutes together.

## Counts

Final run, after the fixes below.
"Failed" is the number of tests with an error or a failure in the JUnit log.

| Area | Tests | Failed | Skipped | Passed | Before the fixes (errors + failures) |
|---|---|---|---|---|---|
| `tests/unit` | 24288 | 3 | 11 | 24273 (1 incomplete) | 3 |
| Framework/DataAbstractionLayer | 801 | 184 | 0 | 617 | 420 + 278 |
| Content/Product | 658 | 54 | 7 | 597 | 97 + 12 |
| Content/Newsletter | 62 | 22 | 0 | 40 | 28 + 1 |
| Checkout | 1992 | 57 | 22 | 1913 | 1288 + 864 |
| System | 470 | 85 | 0 | 385 | 97 + 40 |
| Integration total | 3983 | 402 | 29 | 3552 | |

- The 3 unit failures are `ThumbnailServiceTest::testGenerateRotatesImageForExifOrientation`, they fail the same way on MySQL (3 of 23 tests in that file), not a PostgreSQL issue.
- MySQL check after the changes (`DATABASE_URL=$MYSQL_URL`): `LoginRouteTest` 8 of 8, `EntityRepositoryTest` 40 of 40, `Content/Newsletter` 62 of 62, `Content/Product/Stock` 39 of 39 pass.
- The System numbers vary between runs (136, 74 and 85 failed in three runs, with fixes in between).
  The last run has 19 failures `column product.ce_blog_comment_products_id does not exist` (custom entity tests); `shopware_test` has no such column afterwards, the cause was not investigated.

## Fixes done in this phase (each committed in `instance/`, not pushed)

| Commit | Fix | Effect |
|---|---|---|
| `c128cd391bc` | quote `user` in `INSERT INTO user (...)` | the bootstrap installs on PostgreSQL |
| `06c3ae98d1f` | `SET FOREIGN_KEY_CHECKS=...` sent through `executeQuery()` goes through the DDL rewriter | tests that toggle the switch no longer abort |
| `06c3ae98d1f` | alias the three `LOWER(HEX(..))` columns of `SalesChannelContextRestorer::restoreByCustomer` | PostgreSQL named all three `lower`, the associative result collapsed to one value and `salesChannelId` was `null` (384 TypeErrors in Checkout alone) |
| `2fb35ad766b` | per statement savepoints in test mode | removed the cascade, Checkout from 2152 to 57 failing tests |
| `4b219541628` | `ROUND(double, n)` and `QUARTER(ts)` shims | stock and date histogram queries |
| `1bc106c6a52` | `INTERVAL :n UNIT` rewrite and `DATE_ADD` / `DATE_SUB` shims | context persister cleanup and `SalesChannelContextPersisterTest` |
| `46d6034ce0a` | the middleware unit tests switch the test mode off | keeps the unit suite green when run with a PostgreSQL URL |

Unit tests exist for the translator, the savepoint mode and the query path; the SQL shims are verified by `psql` and the integration runs only.

## Failure classes (402 failing integration tests)

Classified by the first PostgreSQL error in the failure text or the exception class.
The "assertion" row has no PostgreSQL error in its message and was not analysed one by one.

| Class | DAL | Product | Newsletter | Checkout | System | Total | Example |
|---|---|---|---|---|---|---|---|
| Assertion or other, no SQL error in the message | 63 | 25 | 2 | 26 | 34 | 150 | `TreeIndexerTest::testIndexTree`, `StockStorageTest` (stock 5 instead of 4) |
| `CREATE TABLE` of test tables fails: `Unmapped MySQL type key for x.primary` | 29 | 0 | 0 | 0 | 14 | 43 | `WriteProtectedFlagTest`, `StateMachineRegistryTest` |
| Cascade after an aborted or unclosed transaction | 34 | 0 | 0 | 0 | 0 | 34 | `SetNullOnDeleteTest` |
| Other PostgreSQL errors (missing custom entity columns, unknown type) | 6 | 1 | 0 | 0 | 19 | 26 | `CartRestorerTest` (`product.ce_blog_comment_products_id`) |
| Missing JSON function with more arguments: `JSON_SET` with two pairs, `JSON_MERGE`, `JSON_SEARCH`, `JSON_LENGTH` of `json` | 7 | 17 | 0 | 1 | 0 | 25 | `ProductSearchKeywordAnalyzerTest`, `VersioningCustomFieldTest` |
| User variable `SET @languageId = ...` in a test fixture (MySQL only) | 3 | 1 | 20 | 0 | 0 | 24 | `tests/integration/Core/Content/Newsletter/fixtures/recipient.sql` |
| `JSON_VALUE(... RETURNING/USING ...)` syntax | 7 | 2 | 0 | 12 | 0 | 21 | `CustomFieldTest::testSearch` |
| Unique or foreign key violation where MySQL is more lenient | 12 | 2 | 0 | 4 | 2 | 20 | `EntityRepositoryTest::testOrderTransactionsQueries` |
| `GROUP BY` strictness (selected column not in the group) | 10 | 5 | 0 | 0 | 0 | 15 | `EntityAggregatorTest::testDateHistogram...` |
| Text compared with or cast to integer (`invalid input syntax for type integer`) | 13 | 1 | 0 | 1 | 0 | 15 | `EntitySearcherTest::testTotalCountsEntitiesWithASearchTerm` |
| Syntax error elsewhere (quoted alias, enum column in custom entity) | 0 | 0 | 0 | 0 | 14 | 14 | `IncrementSqlStorageTest`, `CustomEntityTest` |
| `FOR UPDATE` together with `GROUP BY` | 0 | 0 | 0 | 13 | 0 | 13 | `ShippingMethodValidatorTest` |

Reading of the classes:

- Test assumes MySQL behaviour: user variables in fixtures, tests that create tables by hand with MySQL DDL (the DDL rewriter does not map the type of the primary key column of these tables), lenient unique keys.
- SQL construct not translated: `JSON_SET`/`JSON_MERGE`/`JSON_SEARCH` variants, `JSON_VALUE ... RETURNING`, `FOR UPDATE` with `GROUP BY` (production code in the shipping method validator, needs a rewrite of the query, not a shim).
- Real differences: `GROUP BY` strictness in DAL aggregation queries and text to integer comparisons in search ranking are bugs of the translated SQL that need a fix in the DAL query builders or a rewriter rule, each one is more than a one line shim.
- Not classified further: the 150 assertion failures (examples: stock 5 instead of 4 in `StockStorageTest`, string comparisons in `ProductListingLoaderTest`).

## What is not run

- `tests/integration` outside the five areas: `Administration`, `Storefront`, `Elasticsearch`, the remaining `Core/Content` directories (Category, Cms, Media, Flow, ImportExport, Mail, Rule, Seo, Sitemap, ...), `Core/Framework` outside the DAL (Api, App, Plugin, Webhook, Store, ...), `Core/Maintenance`, `Core/Migration`, `Core/Installer`, `Core/Service`.
- `tests/migration`, `tests/acceptance` (Playwright), `tests/performance`, admin and storefront JavaScript tests.
- The failing classes above were not fixed further than listed in the fix table.
