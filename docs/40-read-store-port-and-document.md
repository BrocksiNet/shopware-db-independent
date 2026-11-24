# Read store port and document (wave 9, handoff K)

Handoff K of wave 9: the port every read store adapter implements, the product document, the Array adapter and the contract suite (`docs/38-read-store-plan.md`).

## Status

| Milestone | Commit in `instance/` (`poc/read-store`) | Contents |
|---|---|---|
| Port ready | `8358243fe58 feat(core): read store port ready` | Port, store criteria, field resolver, product document, Array adapter, contract suite |
| Pipeline and bridge ready | pending | Document builders, `DocumentExtender`, projector, `read-store:rebuild`, criteria bridge, corpus, `store-<id>` harness implementation |

The sections "Q2", "Q3", "Projector", "Extension point" and "Criteria corpus" are filled at the second milestone.

## Code layout

All code lives in `src/Core/Framework/ReadStore/` and is `@internal`, package `framework`.

| Path | Contents |
|---|---|
| `Port/Storage.php` | Key-value side and generations, every adapter implements it |
| `Port/FilterAware.php`, `Port/AggregationAware.php`, `Port/SearchAware.php` | Optional capabilities |
| `Port/Criteria/**` | `StoreCriteria`, filters, aggregations, `Sorting`, `SearchTerm` |
| `Port/Result/**` | `StoreResult`, `TermsResult`, `MetricResult`, `StatsResult` |
| `Port/Schema/**` | `Field` attribute, `FieldType`, `FieldScope`, `DocumentSchema`, `FieldResolver`, `ResolvedField` |
| `Port/StoreContext.php`, `Port/Total.php`, `Port/NotSupportedByEngine.php` | Context, total mode, the fallback signal |
| `Document/ProductDocument.php` | The document layout, one class with typed public properties and `#[Field]` attributes |
| `Evaluation/QueryEvaluator.php` | In-memory evaluation of store criteria, used by the Array adapter and usable as reference by others |
| `Adapter/ArrayStore/ArrayStorage.php` | Reference adapter, JSON files per generation in `var/read-store` |
| `ReadStoreException.php` | Domain exception, `NotSupportedByEngine` extends it |
| `DependencyInjection/readstore.php` | Services of handoff K, loaded by the glob in `Framework.php` |

Tests live in `tests/unit/Core/Framework/ReadStore/`.

## Port API

### Storage

`Storage` is the key-value side and is mandatory.

| Method | Meaning |
|---|---|
| `setup(string $generation)` | Creates an empty generation that is not live yet, creates the store (tables, indices, collections) if missing |
| `swap(string $generation)` | Makes the generation live and drops the previously live one |
| `liveGeneration(): ?string` | The live generation, `null` before the first swap |
| `store(list<array> $documents, ?string $generation = null)` | Upsert by `id`; without a generation it writes to the live and any pending generation |
| `remove(list<string> $ids)` | Deletes from the live and any pending generation |
| `get(string $id): ?array` | One document of the live generation |
| `mget(list<string> $ids): array` | Documents keyed by id, in the order of `$ids`, missing ids left out |
| `clear()` | Removes all documents of the live generation |
| `destroy()` | Drops every generation and the store itself |

Generations make the blue/green rebuild possible.
While a rebuild fills a pending generation, the projector keeps writing with `store($documents)` without a generation, so both the live and the pending generation stay current and nothing is lost at the swap.
Every adapter persists which generation is live (SQL meta table, OpenSearch alias, Valkey pointer key, a file for Array), so a second PHP process sees the swap.
The contract test `testWritesDuringARebuildReachTheLiveAndThePendingGeneration` and the Array test `testPersistedGenerationsAreSharedBetweenInstances` check both.

Documents are plain arrays at the port, not objects.
Adapters store and return them as they are; `ProductDocument::fromArray()` and `toArray()` exist for builders and tests.

### Capabilities

| Interface | Method | Answers |
|---|---|---|
| `FilterAware` | `filter(StoreCriteria, StoreContext): StoreResult` | Filters, post filters, sortings, paging, collapse by `groupField`, total, aggregations (if `AggregationAware`) |
| `AggregationAware` | `aggregate(StoreCriteria, StoreContext): array<string, AggregationResult>` | Aggregations only, keyed by name |
| `SearchAware` | `search(StoreCriteria, StoreContext): StoreResult` | Like `filter()` plus a `SearchTerm`, hits carry a score, sorting by `Sorting::SCORE` |

