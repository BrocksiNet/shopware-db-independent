# Currency price cast, SEO url ids and id codec (wave 5, handoff C)

Status: done, see the open points at the end of section 5.
Section 4 was published early for handoff D.

## 1. Currency price cast (storefront and store API 500 with a currency factor)

Cause: `PriceFieldAccessorBuilder` and `CheapestPriceAccessorBuilder` multiplied `JSON_UNQUOTE(JSON_EXTRACT(...))` with the currency factor.
On PostgreSQL that extract is text and `text * numeric` has no operator (`SQLSTATE[42883]`), MySQL converts implicitly.

Fix: new `SqlDialect::jsonExtractNumber()` (numeric value, NULL for a missing path or a JSON null).
MySQL, MariaDB and SQLite return the unquoted extract as before, PostgreSQL returns `((jsonb_build_array(jsonb_path_query_first((col)::jsonb, path)) ->> 0)::numeric)`.
Both builders now take the `SqlDialect` as a constructor argument (service definitions updated) and build the extract through it.
The `::jsonb` cast is needed for `cheapest_price_accessor`, which is a text column on PostgreSQL, `jsonb_path_query_first` has no text overload.
The first version of the fix missed that and failed the cheapest price sorting, found by the request test below and fixed in a second commit.

Other numeric JSON arithmetic checked: the `+ 0.0` default path, list price and percentage accessors of `PriceFieldAccessorBuilder` use the same method now.
The custom field and other JSON accessors go through `jsonValue()` with a type, which already casts.

Tests:

- Unit tests per changed builder on MySQL and PostgreSQL (`PriceFieldAccessorBuilderTest`, `CheapestPriceAccessorBuilderTest`) and on the dialect methods (`SqlDialectTest`).
- The integration test `PriceFieldAccessorBuilderTest` builds its expectation through the dialect, green on both databases.

Request test, executed in process instead of over HTTP (the standalone php server of the benchmark source tree fails with `Key cannot be empty`, no JWT key is configured there):
a scratch copy of `bench_pg` (dropped afterwards, `bench_pg` itself was not touched, so nothing has to be reset to EUR) and the product repository of a sales channel context with the USD currency (factor 1.17085), listing criteria with sorting by `cheapestPrice` and a max aggregation on `price`.

| | EUR | USD |
|---|---|---|
| first product unit price | 2 | 2.34 |
| max price aggregation | 50 | 58.54 |

2 * 1.17085 = 2.34 and 50 * 1.17085 = 58.54.
Before the fix this query failed with `operator does not exist: text * numeric`.
Not done: a real HTTP request against a benchmark stack (home, listing, detail, store API listing) and the price comparison with MariaDB, the arithmetic is the same on both.

## 2. SEO url ids

`SeoUrlPersister` bound `id`, `sales_channel_id`, `language_id` and `foreign_key` as `ParameterType::BINARY`.
Now the ids are hex strings with `IdBinding::value()` and `IdBinding::type()`, and `findInUseCanonicalSeoUrls` selects through `IdBinding::selectText()` and normalizes the rows with `IdBinding::toHex()`.
New integration test `SeoUrlPersisterTest` writes, retargets and deletes urls for a foreign key whose 16 bytes are valid UTF-8 (the case the codec cannot recognise), and for random ids with a path takeover.
Green on PostgreSQL and MySQL.
The Seo integration directory has 68 of 68 green on MySQL, on PostgreSQL only the 4 `StoreApiSeoResolverTest` failures remain, which also fail with the old persister.

## 3. Codec decision

Measured rate: of 1,000,000 random 16 byte values 90 are valid UTF-8 without a NUL byte, about 1 in 11,000.
Such an untyped id is bound as text and rejected by the uuid column.

Switch: `SHOPWARE_PG_ID_CODEC=strict` converts only values bound as `BINARY` or `LARGE_OBJECT`, `guess` (default) is the old behaviour.
Unit tests cover both modes (`IdCodecMiddlewareTest`).

DAL integration suite on PostgreSQL, same code, both modes: guess 68 failures (37 errors, 31 failures), strict 67 (36 errors, 31 failures).
The failing sets differ only in data set names and `testNullableDatetime` (a known timing flake), no failure mentions an invalid uuid or byte sequence.

Decision: the default stays `guess`.
Strict does not remove the failure case: an untyped valid UTF-8 id is still bound as text in both modes, only typing the caller helps.
Strict mode also still falls back to binding non-UTF-8 text as binary (needed for NUL bytes), so it removes the id guess but not the content check completely.
Switching the default needs the callers of section 4 converted first (handoff D) and the three benchmark flows measured in strict mode, which was not done.

## 4. Untyped binary id callers (list for handoff D)

How the codec decides (`IdCodecMiddleware::encode()`, `IdCodecStatement::bindValue()` in `instance/src/Core/Framework/Adapter/Database/PostgreSQL/`):

- A 16 byte value bound as `ParameterType::BINARY` or `LARGE_OBJECT` is always converted to a uuid string.
- A 16 byte value bound as `ParameterType::STRING` (the Doctrine default when no type is given) is converted only when it contains a NUL byte or is not valid UTF-8.
  A 16 byte string that happens to be valid UTF-8 and has no NUL byte is passed on unchanged, and the uuid column rejects it.
