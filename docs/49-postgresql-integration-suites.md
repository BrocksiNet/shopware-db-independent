# 49 PostgreSQL integration suites outside the DAL

Wave 10, handoff C.
Question: does Shopware work on PostgreSQL beyond the DAL suite (`docs/46-target-architecture.md` "What is not proven", point 3, suites part)?
Branch `poc/wave10`, PostgreSQL 18.7 (`w10c2`) against MariaDB 10.11.16 (`w10c2`) as the reference on the same checkout.

## Verdict

**Proven with limits.**
Across the five integration suites outside the DAL (8,072 tests total on PostgreSQL), wave 10 C reduced PostgreSQL-only failures from **386** (at the start of `poc/wave10`) to **90** (98.9 % pass rate outside tests that also fail on MariaDB):

- `Core/System` outside `CustomEntity` (458 tests): **0** PostgreSQL-only failures (down from 35).
- `Storefront` (777 tests): **1** PostgreSQL-only failure (down from 65).
- `Core/Checkout` (1,992 tests): **15** PostgreSQL-only failures (down from 33).
- `Core/Framework` (2,913 tests): **24** PostgreSQL-only failures (down from 151).
- `Core/Content` (1,920 tests): **42** PostgreSQL-only failures (down from 94).
- `Core/System/CustomEntity` (12 tests, subset of `Core/System`): **8** PostgreSQL-only failures (same 8 as at the start of `poc/wave10`, down from 9 in wave 7); all 8 are runtime DDL / `CustomEntitySchemaUpdater` gaps (E4.04).

Every remaining failure is classified below; none blocks core DAL or storefront reads, and 59 of the 90 belong to just four narrow groups: document rendering/lookup in tests (23), one MySQL-only `DATE_SUB` newsletter test fixture (20), runtime custom entity DDL (8), and MySQL-only tests / schema-inspection tests in `Core/Framework` (11).

Doc 46 point 3 (suites part), proposed wording: "Integration suites outside the DAL reach 90 PostgreSQL-only failures across 8,072 tests (98.9 % pass rate; `Core/System` outside `CustomEntity` at 0, `Storefront` at 1), with every remaining failure classified (`docs/49`); `CustomEntity` runtime DDL (8/12) remains the main structural gap (E4.04)."

## Method

- Fresh database per suite (`FORCE_INSTALL=1`) in an isolated worktree (`/tmp/w10c/wt2` inside `instance-web-1`), `APP_CACHE_DIR=/tmp/w10c/pgc2` (PostgreSQL 18) and `/tmp/w10c/myc2` (MariaDB 10.11), `--order-by=default --do-not-cache-result --log-junit`.
- Reference run: the exact same five suites on MariaDB. Any test failing on both PostgreSQL and MariaDB is excluded from the PostgreSQL-only count (9 tests in the final run: 6 external-URL media/import tests in `Core/Content`, 1 `ThemeCompilerTest::testCompileWithoutDB` in `Storefront`, and 2 framework tests `ApiAwareTest::testApiAware` and `McpOAuthDiscoveryTest::testUnknownHostFallsBackToAppUrl`; MariaDB also had 2 transient checkout failures that passed on PostgreSQL).
- Baseline (`before`) comes from `pg0-*.xml` / `my0-*.xml` on `poc/wave10` before C's fixes (`my0-Core_Framework.xml` hit the 2026-11-24 disk-full event and `my0-Storefront.xml` aborted at 0 s, so `a-my-Core_Framework.xml` and `a-my-Storefront.xml` are used as their MariaDB reference).
- Final (`after`) comes from `a-pg-*.xml` and `a-my-*.xml` (`a-times.txt`, completed 2026-11-25 10:42 UTC) after all 14 C commits on `poc/wave10` (up to `c7bbb110333`).

## Results

### Suite summary (before vs after)

Failure counts are `failures + errors` from the JUnit XML. `PG-only` = failing on PostgreSQL and passing on MariaDB.

