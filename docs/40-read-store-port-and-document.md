# Read store port and document (wave 9, handoff K)

Handoff K of wave 9: the port every read store adapter implements, the product document, the Array adapter and the contract suite (`docs/38-read-store-plan.md`).

## Status

| Milestone | Commit in `instance/` (`poc/read-store`) | Contents |
|---|---|---|
| Port ready | `8358243fe58 feat(core): read store port ready` | Port, store criteria, field resolver, product document, Array adapter, contract suite |
| Pipeline and bridge ready | `78b72794c37 feat(core): read store pipeline and bridge ready` (`69cbebb016f` registers `CorpusCommand` in `bench.php`) | Document builders (`sql`, `dal`), `DocumentExtender`, projector (`sync`, `queue`), `read-store:rebuild`, criteria bridge, corpus, `StoreImplementation` harness |

All sections below are verified against `orm_spike`, `read_store_large` and `rs_k_corpus`.

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

Measured on 2026-11-24 under `/tmp/wave9-timing.lock`, other lanes stopped: yes (47 containers stopped), host load average 10.05 to 9.78, MySQL 8.4 write model (`read_store_large`: 150,000 products, 2 languages, 2 sales channels, 9 currencies; `orm_spike`: 5,000 products for the Array read comparison).

Two layouts compared:

- **Option (a)**: one document per product holding all languages, all currency and rule prices, and sales channel visibilities; the query picks the context keys at read time.
- **Option (b)**: one document per `(product, salesChannel, language)`, pre-resolved to scalar translated fields and that sales channel's visibility.
  Measured both over all `(salesChannel, language)` combinations (4× documents) and over visible products only (on `read_store_large` one sales channel has visibility rows for 135,000 products, so 270,000 documents across 2 languages).

### Document size on `read_store_large` (150,000 products)

| Layout | Documents | Median JSON (B) | p95 JSON (B) | Total JSON (MiB) | Factor vs (a) |
|---|---|---|---|---|---|
| Option (a): 1 per product | 150,000 | 4,488 | 5,591 | 691.51 | 1.00× |
| Option (b): visible only (`SC × lang`) | 270,000 | 3,693 | 4,614 | 1,008.30 | 1.46× |
| Option (b): all (`SC × lang`) | 600,000 | 3,695 | 4,792 | 2,265.95 | 3.28× |

Extra projection CPU time to fan out option (a) into option (b) for 150,000 products: +5.80 s in PHP, before the additional 1.8× to 4× store writes.

### Read cost on Array (`orm_spike`, 5,000 products, 5 warm-up, 50 iterations)

Both options run the identical JSON decode / scan / ICU sort loop, differing only in reading a language/sales-channel map key vs a scalar field (and 5,000 vs 4,500 visible docs for R2).

| Measure | Option (a) | Option (b) | Difference |
|---|---|---|---|
| Variant document JSON size (`S2`) | 6,420 B | 5,328 B | -17.0 % |
| R1 JSON decode + extract (median / p95) | 0.0229 / 0.0241 ms | 0.0198 / 0.0208 ms | -3.1 µs |
| R2 in-memory scan + ICU sort (median / p95) | 1.9851 / 3.9221 ms | 0.9771 / 1.0321 ms | -1.01 ms |

### Decision

**Option (a) (one document per product) is chosen.**
Most of a Shopware product document is not translated text — it is currency/rule prices (9 currencies), `categoryTree`, `optionIds`, `propertyIds`, media, cover and scalars.
Splitting per `(salesChannel, language)` shrinks an individual document by only ~18 % while multiplying document count, total storage and write amplification linearly by `salesChannels × languages` (already 1.46× to 3.28× with 2×2; a 5-language, 3-storefront shop would store and rewrite up to 15× as many documents on every product edit).
Single-document decode saves ~3 µs, which is negligible against network and query round-trip times.
Option (a) also matches Shopware's existing OpenSearch ADR (`2023-04-11-new-language-inheritance-mechanism-for-opensearch`).
Option (b) remains a straightforward projection on top of option (a) if a key-value cache ever wants per-locale pre-rendered payloads.

