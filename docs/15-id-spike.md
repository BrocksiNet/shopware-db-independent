# Id spike: hex strings above the connection

Decision of 2026-11-19 (`docs/02-decisions.md`, section "3. Ids" in `docs/10-architecture.md`): code above the connection works with ids as hex strings, the dialect side binds them per database.
This spike inventories the call sites, picks the API, automates the common rewrite with Rector, converts one request path and measures it.

Reproduce:

```sh
python3 scripts/id-pattern-inventory.py instance [--examples 3]   # pattern counts
scripts/id-rector-coverage.sh                                      # Rector on a copy of every affected file, counts before and after
scripts/id-path-flow.sh                                            # store API flow over the converted path (lane helper /tmp/pg-store.sh)
podman cp scripts/id-codec-microbench.php instance-web-1:/tmp/mb.php && podman exec instance-web-1 php /tmp/mb.php
```

## 1. Pattern inventory

Line based count over `instance/src/**/*.php` at commit `cbcca5e236f` plus the spike commits, migrations listed separately (they are frozen code and keep running through the compatibility codec).
A line counts once per pattern it contains.

| Pattern | Example | Hits | Files |
|---|---|---|---|
| bytes as array parameter value | `'id' => Uuid::fromHexToBytes($id)` | 251 | 121 |
| bytes in `setParameter()` | `->setParameter('id', Uuid::fromHexToBytes($id))` | 62 | 37 |
| id list | `Uuid::fromHexToBytesList($ids)` | 138 | 75 |
| list parameter type | `['ids' => ArrayParameterType::BINARY]` | 174 | 98 |
| result id to hex | `Uuid::fromBytesToHex($row['id'])` (+ `...List`) | 186 | 88 |
| id as SQL text | `LOWER(HEX(col))` in SQL strings | 372 | 144 |
| other `fromHexToBytes` (payload values, closures, DAL internals) | `$x = Uuid::fromHexToBytes($id)` | 86 | 46 |
| `UNHEX(...)` in SQL strings | `WHERE id = UNHEX(:id)` | 14 | 8 |

`src` without migrations: 309 files before the spike conversion (the 212 in the decision was counted with a narrower pattern set, this inventory also counts `LOWER(HEX())`, `UNHEX()` and the list helpers).
Migrations: 111 files, 160 + 12 + 30 + 50 + 37 + 8 + 117 hits, deliberately not touched.

## 2. API choice

Evaluated:

- Dialect methods only (`idParameterType()`, `idListParameterType()`, `idToText()` of `SqlDialect`): they return types and SQL text, not values.
  MySQL needs 16 bytes as value, so the caller still has to convert hex to bytes and would need the dialect injected into every service (about 300 call sites live in services without a dialect).
- DBAL custom type (`shopware_id`): works for single values (`convertToDatabaseValue()` receives the platform), but not for lists.
  Verified in `vendor/doctrine/dbal/src/ExpandArrayParameters.php` line 93: an array parameter is only expanded when its type is an `ArrayParameterType`, a custom type name is not accepted, and `IN (:ids)` is the most common shape (138 list helper calls).
  A custom type would also not help the `LOWER(HEX())` read side.
- Chosen: a small static facade `Shopware\Core\Framework\Adapter\Database\Dialect\IdBinding` on top of the dialect decision, no second interface.
  `value()`, `values()`, `type()`, `listType()` for binding, `toHex()` / `toHexList()` for results, `text()` for the SQL expression (same output as `SqlDialect::idToText()`).
  MySQL, MariaDB and SQLite bind 16 bytes (`BINARY`), PostgreSQL binds the 32 character hex text (`STRING`), which PostgreSQL parses into the native `uuid`.
  `toHex()` accepts bytes, uuid text and hex text, so a result is correct with and without the id codec.

Why static: it mirrors `Uuid::`, a Rector rule can rewrite to it without constructor and service definition changes, and the active database comes from `ConnectionFactory::getDriver()` like `SqlDialectFactory::getDefault()`.
New code in services that already have a dialect should call `SqlDialect::idToText()` directly.