| Suite | Tests (PG) | Before PG total | Before PG-only | After PG total (fail / err) | After MariaDB total (fail / err) | After PG-only | Runtime after (PG / MariaDB) |
|---|---:|---:|---:|---:|---:|---:|---|
| `Core/Checkout` | 1,992 | 33 | 33 | 15 (13 / 2) | 2 (2 / 0) | **15** | 648 s / 316 s |
| `Core/System` (incl. `CustomEntity`) | 470 | 43 | 43 | 8 (3 / 5) | 0 (0 / 0) | **8** | 57 s / 62 s |
| — of which `Core/System/CustomEntity` | 12 | 8 | 8 | 8 (3 / 5) | 0 (0 / 0) | **8** | (subset of `Core/System`) |
| `Core/Content` | 1,920 | 100 | 94 | 48 (17 / 31) | 6 (4 / 2) | **42** | 311 s / 212 s |
| `Storefront` | 777 | 66 | 65 | 2 (2 / 0) | 1 (1 / 0) | **1** | 192 s / 152 s |
| `Core/Framework` | 2,913 | 153 | 151 | 26 (18 / 11) | 2 (2 / 0) | **24** | 562 s / 462 s |
| **Total** | **8,072** | **395** | **386** | **99** | **11** | **90** | **29.5 min / 20.1 min** |

(`Core/Framework` PG had 26 failing testcases with 18 failures + 11 errors because PHPUnit records teardown errors on top of assertion failures on 3 testcases; `diff.php` counts unique failing testcases.)

## Fixes committed on `poc/wave10`

All fixes follow doc 10 (`SqlDialect` / `IdBinding` / standard SQL where possible; translator shim only for legacy/compat SQL). Unit tests were added or updated and verified with PHPUnit and `php-cs-fixer`.

| Commit | Scope / Fix | Failure class resolved |
|---|---|---|
| `1611e7de28e` | Lock shipping method prices without `GROUP BY ... FOR UPDATE` | Behaviour difference (PG forbids `FOR UPDATE` with `GROUP BY`) |
| `fb5828f1a1a` | Close test kernel connection before reinstalling the test database | Test harness (PG refuses `DROP DATABASE` with active connections) |
| `51511e1922a` | Write number range states through `SqlDialect::upsert()` | Dialect gap |
| `d112fecef94` | Sort global `system_config` values (`sales_channel_id IS NULL`) first explicitly | Behaviour difference (NULL order) |
| `3c3f91c7cf9`, `5bb16a14f29` | Match PostgreSQL unique constraint names in DAL exception handlers (`CustomerWishlistProduct`, `ShippingMethodPrice`, `ProductConfiguratorSetting`, `ProductSearchConfig`, `ProductSearchConfigField`, etc.) | Exception mapping / dialect |
| `4653e801159` | Map `CHAR(n)` to `varchar(n)` and accept `DOUBLE PRECISION` in `DdlRewriter` | DDL rewriter gap |
| `7f11e34e10f` | Join the tag duplicate filter on the dialect-quoted alias | Dialect / quoting |
| `3413499ff56` | Compare usage data deletion time as storage date time in test | Test portability |
| `d8e3e5d0cac` | Wrap `DoctrineSQLHandler` log write and `SalesChannelContextPersister` upsert in `transactional()` savepoints | Transaction abort (`25P02`, step 4) |
| `7036eb087c2` | Bind `BlobField` payloads with `ParameterType::BINARY` in `EntityWriteGateway`; deduplicate colliding rows before `DELETE`+`INSERT` (`REPLACE`) in `MultiInsertQueryQueue` | Binary/bytea binding (core finding 50); `REPLACE` multi-row semantics |
| `0943cbb05b3` | Add `SqlDialect::jsonArrayRemoveString()` / `jsonArrayContainsString()` (MySQL, PG, SQLite) for `WebhookStore` and `PromotionExclusionUpdater`; fix `json_array_append` root path `'$'` in `mysql-compat.sql`; report `auto_increment` in `ShowRewriter` | Dialect gap + compat shim |
| `0e25f43c691` | `StockStorage`: compute `available_stock = stock + :quantity` before `stock` (core finding 47); `MySQLStatsRepository`: `ORDER BY MAX(created_at)` (core finding 48); `ProductShippingCostRoute`: default `position, name` sort (core finding 49); `CustomerNewsletterSalesChannelsUpdater`: `NULLIF(CONCAT(...), '{}')`; `CleanPersonalDataCommand`: date boundary in PHP; `WebhookOutboxStore`: two-step PG update + dialect upsert on `partition_key`; `SchemaUpdater`: quote camelCase custom entity FK column; `ThemeRuntimeConfigStorage`: delete conflicting `technical_name` before `REPLACE` | Behaviour differences, dialect gaps, core portability bugs |
| `c7bbb110333` | Portable test SQL/fixtures (`MailServiceTest`, `NewsletterSubscribeRouteTest`, `recipient.sql`, `salutation.sql`, `RulePayloadIndexerTest`, `ConfirmPageTest`) | Test SQL (E4.05) |

