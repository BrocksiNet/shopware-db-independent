# Read store: research and PoC plan (wave 9)

State: 2026-11-23, research before wave 9.
Question: can Shopware serve its hot reads from a read-optimized store that is fed from the DAL, with interchangeable engines (MySQL/MariaDB/PostgreSQL/SQLite JSON, OpenSearch, MongoDB, Valkey), while the SQL database stays the write model and the source of truth?
Goal, in the words of the archived prototype `shopware/storage` (README): "provide a read-optimized system for better scalability and performance and support different kinds of document storage engines like opensearch, mongodb, etc."

This doc holds the research and the plan.
The wave 9 PoC (docs 39 to 45) builds and measures it, and the conclusion section at the end is written by wave 9 F.

## Why this wave

Feedback on the experiment's results raised three points that wave 8 did not answer:

1. The DAL ties the database structure, the entity model, business data access and the public API contract together.
   A storage change becomes an API change.
   Wave 8 kept the DAL as the write and admin API (doc 29), but it did not ask whether the hot storefront reads need the DAL entity shape at all.
2. Shopware already had a prototype for a separate storage layer (`shopwareArchive/storage`, 2023 to 2024, archived).
   Nobody measured it against Shopware's real read cases.
3. The experiment's database work is about the write model.
   A read store could take load off the write database whatever engine that is, which matters more for scalability than PostgreSQL vs MySQL.

The goal of the wave is the same as for wave 8: find out with a measured PoC slice, not opinions.

## What Shopware has today (verified in `instance/`, trunk)

Read paths:

- Storefront product listing, search, suggest and detail go through the DAL.
  With OpenSearch enabled, `ElasticsearchEntitySearcher` decorates `EntitySearcherInterface`, but only for criteria with `Criteria::STATE_ELASTICSEARCH_AWARE` (`ElasticsearchHelper::allowSearch`), which `ProductListingLoader`, `ProductSearchRoute`, the suggest route, the product stream code, and `ProductDetailRoute::findBestVariantByTerm()` set.
- OpenSearch returns ids, a total and aggregations only.
  `EntityRepository::_search()` then calls `$criteria->cloneForRead($ids)` and reads the full entities from SQL (`src/Core/Framework/DataAbstractionLayer/EntityRepository.php:289`).
  So every listing with OpenSearch is still a full DAL read with its joins on the write database: OpenSearch offloads filtering and aggregations, not hydration.
- On top of entity hydration, the storefront routes run extra SQL around the search:
  `ProductListingLoader` adds `FieldGrouping('displayGroup')` (variant collapsing), computes aggregations without `postFilters`, runs `loadPreviews()` (raw SQL on `product.variant_listing_config` plus a second `searchIds()`), and then hydrates via `resolveData()`.
  `ProductDetailRoute` does not use OpenSearch for normal detail loads at all; it runs raw SQL in `checkVariantListingConfig()`, then `productRepository->search()`, `CategoryBreadcrumbBuilder`, `ProductConfiguratorLoader`, `loadProductTranslations()`, and `cmsPageLoader->load()`.
- SEO urls are already a materialized table (`seo_url`) read by raw SQL in `SeoResolver`.
- Caching is the HTTP cache (`CacheStore`, reverse proxy gateways for Varnish and Fastly) plus object caches (`CachedLanguageLoader`, `CachedSalesChannelContextFactory`, ...).

Write side and change signals:

- `EntityWrittenContainerEvent` after every DAL write, `EntityIndexerRegistry` runs the indexers sync or through the messenger `async` transport (`Context::USE_INDEXING_QUEUE`).
- `ProductIndexer` writes the denormalized product columns (`cheapest_price`, `category_tree`, `variant_listing_config`, `rating_average`, `available_stock`, the `*_ids` fields, ...) and then dispatches `ProductIndexerEvent`.
- The OpenSearch product index is fed from `ProductIndexerEvent` and `ProductStockAlteredEvent` (`src/Elasticsearch/Product/ProductUpdater.php`), not from the write event, so it sees the denormalized values.
- The document is built by raw SQL (`ElasticsearchProductDefinition::fetch()`), one index for all languages (ADR `2023-04-11-new-language-inheritance-mechanism-for-opensearch`), rebuilt blue/green with timestamped indices and an alias swap.
- No outbox or changelog table exists; `version_commit` is the versioning log.
- Writes that bypass the DAL (raw SQL in plugins, doc 28 counted them) emit no event and are missed by every event-based index today.

Pluggable storage pattern that already exists in core (the model for engine selection):

- `AbstractCartPersister` (SQL, Redis; `shopware.cart.storage.type`), `AbstractIncrementStorage` (SQL, Redis), `AbstractIncrementer` (MySQL, Redis, Array; per cluster), `AbstractInvalidatorStorage` (MySQL, Redis), `AbstractStockStorage` (replaceable, ADR `2023-05-15-stock-api`).
  Each is an abstract class with adapters picked by configuration and a compiler pass.

## The archived prototype `shopwareArchive/storage`

Checked in a local clone (HEAD `6d53fcf`, 2024-03-24, archived on GitHub):

- Capability interfaces: `Storage` (`setup`, `get`, `mget`, `store`, `remove`, `clear`, `destroy`), `FilterAware::filter(Criteria, StorageContext): Result`, `AggregationAware::aggregate(...)`, `SearchAware::search(...)`.
  An engine that cannot answer a query throws `NotSupportedByEngine`.
- Adapters: Array, MySQL (one table per collection, JSON columns, `JSON_VALUE`/`JSON_TABLE`, FULLTEXT), OpenSearch (translations through a script), MongoDB, Meilisearch; key-value only: Redis, DynamoDB, plus key variants of MySQL, MongoDB and Array.
- Schema: PHP attributes on typed `Document` classes (`#[Collection]`, `#[Field(type, translated, searchable)]`, `#[ListField]`, `#[ObjectField]`); translated values hold every language and are resolved against a language fallback list in `StorageContext` at read time.
- Shared abstract contract test suites (key-value, filter, aggregation, search) run against every adapter, one CI job per engine.
- Not covered: any Shopware integration, inheritance and variants, sales channels, prices per currency and rule, a write pipeline, consistency, benchmarks.
- Not installable on trunk: it requires PHP `~8.1 || ~8.2` and `doctrine/dbal ^3.6`; trunk requires PHP 8.2 to 8.5 and `doctrine/dbal ~4.4`.