Open point for the dialect owner: `PostgreSqlDialect::idParameterType()` and `idListParameterType()` currently return `BINARY` (they describe the codec era).
With hex values they have to return `STRING` on PostgreSQL, `IdBinding` should then ask the dialect instead of `getDriver()`.

## 3. Rector rule

`src/Core/DevOps/StaticAnalyze/Rector/BinaryUuidToIdBindingRector.php` (excluded from PHPStan, the Rector classes live in `vendor-bin/rector`):

- `Uuid::fromHexToBytes()` / `...List()` / `fromBytesToHex()` / `...List()` become `IdBinding::value()` / `values()` / `toHex()` / `toHexList()`.
- `ArrayParameterType::BINARY` / `ParameterType::BINARY` become `IdBinding::listType()` / `type()` inside a method that also binds ids through one of those calls.
- `LOWER(HEX(col))` in plain quoted SQL strings becomes `'...' . IdBinding::text('col') . '...'`, the unused `use` lines are removed.

Coverage (`scripts/id-rector-coverage.sh`, applied to a copy of all 309 affected files, all rewritten files lint clean):

| | Before | After | Covered |
|---|---|---|---|
| bytes in parameters, lists, results, other `fromHexToBytes` (without SQL text) | 898 hits | 30 hits | 97 % |
| `LOWER(HEX())` in SQL | 372 hits | 210 hits | 44 % |
| `UNHEX()` | 14 hits | 14 hits | 0 % |
| all hits | 1,284 | 254 | 80 % |

Files: 309 before, 250 changed, 105 still contain at least one pattern (204 files are done completely).
Not covered: `LOWER(HEX())` inside heredocs, nowdocs, interpolated strings and non-column expressions (210 hits in 83 files), `UNHEX()` (8 files), `ArrayParameterType::BINARY` in methods that receive already converted bytes from the caller (29 hits in 21 files).

## 4. Converted request path

Converted with the rule (8 files), then the remaining raw id selects by hand:

- `SalesChannelContextPersister`, `ContextFactory`, `SalesChannelContextRestorer` (context load, persist, restore)
- `ProductListingLoader`, `AvailableCombinationLoader`, `ProductDetailRoute` (listing and detail)
- `ProductCartProcessor`, `CartRuleLoader` (cart)

By hand: `ContextFactory` selects `sales_channel.id`, `language_id`, `currency_id` through `IdBinding::text()`, `SalesChannelContextPersister` replaces `SELECT *` on `sales_channel_api_context` with explicit columns and `IdBinding::text()` for `sales_channel_id` and `customer_id`.
Without this the codec still decoded those result columns (27 and 22 conversions per flow).

Verification:

- Store API flow `scripts/id-path-flow.sh` (context, product, listing, detail, find-variant, add to cart, cart, context switch, 9 requests): all 200 on PostgreSQL.
- Admin product PATCH (`/tmp/pg-w.sh`): 204.
- Integration tests of the touched classes (`SalesChannel/Context`, `ProductListingLoaderTest`, `AvailableCombinationLoaderTest`, `CartRuleLoaderTest`, `ProductCartProcessorTest`, 180 tests): MySQL (MariaDB) 180 of 180 pass.
  PostgreSQL: 9 failures, 3 in `ProductCartProcessorTest::testProductFeaturesContainCorrectInformation` (property option order) and the rest in listing and search tests.
  Both groups fail the same way with the files at the commit before the conversion (`ProductCartProcessorTest` 3 errors and 1 failure then as well, listing and detail classes 7 failures before and after), so they are not caused by the id change.
  The `snippet` upsert error in the same output comes from the DAL work of the dialect handoff.
- Unit tests of `Core/System/SalesChannel`, `Core/Checkout/Cart`, `Core/Content/Product`, `Adapter/Database` (4,723 tests) pass, `IdBindingTest` 4 tests.
- `scripts/check-migrations-on-postgresql.sh`: 0 differences.
- PHPStan: 0 errors on the touched files and the new classes.

## 5. Codec cost