An adapter implements what its engine can do.
Anything it cannot answer (a field, a filter, an aggregation, an option, a rounding mode) throws `NotSupportedByEngine`.
The caller then runs the whole query on the DAL; there is no partial answer.

### Store criteria

`StoreCriteria` is a mutable value object built by the criteria bridge, not by application code.

| Property | Type | Notes |
|---|---|---|
| `ids` | `list<string>` | Restricts to ids, like `Criteria::$ids` |
| `filters` | `list<Filter>` | Hits and aggregations |
| `postFilters` | `list<Filter>` | Hits only |
| `sortings` | `list<Sorting>` | `Sorting(field, ASC|DESC)`, `Sorting::SCORE = '_score'` |
| `groupField` | `?string` | Collapse field, `displayGroup` for listings |
| `limit`, `offset` | `?int`, `int` | Paging, applied after the collapse |
| `total` | `Total` | `NONE` or `EXACT`; how the bridge maps `TOTAL_COUNT_MODE_NEXT_PAGES` is decided at the second milestone |
| `aggregations` | `list<Aggregation>` | Each aggregation may carry its own filters |
| `search` | `?SearchTerm` | Only valid for `search()`; `filter()` rejects it |

Filters are `Equals`, `EqualsAny`, `Contains`, `Prefix`, `Range(gte, lte, gt, lt)`, `Multi(AND|OR)` and `Not(AND|OR)`.
Aggregations are `Terms(limit)`, `Min`, `Max`, `Avg`, `Sum`, `Count` (distinct values) and `Stats`.

`SearchTerm(original, scoredKeywords, tokenKeywords, originalScore, andLogic)` carries what the DAL `ProductSearchBuilder` already computed from `product_keyword_dictionary`.
The read store does not tokenize or interpret the term itself, so every engine sees the same keywords as the DAL.

### Store context

`StoreContext` holds what a query needs from the `SalesChannelContext`: language id, sales channel id, currency id, rule ids, the tax state (gross or net) and both roundings (context and currency).
`StoreContext::fromSalesChannelContext()` builds it.

### Results

`StoreResult(documents, total, aggregations, scores)` with `ids()`.
`TermsResult(name, buckets)`, buckets are `{key, count}` with a `null` key for documents without a value, `counts()` leaves that bucket out.
`MetricResult(name, value)` and `StatsResult(name, min, max, avg, sum)`.

## Field resolution

The criteria use logical field names (`name`, `price`, `cheapestPrice`, `categoryTree`).
`FieldResolver::resolve($field, $context)` maps them to the paths in the document for the context.
Every adapter uses it, so the mapping lives in one place and an adapter only translates paths into its query language.

| Logical field | Paths | Rule |
|---|---|---|
| `productNumber`, `categoryTree`, `active`, ... | itself | `FieldScope::NONE` |
| `name`, `description`, `searchKeywords`, ... | `name.<languageId>` | `FieldScope::LANGUAGE` |
| `visibilities` | `visibilities.<salesChannelId>` | `FieldScope::SALES_CHANNEL` |
| `price`, `price.gross`, `price.net` | `priceGross.<currencyId>` or `priceNet.<currencyId>` | `price` follows the tax state of the context |
| `cheapestPrice[.listPrice\|.percentage][.gross\|.net]` | `cheapestPrice.<ruleId>.<currencyId>...` per context rule, then `cheapestPrice.default.<currencyId>...` | First non-null wins (`COALESCE`), like `CheapestPriceAccessorBuilder` |
| `customFields.<name>` | `customFields.<languageId>.<name>` | `FieldType::ANY` |
| `extensions.<name>...` | itself | `FieldType::ANY`, plugin data |

Everything else throws `NotSupportedByEngine::field()`, notably nested association fields such as `manufacturer.name` and payload-only fields (`#[Field(..., queryable: false)]`).
The criteria bridge maps the association fields the product routes use to the flat fields (`manufacturer.id` to `manufacturerId`, `properties.id` to `propertyIds`).

`price` and `cheapestPrice` are rounded at build time with the item rounding of each currency, because the DAL accessor builders (`PriceFieldAccessorBuilder`, `CheapestPriceAccessorBuilder`) round both with the context rounding in SQL.
A context whose rounding differs from the currency rounding (`StoreContext::roundsLikeCurrency()` is false) gets `NotSupportedByEngine` for both, so the DAL answers it.

