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