Method: a temporary log in `IdCodecMiddleware::encode()` / `decode()` (not committed) wrote the first application stack frame of every actual conversion while the flow ran with the codec still enabled.
The log is container wide, so the totals include other sessions' requests, the per-file attribution does not.

| | Before | After |
|---|---|---|
| codec conversions attributed to the 8 converted files, one 9 request flow | 85 | 0 |
| codec conversions of the whole flow (all callers, noisy) | about 5,000 | about 5,000 |

The rest is the DAL (`EntityReader` hydration and `EntitySearcher`, `MultiInsertQueryQueue` on writes), the codec cannot be switched off for the request before the DAL core hands out and binds hex ids too.

Per conversion (`scripts/id-codec-microbench.php`, PHP 8.4, 500,000 iterations):

| Operation | ns |
|---|---|
| parameter: `fromHexToBytes` + codec `encode` (before) | 100 |
| parameter: `IdBinding::value` (after) | 44 |
| result: codec `decode` + `fromBytesToHex` (before) | 285 |
| result: `IdBinding::toHex` (after) | 103 |
| codec scan of a non id string value (paid by every bound value, any statement) | 25 |

On the converted path 85 conversions save about 10 microseconds per flow, not measurable against a request of tens of milliseconds.
The gain of the conversion is architectural: no hidden per-value rewrite, no PostgreSQL special case in the call sites, the same code binds MySQL bytes and PostgreSQL hex.
The performance gain only shows once the DAL (about 550 conversions per request in the noisy log, an upper bound) is converted, at roughly 0.1 to 0.2 ms per request.

## 6. Estimate for the remaining files

- 250 of 309 files can be rewritten mechanically with the rule, 204 of the 309 files completely.
  Applying it to the DAL core, `MultiInsertQueryQueue` and the write gateway needs the dialect handoff finished (same files) and a PostgreSQL run of the DAL integration suite: about one day for the run, review and fixes.
- Remaining by hand: 83 files with `LOWER(HEX())` in heredocs and expressions (extending the rule to heredocs would cut most of them, about half a day), 8 files with `UNHEX()`, 21 files whose callers pass bytes (needs a signature decision per class, about one day).
- Estimate in total: 3 to 4 working days for core plus review of a roughly 300 file diff, extensions are out of scope (they keep bytes on MySQL and go through the compatibility codec elsewhere).
  This estimate is not measured beyond the numbers above.

## Open

- `PostgreSqlDialect::idParameterType()` returns `BINARY`, see section 2.
- The rule is not applied to the DAL core and the other 250 files, only to the converted path.
- PostgreSQL failures listed in section 4 exist before and after the change and are not investigated here.

## 7. DAL migration

The DAL now binds and reads ids as hex strings through `IdBinding`, so the `IdCodecMiddleware` has almost nothing left to convert for DAL statements on PostgreSQL.
The numbers come from the temporary conversion log (one line per encode or decode in the middleware, not committed) over three flows: store API checkout, a storefront listing and an admin product PATCH.

### Conversions per flow

| | Before | After |
|---|---|---|
| all conversions (encode plus decode) | 6,465 | 281 |
| decodes (uuid text to 16 bytes) | 4,972 | 23 |

The three flows still pass on PostgreSQL after the change: store flow 0 non-2xx responses, listing 200, product PATCH 204.

What changed in the DAL:

- Reader, searcher, aggregator, `IteratorFactory`, `EntityDefinitionQueryHelper`, `EntityForeignKeyResolver`, field resolvers and accessor builders, `SqlQueryParser`, serializers, indexers, the write classes and `VersionManager` bind with `IdBinding::value()` / `values()` / `type()` / `listType()` and read with `toHex()`.
- Raw id columns are selected through the new `IdBinding::selectText($col)`, which is `REPLACE(col::text, '-', '')` on PostgreSQL and the plain column elsewhere.
  Without it the middleware decodes the dashed uuid text of `SELECT *` or a raw id column to 16 bytes, which no longer matches the hex primary keys.