## Semantics every adapter keeps

These rules follow the DAL on MySQL and are checked by the contract suite.

- Hits match `filters` and `postFilters`, aggregations match `filters` only and ignore the collapse (`EntityAggregator` resets both).
- With a `groupField`, hits collapse to one document per distinct value, `null` is one group of its own.
  Groups are ordered by the minimum (ascending) or maximum (descending) of each sort field over the group's matching documents, `cheapestPrice` always by the minimum, as the DAL does.
  The representative is the group's first document in the sort order, ties by id; `total` counts groups.
- String comparisons of `Equals`, `EqualsAny`, `Contains` and `Prefix` are case-insensitive (`FieldType::STRING`, `TEXT`, `ANY`), ids compare exactly (`FieldType::ID`, `LIST`).
- `Equals` and `EqualsAny` are null-safe: `null` matches `null`, a missing value does not match a value, also under `Not`.
- `Contains`, `Prefix`, `Range` and filters on a missing list are unknown for a missing value, so `Not` of them does not match either (three-valued logic, as SQL).
- `Contains` is a substring match on the resolved field, not a word search.
- String comparisons fold accents like `utf8mb4_unicode_ci` (`Café` matches `cafe`); the Array adapter decomposes to NFD and drops the combining marks.
  Known gap: MySQL 8.4.13 also expands `ß` to `ss` for `=` (`'Straße' = 'strasse'` is 1) but not for `LIKE` (`'Straße' LIKE '%strasse%'` is 0), checked in `instance-mysql-1`.
  The fold has no expansions, so `Contains` matches MySQL and `Equals` on such a string does not.
- A filter on a `LIST` field matches when any element matches.
- Sorting puts `null` first for ascending and last for descending, as MySQL does.
- The Array adapter sorts strings with an ICU collator at primary strength, which is close to, but not the same as, the UCA 4.0.0 weights of `utf8mb4_unicode_ci`.
- Search scores are best effort; the contract checks matches and ranking order, not absolute scores.

## Product document

One document per product row (parents and variants), `ProductDocument::SCHEMA_VERSION = 1`.
The layout is option (a) of Q2: all languages, currencies, rule prices and sales channel visibilities in one document, the context picks its keys at query time.
Q2 measures it against option (b), one document per sales channel and language, at the second milestone.

Each property carries a `#[Field(FieldType, FieldScope, queryable)]` attribute.
`DocumentSchema::fields(ProductDocument::class)` reads them once, and adapters derive their mapping or DDL from it.

| `FieldType` | Meaning |
|---|---|
| `ID` | Lower case hex, compared exactly |
| `STRING`, `TEXT` | Case-insensitive, `TEXT` for long values |
| `INT`, `FLOAT`, `BOOL`, `DATETIME` | Scalars, date times as `Y-m-d H:i:s.v` UTC strings |
| `LIST` | List of ids, matches when any element matches |
| `OBJECT`, `OBJECT_LIST` | Payload, not queryable |
| `ANY` | Custom fields and extensions, type not known to the core schema |

The types are taken from the prototype (`string`, `text`, `int`, `float`, `bool`, `datetime`, `list`, `object`, `object_list`).
`ID` was split from `STRING` because ids compare exactly and strings do not, and `ANY` was added for data the core does not know.

### Build-time rules

All values are resolved at build time, so query time never needs a fallback, except for the rule ids of `cheapestPrice`, which depend on the customer.

- Variants are complete: every inherited field holds the parent's value when the variant has none, to-many associations included (`prices`, `categoryIds`, `properties`).
- A language map has an entry for every language of the shop, resolved with that language's fallback chain and parent inheritance.
- `priceGross` and `priceNet` per currency: the own price of the currency, else the own default currency price times the currency factor, else the same from the parent, rounded with the item rounding of the currency (as `PriceFieldAccessorBuilder` does with `IFNULL(COALESCE(...), COALESCE(...))`).
- `cheapestPrice` per rule key (`default` or rule id) and currency, from the own `cheapest_price_accessor`, the parent's when the own is empty (the field is inherited), rounded with the item rounding of each currency like `CheapestPriceAccessorBuilder`.
  `CheapestPriceUpdater` writes an accessor for every active simple product and every active variant (`IFNULL(product.active, parent.active) = 1`), none for a parent with variants; on `orm_spike` (MySQL) 550 of the 3,400 products without a parent have none, the 400 parents and 150 inactive simple products.
  `percentage` is stored as `100 - percentage`, the ratio the accessor builder returns.