## Q3: document builders

Two builders implement `Builder/DocumentBuilder` (`build(list<string> $ids): array<string, array<string, mixed>>`, `reset()`, `key()`):

- **`SqlDocumentBuilder`** (`sql`, default): reads raw rows from `product` (own + parent), `product_translation`, `product_price`, `product_visibility`, `product_media`, `product_property`, `product_option`, `product_search_keyword`, and referenced lookup tables (`product_manufacturer`, `tax`, `unit`, `delivery_time`, `property_group_option`, `media`) using portable `IdBinding` SQL; resolves inheritance, language fallback chains, currency/rule prices (`PriceCalculator`) and normalization (`Normalizer`) in PHP.
- **`DalDocumentBuilder`** (`dal`): loads products via `product.repository` once per language with storefront associations (so DAL inheritance and entity extensions come along) plus one SQL read for `cheapest_price_accessor`.

### Build throughput on `read_store_large` (150,000 products, batch 500)

Same stopped-lanes block as Q2 (2026-11-24, other lanes stopped: yes, load average 10.05 to 9.78, MySQL 8.4, separate PHP processes for independent peak memory).
Statement counts per 500-product batch were measured separately on `orm_spike` via MySQL `session_status.Questions`.

| Builder | Documents | Time (s) | Docs / s | Peak memory (MiB) | SQL statements / 500-product batch (cold / warm scope) |
|---|---|---|---|---|---|
| `SqlDocumentBuilder` (`sql`) | 150,000 | 28.32 | 5,296.5 | 74.0 | 21 / 19 |
| `DalDocumentBuilder` (`dal`) | 150,000 | 132.55 | 1,131.6 | 146.5 | 15 / 13 |

- **Output equality**: strict `===` equality across all 5,000 documents on `orm_spike` (0 diffs), and identical SHA-256 (`e589a4d228ea58584d25d26fab06fa38e799887a80b5e175771833441dcef4b8`) over the first 1,000 documents on `read_store_large`.
- **Why SQL is 4.68× faster despite more statements**: `DalDocumentBuilder` issues fewer SQL queries per batch (13 vs 19) because the DAL joins translations and associations per query, but it runs a full DAL `EntityRepository::search()` per language (2× entity hydration, struct instantiation, Criteria compilation and events), which dominates PHP CPU time and doubles peak memory.
- **Recommendation**: `SqlDocumentBuilder` for full rebuilds and core fields; plugins attach custom data via `DocumentExtender` (which runs on both builders with batched IDs) rather than forcing full entity hydration for every product.

## Projector

Lives in `src/Core/Framework/ReadStore/Projector/`.

### Signals (`ReadStoreProjectorSubscriber`)

| Event | Action | Notes |
|---|---|---|
| `ProductIndexerEvent` | `projector->schedule($event->getIds())` | Fires after `ProductIndexer` updates derived columns (`cheapest_price`, `category_tree`, `searchKeywords`, ...). `ProductIndexer::update()` already includes child variant ids when a parent is written. |
| `ProductStockAlteredEvent` | `projector->schedule($event->getIds())` | Order stock changes bypass `ProductIndexer`. |
| `ProductEvents::PRODUCT_DELETED_EVENT` | `projector->remove($ids)` | Immediate delete from live and pending generations; no DB read needed. |

Same signal surface as `src/Elasticsearch/Product/ProductUpdater.php`. Changes to referenced entities alone (manufacturer rename, tax rate change, category rename) or raw SQL writes that bypass the DAL emit none of these events (investigated and probed in handoff C, `docs/45-read-store-consistency.md`).

### Modes and configuration

Configured via env parameters in `DependencyInjection/readstore.php`:

- `READ_STORE_PROJECTOR_STORES`: comma-separated store keys (e.g. `sql-mysql,opensearch`); empty disables projection.
- `READ_STORE_PROJECTOR_MODE`:
  - `sync` (default): calls `ReadStoreProjector::project($ids)` in-request right after the indexer event.
  - `queue`: dispatches one `ProjectProductsMessage($ids)` (`AsyncMessageInterface`, `DeduplicatableMessageInterface` with SHA hash of sorted ids) onto `messenger.default_bus`, consumed by `ProjectProductsHandler`. Note: Shopware core ships no deduplication middleware for the Doctrine transport, so duplicate messages execute idempotently.
- `READ_STORE_PROJECTOR_BUILDER`: `sql` (default) or `dal`.

### Blue/green rebuild (`Rebuilder`, `RebuildCommand`)

`bin/console read-store:rebuild --store=<key> [--builder=sql|dal] [--batch-size=500]` generates a UTC microsecond generation name `g<YmdHisu>`, calls `setup($generation)`, streams `ProductIds::batches()` into `store($docs, $generation)`, and finishes with `swap($generation)` (which atomically flips the live pointer and drops the previous generation).
Concurrent projector writes call `store($docs)` without a generation argument, so adapters write them to both live and pending generations.

## Extension point

`Builder/DocumentExtender` (tagged `read_store.document_extender`) lets plugins add data to product documents during both builds and projector updates:

```php
interface DocumentExtender
{
    public function name(): string;

    /** @param array<string, array<string, mixed>> $documents */
    public function extend(array $documents): array;
}
```

`DocumentExtenders::apply()` runs once per batch on both `SqlDocumentBuilder` and `DalDocumentBuilder`, storing each extender's return value under `extensions.<name>`.
`FieldResolver` resolves `extensions.<name>.<key>` as `FieldType::ANY`, so stores that support `ANY` filters can query plugin fields directly (tested in `tests/unit/Core/Framework/ReadStore/Builder/DocumentExtendersTest.php`).
Data loaded from external plugin tables is re-projected when the product changes; independent plugin-table edits must call `ReadStoreProjector::project($affectedProductIds)`.

## Criteria bridge, harness and criteria corpus

### Criteria bridge (`Bridge/CriteriaBridge`)

Translates DAL `Criteria` passed to `sales_channel.product.repository` into `StoreCriteria` + `StoreContext`:

- Adds implicit `ProductAvailableFilter(VISIBILITY_LINK)` when absent (matching `SalesChannelProductDefinition::processCriteria()`).
- Maps association filter paths used by storefront routes to flat document lists (`categoriesRo.id` -> `categoryTree`, `categories.id` -> `categoryIds`, `streams.id` -> `streamIds`, `tags.id` -> `tagIds`, `properties.id` -> `propertyIds`, `options.id` -> `optionIds`, `manufacturer.id` -> `manufacturerId`, `tax.id` -> `taxId`, `unit.id` -> `unitId`, `deliveryTime.id` -> `deliveryTimeId`, `cover.id` -> `coverId`).
- Converts `ProductSearchBuilder` keyword filters and `ScoreQuery` instances into `SearchTerm`.
- Converts `EntityAggregation` into `Terms` while tracking the entity name in `BridgedCriteria::$entityAggregations`.
- Caps `StoreContext::$ruleIds` at `shopware.dal.max_rule_prices` (like `CheapestPriceAccessorBuilder`).
- Throws `NotSupportedByEngine` (`engine = "bridge"`) for: raw `Criteria::getTerm()` without `ProductSearchBuilder` keyword queries, `Criteria::TOTAL_COUNT_MODE_NEXT_PAGES`, multiple group fields, `CountSorting`, natural sorting, `TermsAggregation` with sorting or nested aggregations, non-keyword `ScoreQuery`, composite ids, other sales channels in `ProductAvailableFilter`, and nested/payload fields (e.g. `manufacturer.name`).