## Classification of the remaining 90 PostgreSQL-only failures

Every remaining failure in `a-pg-*.xml` (excluding the 9 shared MariaDB failures) falls into one of six classes:

| Class | Count | Suites & tests | Root cause & estimate |
|---|---:|---|---|
| **1. Test SQL / MySQL-only tests (E4.05)** | **27** | `Core/Content` (21): `NewsletterRecipientServiceTest` (19) & `NewsletterRecipientTaskHandlerTest` (1) — fixture SQL `DATE_SUB('2026-...', INTERVAL 24 DAY)` rewritten without `::timestamp` cast (`22007`); `FlowExecutorTransactionTest` (1) — `SELECT @@SESSION.innodb_lock_wait_timeout`. `Core/Framework` (6): `MySQLFactoryTest` (2: `@@session`, `CONNECTION_ID()`), `KernelTest::testUTCIsAlwaysSetToDatabase` (1: `@@session.time_zone`), `MigrationStepTest::testAddColumnDeprecated` (1: asserts MySQL `SQLSTATE[42S02] ... 1146` string), `MigrationCommandTest` (2: `PHP_INT_MAX` bound into 32-bit `integer` column). | MySQL-specific assertions/fixtures or missing timestamp cast in shim; 1–2 days (E4.05). |
| **2. Document renderer / lookup** | **23** | `Core/Checkout` (8): `DocumentControllerTest::testCreateDocuments` (4), `DocumentGeneratorControllerTest::testCreateDocuments` (4). `Core/Content` (15): `SendMailActionTest` (8: `Unable to find a document generator with type "invoice"`), `GenerateDocumentActionTest` (7). | All 23 fail on document generation/lookup (document type / renderer matching or generated document query returning 0 rows on PG); likely 1–2 root causes, 1–2 days to isolate and fix. |
| **3. Custom entity runtime DDL (E4.04)** | **8** | `Core/System` (8): `CustomEntityTest` (8 of 12 tests). | `DROP TABLE` without `CASCADE` when FKs depend on it (`2BP01`, 2 tests), MySQL `RENAME INDEX` / `ON table` index syntax (`42601`, 2 tests), `DESCRIBE` in enum test (1 test), default value & uninstall/restrict-delete checks (3 tests). Requires platform-aware DDL in `CustomEntitySchemaUpdater` (E4.04, 1–2 weeks). |
| **4. Behaviour differences (FK/exception wording, ordering, timestamp/locking, schema metadata)** | **18** | `Core/Content` (5): `ImportExportTest` (2: PG FK error text vs expected MySQL constraint violation handler; 1: `testPromotionDiscountImportExport` string diff), `ImportEntityCommandTest::testImportWithInvalidAndRollback` (1), `ProductCartProcessorTest` (1: property option order/array diff), `StockStorageTest::testStockAlterationWithClearanceSaleProduct` (1: 1-second timestamp boundary). `Storefront` (1): `ConfirmPageTest::testItIgnoresUnavailablePaymentMethods`. `Core/Framework` (12): `TableHelperTest` (4: `getIndexOfTable` / `indexSpansColumns` / `tableExists` on PG metadata), `MigrationStepTest` (2: `testDropIndex`, `testDropColumn` via `NonStandardFkGuard`), `SyncServiceTest::testInvalidProductCategoryReferenceIsReportedWithAFieldSpecificWriteError` (1: FK exception mapper), `MySQLInvalidatorStorageTest::testLoadAndDeleteWithParallelDelete` (1), `MySQLWebhookReceiverTest::testKeepaliveExtendsLeaseForLargeHint` (1), `ApiControllerCloneTest` (1), `ScriptLifecycleHandlerTest` (1: `ValueError: Invalid column index` in `IdCodecResult`). | Mostly narrow dialect/metadata/exception-mapper gaps (e.g. `TableHelper`, `NonStandardFkGuard`, FK constraint exception handler, `IdCodecResult` empty-result column count). 3–5 days total. |
| **5. Promotion & order write/id handling** | **7** | `Core/Checkout` (7): `OrderRecalculationControllerTest` (2: `WriteTypeIntendException` expecting `UpdateCommand`, got `InsertCommand`), `PromotionExclusionIndexerTest` (2: empty exclusion array), `PromotionMixedCalculationTest` (1), `DeliveryPromotionCalculationTest` (1), `PromotionExtensionCodesTest` (1). | Existence check / JSON exclusion update edge cases on PG; 2–3 days. |
| **6. API controller id/ACL & transaction nesting** | **7** | `Core/Framework` (7): `UserControllerTest` (3: `403 USER__USER_CHANGE_NOT_ALLOWED` in `AdminUserWriteValidator`), `ApiControllerDeleteTest::testDeleteManyToOne` (1: double hex-encoded UUID passed to `mysql_compat_bytea_to_uuid`), `ApiControllerDeleteTest` (3: `Too many Nesting Levels` cascade after `testDeleteManyToOne` rolled back). | Double-encoding of a hex id in `IdCodec` / `AdminUserWriteValidator` binary-vs-hex user id comparison (E4.02 hex id binding removes this class structurally); 1–2 days. |