- `visibilities` per sales channel id: the visibility value (10, 20, 30), the parent's when the variant has none.
- `searchKeywords` per language: `{keyword: ranking}` from `product_search_keyword`.
- `extensions`: plugin data added by `DocumentExtender`s, keyed by the extender's name.

### Example

Variant `SW-P.1` of the contract fixtures: two languages (English, German), two currencies (EUR, USD with factor 1.1), two sales channels and one rule price.

```json
{
  "id": "a1000000000000000000000000000001",
  "parentId": "a0000000000000000000000000000000",
  "schemaVersion": 1,
  "productNumber": "SW-P.1",
  "displayGroup": "9a000000000000000000000000000000",
  "variantListingConfig": null,
  "childCount": 0,
  "active": true,
  "available": true,
  "stock": 2,
  "availableStock": 2,
  "ratingAverage": 4.0,
  "shippingFree": false,
  "sales": 0,
  "name": {
    "2fbb5fe2e29a4d70aa5854ce7ce3e20b": "Cherry Sneaker",
    "0de0de0de0de0de0de0de0de0de0de00": "Kirsch Turnschuh"
  },
  "customFields": {
    "2fbb5fe2e29a4d70aa5854ce7ce3e20b": {"swag_color": null},
    "0de0de0de0de0de0de0de0de0de0de00": {"swag_color": null}
  },
  "manufacturerId": "aa000000000000000000000000000001",
  "manufacturer": {
    "id": "aa000000000000000000000000000001",
    "name": {
      "2fbb5fe2e29a4d70aa5854ce7ce3e20b": "M aa000000000000000000000000000001",
      "0de0de0de0de0de0de0de0de0de0de00": "M aa000000000000000000000000000001"
    }
  },
  "price": [
    {"currencyId": "b7d2554b0ce847cd82f3ac9bd1c0dfca", "gross": 40.0, "net": 33.61, "linked": true}
  ],
  "prices": [],
  "priceGross": {
    "b7d2554b0ce847cd82f3ac9bd1c0dfca": 40.0,
    "05d05d05d05d05d05d05d05d05d05d00": 44.0
  },
  "priceNet": {
    "b7d2554b0ce847cd82f3ac9bd1c0dfca": 33.61,
    "05d05d05d05d05d05d05d05d05d05d00": 36.97
  },
  "cheapestPrice": {
    "default": {
      "b7d2554b0ce847cd82f3ac9bd1c0dfca": {"gross": 40.0, "net": 33.61},
      "05d05d05d05d05d05d05d05d05d05d00": {"gross": 44.0, "net": 36.97}
    },
    "ae1ae1ae1ae1ae1ae1ae1ae1ae1ae100": {
      "b7d2554b0ce847cd82f3ac9bd1c0dfca": {"gross": 35.0, "net": 29.41},
      "05d05d05d05d05d05d05d05d05d05d00": {"gross": 38.5, "net": 32.35}
    }
  },
  "visibilities": {
    "5c15c15c15c15c15c15c15c15c15c100": 30,
    "5c25c25c25c25c25c25c25c25c25c200": 30
  },
  "categoryIds": ["ca7000000000000000000000000000a2"],
  "categoryTree": ["ca7000000000000000000000000000a0", "ca7000000000000000000000000000a2"],
  "streamIds": [],
  "tagIds": [],
  "propertyIds": ["ed000000000000000000000000000001"],
  "optionIds": ["ed000000000000000000000000000001"],
  "searchKeywords": {
    "2fbb5fe2e29a4d70aa5854ce7ce3e20b": {"cherry": 500.0, "sneaker": 300.0},
    "0de0de0de0de0de0de0de0de0de0de00": {"kirsch": 500.0, "turnschuh": 300.0}
  },
  "extensions": []
}
```

The example leaves out the fields that are `null` or empty in the fixture (`isCloseout`, `minPurchase`, `ean`, `releaseDate`, `description`, `metaTitle`, `tax`, `unit`, `cover`, `media`, `properties`, `options`, `states`, ...).
It was dumped with `ContractFixtures::documents()` in `instance-web-1`; the real layout always has every field.

## The prototype `shopwareArchive/storage`

https://github.com/shopwareArchive/storage at `6d53fcf2d45`, 2024-03-24, cloned to `/tmp/wave9-research/storage-k/` and read, not run.