- `IdBinding::literal()` and a 32 hex character check for values that go into SQL text.
- `EntityWriteGateway::generateChangeSets()` and `RowLoader::load()` normalize the id columns of the loaded rows to hex, so change set before and after values match the primary keys of the write commands.
- Subscribers and validators that bound primary keys as `BINARY` (`OrderStockSubscriber`, `LanguageValidator`, `LockValidator`, `CleanupVersionTaskHandler`, integration, user and service write protection) use `IdBinding::listType()`.
  Binding hex values with a `BINARY` type fails on PostgreSQL with SQLSTATE 22P03.
- `EntityWriteResultFactory::fetchForeignKey()` uses `IdBinding::text(escape($col))` instead of `LOWER(HEX("col"))`, see the translator dependency below.

### Remaining callers, ranked

1. About 126 `ParameterType::BINARY` sites in `src` (without migrations).
   Sites that bind real bytes still work through the middleware.
   Sites that bind values derived from primary keys (`ThemeIndexer`, `ProductVariantsSubscriber`, `ProductSubscriber`, `CustomFieldSearchableSubscriber`, `ProductStreamIndexer`, `MediaPathWriteValidator`, `PromotionRedemptionUpdater`) are not converted and would fail with 22P03 on PostgreSQL once their inputs are hex.
2. `UNHEX()` in SQL text, 0 % covered by the rule.
3. `IterateEntitiesQueryBuilder` (UsageData) still wraps `escape()` in `LOWER(HEX(%s))`, the same quoted-identifier-as-literal risk as `HEX("col")`.
4. Raw id selects outside the DAL (about 23 decodes per flow).

### Rector rule

New patterns from the DAL were added to `BinaryUuidToIdBindingRector`, coverage re-run with `scripts/id-rector-coverage.sh` on a copy of all affected files (249 files, 232 changed, 41 still with hits):

| | Before | After |
|---|---|---|
| all hits | 1,004 | 67 (93 % covered) |
| `LOWER(HEX())` | 340 | 26 |
| `BINARY` types | 139 | 28 |
| `UNHEX()` | 14 | 14 (0 %) |

The numbers of section 3 are the earlier measurement.

### Test results

| Suite | MySQL | PostgreSQL |
|---|---|---|
| DAL integration (801 tests) | 0 failures | 110 errors plus 57 failures = 167 (wave 3: 168) |
| unit (24,337 tests) | 3 failures | 3 failures |

- `scripts/check-migrations-on-postgresql.sh`: 0 differences.
- PHPStan on all touched `src` files: no errors.
- The 3 unit failures on both databases are `ThumbnailServiceTest::testGenerateRotatesImageForExifOrientation` (EXIF rotation), unrelated to ids.
- Tests that hardcoded backticks now fail on PostgreSQL because the dialect quotes with double quotes.
  Adapted to be quote-agnostic: `EntityForeignKeyResolverTest`, `ManyToManyAssociationServiceTest`, `CriteriaQueryHelperTest`, `PriceFieldAccessorBuilderTest`.
- Tests that compared ids as bytes (`EntityWriteGatewayTest`, `RowLoaderTest`) now use `IdBinding::value()` / `toHex()`.
- `MultiInsertQueryQueueTest::testNullableDatetime` failed once on a millisecond format difference and passes alone, a time dependent flake.
- `VersioningTest::testDeleteNoneExistingVersion` fails on PostgreSQL with a `product_search_keyword` foreign key violation, which is the keyword indexer area.

### Dependency on the translator

The DAL now emits quoted identifiers inside functions (`REPLACE("col"::text, ...)`).
`MySQLToPostgreSQLTranslator::isQuotedIdentifier()` decides by position whether a double-quoted token is an identifier or a string literal, and misread these as literals (`InvalidUuid "product_id"`).
Two rules were added there: a quoted token directly followed by `::` is a column, and `("id" IN (?))` is a column.
Those edits are in the translator file of the quoting work and are not part of the DAL commit.

## 8. Remaining call sites (wave 5, handoff D)

### Result