Conclusion for wave 9: port the ideas (capability interfaces, `NotSupportedByEngine`, contract tests, translated values resolved at read time), not the package, and add what it never had: the Shopware product document, the pipeline from the DAL, and measurements.

## Patterns elsewhere (checked against the vendor docs)

- Spryker Publish and Synchronize (https://docs.spryker.com/docs/dg/dev/backend-development/data-manipulation/data-publishing/publish-and-synchronization): a listener builds the storefront data and saves it "to the spy_product_abstract_storage table, one row per store and locale", then sends a message to the `sync.storage.product` queue, which writes it to the key-value store (Redis or Valkey) and the search engine.
  The SQL publish table is the rebuildable source of the read store.
  A "direct synchronize" mode exists next to the queue.
- Magento mview (https://developer.adobe.com/commerce/php/development/components/indexing/): "Update on Save" reindexes right after the write; for "Update by Schedule" "the mechanism creates a record in the change log table using MYSQL triggers", processed by cron.
  Triggers also catch writes that bypass the application.
- commercetools Product Search (https://docs.commercetools.com/api/projects/product-search): the search returns product ids; for the data the docs say to "use Query ProductProjections with the returned Product IDs".
  That is the hybrid shape Shopware has today with OpenSearch, but the projection it reads is itself a read model, not the write tables.
- SEAL, the PHP search engine abstraction (`cmsig/seal` 0.12.19, 2026-10-15, on Packagist): adapters for OpenSearch, Elasticsearch, RediSearch, Meilisearch, Typesense, Loupe, Solr, Algolia and Memory.
  No MongoDB, PostgreSQL or MySQL adapter exists on Packagist.
  It is a search abstraction, not a document store, so it can at most back the search capability of one adapter.
- CDC from the binlog (Debezium) catches every write but emits rows, not aggregates, and needs Kafka Connect to run.
  Wave 9 does not build it; handoff C writes down what it would take.

## Architecture options

| | Option | Read path | Fed by | Notes |
|---|---|---|---|---|
| O0 | Today, DAL only | DAL on the write database | none | baseline |
| O0b | DAL v2 (wave 8) | DAL v2 all levers + projections on the write database (planned; the measured `dalv2` rows ran without levers, see "Correction: O0b ran without levers") | none | baseline: what core achieves without a read store or staleness |
| O1 | Today with OpenSearch | OpenSearch ids, then full DAL read | `ProductIndexerEvent`, raw SQL builder | baseline, hydration stays on SQL |
| O1+ | Composed / hybrid read store | (a) existing OpenSearch `src/Elasticsearch` searcher/aggregator serving full documents from `_source`; or (b) existing OpenSearch ids + aggregations, then `Storage::mget` from Valkey or SQL JSON | `ProductIndexerEvent` / projector | reuses existing OpenSearch query semantics (`displayGroup`, `postFilters`, analyzers); Valkey in its real production role (Spryker / commercetools shape) |
| O2 | Read store, events | full documents from one engine behind a unified query port, no DAL read | projector on `ProductIndexerEvent` / `EntityWrittenContainerEvent`, sync or queued | candidate |
| O3 | Read store with publish table | as O2 or O1+ | projector writes documents to an SQL publish table, a sync step copies them to the target engine | Spryker shape; the SQL adapter of O2 is the publish table, so O3 is O2 plus a copy step |
| O4 | CDC | as O2 | binlog or triggers | desk research only (handoff C) |

Proposed target, to be confirmed or rejected by the PoC (O1+ and O2 compared side by side, with O3 as a pipeline configuration):

```
            write model (unchanged)                         read model (new)
  Admin API / DAL writes ──> SQL database ──┐
                                            │ ProductIndexerEvent, EntityWrittenContainerEvent
                                            v
                                   Projector (sync | messenger)
                                            │ DocumentBuilder (DAL based, extensible by plugins)
                                            v
                         ReadStore port: Storage, FilterAware, AggregationAware, SearchAware
            ┌──────────────┬───────────────┬────────────┬──────────────┬──────────┐
          Array      SQL JSON (MySQL,   OpenSearch    MongoDB        Valkey
          (tests)    MariaDB, PG,       (standalone   (port check,   (KV only; also
                     SQLite; also the    or O1+       SSPL)          composed with
                     publish table)      _source)                    OpenSearch: O1+)
                                            ^
  Store API product routes ── ReadStoreGateway (extension .pre hooks, criteria bridge, capability check, DAL fallback)
                              live parts stay live: rule prices, purchase limit (stock comes from the document)
```

Outcome (added after the conclusion): the diagram above is the plan before the PoC.
The PoC rejected O2, so the `FilterAware`, `AggregationAware` and `SearchAware` capabilities and the standalone query adapters are not part of the target; the port is `Storage` only, queries stay on the existing OpenSearch code, and MongoDB stays a port validation target.
The resulting shape, together with the write side, is the diagram in `docs/46-target-architecture.md`.

Principles:

- The write model stays as decided in wave 8: DAL plus `SqlDialect` on the four SQL engines.
- The read store is a cache with a schema: it can always be rebuilt from the write database, and losing it costs a rebuild, not data.
- The document is a public read contract of its own (typed, versioned), decoupled from the table layout; that answers point 1 of "Why this wave" for the storefront read side.
- Every engine declares its capabilities; what it cannot answer falls back to the DAL, counted and logged, never silently wrong.
- Plugins extend the document through the builder (an event or tagged extender), not through the store.

## What the PoC has to answer

| # | Question | Measured by |
|---|---|---|
| Q1 | Do full documents from a read store (O1+, O2) beat O0 (`dal`), O0b (`dalv2`) and O1 (`dal-opensearch`) on detail, listing and search, per engine, and by how much? | R1 to R3b, R5 |
| Q2 | Document shape: one document per product with all languages, currencies and the price matrix resolved at read time, or one per product × sales channel × language, pre-resolved? | document size, R1 to R3, rebuild time |
| Q3 | Document builder: DAL based (plugin extensions included without extra work) or raw SQL (like OpenSearch today)? | build throughput (R7), extension probe |
| Q4 | Which DAL criteria (filters, `postFilters`, `displayGroup` collapsing, sorting, aggregations, word search) can each engine answer, what falls back, and does Shopware need a multi-engine query port (O2) or only a `Storage` port paired with existing OpenSearch (O1+)? | capability matrix from the contract suite and the Store API criteria corpus |
| Q5 | Consistency: lag from write to readable, sync vs queued, which writes are missed (raw SQL, stock changes, parent-to-variant inheritance updates, indexer-only writes, deletes, version merges)? | R6, miss probes |
| Q6 | What must stay live at read time (rule prices, customer group prices, stock, availability, cart rules) — both at display time (for the page) and at query time (filtering, sorting and min/max price aggregations across the catalog before pagination) — and what does that cost? | R1 to R3b with live parts on and off, rule-price query probe |
| Q7 | Does it scale: throughput and p95 under concurrency, the write database's load with and without the read store, a large catalogue | R5 on two dataset sizes |
| Q8 | Effort, API and extension story: how plugins and apps add fields, what changes for the Store API, BC | handoff F estimate |

Scenarios (the wave 8 harness and contract are reused, S1 to S3 results must equal the DAL result, see `docs/30-orm-spike-baseline.md`):

- R1 detail: S2 (one variant with inherited data).
- R2 listing: S1 (24 products of one category, page 2, total).
- R3 substring filter + aggregations: S3 unchanged for wave 8 comparability (`ContainsFilter('name', 'LI')`, manufacturer pre-filter, total, min/max price and manufacturer terms aggregations). Note: S3 tests `FilterAware` substring matching, not full-text word search.
- R3b storefront search: real word search (`Criteria::setTerm()`), manufacturer as `postFilter` (so the manufacturer terms aggregation stays unfiltered while hits are filtered), `FieldGrouping('displayGroup')` (variant collapsing), total, min/max price and manufacturer terms aggregations. Exercises `SearchAware`, faceted aggregations and variant collapsing.
- R4 batch by id: `mget` of 24 ids (cross selling, wishlist, cart).
- R5 load: R1/R2/R3b mixed, 1, 8 and 32 concurrent pre-booted worker processes, throughput, p95, and CPU of the write database container.
- R6 lag: write a product, poll until the read store returns the new value; sync and queued mode.
- R7 rebuild: full rebuild time, documents per second, store size per engine.

Datasets: `orm_spike` as in wave 8 (3,000 simple products, 400 parents with 4 variants = 5,000 rows) for correctness and comparison with docs 30 to 35, and `read_store_large` (target 100,000 simple products, 10,000 parents with 4 variants = 150,000 rows; or 50,000 / 5,000 = 75,000 rows if seeding exceeds budget, documented by P) for R5 and R7.

## Plan

Handoffs (work packages for parallel sessions, `handoffs/wave9/`):

| Handoff | Topic | Doc | Can run in parallel with |
|---|---|---|---|
| P | Branch, OpenSearch and MongoDB containers, `mongodb` PHP extension, large dataset, harness extension (R3b, R4 to R7, implementation ids per store and composed O1+), O0 (`dal`), O0b (`dalv2`) and O1 (`dal-opensearch`) baseline timings | `docs/39-read-store-baseline.md` | nothing until "branch ready", then K; others wait for "harness ready" |
| K | Port (capability interfaces incl. `displayGroup` collapse and `postFilters`, store criteria, `NotSupportedByEngine`), product document and its schema aligned with `SalesChannelProductEntity` runtime fields (Q2), DAL and SQL document builders (Q3), projector (sync and queued), rebuild command, Array adapter, contract test suite, DAL criteria bridge + 20-criteria corpus | `docs/40-read-store-port-and-document.md` | P after "branch ready"; S/O/M wait for "port ready" to code adapters, R/C (and S/O/M verify/rebuild) wait for "pipeline and bridge ready" |
| S | SQL JSON adapter on MySQL, MariaDB, PostgreSQL and SQLite through `SqlDialect` (JSON columns, generated columns or expression indexes for filter fields), usable as publish table (O3) | `docs/41-read-store-sql.md` | O, M, R, C |
| O | OpenSearch adapter: own adapter vs O1a (reuse existing `src/Elasticsearch` searcher/aggregator + `_source` document hydration) vs SEAL, pick by the contract suite and timings | `docs/42-read-store-opensearch.md` | S, M, R, C |
| M | MongoDB adapter (time-boxed port-validation target, SSPL) and Valkey key-value adapter (standalone R1/R4 plus O1b composed OpenSearch IDs + Valkey `MGET`) | `docs/43-read-store-mongodb-valkey.md` | S, O, R, C |
| R | Read integration: `ReadStoreGateway` via `ExtensionDispatcher` `.pre` hooks (`ProductDetailRouteExtension`, `ResolveListingExtension`, `ProductSearchRouteExtension`), document to `SalesChannelProductEntity` vs DTO response, live parts display-time & query-time (Q6), surrounding route SQL accounting, fallback, Store API response equality | `docs/44-read-store-integration.md` | S, O, M, C |
| C | Consistency and extensibility: R6 lag, miss probes (incl. parent-to-variant inheritance updates), plugin extension probe, rebuild blue/green, O3 copy step, CDC and trigger desk research (O4) | `docs/45-read-store-consistency.md` | S, O, M, R |
| F | One timing block with O0 (`dal`), O0b (`dalv2`), O1 (`dal-opensearch`), O1+ (composed) and every store, Q1 to Q8 answered, effort estimate, conclusion in this doc, `docs/summary.md`, issue drafts | this doc, "Conclusion" | nothing, runs alone and last |

Order: P alone until "branch ready"; then K (with two commits: "port ready" unblocks S, O, M coding; "pipeline and bridge ready" plus P's "harness ready" unblocks R, C and adapter verify/rebuild); F alone at the end.

Out of scope: Meilisearch, DynamoDB, Typesense (the port must allow them, the PoC does not build them), CDC implementation, the admin search index, CMS and navigation documents (named as next candidates in F), production hardening.

## Conclusion

Short answer: a read store pays off, but not as a new multi-engine query layer.
Keep query execution (filters, `postFilters`, `displayGroup` collapsing, aggregations, word search) on the existing OpenSearch code in `src/Elasticsearch`.
Replace only the SQL hydration that follows it with full product documents, read by id through a narrow `Storage` port (O1+).
OpenSearch `_source` comes first, Valkey `MGET` second.
SQL JSON is an optional detail and `mget` store, or a publish table, for shops without extra infrastructure.
Do not build a unified query port (O2) in core.

### Final timing block (handoff F)

Conditions:

- Date and setup: 2026-11-24, branch `poc/read-store` at `91b22d0abbb`, MySQL 8.4 write database (`instance-mysql-1`), `APP_ENV=prod`, warm cache.
- Other lanes stopped: yes (47 containers stopped for the whole block, restored afterwards).
- Host load average was 16.0 at the start of part 1 and between 5.5 and 20.3 during part 2. The load comes from the benchmark's own containers and workers, because the other lanes were stopped. Treat ratios as the result and absolute values as indicative.
- Script: `/tmp/wave9-f-final-bench.sh`. Every store was rebuilt from the same database state first.
- Every scenario ran with `--verify` against `dal` before it was timed.
- `dalv2` ran with its default options, so without any wave 8 lever (see "Correction: O0b ran without levers" below).
- `orm_spike` ran 5 warm-ups and 50 iterations per scenario.
- `read_store_large` ran 5 warm-ups and 50 iterations for S2 and R4, and 3 warm-ups and fewer iterations for S1, S3 and R3b. The slow DAL cells take seconds per run.

`--verify` result:

- Every store is equal to `dal` on S1, S2, S3 and R4 on both datasets.
- On R3b every store differs from `dal` by the same amount: manufacturer aggregation 71 against 73 on `orm_spike`, and 2,167 against 2,169 on `read_store_large`. This is the DAL over-count of core finding 36 (`docs/39-read-store-baseline.md` "O1 `--verify` differences"). The stores return the distinct count, which is the contract result.
- `dal-opensearch` (O1) differs on `orm_spike` S1, S3 and R3b for the known reasons in doc 39: parents with variants are not indexed, a sort tie on multi-valued `productNumber`, and finding 36.
- `dalv2` is equal to `dal` everywhere.

Median / p95 in ms, statements on the write database per run in brackets. A dash means the store does not support the scenario.

`read_store_large` (150,000 products):

| Implementation | S1 listing | S2 detail | S3 filter + aggs | R3b search | R4 mget 24 |
|---|---|---|---|---|---|
| O0 `dal` | 137.44 / 146.00 (4) | 6.15 / 7.45 (5) | 2,988.95 / 4,389.80 (7) | 1,222.48 / 1,375.92 (9) | 11.94 / 12.98 (5) |
| O0b `dalv2` | 147.38 / 173.18 (4) | 6.89 / 7.67 (5) | 3,249.19 / 3,619.71 (7) | 1,316.89 / 1,572.99 (9) | 12.98 / 15.02 (5) |
| O1 `dal-opensearch` | 15.11 / 19.22 (2) | 10.98 / 14.30 (4) | 19.42 / 27.12 (2) | **25.54 / 32.69** (2) | 15.82 / 20.04 (4) |
| `store-opensearch` | **9.87** / 24.86 (0) | 1.25 / 2.11 (0) | **18.58** / 43.39 (0) | 573.81 / 1,270.98 (2) | 7.84 / 18.83 (0) |
| `store-opensearch-valkey` (O1b) | 11.81 / 23.99 (0) | 0.15 / 0.20 (0) | 19.70 / 35.03 (0) | 582.72 / 782.83 (2) | 0.80 / 1.01 (0) |
| `store-mongodb` | 36.05 / 46.66 (0) | 0.25 / 0.33 (0) | 198.94 / 212.90 (0) | 954.61 / 1,256.36 (2) | 0.96 / 1.23 (0) |
| `store-valkey` | – | 0.15 / 0.23 (0) | – | – | **0.66** / 0.98 (0) |
| `store-sql-mysql` | 67.39 / 71.19 (0) | **0.14** / 0.26 (0) | 10,730.31 / 11,361.67 (0) | 798.40 / 856.49 (2) | 1.19 / 1.29 (0) |
| `store-sql-pgsql` | 801.13 / 952.04 (0) | 0.27 / 0.42 (0) | 4,026.09 / 4,402.35 (0) | 5,503.11 / 5,878.74 (2) | 1.46 / 1.95 (0) |

The MariaDB and SQLite SQL JSON stores were left out at 150,000 products.
Their sanity run already put S1 at 15.1 s and 5.8 s, and SQLite R3b did not finish in 315 s (`docs/41-read-store-sql.md`).

`orm_spike` (5,000 products):

| Implementation | S1 | S2 | S3 | R3b | R4 |
|---|---|---|---|---|---|
| O0 `dal` | 14.39 / 27.20 (4) | 13.53 / 23.11 (5) | 109.02 / 177.19 (7) | 71.38 / 125.34 (9) | 15.20 / 28.95 (5) |
| O0b `dalv2` | 26.32 / 42.92 (4) | 7.69 / 11.69 (5) | 131.53 / 245.80 (7) | 82.42 / 123.92 (9) | 17.22 / 36.73 (5) |
| O1 `dal-opensearch` | 19.97 / 34.04 (2) | 11.84 / 24.86 (4) | 18.10 / 28.80 (2) | **19.31** / 30.62 (2) | 15.73 / 18.99 (4) |
| `store-opensearch` | 7.22 / 8.11 (0) | 0.75 / 1.13 (0) | **9.46** / 12.43 (0) | 26.50 / 36.97 (2) | 6.38 / 10.58 (0) |
| `store-opensearch-valkey` | 7.52 / 11.56 (0) | 0.16 / 0.21 (0) | 9.86 / 12.68 (0) | 33.24 / 79.41 (2) | 0.64 / 1.58 (0) |
| `store-mongodb` | **6.58** / 10.88 (0) | 0.31 / 1.63 (0) | 18.59 / 26.43 (0) | 47.49 / 75.79 (2) | 4.31 / 8.27 (0) |
| `store-valkey` | – | 0.14 / 0.21 (0) | – | – | 0.57 / 0.73 (0) |
| `store-sql-mysql` | 11.00 / 20.63 (0) | 0.87 / 2.00 (0) | 78.60 / 106.76 (0) | 47.89 / 80.12 (2) | 1.66 / 4.51 (0) |
| `store-sql-pgsql` | 33.94 / 54.63 (0) | 0.24 / 0.37 (0) | 187.72 / 306.19 (0) | 329.65 / 427.27 (2) | 1.98 / 2.30 (0) |
| `store-sql-mariadb` | 399.43 / 653.19 (0) | 0.20 / 0.30 (0) | 118.30 / 123.10 (0) | 223.59 / 259.68 (2) | 0.78 / 0.88 (0) |
| `store-sql-sqlite` | 176.08 / 190.13 (0) | **0.05** / 0.06 (0) | 273.17 / 372.55 (0) | 4,492.98 / 8,474.88 (2) | **0.46** / 0.81 (0) |

R5 mixed load on `read_store_large`:

- Mix: 50 % R1, 30 % R2, 20 % R3b, 20 s per step (doc 39 ran 60 s), 0 errors in every step.
- Write database CPU is the CPU time of `instance-mysql-1` during the step.
- For `store-sql-pgsql`, the PostgreSQL CPU is not counted.

| Implementation | c=1 req/s, p95 ms, MySQL CPU s | c=8 req/s, p95 ms, MySQL CPU s / duration | c=8 p50 R1 / R2 / R3b ms | statements / request |
|---|---|---|---|---|
| O0 `dal` | 3.2, 1,338.5, 19.7 | 10.4, 3,331.5, 136.8 / 21.8 s | 7.2 / 236.5 / 2,919.1 | 5.3 |
| O0b `dalv2` | 3.1, 1,391.3, 20.1 | 10.3, 3,298.3, 135.5 / 21.3 s | 7.4 / 249.8 / 3,074.5 | 5.3 |
| O1 `dal-opensearch` | 63.3, 32.1, 3.2 | **453.8, 35.4, 19.4 / 20.1 s** | 10.9 / 16.5 / 27.0 | 2.7 |
| `store-opensearch` | 8.6, 577.0, 16.2 | 19.0, 2,083.0, 122.8 / 21.7 s | 1.6 / 16.3 / 1,890.4 | 0.4 |
| `store-opensearch-valkey` | 7.2, 701.1, 16.2 | 20.5, 1,925.0, 119.6 / 20.6 s | **0.1** / 17.4 / 1,772.4 | 0.4 |
| `store-mongodb` | 5.3, 934.8, 10.5 | 19.6, 1,998.9, 100.5 / 21.2 s | 0.5 / 44.2 / 1,871.5 | 0.4 |
| `store-sql-mysql` | 5.1, 869.9, 20.0 | 16.6, 2,238.8, 137.0 / 21.1 s | 0.2 / 94.8 / 2,107.5 | 0.4 |
| `store-sql-pgsql` | 0.7, 6,262.0, – | 1.1, 28,554.0, – / 32.0 s | 1.4 / 1,728.3 / 15,801.1 | 0.6 |

At c=32, O1 reaches 460.3 req/s with p95 137.5 ms and 21.6 s of MySQL CPU in 20.4 s.
Throughput is flat from c=8 to c=32, and the write database uses about one core.

The R3b column explains every standalone store row.
The harness builds R3b through the storefront's SQL `ProductSearchBuilder`, as the storefront does, and only then calls the store (`StoreImplementation`, `docs/42-read-store-opensearch.md` "O1 / O1a versus standalone").
The 2 statements left are `LIKE` queries on `product_search_keyword`.
At c=8 they take 100 to 137 s of MySQL CPU in about 21 s, so about 4.7 to 6.5 of the 8 cores, which is close to the DAL's load (6.3 cores).
O1 sends the term to OpenSearch (`buildTermQuery`) and pays only the 2 hydration statements.
A standalone store that keeps the SQL keyword interpreter does not take search load off the write database.

R7 rebuild on `read_store_large` (same state):

| Store | Time | Documents | Docs/s | Statements on the write DB | Size (from doc) |
|---|---|---|---|---|---|
| O1 `es:index` | 72.8 s | 126,000 | 1,730 | 0 in this process | 192.3 MiB |
| `store-valkey` | 45.6 s | 150,000 | 3,288 | 6,004 | 780.7 MiB RAM (doc 43) |
| `store-mongodb` | 80.3 s | 150,000 | 1,868 | 6,004 | 351.6 MiB disk (doc 43) |
| `store-opensearch` | 122.0 s | 150,000 | 1,229 | 6,004 | 454.0 MB (doc 42) |
| `store-sql-mysql` | 125.9 s | 150,000 | 1,191 | 6,004 | 1,576.0 MiB (doc 41) |
| `store-sql-pgsql` | 127.8 s | 150,000 | 1,173 | 6,004 | 727.4 MiB (doc 41) |
| `store-opensearch-valkey` | 131.9 s | 150,000 | 1,137 | 6,004 | 442.4 MB + 808.0 MiB RAM (doc 43) |

The F block did not measure store sizes (the command prints "n/a"), so the sizes come from the adapter docs on the same dataset.
R6 lag was not rerun in F. The numbers under Q5 come from handoff C on the same branch and commit (`91b22d0abbb`).

### Q1: do full documents beat O0, O0b and O1?

Yes for detail and batch reads, on every engine.
For listing and search they win only when the query runs on OpenSearch.
O1 already gets most of the gain, and a document store on top of it removes only the hydration.

| Read (150k, median) | O0 `dal` | O0b `dalv2` | O1 | Best document read | Factor vs O0 / O0b / O1 |
|---|---|---|---|---|---|
| R1 / S2 detail | 6.15 ms | 6.89 ms | 10.98 ms | 0.14 ms (`sql-mysql`), 0.15 ms (Valkey, O1b) | 44x / 49x / 78x |
| R4 mget 24 | 11.94 ms | 12.98 ms | 15.82 ms | 0.66 ms (Valkey), 0.80 ms (O1b) | 18x / 20x / 24x |
| R2 / S1 listing | 137.44 ms | 147.38 ms | 15.11 ms | 9.87 ms (`store-opensearch`) | 14x / 15x / 1.5x |
| S3 filter + 7 aggs | 2,988.95 ms | 3,249.19 ms | 19.42 ms | 18.58 ms (`store-opensearch`) | 161x / 175x / 1.05x |
| R3b word search | 1,222.48 ms | 1,316.89 ms | **25.54 ms** | 573.81 ms (`store-opensearch`) | 2.1x / 2.3x / 0.04x (O1 is 22x faster) |

What the table shows:

- O0b as measured is DAL v2 without levers, so this table says nothing about DAL v2 with levers at 150,000 products (see "Correction: O0b ran without levers"). Without levers `dalv2` is 5 to 12 % slower than `dal` on every scenario here. On `orm_spike` it is 1.8x faster on S2 and 1.8x slower on S1. The wave 8 levers target statement count and hydration, not the unindexed keyword and aggregation SQL that dominates at this size, so a large change is not expected, but it is not measured.
- Detail and `mget` are key-value reads. Every store answers them in under 1.5 ms with 0 SQL, the SQL JSON table on MySQL included.
- Listing, filters and aggregations need a search engine at 150,000 products:
  - `store-opensearch` is equal to or slightly faster than O1.
  - MongoDB is 2 to 10x slower than O1.
  - SQL JSON is 4x (MySQL S1) to 550x (MySQL S3) slower than O1 (`docs/41-read-store-sql.md` "Verdict").
- Search is won by O1, because it uses OpenSearch's own term query.
- End to end over HTTP on `orm_spike`, the read store saves up to 28 ms on detail (49.76 to 21.77 ms) and 22 ms on listing (56.71 to 34.85 ms). Search over HTTP is fastest on O1 (49.84 ms against 104.99 ms on the DAL). About 19 to 28 ms per request is fixed route and framework cost (`docs/44-read-store-integration.md` "Real Store API HTTP timings").

#### Correction: O0b ran without levers

Found in a doc review on 2026-11-24, after the conclusion was written.
Neither `scripts/read-store-baseline.sh` (doc 39) nor `/tmp/wave9-f-final-bench.sh` (this block) passes `--option` for `dalv2`, and `DalV2Implementation` turns a lever on only through an option (`count=window`, `agg=stats`, `write=key+upd`, `proj=1`, `shape`).
The R5 load worker (`LoadWorkerCommand`) calls `configure([])`, so the Q7 load rows cannot have levers either.
Every wave 9 `dalv2` number is therefore DAL v2 with its default options, not "all levers and projections".
The O1+ recommendation does not depend on it: O1 is 9 to 167x faster than O0 and O0b on R2, S3 and R3b in the Q1 table, and even the best wave 8 lever gain of 3.3x (`docs/34`) would leave O1 ahead on all three.
The claim "DAL v2 does not change storefront reads at 150k" is not proven until `dalv2` with the wave 8 lever set runs on `read_store_large` (wave 10 handoff D).

### Q2: document granularity

| Layout | Documents (150k) | Median size | Total | Decision |
|---|---|---|---|---|
| (a) one per product, all languages, currencies and rule prices | 150,000 | 4,488 B | 691.51 MiB | **chosen** |
| (b) one per product × sales channel × language, visible only | 270,000 | 3,693 B | 1,008.30 MiB (1.46x) | rejected |
| (b) all | 600,000 | 3,695 B | 2,265.95 MiB (3.28x) | rejected |

Source: `docs/40-read-store-port-and-document.md` "Q2".
Layout (b) makes one document 18 % smaller but multiplies document count and write amplification by sales channels × languages.
It saves 3 µs per decode, and it can always be derived from (a).
Layout (a) matches the OpenSearch language-inheritance ADR of 2023-04-11.

### Q3: document builder

| Builder | 150k rebuild | Docs/s | Peak memory | Statements per 500 | Output |
|---|---|---|---|---|---|
| `SqlDocumentBuilder` | 28.32 s | 5,296.5 | 74.0 MiB | 21 / 19 | equal |
| `DalDocumentBuilder` | 132.55 s | 1,131.6 | 146.5 MiB | 15 / 13 | equal |

Source: `docs/40-read-store-port-and-document.md` "Q3". Output is equal: 0 diffs on 5,000 documents, and the same SHA-256 over 1,000 documents at 150k.
Use the raw SQL builder for core fields, which is how OpenSearch is fed today.
Plugin data goes through `DocumentExtender`, which runs on both builders with batched ids.
End-to-end rebuild (R7) takes 45.6 to 131.9 s for 150,000 products. It is bound by the store's write speed, not by the builder's 28 s.

### Q4: capabilities, and O2 against O1+

| Store | Criteria corpus (35): match / DAL defect / fallback | Can answer at 150k | Throws `NotSupportedByEngine` for |
|---|---|---|---|
| OpenSearch (port adapter) | 27 / 5 / 3 | everything, fast | collapse by `cheapestPrice` descending, more than 40,000 groups, `Terms` with other docs |
| OpenSearch + Valkey | 27 / 5 / 3 | same, hydration from Valkey | as OpenSearch, plus a hit without a document |
| MongoDB | 28 / 5 / 2 | everything, S3 10x slower than OpenSearch | list sorting, collapse on lists and custom fields, string min/max |
| SQL JSON (4 dialects) | 28 / 5 / 2 | detail and `mget` only; listing and aggregations too slow | operations on lists and custom fields, collapse on non-id fields |
| Valkey | 0 / 0 / 35 | detail and `mget` only | every query |

Sources: docs 41, 42 and 43, "Capability matrix" and corpus.
The 5 "DAL defect" entries are search route entries hit by finding 36.

On top of the adapters, the criteria bridge rejects several DAL constructs (doc 40 "Criteria bridge"):

- `TOTAL_COUNT_MODE_NEXT_PAGES`
- more than one group field
- `CountSorting`
- sorted or nested terms aggregations
- non-keyword score queries
- nested and payload fields

The stores give no partial answers.
`--verify` is equal on every supported scenario except R3b, where every store differs from the DAL by the finding 36 over-count (see the F block `--verify` result).

O1+ against O2:

| | O1+ (`Storage` port + existing `src/Elasticsearch`) | O2 (unified multi-engine query port) |
|---|---|---|
| Query semantics | already in core: `CriteriaParser`, `postFilters`, native `collapse`, analyzers, `buildTermQuery`, all DAL aggregations (doc 42 "Comparison") | reimplemented per engine. 1,916 lines for OpenSearch, 2,240 for SQL, 1,179 for MongoDB in the PoC, plus the 479-line criteria bridge |
| Search | native term query: R3b 25.5 ms | the port's `SearchAware` reproduces the DAL score with a script and still needs the SQL keyword interpreter: R3b 574 ms, write database saturated at c=8 |
| New code in core | `Storage` port (9 methods), document, builder, projector, `_source` or `MGET` hydration | all of O1+, plus the capability interfaces, the bridge, and per-engine compilers, search and contract suites |
| What a second engine adds | nothing a shop measured here needs: SQL JSON and MongoDB are slower than OpenSearch on every query scenario | portability to engines that lose to OpenSearch at 150k |

Answer: Shopware needs only the `Storage` port paired with the existing OpenSearch code.
The capability interfaces (`FilterAware`, `AggregationAware`, `SearchAware`) did their job in the PoC: they proved the document works on five engines and found the gaps.
They should not become core API.

### Q5: consistency

| Mode | `get()` lag p50 / p95 / max | Missed writes |
|---|---|---|
| sync, SQL JSON MySQL | 0.4 / 0.6 / 1.4 ms | 0 of 50 |
| sync, Valkey | 0.2 / 0.3 / 0.8 ms | 0 of 50 |
| sync, OpenSearch (`get` is realtime) | 1.8 / 3.1 / 11.2 ms | 0 of 50 |
| sync, OpenSearch search with `refresh_interval=1s` | p50 760.7 ms, p95 794.9 ms | – |
| queue (`--sleep=0.05`), OpenSearch | 264.2 / 507.8 / 800.1 ms | 0 of 25 |
| queue, Valkey | 24.5 / 190.0 / 263.2 ms | 0 of 25 |

Source: `docs/45-read-store-consistency.md` sections 1 and 2.

Miss probes (doc 45 section 2):

- The projector listens to the same signals as `ProductUpdater`, plus the C fixes (about 90 lines). With them it catches 15 of the 18 probes in the doc 45 table (the doc's text says 14 of 17):
  - parent-to-variant inheritance
  - sibling `cheapestPrice`
  - `StockStorage::alter`
  - version merge
  - deletes
  - manufacturer, property and media renames
- Three misses are structural:
  - raw SQL writes. 54.6 % of Store plugins contain raw SQL (`docs/28-plugin-sql-inventory.md`).
  - tax rate changes
  - currency factor changes
- Fixes for the misses:
  - Tax and currency changes touch every product. They need an async blue/green rebuild (46 to 132 s at 150k, R7 above), not inline fan-out.
  - Raw SQL needs a `schedule($ids)` call in the plugin, or a nightly reconciliation rebuild.
- Blue/green rebuild under c=4 load works with 0 errors on SQL and OpenSearch. MongoDB had 1 error because `swap()` drops the old generation while a cursor still reads it, so the old generation needs a grace period (E6.06).

CDC (O4) is the only mechanism that also catches raw SQL.
It costs triggers on every product table (Magento `mview`) or Debezium plus a broker, so it is not a phase 1 item (doc 45 section 6).

### Q6: live parts

| Part | Display time | Query time (filter, sort, min/max before pagination) |
|---|---|---|
| Price calculation, tax, rounding, customer-group display | live in PHP (`ProductSubscriber`), under 1 to 2 ms per 24 products, 0 extra SQL warm | – |
| Base and rule prices | live | from `cheapestPrice.<ruleId>.<currencyId>` buckets in the document. Correct only when the context rounding equals the currency rounding; otherwise `NotSupportedByEngine` and the DAL answers |
| App script and cart-rule prices | live | not possible in any store (same limit as SQL `cheapest_price` and O1 today) |
| Stock, availability, closeout | from the document snapshot, not live; only `calculatedMaxPurchase` is recalculated from the snapshot values | eventually consistent. A sold-out closeout can be listed during the lag; checkout validates against SQL |

Source: `docs/44-read-store-integration.md` "Live parts".

With live prices and stock on, R1 costs 8.58 ms and with both off 6.78 ms, on `orm_spike` through the gateway.
"Live stock" is the `liveStock` switch of the gateway: it runs `ProductMaxPurchaseCalculator` on the snapshot values, it does not read stock from SQL.
So live parts cost about 2 ms on detail and nothing on listing (16.56 against 17.09 ms). Search was 63.69 against 54.79 ms, a 9 ms difference that was not investigated, measured with other lanes running.
The rest of the route stays on SQL:

- Detail: 5 to 23 statements (breadcrumb, configurator, CMS page).
- Listing and search: 8 statements, the search ones including the keyword interpreter.

### Q7: scale

| Load (150k, c=8) | Throughput | p95 | Write DB cores used |
|---|---|---|---|
| O0 `dal` | 10.4 req/s | 3,331.5 ms | 6.3 |
| O0b `dalv2` | 10.3 req/s | 3,298.3 ms | 6.4 |
| O1 | **453.8 req/s** | 35.4 ms | **1.0** |
| standalone stores (SQL keyword interpreter kept) | 16.6 to 20.5 req/s | 1,925 to 2,239 ms | 4.7 to 6.5 |
| O1b detail only (R1 p50 inside the mix) | 0.1 ms | 2.7 ms | – |

Source: F block above.
The write database is the limit for O0 and O0b at c=8; DAL v2 without levers does not move it, DAL v2 with levers was not run under load (see "Correction: O0b ran without levers").
O1 removes 86 % of that load, from 136.8 to 19.4 CPU seconds, while serving 44 times as many requests.
The remaining 2.7 statements per request are the hydration that O1+ removes.
Throughput stays flat at c=32 (460.3 req/s), so the next limit is the PHP workers and the host, not the database.

At c=8, the standalone stores serve detail and listing reads faster than O1:

| c=8 p50 | R1 detail | R2 listing |
|---|---|---|
| O1 | 10.9 ms | 16.5 ms |
| `store-opensearch-valkey` | 0.1 ms | 17.4 ms |

R3b's SQL keyword search holds their total throughput back, so the bottleneck is the search path, not the document store.

Rebuild of 150,000 products takes 46 to 132 s on every store, with 6,004 statements on the write database.

### Q8: effort, API and extensions

Method:

- Base: the PoC's line counts per component on `poc/read-store` `91b22d0abbb` (`src/Core/Framework/ReadStore/`):
  - Port: 1,111
  - Document: 395
  - Builder: 1,648
  - Projector: 598
  - Bridge: 479
  - Integration: 1,733
  - Adapters: SQL 2,240, OpenSearch 1,916, MongoDB 1,179, Valkey 243, composed 136, Array 280
- These are PoC lines, not product lines. The estimate assumes about 2 to 3x the work for production quality: BC layer, admin and config, error handling, migration, docs, review, and integration tests on all supported databases.
- Calibration: wave 8 (`docs/29-orm-alternatives.md` "Conclusion").
- Units: person-weeks for one experienced core developer, as a range. This is a judgement, not a measurement.

| Work package | O1+ | O2 | Basis |
|---|---|---|---|
| `Storage` port, `ProductDocument` schema and versioning, `DocumentExtender` (E6.01) | 3–5 | 5–8 | Port + Document; O2 also needs the capability interfaces and `StoreCriteria` |
| `SqlDocumentBuilder`, projector with C fixes, blue/green rebuild, grace GC (E6.02, E6.06) | 5–8 | 5–8 | Builder + Projector, 18 miss probes |
| OpenSearch `_source` hydration in `src/Elasticsearch`: full document in `_source`, hydration in `ElasticsearchEntitySearcher` (E6.03) | 4–7 | – | doc 42 "O1a versus O2": the flag exists, the indexer document must grow to the full product document |
| OpenSearch query adapter on the port | – | 6–10 | 1,916 lines, Painless score, collapse limits |
| Valkey `Storage` adapter (E6.03) | 1–2 | 1–2 | 243 lines, key-value only |
| SQL JSON `Storage` only (no-infra detail / `mget`, publish table) | 1–2 | – | the `get` / `mget` / `store` part of the SQL adapter |
| SQL JSON query adapter on 4 dialects | – | 6–10 | 2,240 lines, dialect gaps (doc 41) |
| MongoDB adapter | – | 3–5 (optional, SSPL review) | 1,179 lines |
| Criteria bridge for the full storefront criteria set | – | 4–8 | 479 lines today, several constructs still fall back |
| Native word search per engine (no SQL keyword interpreter) | – (OpenSearch has it) | 4–8 | R3b result above |
| Route integration: `.pre` hooks, entity hydration, live parts, fallback and circuit breaker (E6.04) | 4–6 | 4–6 | Integration, 1,733 lines |
| Surrounding route SQL (breadcrumb, configurator, CMS) (E6.05) | 3–5 | 3–5 | doc 44 "Surrounding SQL accounting" |
| Plugin and app docs, upgrade guide | 1–2 | 2–3 | – |
| **Total, products** | **22–37** | **40–68** (43–73 with MongoDB) | |
| Next: category and navigation document | 4–6 | 6–9 | tree, SEO paths, visibility per sales channel |
| Next: CMS page document | 6–10 | 8–12 | slots and resolver data are dynamic per request |
| Next: SEO URLs (key-value) | 2–4 | 2–4 | pure `Storage` use |

Plugins and apps:

- Custom fields reach the document without code. The test filter on `customFields.sample_tag` returned the same total on the Array, SQL MySQL, OpenSearch and MongoDB stores (doc 45 section 3).
- Entity extensions need a `DocumentExtender` of about 30 lines.
- Plugins that write with raw SQL need about 15 lines to call `ReadStoreProjector::schedule($ids)`.
- Store API responses stay `SalesChannelProductEntity` (shape (a)), so subscribers, app scripts and Twig keep working. The 50-request equality check was 50 of 50 on SQL JSON and 47 of 50 on OpenSearch, where 3 differ only in price tie order and 5 fell back by design (doc 44).
- The DTO shape (b) is 4x smaller but breaks `ProductDetailRouteResponse` and the `salesChannelLoaded` subscribers. Use it only for new headless endpoints.
- What breaks for plugins:
  - criteria the bridge cannot translate (custom joins in `ProductListingCriteriaEvent`) fall back to the DAL, counted
  - raw SQL writers see stale documents until `schedule($ids)` or the next reconciliation

### Recommendation

| Option | Verdict |
|---|---|
| O0b (DAL v2 only) | keep building it for the write path and the admin (wave 8); without levers it does not change storefront reads at 150k, with levers it is not measured at 150k |
| O1 (today with OpenSearch) | already the best search path. Its 2 to 4 hydration statements per request are the remaining write database load |
| **O1+** | **recommended**: `Storage` port + full `ProductDocument` + projector, hydration from OpenSearch `_source` first, Valkey `MGET` as the second adapter for detail and `mget` at about 0.15 ms |
| O2 | not in core. Twice the effort for engines that lose to OpenSearch on every query scenario at 150k, and its search still needs SQL |
| O3 (publish table) | only when one builder feeds two or more stores: +1.58 GiB on MySQL and +1 to 8 ms lag (doc 45 section 5) |
| O4 (CDC) | later, only as an Enterprise or SaaS option if raw SQL plugin writes must be caught within seconds |

Engines in order:

1. OpenSearch `_source`, no new infrastructure for shops that already run OpenSearch.
2. Valkey, already in most production setups as cache, for detail, cross-selling, wishlist and cart (`mget`).
3. SQL JSON as `Storage` only: a no-extra-infrastructure detail and `mget` store (S2 0.14 ms, R4 1.19 ms on MySQL at 150k), and the publish table of O3. Not a query engine.

MongoDB stays a port validation target: it is fast, but the SSPL and extra infrastructure are not justified when OpenSearch is faster on queries.

What would change the recommendation:

- Shopware stops supporting OpenSearch for the storefront, or targets shops without it. Then O1+ falls back to O0b plus SQL JSON `Storage` for detail and `mget`, and listing and search stay on the DAL, which limits the read store to R1 and R4.
- The full product document does not fit OpenSearch `_source` in production: mapping limits with many custom fields (doc 45 section 3), or index size. Then Valkey (or SQL JSON) becomes the first `Storage` adapter and OpenSearch keeps ids and aggregations only (O1b).
- A product requirement for one engine without OpenSearch at catalog scale (for example a MongoDB or PostgreSQL-only SaaS stack). Only that would justify O2, and the PoC shows PostgreSQL JSON is not enough for that at 150k (S1 0.8 s, R3b 5.5 s).
- Raw SQL plugin writes turn out to be common on hot product data. Then CDC (O4) moves from optional to required.

Issue drafts: epic `docs/issues/E6-read-store/` (E6.01 to E6.07).
Core findings: 36 to 40 in `docs/core-findings.md`.