Taken:

- The split into a mandatory key-value `Storage` and optional `FilterAware`, `AggregationAware` and `SearchAware` capabilities.
- `NotSupportedByEngine` as the signal that an engine cannot answer.
- The field types and the idea of a schema read from the document class.
- `setup`, `store`, `remove`, `get`, `mget`, `clear` and `destroy` on the storage.
- `Total` as an explicit option.

Changed or dropped:

- Generations (`setup($generation)`, `swap()`, `liveGeneration()`) are new; the prototype had `setup()` only and no blue/green rebuild.
- `StorageContext` held a list of languages only; `StoreContext` adds sales channel, currency, rules, tax state and rounding, because the product queries depend on them.
- The prototype translated documents at read time (`Document/Translator.php`) with a language fallback list; the read store resolves fallbacks at build time and reads one key.
- The prototype's filter types (`Any`, `Neither`, `Gt`, `Gte`, `Lt`, `Lte`, `Suffix`) and operators (`Nand`, `Nor`) were reduced to the filters the DAL criteria use: `EqualsAny`, `Range`, `Not(AND|OR)`; `Suffix` is dropped.
- `postFilters`, `groupField` (collapse) and per-aggregation filters are new; the prototype had none of them and the listing needs all three.
- The prototype's search (`Search`, `Group`, `Boost`, `Query`) let each engine interpret the term; `SearchTerm` carries the DAL's keywords instead, so all engines match the same products.
- Typed document objects (`Document`, `Documents`, `Collection`, `Hydrator`) were dropped at the port; documents are arrays, `ProductDocument` is the layout and a helper.
- The per-engine packages (MySQL, MongoDB, OpenSearch, Meilisearch, DynamoDB, Redis) were not taken; handoffs S, O and M write new adapters against this port.

## Contract suite

`tests/unit/Core/Framework/ReadStore/Contract/` holds the contract every adapter test runs.

| File | Role |
|---|---|
| `ContractFixtures.php` | Ids, the context helper and nine documents: S1 to S4 (simple products), P (parent) and V1 to V3 (variants of group `G_P`) |
| `ContractTestCase.php` | Abstract base, `createStorage()`; set up runs `destroy`, `setup('g1')`, `swap('g1')` and stores the fixtures; tear down runs `destroy` |
| `StorageContract.php` | 8 tests: round trip, `mget` order, upsert, remove, clear, swap, writes during a rebuild |
| `FilterContract.php` | 24 tests: case and accent folding, prefix, list fields, visibility, price per currency and tax state, `cheapestPrice` rules, rounding fallback, null-safe equals, three-valued `Not`, sort, paging, total, post filters, collapse |
| `AggregationContract.php` | 10 tests: terms with null bucket and limit, metrics, stats, currency, distinct count, empty match, post filters and collapse ignored |
| `SearchContract.php` | 7 tests: OR and AND logic, accent folding, ranking order, filters with paging and total, no match |

The contracts are traits with `@phpstan-require-extends ContractTestCase`, not abstract classes.
An adapter test extends `ContractTestCase` and uses the traits of the capabilities it implements, so one test class covers an adapter with any mix of capabilities.
`ContractTestCase::attempt()` turns `NotSupportedByEngine` into an incomplete test, so a gap shows in the test output instead of failing the suite.

The Array adapter uses all four traits: 51 tests, 201 assertions, all passing (`tests/unit/Core/Framework/ReadStore`, run in `instance-web-1`).
PHPStan reports no errors on the handoff K paths, `php-cs-fixer` is applied.

### Adding an adapter

1. Implement `Storage` and the capabilities the engine supports under `Adapter/<Name>/`, use `FieldResolver` for every field.
2. Register it in your own `DependencyInjection/<handoff>.php` as `read_store.storage.<id>` with the tag `read_store.storage` and the attribute `key` (the store id, `sql-mysql`, `opensearch`, ...).
3. Add a test under `tests/unit/Core/Framework/ReadStore/Adapter/<Name>/` that extends `ContractTestCase` and uses the contract traits of the implemented capabilities.
4. Throw `NotSupportedByEngine` for anything the engine cannot answer, never return an approximate result.

## Q2: document granularity

Filled at the second milestone.

## Q3: document builders

Filled at the second milestone.

## Projector

Filled at the second milestone.

## Extension point

Filled at the second milestone.

## Criteria corpus

Filled at the second milestone.