The files outside the DAL that bound ids as raw bytes are converted to the `IdBinding` API in eight commits on `poc/db-independent` in `instance/`.
The commits are `05ef0992853` (Checkout, 30 files), `42c0a093ccf` (Checkout validators), `a27c84adfe3` (Content, 61 files), `b6ae634e8e0` (System, 28 files), `bbe0e03e148` (Framework, 48 files), `acda5200d93` (Storefront, Administration, Maintenance, 21 files), `23891f8a2b9` (test helpers and Elasticsearch admin indexers, 36 files) and `8540b8f60b7` (four selects on the store and admin request path).
`scripts/id-pattern-inventory.py` counts 309 files with a bytes pattern in `src` before the spike conversion and 12 files at the end of this handoff (7 of them are left after the Rector rule is applied, see `scripts/id-rector-coverage.sh`).
Migrations are untouched on purpose (111 files).

### Rector rule

The `LOWER(HEX())` regex of `BinaryUuidToIdBindingRector` now also matches one level of `IFNULL`, `COALESCE` and `IF` around the call.
The rule does not handle `UNHEX()`, nowdoc constants, nested expressions and methods that receive bytes from their callers, those were converted by hand.
It also imported fully qualified class names such as `\DateTime`, php-cs-fixer normalizes them.

### Codec conversions per flow

Measured with a temporary log in `IdCodecMiddleware` (removed again) over `scripts/id-path-flow.sh`-style flows (storefront scenarios, listing, product PATCH, 0 non-2xx).

| State | Conversions |
|---|---|
| before wave 4 | 6465 |
| end of wave 4 | 281 (23 decodes) |
| after this handoff | 204 (8 decodes, 196 encodes) |

The 196 encodes are 178 in `MultiInsertQueryQueue` (handoff C), 14 in `SearchKeywordUpdater` (handoff B), 2 in `StatementHelper` (DAL) and 2 in `RefreshTokenRepository` (opaque bytes of the token family id).
The 8 decodes are 5 in `EntityWriteGateway` (DAL), 2 in `SeoUrlPlaceholderHandler` (handoff C) and 1 in `VariantListingUpdater` (the parent id is bound as bytes in several places).

### Tests

Each area was run on PostgreSQL and MySQL before and after the conversion and the failing sets were compared from the junit XML.
New failures in the after runs were rerun alone, they were parallel session noise (App sync foreign key violations, cookie and stock tests) or failed at baseline.
Last runs of the final commit:

| Area | PostgreSQL | MySQL |
|---|---|---|
| `Core/Framework/Api` | 446 tests, 14 failing, all in the baseline sets of earlier runs except `ApiControllerDeleteTest::testPreventDeletionOfDefaultSalesChannelLanguageFromLanguageList`, which also fails with the four last files reverted | OK |
| `Storefront/Theme` | 150 tests, 3 failing, all in the baseline sets | 1 failing (`ThemeCompilerTest`) |
| `Content/Product/DataAbstractionLayer` | 72 tests, 7 failing, all in the baseline sets | OK |
| DAL integration | 801 tests, 16 failing (167 at the start of wave 5, fixes by handoff E) | 801 tests, OK |
| Adapter unit tests (`tests/unit/Core/Framework/Adapter/Database`) | 192 tests, OK | 192 tests, OK |

### Left, with the reason

- `Installer/Configuration/ShopConfigurationService.php`: not converted (not part of the request path, left as is).
- `Core/Test/Stub/Framework/IdsCollection.php`: test stub, left as is.
- `SearchKeyword/*` and `SearchKeywordUpdater`: handoff B.
- `SeoUrlPersister`, `MultiInsertQueryQueue`, `IdCodecMiddleware`: handoff C.
- `ShippingMethodValidator`: comment only.
- DAL internals, `Adapter/Database` and migrations: out of scope, the codec stays for old migrations and extension SQL.
- Refresh token family id, `VariantListingUpdater` parent id, `SeoUrlPlaceholderHandler`, `StatementHelper`, `EntityWriteGateway`: see the conversion table.

### Pitfall

`IdBinding::toHexList()` drops array keys (`array_values`).
Where keys matter (`fetchAllKeyValue`), use `array_map(IdBinding::toHex(...), $rows)`, as in `CustomFieldSetPersister`.