- Everything else (32 character hex ids, any other length) is passed on unchanged.

So every call site below passes real 16 byte ids (`Uuid::fromHexToBytes()`, `Uuid::randomBytes()`) without a `BINARY` type, and only works because the byte string is almost never valid UTF-8.
The right fix per call site is: bind hex with `IdBinding::value()` / `values()` and the type from `IdBinding::type()` / `listType()`.

How the list was made: temporary trace in `IdCodecStatement::bindValue()` (not committed) that logs the first two application stack frames for every `STRING` typed 16 byte value that the codec converts, while the DAL integration suite (`tests/integration/Core/Framework/DataAbstractionLayer`, 801 tests) ran on PostgreSQL.
The listed line is the line that executes the statement (for `MultiInsertQueryQueue` it is the line of `->execute()`, the ids are added at the `addInsert()` calls).
Only code that the suite executes shows up, the static `MultiInsertQueryQueue` list below covers the rest.

### `MultiInsertQueryQueue::addInsert()` callers (all callers in `src`, outside migrations)

- `src/Core/Framework/Adapter/Cache/InvalidatorStorage/MySQLInvalidatorStorage.php:40`: `Uuid::randomBytes()` as `id`, no types.
- `src/Core/Framework/Migration/MigrationCollection.php:39`: no ids.
- `src/Core/Content/Product/DataAbstractionLayer/SearchKeywordUpdater.php:212` and `:230`: product, version, language and random ids as bytes, no types.
- `src/Core/Content/Product/DataAbstractionLayer/ProductCategoryDenormalizer.php:100`: already `IdBinding::value()`.
- `src/Core/Checkout/Cart/Command/CartMigrateCommand.php:150`: cart token only, no binary id.
- `src/Core/System/CustomEntity/Schema/CustomEntityPersister.php:83`: `Uuid::fromHexToBytes()` for `id`, `plugin_id`, `app_id`, no types.
- `src/Core/System/Snippet/Subscriber/CustomFieldSubscriber.php:75`: `Uuid::randomBytes()` as `id`, no types.
- `src/Core/System/SystemConfig/SystemConfigService.php:304`: `id` and `sales_channel_id` as bytes, no types.
- `src/Administration/Controller/UserConfigController.php:128`: `user_id` and `id` as bytes, no types.
- `src/Core/Framework/DataAbstractionLayer/Dbal/EntityWriteGateway.php:218` and `:238`: the payload comes from the field serializers, which bind through `IdBinding`, so these are hex on PostgreSQL.
- `src/Core/Content/Seo/SeoUrlPersister.php:177`: handoff C (typed, converted in section 2).

### Statement call sites seen in the DAL suite run