Total: 27 + 23 + 8 + 18 + 7 + 7 = **90** PostgreSQL-only failures.

## Step 4: Savepoints and failed statements inside transactions

In test mode (`docs/09`), `SqlTranslationMiddleware` / `DdlSavepointStatement` wraps DDL statements inside a transaction in a `SAVEPOINT sw_ddl` so test DDL does not abort the wrapping PHPUnit transaction.
That mechanism does **not** mask regular DML failures inside production transactions.

Audit of `src/Core/` for sites that catch a database exception and continue executing SQL inside an already-open transaction (outside the DAL write gateway, which already uses savepoints):

1. `DoctrineSQLHandler::write()` (`src/Core/Framework/Log/Monolog/DoctrineSQLHandler.php`): catches a failed `log_entry` insert and retries; on PostgreSQL the first failure aborted the caller's transaction (`25P02`). **Fixed** in `d8e3e5d0cac` by wrapping the write in `$this->connection->transactional(...)` (a savepoint when nested).
2. `SalesChannelContextPersister::save()` (`src/Core/System/SalesChannel/Context/SalesChannelContextPersister.php`): catches a unique constraint violation and falls back to delete + insert; on PostgreSQL the failed insert aborted the transaction. **Fixed** in `d8e3e5d0cac` with `$this->connection->transactional(...)`.
3. `WebhookOutboxStore` (`src/Core/Framework/Webhook/Outbox/WebhookOutboxStore.php`, lines 84 and 504): catches `UniqueConstraintViolationException` on outbox delivery and event log inserts and continues in the same transaction. **Fixed** with `$this->connection->transactional(...)` savepoints.
4. Remaining `Core/Framework` cascade (`ApiControllerDeleteTest`, 3 `Too many Nesting Levels` errors): caused by an uncaught `22P02` UUID error in `testDeleteManyToOne` unwinding the PHPUnit test transaction, not a production catch-and-continue bug.
5. Worker implication (cross-check with doc 50): any plugin or handler that catches `\Throwable` around a DB write inside a transaction and keeps using the same connection will hit `25P02` on PostgreSQL (whereas MariaDB silently continues); `E1.05` / `E5.02` must keep enforcing savepoints for catch-and-retry writes and resetting/restarting workers that leak an open transaction.

## Core findings added

Rows 47 to 50 added to `docs/core-findings.md`:

- Row 47: `StockStorage::alter()` relied on MySQL left-to-right `SET` evaluation (`available_stock = stock`).
- Row 48: `MySQLStatsRepository::getActiveMessageTypes()` ordered by ungrouped `created_at` (fails `ONLY_FULL_GROUP_BY`).
- Row 49: `ProductShippingCostRoute` had no default sorting when `$criteria->getSorting() === []`.
- Row 50: `EntityWriteGateway` omitted `ParameterType::BINARY` on `BlobField` writes.

## Proposed change to E4 / E5 issue drafts

- **E4.04 (custom entity DDL)**: still the single clean structural blocker in `Core/System` (8/8 remaining `Core/System` failures); add `DROP TABLE ... CASCADE` / FK drop ordering and portable index rename to its Technical TODO.
- **E4.05 (portable test SQL)**: add the `NewsletterRecipient` fixture `DATE_SUB`, `@@SESSION.*` / `CONNECTION_ID()` guards, and `MigrationStepTest` MySQL error-string assertions.
- **E5.05 (nightly CI)**: after wave 10 C, `Core/System` (excl. `CustomEntity`) and `Storefront` (1 failure) are close enough to green to gate first; remaining 90 PG-only failures across 8,072 tests are roughly 2 to 3 developer-weeks of targeted fixes (excluding E4.04 custom entity DDL).