### Harness (`Bench/StoreImplementation`) and `--verify`

`readstore.php` registers `store-<key>` (`orm_spike.implementation`) for every store (`array`, `sql-mysql`, `sql-mariadb`, `sql-pgsql`, `sql-sqlite`, `opensearch`, `mongodb`, `valkey`, `opensearch-valkey`).
S2 (R1) and R4 use `Storage::get()` / `Storage::mget()` directly with the `ProductAvailableFilter` check in PHP so key-value-only stores (`valkey`) answer R1 and R4 and all other stores use their primary-key path.
S1, S3, R3b and S5 go through `CriteriaBridge` into `FilterAware` / `SearchAware`.

`store-array --verify` on `orm_spike`:

- **MySQL 8.4**: S1 OK, S2 OK, S3 OK, R4 OK, S5 OK. R3b hits and total match; manufacturer aggregation differs by the known DAL keyword-row over-count (71 vs DAL's 73 on Maker 17, finding 36 in `docs/core-findings.md`).
- **PostgreSQL 18**: S1 OK, S2 OK, S3 OK, R4 OK, S5 OK.

### Criteria corpus (`Bench/criteria-corpus.json`, `read-store:bench:corpus`)

35 entries capturing real DAL `Criteria` produced by `ProductListingRoute` (20 entries: default, sort orders, page 2, single/multiple manufacturers, single/same-group/cross-group properties, min/max/range price, rating, shipping-free, combined filters, `no-aggregations`, `only-aggregations`, `reduce-aggregations`), `ProductSearchRoute` (5 entries: default, score, name-asc, manufacturer, price-range) and `RequestCriteriaBuilder` Store API JSON criteria (10 entries: stock range, OR contains, NOT manufacturer, main products, prefix name, mixed aggregations with filter aggregation, post-filter, options, raw `term`, nested `manufacturer.name`).

During corpus verification against MySQL DAL, two semantics of `QueryEvaluator` were aligned with core:

1. **Keyword search score**: when there is a single keyword filter (OR-logic, or AND-logic with one token), the DAL scores only the matching rows of the context language; with two or more token filters it scores all keyword rows across languages.
2. **Scored collapse (`EntitySearcher::buildScoreRankedQuery()`)**: with a search term, the group representative is the highest-scoring hit (ties by lowest id) and groups are ordered by the representative's sort keys rather than `MIN()`/`MAX()` across the group.
3. **`Terms` limit tie-breaking**: changed to highest count first, ties by ascending key (matching `CorpusCommand`'s deterministic cut of the DAL's unordered `GROUP BY ... LIMIT n`).

`read-store:bench:corpus --impl=store-array` results:

| Database | Match | `dal-defect` | Fallback | Diff | Skipped |
|---|---|---|---|---|---|
| `rs_k_corpus` (5,000 products with properties, ratings, shipping-free) | 28 | 5 | 2 | 0 | 0 |
| `orm_spike` (5,000 products, no `product_property` rows) | 22 | 5 | 2 | 0 | 6 |

- The 5 `dal-defect` entries are the 5 `ProductSearchRoute` entries where the DAL's `options` and `properties` aggregations over-count products matching multiple keyword rows (finding 36), while `store-array` equals the ground truth aggregation over the distinct hit ids.
- The 2 `fallback` entries are intentional bridge fallbacks: `criteria-term` (raw `Criteria::setTerm` without `ProductSearchBuilder`) and `criteria-association-field` (`manufacturer.name`, payload only).
- **0 diffs** across all 35 entries.

Unit tests: `tests/unit/Core/Framework/ReadStore/` (including new `Bridge/CriteriaBridgeTest`, `Builder/DocumentExtendersTest`, `Projector/ReadStoreProjectorTest`): 451 tests across all adapters, 1,684 assertions, 0 failures, 2 expected incomplete (OpenSearch collapse descending by cheapestPrice). PHPStan clean on all handoff K files; `php-cs-fixer` applied.