- `src/Core/Content/Category/Subscriber/CategorySubscriber.php` lines 109 (972 untyped binary ids bound in the DAL suite)
- `src/Core/Content/Flow/Indexing/FlowPayloadUpdater.php` lines 92 (105 untyped binary ids bound in the DAL suite)
- `src/Core/Content/Media/DataAbstractionLayer/MediaFolderConfigurationIndexer.php` lines 91 (26 untyped binary ids bound in the DAL suite)
- `src/Core/Content/Media/DataAbstractionLayer/MediaIndexer.php` lines 112 (74 untyped binary ids bound in the DAL suite)
- `src/Core/Content/Media/Infrastructure/Path/SqlMediaPathStorage.php` lines 34 (12 untyped binary ids bound in the DAL suite)
- `src/Core/Content/Newsletter/Subscriber/NewsletterRecipientSalutationSubscriber.php` lines 51 (1 untyped binary ids bound in the DAL suite)
- `src/Core/Content/Product/DataAbstractionLayer/RatingAverageUpdater.php` lines 55,34 (1958 untyped binary ids bound in the DAL suite)
- `src/Core/Content/Product/DataAbstractionLayer/SearchKeywordUpdater.php` lines 214,232,197 (76048 untyped binary ids bound in the DAL suite)
- `src/Core/Content/Product/DataAbstractionLayer/StatesUpdater.php` lines 99,63 (5339 untyped binary ids bound in the DAL suite)
- `src/Core/Content/Product/DataAbstractionLayer/VariantListingUpdater.php` lines 80,72,75 (4224 untyped binary ids bound in the DAL suite)
- `src/Core/Content/Product/Stock/StockStorage.php` lines 152,145,138,67 (2818 untyped binary ids bound in the DAL suite)
- `src/Core/Content/Product/Subscriber/ProductSubscriber.php` lines 212 (9 untyped binary ids bound in the DAL suite)
- `src/Core/Content/Rule/DataAbstractionLayer/RulePayloadUpdater.php` lines 87 (165 untyped binary ids bound in the DAL suite)
- `src/Core/Content/Seo/SeoUrlPersister.php` lines 434,279,319 (1077 untyped binary ids bound in the DAL suite)
- `src/Core/Content/Seo/SeoUrlUpdater.php` lines 244 (2926 untyped binary ids bound in the DAL suite)
- `src/Core/Framework/Api/EventListener/Authentication/UserCredentialsChangedSubscriber.php` lines 75 (1 untyped binary ids bound in the DAL suite)
- `src/Core/Framework/Api/OAuth/RefreshTokenRepository.php` lines 70 (90 untyped binary ids bound in the DAL suite)
- `src/Core/Framework/Api/OAuth/SymfonyBearerTokenValidator.php` lines 114 (28 untyped binary ids bound in the DAL suite)
- `src/Core/Framework/App/Feature/AppFeatureStorage.php` lines 79,168,111,179 (540 untyped binary ids bound in the DAL suite)
- `src/Core/Framework/App/Lifecycle/Handler/FlowEventLifecycleHandler.php` lines 43 (21 untyped binary ids bound in the DAL suite)
- `src/Core/Framework/App/Lifecycle/Handler/WebhookLifecycleHandler.php` lines 63 (21 untyped binary ids bound in the DAL suite)
- `src/Core/Framework/App/Lifecycle/PermissionLifecycleService.php` lines 58 (21 untyped binary ids bound in the DAL suite)
- `src/Core/Framework/App/Privileges/Privileges.php` lines 158 (24 untyped binary ids bound in the DAL suite)
- `src/Core/Framework/DataAbstractionLayer/Dbal/EntityWriteGateway.php` lines 180 (729 untyped binary ids bound in the DAL suite)
- `src/Core/Framework/Log/Monolog/DoctrineSQLHandler.php` lines 43 (115 untyped binary ids bound in the DAL suite)
- `src/Core/Framework/Log/SystemActivitySubscriber.php` lines 115 (21 untyped binary ids bound in the DAL suite)
- `src/Core/Framework/Routing/ApiRequestContextResolver.php` lines 396,357 (86 untyped binary ids bound in the DAL suite)
- `src/Core/Framework/Script/AppContextCreator.php` lines 62 (24 untyped binary ids bound in the DAL suite)
- `src/Core/Framework/Sso/UserService/UserService.php` lines 116 (30 untyped binary ids bound in the DAL suite)
- `src/Core/Framework/Test/TestCaseBase/AdminApiTestBehaviour.php` lines 193,346,184,183,182 (111 untyped binary ids bound in the DAL suite)
- `src/Core/System/CustomEntity/CustomEntityLifecycleService.php` lines 63 (24 untyped binary ids bound in the DAL suite)
- `src/Core/System/CustomField/CustomFieldSetPersister.php` lines 128 (24 untyped binary ids bound in the DAL suite)
- `src/Core/System/NumberRange/ValueGenerator/NumberRangeValueGenerator.php` lines 124 (50 untyped binary ids bound in the DAL suite)
- `src/Core/System/NumberRange/ValueGenerator/Pattern/IncrementStorage/IncrementSqlStorage.php` lines 39,78 (99 untyped binary ids bound in the DAL suite)
- `src/Core/System/Snippet/SnippetService.php` lines 384,285,231 (2182 untyped binary ids bound in the DAL suite)
- `src/Core/System/SystemConfig/SystemConfigLoader.php` lines 47 (269 untyped binary ids bound in the DAL suite)
- `src/Core/System/SystemConfig/SystemConfigService.php` lines 327,288,170 (24 untyped binary ids bound in the DAL suite)
- `src/Core/Test/Integration/Builder/Customer/CustomerBuilder.php` lines 178 (14 untyped binary ids bound in the DAL suite)
- `src/Core/Test/Integration/Traits/Promotion/ShippingMethodPricesTestBehaviour.php` lines 65 (30 untyped binary ids bound in the DAL suite)
- `src/Storefront/Theme/DatabaseSalesChannelThemeLoader.php` lines 52 (478 untyped binary ids bound in the DAL suite)
- `src/Storefront/Theme/Mail/MailThemeIdLoader.php` lines 25 (176 untyped binary ids bound in the DAL suite)

Test helpers and tests that bind untyped binary ids (17 files, all under `tests/integration/Core/Framework/DataAbstractionLayer`, `Checkout` and the like) are not listed, they follow the same pattern.

## 5. Test results

| Suite | MySQL | PostgreSQL |
|---|---|---|
| adapter unit tests (`tests/unit/Core/Framework/Adapter/Database`) | 191 OK | 191 OK |
| DAL integration (801 tests) | 1 error (see below) | 12 errors plus 26 failures = 38 |

The adapter unit tests grew from 185 to 191 with the new codec and dialect tests.
The MySQL run first showed 3 failures in the integration `PriceFieldAccessorBuilderTest` (string expectations of the quoted path), fixed and green on both databases.
`AttributeEntityIntegrationTest::testTranslations` still fails on MySQL with a foreign key violation while the working tree holds uncommitted changes of another handoff in `EntityWriteGateway` (sorting of update commands).
It was not tested in isolation, so the cause is open.
PHPStan: no file level error in the touched source files, only unmatched ignore patterns of the project configuration.
php-cs-fixer was not run over the final state.

Open points: HTTP request test of section 1, benchmark flows in strict mode, the failure above.
